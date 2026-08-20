from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radariq.cli import main
from radariq.data.splitting import (
    SplitArtifactStatus,
    SplitError,
    SplitInput,
    SplitPolicy,
    create_group_aware_splits,
    load_development_splits,
    load_locked_test_indices,
    split_from_config,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _split_input(group_count: int = 24) -> SplitInput:
    sample_ids: list[str] = []
    labels: list[str] = []
    snr_db: list[float | None] = []
    group_ids: list[str] = []
    snr_cycle = (-15.0, -5.0, 5.0, 15.0)
    for group_index in range(group_count):
        for sample_index in range(2):
            sample_ids.append(f"sample-{group_index:02d}-{sample_index}")
            labels.append("BPSK" if group_index % 2 == 0 else "QPSK")
            snr_db.append(snr_cycle[group_index % len(snr_cycle)])
            group_ids.append(f"group-{group_index:02d}")
    return SplitInput(
        sample_ids=tuple(sample_ids),
        labels=tuple(labels),
        snr_db=tuple(snr_db),
        group_ids=tuple(group_ids),
        source_revision="dvc:fixture-v1",
        input_sha256="a" * 64,
    )


def _policy(seed: int = 20260811) -> SplitPolicy:
    return SplitPolicy(
        train_fraction=0.5,
        validation_fraction=0.25,
        test_fraction=0.25,
        seed=seed,
        snr_bin_edges=(-10.0, 0.0, 10.0),
    )


def _write_cli_fixture(tmp_path: Path, *, seed: int = 20260811) -> Path:
    split_input = _split_input()
    np.savez(
        tmp_path / "metadata.npz",
        sample_ids=np.asarray(split_input.sample_ids),
        labels=np.asarray(split_input.labels),
        snr_db=np.asarray(split_input.snr_db, dtype=np.float64),
        group_ids=np.asarray(split_input.group_ids),
    )
    config_path = tmp_path / "split.json"
    config_path.write_text(
        json.dumps(
            {
                "input_path": "metadata.npz",
                "output_dir": "splits/v1",
                "source_revision": "dvc:fixture-v1",
                "split": {
                    "fractions": {"train": 0.5, "validation": 0.25, "test": 0.25},
                    "seed": seed,
                    "snr_bin_edges": [-10.0, 0.0, 10.0],
                    "group_rule_name": "explicit-group-id",
                    "group_rule_version": "1.0",
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_groups_are_disjoint_and_every_sample_is_assigned_once() -> None:
    split_input = _split_input()
    plan = create_group_aware_splits(split_input, _policy())

    index_sets = {name: set(indices) for name, indices in plan.indices_by_split.items()}
    assert index_sets["train"].isdisjoint(index_sets["validation"])
    assert index_sets["train"].isdisjoint(index_sets["test"])
    assert index_sets["validation"].isdisjoint(index_sets["test"])
    assert set.union(*index_sets.values()) == set(range(split_input.sample_count))
    group_splits: dict[str, set[str]] = {}
    for split_name, indices in plan.indices_by_split.items():
        for index in indices:
            group_splits.setdefault(split_input.group_ids[index], set()).add(split_name)
    assert all(len(splits) == 1 for splits in group_splits.values())


def test_same_seed_produces_identical_indices() -> None:
    split_input = _split_input()

    first = create_group_aware_splits(split_input, _policy())
    second = create_group_aware_splits(split_input, _policy())

    assert first.indices_by_split == second.indices_by_split


def test_different_seed_can_change_a_valid_assignment() -> None:
    split_input = _split_input()

    first = create_group_aware_splits(split_input, _policy(seed=11))
    second = create_group_aware_splits(split_input, _policy(seed=12))

    assert first.indices_by_split != second.indices_by_split


def test_manifest_records_balanced_class_and_snr_distributions() -> None:
    plan = create_group_aware_splits(_split_input(), _policy())
    hashes = {
        name: character * 64 for name, character in zip(plan.indices_by_split, "bcd", strict=True)
    }

    manifest = plan.manifest(hashes)

    assert manifest["test_locked"] is True
    assert manifest["balance"]["maximum_class_fraction_deviation"] <= 0.17
    assert manifest["balance"]["maximum_snr_fraction_deviation"] <= 0.17
    for split_name in ("train", "validation", "test"):
        detail = manifest["splits"][split_name]
        assert detail["class_distribution"]
        assert detail["snr_distribution"]
        assert detail["joint_distribution"]


def test_cli_outputs_are_deterministic_and_reused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_cli_fixture(tmp_path)

    assert main(["data", "split", "--config", str(config_path)]) == 0
    first = json.loads(capsys.readouterr().out)
    second = split_from_config(config_path)

    assert first["status"] == "created"
    assert second.status is SplitArtifactStatus.REUSED
    assert first["file_sha256"] == second.file_sha256
    for name in ("train", "validation", "test"):
        indices = np.load(tmp_path / "splits" / "v1" / f"{name}_indices.npy")
        assert indices.dtype == np.int64
        assert np.all(indices[1:] > indices[:-1])


def test_development_loader_exposes_no_test_indices_or_path(tmp_path: Path) -> None:
    config_path = _write_cli_fixture(tmp_path)
    result = split_from_config(config_path)

    development = load_development_splits(result.output_directory)
    manifest_text = (result.output_directory / "development_splits.json").read_text(
        encoding="utf-8"
    )

    assert development.train_indices.size > 0
    assert development.validation_indices.size > 0
    assert not hasattr(development, "test_indices")
    assert "test_indices.npy" not in manifest_text


def test_locked_test_loader_requires_expected_lock_and_detects_tampering(tmp_path: Path) -> None:
    result = split_from_config(_write_cli_fixture(tmp_path))

    indices = load_locked_test_indices(result.output_directory, result.test_lock_sha256)
    assert indices.size > 0
    with pytest.raises(SplitError, match="test lock SHA-256"):
        load_locked_test_indices(result.output_directory, "0" * 64)

    (result.output_directory / "test_indices.npy").write_bytes(b"tampered")
    with pytest.raises(SplitError, match="split index SHA-256"):
        load_locked_test_indices(result.output_directory, result.test_lock_sha256)


def test_existing_output_cannot_be_replaced_by_another_seed(tmp_path: Path) -> None:
    config_path = _write_cli_fixture(tmp_path, seed=10)
    split_from_config(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["split"]["seed"] = 20
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(SplitError, match="yerinde değiştirilemez"):
        split_from_config(config_path)


def test_missing_group_id_fails_without_inventing_a_group() -> None:
    split_input = _split_input()
    groups = list(split_input.group_ids)
    groups[0] = ""

    with pytest.raises(SplitError, match="group_ids çözümlenmiş"):
        SplitInput(
            sample_ids=split_input.sample_ids,
            labels=split_input.labels,
            snr_db=split_input.snr_db,
            group_ids=tuple(groups),
            source_revision=split_input.source_revision,
            input_sha256=split_input.input_sha256,
        )


def test_fewer_than_three_independent_groups_cannot_create_three_splits() -> None:
    with pytest.raises(SplitError, match="en az üç"):
        create_group_aware_splits(_split_input(group_count=2), _policy())


@pytest.mark.parametrize(
    "fractions",
    [
        (0.7, 0.2, 0.2),
        (1.0, 0.0, 0.0),
        (-0.1, 0.5, 0.6),
    ],
)
def test_invalid_split_fractions_fail_closed(fractions: tuple[float, float, float]) -> None:
    with pytest.raises(SplitError):
        SplitPolicy(*fractions, seed=1)


def test_unknown_snr_is_preserved_as_its_own_manifest_bucket() -> None:
    split_input = _split_input()
    snr_values = list(split_input.snr_db)
    snr_values[0] = None
    changed = SplitInput(
        sample_ids=split_input.sample_ids,
        labels=split_input.labels,
        snr_db=tuple(snr_values),
        group_ids=split_input.group_ids,
        source_revision=split_input.source_revision,
        input_sha256=split_input.input_sha256,
    )
    plan = create_group_aware_splits(changed, _policy())
    hashes = {
        name: character * 64 for name, character in zip(plan.indices_by_split, "bcd", strict=True)
    }

    manifest = plan.manifest(hashes)

    assert any(item["snr_bucket"] == "unknown" for item in manifest["global_distribution"]["snr"])


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("sample_ids", np.array([["a"], ["b"]]), "tek boyutlu"),
        ("group_ids", np.arange(48), "group_ids çözümlenmiş"),
        ("snr_db", np.full(48, np.inf), "Inf içeremez"),
    ],
)
def test_cli_rejects_invalid_metadata_arrays(
    tmp_path: Path, field: str, replacement: np.ndarray, message: str
) -> None:
    config_path = _write_cli_fixture(tmp_path)
    input_path = tmp_path / "metadata.npz"
    with np.load(input_path, allow_pickle=False) as payload:
        arrays = {name: np.asarray(payload[name]) for name in payload.files}
    arrays[field] = replacement
    np.savez(input_path, **arrays)

    with pytest.raises(SplitError, match=message):
        split_from_config(config_path)
