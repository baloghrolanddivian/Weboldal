"""Runtime storage helpers for Matt inventory uploads and reports."""

from __future__ import annotations

import json
from pathlib import Path

from .config import price_meta_path, runtime_dir, stock_meta_path
from .engine import read_bytes_if_exists


def read_meta(path: Path) -> dict:
    """Read a runtime metadata JSON object, returning empty dict on failure."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_meta(path: Path, payload: dict) -> None:
    """Persist a runtime metadata JSON object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def _matt_inventory_saved_price_payload() -> tuple[str, bytes] | None:
    """Return the saved price upload name and bytes if available."""
    meta = read_meta(price_meta_path())
    stored_name = str(meta.get("stored_name", "")).strip()
    original_name = str(meta.get("original_name", "")).strip() or stored_name
    if not stored_name:
        return None
    payload = read_bytes_if_exists(runtime_dir() / stored_name)
    if payload is None:
        return None
    return original_name, payload

def _matt_inventory_saved_price_name() -> str:
    """Return the original filename for the saved price upload."""
    meta = read_meta(price_meta_path())
    return str(meta.get("original_name", "")).strip()

def _matt_inventory_saved_stock_name() -> str:
    """Return the original filename for the saved stock upload."""
    meta = read_meta(stock_meta_path())
    return str(meta.get("original_name", "")).strip()

