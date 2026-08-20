"""Deterministic conversion from the data contract to model-ready I/Q tensors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import torch

from radariq.configs import load_config
from radariq.data.contracts import IQBatch, IQRepresentation

CANONICAL_IQ_SCHEMA_VERSION = "1.0"


class CanonicalIQError(ValueError):
    """Raised when a model-facing I/Q tensor cannot be produced safely."""


class CropMode(StrEnum):
    START = "start"
    CENTER = "center"
    END = "end"


class PaddingMode(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class CanonicalIQConfig:
    """Shape policy for the canonical channel-first model input."""

    target_length: int
    crop: CropMode = CropMode.CENTER
    padding: PaddingMode = PaddingMode.RIGHT
    padding_value: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_length, bool)
            or not isinstance(self.target_length, int)
            or self.target_length <= 0
        ):
            raise CanonicalIQError("target_length pozitif integer olmalıdır")
        if not isinstance(self.crop, CropMode):
            raise CanonicalIQError("crop desteklenen bir CropMode olmalıdır")
        if not isinstance(self.padding, PaddingMode):
            raise CanonicalIQError("padding desteklenen bir PaddingMode olmalıdır")
        if isinstance(self.padding_value, bool) or not isinstance(self.padding_value, (int, float)):
            raise CanonicalIQError("padding_value sonlu number olmalıdır")
        if not np.isfinite(self.padding_value):
            raise CanonicalIQError("padding_value sonlu number olmalıdır")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CanonicalIQConfig:
        raw_target_length = value.get("target_length")
        raw_crop = value.get("crop", CropMode.CENTER.value)
        raw_padding = value.get("padding", PaddingMode.RIGHT.value)
        if isinstance(raw_target_length, bool) or not isinstance(raw_target_length, int):
            raise CanonicalIQError("target_length pozitif integer olmalıdır")
        if not isinstance(raw_crop, str) or not isinstance(raw_padding, str):
            raise CanonicalIQError("crop ve padding string olmalıdır")
        try:
            crop = CropMode(raw_crop)
            padding = PaddingMode(raw_padding)
        except ValueError as exc:
            raise CanonicalIQError("crop veya padding politikası desteklenmiyor") from exc
        return cls(
            target_length=raw_target_length,
            crop=crop,
            padding=padding,
            padding_value=value.get("padding_value", 0.0),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_length": self.target_length,
            "crop": self.crop.value,
            "padding": self.padding.value,
            "padding_value": float(self.padding_value),
        }


@dataclass(frozen=True, slots=True)
class TensorMetadata:
    """Auditable length transformation applied uniformly to one homogeneous batch."""

    source_representation: IQRepresentation
    source_length: int
    target_length: int
    crop_start: int
    crop_end: int
    padding_left: int
    padding_right: int
    schema_version: str = CANONICAL_IQ_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_representation": self.source_representation.value,
            "source_length": self.source_length,
            "target_length": self.target_length,
            "crop": {"start": self.crop_start, "end": self.crop_end},
            "padding": {"left": self.padding_left, "right": self.padding_right},
        }


@dataclass(frozen=True, slots=True)
class CanonicalIQTensor:
    """Channel-first values plus a mask that distinguishes samples from padding."""

    values: torch.Tensor
    valid_mask: torch.Tensor
    metadata: TensorMetadata


def to_canonical_iq_tensor(batch: IQBatch, config: CanonicalIQConfig) -> CanonicalIQTensor:
    """Convert one validated I/Q batch to deterministic ``float32 [N, 2, L]`` tensors."""

    if not isinstance(batch, IQBatch):
        raise CanonicalIQError("batch geçerli bir IQBatch olmalıdır")
    if not isinstance(config, CanonicalIQConfig):
        raise CanonicalIQError("config geçerli bir CanonicalIQConfig olmalıdır")

    channel_first = _to_channel_first(batch)
    source_length = batch.signal_length
    crop_start, crop_end = _crop_bounds(source_length, config.target_length, config.crop)
    cropped = channel_first[:, :, crop_start:crop_end]
    retained_length = int(cropped.shape[-1])
    padding_left, padding_right = _padding_widths(
        retained_length, config.target_length, config.padding
    )

    output = np.full(
        (batch.sample_count, 2, config.target_length),
        fill_value=config.padding_value,
        dtype=np.float32,
    )
    valid_mask = np.zeros((batch.sample_count, config.target_length), dtype=np.bool_)
    output[:, :, padding_left : padding_left + retained_length] = cropped
    valid_mask[:, padding_left : padding_left + retained_length] = True

    return CanonicalIQTensor(
        values=torch.from_numpy(output),
        valid_mask=torch.from_numpy(valid_mask),
        metadata=TensorMetadata(
            source_representation=batch.representation,
            source_length=source_length,
            target_length=config.target_length,
            crop_start=crop_start,
            crop_end=crop_end,
            padding_left=padding_left,
            padding_right=padding_right,
        ),
    )


def canonical_iq_from_config(batch: IQBatch, config_path: str | Path) -> CanonicalIQTensor:
    """Load the ``canonical_iq`` config section and convert a batch."""

    value = load_config(config_path)
    canonical_value = value.get("canonical_iq")
    if not isinstance(canonical_value, Mapping):
        raise CanonicalIQError("config canonical_iq nesnesi içermelidir")
    return to_canonical_iq_tensor(batch, CanonicalIQConfig.from_mapping(canonical_value))


def _to_channel_first(batch: IQBatch) -> np.ndarray[Any, Any]:
    if batch.representation is IQRepresentation.CHANNELS_FIRST:
        return batch.samples
    return np.stack((batch.samples.real, batch.samples.imag), axis=1).astype(np.float32)


def _crop_bounds(source_length: int, target_length: int, mode: CropMode) -> tuple[int, int]:
    retained_length = min(source_length, target_length)
    excess = source_length - retained_length
    if mode is CropMode.START:
        start = 0
    elif mode is CropMode.CENTER:
        start = excess // 2
    else:
        start = excess
    return start, start + retained_length


def _padding_widths(retained_length: int, target_length: int, mode: PaddingMode) -> tuple[int, int]:
    missing = target_length - retained_length
    if mode is PaddingMode.LEFT:
        left = missing
    elif mode is PaddingMode.CENTER:
        left = missing // 2
    else:
        left = 0
    return left, missing - left
