from __future__ import annotations

from pathlib import Path

import pytest

from tools.audit_dependencies import allowed_license_names, declared_licenses, load_yaml

pytestmark = [pytest.mark.unit, pytest.mark.contract]
POLICY_PATH = Path(__file__).parents[1] / "security" / "policy.yml"
PYTORCH_SPDX_EXPRESSION = (
    "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause "
    "AND BSD-3-Clause AND BSL-1.0 AND MIT"
)


def test_combined_license_declaration_is_split() -> None:
    assert declared_licenses("Apache Software License; MIT License") == {
        "Apache Software License",
        "MIT License",
    }


def test_single_spdx_expression_stays_intact() -> None:
    assert declared_licenses("Apache-2.0 OR BSD-2-Clause") == {"Apache-2.0 OR BSD-2-Clause"}


def test_official_pytorch_spdx_expression_is_explicitly_allowed() -> None:
    assert declared_licenses(PYTORCH_SPDX_EXPRESSION) == {PYTORCH_SPDX_EXPRESSION}
    assert PYTORCH_SPDX_EXPRESSION in allowed_license_names(load_yaml(POLICY_PATH))


def test_empty_license_is_unknown() -> None:
    assert declared_licenses("") == {"UNKNOWN"}
