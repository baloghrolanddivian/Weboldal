"""Read label metadata belonging to a scanned production item."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from manufacturing.base.common import production_folder


XML_FILENAME = "EtikettKitchen_korp_tip.xml"
ITEM_FIELDS = ("Barcode", "Korpusztipus", "Korp_tip_nev", "pdCode", "pdvDescription", "Korp_Szin")
FEATURE_NAMES = (
    "Láb típusa", "J/B", "Nyitási irány", "Munkalap szín", "Front típus", "Beép.mag.cm",
    "Beép.szél.cm", "Beép.mélys.cm", "Front színe", "Front szín felső", "Keretléc szín", "Hézagtakaró szélessége",
    "Fogantyú furat",
)


def empty_xml_metadata() -> dict:
    """Return the metadata contract without assigning UI meaning to its values."""
    return {
        "production_number": "",
        "source_file": XML_FILENAME,
        "lookup_status": "waiting_for_scan",
        "error_message": "",
        "fields": {name: "" for name in ITEM_FIELDS},
        "features": {name: "" for name in FEATURE_NAMES},
    }


def lookup_xml_item(barcode: str, *, production_number: str, oln_id: object = None) -> dict:
    """Match Barcode and, when supplied, olnID before reading sibling fields."""
    result = empty_xml_metadata()
    number = str(production_number or "").strip()
    result["production_number"] = number
    if not re.fullmatch(r"[0-9]+", number) or int(number) <= 0:
        result.update(lookup_status="error", error_message="Érvénytelen gyártási szám az XML-kereséshez.")
        return result
    path = production_folder(number) / XML_FILENAME
    try:
        # Open and parse the source for every scan; do not reuse a production tree.
        root = ET.parse(path).getroot()
    except OSError as exc:
        result.update(lookup_status="unavailable", error_message=f"A gyártási XML nem olvasható: {exc}")
        return result
    except ET.ParseError as exc:
        result.update(lookup_status="error", error_message=f"Hibás gyártási XML: {exc}")
        return result

    matches = []
    for record in root:
        if _local_name(record.tag) != "CON":
            continue
        fields = {_local_name(child.tag): (child.text or "").strip() for child in record}
        if fields.get("Barcode") != str(barcode).strip():
            continue
        if oln_id is not None and fields.get("olnID") != str(oln_id).strip():
            continue
        matches.append(fields)
    if not matches:
        result["lookup_status"] = "not_found"
        return result
    if len(matches) != 1:
        result.update(lookup_status="ambiguous", error_message="Több XML-rekord tartozik a beolvasott azonosítókhoz.")
        return result

    fields = matches[0]
    result["fields"] = {name: fields.get(name, "") for name in ITEM_FIELDS}
    # The current export spells this tag Korp_szin; expose the requested name.
    result["fields"]["Korp_Szin"] = fields.get("Korp_Szin", fields.get("Korp_szin", ""))
    for tag, label in fields.items():
        match = re.fullmatch(r"FeatureBillTranslation(\d+)", tag)
        if match and label in FEATURE_NAMES:
            suffix = match.group(1)
            result["features"][label] = next(
                (fields.get(prefix + suffix, "") for prefix in ("ertek", "OptionValue", "OptionDescription")
                 if fields.get(prefix + suffix, "")),
                "",
            )
    result["lookup_status"] = "ready"
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalized_xml_metadata(payload: object) -> dict:
    """Preserve only the XML fields and feature labels used by this module."""
    result = empty_xml_metadata()
    if not isinstance(payload, dict):
        return result
    result["production_number"] = str(payload.get("production_number", "") or "")
    status = str(payload.get("lookup_status", "") or "")
    if status in {"waiting_for_scan", "ready", "not_found", "ambiguous", "unavailable", "error"}:
        result["lookup_status"] = status
    result["error_message"] = str(payload.get("error_message", "") or "")
    for section in ("fields", "features"):
        source = payload.get(section)
        if isinstance(source, dict):
            result[section] = {name: str(source.get(name, "") or "") for name in result[section]}
    return result
