from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import radariq.data.quarantine as quarantine_module
from radariq.data.contracts import IQRepresentation
from radariq.data.leakage import (
    DuplicatePolicy,
    ExplicitGroupIdAdapter,
    LeakageCandidate,
    analyze_duplicates_and_leakage,
)
from radariq.data.quarantine import (
    ArtifactStatus,
    QualityLineage,
    QuarantineArtifactError,
    QuarantinePolicy,
    build_quarantine_decision,
    write_quarantine_artifacts,
)
from radariq.data.validation import (
    SampleCandidate,
    ValidationPolicy,
    validate_samples,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def signal(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, 0.2, size=(2, 64)).astype(np.float32)


def validation_policy() -> ValidationPolicy:
    return ValidationPolicy(
        representation=IQRepresentation.CHANNELS_FIRST,
        signal_length=64,
        allowed_labels=frozenset({"BPSK", "QPSK"}),
        snr_min_db=-20,
        snr_max_db=20,
        max_amplitude=4,
        min_power=1e-8,
        max_power=8,
    )


def duplicate_policy() -> DuplicatePolicy:
    return DuplicatePolicy(
        representation=IQRepresentation.CHANNELS_FIRST,
        correlation_threshold=0.999,
        quantization_decimals=3,
    )


def lineage() -> QualityLineage:
    return QualityLineage(
        raw_manifest_sha256="a" * 64,
        validation_policy_sha256="b" * 64,
        leakage_policy_sha256="c" * 64,
    )


def reports(
    samples: list[tuple[str, np.ndarray, str, str | None]],
):
    validation = validate_samples(
        [
            SampleCandidate(sample_id, sample_signal, label, -6.0)
            for sample_id, sample_signal, label, _ in samples
        ],
        validation_policy(),
    )
    valid_ids = set(validation.valid_sample_ids)
    leakage = analyze_duplicates_and_leakage(
        [
            LeakageCandidate(
                sample_id=sample_id,
                signal=sample_signal,
                label=label,
                group_id=group_id,
            )
            for sample_id, sample_signal, label, group_id in samples
            if sample_id in valid_ids
        ],
        duplicate_policy(),
        ExplicitGroupIdAdapter(),
    )
    return validation, leakage


def test_total_equals_accepted_plus_quarantine_and_sets_partition_all_samples() -> None:
    bad_signal = signal(1)
    bad_signal[0, 0] = np.nan
    samples = [
        ("accepted", signal(2), "BPSK", "group-a"),
        ("bad-signal", bad_signal, "BPSK", "group-b"),
    ]
    validation, leakage = reports(samples)

    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert decision.total_count == decision.accepted_count + decision.quarantine_count == 2
    assert decision.accepted_sample_ids == ("accepted",)
    assert decision.quarantine_entries[0].sample_id == "bad-signal"
    assert decision.quarantine_entries[0].error_codes == ("signal.non_finite",)


def test_exact_duplicate_keeps_only_lowest_sample_id() -> None:
    duplicate = signal(3)
    validation, leakage = reports(
        [
            ("sample-b", duplicate.copy(), "BPSK", "group-b"),
            ("sample-a", duplicate, "BPSK", "group-a"),
        ]
    )

    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert decision.accepted_sample_ids == ("sample-a",)
    assert decision.quarantine_entries[0].sample_id == "sample-b"
    assert decision.quarantine_entries[0].duplicate_of == "sample-a"


def test_label_conflict_quarantines_entire_exact_cluster() -> None:
    duplicate = signal(4)
    validation, leakage = reports(
        [
            ("sample-a", duplicate, "BPSK", "group-a"),
            ("sample-b", duplicate.copy(), "QPSK", "group-b"),
        ]
    )

    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert decision.accepted_count == 0
    assert {entry.sample_id for entry in decision.quarantine_entries} == {
        "sample-a",
        "sample-b",
    }
    assert all(
        "duplicate.label_conflict" in entry.error_codes for entry in decision.quarantine_entries
    )


def test_near_duplicate_quarantines_both_with_similarity_evidence() -> None:
    original = signal(5)
    changed = (original.astype(np.float64) * 1.01 + 1e-6).astype(np.float32)
    validation, leakage = reports(
        [
            ("sample-a", original, "BPSK", "group-a"),
            ("sample-b", changed, "BPSK", "group-b"),
        ]
    )

    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert decision.accepted_count == 0
    assert decision.error_counts == {"duplicate.near": 2}
    assert all(entry.evidence[0].similarity is not None for entry in decision.quarantine_entries)


def test_unresolved_group_is_quarantined_for_training_eligibility() -> None:
    validation, leakage = reports([("sample-a", signal(6), "BPSK", None)])

    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert decision.accepted_count == 0
    assert decision.quarantine_entries[0].error_codes == ("group.unresolved",)


def test_error_summary_uses_deterministic_bounded_evidence() -> None:
    samples = [
        (f"sample-{index}", signal(10 + index), "UNKNOWN", f"group-{index}") for index in range(5)
    ]
    validation, leakage = reports(samples)
    decision = build_quarantine_decision(
        validation,
        leakage,
        QuarantinePolicy(evidence_limit_per_error=2),
        lineage(),
    )

    summary = next(
        item for item in decision.error_summary() if item["error_code"] == "label.not_allowed"
    )
    assert summary == {
        "error_code": "label.not_allowed",
        "count": 5,
        "evidence_sample_ids": ["sample-0", "sample-1"],
    }


def test_artifacts_are_atomic_reproducible_and_do_not_touch_raw(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw" / "sample.iq"
    raw_path.parent.mkdir()
    raw_path.write_bytes(b"immutable-raw")
    raw_bytes = raw_path.read_bytes()
    raw_mtime = raw_path.stat().st_mtime_ns
    validation, leakage = reports([("sample-a", signal(20), "BPSK", "group-a")])
    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())
    output = tmp_path / "artifacts" / "quality-v1"

    first = write_quarantine_artifacts(decision, output)
    second = write_quarantine_artifacts(decision, output)

    assert first.status is ArtifactStatus.CREATED
    assert second.status is ArtifactStatus.REUSED
    assert first.file_sha256 == second.file_sha256
    assert raw_path.read_bytes() == raw_bytes
    assert raw_path.stat().st_mtime_ns == raw_mtime
    assert not list(output.parent.glob("*.part"))


def test_json_and_markdown_reports_have_consistent_counts(tmp_path: Path) -> None:
    validation, leakage = reports([("sample-a", signal(21), "BPSK", None)])
    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())
    output = tmp_path / "quality"
    write_quarantine_artifacts(decision, output)

    json_report = json.loads((output / "validation-report.json").read_text(encoding="utf-8"))
    markdown = (output / "validation-report.md").read_text(encoding="utf-8")

    assert json_report["total_count"] == 1
    assert json_report["accepted_count"] == 0
    assert json_report["quarantine_count"] == 1
    assert "- Toplam örnek: 1" in markdown
    assert "- Kabul edilen: 0" in markdown
    assert "- Quarantine: 1" in markdown


def test_existing_artifacts_cannot_be_mutated_in_place(tmp_path: Path) -> None:
    validation, leakage = reports([("sample-a", signal(22), "BPSK", "group-a")])
    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())
    output = tmp_path / "quality"
    write_quarantine_artifacts(decision, output)
    (output / "validation-report.json").write_text("{}", encoding="utf-8")

    with pytest.raises(QuarantineArtifactError, match="yerinde değiştirilemez"):
        write_quarantine_artifacts(decision, output)


def test_same_semantic_input_produces_same_decision_hash_independent_of_order() -> None:
    samples = [
        ("sample-a", signal(25), "BPSK", "group-a"),
        ("sample-b", signal(26), "QPSK", "group-b"),
    ]
    first_validation, first_leakage = reports(samples)
    second_validation, second_leakage = reports(list(reversed(samples)))

    first = build_quarantine_decision(
        first_validation, first_leakage, QuarantinePolicy(), lineage()
    )
    second = build_quarantine_decision(
        second_validation, second_leakage, QuarantinePolicy(), lineage()
    )

    assert first.as_dict() == second.as_dict()
    assert first.sha256 == second.sha256


def test_artifact_write_failure_leaves_no_final_or_partial_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation, leakage = reports([("sample-a", signal(27), "BPSK", "group-a")])
    decision = build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())
    output = tmp_path / "quality"
    writes = 0
    original_write = quarantine_module._write_fsync

    def fail_during_write(path: Path, payload: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("fixture write failure")
        original_write(path, payload)

    monkeypatch.setattr(quarantine_module, "_write_fsync", fail_during_write)

    with pytest.raises(OSError, match="fixture write failure"):
        write_quarantine_artifacts(decision, output)

    assert not output.exists()
    assert not list(tmp_path.glob("*.part"))


def test_mismatched_report_sample_sets_fail_before_artifact_write(tmp_path: Path) -> None:
    validation, _ = reports([("sample-a", signal(23), "BPSK", "group-a")])
    _, leakage = reports([("sample-b", signal(24), "BPSK", "group-b")])

    with pytest.raises(QuarantineArtifactError, match="validation tarafından kabul edilen"):
        build_quarantine_decision(validation, leakage, QuarantinePolicy(), lineage())

    assert not (tmp_path / "quality").exists()


def test_policy_can_be_loaded_from_json_compatible_mapping() -> None:
    policy = QuarantinePolicy.from_mapping(
        {
            "policy_version": "1.0",
            "exact_duplicate_action": "keep_lowest_sample_id",
            "near_duplicate_action": "quarantine_all",
            "unresolved_group_action": "quarantine",
            "evidence_limit_per_error": 5,
        }
    )

    assert policy.evidence_limit_per_error == 5
