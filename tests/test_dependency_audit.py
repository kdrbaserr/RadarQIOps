from __future__ import annotations

import pytest

from tools.audit_dependencies import declared_licenses

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_combined_license_declaration_is_split() -> None:
    assert declared_licenses("Apache Software License; MIT License") == {
        "Apache Software License",
        "MIT License",
    }


def test_single_spdx_expression_stays_intact() -> None:
    assert declared_licenses("Apache-2.0 OR BSD-2-Clause") == {"Apache-2.0 OR BSD-2-Clause"}


def test_empty_license_is_unknown() -> None:
    assert declared_licenses("") == {"UNKNOWN"}
