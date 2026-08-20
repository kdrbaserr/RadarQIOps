"""Amplitude and wrapped-phase transforms for canonical I/Q tensors."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from radariq.configs import load_config
from radariq.features.canonical import CanonicalIQTensor

AMPLITUDE_PHASE_SCHEMA_VERSION = "1.0"


class AmplitudePhaseError(ValueError):
    """Raised when amplitude/phase features cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class AmplitudePhaseConfig:
    """Numerical policy for undefined phase near zero amplitude."""

    zero_amplitude_epsilon: float = 1e-8
    undefined_phase_value: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.zero_amplitude_epsilon, bool)
            or not isinstance(self.zero_amplitude_epsilon, (int, float))
            or not math.isfinite(self.zero_amplitude_epsilon)
            or self.zero_amplitude_epsilon < 0
        ):
            raise AmplitudePhaseError(
                "zero_amplitude_epsilon sonlu ve negatif olmayan number olmalıdır"
            )
        if (
            isinstance(self.undefined_phase_value, bool)
            or not isinstance(self.undefined_phase_value, (int, float))
            or not math.isfinite(self.undefined_phase_value)
            or not -math.pi <= self.undefined_phase_value < math.pi
        ):
            raise AmplitudePhaseError("undefined_phase_value [-pi, pi) aralığında olmalıdır")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AmplitudePhaseConfig:
        return cls(
            zero_amplitude_epsilon=value.get("zero_amplitude_epsilon", 1e-8),
            undefined_phase_value=value.get("undefined_phase_value", 0.0),
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "zero_amplitude_epsilon": float(self.zero_amplitude_epsilon),
            "undefined_phase_value": float(self.undefined_phase_value),
        }


@dataclass(frozen=True, slots=True)
class AmplitudePhaseMetadata:
    """Stable channel and numerical semantics for amplitude/phase features."""

    zero_amplitude_epsilon: float
    undefined_phase_value: float
    schema_version: str = AMPLITUDE_PHASE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "channels": ["amplitude", "wrapped_phase"],
            "phase_range": "[-pi, pi)",
            "zero_amplitude_epsilon": self.zero_amplitude_epsilon,
            "undefined_phase_value": self.undefined_phase_value,
        }


@dataclass(frozen=True, slots=True)
class AmplitudePhaseTensor:
    """Amplitude/phase values and masks for signal and phase validity."""

    values: torch.Tensor
    valid_mask: torch.Tensor
    phase_valid_mask: torch.Tensor
    metadata: AmplitudePhaseMetadata


def to_amplitude_phase_tensor(
    canonical: CanonicalIQTensor,
    config: AmplitudePhaseConfig | None = None,
) -> AmplitudePhaseTensor:
    """Return ``[amplitude, wrapped_phase]`` without NaN at undefined phase points."""

    _validate_canonical(canonical)
    policy = config or AmplitudePhaseConfig()
    if not isinstance(policy, AmplitudePhaseConfig):
        raise AmplitudePhaseError("config geçerli bir AmplitudePhaseConfig olmalıdır")

    valid_mask = canonical.valid_mask.clone()
    i_values = canonical.values[:, 0, :]
    q_values = canonical.values[:, 1, :]
    amplitude = torch.hypot(i_values, q_values)
    raw_phase = torch.atan2(q_values, i_values)
    wrapped_phase = torch.remainder(raw_phase + math.pi, 2 * math.pi) - math.pi
    phase_valid_mask = valid_mask & (amplitude > policy.zero_amplitude_epsilon)

    amplitude = torch.where(valid_mask, amplitude, torch.zeros_like(amplitude))
    phase_fill = torch.full_like(wrapped_phase, float(policy.undefined_phase_value))
    wrapped_phase = torch.where(phase_valid_mask, wrapped_phase, phase_fill)
    values = torch.stack((amplitude, wrapped_phase), dim=1).contiguous()

    if not torch.isfinite(values).all():
        raise AmplitudePhaseError("amplitude/phase dönüşümü NaN veya Inf üretti")

    return AmplitudePhaseTensor(
        values=values,
        valid_mask=valid_mask,
        phase_valid_mask=phase_valid_mask,
        metadata=AmplitudePhaseMetadata(
            zero_amplitude_epsilon=float(policy.zero_amplitude_epsilon),
            undefined_phase_value=float(policy.undefined_phase_value),
        ),
    )


def amplitude_phase_from_config(
    canonical: CanonicalIQTensor, config_path: str | Path
) -> AmplitudePhaseTensor:
    """Load the ``amplitude_phase`` config section and transform a canonical tensor."""

    value = load_config(config_path)
    feature_value = value.get("amplitude_phase")
    if not isinstance(feature_value, Mapping):
        raise AmplitudePhaseError("config amplitude_phase nesnesi içermelidir")
    return to_amplitude_phase_tensor(canonical, AmplitudePhaseConfig.from_mapping(feature_value))


def _validate_canonical(canonical: CanonicalIQTensor) -> None:
    if not isinstance(canonical, CanonicalIQTensor):
        raise AmplitudePhaseError("canonical geçerli bir CanonicalIQTensor olmalıdır")
    values = canonical.values
    valid_mask = canonical.valid_mask
    if values.ndim != 3 or values.shape[1] != 2:
        raise AmplitudePhaseError("canonical values shape [N, 2, L] olmalıdır")
    if values.dtype is not torch.float32:
        raise AmplitudePhaseError("canonical values dtype torch.float32 olmalıdır")
    if valid_mask.shape != (values.shape[0], values.shape[2]):
        raise AmplitudePhaseError("canonical valid_mask shape [N, L] olmalıdır")
    if valid_mask.dtype is not torch.bool:
        raise AmplitudePhaseError("canonical valid_mask dtype torch.bool olmalıdır")
    if values.device != valid_mask.device:
        raise AmplitudePhaseError("canonical values ve valid_mask aynı cihazda olmalıdır")
    if not torch.isfinite(values).all():
        raise AmplitudePhaseError("canonical values NaN veya Inf içeremez")
