from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from radariq.data.contracts import IQBatch, IQRepresentation, IQSampleMetadata
from radariq.data.preprocessing import (
    NormalizationMode,
    PreprocessingLineage,
    PreprocessingPolicy,
    fit_preprocessor,
)
from radariq.features import (
    CanonicalIQTensor,
    FeaturePipeline,
    FeaturePipelineConfig,
    FeaturePipelineError,
    transform_for_inference,
    transform_for_training,
)

pytestmark = [pytest.mark.integration, pytest.mark.contract]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "features" / "golden_transform.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _policy() -> PreprocessingPolicy:
    return PreprocessingPolicy(
        representation=IQRepresentation.CHANNELS_FIRST,
        remove_dc_offset=True,
        normalization=NormalizationMode.TRAIN_RMS_POWER,
        zero_power_epsilon=1e-12,
        max_input_amplitude=1000.0,
        reject_zero_power=True,
    )


def _lineage(sample_count: int) -> PreprocessingLineage:
    return PreprocessingLineage(
        source_revision="dvc:golden-fixture-v1",
        input_sha256="a" * 64,
        train_indices_sha256="b" * 64,
        train_sample_count=sample_count,
    )


def _batch(samples: np.ndarray, sample_prefix: str) -> IQBatch:
    return IQBatch(
        samples=samples,
        metadata=tuple(
            IQSampleMetadata(
                sample_id=f"{sample_prefix}-{index}",
                label="BPSK",
                snr_db=0.0,
                group_id="golden-capture",
                source_version="golden-fixture@v1",
            )
            for index in range(samples.shape[0])
        ),
        representation=IQRepresentation.CHANNELS_FIRST,
    )


def _feature_config(target_length: int = 5) -> FeaturePipelineConfig:
    return FeaturePipelineConfig.from_mapping(
        {
            "schema_version": "1.0",
            "output": "canonical_iq",
            "canonical_iq": {
                "target_length": target_length,
                "crop": "center",
                "padding": "right",
                "padding_value": 0.0,
            },
            "amplitude_phase": {
                "zero_amplitude_epsilon": 1e-8,
                "undefined_phase_value": 0.0,
            },
            "spectral": {"enabled": False},
        }
    )


def test_training_and_inference_match_versioned_golden_vector() -> None:
    fixture = _fixture()
    assert fixture["schema_version"] == "1.0"
    train_samples = np.asarray(fixture["train_samples"], dtype=np.float32)
    golden_sample = np.asarray(fixture["golden_sample"], dtype=np.float32)
    expected = torch.tensor(fixture["expected_tensor"], dtype=torch.float32)
    expected_mask = torch.tensor(fixture["expected_valid_mask"], dtype=torch.bool)
    tolerance = fixture["tolerance"]
    assert isinstance(tolerance, dict)
    preprocessor = fit_preprocessor(train_samples, _policy(), _lineage(len(train_samples)))
    pipeline = FeaturePipeline(preprocessor, _feature_config())
    batch = _batch(golden_sample, "golden")

    training = transform_for_training(pipeline, batch)
    inference = transform_for_inference(pipeline, batch)

    assert isinstance(training, CanonicalIQTensor)
    assert isinstance(inference, CanonicalIQTensor)
    torch.testing.assert_close(
        training.values,
        expected,
        rtol=float(tolerance["rtol"]),
        atol=float(tolerance["atol"]),
    )
    torch.testing.assert_close(training.values, inference.values, rtol=0.0, atol=0.0)
    assert torch.equal(training.valid_mask, expected_mask)
    assert torch.equal(training.valid_mask, inference.valid_mask)


def test_heldout_values_cannot_change_train_fitted_pipeline() -> None:
    fixture = _fixture()
    train_samples = np.asarray(fixture["train_samples"], dtype=np.float32)
    heldout = np.array([[[2.0, 4.0, 0.0, 2.0], [1.0, 3.0, -1.0, 1.0]]], dtype=np.float32)
    first_dataset = np.concatenate((train_samples, heldout), axis=0)
    changed_heldout = heldout.copy()
    changed_heldout *= 100.0
    second_dataset = np.concatenate((train_samples, changed_heldout), axis=0)
    train_indices = np.array([0, 1], dtype=np.int64)

    first_preprocessor = fit_preprocessor(
        first_dataset[train_indices], _policy(), _lineage(len(train_indices))
    )
    second_preprocessor = fit_preprocessor(
        second_dataset[train_indices], _policy(), _lineage(len(train_indices))
    )

    assert not np.array_equal(first_dataset[2:], second_dataset[2:])
    assert (first_preprocessor.dc_i, first_preprocessor.dc_q, first_preprocessor.scale) == (
        second_preprocessor.dc_i,
        second_preprocessor.dc_q,
        second_preprocessor.scale,
    )


def test_shared_pipeline_reloads_same_immutable_preprocessor_artifact(tmp_path: Path) -> None:
    fixture = _fixture()
    train_samples = np.asarray(fixture["train_samples"], dtype=np.float32)
    golden_sample = np.asarray(fixture["golden_sample"], dtype=np.float32)
    fitted = fit_preprocessor(train_samples, _policy(), _lineage(len(train_samples)))
    preprocessor_path = tmp_path / "preprocessor.json"
    feature_path = tmp_path / "features.json"
    preprocessor_path.write_text(json.dumps(fitted.as_dict()), encoding="utf-8")
    feature_path.write_text(json.dumps(_feature_config().as_dict()), encoding="utf-8")

    training_pipeline = FeaturePipeline(fitted, _feature_config())
    inference_pipeline = FeaturePipeline.from_artifacts(preprocessor_path, feature_path)
    batch = _batch(golden_sample, "reload")
    training = transform_for_training(training_pipeline, batch)
    inference = transform_for_inference(inference_pipeline, batch)

    assert training_pipeline.sha256 == inference_pipeline.sha256
    torch.testing.assert_close(training.values, inference.values, rtol=0.0, atol=0.0)


def test_feature_pipeline_rejects_unknown_schema_version() -> None:
    value = _feature_config().as_dict()
    value["schema_version"] = "2.0"

    with pytest.raises(FeaturePipelineError, match="schema_version"):
        FeaturePipelineConfig.from_mapping(value)
