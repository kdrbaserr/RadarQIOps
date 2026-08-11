from __future__ import annotations

from datetime import date

import pytest

from tools.check_security_policy import validate_policy

pytestmark = [pytest.mark.unit, pytest.mark.contract]
TODAY = date(2026, 8, 11)


def base_config() -> dict[str, object]:
    return {
        "version": 1,
        "vulnerabilities": {"fail_on": "all-known"},
        "licenses": {
            "scope": "runtime-and-serve",
            "allowed": ["MIT", "Apache-2.0"],
        },
    }


def empty_exceptions() -> dict[str, object]:
    return {"version": 1, "exceptions": []}


def test_empty_exception_policy_is_valid() -> None:
    assert validate_policy(base_config(), empty_exceptions(), today=TODAY) == []


def test_forbidden_license_cannot_be_allowlisted() -> None:
    config = base_config()
    licenses = config["licenses"]
    assert isinstance(licenses, dict)
    licenses["allowed"] = ["MIT", "AGPL-3.0-only"]

    errors = validate_policy(config, empty_exceptions(), today=TODAY)

    assert any("GPL/AGPL" in error for error in errors)


def test_expired_vulnerability_exception_is_rejected() -> None:
    config = base_config()
    document = empty_exceptions()
    document["exceptions"] = [
        {
            "kind": "vulnerability",
            "id": "GHSA-example",
            "package": "example-package",
            "owner": "security-owner",
            "reason": "Geçici uyumluluk engeli",
            "approved_on": "2026-07-01",
            "expires_on": "2026-08-01",
        }
    ]

    errors = validate_policy(config, document, today=TODAY)

    assert any("süresi dolmuş" in error for error in errors)
