"""Typed, versioned contracts for in-memory I/Q data.

The contract deliberately covers structure and metadata only. Dataset-quality
rules such as amplitude limits, allowed label sets and SNR ranges belong to the
validation stage so they can be configured per source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

CURRENT_SCHEMA_VERSION = "1.0"

# This definition is intentionally JSON-compatible. Its canonical SHA-256 is
# registered below, making incompatible changes visible unless the schema
# version is explicitly increased.
IQ_SCHEMA_DEFINITION: dict[str, Any] = {
    "name": "radariq.iq_batch",
    "schema_version": CURRENT_SCHEMA_VERSION,
    "representations": {
        "channels_first": {"dtype": "float32", "shape": ["N", 2, "L"]},
        "complex": {"dtype": "complex64", "shape": ["N", "L"]},
    },
    "sample_metadata": {
        "sample_id": {"type": "string", "required": True, "nullable": False},
        "label": {"type": ["string", "integer"], "required": True, "nullable": False},
        "snr_db": {"type": "number", "required": True, "nullable": True},
        "group_id": {"type": "string", "required": True, "nullable": True},
        "source_version": {"type": "string", "required": True, "nullable": False},
    },
}

# The value is generated from IQ_SCHEMA_DEFINITION by schema_fingerprint().
# Changing the definition without registering a new version fails closed.
REGISTERED_SCHEMA_FINGERPRINTS = {
    "1.0": "5e21d328b18d8e1a769d32bbde5d91e4b8e0bd2c5e2c343b0273a34dfc0215fc",  # pragma: allowlist secret
}


class IQRepresentation(StrEnum):
    """Supported canonical in-memory I/Q layouts."""

    CHANNELS_FIRST = "channels_first"
    COMPLEX = "complex"


class DataContractError(ValueError):
    """Raised when data does not satisfy the versioned I/Q contract."""

    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} ({field}): {message}")


class SchemaVersionError(DataContractError):
    """Raised when a schema version or its registered definition is invalid."""


@dataclass(frozen=True, slots=True)
class IQSampleMetadata:
    """Required lineage and supervision fields for one I/Q sample."""

    sample_id: str
    label: str | int
    snr_db: float | None
    group_id: str | None
    source_version: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.sample_id, "sample_id")
        _require_label(self.label)
        _require_optional_finite_float(self.snr_db, "snr_db")
        _require_optional_non_empty_string(self.group_id, "group_id")
        _require_non_empty_string(self.source_version, "source_version")


@dataclass(frozen=True, slots=True)
class IQBatch:
    """A homogeneous I/Q batch and its one-to-one sample metadata."""

    samples: np.ndarray[Any, Any]
    metadata: tuple[IQSampleMetadata, ...]
    representation: IQRepresentation
    schema_version: str = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        assert_schema_version_registered(version=self.schema_version)

        if not isinstance(self.samples, np.ndarray):
            raise DataContractError("iq.not_ndarray", "samples", "NumPy ndarray bekleniyor")
        if not isinstance(self.representation, IQRepresentation):
            raise DataContractError(
                "iq.invalid_representation",
                "representation",
                f"desteklenen değerler: {', '.join(IQRepresentation)}",
            )

        metadata = tuple(self.metadata)
        object.__setattr__(self, "metadata", metadata)
        _validate_samples(self.samples, self.representation)
        _validate_metadata(metadata, sample_count=self.samples.shape[0])

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def signal_length(self) -> int:
        return int(self.samples.shape[-1])


def schema_fingerprint(definition: dict[str, Any] | None = None) -> str:
    """Return the canonical SHA-256 for a JSON-compatible schema definition."""

    payload = IQ_SCHEMA_DEFINITION if definition is None else definition
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_schema_version_registered(
    definition: dict[str, Any] | None = None,
    version: str = CURRENT_SCHEMA_VERSION,
) -> None:
    """Fail if a schema changed without an explicit registered version bump."""

    registered = REGISTERED_SCHEMA_FINGERPRINTS.get(version)
    if registered is None:
        raise SchemaVersionError(
            "schema.unsupported_version",
            "schema_version",
            f"şema sürümü kayıtlı değil: {version}",
        )

    actual = schema_fingerprint(definition)
    if actual != registered:
        raise SchemaVersionError(
            "schema.version_bump_required",
            "schema_version",
            "şema tanımı değişti; yeni sürüm ve parmak izi kaydedilmelidir",
        )


def _validate_samples(samples: np.ndarray[Any, Any], representation: IQRepresentation) -> None:
    expected_dtype: np.dtype[Any]
    if representation is IQRepresentation.CHANNELS_FIRST:
        expected_dtype = np.dtype(np.float32)
        valid_shape = samples.ndim == 3 and samples.shape[1] == 2
        expected_shape = "[N, 2, L]"
    else:
        expected_dtype = np.dtype(np.complex64)
        valid_shape = samples.ndim == 2
        expected_shape = "[N, L]"

    if not valid_shape:
        raise DataContractError(
            "iq.invalid_shape",
            "samples",
            f"{representation.value} için {expected_shape} bekleniyor, gelen {list(samples.shape)}",
        )
    if samples.shape[0] == 0 or samples.shape[-1] == 0:
        raise DataContractError(
            "iq.empty_batch_or_signal",
            "samples",
            "N ve L sıfırdan büyük olmalıdır",
        )
    if samples.dtype != expected_dtype:
        raise DataContractError(
            "iq.invalid_dtype",
            "samples",
            f"{representation.value} için {expected_dtype} bekleniyor, gelen {samples.dtype}",
        )


def _validate_metadata(metadata: tuple[IQSampleMetadata, ...], sample_count: int) -> None:
    if len(metadata) != sample_count:
        raise DataContractError(
            "metadata.count_mismatch",
            "metadata",
            f"{sample_count} örnek için {len(metadata)} metadata kaydı var",
        )
    if not all(isinstance(item, IQSampleMetadata) for item in metadata):
        raise DataContractError(
            "metadata.invalid_item",
            "metadata",
            "her kayıt IQSampleMetadata olmalıdır",
        )

    sample_ids = [item.sample_id for item in metadata]
    if len(sample_ids) != len(set(sample_ids)):
        raise DataContractError(
            "metadata.duplicate_sample_id",
            "sample_id",
            "batch içinde sample_id benzersiz olmalıdır",
        )


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataContractError("metadata.invalid_string", field, "boş olmayan string bekleniyor")


def _require_optional_non_empty_string(value: Any, field: str) -> None:
    if value is not None:
        _require_non_empty_string(value, field)


def _require_label(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DataContractError("metadata.invalid_label", "label", "string veya integer bekleniyor")
    if isinstance(value, str) and not value.strip():
        raise DataContractError("metadata.invalid_label", "label", "etiket boş olamaz")


def _require_optional_finite_float(value: Any, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise DataContractError("metadata.invalid_number", field, "sayısal değer bekleniyor")
    if not np.isfinite(value):
        raise DataContractError("metadata.non_finite_number", field, "NaN veya Inf olamaz")
