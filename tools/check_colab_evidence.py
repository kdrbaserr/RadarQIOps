from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evidence" / "colab"
SENSITIVE_PREFIXES = (
    "src/radariq/models/",
    "src/radariq/training/",
    "src/radariq/evaluation/",
)
SENSITIVE_FILES = {
    "configs/model.yaml",
    "configs/train.yaml",
    "configs/evaluate.yaml",
}
REQUIRED_TEST_GROUPS = {
    "model_feature",
    "gradient",
    "overfit",
    "reproducibility",
    "evaluation",
}


class EvidenceError(RuntimeError):
    """Raised when model changes do not have matching Colab evidence."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    output = _git("diff", "--name-only", f"{base_sha}...{head_sha}")
    return [line.replace("\\", "/") for line in output.splitlines() if line]


def is_model_sensitive(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in SENSITIVE_FILES or normalized.startswith(SENSITIVE_PREFIXES)


def sensitive_source_paths() -> list[Path]:
    paths: set[Path] = set()
    for prefix in SENSITIVE_PREFIXES:
        directory = ROOT / prefix
        if directory.exists():
            paths.update(path for path in directory.rglob("*.py") if path.is_file())
    paths.update(ROOT / relative for relative in SENSITIVE_FILES if (ROOT / relative).is_file())
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def source_tree_sha256(paths: list[Path] | None = None) -> str:
    digest = hashlib.sha256()
    for path in paths or sensitive_source_paths():
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_manifest(manifest: dict[str, Any], expected_tree_hash: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0":
        errors.append("schema_version '1.0' olmalı")
    if manifest.get("task_id") != "modulation_classification":
        errors.append("task_id 'modulation_classification' olmalı")
    if manifest.get("source_tree_sha256") != expected_tree_hash:
        errors.append("source_tree_sha256 model kaynak ağacıyla eşleşmiyor")

    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict) or not _nonempty_string(dataset.get("sha256")):
        errors.append("dataset.sha256 zorunlu")

    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or not _nonempty_string(runtime.get("manifest_sha256")):
        errors.append("runtime.manifest_sha256 zorunlu")

    notebook = manifest.get("notebook")
    if not isinstance(notebook, dict) or not _nonempty_string(notebook.get("sha256")):
        errors.append("notebook.sha256 zorunlu")

    tests = manifest.get("tests")
    if not isinstance(tests, dict):
        errors.append("tests nesnesi zorunlu")
    else:
        passed_groups = tests.get("passed_groups")
        if not isinstance(passed_groups, list) or not all(
            isinstance(group, str) for group in passed_groups
        ):
            errors.append("tests.passed_groups metin listesi olmalı")
            groups: set[str] = set()
        else:
            groups = set(passed_groups)
        missing_groups = sorted(REQUIRED_TEST_GROUPS - groups)
        if missing_groups:
            errors.append("eksik/geçmeyen Colab test grupları: " + ", ".join(missing_groups))
        if not _nonempty_string(tests.get("report_sha256")):
            errors.append("tests.report_sha256 zorunlu")

    evaluation = manifest.get("evaluation")
    if not isinstance(evaluation, dict) or not _nonempty_string(evaluation.get("report_sha256")):
        errors.append("evaluation.report_sha256 zorunlu")

    export = manifest.get("export")
    if not isinstance(export, dict):
        errors.append("export nesnesi zorunlu")
    else:
        for field in ("artifact_sha256", "class_map_sha256", "contract_sha256"):
            if not _nonempty_string(export.get(field)):
                errors.append(f"export.{field} zorunlu")
    return errors


def matching_manifest(expected_tree_hash: str) -> Path:
    failures: list[str] = []
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{path.name}: okunamadı ({exc})")
            continue
        if not isinstance(manifest, dict):
            failures.append(f"{path.name}: JSON nesnesi olmalı")
            continue
        errors = validate_manifest(manifest, expected_tree_hash)
        if not errors:
            return path
        failures.append(f"{path.name}: " + "; ".join(errors))

    detail = "\n".join(f"- {failure}" for failure in failures)
    if not detail:
        detail = "- evidence/colab altında manifest yok"
    raise EvidenceError(
        "Model hassas dosyaları değişti fakat eşleşen Colab kanıtı bulunamadı.\n" + detail
    )


def main() -> int:
    base_sha = os.getenv("GITHUB_BASE_SHA") or _git("rev-parse", "HEAD^")
    head_sha = os.getenv("GITHUB_HEAD_SHA") or _git("rev-parse", "HEAD")
    changed = changed_paths(base_sha, head_sha)
    sensitive_changes = sorted(path for path in changed if is_model_sensitive(path))
    if not sensitive_changes:
        print("colab-evidence OK: model hassas dosya değişmedi; kanıt gerekmiyor")
        return 0

    print("Colab kanıtı gerektiren değişiklikler:")
    for path in sensitive_changes:
        print(f"- {path}")
    tree_hash = source_tree_sha256()
    manifest_path = matching_manifest(tree_hash)
    print(f"colab-evidence OK: {manifest_path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, subprocess.CalledProcessError) as exc:
        print(f"colab-evidence ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
