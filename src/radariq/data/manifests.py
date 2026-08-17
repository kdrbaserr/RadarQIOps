"""Versioned source manifests for acquired raw dataset files."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radariq.configs import load_config
from radariq.data.acquisition import (
    AcquisitionConfig,
    AcquisitionConfigError,
    AcquisitionResult,
    AcquisitionStatus,
    SourceType,
    acquire,
    sha256_file,
)

DATA_MANIFEST_SCHEMA_VERSION = "1.0"


class DataManifestError(AcquisitionConfigError):
    """Raised when source provenance cannot be recorded or verified safely."""


@dataclass(frozen=True, slots=True)
class DataManifestConfig:
    """Required provenance and licensing settings for one source."""

    path: Path
    source_id: str
    source_version: str
    source_reference: str
    license_id: str
    attribution: str

    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        base_directory: Path,
    ) -> DataManifestConfig:
        if not isinstance(value, Mapping):
            raise DataManifestError("manifest bir config nesnesi olmalıdır")

        path_value = _required_string(value, "path", prefix="manifest")
        license_value = value.get("license")
        if not isinstance(license_value, Mapping):
            raise DataManifestError("manifest.license bir config nesnesi olmalıdır")

        return cls(
            path=_resolve_config_path(base_directory, path_value),
            source_id=_required_string(value, "source_id", prefix="manifest"),
            source_version=_required_string(value, "source_version", prefix="manifest"),
            source_reference=_required_string(value, "source_reference", prefix="manifest"),
            license_id=_required_string(license_value, "id", prefix="manifest.license"),
            attribution=_required_string(license_value, "attribution", prefix="manifest.license"),
        )


@dataclass(frozen=True, slots=True)
class DataSourceManifest:
    """Portable provenance record for one immutable acquired file."""

    schema_version: str
    source_id: str
    source_version: str
    source_reference: str
    access_method: SourceType
    file_name: str
    size_bytes: int
    sha256: str
    license_id: str
    attribution: str
    downloaded_at_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {
                "id": self.source_id,
                "version": self.source_version,
                "reference": self.source_reference,
                "access_method": self.access_method.value,
            },
            "file": {
                "name": self.file_name,
                "size_bytes": self.size_bytes,
                "sha256": self.sha256,
            },
            "license": {
                "id": self.license_id,
                "attribution": self.attribution,
            },
            "downloaded_at_utc": self.downloaded_at_utc,
        }

    @classmethod
    def from_mapping(cls, value: Any) -> DataSourceManifest:
        if not isinstance(value, Mapping):
            raise DataManifestError("data manifest bir JSON nesnesi olmalıdır")

        schema_version = _required_string(value, "schema_version")
        if schema_version != DATA_MANIFEST_SCHEMA_VERSION:
            raise DataManifestError(f"desteklenmeyen data manifest sürümü: {schema_version}")

        source = _required_mapping(value, "source")
        file_value = _required_mapping(value, "file")
        license_value = _required_mapping(value, "license")
        access_method_value = _required_string(source, "access_method", prefix="source")
        try:
            access_method = SourceType(access_method_value)
        except ValueError as exc:
            raise DataManifestError(
                f"source.access_method desteklenmiyor: {access_method_value}"
            ) from exc

        sha256 = _required_sha256(file_value, "sha256", prefix="file")
        size_bytes = file_value.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise DataManifestError("file.size_bytes sıfır veya pozitif integer olmalıdır")

        downloaded_at_utc = _required_string(value, "downloaded_at_utc")
        _validate_utc_timestamp(downloaded_at_utc)

        return cls(
            schema_version=schema_version,
            source_id=_required_string(source, "id", prefix="source"),
            source_version=_required_string(source, "version", prefix="source"),
            source_reference=_required_string(source, "reference", prefix="source"),
            access_method=access_method,
            file_name=_required_string(file_value, "name", prefix="file"),
            size_bytes=size_bytes,
            sha256=sha256,
            license_id=_required_string(license_value, "id", prefix="license"),
            attribution=_required_string(license_value, "attribution", prefix="license"),
            downloaded_at_utc=downloaded_at_utc,
        )


@dataclass(frozen=True, slots=True)
class DataRegistrationResult:
    """Combined acquisition and manifest verification outcome."""

    status: AcquisitionStatus
    raw_path: Path
    raw_sha256: str
    manifest_path: Path
    manifest_sha256: str
    downloaded_at_utc: str

    def as_dict(self) -> dict[str, str]:
        return {
            "status": self.status.value,
            "raw_path": str(self.raw_path),
            "raw_sha256": self.raw_sha256,
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "downloaded_at_utc": self.downloaded_at_utc,
        }


def register_source_from_config(config_path: str | Path) -> DataRegistrationResult:
    """Acquire and register one source, or verify its existing immutable state."""

    path = Path(config_path).expanduser().resolve()
    value = load_config(path)
    acquisition_config = AcquisitionConfig.from_mapping(value, base_directory=path.parent)
    if acquisition_config.expected_sha256 is None:
        raise DataManifestError("expected_sha256 data manifest kaydı için zorunludur")
    manifest_config = DataManifestConfig.from_mapping(
        value.get("manifest"), base_directory=path.parent
    )
    _require_distinct_paths(acquisition_config.destination, manifest_config.path)

    raw_exists = acquisition_config.destination.exists()
    manifest_exists = manifest_config.path.exists()
    if raw_exists != manifest_exists:
        raise DataManifestError(
            "raw dosya ve data manifest birlikte bulunmalı veya birlikte oluşturulmalıdır"
        )

    acquisition_result = acquire(acquisition_config)
    if manifest_exists:
        manifest = load_data_manifest(manifest_config.path)
        _verify_manifest(manifest, manifest_config, acquisition_result)
    else:
        manifest = _new_manifest(manifest_config, acquisition_result)
        _write_manifest_atomic(manifest_config.path, manifest)

    return DataRegistrationResult(
        status=acquisition_result.status,
        raw_path=acquisition_result.destination,
        raw_sha256=acquisition_result.sha256,
        manifest_path=manifest_config.path,
        manifest_sha256=sha256_file(manifest_config.path),
        downloaded_at_utc=manifest.downloaded_at_utc,
    )


def load_data_manifest(path: Path) -> DataSourceManifest:
    """Load and structurally validate a versioned data source manifest."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataManifestError(f"data manifest bulunamadı: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataManifestError(f"data manifest geçerli JSON değil: {path}: {exc}") from exc
    return DataSourceManifest.from_mapping(value)


def _new_manifest(
    config: DataManifestConfig,
    acquisition: AcquisitionResult,
) -> DataSourceManifest:
    return DataSourceManifest(
        schema_version=DATA_MANIFEST_SCHEMA_VERSION,
        source_id=config.source_id,
        source_version=config.source_version,
        source_reference=config.source_reference,
        access_method=acquisition.source_type,
        file_name=acquisition.destination.name,
        size_bytes=acquisition.size_bytes,
        sha256=acquisition.sha256,
        license_id=config.license_id,
        attribution=config.attribution,
        downloaded_at_utc=_utc_now(),
    )


def _verify_manifest(
    manifest: DataSourceManifest,
    config: DataManifestConfig,
    acquisition: AcquisitionResult,
) -> None:
    expected_fields = {
        "source.id": (config.source_id, manifest.source_id),
        "source.version": (config.source_version, manifest.source_version),
        "source.reference": (config.source_reference, manifest.source_reference),
        "source.access_method": (acquisition.source_type, manifest.access_method),
        "file.name": (acquisition.destination.name, manifest.file_name),
        "file.size_bytes": (acquisition.size_bytes, manifest.size_bytes),
        "file.sha256": (acquisition.sha256, manifest.sha256),
        "license.id": (config.license_id, manifest.license_id),
        "license.attribution": (config.attribution, manifest.attribution),
    }
    mismatches = [
        field for field, (expected, actual) in expected_fields.items() if expected != actual
    ]
    if mismatches:
        raise DataManifestError("data manifest alanları eşleşmiyor: " + ", ".join(mismatches))


def _write_manifest_atomic(path: Path, manifest: DataSourceManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".part",
    )
    temporary_path = Path(temporary_name)
    try:
        payload = json.dumps(
            manifest.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(payload + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _required_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        raise DataManifestError(f"{field} bir nesne olmalıdır")
    return result


def _required_string(value: Mapping[str, Any], field: str, *, prefix: str = "") -> str:
    result = value.get(field)
    qualified = f"{prefix}.{field}" if prefix else field
    if not isinstance(result, str) or not result.strip():
        raise DataManifestError(f"{qualified} boş olmayan string olmalıdır")
    return result.strip()


def _required_sha256(value: Mapping[str, Any], field: str, *, prefix: str) -> str:
    result = _required_string(value, field, prefix=prefix).lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise DataManifestError(f"{prefix}.{field} geçerli SHA-256 olmalıdır")
    return result


def _validate_utc_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataManifestError("downloaded_at_utc geçerli ISO-8601 zamanı olmalıdır") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise DataManifestError("downloaded_at_utc UTC timezone içermelidir")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_config_path(base_directory: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (base_directory / path).resolve() if not path.is_absolute() else path.resolve()


def _require_distinct_paths(raw_path: Path, manifest_path: Path) -> None:
    if raw_path.expanduser().resolve() == manifest_path.expanduser().resolve():
        raise DataManifestError("raw dosya ve data manifest aynı path olamaz")
