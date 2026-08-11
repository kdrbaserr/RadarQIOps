from __future__ import annotations

from datetime import date

import pytest

from tools.check_pr_policy import (
    CHECKLIST_CONTROLS,
    checked_controls,
    valid_conventional_subject,
    validate_exception_document,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.parametrize(
    "subject",
    [
        "feat(api): add inference endpoint",
        "fix!: change artifact contract",
        "ci(policy): enforce PR rules",
        'Revert "feat(api): add inference endpoint"',
    ],
)
def test_valid_commit_subjects(subject: str) -> None:
    assert valid_conventional_subject(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "general test",
        "WIP train model",
        "fixup! feat(api): add endpoint",
        "feat: sentence ending with period.",
    ],
)
def test_invalid_commit_subjects(subject: str) -> None:
    assert not valid_conventional_subject(subject)


def test_checked_controls_are_extracted() -> None:
    body = "\n".join(f"- [x] <!-- policy:{control} --> done" for control in CHECKLIST_CONTROLS)

    assert checked_controls(body) == CHECKLIST_CONTROLS


def test_expired_policy_exception_is_rejected() -> None:
    document = {
        "version": 1,
        "exceptions": [
            {
                "pr": 14,
                "controls": ["tests"],
                "owner": "repo-owner",
                "reason": "Geçici CI kesintisi",
                "approved_on": "2026-07-01",
                "expires_on": "2026-07-15",
            }
        ],
    }

    errors = validate_exception_document(document, today=date(2026, 8, 11))

    assert any("süresi dolmuş" in error for error in errors)
