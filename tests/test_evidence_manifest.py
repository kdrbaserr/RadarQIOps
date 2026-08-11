from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.unit]


def test_evidence_manifest_declares_local_colab_boundary(evidence_manifest) -> None:
    assert evidence_manifest["schema_version"] == "1.0"
    assert evidence_manifest["default_seed"] == 20260811
    assert evidence_manifest["local_excluded_marker"] == "colab"
    assert set(evidence_manifest["colab_groups"]) == {
        "model_feature",
        "gradient",
        "overfit",
        "reproducibility",
        "evaluation",
    }
