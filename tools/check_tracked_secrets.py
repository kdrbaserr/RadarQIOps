from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".secrets.baseline"


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def main() -> int:
    executable = shutil.which("detect-secrets-hook")
    if executable is None:
        scripts_dir = Path(sys.executable).parent
        for name in ("detect-secrets-hook", "detect-secrets-hook.exe"):
            candidate = scripts_dir / name
            if candidate.is_file():
                executable = str(candidate)
                break
    if executable is None:
        print("security-secrets ERROR: detect-secrets-hook bulunamadı", file=sys.stderr)
        return 2

    files = tracked_files()
    if not files:
        print("security-secrets OK: taranacak takipli dosya yok")
        return 0

    result = subprocess.run(
        [executable, "--baseline", str(BASELINE), *files],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        print("security-secrets ERROR: olası secret bulundu", file=sys.stderr)
        return result.returncode

    print(f"security-secrets OK: {len(files)} takipli dosya tarandı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
