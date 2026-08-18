"""Safe, deterministic and immutable raw archive ingestion."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import IO, Any

from radariq.configs import load_config
from radariq.data.acquisition import sha256_file

RAW_INGESTION_SCHEMA_VERSION = "1.0"
DEFAULT_CHUNK_SIZE_BYTES = 1024 * 1024


class RawIngestionError(RuntimeError):
    """Raised when an archive cannot become a complete raw stage."""


class RawMutationError(RawIngestionError):
    """Raised when an existing immutable raw stage has changed in place."""


class IngestionStatus(StrEnum):
    CREATED = "created"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class RawIngestionConfig:
    """Location and immutable identity of one acquired source archive."""

    archive_path: Path
    raw_root: Path
    source_id: str
    source_version: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        base_directory: Path,
    ) -> RawIngestionConfig:
        archive_path = _required_path(value, "archive_path", base_directory)
        raw_root = _required_path(value, "raw_root", base_directory)
        source_id = _safe_identity(value.get("source_id"), "source_id")
        source_version = _safe_identity(value.get("source_version"), "source_version")
        return cls(
            archive_path=archive_path,
            raw_root=raw_root,
            source_id=source_id,
            source_version=source_version,
        )

    @property
    def stage_path(self) -> Path:
        return self.raw_root / self.source_id / self.source_version


@dataclass(frozen=True, slots=True)
class RawIngestionResult:
    status: IngestionStatus
    stage_path: Path
    manifest_path: Path
    manifest_sha256: str
    sample_count: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "status": self.status.value,
            "stage_path": str(self.stage_path),
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "sample_count": self.sample_count,
        }


def ingest_from_config(config_path: str | Path) -> RawIngestionResult:
    """Load a JSON-compatible config and ingest its acquired archive."""

    path = Path(config_path).expanduser().resolve()
    config = RawIngestionConfig.from_mapping(load_config(path), base_directory=path.parent)
    return ingest_archive(config)


def ingest_archive(config: RawIngestionConfig) -> RawIngestionResult:
    """Publish a new raw stage or verify an existing stage without changing it."""

    archive_path = config.archive_path.expanduser().resolve()
    stage_path = config.stage_path.expanduser().resolve()
    if not archive_path.is_file():
        raise RawIngestionError(f"ingestion arşivi bulunamadı: {archive_path}")
    if _is_relative_to(archive_path, stage_path):
        raise RawIngestionError("ingestion arşivi raw stage içinde olamaz")

    archive_sha256 = sha256_file(archive_path)
    if stage_path.exists():
        manifest = _verify_existing_stage(config, stage_path, archive_path, archive_sha256)
        return _result(IngestionStatus.REUSED, stage_path, manifest)

    stage_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = Path(
        tempfile.mkdtemp(
            dir=stage_path.parent,
            prefix=f".{config.source_version}.",
            suffix=".part",
        )
    )
    try:
        files = _extract_archive(archive_path, temporary_path, config)
        if not files:
            raise RawIngestionError("arşiv en az bir normal dosya içermelidir")
        manifest = _build_manifest(config, archive_path, archive_sha256, files)
        _write_manifest(temporary_path / "manifest.json", manifest)
        try:
            temporary_path.rename(stage_path)
        except FileExistsError:
            verified = _verify_existing_stage(config, stage_path, archive_path, archive_sha256)
            return _result(IngestionStatus.REUSED, stage_path, verified)
        return _result(IngestionStatus.CREATED, stage_path, manifest)
    finally:
        if temporary_path.exists():
            shutil.rmtree(temporary_path)


def _extract_archive(
    archive_path: Path,
    destination: Path,
    config: RawIngestionConfig,
) -> list[dict[str, str | int]]:
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            members = _zip_members(archive)
            return _write_members(members, destination, config)
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = _tar_members(archive)
            return _write_members(members, destination, config)
    raise RawIngestionError(f"desteklenen ZIP/TAR arşivi bekleniyor: {archive_path}")


def _inventory_archive(
    archive_path: Path,
    config: RawIngestionConfig,
) -> list[dict[str, str | int]]:
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            return _inventory_members(_zip_members(archive), config)
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, mode="r:*") as archive:
            return _inventory_members(_tar_members(archive), config)
    raise RawIngestionError(f"desteklenen ZIP/TAR arşivi bekleniyor: {archive_path}")


def _zip_members(archive: zipfile.ZipFile) -> Iterator[tuple[str, IO[bytes]]]:
    for member in archive.infolist():
        if member.is_dir():
            continue
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise RawIngestionError(f"arşiv symlink içeremez: {member.filename}")
        if member.flag_bits & 0x1:
            raise RawIngestionError(f"şifreli arşiv üyesi desteklenmiyor: {member.filename}")
        with archive.open(member, mode="r") as stream:
            yield member.filename, stream


def _tar_members(archive: tarfile.TarFile) -> Iterator[tuple[str, IO[bytes]]]:
    for member in archive.getmembers():
        if member.isdir():
            continue
        if not member.isfile():
            raise RawIngestionError(f"arşiv yalnız normal dosya içerebilir: {member.name}")
        stream = archive.extractfile(member)
        if stream is None:
            raise RawIngestionError(f"arşiv üyesi okunamadı: {member.name}")
        with stream:
            yield member.name, stream


def _write_members(
    members: Iterator[tuple[str, IO[bytes]]],
    destination: Path,
    config: RawIngestionConfig,
) -> list[dict[str, str | int]]:
    files: list[dict[str, str | int]] = []
    seen_paths: set[str] = set()
    for raw_name, stream in members:
        relative_path = _safe_member_path(raw_name)
        collision_key = relative_path.as_posix().casefold()
        if collision_key in seen_paths or relative_path.name == "manifest.json":
            raise RawIngestionError(f"yinelenen veya ayrılmış arşiv yolu: {relative_path}")
        seen_paths.add(collision_key)

        output_path = destination.joinpath(*relative_path.parts)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        size_bytes, digest = _copy_with_sha256(stream, output_path)
        relative_name = relative_path.as_posix()
        files.append(
            {
                "path": relative_name,
                "size_bytes": size_bytes,
                "sha256": digest,
                "sample_id": _sample_id(config, relative_name, digest),
            }
        )
    return sorted(files, key=lambda item: str(item["path"]))


def _inventory_members(
    members: Iterator[tuple[str, IO[bytes]]],
    config: RawIngestionConfig,
) -> list[dict[str, str | int]]:
    files: list[dict[str, str | int]] = []
    seen_paths: set[str] = set()
    for raw_name, stream in members:
        relative_path = _safe_member_path(raw_name)
        collision_key = relative_path.as_posix().casefold()
        if collision_key in seen_paths or relative_path.name == "manifest.json":
            raise RawIngestionError(f"yinelenen veya ayrılmış arşiv yolu: {relative_path}")
        seen_paths.add(collision_key)
        relative_name = relative_path.as_posix()
        size_bytes, digest = _hash_stream(stream)
        files.append(
            {
                "path": relative_name,
                "size_bytes": size_bytes,
                "sha256": digest,
                "sample_id": _sample_id(config, relative_name, digest),
            }
        )
    return sorted(files, key=lambda item: str(item["path"]))


def _copy_with_sha256(stream: IO[bytes], output_path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    with output_path.open("xb") as output:
        while chunk := stream.read(DEFAULT_CHUNK_SIZE_BYTES):
            output.write(chunk)
            digest.update(chunk)
            size_bytes += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    return size_bytes, digest.hexdigest()


def _hash_stream(stream: IO[bytes]) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    while chunk := stream.read(DEFAULT_CHUNK_SIZE_BYTES):
        digest.update(chunk)
        size_bytes += len(chunk)
    return size_bytes, digest.hexdigest()


def _build_manifest(
    config: RawIngestionConfig,
    archive_path: Path,
    archive_sha256: str,
    files: list[dict[str, str | int]],
) -> dict[str, Any]:
    return {
        "schema_version": RAW_INGESTION_SCHEMA_VERSION,
        "source": {"id": config.source_id, "version": config.source_version},
        "archive": {
            "sha256": archive_sha256,
            "size_bytes": archive_path.stat().st_size,
        },
        "sample_count": len(files),
        "files": files,
    }


def _verify_existing_stage(
    config: RawIngestionConfig,
    stage_path: Path,
    archive_path: Path,
    archive_sha256: str,
) -> dict[str, Any]:
    if not stage_path.is_dir():
        raise RawMutationError(f"raw stage dizin olmalıdır: {stage_path}")
    manifest_path = stage_path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RawMutationError(f"raw stage manifesti eksik veya bozuk: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise RawMutationError("raw stage manifesti JSON nesnesi olmalıdır")

    expected_header = {
        "schema_version": RAW_INGESTION_SCHEMA_VERSION,
        "source": {"id": config.source_id, "version": config.source_version},
    }
    for field, expected in expected_header.items():
        if manifest.get(field) != expected:
            raise RawMutationError(f"raw stage manifest alanı değişmiş: {field}")
    archive = manifest.get("archive")
    if not isinstance(archive, dict) or archive.get("sha256") != archive_sha256:
        raise RawMutationError(
            "aynı source_version farklı arşiv içeriğiyle yeniden kullanılamaz; yeni sürüm gerekir"
        )
    expected_files = _inventory_archive(archive_path, config)
    expected_manifest = _build_manifest(
        config,
        archive_path,
        archive_sha256,
        expected_files,
    )
    if manifest != expected_manifest:
        raise RawMutationError("raw stage manifesti deterministik kaynak manifestinden farklı")
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("sample_count") != len(files):
        raise RawMutationError("raw stage manifest dosya sayımı değişmiş")

    expected_paths = {"manifest.json"}
    for item in files:
        if not isinstance(item, dict):
            raise RawMutationError("raw stage manifest dosya kaydı bozuk")
        relative = _safe_member_path(item.get("path"))
        relative_name = relative.as_posix()
        expected_paths.add(relative_name)
        file_path = stage_path.joinpath(*relative.parts)
        if file_path.is_symlink() or not file_path.is_file():
            raise RawMutationError(f"raw stage dosyası eksik: {relative_name}")
        actual_size = file_path.stat().st_size
        actual_sha256 = sha256_file(file_path)
        expected_sample_id = _sample_id(config, relative_name, actual_sha256)
        if (
            item.get("size_bytes") != actual_size
            or item.get("sha256") != actual_sha256
            or item.get("sample_id") != expected_sample_id
        ):
            raise RawMutationError(f"raw stage dosyası yerinde değişmiş: {relative_name}")

    discovered = list(stage_path.rglob("*"))
    if any(path.is_symlink() for path in discovered):
        raise RawMutationError("raw stage symlink içeremez")
    actual_paths = {
        path.relative_to(stage_path).as_posix() for path in discovered if path.is_file()
    }
    if actual_paths != expected_paths:
        unexpected = sorted(actual_paths.symmetric_difference(expected_paths))
        raise RawMutationError("raw stage dosya kümesi değişmiş: " + ", ".join(unexpected))
    return manifest


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(payload + "\n")
        output.flush()
        os.fsync(output.fileno())


def _result(
    status: IngestionStatus,
    stage_path: Path,
    manifest: dict[str, Any],
) -> RawIngestionResult:
    manifest_path = stage_path / "manifest.json"
    return RawIngestionResult(
        status=status,
        stage_path=stage_path,
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        sample_count=int(manifest["sample_count"]),
    )


def _sample_id(config: RawIngestionConfig, relative_path: str, digest: str) -> str:
    identity = "\0".join((config.source_id, config.source_version, relative_path, digest))
    return "sample-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _safe_member_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise RawIngestionError("arşiv üye yolu boş olamaz")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    forbidden = set('<>:"|?*')
    if path.is_absolute() or not path.parts:
        raise RawIngestionError(f"güvensiz arşiv yolu: {value}")
    for part in path.parts:
        if (
            part in {"", ".", ".."}
            or any(character in forbidden or ord(character) < 32 for character in part)
            or part.rstrip(" .") != part
        ):
            raise RawIngestionError(f"güvensiz arşiv yolu: {value}")
    return path


def _safe_identity(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RawIngestionError(f"{field} boş olmayan string olmalıdır")
    result = value.strip()
    if any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in result
    ):
        raise RawIngestionError(f"{field} yalnız harf, rakam, nokta, alt çizgi ve tire içerebilir")
    if result in {".", ".."}:
        raise RawIngestionError(f"{field} güvenli bir path bileşeni olmalıdır")
    return result


def _required_path(value: Mapping[str, Any], field: str, base_directory: Path) -> Path:
    raw_path = value.get(field)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RawIngestionError(f"{field} boş olmayan string olmalıdır")
    path = Path(raw_path.strip()).expanduser()
    return (base_directory / path).resolve() if not path.is_absolute() else path.resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
