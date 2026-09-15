"""Shared recount state helpers for front and semifinished inventories."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation


def inventory_row_values(row: dict, kind: str) -> dict:
    """Return normalized quantities and recount flags for an inventory row."""
    counted_raw = row.get("initial_count_qty", row.get("input_qty", row.get("counted_qty", "")))
    counted = _number(counted_raw)
    book = _number(row.get("stock_qty") if kind == "front" else row.get("book_qty"))
    is_counted = counted is not None
    mismatch = is_counted and book is not None and counted != book
    selected = bool(row.get("recount_selected")) if "recount_selected" in row else mismatch
    recount_raw = row.get("recount_input_qty", "")
    return {
        "book_qty": _display_number(book),
        "counted_qty": _display_number(counted),
        "is_counted": is_counted,
        "mismatch": mismatch,
        "selected": selected,
        "send_count": int(row.get("recount_send_count", 0) or 0),
        "pending": bool(row.get("recount_pending")),
        "recount_qty": _display_number(_number(recount_raw)),
        "recounted": str(recount_raw or "").strip() != "",
    }


def set_recount_selection(session: dict, row_id: str, selected: bool) -> tuple[bool, str]:
    """Persist an administrator's explicit recount selection."""
    row = _find_row(session, row_id)
    if row is None:
        return False, "A kiválasztott tétel nem található."
    if _is_finalized(session):
        return False, "A leltár már le van zárva."
    row["recount_selected"] = bool(selected)
    _touch(session)
    return True, ""


def send_group_to_recount(session: dict, group: str, kind: str) -> tuple[bool, str, int]:
    """Send selected rows from exactly one size/color group to recounting."""
    if _is_finalized(session):
        return False, "A leltár már le van zárva.", 0
    target_group = str(group or "").strip()
    if not target_group:
        return False, "Válassz méret- vagy színcsoportot.", 0

    matches = []
    for row in session.get("rows", []):
        if not isinstance(row, dict) or row_group(row, kind) != target_group:
            continue
        values = inventory_row_values(row, kind)
        if values["selected"]:
            matches.append(row)
    if not matches:
        return False, "A kiválasztott csoportban nincs újraszámolásra jelölt tétel.", 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for row in matches:
        history = row.setdefault("recount_history", [])
        previous = str(row.get("recount_input_qty", "") or "").strip()
        if previous:
            history.append({"round": int(row.get("recount_send_count", 0) or 0), "quantity": previous, "recorded_at": stamp})
        if "initial_count_qty" not in row:
            row["initial_count_qty"] = str(row.get("input_qty", row.get("counted_qty", "")) or "")
        row["recount_send_count"] = int(row.get("recount_send_count", 0) or 0) + 1
        row["recount_pending"] = True
        row["recount_input_qty"] = ""
        row["recount_selected"] = False
        row["recount_sent_at"] = stamp
    _touch(session)
    return True, f"{len(matches)} tétel újraszámolásra elküldve: {target_group}.", len(matches)


def update_recount_input(session: dict, row_id: str, raw_value: str, mode: str, kind: str) -> tuple[bool, str, str]:
    """Update a pending recount and mirror it to the finalization input."""
    row = _find_row(session, row_id)
    if row is None:
        return False, "A kiválasztott tétel nem található.", ""
    if _is_finalized(session):
        return False, "A leltár már le van zárva.", ""
    if not row.get("recount_pending"):
        return False, "Ez a tétel nincs újraszámolásra kijelölve.", ""

    clean_mode = str(mode or "set").strip().lower()
    if clean_mode not in {"set", "add", "subtract"}:
        clean_mode = "set"
    clean_value = str(raw_value or "").strip().replace(",", ".")
    if not clean_value and clean_mode == "set":
        row["recount_input_qty"] = ""
        _touch(session)
        return True, "", ""
    amount = _number(clean_value)
    if amount is None or amount < 0:
        return False, "Csak nem negatív szám adható meg.", ""
    current = _number(row.get("recount_input_qty")) or Decimal(0)
    result = amount if clean_mode == "set" else current + amount if clean_mode == "add" else current - amount
    if result < 0:
        return False, "A levonás után nem lehet negatív a darabszám.", ""
    if kind == "front" and result != result.to_integral_value():
        return False, "A frontoknál egész darabszám adható meg.", ""

    display = _display_number(result)
    row["recount_input_qty"] = display
    # The existing close operation remains unchanged and consumes input_qty.
    row["input_qty"] = display
    row["recount_completed_at"] = datetime.now().isoformat(timespec="seconds")
    _touch(session)
    return True, "", display


def recount_groups(session: dict, kind: str, only_selected: bool = False) -> list[dict]:
    """Return sorted size/color group summaries for admin actions."""
    buckets: dict[str, int] = {}
    for row in session.get("rows", []):
        if not isinstance(row, dict):
            continue
        if only_selected and not inventory_row_values(row, kind)["selected"]:
            continue
        group = row_group(row, kind)
        if group:
            buckets[group] = buckets.get(group, 0) + 1
    return [{"key": key, "count": buckets[key]} for key in sorted(buckets, key=_natural_key)]


def recount_rows(session: dict, kind: str, view: str = "check") -> list[dict]:
    """Return rows decorated for the checker or recount-review views."""
    result = []
    for row in session.get("rows", []):
        if not isinstance(row, dict):
            continue
        values = inventory_row_values(row, kind)
        if view == "recount" and values["send_count"] < 1:
            continue
        result.append({**row, **values, "group": row_group(row, kind)})
    return sorted(result, key=lambda row: (_natural_key(str(row.get("group", ""))), str(row.get("description", "")).casefold()))


def row_group(row: dict, kind: str) -> str:
    """Return the requested business grouping: front size or semifinished color."""
    if kind == "front":
        return str(row.get("category") or row.get("size") or "Egyéb").strip()
    return str(row.get("icg_code") or "Szín nélkül").strip()


def _find_row(session: dict, row_id: str) -> dict | None:
    target = str(row_id or "").strip().casefold()
    return next((row for row in session.get("rows", []) if isinstance(row, dict) and str(row.get("row_id", "")).strip().casefold() == target), None)


def _is_finalized(session: dict) -> bool:
    return str(session.get("phase", "")).strip().lower() == "finalized"


def _touch(session: dict) -> None:
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")


def _number(value: object) -> Decimal | None:
    text = str(value if value is not None else "").strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _display_number(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _natural_key(value: str) -> tuple:
    import re
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))
