from __future__ import annotations

import math

import numpy as np
import pytest
import torch

from radariq.data.contracts import IQBatch, IQRepresentation, IQSampleMetadata
from radariq.features import (
    AmplitudePhaseConfig,
    AmplitudePhaseError,
    CanonicalIQConfig,
    PaddingMode,
    amplitude_phase_from_config,
    to_amplitude_phase_tensor,
    to_canonical_iq_tensor,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _canonical(samples: np.ndarray, target_length: int | None = None, padding_value: float = 0.0):
    batch = IQBatch(
        samples=samples,
        metadata=tuple(
            IQSampleMetadata(
                sample_id=f"sample-{index}",
                label="BPSK",
                snr_db=0.0,
                group_id="capture-1",
                source_version="fixture@v1",
            )
            for index in range(samples.shape[0])
        ),
        representation=IQRepresentation.CHANNELS_FIRST,
    )
    return to_canonical_iq_tensor(
        batch,
        CanonicalIQConfig(
            target_length or samples.shape[-1],
            padding=PaddingMode.RIGHT,
            padding_value=padding_value,
        ),
    )


def test_known_iq_points_have_correct_amplitude_and_wrapped_phase() -> None:
    samples = np.array(
        [[[1.0, 0.0, -1.0, 0.0, 3.0], [0.0, 1.0, 0.0, -1.0, 4.0]]],
        dtype=np.float32,
    )

    result = to_amplitude_phase_tensor(_canonical(samples))

    expected_amplitude = torch.tensor([1.0, 1.0, 1.0, 1.0, 5.0])
    expected_phase = torch.tensor([0.0, math.pi / 2, -math.pi, -math.pi / 2, math.atan2(4, 3)])
    torch.testing.assert_close(result.values[0, 0], expected_amplitude)
    torch.testing.assert_close(result.values[0, 1], expected_phase)
    assert result.values.dtype is torch.float32
    assert result.values.is_contiguous()
    assert result.phase_valid_mask.all()


def test_zero_and_near_zero_amplitude_have_explicit_finite_phase() -> None:
    samples = np.array([[[0.0, 1e-9, 1.0], [0.0, -1e-9, 0.0]]], dtype=np.float32)
    config = AmplitudePhaseConfig(zero_amplitude_epsilon=1e-6, undefined_phase_value=0.25)

    result = to_amplitude_phase_tensor(_canonical(samples), config)

    assert result.phase_valid_mask[0].tolist() == [False, False, True]
    torch.testing.assert_close(result.values[0, 1, :2], torch.tensor([0.25, 0.25]))
    assert torch.isfinite(result.values).all()
    assert not torch.isnan(result.values).any()


def test_padding_is_zeroed_and_excluded_from_both_masks() -> None:
    samples = np.array([[[3.0, 4.0], [4.0, 3.0]]], dtype=np.float32)

    result = to_amplitude_phase_tensor(_canonical(samples, target_length=4, padding_value=-2.0))

    assert result.valid_mask[0].tolist() == [True, True, False, False]
    assert result.phase_valid_mask[0].tolist() == [True, True, False, False]
    torch.testing.assert_close(result.values[0, :, 2:], torch.zeros((2, 2)))


def test_repository_config_defines_zero_amplitude_behavior() -> None:
    samples = np.zeros((1, 2, 2), dtype=np.float32)

    result = amplitude_phase_from_config(_canonical(samples), "configs/features.yaml")

    assert not result.phase_valid_mask.any()
    assert result.metadata.as_dict() == {
        "schema_version": "1.0",
        "channels": ["amplitude", "wrapped_phase"],
        "phase_range": "[-pi, pi)",
        "zero_amplitude_epsilon": 1e-8,
        "undefined_phase_value": 0.0,
    }


@pytest.mark.parametrize(
    "value",
    [
        {"zero_amplitude_epsilon": -1.0},
        {"zero_amplitude_epsilon": float("nan")},
        {"zero_amplitude_epsilon": True},
        {"undefined_phase_value": math.pi},
        {"undefined_phase_value": float("inf")},
    ],
)
def test_invalid_amplitude_phase_policy_fails_early(value: dict[str, object]) -> None:
    with pytest.raises(AmplitudePhaseError):
        AmplitudePhaseConfig.from_mapping(value)
