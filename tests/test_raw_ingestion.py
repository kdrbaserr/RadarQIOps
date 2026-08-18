from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from radariq.cli import main
from radariq.data.ingestion import (
    IngestionStatus,
    RawIngestionConfig,
    RawIngestionError,
    RawMutationError,
    ingest_archive,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_same_input_reuses_identical_manifest_and_sample_ids(tmp_path: Path) -> None:
    archive = write_archive(tmp_path / "source.zip")
    config = ingestion_config(archive, tmp_path / "raw")

    first = ingest_archive(config)
    first_manifest = first.manifest_path.read_bytes()
    first_mtime = first.manifest_path.stat().st_mtime_ns
    second = ingest_archive(config)

    assert first.status is IngestionStatus.CREATED
    assert second.status is IngestionStatus.REUSED
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.manifest_path.read_bytes() == first_manifest
    assert second.manifest_path.stat().st_mtime_ns == first_mtime
    manifest = json.loads(first_manifest)
    assert manifest["sample_count"] == 2
    assert len({item["sample_id"] for item in manifest["files"]}) == 2


def test_manifest_is_independent_of_archive_and_raw_absolute_paths(tmp_path: Path) -> None:
    first_archive = write_archive(tmp_path / "first" / "source.zip")
    second_archive = write_archive(tmp_path / "second" / "renamed.zip")

    first = ingest_archive(ingestion_config(first_archive, tmp_path / "raw-a"))
    second = ingest_archive(ingestion_config(second_archive, tmp_path / "raw-b"))

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()


def test_in_place_raw_mutation_fails_without_repair(tmp_path: Path) -> None:
    archive = write_archive(tmp_path / "source.zip")
    config = ingestion_config(archive, tmp_path / "raw")
    result = ingest_archive(config)
    sample_path = result.stage_path / "samples" / "a.iq"
    sample_path.write_bytes(b"mutated")

    with pytest.raises(RawMutationError, match="yerinde değişmiş"):
        ingest_archive(config)

    assert sample_path.read_bytes() == b"mutated"


def test_coordinated_raw_and_manifest_mutation_still_fails(tmp_path: Path) -> None:
    archive = write_archive(tmp_path / "source.zip")
    config = ingestion_config(archive, tmp_path / "raw")
    result = ingest_archive(config)
    sample_path = result.stage_path / "samples" / "a.iq"
    mutated = b"coordinated-mutation"
    sample_path.write_bytes(mutated)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    item = next(entry for entry in manifest["files"] if entry["path"] == "samples/a.iq")
    digest = hashlib.sha256(mutated).hexdigest()
    identity = "\0".join(("fixture", "v1", "samples/a.iq", digest))
    item.update(
        size_bytes=len(mutated),
        sha256=digest,
        sample_id="sample-" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
    )
    result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RawMutationError, match="deterministik kaynak manifestinden farklı"):
        ingest_archive(config)


def test_changed_archive_requires_a_new_source_version(tmp_path: Path) -> None:
    archive = write_archive(tmp_path / "source.zip")
    raw_root = tmp_path / "raw"
    ingest_archive(ingestion_config(archive, raw_root, version="v1"))
    write_archive(archive, first_payload=b"changed")

    with pytest.raises(RawMutationError, match="yeni sürüm gerekir"):
        ingest_archive(ingestion_config(archive, raw_root, version="v1"))

    second = ingest_archive(ingestion_config(archive, raw_root, version="v2"))
    assert second.status is IngestionStatus.CREATED
    assert second.stage_path.name == "v2"


def test_archive_path_traversal_is_rejected_without_partial_stage(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../escape.iq", b"unsafe")
    config = ingestion_config(archive, tmp_path / "raw")

    with pytest.raises(RawIngestionError, match="güvensiz arşiv yolu"):
        ingest_archive(config)

    assert not config.stage_path.exists()
    assert not (tmp_path / "escape.iq").exists()
    assert not list(config.stage_path.parent.glob("*.part"))


def test_tar_archive_is_extracted_with_the_same_raw_contract(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    payload = b"tar-sample"
    member = tarfile.TarInfo("samples/a.iq")
    member.size = len(payload)
    with tarfile.open(archive, "w:gz") as output:
        output.addfile(member, io.BytesIO(payload))

    result = ingest_archive(ingestion_config(archive, tmp_path / "raw"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert (result.stage_path / "samples" / "a.iq").read_bytes() == payload
    assert manifest["sample_count"] == 1
    assert manifest["files"][0]["sample_id"].startswith("sample-")


def test_ingestion_cli_resolves_paths_relative_to_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive = write_archive(tmp_path / "incoming" / "source.zip")
    config_directory = tmp_path / "configs"
    config_directory.mkdir()
    config_path = config_directory / "ingest.yaml"
    config_path.write_text(
        json.dumps(
            {
                "archive_path": "../incoming/source.zip",
                "raw_root": "../data/raw/ingested",
                "source_id": "fixture",
                "source_version": "v1",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["data", "ingest", "--config", str(config_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "created"
    assert Path(output["stage_path"]) == tmp_path / "data" / "raw" / "ingested" / "fixture" / "v1"
    assert archive.exists()


def write_archive(path: Path, *, first_payload: bytes = b"first") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as output:
        output.writestr("samples/b.iq", b"second")
        output.writestr("samples/a.iq", first_payload)
    return path


def ingestion_config(
    archive: Path,
    raw_root: Path,
    *,
    version: str = "v1",
) -> RawIngestionConfig:
    return RawIngestionConfig(
        archive_path=archive,
        raw_root=raw_root,
        source_id="fixture",
        source_version=version,
    )
