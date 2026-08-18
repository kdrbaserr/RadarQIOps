from __future__ import annotations

import numpy as np
import pytest

from radariq.data.contracts import IQRepresentation
from radariq.data.leakage import (
    DuplicateLeakageReport,
    DuplicatePolicy,
    ExplicitGroupIdAdapter,
    LeakageAnalysisError,
    LeakageCandidate,
    SourceSequenceGroupAdapter,
    analyze_duplicates_and_leakage,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def policy() -> DuplicatePolicy:
    return DuplicatePolicy(
        representation=IQRepresentation.CHANNELS_FIRST,
        correlation_threshold=0.999,
        quantization_decimals=3,
    )


def signal(seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    return generator.normal(0, 0.2, size=(2, 128)).astype(np.float32)


def candidate(
    sample_id: str,
    sample_signal: np.ndarray,
    *,
    label: str = "BPSK",
    group_id: str | None = "capture-1",
    sequence_id: str | None = "sequence-1",
) -> LeakageCandidate:
    return LeakageCandidate(
        sample_id=sample_id,
        signal=sample_signal,
        label=label,
        group_id=group_id,
        sequence_id=sequence_id,
        source_id="radioml-fixture",
        source_version="v1",
    )


def issue_codes(report: DuplicateLeakageReport) -> set[str]:
    return {issue.error_code for issue in report.issues}


def test_exact_duplicate_cluster_is_detected() -> None:
    duplicate = signal(1)
    report = analyze_duplicates_and_leakage(
        [candidate("a", duplicate), candidate("b", duplicate.copy())],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert report.exact_duplicate_clusters[0].sample_ids == ("a", "b")
    assert "duplicate.exact" in issue_codes(report)
    assert report.split_ready is False


def test_exact_duplicate_with_conflicting_labels_is_reported() -> None:
    duplicate = signal(2)
    report = analyze_duplicates_and_leakage(
        [
            candidate("a", duplicate, label="BPSK"),
            candidate("b", duplicate.copy(), label="QPSK"),
        ],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert "duplicate.label_conflict" in issue_codes(report)


def test_small_numeric_change_is_detected_as_near_duplicate() -> None:
    original = signal(3)
    changed = (original.astype(np.float64) * 1.01 + 1e-6).astype(np.float32)
    report = analyze_duplicates_and_leakage(
        [candidate("a", original), candidate("b", changed)],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert report.near_duplicate_pairs[0].sample_ids == ("a", "b")
    assert report.near_duplicate_pairs[0].similarity >= 0.999
    assert "duplicate.near" in issue_codes(report)


def test_global_phase_and_amplitude_change_is_detected_as_near_duplicate() -> None:
    original = signal(30)
    complex_signal = original[0].astype(np.float64) + 1j * original[1].astype(np.float64)
    changed_complex = complex_signal * 1.2 * np.exp(1j * 0.4)
    changed = np.stack((changed_complex.real, changed_complex.imag)).astype(np.float32)

    report = analyze_duplicates_and_leakage(
        [candidate("a", original), candidate("b", changed)],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert len(report.near_duplicate_pairs) == 1
    assert report.near_duplicate_pairs[0].similarity >= 0.999


def test_distinct_signals_are_not_near_duplicates() -> None:
    report = analyze_duplicates_and_leakage(
        [candidate("a", signal(4)), candidate("b", signal(5))],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert report.exact_duplicate_clusters == ()
    assert report.near_duplicate_pairs == ()
    assert report.split_ready is True


def test_unresolved_group_blocks_split_readiness() -> None:
    report = analyze_duplicates_and_leakage(
        [candidate("a", signal(6), group_id=None)],
        policy(),
        ExplicitGroupIdAdapter(),
    )

    assert report.unresolved_group_count == 1
    assert "group.unresolved" in issue_codes(report)
    assert report.split_ready is False


def test_source_sequence_adapter_is_deterministic_and_versioned() -> None:
    adapter = SourceSequenceGroupAdapter()
    first = candidate("a", signal(7), group_id=None)
    second = candidate("b", signal(8), group_id=None)

    report = analyze_duplicates_and_leakage([first, second], policy(), adapter)

    groups = {group_id for _, group_id in report.group_assignments}
    assert len(groups) == 1
    assert None not in groups
    assert report.group_rule_name == "source-sequence"
    assert report.group_rule_version == "1.0"


def test_same_group_in_different_splits_is_leakage() -> None:
    report = analyze_duplicates_and_leakage(
        [candidate("a", signal(9)), candidate("b", signal(10))],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "train", "b": "test"},
    )

    issue = next(
        issue for issue in report.issues if issue.error_code == "leakage.group_cross_split"
    )
    assert issue.group_id == "capture-1"
    assert issue.splits == ("test", "train")


def test_same_group_inside_one_split_is_not_cross_split_leakage() -> None:
    report = analyze_duplicates_and_leakage(
        [candidate("a", signal(11)), candidate("b", signal(12))],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "train", "b": "train"},
    )

    assert not any(issue.error_code.startswith("leakage.") for issue in report.issues)
    assert report.split_ready is True


def test_distinct_groups_can_be_assigned_to_different_splits() -> None:
    report = analyze_duplicates_and_leakage(
        [
            candidate("a", signal(31), group_id="capture-a"),
            candidate("b", signal(32), group_id="capture-b"),
        ],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "train", "b": "test"},
    )

    assert not any(issue.error_code.startswith("leakage.") for issue in report.issues)
    assert report.split_ready is True


def test_exact_duplicate_across_splits_is_reported() -> None:
    duplicate = signal(13)
    report = analyze_duplicates_and_leakage(
        [
            candidate("a", duplicate, group_id="capture-a"),
            candidate("b", duplicate.copy(), group_id="capture-b"),
        ],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "train", "b": "validation"},
    )

    assert "leakage.exact_cross_split" in issue_codes(report)


def test_near_duplicate_across_splits_contains_similarity_evidence() -> None:
    original = signal(14)
    changed = (original.astype(np.float64) * 0.99 + 1e-6).astype(np.float32)
    report = analyze_duplicates_and_leakage(
        [
            candidate("a", original, group_id="capture-a"),
            candidate("b", changed, group_id="capture-b"),
        ],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "train", "b": "test"},
    )

    issue = next(issue for issue in report.issues if issue.error_code == "leakage.near_cross_split")
    assert issue.similarity is not None and issue.similarity >= 0.999
    assert issue.splits == ("test", "train")


def test_same_input_order_independently_produces_same_report_hash() -> None:
    candidates = [
        candidate("a", signal(15), group_id="capture-a"),
        candidate("b", signal(16), group_id="capture-b"),
    ]
    first = analyze_duplicates_and_leakage(candidates, policy(), ExplicitGroupIdAdapter())
    second = analyze_duplicates_and_leakage(
        list(reversed(candidates)), policy(), ExplicitGroupIdAdapter()
    )

    assert first.as_dict() == second.as_dict()
    assert first.sha256 == second.sha256


def test_missing_or_invalid_split_assignment_blocks_readiness() -> None:
    report = analyze_duplicates_and_leakage(
        [
            candidate("a", signal(17), group_id="capture-a"),
            candidate("b", signal(18), group_id="capture-b"),
        ],
        policy(),
        ExplicitGroupIdAdapter(),
        split_assignments={"a": "unknown"},
    )

    assert {"split.assignment_invalid", "split.assignment_missing"}.issubset(issue_codes(report))
    assert report.split_ready is False


def test_unvalidated_signal_fails_closed_before_duplicate_analysis() -> None:
    invalid = np.zeros((2, 128), dtype=np.float64)

    with pytest.raises(LeakageAnalysisError, match="020 validation geçmemiş"):
        analyze_duplicates_and_leakage(
            [candidate("a", invalid)],
            policy(),
            ExplicitGroupIdAdapter(),
        )


def test_policy_can_be_loaded_from_json_compatible_mapping() -> None:
    loaded = DuplicatePolicy.from_mapping(
        {
            "representation": "channels_first",
            "near_duplicate_enabled": True,
            "correlation_threshold": 0.9995,
            "quantization_decimals": 4,
            "remove_dc": True,
            "allowed_splits": ["train", "validation", "test"],
        }
    )

    assert loaded.correlation_threshold == 0.9995
    assert loaded.quantization_decimals == 4
