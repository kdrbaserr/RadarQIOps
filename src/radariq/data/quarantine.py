"""Deterministic quarantine decisions and immutable quality-report artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from radariq.data.leakage import DuplicateLeakageReport, LeakageIssue
from radariq.data.validation import ValidationReport

QUARANTINE_SCHEMA_VERSION = "1.0"


class QuarantineArtifactError(RuntimeError):
    """Raised when reports cannot produce complete and trustworthy artifacts."""


class ArtifactStatus(StrEnum):
    CREATED = "created"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class QuarantinePolicy:
    """Versioned, fail-closed decisions for unresolved quality findings."""

    policy_version: str = "1.0"
    exact_duplicate_action: str = "keep_lowest_sample_id"
    near_duplicate_action: str = "quarantine_all"
    unresolved_group_action: str = "quarantine"
    evidence_limit_per_error: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise QuarantineArtifactError("policy_version boş olmayan string olmalıdır")
        if self.exact_duplicate_action != "keep_lowest_sample_id":
            raise QuarantineArtifactError(
                "exact_duplicate_action yalnız keep_lowest_sample_id olabilir"
            )
        if self.near_duplicate_action != "quarantine_all":
            raise QuarantineArtifactError("near_duplicate_action yalnız quarantine_all olabilir")
        if self.unresolved_group_action != "quarantine":
            raise QuarantineArtifactError("unresolved_group_action yalnız quarantine olabilir")
        if (
            isinstance(self.evidence_limit_per_error, bool)
            or not isinstance(self.evidence_limit_per_error, int)
            or self.evidence_limit_per_error <= 0
        ):
            raise QuarantineArtifactError("evidence_limit_per_error pozitif integer olmalıdır")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> QuarantinePolicy:
        return cls(
            policy_version=value.get("policy_version", "1.0"),
            exact_duplicate_action=value.get("exact_duplicate_action", "keep_lowest_sample_id"),
            near_duplicate_action=value.get("near_duplicate_action", "quarantine_all"),
            unresolved_group_action=value.get("unresolved_group_action", "quarantine"),
            evidence_limit_per_error=value.get("evidence_limit_per_error", 3),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "exact_duplicate_action": self.exact_duplicate_action,
            "near_duplicate_action": self.near_duplicate_action,
            "unresolved_group_action": self.unresolved_group_action,
            "evidence_limit_per_error": self.evidence_limit_per_error,
        }


@dataclass(frozen=True, slots=True)
class QualityLineage:
    """Immutable identities of the raw data and policies used by the decision."""

    raw_manifest_sha256: str
    validation_policy_sha256: str
    leakage_policy_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "raw_manifest_sha256",
            "validation_policy_sha256",
            "leakage_policy_sha256",
        ):
            _require_sha256(getattr(self, field), field)

    def as_dict(self) -> dict[str, str]:
        return {
            "raw_manifest_sha256": self.raw_manifest_sha256,
            "validation_policy_sha256": self.validation_policy_sha256,
            "leakage_policy_sha256": self.leakage_policy_sha256,
        }


@dataclass(frozen=True, slots=True)
class QuarantineEvidence:
    error_code: str
    related_sample_ids: tuple[str, ...] = ()
    group_id: str | None = None
    splits: tuple[str, ...] = ()
    similarity: float | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"error_code": self.error_code}
        if self.related_sample_ids:
            result["related_sample_ids"] = list(self.related_sample_ids)
        if self.group_id is not None:
            result["group_id"] = self.group_id
        if self.splits:
            result["splits"] = list(self.splits)
        if self.similarity is not None:
            result["similarity"] = self.similarity
        return result


@dataclass(frozen=True, slots=True)
class QuarantineEntry:
    sample_id: str
    error_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    duplicate_of: str | None = None
    evidence: tuple[QuarantineEvidence, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sample_id": self.sample_id,
            "status": "quarantined",
            "error_codes": list(self.error_codes),
            "reasons": list(self.reasons),
            "evidence": [item.as_dict() for item in self.evidence],
        }
        if self.duplicate_of is not None:
            result["duplicate_of"] = self.duplicate_of
        return result


@dataclass(frozen=True, slots=True)
class QuarantineDecision:
    policy: QuarantinePolicy
    lineage: QualityLineage
    validation_report_sha256: str
    leakage_report_sha256: str
    total_count: int
    accepted_sample_ids: tuple[str, ...]
    quarantine_entries: tuple[QuarantineEntry, ...]

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_sample_ids)

    @property
    def quarantine_count(self) -> int:
        return len(self.quarantine_entries)

    @property
    def error_counts(self) -> dict[str, int]:
        counts = Counter(code for entry in self.quarantine_entries for code in entry.error_codes)
        return dict(sorted(counts.items()))

    def error_summary(self) -> list[dict[str, Any]]:
        samples: dict[str, list[str]] = defaultdict(list)
        for entry in self.quarantine_entries:
            for code in entry.error_codes:
                samples[code].append(entry.sample_id)
        return [
            {
                "error_code": code,
                "count": self.error_counts[code],
                "evidence_sample_ids": sorted(samples[code])[
                    : self.policy.evidence_limit_per_error
                ],
            }
            for code in sorted(samples)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUARANTINE_SCHEMA_VERSION,
            "policy": self.policy.as_dict(),
            "lineage": {
                **self.lineage.as_dict(),
                "validation_report_sha256": self.validation_report_sha256,
                "leakage_report_sha256": self.leakage_report_sha256,
            },
            "total_count": self.total_count,
            "accepted_count": self.accepted_count,
            "quarantine_count": self.quarantine_count,
            "accepted_sample_ids": list(self.accepted_sample_ids),
            "quarantine": [entry.as_dict() for entry in self.quarantine_entries],
            "error_counts": self.error_counts,
            "error_summary": self.error_summary(),
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class QuarantineArtifactResult:
    status: ArtifactStatus
    output_directory: Path
    decision_sha256: str
    file_sha256: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "output_directory": str(self.output_directory),
            "decision_sha256": self.decision_sha256,
            "file_sha256": dict(sorted(self.file_sha256.items())),
        }


def build_quarantine_decision(
    validation_report: ValidationReport,
    leakage_report: DuplicateLeakageReport,
    policy: QuarantinePolicy,
    lineage: QualityLineage,
) -> QuarantineDecision:
    """Classify every sample as accepted or quarantined without touching raw data."""

    universe = _validate_report_universe(validation_report, leakage_report)
    codes: dict[str, set[str]] = defaultdict(set)
    reasons: dict[str, set[str]] = defaultdict(set)
    evidence: dict[str, list[QuarantineEvidence]] = defaultdict(list)
    duplicate_of: dict[str, str] = {}

    for validation_issue in validation_report.issues:
        _record(
            codes,
            reasons,
            validation_issue.sample_id,
            validation_issue.error_code,
            validation_issue.message,
        )

    label_conflict_samples = {
        sample_id
        for leakage_issue in leakage_report.issues
        if leakage_issue.error_code == "duplicate.label_conflict"
        for sample_id in leakage_issue.sample_ids
    }
    for cluster in leakage_report.exact_duplicate_clusters:
        if label_conflict_samples.intersection(cluster.sample_ids):
            for sample_id in cluster.sample_ids:
                _record(
                    codes,
                    reasons,
                    sample_id,
                    "duplicate.label_conflict",
                    "aynı canonical sinyal çelişkili label değerleri taşıyor",
                )
                _record(
                    codes,
                    reasons,
                    sample_id,
                    "duplicate.exact",
                    "label çatışması çözülene kadar exact duplicate kümesi dışlandı",
                )
        else:
            canonical = min(cluster.sample_ids)
            for sample_id in cluster.sample_ids:
                if sample_id == canonical:
                    continue
                _record(
                    codes,
                    reasons,
                    sample_id,
                    "duplicate.exact",
                    "exact duplicate kümesinin deterministik canonical örneği korundu",
                )
                duplicate_of[sample_id] = canonical
                evidence[sample_id].append(
                    QuarantineEvidence(
                        error_code="duplicate.exact",
                        related_sample_ids=(canonical,),
                    )
                )

    for pair in leakage_report.near_duplicate_pairs:
        for sample_id in pair.sample_ids:
            related = tuple(item for item in pair.sample_ids if item != sample_id)
            _record(
                codes,
                reasons,
                sample_id,
                "duplicate.near",
                "near duplicate kararı dataset incelemesi tamamlanana kadar dışlandı",
            )
            evidence[sample_id].append(
                QuarantineEvidence(
                    error_code="duplicate.near",
                    related_sample_ids=related,
                    similarity=pair.similarity,
                )
            )

    handled_codes = {"duplicate.exact", "duplicate.near", "duplicate.label_conflict"}
    for leakage_issue in leakage_report.issues:
        if leakage_issue.error_code in handled_codes:
            continue
        for sample_id in leakage_issue.sample_ids:
            _record(
                codes,
                reasons,
                sample_id,
                leakage_issue.error_code,
                leakage_issue.message,
            )
            evidence[sample_id].append(_evidence_from_issue(leakage_issue, sample_id))

    quarantine_entries = tuple(
        QuarantineEntry(
            sample_id=sample_id,
            error_codes=tuple(sorted(codes[sample_id])),
            reasons=tuple(sorted(reasons[sample_id])),
            duplicate_of=duplicate_of.get(sample_id),
            evidence=tuple(sorted(evidence[sample_id], key=_evidence_sort_key)),
        )
        for sample_id in sorted(codes)
    )
    quarantined_ids = {entry.sample_id for entry in quarantine_entries}
    accepted_ids = tuple(sorted(universe.difference(quarantined_ids)))
    decision = QuarantineDecision(
        policy=policy,
        lineage=lineage,
        validation_report_sha256=_validation_report_sha256(validation_report),
        leakage_report_sha256=leakage_report.sha256,
        total_count=len(universe),
        accepted_sample_ids=accepted_ids,
        quarantine_entries=quarantine_entries,
    )
    _require_complete_partition(decision, universe)
    return decision


def write_quarantine_artifacts(
    decision: QuarantineDecision,
    output_directory: str | Path,
) -> QuarantineArtifactResult:
    """Atomically publish deterministic JSON and Markdown artifacts."""

    destination = Path(output_directory).expanduser().resolve()
    payloads = _artifact_payloads(decision)
    if destination.exists():
        _verify_existing_artifacts(destination, payloads)
        return _artifact_result(ArtifactStatus.REUSED, destination, decision, payloads)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
        )
    )
    try:
        for name, payload in payloads.items():
            _write_fsync(temporary / name, payload)
        try:
            temporary.rename(destination)
        except FileExistsError:
            _verify_existing_artifacts(destination, payloads)
            return _artifact_result(ArtifactStatus.REUSED, destination, decision, payloads)
        return _artifact_result(ArtifactStatus.CREATED, destination, decision, payloads)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _validate_report_universe(
    validation_report: ValidationReport,
    leakage_report: DuplicateLeakageReport,
) -> set[str]:
    validation_ids = [
        *validation_report.valid_sample_ids,
        *validation_report.invalid_sample_ids,
    ]
    if len(validation_ids) != len(set(validation_ids)):
        raise QuarantineArtifactError("validation report benzersiz sample_id değerleri gerektirir")
    if validation_report.total_count != len(validation_ids):
        raise QuarantineArtifactError("validation report total_count örnek listeleriyle eşleşmiyor")
    leakage_ids = [sample_id for sample_id, _ in leakage_report.group_assignments]
    if len(leakage_ids) != len(set(leakage_ids)):
        raise QuarantineArtifactError("leakage report benzersiz sample_id değerleri gerektirir")
    if leakage_report.total_count != len(leakage_ids):
        raise QuarantineArtifactError("leakage report total_count group listesiyle eşleşmiyor")
    valid_ids = set(validation_report.valid_sample_ids)
    if valid_ids != set(leakage_ids):
        raise QuarantineArtifactError(
            "leakage raporu validation tarafından kabul edilen sample kümesini içermiyor"
        )
    universe = set(validation_ids)
    for validation_issue in validation_report.issues:
        if validation_issue.sample_id not in universe:
            raise QuarantineArtifactError("validation issue bilinmeyen sample_id içeriyor")
    for leakage_issue in leakage_report.issues:
        if not set(leakage_issue.sample_ids).issubset(valid_ids):
            raise QuarantineArtifactError("leakage issue bilinmeyen sample_id içeriyor")
    return universe


def _require_complete_partition(decision: QuarantineDecision, universe: set[str]) -> None:
    accepted = set(decision.accepted_sample_ids)
    quarantined = {entry.sample_id for entry in decision.quarantine_entries}
    if accepted.intersection(quarantined):
        raise QuarantineArtifactError("accepted ve quarantine sample kümeleri kesişemez")
    if accepted.union(quarantined) != universe:
        raise QuarantineArtifactError("her sample accepted veya quarantine durumunda olmalıdır")
    if decision.total_count != decision.accepted_count + decision.quarantine_count:
        raise QuarantineArtifactError("total_count = accepted_count + quarantine_count sağlanmalı")


def _record(
    codes: dict[str, set[str]],
    reasons: dict[str, set[str]],
    sample_id: str,
    error_code: str,
    reason: str,
) -> None:
    codes[sample_id].add(error_code)
    reasons[sample_id].add(reason)


def _evidence_from_issue(issue: LeakageIssue, sample_id: str) -> QuarantineEvidence:
    return QuarantineEvidence(
        error_code=issue.error_code,
        related_sample_ids=tuple(item for item in issue.sample_ids if item != sample_id),
        group_id=issue.group_id,
        splits=issue.splits,
        similarity=issue.similarity,
    )


def _evidence_sort_key(evidence: QuarantineEvidence) -> tuple[Any, ...]:
    return (
        evidence.error_code,
        evidence.related_sample_ids,
        evidence.group_id or "",
        evidence.splits,
        evidence.similarity if evidence.similarity is not None else -1.0,
    )


def _artifact_payloads(decision: QuarantineDecision) -> dict[str, bytes]:
    accepted_manifest = {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "decision_sha256": decision.sha256,
        "lineage": decision.as_dict()["lineage"],
        "accepted_count": decision.accepted_count,
        "sample_ids": list(decision.accepted_sample_ids),
    }
    quarantine_manifest = {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "decision_sha256": decision.sha256,
        "lineage": decision.as_dict()["lineage"],
        "quarantine_count": decision.quarantine_count,
        "samples": [entry.as_dict() for entry in decision.quarantine_entries],
    }
    report = decision.as_dict()
    report["decision_sha256"] = decision.sha256
    return {
        "accepted-manifest.json": _json_bytes(accepted_manifest),
        "quarantine-manifest.json": _json_bytes(quarantine_manifest),
        "validation-report.json": _json_bytes(report),
        "validation-report.md": _markdown_report(decision).encode("utf-8"),
    }


def _markdown_report(decision: QuarantineDecision) -> str:
    lines = [
        "# Veri kalite ve quarantine raporu",
        "",
        f"- Karar SHA-256: `{decision.sha256}`",
        f"- Toplam örnek: {decision.total_count}",
        f"- Kabul edilen: {decision.accepted_count}",
        f"- Quarantine: {decision.quarantine_count}",
        "",
        "## Hata dağılımı",
        "",
        "| Hata kodu | Sayı | Örnek kanıtları |",
        "|---|---:|---|",
    ]
    if decision.error_summary():
        for item in decision.error_summary():
            evidence = ", ".join(
                f"`{_markdown_cell(sample_id)}`" for sample_id in item["evidence_sample_ids"]
            )
            lines.append(
                f"| `{_markdown_cell(item['error_code'])}` | {item['count']} | {evidence} |"
            )
    else:
        lines.append("| Yok | 0 | - |")
    lines.extend(
        [
            "",
            "## Soy ağacı",
            "",
            f"- Raw manifest: `{decision.lineage.raw_manifest_sha256}`",
            f"- Validation policy: `{decision.lineage.validation_policy_sha256}`",
            f"- Leakage policy: `{decision.lineage.leakage_policy_sha256}`",
            f"- Validation report: `{decision.validation_report_sha256}`",
            f"- Leakage report: `{decision.leakage_report_sha256}`",
            f"- Quarantine policy: `{decision.policy.policy_version}`",
            "",
            "Raw örnekler silinmemiş veya taşınmamıştır; bu rapor yalnız eğitim uygunluğunu belirler.",
        ]
    )
    return "\n".join(lines) + "\n"


def _verify_existing_artifacts(destination: Path, payloads: Mapping[str, bytes]) -> None:
    if not destination.is_dir():
        raise QuarantineArtifactError(f"artifact hedefi dizin olmalıdır: {destination}")
    entries = list(destination.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise QuarantineArtifactError("quarantine artifact dizini yalnız normal dosya içerebilir")
    actual_files = {path.name for path in entries}
    if actual_files != set(payloads):
        raise QuarantineArtifactError("mevcut quarantine artifact dosya kümesi farklı")
    for name, payload in payloads.items():
        if (destination / name).read_bytes() != payload:
            raise QuarantineArtifactError(
                "mevcut artifact farklı içerikle yerinde değiştirilemez; yeni output yolu kullanın"
            )


def _artifact_result(
    status: ArtifactStatus,
    destination: Path,
    decision: QuarantineDecision,
    payloads: Mapping[str, bytes],
) -> QuarantineArtifactResult:
    return QuarantineArtifactResult(
        status=status,
        output_directory=destination,
        decision_sha256=decision.sha256,
        file_sha256={
            name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()
        },
    )


def _write_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _validation_report_sha256(report: ValidationReport) -> str:
    payload = report.as_dict()
    payload["valid_sample_ids"] = sorted(payload["valid_sample_ids"])
    payload["invalid_sample_ids"] = sorted(payload["invalid_sample_ids"])
    payload["issues"] = sorted(
        (_json_safe(item) for item in payload["issues"]),
        key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True),
    )
    return _canonical_sha256(payload)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_bytes(value: Any) -> bytes:
    payload = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    return (payload + "\n").encode("utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _markdown_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _require_sha256(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise QuarantineArtifactError(f"{field} geçerli küçük harf SHA-256 olmalıdır")
