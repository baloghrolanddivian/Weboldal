"""Default Manufacturing common API and state-changing persistence."""

from __future__ import annotations

import json
import re
import time
import threading
from pathlib import Path

from .base.common import *
from .base.common import _production_date_label_cached


PANTOLO_MISSING_INDEX_LOCK = threading.RLock()


def _pantolo_missing_row_snapshot(production_number: str, state_key: str) -> tuple[dict, dict] | None:
    """Resolve one newly-red Pántoló identity while its source XML is available."""
    from .pantolas.sections import _manufacturing_pantolo_sections
    from .workflow import _load_manufacturing_bundle_cached, _manufacturing_row_state_storage_key

    bundle = _load_manufacturing_bundle_cached(production_number)
    sections, _count = _manufacturing_pantolo_sections(bundle, production_number)
    wanted = str(state_key or "").strip()
    wanted_parts = wanted.split("::")
    for section in sections:
        if not isinstance(section, dict):
            continue
        for row in section.get("rows", []):
            if not isinstance(row, dict):
                continue
            parent_key = _manufacturing_row_state_storage_key(production_number, row)
            parent_row_id = str(row.get("row_id", "") or "").strip()
            matches_parent = wanted in {
                parent_key,
                parent_row_id,
                str(row.get("state_key", "") or "").strip(),
            }
            matches_child = (
                len(wanted_parts) == 4
                and len(parent_key.split("::")) == 4
                and wanted_parts[:3] == parent_key.split("::")[:3]
                and wanted_parts[3].isdigit()
                and int(wanted_parts[3]) > 0
            ) or bool(parent_row_id and re.fullmatch(re.escape(parent_row_id) + r"__(?:child|pantolo)_unit_\d+", wanted))
            if not matches_parent and not matches_child:
                continue
            snapshot = {
                key: value
                for key, value in row.items()
                if not str(key).startswith("_")
            }
            snapshot["production_number"] = production_number
            snapshot["state_storage_key"] = wanted
            snapshot["state_key"] = wanted
            snapshot["sourceRowIds"] = []
            if matches_child:
                child_match = re.search(r"(\d+)$", wanted)
                child_number = int(child_match.group(1)) if child_match else 1
                snapshot["row_id"] = f"{str(row.get('row_id', '')).strip()}__child_unit_{child_number}"
                snapshot["quantity"] = 1
                snapshot["meValue"] = 1
                snapshot["isPantoloUnit"] = True
            category = {
                "key": str(section.get("key", "") or "pantolo").strip(),
                "label": str(section.get("label", "") or "Pántoló").strip(),
                "cabinetLevel": str(section.get("cabinetLevel", "") or "").strip(),
                "columnLayout": str(section.get("columnLayout", "") or snapshot.get("columnLayout", "pantolo")).strip(),
            }
            return category, snapshot
    return None


def sync_pantolo_missing_state(runtime_root: Path, production_number: str, state_keys: list[str], state: str) -> None:
    """Add/remove Pántoló red snapshots without consulting old XML on reads."""
    clean_number = re.sub(r"[^0-9]", "", str(production_number or ""))
    clean_keys = list(dict.fromkeys(str(key or "").strip() for key in state_keys if str(key or "").strip()))
    if not clean_number or not clean_keys:
        return
    normalized_state = str(state or "").strip().lower()
    with PANTOLO_MISSING_INDEX_LOCK:
        payload = load_pantolo_missing_index(runtime_root)
        productions = payload.setdefault("productions", {})
        production = productions.get(clean_number)
        if not isinstance(production, dict):
            production = {"production_date": "", "categories": {}}
            productions[clean_number] = production
        categories = production.setdefault("categories", {})
        if not isinstance(categories, dict):
            categories = {}
            production["categories"] = categories

        for key in clean_keys:
            for category_key, category in list(categories.items()):
                rows = category.get("rows", {}) if isinstance(category, dict) else {}
                if isinstance(rows, dict):
                    rows.pop(key, None)
                if not rows:
                    categories.pop(category_key, None)
            if normalized_state != "red":
                continue
            resolved = _pantolo_missing_row_snapshot(clean_number, key)
            if not resolved:
                continue
            category_data, row_snapshot = resolved
            category_key = category_data.pop("key") or "pantolo"
            category = categories.setdefault(category_key, {**category_data, "rows": {}})
            category.setdefault("rows", {})[key] = row_snapshot

        if categories and not str(production.get("production_date", "")).strip():
            production["production_date"] = _production_date_label_cached(production_folder(clean_number))
        if not categories:
            productions.pop(clean_number, None)
        target = runtime_root / PANTOLO_MISSING_INDEX_FILE
        runtime_root.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def save_pantolo_missing_description(runtime_root: Path, production_number: str, row_key: str, description: str) -> None:
    """Save an admin description into every missing child of one parent row."""
    clean_number = re.sub(r"[^0-9]", "", str(production_number or ""))
    clean_key = str(row_key or "").strip()
    if not clean_number or not clean_key:
        return
    clean_description = str(description or "")[:500]
    clean_parts = clean_key.split("::")
    with PANTOLO_MISSING_INDEX_LOCK:
        payload = load_pantolo_missing_index(runtime_root)
        production = payload.get("productions", {}).get(clean_number, {})
        categories = production.get("categories", {}) if isinstance(production, dict) else {}
        changed = False
        for category in categories.values() if isinstance(categories, dict) else []:
            rows = category.get("rows", {}) if isinstance(category, dict) else {}
            for state_key, row in rows.items() if isinstance(rows, dict) else []:
                state_parts = str(state_key or "").split("::")
                same_parent = (
                    len(clean_parts) == 4
                    and len(state_parts) == 4
                    and clean_parts[:3] == state_parts[:3]
                )
                if not isinstance(row, dict) or (str(state_key) != clean_key and not same_parent):
                    continue
                row["missingDescription"] = clean_description
                changed = True
        if not changed:
            return
        target = runtime_root / PANTOLO_MISSING_INDEX_FILE
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


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
