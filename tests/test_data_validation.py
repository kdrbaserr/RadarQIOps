from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from radariq.data.contracts import IQRepresentation
from radariq.data.validation import (
    SampleCandidate,
    ValidationPolicy,
    ValidationPolicyError,
    validate_samples,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def policy() -> ValidationPolicy:
    return ValidationPolicy(
        representation=IQRepresentation.CHANNELS_FIRST,
        signal_length=4,
        allowed_labels=frozenset({"BPSK", "QPSK"}),
        snr_min_db=-20.0,
        snr_max_db=20.0,
        max_amplitude=1.0,
        min_power=0.001,
        max_power=10.0,
    )


def valid_signal() -> np.ndarray:
    return np.array(
        [[0.1, -0.1, 0.2, -0.2], [0.2, -0.2, 0.1, -0.1]],
        dtype=np.float32,
    )


def candidate(
    sample_id: str = "sample-001",
    *,
    signal: object | None = None,
    label: object = "BPSK",
    snr_db: object = -6.0,
) -> SampleCandidate:
    return SampleCandidate(
        sample_id=sample_id,
        signal=valid_signal() if signal is None else signal,
        label=label,
        snr_db=snr_db,
    )


def error_codes(
    sample: SampleCandidate, selected_policy: ValidationPolicy | None = None
) -> set[str]:
    report = validate_samples([sample], selected_policy or policy())
    return {issue.error_code for issue in report.issues}


def test_valid_channels_first_sample_is_accepted() -> None:
    report = validate_samples([candidate()], policy())

    assert report.total_count == 1
    assert report.valid_count == 1
    assert report.invalid_count == 0
    assert report.error_counts == {}


def test_valid_complex64_sample_is_accepted() -> None:
    complex_policy = replace(policy(), representation=IQRepresentation.COMPLEX)
    signal = np.array([0.1 + 0.2j, -0.1 - 0.2j, 0.2 + 0.1j, -0.2 - 0.1j], dtype=np.complex64)

    assert validate_samples([candidate(signal=signal)], complex_policy).valid_count == 1


def test_invalid_shape_has_its_own_error_code() -> None:
    assert error_codes(candidate(signal=np.zeros(4, dtype=np.float32))) == {"signal.invalid_shape"}


def test_invalid_length_has_its_own_error_code() -> None:
    signal = np.zeros((2, 5), dtype=np.float32)
    signal[0, 1] = 0.1
    assert "signal.invalid_length" in error_codes(candidate(signal=signal))


def test_invalid_dtype_has_its_own_error_code() -> None:
    assert error_codes(candidate(signal=valid_signal().astype(np.float64))) == {
        "signal.invalid_dtype"
    }


def test_empty_record_is_reported() -> None:
    codes = error_codes(candidate(signal=np.empty((2, 0), dtype=np.float32)))
    assert "signal.empty" in codes
    assert "signal.invalid_length" in codes


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_signal_values_are_reported(value: float) -> None:
    signal = valid_signal()
    signal[0, 0] = value
    assert error_codes(candidate(signal=signal)) == {"signal.non_finite"}


def test_constant_signal_is_reported() -> None:
    signal = np.full((2, 4), 0.2, dtype=np.float32)
    assert "signal.constant" in error_codes(candidate(signal=signal))


def test_amplitude_limit_is_reported() -> None:
    signal = valid_signal()
    signal[:, 0] = 0.8
    assert "signal.amplitude_out_of_range" in error_codes(candidate(signal=signal))


def test_power_limit_is_reported() -> None:
    strict_power = replace(policy(), max_power=0.04)
    assert error_codes(candidate(), strict_power) == {"signal.power_out_of_range"}


def test_unknown_label_is_reported() -> None:
    assert error_codes(candidate(label="UNKNOWN")) == {"label.not_allowed"}


@pytest.mark.parametrize("snr", [-21.0, 21.0])
def test_snr_range_violation_is_reported(snr: float) -> None:
    assert error_codes(candidate(snr_db=snr)) == {"snr.out_of_range"}


@pytest.mark.parametrize("snr", [float("nan"), float("inf")])
def test_non_finite_snr_is_reported(snr: float) -> None:
    assert error_codes(candidate(snr_db=snr)) == {"snr.non_finite"}


def test_nullable_snr_remains_valid() -> None:
    assert validate_samples([candidate(snr_db=None)], policy()).valid_count == 1


def test_report_contains_sample_ids_counts_and_all_violations() -> None:
    report = validate_samples(
        [
            candidate("accepted"),
            candidate("bad-label", label="UNKNOWN"),
            candidate("bad-snr", snr_db=99.0),
        ],
        policy(),
    )

    assert report.total_count == report.valid_count + report.invalid_count == 3
    assert report.valid_sample_ids == ("accepted",)
    assert report.invalid_sample_ids == ("bad-label", "bad-snr")
    assert report.error_counts == {"label.not_allowed": 1, "snr.out_of_range": 1}
    assert [issue.sample_id for issue in report.issues] == ["bad-label", "bad-snr"]


def test_policy_can_be_loaded_from_json_compatible_mapping() -> None:
    loaded = ValidationPolicy.from_mapping(
        {
            "representation": "channels_first",
            "signal_length": 128,
            "allowed_labels": ["BPSK", "QPSK"],
            "snr_min_db": -20,
            "snr_max_db": 20,
            "max_amplitude": 4,
            "min_power": 1e-8,
            "max_power": 8,
            "constant_tolerance": 1e-7,
        }
    )

    assert loaded.signal_length == 128
    assert loaded.allowed_labels == frozenset({"BPSK", "QPSK"})


@pytest.mark.parametrize(
    "updates",
    [
        {"signal_length": 0},
        {"allowed_labels": frozenset()},
        {"snr_min_db": 21.0},
        {"max_amplitude": 0.0},
        {"min_power": -1.0},
        {"constant_tolerance": -1.0},
    ],
)
def test_invalid_policy_fails_before_samples_are_processed(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationPolicyError):
        replace(policy(), **updates)
