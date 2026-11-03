"""Per-user runtime state for the scanned-part tablet workstation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path


_runtime_dir = Path("runtime") / "alkatresz-munkalap"
_lock = threading.RLock()
MAX_BARCODE_LENGTH = 160


def configure_part_workstation(runtime_dir: Path) -> None:
    """Set the runtime directory used to keep each user's latest scan."""
    global _runtime_dir
    _runtime_dir = Path(runtime_dir)


def empty_state() -> dict:
    """Return the stable client contract used before an item API is available."""
    return {
        "barcode": "",
        "scanned_at": "",
        "lookup_status": "waiting_for_scan",
        "item": {
            "part_number": "",
            "description": "",
            "dimensions": "",
            "material": "",
            "color": "",
            "production_number": "",
            "order_number": "",
        },
        "model": None,
        "bom": [],
    }


def load_user_state(user_id: str) -> dict:
    """Load only the state belonging to the given authenticated user."""
    path = _state_path(user_id)
    with _lock:
        if not path.is_file():
            return empty_state()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_state()
    return _normalized_state(payload)


def register_scan(user_id: str, barcode: str) -> dict:
    """Persist a scan and expose the future item-API integration boundary."""
    clean_barcode = _clean_barcode(barcode)
    if not clean_barcode:
        raise ValueError("A vonalkód nem lehet üres.")
    if len(clean_barcode) > MAX_BARCODE_LENGTH:
        raise ValueError(f"A vonalkód legfeljebb {MAX_BARCODE_LENGTH} karakter lehet.")

    # Future integration point: replace this API-pending payload with the
    # normalized response of the item/master-data service.
    state = empty_state()
    state.update(
        {
            "barcode": clean_barcode,
            "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "lookup_status": "api_pending",
        }
    )
    _write_user_state(user_id, state)
    return state


def reset_user_state(user_id: str) -> dict:
    """Clear one user's workstation without changing any other user's state."""
    path = _state_path(user_id)
    with _lock:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return empty_state()


def _clean_barcode(value: object) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()


def _state_path(user_id: str) -> Path:
    identity = str(user_id or "anonymous").encode("utf-8")
    key = hashlib.sha256(identity).hexdigest()[:24]
    return _runtime_dir / "users" / f"{key}.json"


def _write_user_state(user_id: str, state: dict) -> None:
    path = _state_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(_normalized_state(state), ensure_ascii=False, indent=2)
    with _lock:
        file_descriptor, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


def _normalized_state(payload: object) -> dict:
    result = empty_state()
    if not isinstance(payload, dict):
        return result
    result["barcode"] = _clean_barcode(payload.get("barcode", ""))[:MAX_BARCODE_LENGTH]
    result["scanned_at"] = str(payload.get("scanned_at", "") or "")[:64]
    status = str(payload.get("lookup_status", "") or "")
    result["lookup_status"] = status if status in {"waiting_for_scan", "api_pending", "ready", "error"} else "waiting_for_scan"
    source_item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    for key in result["item"]:
        result["item"][key] = str(source_item.get(key, "") or "")[:500]
    result["model"] = payload.get("model") if isinstance(payload.get("model"), dict) else None
    source_bom = payload.get("bom") if isinstance(payload.get("bom"), list) else []
    result["bom"] = [row for row in source_bom if isinstance(row, dict)][:100]
    return result
