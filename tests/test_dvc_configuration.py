from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def test_dvc_local_remote_is_secret_free() -> None:
    config = (ROOT / ".dvc" / "config").read_text(encoding="utf-8")

    assert "remote = local" in config
    assert "url = ../.dvc-storage" in config
    assert not any(
        token in config.casefold() for token in ("password", "secret", "token", "credential")
    )


def test_data_pipeline_declares_safe_stage_order_and_train_fitted_dependency() -> None:
    pipeline = (ROOT / "dvc.yaml").read_text(encoding="utf-8")
    lock = (ROOT / "dvc.lock").read_text(encoding="utf-8")

    positions = [
        pipeline.index(f"  {stage}:") for stage in ("validate", "split", "preprocess", "report")
    ]
    assert positions == sorted(positions)
    assert "${pipeline.split_output}/train_indices.npy" in pipeline
    assert "${pipeline.preprocessing_output}/preprocessor.json" in pipeline
    assert "tests/fixtures/data_pipeline/raw_iq.json" in lock
    assert "pipeline.source_revision: fixture:raw-iq-v1" in lock


def test_pipeline_params_keep_fixture_local_and_colab_evidence_explicit() -> None:
    params = (ROOT / "params.yaml").read_text(encoding="utf-8")

    assert '"execution_profile": "fixture"' in params
    assert '"dvc_remote": "local"' in params
    assert "dvc_pull_log_sha256" not in params
    assert "runtime_manifest_sha256" not in params


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/dataset.zip",
        "artifacts/model.onnx",
        "artifacts/checkpoints/model.ckpt",
    ],
)
def test_large_ml_files_are_ignored_by_git(path: str) -> None:
    assert _is_ignored(path)


@pytest.mark.parametrize(
    "path",
    [
        "data/raw.dvc",
        "artifacts/model.onnx.dvc",
        "artifacts/evaluation.json",
    ],
)
def test_dvc_pointers_and_small_evidence_can_be_tracked(path: str) -> None:
    assert not _is_ignored(path)
