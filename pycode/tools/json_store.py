"""Small JSON file storage helpers."""

from __future__ import annotations

import json
from pathlib import Path


def read_json_object(path: Path) -> dict:
    """Read a JSON object from path, returning an empty dict on invalid input."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_object(path: Path, payload: dict) -> None:
    """Write a dict payload as pretty UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

