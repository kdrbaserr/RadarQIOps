from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "security" / "policy.yml"
EXCEPTIONS_PATH = ROOT / "security" / "exceptions.yml"
MAX_EXCEPTION_DAYS = 90
FORBIDDEN_LICENSE_FRAGMENTS = ("AGPL", "GPL")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(_text(item) for item in value):
        return None
    return [str(item) for item in value]


def _parse_date(value: Any, field: str, errors: list[str]) -> date | None:
    if isinstance(value, date):
        return value
    if not _text(value):
        errors.append(f"{field} YYYY-MM-DD biçiminde olmalı")
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{field} YYYY-MM-DD biçiminde olmalı")
        return None


def validate_policy(
    config: dict[str, Any],
    exception_document: dict[str, Any],
    *,
    today: date | None = None,
) -> list[str]:
    errors: list[str] = []
    current_date = today or date.today()

    if config.get("version") != 1:
        errors.append("security/policy.yml version değeri 1 olmalı")

    vulnerabilities = config.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict) or vulnerabilities.get("fail_on") != "all-known":
        errors.append("vulnerabilities.fail_on 'all-known' olmalı")

    licenses = config.get("licenses")
    if not isinstance(licenses, dict):
        errors.append("licenses nesnesi zorunlu")
        licenses = {}
    if licenses.get("scope") != "runtime-and-serve":
        errors.append("licenses.scope 'runtime-and-serve' olmalı")
    allowed_licenses = _string_list(licenses.get("allowed"))
    if not allowed_licenses:
        errors.append("licenses.allowed boş olmayan bir metin listesi olmalı")
    elif any(
        fragment in license_id.upper()
        for license_id in allowed_licenses
        for fragment in FORBIDDEN_LICENSE_FRAGMENTS
    ):
        errors.append("GPL/AGPL lisansları licenses.allowed içinde olamaz")

    if exception_document.get("version") != 1:
        errors.append("security/exceptions.yml version değeri 1 olmalı")
    exceptions = exception_document.get("exceptions")
    if not isinstance(exceptions, list):
        errors.append("exceptions bir liste olmalı")
        exceptions = []

    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(exceptions):
        prefix = f"exceptions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} nesne olmalı")
            continue

        kind = item.get("kind")
        identifier = item.get("id")
        if kind not in {"vulnerability", "license"}:
            errors.append(f"{prefix}.kind vulnerability veya license olmalı")
        if not _text(identifier):
            errors.append(f"{prefix}.id zorunlu")
            continue
        identifier = str(identifier)
        key = (str(kind), identifier)
        if key in seen:
            errors.append(f"{prefix}: yinelenen istisna {identifier}")
        seen.add(key)

        for field in ("package", "owner", "reason"):
            if not _text(item.get(field)):
                errors.append(f"{prefix}.{field} zorunlu")

        approved_on = _parse_date(item.get("approved_on"), f"{prefix}.approved_on", errors)
        expires_on = _parse_date(item.get("expires_on"), f"{prefix}.expires_on", errors)
        if approved_on and expires_on:
            if expires_on < current_date:
                errors.append(f"{prefix} süresi dolmuş: {expires_on.isoformat()}")
            if expires_on < approved_on:
                errors.append(f"{prefix}.expires_on approved_on tarihinden önce olamaz")
            if expires_on > approved_on + timedelta(days=MAX_EXCEPTION_DAYS):
                errors.append(f"{prefix} en fazla {MAX_EXCEPTION_DAYS} gün geçerli olabilir")

        if kind == "vulnerability":
            if not identifier.startswith(("GHSA-", "PYSEC-", "CVE-", "OSV-")):
                errors.append(f"{prefix}.id desteklenen bir zafiyet kimliği olmalı")
        elif kind == "license" and not identifier.startswith("pkg:"):
            errors.append(f"{prefix}.id bir package URL olmalı (pkg:...)")
    return errors


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.relative_to(ROOT).as_posix()} YAML nesnesi olmalı")
    return document


def main() -> int:
    try:
        config = load_yaml(CONFIG_PATH)
        exceptions = load_yaml(EXCEPTIONS_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"security-policy ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate_policy(config, exceptions)
    if errors:
        for error in errors:
            print(f"security-policy ERROR: {error}", file=sys.stderr)
        return 2

    print("security-policy OK: lisans, zafiyet eşiği ve süreli istisnalar geçerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
