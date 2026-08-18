"""Deterministic duplicate, group and cross-split leakage analysis."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from radariq.data.contracts import IQRepresentation


class LeakageAnalysisError(RuntimeError):
    """Raised when leakage analysis cannot produce trustworthy evidence."""


@dataclass(frozen=True, slots=True)
class LeakageCandidate:
    """Validated signal plus source lineage needed for leakage analysis."""

    sample_id: str
    signal: np.ndarray[Any, Any]
    label: str | int
    group_id: str | None = None
    sequence_id: str | None = None
    source_id: str | None = None
    source_version: str | None = None


class GroupIdAdapter(Protocol):
    """Dataset-specific and versioned group derivation rule."""

    rule_name: str
    rule_version: str

    def derive_group_id(self, candidate: LeakageCandidate) -> str | None:
        """Return a stable group identity, or None when evidence is insufficient."""


@dataclass(frozen=True, slots=True)
class ExplicitGroupIdAdapter:
    """Use a source-provided capture/subject/group identity without guessing."""

    rule_name: str = "explicit-group-id"
    rule_version: str = "1.0"

    def derive_group_id(self, candidate: LeakageCandidate) -> str | None:
        return _optional_non_empty(candidate.group_id)


@dataclass(frozen=True, slots=True)
class SourceSequenceGroupAdapter:
    """Derive a private stable group from source version and sequence identity."""

    rule_name: str = "source-sequence"
    rule_version: str = "1.0"

    def derive_group_id(self, candidate: LeakageCandidate) -> str | None:
        source_id = _optional_non_empty(candidate.source_id)
        source_version = _optional_non_empty(candidate.source_version)
        sequence_id = _optional_non_empty(candidate.sequence_id)
        if source_id is None or source_version is None or sequence_id is None:
            return None
        identity = "\0".join((source_id, source_version, sequence_id))
        return "group-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DuplicatePolicy:
    """Deterministic exact and approximate duplicate detection settings."""

    representation: IQRepresentation
    near_duplicate_enabled: bool = True
    correlation_threshold: float = 0.999
    quantization_decimals: int = 3
    remove_dc: bool = True
    allowed_splits: frozenset[str] = frozenset({"train", "validation", "test"})

    def __post_init__(self) -> None:
        if not isinstance(self.representation, IQRepresentation):
            raise LeakageAnalysisError("representation geçerli bir IQRepresentation olmalıdır")
        if not isinstance(self.near_duplicate_enabled, bool):
            raise LeakageAnalysisError("near_duplicate_enabled boolean olmalıdır")
        if (
            isinstance(self.correlation_threshold, bool)
            or not isinstance(self.correlation_threshold, (int, float))
            or not math.isfinite(self.correlation_threshold)
            or not 0.0 <= self.correlation_threshold <= 1.0
        ):
            raise LeakageAnalysisError("correlation_threshold [0, 1] aralığında olmalıdır")
        if (
            isinstance(self.quantization_decimals, bool)
            or not isinstance(self.quantization_decimals, int)
            or not 0 <= self.quantization_decimals <= 8
        ):
            raise LeakageAnalysisError("quantization_decimals 0 ile 8 arasında integer olmalıdır")
        if not isinstance(self.remove_dc, bool):
            raise LeakageAnalysisError("remove_dc boolean olmalıdır")
        if not self.allowed_splits or any(
            not isinstance(split, str) or not split.strip() for split in self.allowed_splits
        ):
            raise LeakageAnalysisError("allowed_splits boş olmayan split adları içermelidir")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DuplicatePolicy:
        raw_representation = value.get("representation")
        if not isinstance(raw_representation, str):
            raise LeakageAnalysisError("representation channels_first veya complex olmalıdır")
        try:
            representation = IQRepresentation(raw_representation)
        except ValueError as exc:
            raise LeakageAnalysisError(
                "representation channels_first veya complex olmalıdır"
            ) from exc
        raw_splits = value.get("allowed_splits", ["train", "validation", "test"])
        if not isinstance(raw_splits, list):
            raise LeakageAnalysisError("allowed_splits bir liste olmalıdır")
        return cls(
            representation=representation,
            near_duplicate_enabled=value.get("near_duplicate_enabled", True),
            correlation_threshold=value.get("correlation_threshold", 0.999),
            quantization_decimals=value.get("quantization_decimals", 3),
            remove_dc=value.get("remove_dc", True),
            allowed_splits=frozenset(raw_splits),
        )


@dataclass(frozen=True, slots=True)
class ExactDuplicateCluster:
    fingerprint: str
    sample_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"fingerprint": self.fingerprint, "sample_ids": list(self.sample_ids)}


@dataclass(frozen=True, slots=True)
class NearDuplicatePair:
    sample_ids: tuple[str, str]
    similarity: float

    def as_dict(self) -> dict[str, Any]:
        return {"sample_ids": list(self.sample_ids), "similarity": self.similarity}


@dataclass(frozen=True, slots=True)
class LeakageIssue:
    error_code: str
    sample_ids: tuple[str, ...]
    message: str
    group_id: str | None = None
    splits: tuple[str, ...] = ()
    similarity: float | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error_code": self.error_code,
            "sample_ids": list(self.sample_ids),
            "message": self.message,
        }
        if self.group_id is not None:
            result["group_id"] = self.group_id
        if self.splits:
            result["splits"] = list(self.splits)
        if self.similarity is not None:
            result["similarity"] = self.similarity
        return result


@dataclass(frozen=True, slots=True)
class DuplicateLeakageReport:
    total_count: int
    group_rule_name: str
    group_rule_version: str
    group_assignments: tuple[tuple[str, str | None], ...]
    exact_duplicate_clusters: tuple[ExactDuplicateCluster, ...]
    near_duplicate_pairs: tuple[NearDuplicatePair, ...]
    issues: tuple[LeakageIssue, ...]

    @property
    def unresolved_group_count(self) -> int:
        return sum(group_id is None for _, group_id in self.group_assignments)

    @property
    def cross_split_leakage_count(self) -> int:
        return sum(issue.error_code.startswith("leakage.") for issue in self.issues)

    @property
    def split_ready(self) -> bool:
        blocking_prefixes = ("duplicate.", "group.", "split.", "leakage.")
        return not any(issue.error_code.startswith(blocking_prefixes) for issue in self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_count": self.total_count,
            "group_rule": {
                "name": self.group_rule_name,
                "version": self.group_rule_version,
            },
            "group_assignments": [
                {"sample_id": sample_id, "group_id": group_id}
                for sample_id, group_id in self.group_assignments
            ],
            "exact_duplicate_cluster_count": len(self.exact_duplicate_clusters),
            "near_duplicate_pair_count": len(self.near_duplicate_pairs),
            "unresolved_group_count": self.unresolved_group_count,
            "cross_split_leakage_count": self.cross_split_leakage_count,
            "split_ready": self.split_ready,
            "exact_duplicate_clusters": [
                cluster.as_dict() for cluster in self.exact_duplicate_clusters
            ],
            "near_duplicate_pairs": [pair.as_dict() for pair in self.near_duplicate_pairs],
            "issues": [issue.as_dict() for issue in self.issues],
        }

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analyze_duplicates_and_leakage(
    candidates: Sequence[LeakageCandidate],
    policy: DuplicatePolicy,
    group_adapter: GroupIdAdapter,
    *,
    split_assignments: Mapping[str, str] | None = None,
) -> DuplicateLeakageReport:
    """Analyze validated candidates without loading or training a model."""

    ordered = sorted(candidates, key=lambda candidate: candidate.sample_id)
    _require_unique_sample_ids(ordered)
    _require_adapter_identity(group_adapter)

    exact_fingerprints: dict[str, str] = {}
    normalized_vectors: dict[str, np.ndarray[Any, Any]] = {}
    labels: dict[str, str | int] = {}
    exact_buckets: dict[str, list[str]] = defaultdict(list)
    near_buckets: dict[str, list[str]] = defaultdict(list)
    group_assignments: list[tuple[str, str | None]] = []
    issues: list[LeakageIssue] = []

    for candidate in ordered:
        _require_candidate(candidate, policy.representation)
        fingerprint = _exact_fingerprint(candidate.signal, policy.representation)
        vector = _normalized_complex_vector(candidate.signal, policy)
        exact_fingerprints[candidate.sample_id] = fingerprint
        normalized_vectors[candidate.sample_id] = vector
        labels[candidate.sample_id] = candidate.label
        exact_buckets[fingerprint].append(candidate.sample_id)
        if policy.near_duplicate_enabled:
            for signature in _near_signatures(vector, policy.quantization_decimals):
                near_buckets[signature].append(candidate.sample_id)

        group_id = group_adapter.derive_group_id(candidate)
        if group_id is not None and (not isinstance(group_id, str) or not group_id.strip()):
            raise LeakageAnalysisError("group adapter boş olmayan string veya None döndürmelidir")
        normalized_group_id = group_id.strip() if group_id is not None else None
        group_assignments.append((candidate.sample_id, normalized_group_id))
        if normalized_group_id is None:
            issues.append(
                LeakageIssue(
                    error_code="group.unresolved",
                    sample_ids=(candidate.sample_id,),
                    message="group-aware split için group_id üretilemedi",
                )
            )

    exact_clusters = _exact_clusters(exact_buckets)
    for cluster in exact_clusters:
        issues.append(
            LeakageIssue(
                error_code="duplicate.exact",
                sample_ids=cluster.sample_ids,
                message="aynı canonical sinyal içeriğine sahip örnekler bulundu",
            )
        )
        if len({labels[sample_id] for sample_id in cluster.sample_ids}) > 1:
            issues.append(
                LeakageIssue(
                    error_code="duplicate.label_conflict",
                    sample_ids=cluster.sample_ids,
                    message="aynı sinyal birden fazla label ile kayıtlı",
                )
            )

    near_pairs = _near_pairs(
        near_buckets,
        normalized_vectors,
        exact_fingerprints,
        policy.correlation_threshold,
    )
    for pair in near_pairs:
        issues.append(
            LeakageIssue(
                error_code="duplicate.near",
                sample_ids=pair.sample_ids,
                message="normalize sinyal korelasyonu near-duplicate eşiğini geçti",
                similarity=pair.similarity,
            )
        )

    if split_assignments is not None:
        issues.extend(
            _split_issues(
                ordered,
                dict(group_assignments),
                exact_clusters,
                near_pairs,
                split_assignments,
                policy.allowed_splits,
            )
        )

    return DuplicateLeakageReport(
        total_count=len(ordered),
        group_rule_name=group_adapter.rule_name,
        group_rule_version=group_adapter.rule_version,
        group_assignments=tuple(group_assignments),
        exact_duplicate_clusters=exact_clusters,
        near_duplicate_pairs=near_pairs,
        issues=tuple(sorted(issues, key=_issue_sort_key)),
    )


def _exact_clusters(
    buckets: Mapping[str, list[str]],
) -> tuple[ExactDuplicateCluster, ...]:
    clusters = [
        ExactDuplicateCluster(fingerprint=fingerprint, sample_ids=tuple(sorted(sample_ids)))
        for fingerprint, sample_ids in buckets.items()
        if len(sample_ids) > 1
    ]
    return tuple(sorted(clusters, key=lambda cluster: cluster.sample_ids))


def _near_pairs(
    buckets: Mapping[str, list[str]],
    vectors: Mapping[str, np.ndarray[Any, Any]],
    exact_fingerprints: Mapping[str, str],
    threshold: float,
) -> tuple[NearDuplicatePair, ...]:
    candidates: set[tuple[str, str]] = set()
    for sample_ids in buckets.values():
        unique_ids = sorted(set(sample_ids))
        for left_index, left_id in enumerate(unique_ids):
            for right_id in unique_ids[left_index + 1 :]:
                candidates.add((left_id, right_id))

    pairs: list[NearDuplicatePair] = []
    for left_id, right_id in sorted(candidates):
        if exact_fingerprints[left_id] == exact_fingerprints[right_id]:
            continue
        similarity = float(abs(np.vdot(vectors[left_id], vectors[right_id])))
        similarity = min(1.0, round(similarity, 12))
        if similarity >= threshold:
            pairs.append(NearDuplicatePair((left_id, right_id), similarity))
    return tuple(pairs)


def _split_issues(
    candidates: Sequence[LeakageCandidate],
    groups: Mapping[str, str | None],
    exact_clusters: Sequence[ExactDuplicateCluster],
    near_pairs: Sequence[NearDuplicatePair],
    assignments: Mapping[str, str],
    allowed_splits: frozenset[str],
) -> list[LeakageIssue]:
    issues: list[LeakageIssue] = []
    candidate_ids = {candidate.sample_id for candidate in candidates}
    unexpected = sorted(set(assignments).difference(candidate_ids))
    if unexpected:
        raise LeakageAnalysisError(
            "split assignment bilinmeyen sample_id içeriyor: " + ", ".join(unexpected)
        )

    valid_assignments: dict[str, str] = {}
    for sample_id in sorted(candidate_ids):
        split = assignments.get(sample_id)
        if split is None:
            issues.append(
                LeakageIssue(
                    error_code="split.assignment_missing",
                    sample_ids=(sample_id,),
                    message="örnek için split ataması bulunamadı",
                )
            )
        elif split not in allowed_splits:
            issues.append(
                LeakageIssue(
                    error_code="split.assignment_invalid",
                    sample_ids=(sample_id,),
                    message="örnek izin verilmeyen split adına atanmış",
                    splits=(split,),
                )
            )
        else:
            valid_assignments[sample_id] = split

    group_members: dict[str, list[str]] = defaultdict(list)
    for sample_id, group_id in groups.items():
        if group_id is not None and sample_id in valid_assignments:
            group_members[group_id].append(sample_id)
    for group_id, sample_ids in sorted(group_members.items()):
        splits = tuple(sorted({valid_assignments[sample_id] for sample_id in sample_ids}))
        if len(splits) > 1:
            issues.append(
                LeakageIssue(
                    error_code="leakage.group_cross_split",
                    sample_ids=tuple(sorted(sample_ids)),
                    group_id=group_id,
                    splits=splits,
                    message="aynı kaynak grubu birden fazla split'e dağılmış",
                )
            )

    for cluster in exact_clusters:
        splits = _pair_splits(cluster.sample_ids, valid_assignments)
        if len(splits) > 1:
            issues.append(
                LeakageIssue(
                    error_code="leakage.exact_cross_split",
                    sample_ids=cluster.sample_ids,
                    splits=splits,
                    message="exact duplicate örnekler farklı split'lerde bulunuyor",
                )
            )
    for pair in near_pairs:
        splits = _pair_splits(pair.sample_ids, valid_assignments)
        if len(splits) > 1:
            issues.append(
                LeakageIssue(
                    error_code="leakage.near_cross_split",
                    sample_ids=pair.sample_ids,
                    splits=splits,
                    similarity=pair.similarity,
                    message="near duplicate örnekler farklı split'lerde bulunuyor",
                )
            )
    return issues


def _exact_fingerprint(signal: np.ndarray[Any, Any], representation: IQRepresentation) -> str:
    contiguous = np.ascontiguousarray(signal)
    header = json.dumps(
        {
            "representation": representation.value,
            "shape": list(contiguous.shape),
            "dtype": contiguous.dtype.str,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(b"\0")
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _normalized_complex_vector(
    signal: np.ndarray[Any, Any], policy: DuplicatePolicy
) -> np.ndarray[Any, Any]:
    if policy.representation is IQRepresentation.CHANNELS_FIRST:
        vector = signal[0].astype(np.float64) + 1j * signal[1].astype(np.float64)
    else:
        vector = signal.astype(np.complex128)
    if policy.remove_dc:
        vector = vector - np.mean(vector)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise LeakageAnalysisError("duplicate analizi sonlu ve sıfırdan farklı güçlü sinyal bekler")
    vector = vector / norm
    anchor = vector[int(np.argmax(np.abs(vector)))]
    if anchor != 0:
        vector = vector * np.exp(-1j * np.angle(anchor))
    return vector


def _near_signatures(vector: np.ndarray[Any, Any], decimals: int) -> tuple[str, ...]:
    values = np.concatenate((vector.real, vector.imag))
    scale = float(10**decimals)
    signatures: list[str] = []
    for offset in (-0.5, 0.0, 0.5):
        quantized = np.floor(values * scale + offset).astype("<i8", copy=False)
        signatures.append(hashlib.sha256(quantized.tobytes(order="C")).hexdigest())
    return tuple(signatures)


def _require_candidate(candidate: LeakageCandidate, representation: IQRepresentation) -> None:
    if not isinstance(candidate.sample_id, str) or not candidate.sample_id.strip():
        raise LeakageAnalysisError("sample_id boş olmayan string olmalıdır")
    if not isinstance(candidate.signal, np.ndarray):
        raise LeakageAnalysisError(f"{candidate.sample_id}: signal NumPy ndarray olmalıdır")
    expected_dtype = np.dtype(
        np.float32 if representation is IQRepresentation.CHANNELS_FIRST else np.complex64
    )
    shape_valid = (
        candidate.signal.ndim == 2 and candidate.signal.shape[0] == 2
        if representation is IQRepresentation.CHANNELS_FIRST
        else candidate.signal.ndim == 1
    )
    if not shape_valid or candidate.signal.size == 0 or candidate.signal.dtype != expected_dtype:
        raise LeakageAnalysisError(
            f"{candidate.sample_id}: 020 validation geçmemiş signal duplicate analizine giremez"
        )
    if not np.all(np.isfinite(candidate.signal)):
        raise LeakageAnalysisError(
            f"{candidate.sample_id}: sonlu olmayan signal duplicate analizine giremez"
        )


def _require_unique_sample_ids(candidates: Sequence[LeakageCandidate]) -> None:
    sample_ids = [candidate.sample_id for candidate in candidates]
    if len(sample_ids) != len(set(sample_ids)):
        raise LeakageAnalysisError("duplicate analizi benzersiz sample_id değerleri gerektirir")


def _require_adapter_identity(adapter: GroupIdAdapter) -> None:
    if not isinstance(adapter.rule_name, str) or not adapter.rule_name.strip():
        raise LeakageAnalysisError("group adapter rule_name sağlamalıdır")
    if not isinstance(adapter.rule_version, str) or not adapter.rule_version.strip():
        raise LeakageAnalysisError("group adapter rule_version sağlamalıdır")


def _pair_splits(sample_ids: Sequence[str], assignments: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        sorted({assignments[sample_id] for sample_id in sample_ids if sample_id in assignments})
    )


def _issue_sort_key(issue: LeakageIssue) -> tuple[Any, ...]:
    return (
        issue.error_code,
        issue.sample_ids,
        issue.group_id or "",
        issue.splits,
        issue.similarity if issue.similarity is not None else -1.0,
    )


def _optional_non_empty(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
