from __future__ import annotations

import numpy as np
import pytest
import torch

from radariq.data.contracts import IQBatch, IQRepresentation, IQSampleMetadata
from radariq.features import (
    CanonicalIQConfig,
    CanonicalIQError,
    CropMode,
    PaddingMode,
    canonical_iq_from_config,
    to_canonical_iq_tensor,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _metadata(index: int) -> IQSampleMetadata:
    return IQSampleMetadata(
        sample_id=f"sample-{index}",
        label="BPSK",
        snr_db=-6.0,
        group_id="capture-1",
        source_version="fixture@v1",
    )


def _batch(samples: np.ndarray, representation: IQRepresentation) -> IQBatch:
    return IQBatch(
        samples=samples,
        metadata=tuple(_metadata(index) for index in range(samples.shape[0])),
        representation=representation,
    )


def test_channels_first_input_preserves_i_then_q_order_and_dtype() -> None:
    samples = np.array([[[1, 2, 3], [10, 20, 30]]], dtype=np.float32)

    result = to_canonical_iq_tensor(
        _batch(samples, IQRepresentation.CHANNELS_FIRST), CanonicalIQConfig(3)
    )

    assert result.values.shape == (1, 2, 3)
    assert result.values.dtype is torch.float32
    assert result.values.is_contiguous()
    torch.testing.assert_close(result.values[0, 0], torch.tensor([1.0, 2.0, 3.0]))
    torch.testing.assert_close(result.values[0, 1], torch.tensor([10.0, 20.0, 30.0]))
    assert result.valid_mask.dtype is torch.bool
    assert result.valid_mask.all()


def test_complex_input_becomes_channel_first_real_then_imaginary() -> None:
    samples = np.array([[1 + 10j, 2 + 20j, 3 + 30j]], dtype=np.complex64)

    result = to_canonical_iq_tensor(_batch(samples, IQRepresentation.COMPLEX), CanonicalIQConfig(3))

    torch.testing.assert_close(result.values[0, 0], torch.tensor([1.0, 2.0, 3.0]))
    torch.testing.assert_close(result.values[0, 1], torch.tensor([10.0, 20.0, 30.0]))
    assert result.metadata.source_representation is IQRepresentation.COMPLEX


@pytest.mark.parametrize(
    ("padding", "expected_i", "expected_mask", "expected_widths"),
    [
        (PaddingMode.RIGHT, [1, 2, -1, -1, -1], [True, True, False, False, False], (0, 3)),
        (PaddingMode.LEFT, [-1, -1, -1, 1, 2], [False, False, False, True, True], (3, 0)),
        (PaddingMode.CENTER, [-1, 1, 2, -1, -1], [False, True, True, False, False], (1, 2)),
    ],
)
def test_padding_policy_and_mask_metadata(
    padding: PaddingMode,
    expected_i: list[int],
    expected_mask: list[bool],
    expected_widths: tuple[int, int],
) -> None:
    samples = np.array([[[1, 2], [10, 20]]], dtype=np.float32)
    config = CanonicalIQConfig(5, padding=padding, padding_value=-1.0)

    result = to_canonical_iq_tensor(_batch(samples, IQRepresentation.CHANNELS_FIRST), config)

    torch.testing.assert_close(result.values[0, 0], torch.tensor(expected_i, dtype=torch.float32))
    assert result.valid_mask[0].tolist() == expected_mask
    assert (result.metadata.padding_left, result.metadata.padding_right) == expected_widths


@pytest.mark.parametrize(
    ("crop", "expected", "expected_bounds"),
    [
        (CropMode.START, [0, 1, 2, 3], (0, 4)),
        (CropMode.CENTER, [2, 3, 4, 5], (2, 6)),
        (CropMode.END, [4, 5, 6, 7], (4, 8)),
    ],
)
def test_crop_policy_is_explicit(
    crop: CropMode, expected: list[int], expected_bounds: tuple[int, int]
) -> None:
    values = np.arange(8, dtype=np.float32)
    samples = np.stack((values, values + 10), axis=0)[None, :, :]

    result = to_canonical_iq_tensor(
        _batch(samples, IQRepresentation.CHANNELS_FIRST),
        CanonicalIQConfig(4, crop=crop),
    )

    torch.testing.assert_close(result.values[0, 0], torch.tensor(expected, dtype=torch.float32))
    assert (result.metadata.crop_start, result.metadata.crop_end) == expected_bounds


def test_same_input_and_config_produce_identical_tensors() -> None:
    samples = np.arange(20, dtype=np.float32).reshape(2, 2, 5)
    batch = _batch(samples, IQRepresentation.CHANNELS_FIRST)
    config = CanonicalIQConfig(8, padding=PaddingMode.CENTER)

    first = to_canonical_iq_tensor(batch, config)
    second = to_canonical_iq_tensor(batch, config)

    assert torch.equal(first.values, second.values)
    assert torch.equal(first.valid_mask, second.valid_mask)
    assert first.metadata == second.metadata


def test_policy_loads_from_repository_config() -> None:
    samples = np.ones((1, 2, 4), dtype=np.float32)

    result = canonical_iq_from_config(
        _batch(samples, IQRepresentation.CHANNELS_FIRST), "configs/features.yaml"
    )

    assert result.values.shape == (1, 2, 128)
    assert result.valid_mask.sum().item() == 4
    assert result.metadata.as_dict()["padding"] == {"left": 0, "right": 124}


@pytest.mark.parametrize(
    "value",
    [
        {"target_length": 0},
        {"target_length": True},
        {"target_length": 8, "crop": "random"},
        {"target_length": 8, "padding": "reflect"},
        {"target_length": 8, "padding_value": float("nan")},
    ],
)
def test_invalid_tensor_policy_fails_early(value: dict[str, object]) -> None:
    with pytest.raises(CanonicalIQError):
        CanonicalIQConfig.from_mapping(value)
