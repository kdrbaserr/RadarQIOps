from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radariq.cli import main
from radariq.data.contracts import IQRepresentation
from radariq.data.preprocessing import (
    FittedPreprocessor,
    NormalizationMode,
    PreprocessingArtifactStatus,
    PreprocessingError,
    PreprocessingLineage,
    PreprocessingPolicy,
    fit_preprocessor,
    preprocess_from_config,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _samples() -> np.ndarray:
    return np.array(
        [
            [[2, 4, 2, 4], [-1, 1, -1, 1]],
            [[4, 2, 4, 2], [1, -1, 1, -1]],
            [[5, 3, 5, 3], [2, 0, 2, 0]],
        ],
        dtype=np.float32,
    )


def _policy(**updates: object) -> PreprocessingPolicy:
    values: dict[str, object] = {
        "representation": IQRepresentation.CHANNELS_FIRST,
        "remove_dc_offset": True,
        "normalization": NormalizationMode.TRAIN_RMS_POWER,
        "zero_power_epsilon": 1e-12,
        "max_input_amplitude": 100.0,
        "reject_zero_power": True,
    }
    values.update(updates)
    return PreprocessingPolicy(**values)  # type: ignore[arg-type]


def _lineage(count: int = 2) -> PreprocessingLineage:
    return PreprocessingLineage(
        source_revision="dvc:fixture-v1",
        input_sha256="a" * 64,
        train_indices_sha256="b" * 64,
        train_sample_count=count,
    )


def _write_cli_fixture(tmp_path: Path) -> Path:
    np.savez(
        tmp_path / "validated.npz",
        samples=_samples(),
        labels=np.array(["BPSK", "QPSK", "BPSK"]),
        snr_db=np.array([-10.0, 0.0, 10.0]),
        sample_ids=np.array(["a", "b", "c"]),
    )
    np.save(tmp_path / "train.npy", np.array([0, 1], dtype=np.int64), allow_pickle=False)
    config_path = tmp_path / "preprocess.json"
    config_path.write_text(
        json.dumps(
            {
                "input_path": "validated.npz",
                "train_indices_path": "train.npy",
                "output_dir": "processed/v1",
                "source_revision": "dvc:fixture-v1",
                "preprocessing": {
                    "representation": "channels_first",
                    "remove_dc_offset": True,
                    "normalization": "train_rms_power",
                    "zero_power_epsilon": 1e-12,
                    "max_input_amplitude": 100.0,
                    "reject_zero_power": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_train_rms_fit_centers_channels_and_normalizes_power() -> None:
    fitted = fit_preprocessor(_samples()[:2], _policy(), _lineage())
    transformed = fitted.transform(_samples()[:2])

    assert fitted.dc_i == 3.0
    assert fitted.dc_q == 0.0
    assert fitted.scale == pytest.approx(np.sqrt(2.0))
    assert float(np.mean(transformed[:, 0, :])) == pytest.approx(0.0, abs=1e-7)
    assert float(np.mean(transformed[:, 1, :])) == pytest.approx(0.0, abs=1e-7)
    powers = np.square(transformed[:, 0, :]) + np.square(transformed[:, 1, :])
    assert float(np.mean(powers)) == pytest.approx(1.0, abs=1e-7)


def test_validation_values_do_not_change_fitted_statistics() -> None:
    first_dataset = _samples()
    second_dataset = _samples()
    second_dataset[2] = np.array([[8, 6, 8, 6], [-4, -2, -4, -2]], dtype=np.float32)

    first = fit_preprocessor(first_dataset[[0, 1]], _policy(), _lineage())
    second = fit_preprocessor(second_dataset[[0, 1]], _policy(), _lineage())

    assert first.as_dict() == second.as_dict()
    first_validation = first.transform(first_dataset[2:])
    second_validation = second.transform(second_dataset[2:])
    assert not np.array_equal(first_validation, second_validation)


def test_inverse_transform_recovers_original_within_float32_tolerance() -> None:
    fitted = fit_preprocessor(_samples()[:2], _policy(), _lineage())

    restored = fitted.inverse_transform(fitted.transform(_samples()))

    np.testing.assert_allclose(restored, _samples(), rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize(
    ("bad_samples", "message"),
    [
        (
            np.array([[[np.nan, 1], [1, 1]]], dtype=np.float32),
            "NaN veya Inf",
        ),
        (
            np.zeros((1, 2, 2), dtype=np.float32),
            "zero-power",
        ),
        (
            np.array([[[101, 1], [1, 1]]], dtype=np.float32),
            "max_input_amplitude",
        ),
    ],
)
def test_unsafe_fit_input_fails_closed(bad_samples: np.ndarray, message: str) -> None:
    with pytest.raises(PreprocessingError, match=message):
        fit_preprocessor(bad_samples, _policy(), _lineage(count=1))


def test_fit_lineage_rejects_validation_or_test_split() -> None:
    with pytest.raises(PreprocessingError, match="yalnız train split"):
        PreprocessingLineage(
            source_revision="dvc:fixture-v1",
            input_sha256="a" * 64,
            train_indices_sha256="b" * 64,
            train_sample_count=2,
            fit_split="validation",
        )


def test_peak_amplitude_mode_uses_only_train_peak() -> None:
    fitted = fit_preprocessor(
        _samples()[:2],
        _policy(normalization=NormalizationMode.TRAIN_PEAK_AMPLITUDE),
        _lineage(),
    )

    assert fitted.scale == pytest.approx(np.sqrt(2.0))
    transformed = fitted.transform(_samples()[:2])
    amplitudes = np.hypot(transformed[:, 0, :], transformed[:, 1, :])
    assert float(np.max(amplitudes)) == pytest.approx(1.0)


def test_complex_representation_round_trip() -> None:
    samples = np.array(
        [[1 + 2j, 3 + 4j], [3 + 4j, 1 + 2j]],
        dtype=np.complex64,
    )
    policy = _policy(representation=IQRepresentation.COMPLEX)
    fitted = fit_preprocessor(samples, policy, _lineage())

    assert fitted.transform(samples).dtype == np.complex64
    np.testing.assert_allclose(fitted.inverse_transform(fitted.transform(samples)), samples)


def test_artifact_round_trip_preserves_transform() -> None:
    fitted = fit_preprocessor(_samples()[:2], _policy(), _lineage())
    loaded = FittedPreprocessor.from_mapping(json.loads(json.dumps(fitted.as_dict())))

    assert loaded.sha256 == fitted.sha256
    np.testing.assert_array_equal(loaded.transform(_samples()), fitted.transform(_samples()))


def test_cli_writes_deterministic_immutable_artifacts_and_preserves_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_cli_fixture(tmp_path)

    assert main(["data", "preprocess", "--config", str(config_path)]) == 0
    first_payload = json.loads(capsys.readouterr().out)
    second = preprocess_from_config(config_path)

    assert first_payload["status"] == "created"
    assert second.status is PreprocessingArtifactStatus.REUSED
    assert first_payload["file_sha256"] == second.file_sha256
    with np.load(tmp_path / "processed" / "v1" / "processed_iq.npz", allow_pickle=False) as data:
        assert set(data.files) == {"samples", "labels", "snr_db", "sample_ids"}
        np.testing.assert_array_equal(data["labels"], np.array(["BPSK", "QPSK", "BPSK"]))
    artifact = json.loads(
        (tmp_path / "processed" / "v1" / "preprocessor.json").read_text(encoding="utf-8")
    )
    assert artifact["fit_lineage"]["fit_split"] == "train"
    assert artifact["fit_lineage"]["train_sample_count"] == 2


def test_existing_output_cannot_be_overwritten_with_different_fit(tmp_path: Path) -> None:
    config_path = _write_cli_fixture(tmp_path)
    preprocess_from_config(config_path)
    np.save(tmp_path / "train.npy", np.array([1, 2], dtype=np.int64), allow_pickle=False)

    with pytest.raises(PreprocessingError, match="yerinde değiştirilemez"):
        preprocess_from_config(config_path)


@pytest.mark.parametrize(
    "indices",
    [
        np.array([], dtype=np.int64),
        np.array([0, 0], dtype=np.int64),
        np.array([1, 0], dtype=np.int64),
        np.array([0, 9], dtype=np.int64),
        np.array([0.0, 1.0], dtype=np.float32),
    ],
)
def test_cli_rejects_invalid_train_indices(tmp_path: Path, indices: np.ndarray) -> None:
    config_path = _write_cli_fixture(tmp_path)
    np.save(tmp_path / "train.npy", indices, allow_pickle=False)

    with pytest.raises(PreprocessingError):
        preprocess_from_config(config_path)
