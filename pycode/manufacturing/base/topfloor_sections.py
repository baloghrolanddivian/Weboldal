"""Shared Topfloor section builder for all Manufacturing views."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from ..config import REPO_ROOT, runtime_dir


TOPFLOOR_OPERATION_KEY = "topfloor"
TOPFLOOR_OPERATION_LABEL = "Anyagrakt\u00e1r"
TOPFLOOR_XML_NAMES = (
    "Szerelveny_dobozolas.xml",
    "Topfloor.xml",
    "Anyagraktar.xml",
    "Anyagrakt\u00e1r.xml",
    "Anyagraktar_topfloor.xml",
)
TOPFLOOR_TRANSFER_XML_NAME = "Atraktarozas.xml"
TOPFLOOR_HETTICH_VIEW_KEY = "shipment::hettich"
TOPFLOOR_VENCODE_ABBREVIATIONS_PATH = REPO_ROOT / "data" / "venCode_Abrv"
_TOPFLOOR_VENCODE_ABBREVIATIONS: dict[str, str] | None = None
_TOPFLOOR_VENCODE_ABBREVIATIONS_MTIME_NS: int | None = None


def _manufacturing_topfloor_document(bundle: dict, production_number: str) -> dict:
    """Build the Topfloor operation document from the shipment XML."""
    return _manufacturing_topfloor_document_from_bundles([(bundle, production_number)])


def _manufacturing_topfloor_document_from_bundles(bundles: list[tuple[dict, str]]) -> dict:
    """Build the Topfloor operation document from multiple production XML folders."""
    xml_paths: list[Path] = []
    transfer_xml_paths: list[Path] = []
    for bundle, _production_number in bundles:
        xml_path = _topfloor_xml_path(bundle)
        if xml_path is not None:
            xml_paths.append(xml_path)
        transfer_xml_path = _topfloor_transfer_xml_path(bundle)
        if transfer_xml_path is not None:
            transfer_xml_paths.append(transfer_xml_path)
    if not xml_paths and not transfer_xml_paths:
        return _topfloor_empty_document("Az Anyagraktár XML még nem található.")

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for xml_path in xml_paths:
        try:
            rows.extend(_topfloor_xml_rows(xml_path))
        except Exception as exc:
            errors.append(f"{xml_path.name}: {exc}")
    if errors and not rows and not transfer_xml_paths:
        return _topfloor_empty_document(f"Az Anyagraktár XML feldolgozása nem sikerült: {'; '.join(errors)}")
    rows = _topfloor_deduplicate_rows(rows)
    hettich_rows = _topfloor_transfer_rows_from_paths(transfer_xml_paths)
    source_xml_path = xml_paths[0] if xml_paths else transfer_xml_paths[0]
    source_label = (
        f"Beolvasva: {source_xml_path.name}"
        if len(xml_paths) <= 1
        else f"Beolvasva: {len(xml_paths)} Anyagraktár XML"
    )

    if not rows and not hettich_rows:
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
        visible_rows = [
            row
            for section in sections
            for row in (section.get("rows", []) if isinstance(section, dict) else [])
            if isinstance(row, dict)
        ]
        shipment_views.append(
            {
                "key": f"shipment::{shipment_id}",
                "label": _topfloor_shipment_buyer_label(visible_rows),
                "count": len(sections),
            }
        )
        row_count += sum(len(section.get("rows", [])) for section in sections)
        all_sections.extend(sections)

    hettich_sections = _topfloor_hettich_sections(hettich_rows)
    if hettich_sections:
        shipment_views.insert(
            0,
            {
                "key": TOPFLOOR_HETTICH_VIEW_KEY,
                "label": "Hettich",
                "count": len(hettich_sections),
                "isHettich": True,
            },
        )
        row_count += sum(len(section.get("rows", [])) for section in hettich_sections)
        all_sections = [*hettich_sections, *all_sections]

    normal_section_count = len(all_sections) - len(hettich_sections)
    source_label = f"{normal_section_count} doboz" if normal_section_count else source_label
    if normal_section_count:
        shipment_views.insert(
            0,
            {
                "key": "shipment::__all__",
                "label": "\u00d6sszes",
                "count": normal_section_count,
            },
        )

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


def _topfloor_transfer_xml_path(bundle: dict) -> Path | None:
    """Find Atraktarozas.xml in one production folder."""
    folder = Path(str(bundle.get("folder", "") or "").strip())
    if not folder.exists():
        return None
    try:
        return next(
            (
                path
                for path in folder.iterdir()
                if path.is_file() and path.name.casefold() == TOPFLOOR_TRANSFER_XML_NAME.casefold()
            ),
            None,
        )
    except OSError:
        return None


def _topfloor_transfer_rows_from_paths(xml_paths: list[Path]) -> list[dict[str, object]]:
    """Read and deduplicate PA_FISH transfer rows from recent production folders."""
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for xml_path in xml_paths:
        try:
            root = ET.parse(xml_path).getroot()
        except Exception:
            continue
        for index, element in enumerate(root.iter(), start=1):
            values = {
                re.sub(r"[^a-z0-9]+", "", _topfloor_fold(str(child.tag).split("}", 1)[-1])): "".join(child.itertext()).strip()
                for child in list(element)
            }
            values.update(
                {
                    re.sub(r"[^a-z0-9]+", "", _topfloor_fold(str(key).split("}", 1)[-1])): str(value or "").strip()
                    for key, value in element.attrib.items()
                }
            )
            item_number = str(values.get("itmitemnumber", "") or "").strip()
            item_id = str(values.get("itmid", "") or "").strip()
            prd_id = str(values.get("prdid", "") or "").strip()
            quantity = _topfloor_transfer_integer_quantity(values.get("orireqqty", ""))
            uom_code = str(values.get("primaryuomcode", "") or "").strip()
            item_description = str(values.get("itmdescription", "") or "").strip()
            if not item_number.upper().startswith("PA_FISH") or not item_id or not prd_id or quantity is None or not uom_code:
                continue
            identity = (prd_id, item_id, item_number.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            result.append(
                {
                    "itmItemNumber": item_number,
                    "itmID": item_id,
                    "prdID": prd_id,
                    "oriReqQty": quantity,
                    "PrimaryUOMCode": uom_code,
                    "itmDescription": item_description,
                    "sourceFileStem": xml_path.stem,
                    "_index": str(index),
                }
            )
    return result


def _topfloor_transfer_integer_quantity(value: object) -> int | None:
    """Convert an Atraktarozas quantity to a non-negative whole number."""
    try:
        quantity = int(float(str(value or "").strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return quantity if quantity >= 0 else None


def _topfloor_hettich_sections(rows: list[dict[str, object]]) -> list[dict]:
    """Group Hettich transfer rows by prdID."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("prdID", "") or "").strip()].append(row)
    sections: list[dict] = []
    for prd_id in sorted(grouped, key=_topfloor_id_sort_key, reverse=True):
        section_rows: list[dict] = []
        for row in grouped[prd_id]:
            item_id = str(row.get("itmID", "") or "").strip()
            item_number = str(row.get("itmItemNumber", "") or "").strip()
            state_key = f"Atraktarozas::{prd_id}::{item_id}::0"
            row_hash = hashlib.sha1(f"{prd_id}|{item_id}|{item_number}".encode("utf-8")).hexdigest()[:16]
            section_rows.append(
                {
                    "row_id": f"hettich-{row_hash}",
                    "state_key": state_key,
                    "state_storage_key": state_key,
                    "production_number": prd_id,
                    "doc_key": TOPFLOOR_OPERATION_KEY,
                    "section_key": f"hettich-{_topfloor_local_slug(prd_id)}",
                    "section_label": f"prdID: {prd_id}",
                    "columnLayout": "topfloor",
                    "name": row.get("itmDescription", "") or item_number,
                    "detail": "",
                    "hideSubtitle": True,
                    "size": "-",
                    "color": "-",
                    "edge": "-",
                    "quantity": row["oriReqQty"],
                    "code": item_number,
                    "itmItemNumber": item_number,
                    "itmID": item_id,
                    "prdID": prd_id,
                    "oriReqQty": row["oriReqQty"],
                    "PrimaryUOMCode": row["PrimaryUOMCode"],
                    "itmDescription": row.get("itmDescription", ""),
                    "isHettichTransfer": True,
                }
            )
        sections.append(
            {
                "key": f"hettich::{_topfloor_local_slug(prd_id)}",
                "label": f"prdID: {prd_id}",
                "rows": section_rows,
                "hettichCategory": {"prdID": prd_id, "transferDone": False},
            }
        )
    return sections


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
                "childID": _topfloor_value(values, "childID"),
                "venCode": _topfloor_value(values, "venCode"),
                "prdInfo1": _topfloor_value(values, "prdInfo1"),
                "prdProdDate": _topfloor_value(values, "prdProdDate"),
                "orderType": _topfloor_value(values, "orderType"),
                "sourceFileStem": xml_path.stem,
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
            "orderType": row["orderType"],
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
                    "boxCreatedBy": str(box.get("createdBy", "") or "Err404").strip() or "Err404",
                    "boxDescription": str(box.get("conDescription", "") or ""),
                    "boxOpen": bool(box.get("open")),
                    "storageBoxIssued": bool(box.get("storageBoxIssued")),
                    "storageBoxName": str(box.get("storageBoxName", "") or ""),
                    "storageBoxCode": str(box.get("storageBoxCode", "") or ""),
                    "storageBoxId": str(box.get("storageBoxId", "") or ""),
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
    child_id = str(row.get("childID", "") or row.get("childId", "") or "0").strip() or "0"
    source_file_stem = str(row.get("sourceFileStem", "") or TOPFLOOR_OPERATION_KEY).strip()
    state_key = f"{source_file_stem}::{shipment_id}::{barcode}::{child_id}"
    row_id = _topfloor_row_id(row, category_key)
    return {
        "row_id": row_id,
        "state_key": state_key,
        "state_storage_key": state_key,
        "xmlSource": True,
        "xmlSourceFile": source_file_stem,
        "xmlChildId": child_id,
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
        "prdproddate": "prdProdDate",
        "otpdescription": "orderType",
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
    ven_code = _topfloor_vencode_abbreviations().get(ven_code, ven_code)
    description = " ".join(
        part
        for part in (
            ven_code,
            str(row.get("location", "") or "").split(",", 1)[0].strip(),
            _topfloor_box_prod_date(row.get("prdProdDate", "")),
        )
        if part
    )
    return _topfloor_strip_trailing_matt(description)


def _topfloor_vencode_abbreviations() -> dict[str, str]:
    """Return manually maintained Topfloor venCode abbreviations."""
    global _TOPFLOOR_VENCODE_ABBREVIATIONS, _TOPFLOOR_VENCODE_ABBREVIATIONS_MTIME_NS
    try:
        file_mtime_ns = TOPFLOOR_VENCODE_ABBREVIATIONS_PATH.stat().st_mtime_ns
    except OSError:
        file_mtime_ns = None
    if (
        _TOPFLOOR_VENCODE_ABBREVIATIONS is not None
        and _TOPFLOOR_VENCODE_ABBREVIATIONS_MTIME_NS == file_mtime_ns
    ):
        return dict(_TOPFLOOR_VENCODE_ABBREVIATIONS)
    try:
        payload = json.loads(TOPFLOOR_VENCODE_ABBREVIATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    _TOPFLOOR_VENCODE_ABBREVIATIONS = {
        str(key).strip(): str(value).strip()
        for key, value in payload.items()
        if str(key).strip() and str(value).strip()
    }
    _TOPFLOOR_VENCODE_ABBREVIATIONS_MTIME_NS = file_mtime_ns
    return dict(_TOPFLOOR_VENCODE_ABBREVIATIONS)


def _topfloor_box_prod_date(value: object) -> str:
    """Format prdProdDate as the date suffix used for box descriptions."""
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(2)}.{match.group(3)}."
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
