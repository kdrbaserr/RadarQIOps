from __future__ import annotations

from copy import deepcopy

import pytest

from tools.check_colab_evidence import (
    REQUIRED_TEST_GROUPS,
    is_model_sensitive,
    source_tree_sha256,
    validate_manifest,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def valid_manifest(tree_hash: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": "modulation_classification",
        "source_tree_sha256": tree_hash,
        "dataset": {"sha256": "dataset-hash"},
        "runtime": {"manifest_sha256": "runtime-hash"},
        "notebook": {"sha256": "notebook-hash"},
        "tests": {
            "passed_groups": sorted(REQUIRED_TEST_GROUPS),
            "report_sha256": "tests-hash",
        },
        "evaluation": {"report_sha256": "evaluation-hash"},
        "export": {
            "artifact_sha256": "artifact-hash",
            "class_map_sha256": "class-map-hash",
            "contract_sha256": "contract-hash",
        },
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/radariq/models/network.py", True),
        ("configs/train.yaml", True),
        ("docs/architecture.md", False),
        ("tests/test_api.py", False),
    ],
)
def test_model_sensitive_path_detection(path: str, expected: bool) -> None:
    assert is_model_sensitive(path) is expected


def test_current_sensitive_source_hash_is_stable() -> None:
    first = source_tree_sha256()
    second = source_tree_sha256()

    assert first == second
    assert len(first) == 64


def test_complete_manifest_is_accepted() -> None:
    tree_hash = source_tree_sha256()

    assert validate_manifest(valid_manifest(tree_hash), tree_hash) == []


def test_missing_colab_test_group_is_rejected() -> None:
    tree_hash = source_tree_sha256()
    manifest = deepcopy(valid_manifest(tree_hash))
    tests = manifest["tests"]
    assert isinstance(tests, dict)
    tests["passed_groups"] = sorted(REQUIRED_TEST_GROUPS - {"gradient"})

    errors = validate_manifest(manifest, tree_hash)

    assert any("gradient" in error for error in errors)


def test_invalid_colab_test_groups_are_rejected_cleanly() -> None:
    tree_hash = source_tree_sha256()
    manifest = deepcopy(valid_manifest(tree_hash))
    tests = manifest["tests"]
    assert isinstance(tests, dict)
    tests["passed_groups"] = None

    errors = validate_manifest(manifest, tree_hash)

    assert any("tests.passed_groups" in error for error in errors)
