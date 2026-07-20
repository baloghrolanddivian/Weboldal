"""Admin Manufacturing common API and admin-only display persistence."""

from __future__ import annotations

# Admin-only persistence remains isolated from the shared read layer.

import json
import time
from datetime import date
from pathlib import Path

from manufacturing.base.common import *


def row_data_path(runtime_root: Path, production_number: str) -> Path:
    """Return the row-data override file beside the production state file."""
    return runtime_root / production_number / "row-data.json"


def save_row_data(
    runtime_root: Path,
    production_number: str,
    row_key: str,
    fields: dict[str, object],
) -> dict[str, str]:
    """Persist safe display overrides using the row's state identity."""
    clean_number = str(production_number or "").strip()
    clean_row_key = str(row_key or "").strip()
    if not clean_number or not clean_row_key:
        raise ValueError("Hiányzik a gyártás/szállítmány vagy a sorazonosító.")
    clean_fields = {
        str(field): str(value or "").strip()[:500]
        for field, value in fields.items()
        if str(field) in ROW_DATA_EDITABLE_FIELDS
    }
    if not clean_fields:
        raise ValueError("Nincs menthető soradat.")
    target_dir = runtime_root / clean_number
    target_dir.mkdir(parents=True, exist_ok=True)
    path = row_data_path(runtime_root, clean_number)
    current = load_row_data(runtime_root, clean_number)
    merged_fields = {**current.get(clean_row_key, {}), **clean_fields}
    current[clean_row_key] = merged_fields
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(merged_fields)


def topfloor_category_is_issued(runtime_root: Path, shipment_id: str, category_key: str) -> bool:
    """Return whether the row's persisted Topfloor category has been issued."""
    clean_shipment_id = str(shipment_id or "").strip()
    clean_category_key = str(category_key or "").strip()
    if not clean_shipment_id or not clean_category_key:
        return False
    state_path = runtime_root / clean_shipment_id / "state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    category_parts = clean_category_key.split("::")
    candidate_keys = {clean_category_key}
    if len(category_parts) >= 4:
        candidate_keys.add("::".join(category_parts[:3]))
    return any(
        isinstance(value, dict) and bool(value.get("storageBoxIssued"))
        for key, value in payload.items()
        if str(key or "").strip() in candidate_keys
    )


def topfloor_row_requires_edit_alert(
    runtime_root: Path,
    shipment_id: str,
    category_key: str,
    row_key: str,
) -> bool:
    """Return whether a Topfloor row is already loaded or its box is issued."""
    clean_shipment_id = str(shipment_id or "").strip()
    clean_row_key = str(row_key or "").strip()
    if not clean_shipment_id or not clean_row_key:
        return False
    if topfloor_category_is_issued(runtime_root, clean_shipment_id, category_key):
        return True
    state_path = runtime_root / clean_shipment_id / "state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    candidate_keys = {clean_row_key}
    if clean_row_key.endswith("::0"):
        candidate_keys.add(clean_row_key[:-3])
    elif clean_row_key.count("::") >= 2:
        candidate_keys.add(f"{clean_row_key}::0")
    normalized_candidates = {key.casefold() for key in candidate_keys}

    def topfloor_row_identity(value: object) -> str:
        """Match equivalent Topfloor/source keys by shipment, CON id and child."""
        parts = str(value or "").strip().split("::")
        if len(parts) != 4:
            return ""
        return "::".join(parts[1:]).casefold()

    candidate_identities = {
        identity
        for key in candidate_keys
        if (identity := topfloor_row_identity(key))
    }
    return any(
        (
            str(key or "").strip().casefold() in normalized_candidates
            or topfloor_row_identity(key) in candidate_identities
        )
        and str(value or "").strip().isdigit()
        and 1 <= len(str(value or "").strip()) <= 12
        for key, value in payload.items()
    )


def manufacturing_row_requires_edit_alert(
    runtime_root: Path,
    production_number: str,
    row_key: str,
    state_keys: list[str] | tuple[str, ...] | set[str] = (),
    visible_state: str = "",
) -> bool:
    """Return whether an edited non-Topfloor row is green or completed."""
    clean_number = str(production_number or "").strip()
    clean_row_key = str(row_key or "").strip()
    if not clean_number or not clean_row_key:
        return False
    if str(visible_state or "").strip().lower() in {"green", "done"}:
        return True

    candidates = {
        str(value or "").strip()
        for value in (clean_row_key, *state_keys)
        if str(value or "").strip()
    }
    expanded_candidates = set(candidates)
    for key in candidates:
        if key.endswith("::0"):
            expanded_candidates.add(key[:-3])
        elif key.count("::") >= 2:
            expanded_candidates.add(f"{key}::0")
        if not key.startswith(f"{clean_number}::") and key.count("::") < 2:
            expanded_candidates.add(f"{clean_number}::{key}")

    normalized_candidates = {key.casefold() for key in expanded_candidates}

    def structured_identity(value: object) -> str:
        parts = str(value or "").strip().split("::")
        if len(parts) != 4:
            return ""
        return "::".join(parts[1:]).casefold()

    candidate_identities = {
        identity
        for key in expanded_candidates
        if (identity := structured_identity(key))
    }
    state = load_selection_state(runtime_root, clean_number)
    return any(
        str(value or "").strip().lower() in {"green", "done"}
        and (
            str(key or "").strip().casefold() in normalized_candidates
            or structured_identity(key) in candidate_identities
        )
        for key, value in state.items()
    )


def save_issued_row_edit_marker(
    runtime_root: Path,
    shipment_id: str,
    row_key: str,
    category_key: str,
    edited_fields: list[str] | tuple[str, ...] | set[str],
) -> dict[str, object]:
    """Persist an alert marker for a handled row changed by an administrator."""
    clean_shipment_id = str(shipment_id or "").strip()
    clean_row_key = str(row_key or "").strip()
    clean_category_key = str(category_key or "").strip()
    clean_fields = sorted({
        str(field).strip()
        for field in edited_fields
        if str(field).strip() in ROW_DATA_EDITABLE_FIELDS
    })
    if not clean_shipment_id or not clean_row_key or not clean_fields:
        raise ValueError("Hiányos betöltés vagy kiadás utáni sormódosítás-jelölés.")
    target_dir = runtime_root / clean_shipment_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "issued-row-edits.json"
    current = load_issued_row_edits(runtime_root, clean_shipment_id)
    previous = current.get(clean_row_key, {})
    previous_fields = previous.get("edited_fields", []) if isinstance(previous, dict) else []
    marker = {
        "category_key": clean_category_key,
        "edited_at": str(time.time_ns()),
        "edited_fields": sorted(set(previous_fields if isinstance(previous_fields, list) else []) | set(clean_fields)),
    }
    current[clean_row_key] = marker
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(marker)


def save_shipment_date(runtime_root: Path, shipment_id: str, shipment_date: str) -> str:
    """Save or clear a Topfloor shipment date beside its state JSON."""
    clean_shipment_id = str(shipment_id or "").strip()
    clean_date = str(shipment_date or "").strip()
    if not clean_shipment_id:
        raise ValueError("Hiányzik a szállítmány azonosítója.")
    if clean_date:
        try:
            date.fromisoformat(clean_date)
        except ValueError as exc:
            raise ValueError("A szállítási dátum formátuma hibás.") from exc
    target_dir = runtime_root / clean_shipment_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "shipment-date.json").write_text(
        json.dumps({"shipment_date": clean_date}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return clean_date


def signal_admin_change(runtime_root: Path, *, kind: str, target: str) -> str:
    """Bump the revision observed by every open Manufacturing view."""
    runtime_root.mkdir(parents=True, exist_ok=True)
    revision = str(time.time_ns())
    (runtime_root / "admin-change.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "kind": str(kind or "").strip(),
                "target": str(target or "").strip(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return revision
