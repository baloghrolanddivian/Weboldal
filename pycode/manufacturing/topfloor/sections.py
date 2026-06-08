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
    "Szerelveny_dobozolas.xml",
    "Topfloor.xml",
    "Anyagraktar.xml",
    "Anyagrakt\u00e1r.xml",
    "Anyagraktar_topfloor.xml",
)
TOPFLOOR_VENCODE_ABBREVIATIONS: dict[str, str] = {
    # TODO: Add manually approved venCode abbreviations here.
}


def _manufacturing_topfloor_document(bundle: dict, production_number: str) -> dict:
    """Build the Topfloor operation document from the shipment XML."""
    return _manufacturing_topfloor_document_from_bundles([(bundle, production_number)])


def _manufacturing_topfloor_document_from_bundles(bundles: list[tuple[dict, str]]) -> dict:
    """Build the Topfloor operation document from multiple production XML folders."""
    xml_paths: list[Path] = []
    for bundle, _production_number in bundles:
        xml_path = _topfloor_xml_path(bundle)
        if xml_path is not None:
            xml_paths.append(xml_path)
    if not xml_paths:
        return _topfloor_empty_document("Az Anyagraktár XML még nem található.")

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for xml_path in xml_paths:
        try:
            rows.extend(_topfloor_xml_rows(xml_path))
        except Exception as exc:
            errors.append(f"{xml_path.name}: {exc}")
    if errors and not rows:
        return _topfloor_empty_document(f"Az Anyagraktár XML feldolgozása nem sikerült: {'; '.join(errors)}")
    rows = _topfloor_deduplicate_rows(rows)
    source_xml_path = xml_paths[0]
    source_label = (
        f"Beolvasva: {source_xml_path.name}"
        if len(xml_paths) == 1
        else f"Beolvasva: {len(xml_paths)} Anyagraktár XML"
    )

    if not rows:
        return _topfloor_empty_document("Az Anyagraktár XML-ben nincs megjeleníthető elem.", xml_path=source_xml_path)

    box_registry = _topfloor_category_box_registry()
    shipment_ids = sorted(
        {row["shipmentID"] for row in rows if row["shipmentID"]},
        key=_topfloor_id_sort_key,
        reverse=True,
    )
    shipment_set = set(shipment_ids)
    rows = [row for row in rows if row["shipmentID"] in shipment_set]

    shipment_views: list[dict] = []
    row_count = 0
    all_sections: list[dict] = []
    for shipment_id in shipment_ids:
        shipment_rows = [row for row in rows if row["shipmentID"] == shipment_id]
        sections = _topfloor_category_sections(shipment_id, shipment_rows, box_registry)
        if not sections:
            continue
        shipment_views.append(
            {
                "key": f"shipment::{shipment_id}",
                "label": _topfloor_shipment_buyer_label(shipment_rows),
                "count": sum(len(section.get("rows", [])) for section in sections),
            }
        )
        row_count += sum(len(section.get("rows", [])) for section in sections)
        all_sections.extend(sections)

    return {
        "key": TOPFLOOR_OPERATION_KEY,
        "label": TOPFLOOR_OPERATION_LABEL,
        "sourceType": "XML",
        "sourceLabel": source_label,
        "file_name": source_xml_path.name,
        "sections": all_sections,
        "row_count": row_count,
        "placeholderMessage": "Az Anyagraktár XML-ben nincs megjeleníthető elem.",
        "specialViews": [],
        "topfloorShipmentViews": shipment_views,
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
        "topfloorShipmentViews": [],
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


def _topfloor_deduplicate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove repeated XML rows when the same shipment appears in multiple folders."""
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("shipmentID", "") or "").strip(),
            str(row.get("productionID", "") or "").strip(),
            str(row.get("orderNumber", "") or "").strip(),
            str(row.get("barcode", "") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


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
                "location": _topfloor_location(values),
                "orderNumber": _topfloor_value(values, "orderNumber"),
                "buyerID": _topfloor_value(values, "buyerID"),
                "shipmentID": shipment_id,
                "productionID": _topfloor_value(values, "productionID"),
                "description": _topfloor_value(values, "description"),
                "quantity": _topfloor_value(values, "quantity") or "1",
                "barcode": barcode,
                "venCode": _topfloor_value(values, "venCode"),
                "prdInfo1": _topfloor_value(values, "prdInfo1"),
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
            "legacyBoxCategoryKey": _topfloor_legacy_category_key(row),
            "defaultBoxDescription": _topfloor_default_box_description(row),
        }

    sections: list[dict] = []
    for group_key, category_rows in sorted(grouped.items(), key=lambda item: _topfloor_category_sort_key(category_meta[item[0]])):
        meta = category_meta[group_key]
        box_category_key = meta["boxCategoryKey"]
        box = box_registry.get(box_category_key) or box_registry.get(meta["legacyBoxCategoryKey"], {})
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
                    "boxDescription": str(box.get("conDescription", "") or ""),
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
        "vencompanyname": "buyer",
        "location": "location",
        "addcity": "addCity",
        "addaddress1": "addAddress1",
        "ordernumber": "orderNumber",
        "ordorderno": "orderNumber",
        "order": "orderNumber",
        "rendelesszam": "orderNumber",
        "buyerid": "buyerID",
        "rendkod": "buyerID",
        "shipmentid": "shipmentID",
        "shpid": "shipmentID",
        "productionid": "productionID",
        "prdid": "productionID",
        "description": "description",
        "leiras": "description",
        "quantity": "quantity",
        "conquantity": "quantity",
        "qty": "quantity",
        "barcode": "barcode",
        "vencode": "venCode",
        "prdinfo1": "prdInfo1",
        "prdinfo01": "prdInfo1",
    }
    return aliases.get(text, "")


def _topfloor_value(values: dict[str, str], key: str) -> str:
    """Return a stripped XML value."""
    return str(values.get(key, "") or "").strip()


def _topfloor_location(values: dict[str, str]) -> str:
    """Return the Topfloor location from city and address fields."""
    explicit = _topfloor_value(values, "location")
    if explicit:
        return explicit
    return ", ".join(part for part in (_topfloor_value(values, "addCity"), _topfloor_value(values, "addAddress1")) if part)


def _topfloor_default_box_description(row: dict[str, str]) -> str:
    """Return the editable default Topfloor box description."""
    ven_code = str(row.get("venCode", "") or "").strip()
    ven_code = TOPFLOOR_VENCODE_ABBREVIATIONS.get(ven_code, ven_code)
    description = " ".join(
        part
        for part in (
            ven_code,
            str(row.get("location", "") or "").split(",", 1)[0].strip(),
            _topfloor_box_prd_info(row.get("prdInfo1", "")),
        )
        if part
    )
    return _topfloor_strip_trailing_matt(description)


def _topfloor_box_prd_info(value: object) -> str:
    """Trim prdInfo text to the date suffix used for box descriptions."""
    text = str(value or "").strip()
    matches = re.findall(r"\b(\d{2}\.\d{2})\.?", text)
    if matches:
        return f"{matches[-1]}."
    return text


def _topfloor_strip_trailing_matt(value: object) -> str:
    """Remove the trailing Matt marker from box descriptions."""
    return re.sub(r"\s+\bMatt\b\s*$", "", str(value or "").strip(), flags=re.IGNORECASE)


def _topfloor_shipment_buyer_label(rows: list[dict[str, str]]) -> str:
    """Return the buyer label shown for a shipment tab."""
    buyers = {
        str(row.get("buyer", "") or "").strip()
        for row in rows
        if str(row.get("buyer", "") or "").strip()
    }
    if len(buyers) == 1:
        return next(iter(buyers))
    return "Nagyaut\u00f3"


def _topfloor_category_key(row: dict[str, str]) -> str:
    """Return the persisted Topfloor box/category key."""
    buyer_id = str(row.get("buyerID", "") or "").strip() or "Nincs"
    return f"{row['shipmentID']}::{row['productionID']}::{row['orderNumber']}::{buyer_id}"


def _topfloor_legacy_category_key(row: dict[str, str]) -> str:
    """Return the pre-buyerID Topfloor box/category key for compatibility reads."""
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
    return " · ".join(
        part
        for part in (
            meta.get("productionID", ""),
            meta.get("buyer", ""),
            meta.get("buyerID", ""),
            meta.get("orderNumber", ""),
            meta.get("location", ""),
        )
        if part
    ) or "Kateg\u00f3ria"


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
    result: dict[str, dict] = {}
    for state_path in sorted((runtime_dir() / "topfloor").glob("*/state.json")):
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        shipment_id = state_path.parent.name
        result.update(
            {
                str(key): value
                for key, value in payload.items()
                if isinstance(value, dict) and str(key).startswith(f"{shipment_id}::")
            }
        )
    return result
