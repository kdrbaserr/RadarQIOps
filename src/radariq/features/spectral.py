"""Config-selected FFT and spectrogram representations for canonical I/Q tensors."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import torch

from radariq.configs import load_config
from radariq.features.canonical import CanonicalIQTensor

SPECTRAL_SCHEMA_VERSION = "1.0"


class SpectralFeatureError(ValueError):
    """Raised when a spectral feature cannot be produced safely."""


class SpectralMode(StrEnum):
    FFT = "fft"
    SPECTROGRAM = "spectrogram"


class SpectralWindow(StrEnum):
    NONE = "none"
    HANN = "hann"


class SpectralScale(StrEnum):
    MAGNITUDE = "magnitude"
    POWER = "power"
    LOG_POWER = "log_power"


@dataclass(frozen=True, slots=True)
class SpectralConfig:
    """Versioned selection and numerical policy for spectral features."""

    enabled: bool = False
    mode: SpectralMode = SpectralMode.FFT
    n_fft: int = 128
    window: SpectralWindow = SpectralWindow.HANN
    overlap: int = 0
    scale: SpectralScale = SpectralScale.POWER
    sample_rate_hz: float = 1.0
    log_epsilon: float = 1e-12

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise SpectralFeatureError("enabled boolean olmalıdır")
        if not isinstance(self.mode, SpectralMode):
            raise SpectralFeatureError("mode desteklenen bir SpectralMode olmalıdır")
        if not isinstance(self.window, SpectralWindow):
            raise SpectralFeatureError("window desteklenen bir SpectralWindow olmalıdır")
        if not isinstance(self.scale, SpectralScale):
            raise SpectralFeatureError("scale desteklenen bir SpectralScale olmalıdır")
        if isinstance(self.n_fft, bool) or not isinstance(self.n_fft, int) or self.n_fft <= 0:
            raise SpectralFeatureError("n_fft pozitif integer olmalıdır")
        if (
            isinstance(self.overlap, bool)
            or not isinstance(self.overlap, int)
            or self.overlap < 0
            or self.overlap >= self.n_fft
        ):
            raise SpectralFeatureError("overlap [0, n_fft) aralığında integer olmalıdır")
        _require_positive_finite(self.sample_rate_hz, "sample_rate_hz")
        _require_positive_finite(self.log_epsilon, "log_epsilon")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SpectralConfig:
        raw_mode = value.get("mode", SpectralMode.FFT.value)
        raw_window = value.get("window", SpectralWindow.HANN.value)
        raw_scale = value.get("scale", SpectralScale.POWER.value)
        if not all(isinstance(item, str) for item in (raw_mode, raw_window, raw_scale)):
            raise SpectralFeatureError("mode, window ve scale string olmalıdır")
        try:
            mode = SpectralMode(raw_mode)
            window = SpectralWindow(raw_window)
            scale = SpectralScale(raw_scale)
        except ValueError as exc:
            raise SpectralFeatureError("mode, window veya scale desteklenmiyor") from exc
        return cls(
            enabled=value.get("enabled", False),
            mode=mode,
            n_fft=value.get("n_fft", 128),
            window=window,
            overlap=value.get("overlap", 0),
            scale=scale,
            sample_rate_hz=value.get("sample_rate_hz", 1.0),
            log_epsilon=value.get("log_epsilon", 1e-12),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SPECTRAL_SCHEMA_VERSION,
            "enabled": self.enabled,
            "mode": self.mode.value,
            "n_fft": self.n_fft,
            "window": self.window.value,
            "overlap": self.overlap,
            "scale": self.scale.value,
            "sample_rate_hz": float(self.sample_rate_hz),
            "log_epsilon": float(self.log_epsilon),
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class SpectralMetadata:
    """Auditable spectral axes and the exact config identity."""

    config: SpectralConfig
    source_length: int
    frequency_bins: int
    time_frames: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SPECTRAL_SCHEMA_VERSION,
            "config_sha256": self.config.sha256,
            "config": self.config.as_dict(),
            "source_length": self.source_length,
            "frequency_bins": self.frequency_bins,
            "time_frames": self.time_frames,
            "frequency_axis": "fftshift_hz",
            "time_axis": "frame_start_seconds",
        }


@dataclass(frozen=True, slots=True)
class SpectralTensor:
    """FFT `[N,1,F]` or spectrogram `[N,1,F,T]` plus deterministic axes."""

    values: torch.Tensor
    frequencies_hz: torch.Tensor
    frame_start_seconds: torch.Tensor
    metadata: SpectralMetadata

    @property
    def artifact_sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(_canonical_json(self.metadata.as_dict()))
        for tensor in (self.values, self.frequencies_hz, self.frame_start_seconds):
            normalized = tensor.detach().cpu().contiguous()
            digest.update(str(normalized.dtype).encode("ascii"))
            digest.update(json.dumps(list(normalized.shape)).encode("ascii"))
            digest.update(normalized.numpy().tobytes(order="C"))
        return digest.hexdigest()


def to_spectral_tensor(canonical: CanonicalIQTensor, config: SpectralConfig) -> SpectralTensor:
    """Produce the explicitly enabled FFT or spectrogram alternative representation."""

    _validate_canonical(canonical)
    if not isinstance(config, SpectralConfig):
        raise SpectralFeatureError("config geçerli bir SpectralConfig olmalıdır")
    if not config.enabled:
        raise SpectralFeatureError("spectral feature config içinde enabled=true olmalıdır")

    signal = torch.complex(canonical.values[:, 0, :], canonical.values[:, 1, :])
    signal = torch.where(canonical.valid_mask, signal, torch.zeros_like(signal))
    if config.mode is SpectralMode.FFT:
        values, frame_starts = _fft_features(signal, config)
    else:
        values, frame_starts = _spectrogram_features(signal, config)
    frequencies = torch.fft.fftshift(
        torch.fft.fftfreq(
            config.n_fft,
            d=1.0 / float(config.sample_rate_hz),
            device=signal.device,
        )
    ).to(torch.float32)

    if not torch.isfinite(values).all():
        raise SpectralFeatureError("spectral dönüşüm NaN veya Inf üretti")
    return SpectralTensor(
        values=values.contiguous(),
        frequencies_hz=frequencies.contiguous(),
        frame_start_seconds=frame_starts.contiguous(),
        metadata=SpectralMetadata(
            config=config,
            source_length=int(signal.shape[-1]),
            frequency_bins=int(values.shape[-2] if values.ndim == 4 else values.shape[-1]),
            time_frames=int(values.shape[-1] if values.ndim == 4 else 1),
        ),
    )


def spectral_from_config(
    canonical: CanonicalIQTensor, config_path: str | Path
) -> SpectralTensor | None:
    """Return no spectral feature when disabled; otherwise apply the selected mode."""

    value = load_config(config_path)
    spectral_value = value.get("spectral")
    if not isinstance(spectral_value, Mapping):
        raise SpectralFeatureError("config spectral nesnesi içermelidir")
    config = SpectralConfig.from_mapping(spectral_value)
    return to_spectral_tensor(canonical, config) if config.enabled else None


def _fft_features(
    signal: torch.Tensor, config: SpectralConfig
) -> tuple[torch.Tensor, torch.Tensor]:
    source_length = int(signal.shape[-1])
    if config.n_fft < source_length:
        raise SpectralFeatureError("FFT n_fft canonical sinyal uzunluğundan küçük olamaz")
    window = _window(source_length, config.window, signal)
    spectrum = torch.fft.fftshift(torch.fft.fft(signal * window, n=config.n_fft), dim=-1)
    values = _scale(spectrum, config).unsqueeze(1)
    frame_starts = torch.zeros(1, dtype=torch.float32, device=signal.device)
    return values, frame_starts


def _spectrogram_features(
    signal: torch.Tensor, config: SpectralConfig
) -> tuple[torch.Tensor, torch.Tensor]:
    source_length = int(signal.shape[-1])
    if config.n_fft > source_length:
        raise SpectralFeatureError("spectrogram n_fft canonical sinyal uzunluğunu aşamaz")
    hop_length = config.n_fft - config.overlap
    window = _window(config.n_fft, config.window, signal)
    spectrum = torch.stft(
        signal,
        n_fft=config.n_fft,
        hop_length=hop_length,
        window=window,
        center=False,
        onesided=False,
        return_complex=True,
    )
    spectrum = torch.fft.fftshift(spectrum, dim=-2)
    values = _scale(spectrum, config).unsqueeze(1)
    frame_starts = (
        torch.arange(values.shape[-1], dtype=torch.float32, device=signal.device)
        * hop_length
        / float(config.sample_rate_hz)
    )
    return values, frame_starts


def _window(length: int, mode: SpectralWindow, signal: torch.Tensor) -> torch.Tensor:
    if mode is SpectralWindow.NONE:
        return torch.ones(length, dtype=signal.real.dtype, device=signal.device)
    return torch.hann_window(
        length,
        periodic=True,
        dtype=signal.real.dtype,
        device=signal.device,
    )


def _scale(spectrum: torch.Tensor, config: SpectralConfig) -> torch.Tensor:
    magnitude = torch.abs(spectrum)
    if config.scale is SpectralScale.MAGNITUDE:
        return magnitude.to(torch.float32)
    power = torch.square(magnitude)
    if config.scale is SpectralScale.POWER:
        return power.to(torch.float32)
    return (10.0 * torch.log10(torch.clamp(power, min=config.log_epsilon))).to(torch.float32)


def _validate_canonical(canonical: CanonicalIQTensor) -> None:
    if not isinstance(canonical, CanonicalIQTensor):
        raise SpectralFeatureError("canonical geçerli bir CanonicalIQTensor olmalıdır")
    values = canonical.values
    valid_mask = canonical.valid_mask
    if values.ndim != 3 or values.shape[1] != 2 or values.dtype is not torch.float32:
        raise SpectralFeatureError("canonical values float32 [N, 2, L] olmalıdır")
    if valid_mask.shape != (values.shape[0], values.shape[2]) or valid_mask.dtype is not torch.bool:
        raise SpectralFeatureError("canonical valid_mask bool [N, L] olmalıdır")
    if values.device != valid_mask.device:
        raise SpectralFeatureError("canonical values ve valid_mask aynı cihazda olmalıdır")
    if not torch.isfinite(values).all():
        raise SpectralFeatureError("canonical values NaN veya Inf içeremez")


def _require_positive_finite(value: object, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise SpectralFeatureError(f"{field} pozitif ve sonlu number olmalıdır")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()
