from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from radariq.data.dvc_pipeline import (
    DataPipelineError,
    run_preprocessing_stage,
    run_report_stage,
    run_split_stage,
    run_validation_stage,
    validate_pipeline_export_manifest,
)
from tools.check_data_pipeline_export import verify_manifest

pytestmark = [pytest.mark.integration, pytest.mark.contract]

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "data_pipeline" / "raw_iq.json"


def _params(tmp_path: Path, *, execution_profile: str = "fixture") -> Path:
    pipeline: dict[str, object] = {
        "raw_input": str(FIXTURE),
        "validation_output": str(tmp_path / "validation"),
        "split_output": str(tmp_path / "splits"),
        "preprocessing_output": str(tmp_path / "processed"),
        "report_output": str(tmp_path / "report"),
        "source_revision": "fixture:raw-iq-v1",
        "execution_profile": execution_profile,
        "dvc_remote": "local" if execution_profile == "fixture" else "full-run",
        "dvc_pull_status": "fixture" if execution_profile == "fixture" else "verified",
    }
    if execution_profile == "colab":
        pipeline["dvc_pull_log_sha256"] = "a" * 64
        pipeline["runtime_manifest_sha256"] = "b" * 64
    value = {
        "pipeline": pipeline,
        "validation": {
            "representation": "channels_first",
            "signal_length": 4,
            "allowed_labels": ["BPSK", "QPSK"],
            "snr_min_db": -20,
            "snr_max_db": 20,
            "max_amplitude": 2,
            "min_power": 1e-8,
            "max_power": 8,
            "constant_tolerance": 1e-7,
        },
        "leakage": {
            "representation": "channels_first",
            "near_duplicate_enabled": False,
            "correlation_threshold": 0.999,
            "quantization_decimals": 3,
            "remove_dc": True,
            "allowed_splits": ["train", "validation", "test"],
        },
        "split": {
            "fractions": {"train": 0.5, "validation": 0.25, "test": 0.25},
            "seed": 20260811,
            "snr_bin_edges": [-10, 0, 10],
            "group_rule_name": "explicit-group-id",
            "group_rule_version": "1.0",
        },
        "preprocessing": {
            "representation": "channels_first",
            "remove_dc_offset": True,
            "normalization": "train_rms_power",
            "zero_power_epsilon": 1e-12,
            "max_input_amplitude": 100,
            "reject_zero_power": True,
        },
    }
    path = tmp_path / "params.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _run_pipeline(params_path: Path) -> dict[str, Any]:
    run_validation_stage(params_path)
    run_split_stage(params_path)
    run_preprocessing_stage(params_path)
    return run_report_stage(params_path)


def _rehash(manifest: dict[str, Any]) -> None:
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    payload = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(payload.encode()).hexdigest()


def test_fixture_pipeline_builds_complete_hash_chain(tmp_path: Path) -> None:
    manifest = _run_pipeline(_params(tmp_path))

    assert validate_pipeline_export_manifest(manifest) == []
    assert manifest["pipeline"]["stage_order"] == ["validate", "split", "preprocess", "report"]
    assert manifest["validation"]["accepted_count"] == 12
    assert manifest["validation"]["quarantine_count"] == 0
    assert manifest["preprocessing"]["fit_split"] == "train"
    assert (
        manifest["split"]["train_indices_sha256"]
        == manifest["preprocessing"]["train_indices_sha256"]
    )
    with np.load(tmp_path / "processed" / "processed_iq.npz", allow_pickle=False) as data:
        assert len(data["samples"]) == 12


def test_same_fixture_pipeline_reuses_identical_artifacts(tmp_path: Path) -> None:
    params_path = _params(tmp_path)
    first = _run_pipeline(params_path)
    second = _run_pipeline(params_path)

    assert first == second


def test_report_rejects_tampered_split_indices(tmp_path: Path) -> None:
    params_path = _params(tmp_path)
    run_validation_stage(params_path)
    run_split_stage(params_path)
    run_preprocessing_stage(params_path)
    train_path = tmp_path / "splits" / "train_indices.npy"
    indices = np.load(train_path, allow_pickle=False)
    np.save(train_path, indices[::-1], allow_pickle=False)

    with pytest.raises(DataPipelineError, match="train indeks hash"):
        run_report_stage(params_path)


def test_local_verifier_reads_only_export_manifest(tmp_path: Path) -> None:
    manifest = _run_pipeline(_params(tmp_path))
    manifest_path = tmp_path / "report" / "pipeline_export_manifest.json"

    assert verify_manifest(manifest_path, manifest["split"]["split_plan_sha256"]) == []
    assert verify_manifest(manifest_path, "0" * 64) == [
        "split_plan_sha256 beklenen değerle eşleşmiyor"
    ]


def test_colab_profile_requires_pull_and_runtime_evidence(tmp_path: Path) -> None:
    manifest = _run_pipeline(_params(tmp_path, execution_profile="colab"))
    assert validate_pipeline_export_manifest(manifest) == []

    changed = deepcopy(manifest)
    changed["execution"].pop("dvc_pull_log_sha256")
    _rehash(changed)

    assert any(
        "dvc_pull_log_sha256" in error for error in validate_pipeline_export_manifest(changed)
    )


def test_manifest_rejects_preprocessing_with_different_train_indices(tmp_path: Path) -> None:
    manifest = _run_pipeline(_params(tmp_path))
    changed = deepcopy(manifest)
    changed["preprocessing"]["train_indices_sha256"] = "f" * 64
    _rehash(changed)

    assert "split ve preprocessing train indeks hash'leri eşleşmiyor" in (
        validate_pipeline_export_manifest(changed)
    )
