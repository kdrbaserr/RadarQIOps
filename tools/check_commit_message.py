from __future__ import annotations

import sys
from pathlib import Path

from check_pr_policy import valid_conventional_subject


def main() -> int:
    if len(sys.argv) != 2:
        print("commit-msg ERROR: commit mesajı dosyası bekleniyor", file=sys.stderr)
        return 2
    subject = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[0].strip()
    if not valid_conventional_subject(subject):
        print(
            "commit-msg ERROR: '<type>(<scope>): <açıklama>' biçimini kullan; "
            "WIP/fixup/squash mesajları kabul edilmez",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
