"""Atomic runtime persistence and audit history for NettFront invoices."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path


_LOCK = threading.RLock()
_runtime_dir = Path(__file__).resolve().parents[2] / "runtime" / "nettfront-szamla"


class DuplicateInvoiceError(ValueError):
    """Raised when an invoice has already been persisted."""


def configure_nettfront_invoice(runtime_dir: Path) -> None:
    global _runtime_dir
    _runtime_dir = Path(runtime_dir)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_invoice_code(value: object) -> str:
    code = re.sub(r"\s+", "", str(value or "")).upper()
    if not code or len(code) > 80 or not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]*", code):
        raise ValueError("Hiányzó vagy érvénytelen számlakód.")
    return code


def _key(code: str) -> str:
    readable = re.sub(r"[^A-Z0-9]+", "-", normalize_invoice_code(code)).strip("-")[:48]
    digest = hashlib.sha256(normalize_invoice_code(code).encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"


def _invoice_dir(code: str) -> Path:
    return _runtime_dir / "invoices" / _key(code)


def _record_path(code: str) -> Path:
    return _invoice_dir(code) / "invoice.json"


def _safe_file_part(value: object, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return cleaned or fallback


def _saved_source_name(record: dict, suffix: str | None = None) -> str:
    code = _safe_file_part(record.get("invoice_code"), "invoice")
    invoice_date = _safe_file_part(record.get("invoice_date"), "date-unknown")
    status = _safe_file_part(record.get("status"), "opened")
    clean_suffix = str(suffix or record.get("source_extension", ".xml")).lower()
    if clean_suffix != ".xml":
        clean_suffix = ".xml"
    return f"{code}_{invoice_date}_{status}{clean_suffix}"


def _find_saved_source(record: dict) -> Path | None:
    invoice_dir = _invoice_dir(str(record.get("invoice_code", "")))
    saved_name = str(record.get("saved_file_name", "")).strip()
    if saved_name:
        candidate = invoice_dir / Path(saved_name).name
        if candidate.is_file():
            return candidate
    candidates = sorted(invoice_dir.glob("*.xml"))
    return candidates[0] if candidates else None


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(payload)
    os.replace(temp_path, path)


def _event(action: str, user: str, **details: object) -> dict:
    return {"time": _now(), "action": action, "user": str(user).strip(), "details": details}


def create_invoice(parsed: dict, source_data: bytes, opened_by: str, source_name: str) -> dict:
    code = normalize_invoice_code(parsed.get("invoice_code"))
    operator = str(opened_by or "").strip()
    if not operator:
        raise ValueError("Az azonosítás kötelező a számla megnyitásához.")
    with _LOCK:
        path = _record_path(code)
        if path.exists():
            raise DuplicateInvoiceError(f"A(z) {code} számlát már korábban rögzítették; nem tölthető fel újra.")
        created_at = _now()
        record = {
            **parsed,
            "invoice_code": code,
            "created_at": created_at,
            "status": "opened",
            "opened_by": operator,
            "closed_at": "",
            "closed_by": "",
            "failed_reads": [],
            "scan_history": [],
            "events": [_event("invoice_imported", operator, source_name=source_name)],
        }
        source_extension = Path(source_name).suffix.lower()
        if source_extension != ".xml":
            source_extension = ".xml"
        record["source_extension"] = source_extension
        record["saved_file_name"] = _saved_source_name(record, source_extension)
        if isinstance(record.get("batch_xml"), dict):
            record["batch_xml"]["attached_at"] = created_at
            record["batch_xml"]["attached_by"] = operator
            record["batch_xml"]["saved_file_name"] = record["saved_file_name"]
        invoice_dir = _invoice_dir(code)
        invoice_dir.mkdir(parents=True, exist_ok=False)
        _atomic_write_bytes(invoice_dir / record["saved_file_name"], source_data)
        _atomic_write_json(path, record)
        return record


def load_invoice(code: str) -> dict | None:
    try:
        path = _record_path(code)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def list_invoices() -> list[dict]:
    records: list[dict] = []
    root = _runtime_dir / "invoices"
    if not root.exists():
        return records
    for path in root.glob("*/invoice.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(value, dict):
            records.append(value)
    return sorted(records, key=lambda row: str(row.get("created_at", "")), reverse=True)


def record_open(code: str, operator: str) -> dict:
    return update_invoice(code, "invoice_opened", operator)


def close_invoice(code: str, operator: str) -> dict:
    return update_invoice(code, "invoice_closed", operator, status="closed", close=True)


def reopen_invoice(code: str, operator: str) -> dict:
    return update_invoice(code, "invoice_reopened", operator, status="opened", reopen=True)


def record_scan_failure(code: str, operator: str, message: str, reason: str = "camera_failure") -> tuple[dict, dict]:
    """Persist a camera/API failure in both singular history and failed reads."""
    clean_operator = str(operator or "").strip()
    if not clean_operator:
        raise ValueError("Az azonosítás kötelező.")
    with _LOCK:
        record = load_invoice(code)
        if record is None:
            raise FileNotFoundError("A számla nem található.")
        result = {
            "time": _now(),
            "user": clean_operator,
            "icn": "",
            "quantity": 0,
            "result": "failed",
            "message": str(message),
        }
        record.setdefault("scan_history", []).append(result)
        record.setdefault("failed_reads", []).append(result)
        record.setdefault("events", []).append(_event("icn_scan_failed", clean_operator, reason=reason))
        _atomic_write_json(_record_path(code), record)
        return record, result


def attach_batch_xml(code: str, batch_data: dict, xml_data: bytes, operator: str) -> dict:
    """Attach parsed batch lines and their ICNs to an opened invoice."""
    clean_operator = str(operator or "").strip()
    if not clean_operator:
        raise ValueError("Az azonosítás kötelező.")
    with _LOCK:
        record = load_invoice(code)
        if record is None:
            raise FileNotFoundError("A számla nem található.")
        if record.get("status") != "opened":
            raise ValueError("Lezárt számlához nem csatolható batch XML.")
        xml_invoice = re.sub(r"\D", "", str(batch_data.get("invoice_number", "")))
        record_invoice = re.sub(r"\D", "", str(record.get("invoice_code", "")))
        if not xml_invoice or not record_invoice.endswith(xml_invoice):
            raise ValueError(
                f"Az XML számlaszáma ({batch_data.get('invoice_number', '')}) nem egyezik a megnyitott számlával ({record.get('invoice_code', '')})."
            )
        item_lookup: dict[tuple[str, str], int] = {}
        for index, item in enumerate(record.get("items", [])):
            item_lookup[(str(item.get("batch_id", "")), str(item.get("kod", "")))] = index
        icn_index: dict[str, int] = {}
        unmatched: list[dict] = []
        matched_lines = 0
        for xml_line in batch_data.get("lines", []):
            key = (str(xml_line.get("batch_id", "")), str(xml_line.get("kod", "")))
            item_index = item_lookup.get(key)
            if item_index is None:
                unmatched.append(xml_line)
                continue
            item = record["items"][item_index]
            item["available_icns"] = list(xml_line.get("icns", []))
            item["xml_quantity"] = int(xml_line.get("quantity", 0) or 0)
            item["xml_icn_count"] = len(item["available_icns"])
            item["xml_line_no"] = str(xml_line.get("line_no", ""))
            for icn in item["available_icns"]:
                if icn in icn_index:
                    raise ValueError(f"Az ICN több számlatételhez tartozik: {icn}")
                icn_index[icn] = item_index
            matched_lines += 1
        record["icn_index"] = icn_index
        record["batch_xml"] = {
            "invoice_number": batch_data.get("invoice_number", ""),
            "attached_at": _now(),
            "attached_by": clean_operator,
            "line_count": len(batch_data.get("lines", [])),
            "matched_line_count": matched_lines,
            "unmatched_lines": unmatched,
            "icn_count": len(icn_index),
        }
        xml_name = f"{Path(str(record.get('saved_file_name', 'invoice.xml'))).stem}_batch.xml"
        _atomic_write_bytes(_invoice_dir(code) / xml_name, xml_data)
        record["batch_xml"]["saved_file_name"] = xml_name
        record.setdefault("events", []).append(
            _event("batch_xml_attached", clean_operator, matched_lines=matched_lines, unmatched_lines=len(unmatched), icn_count=len(icn_index))
        )
        _atomic_write_json(_record_path(code), record)
        return record


def scan_invoice_icn(code: str, icn: str, quantity: object, operator: str) -> tuple[dict, dict]:
    """Apply one ICN read and persist a clear success/failure audit result."""
    clean_operator = str(operator or "").strip()
    clean_icn = re.sub(r"\s+", "", str(icn or ""))
    if not clean_operator:
        raise ValueError("Az azonosítás kötelező.")
    with _LOCK:
        record = load_invoice(code)
        if record is None:
            raise FileNotFoundError("A számla nem található.")
        now = _now()
        try:
            clean_quantity = int(str(quantity or "1"))
        except ValueError:
            clean_quantity = 0

        def save_failure(message: str, reason: str) -> tuple[dict, dict]:
            result = {"time": now, "user": clean_operator, "icn": clean_icn, "quantity": clean_quantity, "result": "failed", "message": message}
            record.setdefault("scan_history", []).append(result)
            record.setdefault("failed_reads", []).append(result)
            record.setdefault("events", []).append(_event("icn_scan_failed", clean_operator, icn=clean_icn, reason=reason))
            _atomic_write_json(_record_path(code), record)
            return record, result

        if not re.fullmatch(r"\d{4,30}", clean_icn):
            return save_failure("Sikertelen beolvasás: az ICN formátuma érvénytelen.", "invalid_icn")
        if clean_quantity < 1 or clean_quantity > 10000:
            return save_failure("Sikertelen beolvasás: a darabszám érvénytelen.", "invalid_quantity")
        if record.get("status") != "opened":
            return save_failure("Sikertelen beolvasás: a számla le van zárva.", "invoice_closed")
        item_index = record.get("icn_index", {}).get(clean_icn)
        history = record.setdefault("scan_history", [])
        if item_index is None:
            return save_failure("Sikertelen beolvasás: az ICN nem szerepel a számlához csatolt batch XML-ben.", "not_in_invoice")
        scanned_icns = record.setdefault("scanned_icns", {})
        already_scanned = clean_icn in scanned_icns or any(
            isinstance(entry, dict)
            and str(entry.get("icn", "")) == clean_icn
            and str(entry.get("result", "")) in {"success", "warning"}
            for entry in history
        )
        if already_scanned:
            return save_failure(
                "Sikertelen beolvasás: ezt az ICN-t már korábban beolvasták, ezért a darabszám nem változott.",
                "duplicate_icn",
            )
        item = record["items"][int(item_index)]
        if item.get("missing_in_our_system"):
            return save_failure("Sikertelen beolvasás: a képzett saját kód nem található a saját rendszerben.", "missing_our_code")
        counted = int(item.get("counted_qty", 0) or 0) + clean_quantity
        expected = int(item.get("expected_qty", 0) or 0)
        item["counted_qty"] = counted
        item["read_at"] = now
        item["read_by"] = clean_operator
        item.setdefault("icns_read", []).append({"icn": clean_icn, "quantity": clean_quantity, "time": now, "user": clean_operator})
        warning = counted > expected
        message = "Sikeres beolvasás. Figyelem: a darabszám meghaladja a rendelt mennyiséget." if warning else "Sikeres beolvasás."
        result = {"time": now, "user": clean_operator, "icn": clean_icn, "quantity": clean_quantity, "result": "warning" if warning else "success", "message": message}
        history.append(result)
        scanned_icns[clean_icn] = {"time": now, "user": clean_operator, "quantity": clean_quantity}
        record.setdefault("events", []).append(_event("icn_scanned", clean_operator, icn=clean_icn, quantity=clean_quantity, warning=warning))
        _atomic_write_json(_record_path(code), record)
        return record, result


def update_invoice(
    code: str,
    action: str,
    operator: str,
    *,
    status: str | None = None,
    close: bool = False,
    reopen: bool = False,
) -> dict:
    clean_operator = str(operator or "").strip()
    if not clean_operator:
        raise ValueError("Az azonosítás kötelező.")
    with _LOCK:
        record = load_invoice(code)
        if record is None:
            raise FileNotFoundError("A számla nem található.")
        if close and record.get("status") == "closed":
            raise ValueError("A számla már le van zárva.")
        if reopen and record.get("status") != "closed":
            raise ValueError("Csak lezárt számla nyitható újra.")
        if status:
            record["status"] = status
        if close:
            record["closed_at"] = _now()
            record["closed_by"] = clean_operator
        if reopen:
            record["closed_at"] = ""
            record["closed_by"] = ""
        events = record.setdefault("events", [])
        if not isinstance(events, list):
            events = []
            record["events"] = events
        events.append(_event(action, clean_operator))
        old_source_path = _find_saved_source(record)
        new_source_name = _saved_source_name(record)
        if old_source_path is not None and old_source_path.name != new_source_name:
            new_source_path = old_source_path.with_name(new_source_name)
            if new_source_path.exists():
                raise FileExistsError(f"A cél forrásfájl már létezik: {new_source_name}")
            os.replace(old_source_path, new_source_path)
        record["saved_file_name"] = new_source_name
        if isinstance(record.get("batch_xml"), dict):
            record["batch_xml"]["saved_file_name"] = new_source_name
        _atomic_write_json(_record_path(code), record)
        return record
