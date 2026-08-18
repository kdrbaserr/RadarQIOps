"""Configurable per-sample quality validation for canonical I/Q signals."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from radariq.data.contracts import IQRepresentation


class ValidationPolicyError(ValueError):
    """Raised when quality thresholds cannot form a safe validation policy."""


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """Dataset-specific limits applied without mutating candidate samples."""

    representation: IQRepresentation
    signal_length: int
    allowed_labels: frozenset[str | int]
    snr_min_db: float
    snr_max_db: float
    max_amplitude: float
    min_power: float
    max_power: float
    constant_tolerance: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.representation, IQRepresentation):
            raise ValidationPolicyError("representation desteklenen bir IQRepresentation olmalıdır")
        if isinstance(self.signal_length, bool) or not isinstance(self.signal_length, int):
            raise ValidationPolicyError("signal_length pozitif integer olmalıdır")
        if self.signal_length <= 0:
            raise ValidationPolicyError("signal_length pozitif integer olmalıdır")
        if not self.allowed_labels:
            raise ValidationPolicyError("allowed_labels en az bir etiket içermelidir")
        if any(not _is_label(label) for label in self.allowed_labels):
            raise ValidationPolicyError(
                "allowed_labels yalnız boş olmayan string veya integer içerir"
            )

        numeric_fields = {
            "snr_min_db": self.snr_min_db,
            "snr_max_db": self.snr_max_db,
            "max_amplitude": self.max_amplitude,
            "min_power": self.min_power,
            "max_power": self.max_power,
            "constant_tolerance": self.constant_tolerance,
        }
        for field, value in numeric_fields.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValidationPolicyError(f"{field} sonlu number olmalıdır")
        if self.snr_min_db > self.snr_max_db:
            raise ValidationPolicyError("snr_min_db, snr_max_db değerinden büyük olamaz")
        if self.max_amplitude <= 0:
            raise ValidationPolicyError("max_amplitude sıfırdan büyük olmalıdır")
        if self.min_power < 0 or self.min_power > self.max_power:
            raise ValidationPolicyError("power sınırları 0 <= min_power <= max_power sağlamalıdır")
        if self.constant_tolerance < 0:
            raise ValidationPolicyError("constant_tolerance negatif olamaz")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ValidationPolicy:
        """Build and validate a policy from a JSON-compatible mapping."""

        raw_representation = value.get("representation")
        if not isinstance(raw_representation, str):
            raise ValidationPolicyError("representation channels_first veya complex olmalıdır")
        try:
            representation = IQRepresentation(raw_representation)
        except (TypeError, ValueError) as exc:
            raise ValidationPolicyError(
                "representation channels_first veya complex olmalıdır"
            ) from exc

        raw_labels = value.get("allowed_labels")
        if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, (str, bytes)):
            raise ValidationPolicyError("allowed_labels bir liste olmalıdır")
        labels: set[str | int] = set()
        for label in raw_labels:
            if not _is_label(label):
                raise ValidationPolicyError(
                    "allowed_labels yalnız boş olmayan string veya integer içerir"
                )
            labels.add(label)

        return cls(
            representation=representation,
            signal_length=_required_positive_int(value, "signal_length"),
            allowed_labels=frozenset(labels),
            snr_min_db=_required_float(value, "snr_min_db"),
            snr_max_db=_required_float(value, "snr_max_db"),
            max_amplitude=_required_float(value, "max_amplitude"),
            min_power=_required_float(value, "min_power"),
            max_power=_required_float(value, "max_power"),
            constant_tolerance=_optional_float(value, "constant_tolerance", 0.0),
        )


@dataclass(frozen=True, slots=True)
class SampleCandidate:
    """Untrusted sample fields as read from a raw dataset adapter."""

    sample_id: str
    signal: Any
    label: Any
    snr_db: Any


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One machine-readable rule violation attached to a sample identity."""

    error_code: str
    sample_id: str
    field: str
    message: str
    observed: Any = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "error_code": self.error_code,
            "sample_id": self.sample_id,
            "field": self.field,
            "message": self.message,
        }
        if self.observed is not None:
            result["observed"] = self.observed
        return result


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Complete deterministic outcome for one validation run."""

    total_count: int
    valid_sample_ids: tuple[str, ...]
    invalid_sample_ids: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def valid_count(self) -> int:
        return len(self.valid_sample_ids)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_sample_ids)

    @property
    def error_counts(self) -> dict[str, int]:
        counts = Counter(issue.error_code for issue in self.issues)
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_count": self.total_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "valid_sample_ids": list(self.valid_sample_ids),
            "invalid_sample_ids": list(self.invalid_sample_ids),
            "error_counts": self.error_counts,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def validate_samples(
    candidates: Sequence[SampleCandidate],
    policy: ValidationPolicy,
) -> ValidationReport:
    """Validate every sample and preserve all independently observable violations."""

    issues: list[ValidationIssue] = []
    valid_sample_ids: list[str] = []
    invalid_sample_ids: list[str] = []
    for candidate in candidates:
        before = len(issues)
        _validate_signal(candidate, policy, issues)
        _validate_label(candidate, policy, issues)
        _validate_snr(candidate, policy, issues)
        if len(issues) == before:
            valid_sample_ids.append(candidate.sample_id)
        else:
            invalid_sample_ids.append(candidate.sample_id)

    return ValidationReport(
        total_count=len(candidates),
        valid_sample_ids=tuple(valid_sample_ids),
        invalid_sample_ids=tuple(invalid_sample_ids),
        issues=tuple(issues),
    )


def _validate_signal(
    candidate: SampleCandidate,
    policy: ValidationPolicy,
    issues: list[ValidationIssue],
) -> None:
    signal = candidate.signal
    if not isinstance(signal, np.ndarray):
        _add_issue(
            issues,
            "signal.not_ndarray",
            candidate.sample_id,
            "signal",
            "NumPy ndarray bekleniyor",
            type(signal).__name__,
        )
        return

    shape_valid = _shape_is_valid(signal, policy.representation)
    if not shape_valid:
        expected = "[2, L]" if policy.representation is IQRepresentation.CHANNELS_FIRST else "[L]"
        _add_issue(
            issues,
            "signal.invalid_shape",
            candidate.sample_id,
            "signal.shape",
            f"{policy.representation.value} için {expected} bekleniyor",
            list(signal.shape),
        )
    elif signal.shape[-1] != policy.signal_length:
        _add_issue(
            issues,
            "signal.invalid_length",
            candidate.sample_id,
            "signal.length",
            f"sinyal uzunluğu {policy.signal_length} olmalıdır",
            int(signal.shape[-1]),
        )

    if signal.size == 0:
        _add_issue(
            issues,
            "signal.empty",
            candidate.sample_id,
            "signal",
            "boş sinyal kaydı kabul edilmez",
            0,
        )

    expected_dtype = (
        np.dtype(np.float32)
        if policy.representation is IQRepresentation.CHANNELS_FIRST
        else np.dtype(np.complex64)
    )
    dtype_valid = signal.dtype == expected_dtype
    if not dtype_valid:
        _add_issue(
            issues,
            "signal.invalid_dtype",
            candidate.sample_id,
            "signal.dtype",
            f"dtype {expected_dtype} olmalıdır",
            str(signal.dtype),
        )

    if not shape_valid or signal.size == 0 or not dtype_valid:
        return
    if not np.all(np.isfinite(signal)):
        _add_issue(
            issues,
            "signal.non_finite",
            candidate.sample_id,
            "signal.values",
            "sinyal NaN veya Inf içeremez",
        )
        return

    if _is_constant(signal, policy.constant_tolerance):
        _add_issue(
            issues,
            "signal.constant",
            candidate.sample_id,
            "signal.values",
            "sabit sinyal kaydı kabul edilmez",
        )

    amplitudes = _amplitudes(signal, policy.representation)
    max_amplitude = float(np.max(amplitudes))
    if max_amplitude > policy.max_amplitude:
        _add_issue(
            issues,
            "signal.amplitude_out_of_range",
            candidate.sample_id,
            "signal.amplitude",
            f"maksimum genlik {policy.max_amplitude} değerini aşamaz",
            max_amplitude,
        )

    power = float(np.mean(np.square(amplitudes, dtype=np.float64)))
    if power < policy.min_power or power > policy.max_power:
        _add_issue(
            issues,
            "signal.power_out_of_range",
            candidate.sample_id,
            "signal.power",
            f"ortalama güç [{policy.min_power}, {policy.max_power}] aralığında olmalıdır",
            power,
        )


def _validate_label(
    candidate: SampleCandidate,
    policy: ValidationPolicy,
    issues: list[ValidationIssue],
) -> None:
    if not _is_label(candidate.label) or candidate.label not in policy.allowed_labels:
        _add_issue(
            issues,
            "label.not_allowed",
            candidate.sample_id,
            "label",
            "etiket izin verilen label kümesinde bulunmalıdır",
            candidate.label,
        )


def _validate_snr(
    candidate: SampleCandidate,
    policy: ValidationPolicy,
    issues: list[ValidationIssue],
) -> None:
    snr = candidate.snr_db
    if snr is None:
        return
    if isinstance(snr, bool) or not isinstance(snr, (int, float, np.integer, np.floating)):
        _add_issue(
            issues,
            "snr.invalid_type",
            candidate.sample_id,
            "snr_db",
            "SNR sayısal veya null olmalıdır",
            type(snr).__name__,
        )
        return
    if not np.isfinite(snr):
        _add_issue(
            issues,
            "snr.non_finite",
            candidate.sample_id,
            "snr_db",
            "SNR NaN veya Inf olamaz",
            str(snr),
        )
        return
    numeric_snr = float(snr)
    if numeric_snr < policy.snr_min_db or numeric_snr > policy.snr_max_db:
        _add_issue(
            issues,
            "snr.out_of_range",
            candidate.sample_id,
            "snr_db",
            f"SNR [{policy.snr_min_db}, {policy.snr_max_db}] aralığında olmalıdır",
            numeric_snr,
        )


def _shape_is_valid(signal: np.ndarray[Any, Any], representation: IQRepresentation) -> bool:
    if representation is IQRepresentation.CHANNELS_FIRST:
        return signal.ndim == 2 and signal.shape[0] == 2
    return signal.ndim == 1


def _is_constant(signal: np.ndarray[Any, Any], tolerance: float) -> bool:
    reference = signal[..., :1]
    return bool(np.max(np.abs(signal - reference)) <= tolerance)


def _amplitudes(
    signal: np.ndarray[Any, Any],
    representation: IQRepresentation,
) -> np.ndarray[Any, Any]:
    if representation is IQRepresentation.CHANNELS_FIRST:
        return np.hypot(signal[0], signal[1])
    return np.abs(signal)


def _add_issue(
    issues: list[ValidationIssue],
    error_code: str,
    sample_id: str,
    field: str,
    message: str,
    observed: Any = None,
) -> None:
    issues.append(
        ValidationIssue(
            error_code=error_code,
            sample_id=sample_id,
            field=field,
            message=message,
            observed=observed,
        )
    )


def _is_label(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, str) and bool(value.strip())
    )


def _required_positive_int(value: Mapping[str, Any], field: str) -> int:
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, int) or result <= 0:
        raise ValidationPolicyError(f"{field} pozitif integer olmalıdır")
    return result


def _required_float(value: Mapping[str, Any], field: str) -> float:
    if field not in value:
        raise ValidationPolicyError(f"{field} zorunludur")
    return _finite_float(value[field], field)


def _optional_float(value: Mapping[str, Any], field: str, default: float) -> float:
    return _finite_float(value.get(field, default), field)


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationPolicyError(f"{field} sonlu number olmalıdır")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationPolicyError(f"{field} sonlu number olmalıdır")
    return result
