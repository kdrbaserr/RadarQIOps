from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from radariq.data.dvc_pipeline import validate_pipeline_export_manifest


def verify_manifest(path: str | Path, expected_split_sha256: str | None = None) -> list[str]:
    manifest_path = Path(path)
    try:
        value: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest okunamadı: {exc}"]
    if not isinstance(value, dict):
        return ["manifest JSON nesnesi olmalıdır"]
    return validate_pipeline_export_manifest(value, expected_split_sha256)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="İndirilen küçük data-pipeline manifestini model verisini açmadan doğrula"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-split-sha256")
    args = parser.parse_args()
    errors = verify_manifest(args.manifest, args.expected_split_sha256)
    if errors:
        for error in errors:
            print(f"data-pipeline-export ERROR: {error}", file=sys.stderr)
        return 2
    print("data-pipeline-export OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
