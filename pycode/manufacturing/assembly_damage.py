"""Persistent component replacement requests from the assembly workstation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import uuid

from .base.config import runtime_dir
from .state_store import atomic_write_json, locked_state_file

DAMAGE_VIEW_KEY = "assembly-damaged"


def bom_snapshot(row: object) -> dict:
    """Compare API and browser rows without numeric/string quantity differences."""
    if not isinstance(row, dict):
        raise ValueError("Hiányzó darabjegyzéktétel.")
    part_number = str(row.get("part_number") or "").strip()
    description = str(row.get("description") or "").strip()
    try:
        quantity = Decimal(str(row.get("quantity")).replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Érvénytelen tételmennyiség.") from exc
    if (not part_number or len(part_number) > 500 or len(description) > 2000
            or not quantity.is_finite() or quantity < 0 or quantity.adjusted() > 12 or quantity.as_tuple().exponent < -12):
        raise ValueError("Érvénytelen darabjegyzéktétel.")
    return {"part_number": part_number, "description": description, "quantity": format(quantity.normalize(), "f")}


def _load() -> dict:
    path = runtime_dir() / "assembly-damaged.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"reports": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("reports"), dict):
        raise ValueError("A sérült alkatrészek nyilvántartása nem olvasható.")
    return payload


def pending_damage_reports() -> list[dict]:
    with locked_state_file():
        return [dict(report) for report in _load()["reports"].values() if report.get("status") == "open"]


def damaged_bom_indexes(production_number: str, barcode: str, rows: list) -> list[int]:
    reports = pending_damage_reports()
    indexes = []
    for index, row in enumerate(rows):
        try:
            snapshot = bom_snapshot(row)
        except ValueError:
            continue
        if any(report["production_number"] == production_number and report["barcode"] == barcode
               and report["bom_index"] == index and report["item"] == snapshot for report in reports):
            indexes.append(index)
    return indexes


def record_bom_damage(production_number: str, barcode: str, index: int, row: dict, *, request_id: str, reported_by: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,20}", production_number) or int(production_number) <= 0:
        raise ValueError("Érvénytelen gyártási azonosító.")
    if not barcode or len(barcode) > 160 or type(index) is not int or index < 0:
        raise ValueError("Érvénytelen beolvasott tétel.")
    try:
        request_id = str(uuid.UUID(request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Érvénytelen bejelentési azonosító.") from exc
    snapshot = bom_snapshot(row)
    with locked_state_file():
        payload = _load()
        for report in payload["reports"].values():
            same_item = report["production_number"] == production_number and report["barcode"] == barcode and report["bom_index"] == index and report["item"] == snapshot
            if request_id in report.get("request_ids", [report["request_id"]]):
                if not same_item:
                    raise ValueError("A bejelentési azonosító másik tételhez tartozik.")
                return dict(report)
        for report in payload["reports"].values():
            same_item = report["production_number"] == production_number and report["barcode"] == barcode and report["bom_index"] == index and report["item"] == snapshot
            if same_item and report["status"] == "open":
                report.setdefault("request_ids", [report["request_id"]]).append(request_id)
                atomic_write_json(runtime_dir() / "assembly-damaged.json", payload)
                return dict(report)
        report_id = str(uuid.uuid4())
        report = {"id": report_id, "request_id": request_id, "request_ids": [request_id], "production_number": production_number,
                  "barcode": barcode, "bom_index": index, "item": snapshot, "status": "open",
                  "reported_at": datetime.now().astimezone().isoformat(timespec="seconds"), "reported_by": reported_by}
        payload["reports"][report_id] = report
        atomic_write_json(runtime_dir() / "assembly-damaged.json", payload)
        return dict(report)


def complete_damage_report(report_id: object, *, completed_by: str) -> dict:
    with locked_state_file():
        payload = _load()
        report = payload["reports"].get(str(report_id))
        if report is None:
            raise ValueError("A sérült alkatrész bejelentése nem található.")
        if report["status"] != "prepared":
            report.update(status="prepared", completed_by=completed_by, completed_at=datetime.now().astimezone().isoformat(timespec="seconds"))
            atomic_write_json(runtime_dir() / "assembly-damaged.json", payload)
        return dict(report)


def damage_special_view() -> dict:
    sections = {}
    for report in sorted(pending_damage_reports(), key=lambda report: (report["production_number"], report["reported_at"], report["id"])):
        number = report["production_number"]
        section = sections.setdefault(number, {"key": f"assembly-damaged::{number}", "label": f"Gyártás {number} · Összekészítő", "rows": []})
        item = report["item"]
        section["rows"].append({"row_id": report["id"], "damage_id": report["id"], "production_number": number,
                                "name": item["part_number"], "part_number": item["part_number"], "detail": item["description"],
                                "quantity": item["quantity"], "code": report["barcode"], "reported_at": report["reported_at"],
                                "reported_by": report["reported_by"], "doc_key": "osszekeszito"})
    return {"key": DAMAGE_VIEW_KEY, "label": "Sérült alkatrészek", "count": sum(len(section["rows"]) for section in sections.values()),
            "sections": list(sections.values()), "excludeFromCompletion": True}
