"""One immutable feature path shared by training and inference callers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias

from radariq.configs import load_config
from radariq.data.contracts import IQBatch
from radariq.data.preprocessing import FittedPreprocessor
from radariq.features.amplitude_phase import (
    AmplitudePhaseConfig,
    AmplitudePhaseTensor,
    to_amplitude_phase_tensor,
)
from radariq.features.canonical import (
    CanonicalIQConfig,
    CanonicalIQTensor,
    to_canonical_iq_tensor,
)
from radariq.features.spectral import SpectralConfig, SpectralTensor, to_spectral_tensor

FEATURE_PIPELINE_SCHEMA_VERSION = "1.0"

FeatureTensor: TypeAlias = CanonicalIQTensor | AmplitudePhaseTensor | SpectralTensor


class FeaturePipelineError(ValueError):
    """Raised when the shared train/inference feature contract is invalid."""


class FeatureOutput(StrEnum):
    CANONICAL_IQ = "canonical_iq"
    AMPLITUDE_PHASE = "amplitude_phase"
    SPECTRAL = "spectral"


@dataclass(frozen=True, slots=True)
class FeaturePipelineConfig:
    """Typed selection of one model-facing representation."""

    output: FeatureOutput
    canonical_iq: CanonicalIQConfig
    amplitude_phase: AmplitudePhaseConfig
    spectral: SpectralConfig

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> FeaturePipelineConfig:
        if value.get("schema_version") != FEATURE_PIPELINE_SCHEMA_VERSION:
            raise FeaturePipelineError("feature pipeline schema_version desteklenmiyor")
        raw_output = value.get("output", FeatureOutput.CANONICAL_IQ.value)
        if not isinstance(raw_output, str):
            raise FeaturePipelineError("features output string olmalıdır")
        try:
            output = FeatureOutput(raw_output)
        except ValueError as exc:
            raise FeaturePipelineError("features output desteklenmiyor") from exc

        canonical_value = value.get("canonical_iq")
        amplitude_phase_value = value.get("amplitude_phase", {})
        spectral_value = value.get("spectral", {})
        if not isinstance(canonical_value, Mapping):
            raise FeaturePipelineError("canonical_iq config nesnesi zorunludur")
        if not isinstance(amplitude_phase_value, Mapping):
            raise FeaturePipelineError("amplitude_phase config nesnesi olmalıdır")
        if not isinstance(spectral_value, Mapping):
            raise FeaturePipelineError("spectral config nesnesi olmalıdır")

        config = cls(
            output=output,
            canonical_iq=CanonicalIQConfig.from_mapping(canonical_value),
            amplitude_phase=AmplitudePhaseConfig.from_mapping(amplitude_phase_value),
            spectral=SpectralConfig.from_mapping(spectral_value),
        )
        if config.output is FeatureOutput.SPECTRAL and not config.spectral.enabled:
            raise FeaturePipelineError("output=spectral için spectral.enabled=true olmalıdır")
        return config

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FEATURE_PIPELINE_SCHEMA_VERSION,
            "output": self.output.value,
            "canonical_iq": self.canonical_iq.as_dict(),
            "amplitude_phase": self.amplitude_phase.as_dict(),
            "spectral": self.spectral.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class FeaturePipeline:
    """Apply one fitted preprocessor and feature config without ever fitting at inference."""

    preprocessor: FittedPreprocessor
    config: FeaturePipelineConfig

    def __post_init__(self) -> None:
        if not isinstance(self.preprocessor, FittedPreprocessor):
            raise FeaturePipelineError("preprocessor fit edilmiş FittedPreprocessor olmalıdır")
        if not isinstance(self.config, FeaturePipelineConfig):
            raise FeaturePipelineError("config geçerli bir FeaturePipelineConfig olmalıdır")
        if self.preprocessor.lineage.fit_split != "train":
            raise FeaturePipelineError(
                "feature pipeline yalnız train-fitted preprocessor kabul eder"
            )

    @classmethod
    def from_artifacts(
        cls,
        preprocessor_path: str | Path,
        feature_config_path: str | Path,
    ) -> FeaturePipeline:
        """Load the immutable train-fitted artifact used by both runtime paths."""

        preprocessor_value = load_config(preprocessor_path)
        feature_value = load_config(feature_config_path)
        return cls(
            preprocessor=FittedPreprocessor.from_mapping(preprocessor_value),
            config=FeaturePipelineConfig.from_mapping(feature_value),
        )

    @property
    def sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": FEATURE_PIPELINE_SCHEMA_VERSION,
                "preprocessor_sha256": self.preprocessor.sha256,
                "feature_config": self.config.as_dict(),
            }
        )

    def transform(self, batch: IQBatch) -> FeatureTensor:
        """Apply the exact same immutable transform regardless of caller context."""

        if not isinstance(batch, IQBatch):
            raise FeaturePipelineError("batch geçerli bir IQBatch olmalıdır")
        if batch.representation is not self.preprocessor.policy.representation:
            raise FeaturePipelineError("batch ve preprocessor I/Q gösterimleri eşleşmelidir")

        transformed = self.preprocessor.transform(batch.samples)
        processed_batch = IQBatch(
            samples=transformed,
            metadata=batch.metadata,
            representation=batch.representation,
            schema_version=batch.schema_version,
        )
        canonical = to_canonical_iq_tensor(processed_batch, self.config.canonical_iq)
        if self.config.output is FeatureOutput.CANONICAL_IQ:
            return canonical
        if self.config.output is FeatureOutput.AMPLITUDE_PHASE:
            return to_amplitude_phase_tensor(canonical, self.config.amplitude_phase)
        return to_spectral_tensor(canonical, self.config.spectral)


def transform_for_training(pipeline: FeaturePipeline, batch: IQBatch) -> FeatureTensor:
    """Training adapter kept deliberately thin so parity tests detect future divergence."""

    return pipeline.transform(batch)


def transform_for_inference(pipeline: FeaturePipeline, batch: IQBatch) -> FeatureTensor:
    """Inference adapter uses the immutable train-fitted pipeline without refitting."""

    return pipeline.transform(batch)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()
