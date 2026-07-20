"""Default Manufacturing common API and state-changing persistence."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .base.common import *


def save_selection_state(runtime_root: Path, production_number: str, row_id: str, state: str) -> dict[str, str]:
    """Persist a row state while preserving non-state metadata records."""
    target_dir = runtime_root / production_number
    target_dir.mkdir(parents=True, exist_ok=True)
    path = selection_state_path(runtime_root, production_number)
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        raw_payload = {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    metadata = {
        str(key): value
        for key, value in raw_payload.items()
        if isinstance(value, (dict, list))
    }
    current = load_selection_state(runtime_root, production_number)
    normalized_state = str(state or "").strip().lower()
    if normalized_state in {"", "none", "clear"}:
        current.pop(row_id, None)
    elif normalized_state in {"green", "red", "done"}:
        current[row_id] = normalized_state
    elif is_structured_manufacturing_state_key(row_id) and re.fullmatch(r"\d{1,12}", normalized_state):
        current[row_id] = normalized_state
    path.write_text(json.dumps({**metadata, **current}, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def save_partial_quantity_state(runtime_root: Path, production_number: str, key: str, value: str) -> dict[str, str]:
    """Save or clear one partial-quantity value and return the new state map."""
    current = load_partial_quantity_state(runtime_root, production_number)
    normalized_key = str(key or "").strip()
    normalized_value = str(value or "").strip()
    if not normalized_key:
        return current
    if normalized_value:
        current[normalized_key] = normalized_value
    else:
        current.pop(normalized_key, None)
    target_dir = runtime_root / production_number
    target_dir.mkdir(parents=True, exist_ok=True)
    path = partial_quantity_state_path(runtime_root, production_number)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def complete_issued_row_edit(runtime_root: Path, shipment_id: str, row_key: str) -> bool:
    """Acknowledge one post-state admin-edit alert and return whether it existed."""
    clean_shipment_id = str(shipment_id or "").strip()
    clean_row_key = str(row_key or "").strip()
    if not clean_shipment_id or not clean_row_key:
        raise ValueError("Hiányzik a szállítmány vagy a sorazonosító.")
    target_dir = runtime_root / clean_shipment_id
    path = target_dir / "issued-row-edits.json"
    current = load_issued_row_edits(runtime_root, clean_shipment_id)
    previous = current.get(clean_row_key, {})
    was_pending = not bool(previous.get("completed")) if isinstance(previous, dict) else True
    current[clean_row_key] = {
        "category_key": str(previous.get("category_key", "") if isinstance(previous, dict) else ""),
        "edited_at": str(previous.get("edited_at", "") if isinstance(previous, dict) else ""),
        "edited_fields": list(previous.get("edited_fields", []) if isinstance(previous, dict) else []),
        "completed": True,
        "completed_at": str(time.time_ns()),
    }
    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return was_pending
