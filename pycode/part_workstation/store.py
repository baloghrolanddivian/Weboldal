"""Request-local scan results for the browser-owned tablet workstation."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .lookup import lookup_scan
from .production_xml import empty_xml_metadata, lookup_xml_item, normalized_xml_metadata

MAX_BARCODE_LENGTH = 160


def empty_state() -> dict:
    """Return the workstation state before a barcode is scanned."""
    return {
        "barcode": "",
        "scanned_at": "",
        "lookup_status": "waiting_for_scan",
        "error_message": "",
        "item": {
            "part_number": "",
            "description": "",
            "cabinet": "",
            "handing": "",
            "front": "",
            "legs": "",
            "worktop": "",
            "filler_width": "",
            "handle_drilling": "",
            "dimensions": "",
            "material": "",
            "color": "",
            "production_number": "",
            "order_number": "",
        },
        "model": None,
        "bom": [],
        "production_xml": empty_xml_metadata(),
    }


def register_scan(barcode: str) -> dict:
    """Resolve one scan without reading or writing shared workstation state."""
    clean_barcode = _clean_barcode(barcode)
    if not clean_barcode:
        raise ValueError("A vonalkód nem lehet üres.")
    if len(clean_barcode) > MAX_BARCODE_LENGTH:
        raise ValueError(f"A vonalkód legfeljebb {MAX_BARCODE_LENGTH} karakter lehet.")

    state = empty_state()
    state.update(
        {
            "barcode": clean_barcode,
            "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "lookup_status": "api_pending",
        }
    )
    lookup = lookup_scan(clean_barcode)
    state["bom"] = lookup["bom"]
    scan = lookup["scan"]
    state["production_xml"] = lookup_xml_item(
        scan.get("scan") or clean_barcode,
        production_number=lookup["production_number"],
        oln_id=scan.get("olnId"),
    )
    state["lookup_status"] = "ready"
    return _normalized_state(state)


def _clean_barcode(value: object) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()


def _normalized_state(payload: object) -> dict:
    result = empty_state()
    if not isinstance(payload, dict):
        return result
    result["barcode"] = _clean_barcode(payload.get("barcode", ""))[:MAX_BARCODE_LENGTH]
    result["scanned_at"] = str(payload.get("scanned_at", "") or "")[:64]
    status = str(payload.get("lookup_status", "") or "")
    result["lookup_status"] = status if status in {"waiting_for_scan", "api_pending", "ready", "error"} else "waiting_for_scan"
    result["error_message"] = str(payload.get("error_message", "") or "")[:2000]
    source_item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    for key in result["item"]:
        result["item"][key] = str(source_item.get(key, "") or "")[:500]
    result["model"] = payload.get("model") if isinstance(payload.get("model"), dict) else None
    source_bom = payload.get("bom") if isinstance(payload.get("bom"), list) else []
    result["bom"] = [row for row in source_bom if isinstance(row, dict)]
    result["production_xml"] = normalized_xml_metadata(payload.get("production_xml"))
    if result["production_xml"]["lookup_status"] == "ready":
        fields = result["production_xml"]["fields"]
        features = result["production_xml"]["features"]
        result["item"]["part_number"] = fields["pdCode"][:500]
        result["item"]["description"] = fields["pdvDescription"][:500]
        result["item"]["cabinet"] = " | ".join(filter(None, (fields["Korpusztipus"], fields["Korp_tip_nev"])))
        result["item"]["handing"] = features["J/B"] or features["Nyitási irány"]
        result["item"]["front"] = " | ".join(filter(None, (
            features["Front színe"] or features["Front szín felső"] or features["Keretléc szín"], features["Front típus"],
        )))
        result["item"]["color"] = fields["Korp_Szin"]
        result["item"]["legs"] = features["Láb típusa"]
        result["item"]["worktop"] = features["Munkalap szín"]
        result["item"]["filler_width"] = features["Hézagtakaró szélessége"]
        result["item"]["handle_drilling"] = features["Fogantyú furat"]
        dimensions = [_millimeters(features[name]) for name in ("Beép.mag.cm", "Beép.szél.cm", "Beép.mélys.cm")]
        result["item"]["dimensions"] = " × ".join(value or "—" for value in dimensions) + " mm" if any(dimensions) else ""
    return result


def _millimeters(value: str) -> str:
    """Convert an XML centimeter value without floating point rounding noise."""
    try:
        number = Decimal(value.strip().replace(",", ".")) * 10
    except InvalidOperation:
        return ""
    if not number.is_finite():
        return ""
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
