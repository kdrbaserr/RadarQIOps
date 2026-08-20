from __future__ import annotations

import numpy as np
import pytest
import torch

from radariq.data.contracts import IQBatch, IQRepresentation, IQSampleMetadata
from radariq.features import (
    CanonicalIQConfig,
    SpectralConfig,
    SpectralFeatureError,
    SpectralMode,
    SpectralScale,
    SpectralWindow,
    spectral_from_config,
    to_canonical_iq_tensor,
    to_spectral_tensor,
)
from radariq.features.canonical import CanonicalIQTensor

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _canonical_tone(length: int, bin_index: int, sample_rate_hz: float) -> CanonicalIQTensor:
    time = np.arange(length, dtype=np.float32) / sample_rate_hz
    tone = np.exp(2j * np.pi * bin_index * time).astype(np.complex64)
    batch = IQBatch(
        samples=tone[None, :],
        metadata=(
            IQSampleMetadata(
                sample_id="tone-1",
                label="tone",
                snr_db=None,
                group_id=None,
                source_version="synthetic@v1",
            ),
        ),
        representation=IQRepresentation.COMPLEX,
    )
    return to_canonical_iq_tensor(batch, CanonicalIQConfig(length))


def test_fft_of_clean_tone_peaks_at_expected_frequency() -> None:
    canonical = _canonical_tone(length=64, bin_index=5, sample_rate_hz=64.0)
    config = SpectralConfig(
        enabled=True,
        mode=SpectralMode.FFT,
        n_fft=64,
        window=SpectralWindow.NONE,
        scale=SpectralScale.MAGNITUDE,
        sample_rate_hz=64.0,
    )

    result = to_spectral_tensor(canonical, config)

    peak_index = int(torch.argmax(result.values[0, 0]).item())
    assert result.frequencies_hz[peak_index].item() == pytest.approx(5.0)
    assert result.values.shape == (1, 1, 64)
    assert result.values.dtype is torch.float32
    assert torch.isfinite(result.values).all()


def test_spectrogram_uses_versioned_window_overlap_and_scale() -> None:
    canonical = _canonical_tone(length=32, bin_index=4, sample_rate_hz=32.0)
    config = SpectralConfig(
        enabled=True,
        mode=SpectralMode.SPECTROGRAM,
        n_fft=8,
        window=SpectralWindow.HANN,
        overlap=4,
        scale=SpectralScale.LOG_POWER,
        sample_rate_hz=32.0,
    )

    result = to_spectral_tensor(canonical, config)

    assert result.values.shape == (1, 1, 8, 7)
    assert result.frame_start_seconds.tolist() == pytest.approx(
        [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75]
    )
    assert result.metadata.config.sha256 == config.sha256
    assert result.metadata.as_dict()["config"]["window"] == "hann"
    assert torch.isfinite(result.values).all()


def test_artifact_hash_changes_when_spectral_config_changes() -> None:
    canonical = _canonical_tone(length=32, bin_index=4, sample_rate_hz=32.0)
    first_config = SpectralConfig(
        enabled=True,
        mode=SpectralMode.SPECTROGRAM,
        n_fft=8,
        overlap=0,
        sample_rate_hz=32.0,
    )
    second_config = SpectralConfig(
        enabled=True,
        mode=SpectralMode.SPECTROGRAM,
        n_fft=8,
        overlap=4,
        sample_rate_hz=32.0,
    )

    first = to_spectral_tensor(canonical, first_config)
    second = to_spectral_tensor(canonical, second_config)

    assert first_config.sha256 != second_config.sha256
    assert first.artifact_sha256 != second.artifact_sha256


def test_repository_config_keeps_spectral_feature_disabled_by_default() -> None:
    canonical = _canonical_tone(length=128, bin_index=4, sample_rate_hz=128.0)

    result = spectral_from_config(canonical, "configs/features.yaml")

    assert result is None


@pytest.mark.parametrize(
    "value",
    [
        {"enabled": "yes"},
        {"n_fft": 0},
        {"n_fft": 8, "overlap": 8},
        {"window": "blackman"},
        {"scale": "decibel"},
        {"sample_rate_hz": 0.0},
        {"log_epsilon": float("nan")},
    ],
)
def test_invalid_spectral_config_fails_early(value: dict[str, object]) -> None:
    with pytest.raises(SpectralFeatureError):
        SpectralConfig.from_mapping(value)


def test_disabled_config_cannot_be_applied_directly() -> None:
    canonical = _canonical_tone(length=16, bin_index=2, sample_rate_hz=16.0)

    with pytest.raises(SpectralFeatureError, match="enabled=true"):
        to_spectral_tensor(canonical, SpectralConfig())
