from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_PATH = ROOT / "policy" / "exceptions.json"
POLICY_WORKFLOW = ".github/workflows/pr-policy.yaml"
MAX_EXCEPTION_DAYS = 30
COMMIT_TYPES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)
COMMIT_PATTERN = re.compile(
    rf"^(?:{'|'.join(COMMIT_TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: .+[^.]$"
)
BLOCKED_PREFIXES = ("fixup!", "squash!", "wip", "WIP")
CHECKLIST_CONTROLS = {"scope", "tests", "security", "colab", "docs"}
CHECKED_ITEM_PATTERN = re.compile(
    r"^- \[[xX]\]\s+<!--\s*policy:(scope|tests|security|colab|docs)\s*-->",
    re.MULTILINE,
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def valid_conventional_subject(subject: str) -> bool:
    if subject.startswith(BLOCKED_PREFIXES) or len(subject) > 100:
        return False
    if subject.startswith(("Merge pull request #", 'Revert "')):
        return True
    return COMMIT_PATTERN.fullmatch(subject) is not None


def commit_subjects(base_sha: str, head_sha: str) -> list[tuple[str, str]]:
    commits = _git("rev-list", "--reverse", f"{base_sha}..{head_sha}").splitlines()
    subjects = [(commit, _git("show", "-s", "--format=%s", commit)) for commit in commits]

    # The adoption PR may contain older commits created before this policy existed.
    if _file_exists_at(base_sha, POLICY_WORKFLOW):
        return subjects
    for index, (commit, _) in enumerate(subjects):
        if _file_exists_at(commit, POLICY_WORKFLOW):
            return subjects[index:]
    return subjects[-1:]


def _file_exists_at(commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def checked_controls(body: str) -> set[str]:
    return set(CHECKED_ITEM_PATTERN.findall(body))


def validate_exception_document(document: dict[str, Any], *, today: date) -> list[str]:
    errors: list[str] = []
    if document.get("version") != 1:
        errors.append("policy/exceptions.json version değeri 1 olmalı")
    exceptions = document.get("exceptions")
    if not isinstance(exceptions, list):
        return [*errors, "exceptions bir liste olmalı"]

    seen_prs: set[int] = set()
    for index, item in enumerate(exceptions):
        prefix = f"exceptions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} nesne olmalı")
            continue
        pr_number = item.get("pr")
        if not isinstance(pr_number, int) or pr_number <= 0:
            errors.append(f"{prefix}.pr pozitif sayı olmalı")
        elif pr_number in seen_prs:
            errors.append(f"{prefix}.pr yinelenemez")
        else:
            seen_prs.add(pr_number)

        controls = item.get("controls")
        if not isinstance(controls, list) or not controls:
            errors.append(f"{prefix}.controls boş olmayan liste olmalı")
        elif not all(
            isinstance(control, str)
            and (control in CHECKLIST_CONTROLS or control in {"commits", "title", "draft"})
            for control in controls
        ):
            errors.append(f"{prefix}.controls bilinmeyen kontrol içeriyor")

        for field in ("owner", "reason"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{prefix}.{field} zorunlu")
        try:
            approved_on = date.fromisoformat(str(item.get("approved_on")))
            expires_on = date.fromisoformat(str(item.get("expires_on")))
        except ValueError:
            errors.append(f"{prefix} tarihleri YYYY-MM-DD biçiminde olmalı")
            continue
        if expires_on < today:
            errors.append(f"{prefix} süresi dolmuş")
        if expires_on < approved_on or expires_on > approved_on + timedelta(
            days=MAX_EXCEPTION_DAYS
        ):
            errors.append(f"{prefix} en fazla {MAX_EXCEPTION_DAYS} gün geçerli olabilir")
    return errors


def active_exception_controls(
    document: dict[str, Any],
    *,
    pr_number: int,
    today: date,
) -> set[str]:
    exceptions = document.get("exceptions", [])
    if not isinstance(exceptions, list):
        return set()
    for item in exceptions:
        if not isinstance(item, dict) or item.get("pr") != pr_number:
            continue
        try:
            expires_on = date.fromisoformat(str(item.get("expires_on")))
        except ValueError:
            return set()
        if expires_on >= today and isinstance(item.get("controls"), list):
            return {str(control) for control in item["controls"]}
    return set()


def _load_exceptions() -> dict[str, Any]:
    document = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("policy/exceptions.json nesne olmalı")
    return document


def _event() -> dict[str, Any] | None:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    document = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("GitHub event JSON nesne olmalı")
    return document


def main() -> int:
    try:
        exceptions = _load_exceptions()
        exception_errors = validate_exception_document(exceptions, today=date.today())
        event = _event()
        base_sha = os.getenv("GITHUB_BASE_SHA") or _git("rev-parse", "HEAD^")
        head_sha = os.getenv("GITHUB_HEAD_SHA") or _git("rev-parse", "HEAD")
        subjects = commit_subjects(base_sha, head_sha)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"pr-policy ERROR: {exc}", file=sys.stderr)
        return 2

    errors = list(exception_errors)
    pr_number = 0
    controls: set[str] = set()
    if event is not None:
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, dict):
            errors.append("pull_request event verisi bulunamadı")
        else:
            pr_number = int(event.get("number", 0))
            controls = active_exception_controls(
                exceptions,
                pr_number=pr_number,
                today=date.today(),
            )
            title = str(pull_request.get("title", ""))
            body = str(pull_request.get("body") or "")
            if pull_request.get("draft") and "draft" not in controls:
                errors.append("PR draft durumunda; merge için ready olmalı")
            if not valid_conventional_subject(title) and "title" not in controls:
                errors.append(f"PR başlığı Conventional Commits biçiminde değil: {title!r}")
            missing = CHECKLIST_CONTROLS - checked_controls(body) - controls
            if missing:
                errors.append("işaretlenmemiş PR kontrolleri: " + ", ".join(sorted(missing)))

    if "commits" not in controls:
        for commit, subject in subjects:
            if not valid_conventional_subject(subject):
                errors.append(f"geçersiz commit {commit[:8]}: {subject!r}")

    if errors:
        for error in errors:
            print(f"pr-policy ERROR: {error}", file=sys.stderr)
        return 1

    mode = f"PR #{pr_number}" if event is not None else "yerel commit"
    print(f"pr-policy OK: {mode}; commit, başlık, checklist ve istisna politikası geçerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
