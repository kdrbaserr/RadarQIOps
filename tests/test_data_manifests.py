from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from radariq.cli import main
from radariq.data.acquisition import ChecksumMismatchError
from radariq.data.manifests import (
    DataManifestError,
    load_data_manifest,
    register_source_from_config,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_register_source_writes_complete_versioned_manifest(tmp_path: Path) -> None:
    payload = b"versioned-source-fixture"
    config_path, raw_path, manifest_path = write_registration_fixture(tmp_path, payload)

    result = register_source_from_config(config_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.status.value == "acquired"
    assert result.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.manifest_sha256 == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert manifest == {
        "downloaded_at_utc": result.downloaded_at_utc,
        "file": {
            "name": "dataset.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        },
        "license": {
            "attribution": "Example Dataset, Example Research Group",
            "id": "CC-BY-4.0",
        },
        "schema_version": "1.0",
        "source": {
            "access_method": "local_file",
            "id": "example-dataset",
            "reference": "https://example.org/datasets/example",
            "version": "2026.08",
        },
    }
    assert result.downloaded_at_utc.endswith("Z")
    assert raw_path.read_bytes() == payload


def test_second_registration_reuses_raw_and_preserves_original_manifest(tmp_path: Path) -> None:
    config_path, _, manifest_path = write_registration_fixture(tmp_path, b"stable-fixture")
    first = register_source_from_config(config_path)
    original_manifest = manifest_path.read_bytes()
    original_mtime = manifest_path.stat().st_mtime_ns

    second = register_source_from_config(config_path)

    assert second.status.value == "reused"
    assert second.downloaded_at_utc == first.downloaded_at_utc
    assert manifest_path.read_bytes() == original_manifest
    assert manifest_path.stat().st_mtime_ns == original_mtime


def test_checksum_mismatch_stops_before_raw_publication(tmp_path: Path) -> None:
    config_path, raw_path, manifest_path = write_registration_fixture(
        tmp_path,
        b"actual-content",
        expected_sha256="0" * 64,
    )

    with pytest.raises(ChecksumMismatchError, match="SHA-256 uyuşmazlığı"):
        register_source_from_config(config_path)

    assert not raw_path.exists()
    assert not manifest_path.exists()
    assert not list(raw_path.parent.glob("*.part"))


@pytest.mark.parametrize(
    ("missing_field", "error_pattern"),
    [
        ("license.id", "manifest.license.id"),
        ("license.attribution", "manifest.license.attribution"),
        ("expected_sha256", "expected_sha256"),
    ],
)
def test_missing_g2_metadata_fails_before_acquisition(
    tmp_path: Path,
    missing_field: str,
    error_pattern: str,
) -> None:
    config_path, raw_path, manifest_path = write_registration_fixture(tmp_path, b"fixture")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if missing_field == "expected_sha256":
        del config[missing_field]
    else:
        _, license_field = missing_field.split(".")
        del config["manifest"]["license"][license_field]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(DataManifestError, match=error_pattern):
        register_source_from_config(config_path)

    assert not raw_path.exists()
    assert not manifest_path.exists()


def test_tampered_raw_file_is_rejected_against_checksum_and_manifest(tmp_path: Path) -> None:
    config_path, raw_path, manifest_path = write_registration_fixture(tmp_path, b"trusted")
    register_source_from_config(config_path)
    raw_path.write_bytes(b"tampered")

    with pytest.raises(ChecksumMismatchError):
        register_source_from_config(config_path)

    assert manifest_path.exists()


def test_tampered_manifest_metadata_is_rejected(tmp_path: Path) -> None:
    config_path, _, manifest_path = write_registration_fixture(tmp_path, b"trusted")
    register_source_from_config(config_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["license"]["id"] = "LicenseRef-Unverified"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DataManifestError, match=r"license\.id"):
        register_source_from_config(config_path)


@pytest.mark.parametrize("orphan", ["raw", "manifest"])
def test_raw_and_manifest_must_exist_as_a_consistent_pair(tmp_path: Path, orphan: str) -> None:
    config_path, raw_path, manifest_path = write_registration_fixture(tmp_path, b"fixture")
    if orphan == "raw":
        raw_path.parent.mkdir(parents=True)
        raw_path.write_bytes(b"fixture")
    else:
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text("{}", encoding="utf-8")

    with pytest.raises(DataManifestError, match="birlikte"):
        register_source_from_config(config_path)


def test_unknown_manifest_schema_version_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"schema_version": "2.0"}), encoding="utf-8")

    with pytest.raises(DataManifestError, match="desteklenmeyen"):
        load_data_manifest(manifest_path)


def test_register_cli_emits_machine_readable_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, raw_path, manifest_path = write_registration_fixture(tmp_path, b"cli")

    exit_code = main(["data", "register", "--config", str(config_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "acquired"
    assert Path(output["raw_path"]) == raw_path
    assert Path(output["manifest_path"]) == manifest_path


def write_registration_fixture(
    root: Path,
    payload: bytes,
    *,
    expected_sha256: str | None = None,
) -> tuple[Path, Path, Path]:
    config_directory = root / "configs"
    source_path = root / "incoming" / "dataset.bin"
    raw_path = root / "data" / "raw" / "dataset.bin"
    manifest_path = root / "data" / "manifests" / "dataset.json"
    config_directory.mkdir(parents=True)
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(payload)

    config: dict[str, Any] = {
        "source": {"type": "local_file", "location": "../incoming/dataset.bin"},
        "destination": "../data/raw/dataset.bin",
        "expected_sha256": expected_sha256 or hashlib.sha256(payload).hexdigest(),
        "max_attempts": 1,
        "manifest": {
            "path": "../data/manifests/dataset.json",
            "source_id": "example-dataset",
            "source_version": "2026.08",
            "source_reference": "https://example.org/datasets/example",
            "license": {
                "id": "CC-BY-4.0",
                "attribution": "Example Dataset, Example Research Group",
            },
        },
    }
    config_path = config_directory / "register.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path, raw_path, manifest_path
