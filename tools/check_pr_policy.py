from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_PATH = ROOT / "policy" / "exceptions.json"
MAX_EXCEPTION_DAYS = 30
CHECKLIST_CONTROLS = {"scope", "tests", "security", "colab", "docs"}
CHECKLIST_TEXT = {
    "scope": "PR tek bir anlaşılır amacı kapsıyor",
    "tests": "İlgili yerel testler ve kalite kontrolleri çalıştırıldı",
    "security": "Secret, bağımlılık ve lisans etkileri kontrol edildi",
    "colab": "Colab/model etkisi yok veya gerekli kanıt manifesti hazır",
    "docs": "Dokümantasyon güncellendi veya değişiklik gerektirmediği doğrulandı",
}
CHECKED_ITEM_PATTERN = re.compile(r"^\s*[-*+]\s+\[[xX]\]\s+(.+)$", re.MULTILINE)
POLICY_MARKER_PATTERN = re.compile(r"<!--\s*policy:(scope|tests|security|colab|docs)\s*-->")


def checked_controls(body: str) -> set[str]:
    controls: set[str] = set()
    for item in CHECKED_ITEM_PATTERN.findall(body):
        marker = POLICY_MARKER_PATTERN.search(item)
        if marker:
            controls.add(marker.group(1))
            continue
        normalized = item.casefold()
        controls.update(
            control for control, text in CHECKLIST_TEXT.items() if text.casefold() in normalized
        )
    return controls


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
            isinstance(control, str) and (control in CHECKLIST_CONTROLS or control == "draft")
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
    except (OSError, ValueError, json.JSONDecodeError) as exc:
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
            body = str(pull_request.get("body") or "")
            if pull_request.get("draft") and "draft" not in controls:
                errors.append("PR draft durumunda; merge için ready olmalı")
            missing = CHECKLIST_CONTROLS - checked_controls(body) - controls
            if missing:
                errors.append("işaretlenmemiş PR kontrolleri: " + ", ".join(sorted(missing)))

    if errors:
        for error in errors:
            print(f"pr-policy ERROR: {error}", file=sys.stderr)
        return 1

    mode = f"PR #{pr_number}" if event is not None else "yerel kontrol"
    print(f"pr-policy OK: {mode}; readiness, checklist ve istisna politikası geçerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
