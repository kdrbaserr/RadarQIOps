"""Deterministic stratified group-aware train/validation/test splitting."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from radariq.configs import load_config

SPLIT_SCHEMA_VERSION = "1.0"
SPLIT_NAMES = ("train", "validation", "test")
SPLIT_STRATEGY = "greedy-joint-label-snr-group-v1"


class SplitError(ValueError):
    """Raised when a leakage-safe deterministic split cannot be produced."""


class SplitArtifactStatus(StrEnum):
    CREATED = "created"
    REUSED = "reused"


@dataclass(frozen=True, slots=True)
class SplitPolicy:
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    seed: int
    snr_bin_edges: tuple[float, ...] = ()
    group_rule_name: str = "explicit-group-id"
    group_rule_version: str = "1.0"

    def __post_init__(self) -> None:
        fractions = (self.train_fraction, self.validation_fraction, self.test_fraction)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in fractions
        ):
            raise SplitError("split oranları pozitif ve sonlu number olmalıdır")
        if not math.isclose(sum(fractions), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise SplitError("train, validation ve test oranları toplamı 1 olmalıdır")
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or not 0 <= self.seed < 2**63
        ):
            raise SplitError("seed 0 ile 2^63 arasında integer olmalıdır")
        if any(not math.isfinite(edge) for edge in self.snr_bin_edges):
            raise SplitError("snr_bin_edges yalnız sonlu değerler içermelidir")
        if tuple(sorted(set(self.snr_bin_edges))) != self.snr_bin_edges:
            raise SplitError("snr_bin_edges benzersiz ve artan sırada olmalıdır")
        for field in ("group_rule_name", "group_rule_version"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise SplitError(f"{field} boş olmayan string olmalıdır")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SplitPolicy:
        fractions = value.get("fractions")
        if not isinstance(fractions, Mapping):
            raise SplitError("fractions config nesnesi zorunludur")
        raw_edges = value.get("snr_bin_edges", [])
        if not isinstance(raw_edges, Sequence) or isinstance(raw_edges, (str, bytes)):
            raise SplitError("snr_bin_edges liste olmalıdır")
        try:
            edges = tuple(float(edge) for edge in raw_edges)
        except (TypeError, ValueError) as exc:
            raise SplitError("snr_bin_edges sayısal değerler içermelidir") from exc
        return cls(
            train_fraction=_required_float(fractions, "train"),
            validation_fraction=_required_float(fractions, "validation"),
            test_fraction=_required_float(fractions, "test"),
            seed=_required_int(value, "seed"),
            snr_bin_edges=edges,
            group_rule_name=_optional_string(value, "group_rule_name", "explicit-group-id"),
            group_rule_version=_optional_string(value, "group_rule_version", "1.0"),
        )

    @property
    def fractions(self) -> dict[str, float]:
        return {
            "train": float(self.train_fraction),
            "validation": float(self.validation_fraction),
            "test": float(self.test_fraction),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "fractions": self.fractions,
            "seed": self.seed,
            "snr_bin_edges": list(self.snr_bin_edges),
            "group_rule_name": self.group_rule_name,
            "group_rule_version": self.group_rule_version,
        }


@dataclass(frozen=True, slots=True)
class SplitInput:
    sample_ids: tuple[str, ...]
    labels: tuple[str | int, ...]
    snr_db: tuple[float | None, ...]
    group_ids: tuple[str, ...]
    source_revision: str
    input_sha256: str

    def __post_init__(self) -> None:
        count = len(self.sample_ids)
        if count == 0:
            raise SplitError("split input en az bir örnek içermelidir")
        if len(self.labels) != count or len(self.snr_db) != count or len(self.group_ids) != count:
            raise SplitError("sample_ids, labels, snr_db ve group_ids sayıları eşit olmalıdır")
        if any(not isinstance(value, str) or not value.strip() for value in self.sample_ids):
            raise SplitError("sample_ids boş olmayan string değerler olmalıdır")
        if len(set(self.sample_ids)) != count:
            raise SplitError("sample_ids benzersiz olmalıdır")
        if any(not _valid_label(value) for value in self.labels):
            raise SplitError("labels boş olmayan string veya integer olmalıdır")
        if any(value is not None and not math.isfinite(value) for value in self.snr_db):
            raise SplitError("snr_db sonlu number veya null olmalıdır")
        if any(not isinstance(value, str) or not value.strip() for value in self.group_ids):
            raise SplitError("group_ids çözümlenmiş boş olmayan string değerler olmalıdır")
        if not isinstance(self.source_revision, str) or not self.source_revision.strip():
            raise SplitError("source_revision boş olmayan string olmalıdır")
        _require_sha256(self.input_sha256, "input_sha256")

    @property
    def sample_count(self) -> int:
        return len(self.sample_ids)


@dataclass(frozen=True, slots=True)
class SplitPlan:
    policy: SplitPolicy
    split_input: SplitInput
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        split_indices = self.indices_by_split
        if any(not indices for indices in split_indices.values()):
            raise SplitError("train, validation ve test split'leri boş olamaz")
        flattened = [index for indices in split_indices.values() for index in indices]
        if len(flattened) != len(set(flattened)):
            raise SplitError("split indeksleri kesişemez")
        if sorted(flattened) != list(range(self.split_input.sample_count)):
            raise SplitError("her örnek tam olarak bir split'e atanmalıdır")
        for indices in split_indices.values():
            if tuple(sorted(indices)) != indices:
                raise SplitError("split indeksleri artan sırada olmalıdır")
        group_splits: dict[str, set[str]] = defaultdict(set)
        for split_name, indices in split_indices.items():
            for index in indices:
                group_splits[self.split_input.group_ids[index]].add(split_name)
        if any(len(splits) != 1 for splits in group_splits.values()):
            raise SplitError("aynı group_id birden fazla split'e atanamaz")

    @property
    def indices_by_split(self) -> dict[str, tuple[int, ...]]:
        return {
            "train": self.train_indices,
            "validation": self.validation_indices,
            "test": self.test_indices,
        }

    def manifest(self, index_sha256: Mapping[str, str]) -> dict[str, Any]:
        for split_name in SPLIT_NAMES:
            _require_sha256(index_sha256.get(split_name), f"{split_name}_indices_sha256")
        global_class = _distribution(self.split_input.labels, "label")
        global_snr_values = tuple(
            _snr_bucket(value, self.policy.snr_bin_edges) for value in self.split_input.snr_db
        )
        global_snr = _distribution(global_snr_values, "snr_bucket")
        split_details: dict[str, Any] = {}
        class_deviations: list[float] = []
        snr_deviations: list[float] = []
        for split_name, indices in self.indices_by_split.items():
            labels = tuple(self.split_input.labels[index] for index in indices)
            snr_buckets = tuple(global_snr_values[index] for index in indices)
            class_distribution = _distribution(labels, "label")
            snr_distribution = _distribution(snr_buckets, "snr_bucket")
            class_deviations.append(
                _maximum_distribution_deviation(global_class, class_distribution, "label")
            )
            snr_deviations.append(
                _maximum_distribution_deviation(global_snr, snr_distribution, "snr_bucket")
            )
            split_details[split_name] = {
                "target_fraction": self.policy.fractions[split_name],
                "actual_fraction": len(indices) / self.split_input.sample_count,
                "sample_count": len(indices),
                "group_count": len({self.split_input.group_ids[index] for index in indices}),
                "indices_sha256": index_sha256[split_name],
                "class_distribution": class_distribution,
                "snr_distribution": snr_distribution,
                "joint_distribution": _joint_distribution(labels, snr_buckets),
            }
        return {
            "schema_version": SPLIT_SCHEMA_VERSION,
            "strategy": SPLIT_STRATEGY,
            "source_revision": self.split_input.source_revision,
            "input_sha256": self.split_input.input_sha256,
            "seed": self.policy.seed,
            "group_rule": {
                "name": self.policy.group_rule_name,
                "version": self.policy.group_rule_version,
            },
            "sample_count": self.split_input.sample_count,
            "group_count": len(set(self.split_input.group_ids)),
            "policy": self.policy.as_dict(),
            "global_distribution": {
                "class": global_class,
                "snr": global_snr,
            },
            "balance": {
                "maximum_class_fraction_deviation": max(class_deviations),
                "maximum_snr_fraction_deviation": max(snr_deviations),
            },
            "test_locked": True,
            "splits": split_details,
        }


@dataclass(frozen=True, slots=True)
class DevelopmentSplits:
    """Model-development view intentionally containing no test indices."""

    train_indices: np.ndarray[Any, Any]
    validation_indices: np.ndarray[Any, Any]
    split_plan_sha256: str
    test_lock_sha256: str


@dataclass(frozen=True, slots=True)
class SplitArtifactResult:
    status: SplitArtifactStatus
    output_directory: Path
    split_plan_sha256: str
    test_lock_sha256: str
    file_sha256: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "output_directory": str(self.output_directory),
            "split_plan_sha256": self.split_plan_sha256,
            "test_lock_sha256": self.test_lock_sha256,
            "file_sha256": dict(sorted(self.file_sha256.items())),
        }


def create_group_aware_splits(split_input: SplitInput, policy: SplitPolicy) -> SplitPlan:
    """Assign indivisible groups while minimizing size and joint label/SNR imbalance."""

    group_indices: dict[str, list[int]] = defaultdict(list)
    strata: list[str] = []
    for index, group_id in enumerate(split_input.group_ids):
        group_indices[group_id].append(index)
        strata.append(
            _stratum_key(split_input.labels[index], split_input.snr_db[index], policy.snr_bin_edges)
        )
    if len(group_indices) < len(SPLIT_NAMES):
        raise SplitError("üç split için en az üç bağımsız group_id gerekir")

    group_strata = {
        group_id: Counter(strata[index] for index in indices)
        for group_id, indices in group_indices.items()
    }
    total_strata = Counter(strata)
    target_sizes = {
        split_name: split_input.sample_count * policy.fractions[split_name]
        for split_name in SPLIT_NAMES
    }
    target_strata = {
        split_name: {
            stratum: count * policy.fractions[split_name] for stratum, count in total_strata.items()
        }
        for split_name in SPLIT_NAMES
    }
    assigned_groups: dict[str, list[str]] = {name: [] for name in SPLIT_NAMES}
    current_sizes = dict.fromkeys(SPLIT_NAMES, 0)
    current_strata: dict[str, Counter[str]] = {name: Counter() for name in SPLIT_NAMES}
    ordered_groups = sorted(
        group_indices,
        key=lambda group_id: (
            -len(group_indices[group_id]),
            -max(group_strata[group_id].values()),
            _seeded_key(policy.seed, group_id),
        ),
    )

    for position, group_id in enumerate(ordered_groups):
        remaining_count = len(ordered_groups) - position
        empty_splits = [name for name in SPLIT_NAMES if not assigned_groups[name]]
        candidates = empty_splits if remaining_count == len(empty_splits) else list(SPLIT_NAMES)
        scored = [
            (
                _assignment_score(
                    candidate,
                    group_id,
                    group_indices,
                    group_strata,
                    current_sizes,
                    current_strata,
                    target_sizes,
                    target_strata,
                ),
                _seeded_key(policy.seed, f"{group_id}\0{candidate}"),
                candidate,
            )
            for candidate in candidates
        ]
        selected = min(scored)[2]
        assigned_groups[selected].append(group_id)
        current_sizes[selected] += len(group_indices[group_id])
        current_strata[selected].update(group_strata[group_id])

    indices_by_split = {
        split_name: tuple(
            sorted(
                index
                for group_id in assigned_groups[split_name]
                for index in group_indices[group_id]
            )
        )
        for split_name in SPLIT_NAMES
    }
    return SplitPlan(
        policy=policy,
        split_input=split_input,
        train_indices=indices_by_split["train"],
        validation_indices=indices_by_split["validation"],
        test_indices=indices_by_split["test"],
    )


def split_from_config(config_path: str | Path) -> SplitArtifactResult:
    path = Path(config_path)
    value = load_config(path)
    input_path = _required_path(value, "input_path", path.parent)
    output_directory = _required_path(value, "output_dir", path.parent)
    source_revision = _required_string(value, "source_revision")
    policy_value = value.get("split")
    if not isinstance(policy_value, Mapping):
        raise SplitError("split config nesnesi zorunludur")
    policy = SplitPolicy.from_mapping(policy_value)
    split_input = _load_split_input(input_path, source_revision)
    plan = create_group_aware_splits(split_input, policy)
    payloads, split_plan_sha256, test_lock_sha256 = _artifact_payloads(plan)
    return _write_artifacts(output_directory, payloads, split_plan_sha256, test_lock_sha256)


def load_development_splits(output_directory: str | Path) -> DevelopmentSplits:
    """Load only train and validation indices for model development."""

    directory = Path(output_directory)
    manifest_path = directory / "development_splits.json"
    manifest = _load_json_object(manifest_path)
    if manifest.get("schema_version") != SPLIT_SCHEMA_VERSION:
        raise SplitError("development split schema_version desteklenmiyor")
    splits = manifest.get("splits")
    if not isinstance(splits, Mapping) or set(splits) != {"train", "validation"}:
        raise SplitError("development manifest yalnız train ve validation içermelidir")
    train = _load_index_reference(directory, splits, "train")
    validation = _load_index_reference(directory, splits, "validation")
    split_plan_sha256 = _required_sha256(manifest, "split_plan_sha256")
    test_lock_sha256 = _required_sha256(manifest, "test_lock_sha256")
    return DevelopmentSplits(train, validation, split_plan_sha256, test_lock_sha256)


def load_locked_test_indices(
    output_directory: str | Path, expected_lock_sha256: str
) -> np.ndarray[Any, Any]:
    """Evaluation-only loader requiring an approved test-lock identity."""

    _require_sha256(expected_lock_sha256, "expected_lock_sha256")
    directory = Path(output_directory)
    lock_path = directory / "test_lock.json"
    lock_payload = lock_path.read_bytes()
    if hashlib.sha256(lock_payload).hexdigest() != expected_lock_sha256:
        raise SplitError("test lock SHA-256 beklenen kimlikle eşleşmiyor")
    lock = _load_json_bytes(lock_payload, lock_path)
    reference = lock.get("test_indices")
    if not isinstance(reference, Mapping):
        raise SplitError("test lock test_indices referansı içermelidir")
    return _load_single_index_reference(directory, reference)


def _assignment_score(
    candidate: str,
    group_id: str,
    group_indices: Mapping[str, list[int]],
    group_strata: Mapping[str, Counter[str]],
    current_sizes: Mapping[str, int],
    current_strata: Mapping[str, Counter[str]],
    target_sizes: Mapping[str, float],
    target_strata: Mapping[str, Mapping[str, float]],
) -> float:
    size_loss = 0.0
    strata_loss = 0.0
    for split_name in SPLIT_NAMES:
        added_size = len(group_indices[group_id]) if split_name == candidate else 0
        size_value = current_sizes[split_name] + added_size
        size_loss += ((size_value - target_sizes[split_name]) / target_sizes[split_name]) ** 2
        for stratum, target in target_strata[split_name].items():
            added = group_strata[group_id][stratum] if split_name == candidate else 0
            actual = current_strata[split_name][stratum] + added
            strata_loss += ((actual - target) / max(target, 1.0)) ** 2
    return size_loss + 2.0 * strata_loss


def _artifact_payloads(plan: SplitPlan) -> tuple[dict[str, bytes], str, str]:
    index_payloads = {
        split_name: _npy_bytes(np.asarray(indices, dtype=np.int64))
        for split_name, indices in plan.indices_by_split.items()
    }
    index_sha256 = {
        split_name: hashlib.sha256(payload).hexdigest()
        for split_name, payload in index_payloads.items()
    }
    split_manifest = plan.manifest(index_sha256)
    split_plan_sha256 = _canonical_sha256(split_manifest)
    test_lock = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "split_plan_sha256": split_plan_sha256,
        "source_revision": plan.split_input.source_revision,
        "input_sha256": plan.split_input.input_sha256,
        "seed": plan.policy.seed,
        "test_indices": {
            "path": "test_indices.npy",
            "sha256": index_sha256["test"],
            "count": len(plan.test_indices),
        },
    }
    test_lock_payload = _json_bytes(test_lock)
    test_lock_sha256 = hashlib.sha256(test_lock_payload).hexdigest()
    development_manifest = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "split_plan_sha256": split_plan_sha256,
        "source_revision": plan.split_input.source_revision,
        "input_sha256": plan.split_input.input_sha256,
        "seed": plan.policy.seed,
        "splits": {
            "train": {
                "path": "train_indices.npy",
                "sha256": index_sha256["train"],
                "count": len(plan.train_indices),
            },
            "validation": {
                "path": "validation_indices.npy",
                "sha256": index_sha256["validation"],
                "count": len(plan.validation_indices),
            },
        },
        "test_lock_sha256": test_lock_sha256,
    }
    payloads = {
        "train_indices.npy": index_payloads["train"],
        "validation_indices.npy": index_payloads["validation"],
        "test_indices.npy": index_payloads["test"],
        "split_manifest.json": _json_bytes(split_manifest),
        "development_splits.json": _json_bytes(development_manifest),
        "test_lock.json": test_lock_payload,
    }
    return payloads, split_plan_sha256, test_lock_sha256


def _write_artifacts(
    destination: Path,
    payloads: Mapping[str, bytes],
    split_plan_sha256: str,
    test_lock_sha256: str,
) -> SplitArtifactResult:
    destination = destination.expanduser().resolve()
    if destination.exists():
        _verify_existing(destination, payloads)
        return _artifact_result(
            SplitArtifactStatus.REUSED,
            destination,
            payloads,
            split_plan_sha256,
            test_lock_sha256,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".part")
    )
    try:
        for name, payload in payloads.items():
            _write_fsync(temporary / name, payload)
        try:
            temporary.rename(destination)
        except FileExistsError:
            _verify_existing(destination, payloads)
            return _artifact_result(
                SplitArtifactStatus.REUSED,
                destination,
                payloads,
                split_plan_sha256,
                test_lock_sha256,
            )
        return _artifact_result(
            SplitArtifactStatus.CREATED,
            destination,
            payloads,
            split_plan_sha256,
            test_lock_sha256,
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _verify_existing(destination: Path, payloads: Mapping[str, bytes]) -> None:
    if not destination.is_dir():
        raise SplitError("split artifact hedefi dizin olmalıdır")
    entries = list(destination.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise SplitError("split artifact dizini yalnız normal dosya içerebilir")
    if {path.name for path in entries} != set(payloads):
        raise SplitError("mevcut split artifact dosya kümesi farklı")
    if any((destination / name).read_bytes() != payload for name, payload in payloads.items()):
        raise SplitError("split artifact farklı içerikle yerinde değiştirilemez")


def _artifact_result(
    status: SplitArtifactStatus,
    destination: Path,
    payloads: Mapping[str, bytes],
    split_plan_sha256: str,
    test_lock_sha256: str,
) -> SplitArtifactResult:
    return SplitArtifactResult(
        status=status,
        output_directory=destination,
        split_plan_sha256=split_plan_sha256,
        test_lock_sha256=test_lock_sha256,
        file_sha256={
            name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()
        },
    )


def _load_split_input(path: Path, source_revision: str) -> SplitInput:
    if not path.is_file():
        raise SplitError(f"split input bulunamadı: {path}")
    required = {"sample_ids", "labels", "snr_db", "group_ids"}
    try:
        with np.load(path, allow_pickle=False) as payload:
            missing = sorted(required.difference(payload.files))
            if missing:
                raise SplitError("split NPZ alanları eksik: " + ", ".join(missing))
            raw_sample_ids = _require_one_dimensional(payload["sample_ids"], "sample_ids")
            raw_labels_array = _require_one_dimensional(payload["labels"], "labels")
            raw_snr = _require_one_dimensional(payload["snr_db"], "snr_db").astype(np.float64)
            raw_group_ids = _require_one_dimensional(payload["group_ids"], "group_ids")
            sample_ids = tuple(_json_scalar(value) for value in raw_sample_ids.tolist())
            raw_labels = raw_labels_array.tolist()
            labels = tuple(_json_scalar(value) for value in raw_labels)
            if np.any(np.isinf(raw_snr)):
                raise SplitError("snr_db Inf içeremez; yalnız sonlu değer veya NaN kullanılabilir")
            snr_db = tuple(float(value) if not np.isnan(value) else None for value in raw_snr)
            group_ids = tuple(_json_scalar(value) for value in raw_group_ids.tolist())
    except SplitError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise SplitError(f"split NPZ okunamadı: {path}: {exc}") from exc
    return SplitInput(
        sample_ids=sample_ids,
        labels=labels,
        snr_db=snr_db,
        group_ids=group_ids,
        source_revision=source_revision,
        input_sha256=_file_sha256(path),
    )


def _require_one_dimensional(value: Any, field: str) -> np.ndarray[Any, Any]:
    array = np.asarray(value)
    if array.ndim != 1:
        raise SplitError(f"{field} tek boyutlu array olmalıdır")
    return array


def _load_index_reference(
    directory: Path, references: Mapping[str, Any], split_name: str
) -> np.ndarray[Any, Any]:
    reference = references.get(split_name)
    if not isinstance(reference, Mapping):
        raise SplitError(f"development manifest {split_name} referansı eksik")
    return _load_single_index_reference(directory, reference)


def _load_single_index_reference(
    directory: Path, reference: Mapping[str, Any]
) -> np.ndarray[Any, Any]:
    raw_path = reference.get("path")
    if not isinstance(raw_path, str) or Path(raw_path).name != raw_path:
        raise SplitError("split index path yalnız güvenli dosya adı olmalıdır")
    expected_sha256 = _required_sha256(reference, "sha256")
    path = directory / raw_path
    if _file_sha256(path) != expected_sha256:
        raise SplitError(f"split index SHA-256 eşleşmiyor: {raw_path}")
    try:
        indices = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise SplitError(f"split index okunamadı: {raw_path}: {exc}") from exc
    if not isinstance(indices, np.ndarray) or indices.ndim != 1 or indices.dtype != np.int64:
        raise SplitError("split index tek boyutlu int64 NumPy array olmalıdır")
    count = reference.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count != indices.size:
        raise SplitError("split index count manifest ile eşleşmiyor")
    return indices


def _distribution(values: Sequence[Any], key_name: str) -> list[dict[str, Any]]:
    identities = [(_value_identity(value), value) for value in values]
    counts = Counter(identity for identity, _ in identities)
    representatives = {identity: value for identity, value in identities}
    total = len(values)
    return [
        {
            key_name: representatives[identity],
            "count": counts[identity],
            "fraction": counts[identity] / total,
        }
        for identity in sorted(counts)
    ]


def _joint_distribution(
    labels: Sequence[str | int], snr_buckets: Sequence[str]
) -> list[dict[str, Any]]:
    values = [
        (_value_identity(label), bucket) for label, bucket in zip(labels, snr_buckets, strict=True)
    ]
    counts = Counter(values)
    representatives = {_value_identity(label): label for label in labels}
    return [
        {
            "label": representatives[label_identity],
            "snr_bucket": bucket,
            "count": counts[(label_identity, bucket)],
            "fraction": counts[(label_identity, bucket)] / len(labels),
        }
        for label_identity, bucket in sorted(counts)
    ]


def _maximum_distribution_deviation(
    global_distribution: Sequence[Mapping[str, Any]],
    split_distribution: Sequence[Mapping[str, Any]],
    key_name: str,
) -> float:
    global_fractions = {
        _value_identity(item[key_name]): float(item["fraction"]) for item in global_distribution
    }
    split_fractions = {
        _value_identity(item[key_name]): float(item["fraction"]) for item in split_distribution
    }
    return max(
        abs(split_fractions.get(identity, 0.0) - fraction)
        for identity, fraction in global_fractions.items()
    )


def _stratum_key(label: str | int, snr: float | None, edges: tuple[float, ...]) -> str:
    return json.dumps(
        {"label": label, "snr_bucket": _snr_bucket(snr, edges)},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _snr_bucket(value: float | None, edges: tuple[float, ...]) -> str:
    if value is None:
        return "unknown"
    lower = "-inf"
    for index, edge in enumerate(edges):
        if value < edge:
            return f"bin-{index:02d}:[{lower},{edge:g})"
        lower = f"{edge:g}"
    return f"bin-{len(edges):02d}:[{lower},+inf)"


def _seeded_key(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode()).hexdigest()


def _value_identity(value: Any) -> str:
    return json.dumps(
        {"type": type(value).__name__, "value": value},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _valid_label(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, str) and bool(value.strip())
    )


def _json_scalar(value: Any) -> Any:
    return value.item() if isinstance(value, np.generic) else value


def _required_path(value: Mapping[str, Any], field: str, base_dir: Path) -> Path:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise SplitError(f"{field} boş olmayan path string olmalıdır")
    path = Path(raw)
    return path if path.is_absolute() else base_dir / path


def _required_string(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise SplitError(f"{field} boş olmayan string olmalıdır")
    return raw.strip()


def _optional_string(value: Mapping[str, Any], field: str, default: str) -> str:
    raw = value.get(field, default)
    if not isinstance(raw, str) or not raw.strip():
        raise SplitError(f"{field} boş olmayan string olmalıdır")
    return raw.strip()


def _required_float(value: Mapping[str, Any], field: str) -> float:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise SplitError(f"{field} sonlu number olmalıdır")
    return float(raw)


def _required_int(value: Mapping[str, Any], field: str) -> int:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SplitError(f"{field} integer olmalıdır")
    return raw


def _required_sha256(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    _require_sha256(raw, field)
    assert isinstance(raw, str)
    return raw


def _require_sha256(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SplitError(f"{field} geçerli küçük harf SHA-256 olmalıdır")


def _npy_bytes(array: np.ndarray[Any, Any]) -> bytes:
    output = io.BytesIO()
    np.lib.format.write_array(output, array, allow_pickle=False)
    return output.getvalue()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _json_bytes(value: Any) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return (payload + "\n").encode()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        return _load_json_bytes(path.read_bytes(), path)
    except OSError as exc:
        raise SplitError(f"JSON artifact okunamadı: {path}: {exc}") from exc


def _load_json_bytes(payload: bytes, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SplitError(f"JSON artifact geçersiz: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SplitError(f"JSON artifact nesne olmalıdır: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SplitError(f"dosya okunamadı: {path}: {exc}") from exc
    return digest.hexdigest()


def _write_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
