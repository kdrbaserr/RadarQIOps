from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "security" / "policy.yml"
EXCEPTIONS_PATH = ROOT / "security" / "exceptions.yml"


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.relative_to(ROOT).as_posix()} YAML nesnesi olmalı")
    return document


def export_requirements(output: Path, *, runtime_only: bool) -> None:
    command = [
        "uv",
        "export",
        "--locked",
        "--all-extras",
        "--no-emit-project",
        "--quiet",
        "--output-file",
        str(output),
    ]
    if runtime_only:
        command.extend(("--no-dev", "--no-hashes"))
    else:
        command.append("--all-groups")
    subprocess.run(command, cwd=ROOT, check=True)


def vulnerability_exception_ids(exceptions: dict[str, Any]) -> list[str]:
    items = exceptions.get("exceptions", [])
    if not isinstance(items, list):
        return []
    return [
        str(item["id"])
        for item in items
        if isinstance(item, dict) and item.get("kind") == "vulnerability" and item.get("id")
    ]


def audit_vulnerabilities(requirements: Path, exceptions: dict[str, Any]) -> int:
    command = [
        "pip-audit",
        "--requirement",
        str(requirements),
        "--progress-spinner",
        "off",
        "--aliases",
        "on",
        "--disable-pip",
        "--require-hashes",
    ]
    for identifier in vulnerability_exception_ids(exceptions):
        command.extend(("--ignore-vuln", identifier))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def runtime_package_names(requirements: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-e ")) or line == "\\":
            continue
        line = re.sub(r"\s+\\$", "", line)
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            names.add(canonicalize_name(requirement.name))
    return names


def allowed_license_names(policy: dict[str, Any]) -> set[str]:
    licenses = policy.get("licenses")
    if not isinstance(licenses, dict) or not isinstance(licenses.get("allowed"), list):
        return set()
    return {str(item) for item in licenses["allowed"]}


def declared_licenses(value: Any) -> set[str]:
    if not isinstance(value, str):
        return {"UNKNOWN"}
    licenses = {item.strip() for item in value.split(";") if item.strip()}
    return licenses or {"UNKNOWN"}


def license_exception_packages(exceptions: dict[str, Any]) -> set[str]:
    items = exceptions.get("exceptions", [])
    if not isinstance(items, list):
        return set()
    return {
        canonicalize_name(str(item["package"]))
        for item in items
        if isinstance(item, dict) and item.get("kind") == "license" and item.get("package")
    }


def audit_runtime_licenses(
    requirements: Path,
    policy: dict[str, Any],
    exceptions: dict[str, Any],
) -> list[str]:
    result = subprocess.run(
        ["pip-licenses", "--format=json", "--with-system"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(result.stdout)
    if not isinstance(rows, list):
        raise ValueError("pip-licenses çıktısı liste olmalı")

    runtime_names = runtime_package_names(requirements)
    allowed = allowed_license_names(policy)
    excepted = license_exception_packages(exceptions)
    installed_runtime: set[str] = set()
    violations: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = canonicalize_name(str(row.get("Name", "")))
        if name not in runtime_names:
            continue
        installed_runtime.add(name)
        license_name = str(row.get("License", "UNKNOWN"))
        unapproved = declared_licenses(license_name) - allowed
        if unapproved and name not in excepted:
            violations.append(
                f"{name}: izin verilmeyen lisans(lar) '{'; '.join(sorted(unapproved))}'"
            )

    missing = sorted(runtime_names - installed_runtime)
    violations.extend(f"{name}: lisans bilgisi bulunamadı" for name in missing)
    return violations


def main() -> int:
    try:
        policy = load_yaml(POLICY_PATH)
        exceptions = load_yaml(EXCEPTIONS_PATH)
        with tempfile.TemporaryDirectory(prefix="radariq-security-") as temp_dir:
            temp = Path(temp_dir)
            all_requirements = temp / "all-requirements.txt"
            runtime_requirements = temp / "runtime-requirements.txt"
            export_requirements(all_requirements, runtime_only=False)
            export_requirements(runtime_requirements, runtime_only=True)

            vulnerability_status = audit_vulnerabilities(all_requirements, exceptions)
            violations = audit_runtime_licenses(runtime_requirements, policy, exceptions)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"security-dependencies ERROR: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"security-dependencies ERROR: komut başarısız ({exc})", file=sys.stderr)
        return 2

    if vulnerability_status != 0:
        print("security-dependencies ERROR: bilinen zafiyet bulundu", file=sys.stderr)
    for violation in violations:
        print(f"security-dependencies ERROR: {violation}", file=sys.stderr)
    if vulnerability_status != 0 or violations:
        return 1

    print("security-dependencies OK: bilinen zafiyet yok; runtime lisansları izinli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
