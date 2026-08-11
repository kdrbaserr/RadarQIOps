from __future__ import annotations

import json
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

DEFAULT_TEST_SEED = 20260811
EVIDENCE_MANIFEST_PATH = Path(__file__).with_name("evidence-manifest.json")


@pytest.fixture(autouse=True)
def deterministic_seed() -> Iterator[None]:
    """Reset Python and NumPy RNGs before every local test."""
    random.seed(DEFAULT_TEST_SEED)
    np.random.seed(DEFAULT_TEST_SEED)
    yield


@pytest.fixture
def test_seed() -> int:
    return DEFAULT_TEST_SEED


@pytest.fixture
def rng(test_seed: int) -> np.random.Generator:
    return np.random.default_rng(test_seed)


@pytest.fixture(scope="session")
def evidence_manifest() -> dict[str, Any]:
    return json.loads(EVIDENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
