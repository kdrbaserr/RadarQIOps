from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    """Load the repository's JSON-compatible YAML configuration files."""
    config_path = Path(path)
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Config bulunamadı: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config geçerli JSON/YAML değil: {config_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Config nesne olmalıdır: {config_path}")
    return value
