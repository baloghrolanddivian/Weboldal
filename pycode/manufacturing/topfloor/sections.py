"""Operation-specific section builders for Topfloor manufacturing views."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from ..config import runtime_dir


TOPFLOOR_OPERATION_KEY = "topfloor"
TOPFLOOR_OPERATION_LABEL = "Anyagrakt\u00e1r"
TOPFLOOR_XML_NAMES = (
    "Topfloor.xml",
    "Anyagraktar.xml",
    "Anyagrakt\u00e1r.xml",
    "Anyagraktar_topfloor.xml",
)
TOPFLOOR_MAX_SHIPMENTS = 20


def _manufacturing_topfloor_document(bundle: dict, production_number: str) -> dict:
    """Build the Topfloor operation document from the shipment XML."""
    xml_path = _topfloor_xml_path(bundle)
    if xml_path is None:
        return _topfloor_empty_document("Az Anyagrakt\u00e1r XML m\u00e9g nem tal\u00e1lhat\u00f3.")

    try:
        rows = _topfloor_xml_rows(xml_path)
    except Exception as exc:
        return _topfloor_empty_document(f"Az Anyagrakt\u00e1r XML feldolgoz\u00e1sa nem siker\u00fclt: {exc}")

    if not rows:
        return _topfloor_empty_document("Az Anyagrakt\u00e1r XML-ben nincs megjelen\u00edthet\u0151 elem.", xml_path=xml_path)

    box_registry = _topfloor_category_box_registry()
    shipment_ids = sorted(
        {row["shipmentID"] for row in rows if row["shipmentID"]},
        key=_topfloor_id_sort_key,
        reverse=True,
    )[:TOPFLOOR_MAX_SHIPMENTS]
    shipment_set = set(shipment_ids)
    rows = [row for row in rows if row["shipmentID"] in shipment_set]

    special_views: list[dict] = []
    row_count = 0
    all_sections: list[dict] = []
    for shipment_id in shipment_ids:
        shipment_rows = [row for row in rows if row["shipmentID"] == shipment_id]
        sections = _topfloor_category_sections(shipment_id, shipment_rows, box_registry)
        if not sections:
            continue
        special_views.append(
            {
                "key": f"shipment::{shipment_id}",
                "label": f"Sz\u00e1ll\u00edtm\u00e1ny {shipment_id}",
                "count": sum(len(section.get("rows", [])) for section in sections),
                "sections": sections,
            }
        )
        row_count += sum(len(section.get("rows", [])) for section in sections)
        all_sections.extend(sections)

    return {
        "key": TOPFLOOR_OPERATION_KEY,
        "label": TOPFLOOR_OPERATION_LABEL,
        "sourceType": "XML",
        "sourceLabel": f"Beolvasva: {xml_path.name}",
        "file_name": xml_path.name,
        "sections": all_sections,
        "row_count": row_count,
        "placeholderMessage": "Az Anyagrakt\u00e1r XML-ben nincs megjelen\u00edthet\u0151 elem.",
        "specialViews": special_views,
        "hideBarcodeColumn": False,
        "allowSplit": False,
        "singleColumnOverview": True,
        "usesSearch": True,
    }


def _topfloor_empty_document(message: str, *, xml_path: Path | None = None) -> dict:
    """Return an empty Topfloor document."""
    return {
        "key": TOPFLOOR_OPERATION_KEY,
        "label": TOPFLOOR_OPERATION_LABEL,
        "sourceType": "XML" if xml_path else "Nincs XML",
        "sourceLabel": f"Beolvasva: {xml_path.name}" if xml_path else "Anyagrakt\u00e1r XML nincs beolvasva",
        "file_name": xml_path.name if xml_path else "",
        "sections": [],
        "row_count": 0,
        "placeholderMessage": message,
        "specialViews": [],
        "hideBarcodeColumn": False,
        "allowSplit": False,
        "singleColumnOverview": True,
        "usesSearch": True,
    }


def _topfloor_xml_path(bundle: dict) -> Path | None:
    """Find the Topfloor XML in the production folder."""
    folder = Path(str(bundle.get("folder", "") or "").strip())
    if not folder.exists():
        return None
    lower_names = {name.lower(): name for name in TOPFLOOR_XML_NAMES}
    try:
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() != ".xml":
                continue
            if path.name.lower() in lower_names:
                return path
            folded_name = _topfloor_fold(path.stem)
            if folded_name in {"topfloor", "anyagraktar", "anyagraktar topfloor"}:
                return path
    except OSError:
        return None
    return None


def _topfloor_xml_rows(xml_path: Path) -> list[dict[str, str]]:
    """Read Topfloor XML elements into normalized row dictionaries."""
    root = ET.parse(xml_path).getroot()
    result: list[dict[str, str]] = []
    for index, element in enumerate(root.iter(), start=1):
        values = _topfloor_element_values(element)
        if not values:
            continue
        barcode = _topfloor_value(values, "barcode")
        shipment_id = _topfloor_value(values, "shipmentID")
        if not barcode or not shipment_id:
            continue
        result.append(
            {
                "buyer": _topfloor_value(values, "buyer"),
                "location": _topfloor_value(values, "location"),
                "orderNumber": _topfloor_value(values, "orderNumber"),
                "buyerID": _topfloor_value(values, "buyerID"),
                "shipmentID": shipment_id,
                "productionID": _topfloor_value(values, "productionID"),
                "description": _topfloor_value(values, "description"),
                "quantity": _topfloor_value(values, "quantity") or "1",
                "barcode": barcode,
                "_index": str(index),
            }
        )
    return result


def _topfloor_category_sections(shipment_id: str, rows: list[dict[str, str]], box_registry: dict[str, dict]) -> list[dict]:
    """Group one shipment by Topfloor category fields."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    category_meta: dict[str, dict[str, str]] = {}
    for row in rows:
        group_key = _topfloor_group_key(row)
        grouped[group_key].append(row)
        category_meta[group_key] = {
            "shipmentID": shipment_id,
            "productionID": row["productionID"],
            "orderNumber": row["orderNumber"],
            "buyer": row["buyer"],
            "location": row["location"],
            "buyerID": row["buyerID"],
            "boxCategoryKey": _topfloor_category_key(row),
        }

    sections: list[dict] = []
    for group_key, category_rows in sorted(grouped.items(), key=lambda item: _topfloor_category_sort_key(category_meta[item[0]])):
        meta = category_meta[group_key]
        box_category_key = meta["boxCategoryKey"]
        box = box_registry.get(box_category_key, {})
        section_rows = [_topfloor_view_row(row, group_key) for row in category_rows]
        sections.append(
            {
                "key": f"topfloor::{_topfloor_local_slug(group_key)}",
                "label": _topfloor_category_label(meta),
                "rows": section_rows,
                "topfloorCategory": {
                    **meta,
                    "categoryKey": box_category_key,
                    "groupKey": group_key,
                    "boxId": str(box.get("conId", "") or ""),
                    "boxOpen": bool(box.get("open")),
                    "createEnabled": not bool(box.get("conId")),
                    "openEnabled": bool(box.get("conId")) and not bool(box.get("open")),
                    "closeEnabled": bool(box.get("conId")) and bool(box.get("open")),
                },
            }
        )
    return sections


def _topfloor_view_row(row: dict[str, str], category_key: str) -> dict:
    """Convert a Topfloor XML row into the manufacturing row shape."""
    shipment_id = row["shipmentID"]
    barcode = row["barcode"]
    state_key = f"topfloor::{shipment_id}::{barcode}::0"
    row_id = _topfloor_row_id(row, category_key)
    return {
        "row_id": row_id,
        "state_key": state_key,
        "state_storage_key": state_key,
        "production_number": shipment_id,
        "doc_key": TOPFLOOR_OPERATION_KEY,
        "section_key": _topfloor_local_slug(category_key),
        "section_label": _topfloor_category_label(row),
        "topfloorCategoryKey": category_key,
        "columnLayout": "topfloor",
        "shipmentID": shipment_id,
        "productionID": row["productionID"],
        "orderNumber": row["orderNumber"],
        "buyer": row["buyer"],
        "location": row["location"],
        "buyerID": row["buyerID"],
        "name": row["description"] or "Anyagrakt\u00e1r t\u00e9tel",
        "detail": "",
        "hideSubtitle": True,
        "size": "-",
        "color": "-",
        "edge": "-",
        "quantity": _topfloor_quantity(row["quantity"]),
        "code": barcode,
    }


def _topfloor_element_values(element: ET.Element) -> dict[str, str]:
    """Return normalized field values from element attributes and direct children."""
    values: dict[str, str] = {}
    for key, value in element.attrib.items():
        clean_key = _topfloor_field_key(key)
        if clean_key:
            values[clean_key] = str(value or "").strip()
    for child in list(element):
        clean_key = _topfloor_field_key(child.tag)
        if not clean_key:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            values[clean_key] = text
    return values


def _topfloor_field_key(value: object) -> str:
    """Normalize XML field names to canonical Topfloor keys."""
    text = re.sub(r"[^a-z0-9]+", "", _topfloor_fold(str(value or "").split("}", 1)[-1]))
    aliases = {
        "buyer": "buyer",
        "location": "location",
        "ordernumber": "orderNumber",
        "order": "orderNumber",
        "rendelesszam": "orderNumber",
        "buyerid": "buyerID",
        "shipmentid": "shipmentID",
        "productionid": "productionID",
        "description": "description",
        "quantity": "quantity",
        "qty": "quantity",
        "barcode": "barcode",
    }
    return aliases.get(text, "")


def _topfloor_value(values: dict[str, str], key: str) -> str:
    """Return a stripped XML value."""
    return str(values.get(key, "") or "").strip()


def _topfloor_category_key(row: dict[str, str]) -> str:
    """Return the persisted Topfloor box/category key."""
    return f"{row['shipmentID']}::{row['productionID']}::{row['orderNumber']}"


def _topfloor_group_key(row: dict[str, str]) -> str:
    """Return the full Topfloor grouping key."""
    return "::".join(
        [
            row["shipmentID"],
            row["productionID"],
            row["buyer"],
            row["location"],
            row["buyerID"],
            row["orderNumber"],
        ]
    )


def _topfloor_category_label(meta: dict[str, str]) -> str:
    """Return the visible Topfloor category label."""
    return " · ".join(part for part in (meta.get("buyer", ""), meta.get("location", ""), meta.get("buyerID", "")) if part) or "Kateg\u00f3ria"


def _topfloor_row_id(row: dict[str, str], category_key: str) -> str:
    """Build a stable row id for Topfloor rows."""
    payload = "|".join(
        [
            category_key,
            row.get("barcode", ""),
            row.get("description", ""),
            row.get("quantity", ""),
            row.get("_index", ""),
        ]
    )
    return f"topfloor-{hashlib.sha1(payload.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _topfloor_quantity(value: object) -> int:
    """Parse XML quantity into a positive integer."""
    try:
        return max(1, int(float(str(value or "1").replace(",", "."))))
    except ValueError:
        return 1


def _topfloor_id_sort_key(value: object) -> tuple[int, str]:
    """Sort shipment IDs numerically when possible."""
    text = str(value or "").strip()
    match = re.search(r"\d+", text)
    return (int(match.group(0)) if match else -1, text)


def _topfloor_category_sort_key(meta: dict[str, str]) -> tuple[str, str, str, str]:
    """Sort categories by their visible and identifying fields."""
    return (
        _topfloor_fold(meta.get("buyer", "")),
        _topfloor_fold(meta.get("location", "")),
        _topfloor_fold(meta.get("buyerID", "")),
        _topfloor_fold(meta.get("orderNumber", "")),
    )


def _topfloor_local_slug(value: str) -> str:
    """Return a local slug."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", _topfloor_fold(value))
    return cleaned.strip("-") or "topfloor"


def _topfloor_fold(value: object) -> str:
    """Lowercase and remove accents for matching/sorting."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.strip().lower())


def _topfloor_category_box_registry() -> dict[str, dict]:
    """Read saved Topfloor category-to-box assignments."""
    path = runtime_dir() / "dobozok" / "categories.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}
