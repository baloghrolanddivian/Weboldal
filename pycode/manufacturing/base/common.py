"""Shared Manufacturing discovery and read-only persistence helpers."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path


MANUFACTURING_ROOT = Path(os.getenv("DIVIAN_MANUFACTURING_ROOT", r"J:\inSightData\Output\Gyartasi_papirok"))
MANUFACTURING_ENTRIES_CACHE_LOCK = threading.Lock()
MANUFACTURING_ENTRIES_CACHE: dict[tuple[int, bool, str], dict[str, object]] = {}
MANUFACTURING_DATE_LABEL_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_ENTRIES_CACHE_TTL_SECONDS = 30.0


MANUFACTURING_OPERATION_XML_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    "korpusz_osszekeszites": (
        frozenset({"osszekeszito.xml", "alkatresz_kesz.xml"}),
    ),
    "front_osszekeszites": (
        frozenset({"front_osszekeszito.xml"}),
    ),
    "cnc_furas": (
        frozenset({"cnc.xml", "fiokelo_furas.xml"}),
    ),
    "pantolas": (
        frozenset({"pantolo.xml"}),
    ),
    "topfloor": (
        frozenset(
            {
                "szerelveny_dobozolas.xml",
                "topfloor.xml",
                "anyagraktar.xml",
                "anyagraktár.xml",
                "anyagraktar_topfloor.xml",
            }
        ),
    ),
}
MANUFACTURING_XML_SOURCE_NAMES = frozenset(
    name
    for groups in MANUFACTURING_OPERATION_XML_GROUPS.values()
    for group in groups
    for name in group
)


def is_structured_manufacturing_state_key(value: object) -> bool:
    """Return whether value looks like source_file::prdID::conID::childID."""
    parts = str(value or "").strip().split("::")
    return (
        len(parts) == 4
        and bool(parts[0].strip())
        and parts[1].strip().isdigit()
        and bool(parts[2].strip())
        and parts[3].strip().isdigit()
    )


def _production_xml_names(folder: Path) -> frozenset[str]:
    """Return normalized XML file names in a production folder."""
    if not folder.exists():
        return frozenset()
    try:
        return frozenset(
            path.name.lower()
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".xml"
        )
    except OSError:
        return frozenset()


def _production_xml_files(folder: Path) -> list[Path]:
    """Return XML files in deterministic source-priority order."""
    if not folder.exists():
        return []
    try:
        xml_files = [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".xml"
        ]
    except OSError:
        return []
    priority = {name: index for index, name in enumerate(sorted(MANUFACTURING_XML_SOURCE_NAMES))}
    xml_files.sort(key=lambda path: (priority.get(path.name.lower(), 999), path.name.lower()))
    return xml_files


def has_usable_manufacturing_xml(folder: Path, operation: str = "") -> bool:
    """Return whether a production folder has XML input for the requested operation."""
    xml_names = _production_xml_names(folder)
    if not xml_names:
        return False
    operation_key = str(operation or "").strip().lower()
    groups = MANUFACTURING_OPERATION_XML_GROUPS.get(operation_key)
    if groups:
        return all(bool(xml_names & group) for group in groups)
    return any(name in MANUFACTURING_XML_SOURCE_NAMES for name in xml_names)

def _entries_cache_signature() -> tuple[tuple[str, int], ...]:
    """Return a compact signature for recent numeric production folders."""
    if not MANUFACTURING_ROOT.exists():
        return tuple()
    entries: list[tuple[str, int]] = []
    for item in MANUFACTURING_ROOT.iterdir():
        if not item.is_dir() or not item.name.isdigit():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append((item.name, stat.st_mtime_ns))
    entries.sort(key=lambda pair: int(pair[0]), reverse=True)
    return tuple(entries[:200])


def _production_date_cache_signature(folder: Path) -> tuple[tuple[str, int, int], ...]:
    """Return a signature for XML dates, falling back to folder mtime."""
    entries: list[tuple[str, int, int]] = []
    for path in _production_xml_files(folder):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path.name, stat.st_mtime_ns, stat.st_size))
    if entries:
        return tuple(entries)
    try:
        stat = folder.stat()
    except OSError:
        return tuple()
    return (("__folder__", stat.st_mtime_ns, 0),)


def _production_date_label_cached(folder: Path) -> str:
    """Return the production date label using a per-folder signature cache."""
    signature = _production_date_cache_signature(folder)
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_DATE_LABEL_CACHE.get(str(folder))
        if cached and cached.get("signature") == signature:
            return str(cached.get("value", ""))
    value = _production_date_label(folder)
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        MANUFACTURING_DATE_LABEL_CACHE[str(folder)] = {"signature": signature, "value": value}
    return value


def available_production_entries(limit: int = 60, ready_only: bool = False, operation: str = "") -> list[dict[str, str]]:
    """Return recent production folders suitable for the operation picker.

    When ready_only is true, folders must contain the XML group required by the
    requested operation. Results are cached briefly because every page load asks
    for the same recent list several times.
    """
    operation_key = str(operation or "").strip().lower()
    cache_key = (int(limit), bool(ready_only), operation_key)
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_ENTRIES_CACHE.get(cache_key)
        if cached and (time.time() - float(cached.get("created_at", 0.0) or 0.0)) < MANUFACTURING_ENTRIES_CACHE_TTL_SECONDS:
            return [dict(item) for item in cached.get("entries", []) if isinstance(item, dict)]
    signature = _entries_cache_signature()
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_ENTRIES_CACHE.get(cache_key)
        if cached and cached.get("signature") == signature:
            return [dict(item) for item in cached.get("entries", []) if isinstance(item, dict)]

    if not MANUFACTURING_ROOT.exists():
        return []

    candidates = [path for path in MANUFACTURING_ROOT.iterdir() if path.is_dir() and path.name.isdigit()]
    candidates.sort(key=lambda path: int(path.name), reverse=True)

    entries: list[dict[str, str]] = []
    seen_numbers: set[str] = set()
    for folder in candidates:
        number = folder.name
        if number in seen_numbers:
            continue
        if ready_only and not has_usable_manufacturing_xml(folder, operation_key):
            continue
        seen_numbers.add(number)
        entries.append(
            {
                "number": number,
                "date_label": _production_date_label_cached(folder),
            }
        )
        if len(entries) >= limit:
            break

    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        MANUFACTURING_ENTRIES_CACHE[cache_key] = {
            "signature": signature,
            "created_at": time.time(),
            "entries": [dict(item) for item in entries],
        }
    return entries


def _production_date_label(folder: Path) -> str:
    """Return the label shown on production chips, preferring XML prdProdDate."""
    xml_date_label = _production_prd_prod_date_label(folder)
    if xml_date_label:
        return xml_date_label
    try:
        timestamp = folder.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y.%m.%d.")


def _production_xml_field_key(value: object) -> str:
    """Normalize XML field names for date lookup."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").rsplit("}", 1)[-1].strip().lower())


def _format_production_prd_prod_date(value: object) -> str:
    """Format prdProdDate for production chips."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"\b(\d{4})[-./](\d{1,2})[-./](\d{1,2})\b", text)
    if match:
        return f"{match.group(1)}.{int(match.group(2)):02d}.{int(match.group(3)):02d}."
    match = re.search(r"\b(\d{1,2})[.](\d{1,2})[.]?(?:\s|$)", text)
    if match:
        year = datetime.now().year
        return f"{year}.{int(match.group(1)):02d}.{int(match.group(2)):02d}."
    return text


def _production_prd_prod_date_label(folder: Path) -> str:
    """Read prdProdDate from the production XML files."""
    for xml_path in _production_xml_files(folder):
        try:
            root = ET.parse(xml_path).getroot()
        except Exception:
            continue
        for element in root.iter():
            for attr_key, attr_value in element.attrib.items():
                if _production_xml_field_key(attr_key) == "prdproddate":
                    label = _format_production_prd_prod_date(attr_value)
                    if label:
                        return label
            for child in list(element):
                if _production_xml_field_key(child.tag) != "prdproddate":
                    continue
                label = _format_production_prd_prod_date(child.text)
                if label:
                    return label
    return ""


def available_production_numbers(limit: int = 60, ready_only: bool = False, operation: str = "") -> list[str]:
    """Return only the numeric production ids from available entries."""
    return [
        str(item.get("number", ""))
        for item in available_production_entries(limit=limit, ready_only=ready_only, operation=operation)
        if str(item.get("number", "")).isdigit()
    ]


def latest_production_number(operation: str = "") -> str:
    """Return the newest usable production number for an operation."""
    numbers = available_production_numbers(limit=1, ready_only=True, operation=operation)
    return numbers[0] if numbers else ""


def production_folder(production_number: str) -> Path:
    """Return the source folder for a production number."""
    return MANUFACTURING_ROOT / production_number.strip()


def load_production_bundle(production_number: str) -> dict:
    """Load production metadata; operation builders read XML sources directly."""
    folder = production_folder(production_number)
    if not folder.exists():
        raise FileNotFoundError(f"A gyartasi mappa nem talalhato: {folder}")

    return {
        "production_number": production_number,
        "folder": str(folder),
        "documents": [],
    }


def selection_state_path(runtime_root: Path, production_number: str) -> Path:
    """Return the row-state JSON path without changing the filesystem."""
    return runtime_root / production_number / "state.json"


def load_selection_state(runtime_root: Path, production_number: str) -> dict[str, str]:
    """Load persisted row state, filtering unsupported keys and values."""
    path = selection_state_path(runtime_root, production_number)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in payload.items():
        clean_key = str(key)
        clean_value = str(value)
        if clean_value in {"green", "red", "done"}:
            result[clean_key] = clean_value
        elif is_structured_manufacturing_state_key(clean_key) and re.fullmatch(r"\d{1,12}", clean_value):
            result[clean_key] = clean_value
    return result


def partial_quantity_state_path(runtime_root: Path, production_number: str) -> Path:
    """Return the partial-quantity JSON path without changing the filesystem."""
    return runtime_root / production_number / "partial-qty.json"


def load_partial_quantity_state(runtime_root: Path, production_number: str) -> dict[str, str]:
    """Load saved partial quantities for split/partial reporting rows."""
    path = partial_quantity_state_path(runtime_root, production_number)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in payload.items():
        text = str(value or "").strip()
        if key and text:
            result[str(key)] = text
    return result


ROW_DATA_EDITABLE_FIELDS = frozenset({
    "name",
    "detail",
    "model",
    "modelLabel",
    "size",
    "color",
    "color23",
    "edge",
    "drawer_drill",
    "side_type",
    "hardware_type",
    "netfrontColor",
    "drillLabel",
    "drawerType",
    "handleDrill",
    "handleType",
    "openingDir",
    "doorType",
    "pantType",
    "frontTrait",
})


def load_row_data(runtime_root: Path, production_number: str) -> dict[str, dict[str, str]]:
    """Load display-field overrides stored beside manufacturing state."""
    path = runtime_root / production_number / "row-data.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for row_key, raw_fields in payload.items():
        clean_key = str(row_key or "").strip()
        if not clean_key or not isinstance(raw_fields, dict):
            continue
        fields = {
            str(field): str(value or "")[:500]
            for field, value in raw_fields.items()
            if str(field) in ROW_DATA_EDITABLE_FIELDS
        }
        if fields:
            result[clean_key] = fields
    return result


def load_issued_row_edits(runtime_root: Path, production_number: str) -> dict[str, dict[str, object]]:
    """Load pending/completed alerts for rows edited after reaching their handled state."""
    path = runtime_root / production_number / "issued-row-edits.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    for row_key, raw_marker in payload.items():
        clean_key = str(row_key or "").strip()
        if not clean_key or not isinstance(raw_marker, dict):
            continue
        result[clean_key] = {
            "category_key": str(raw_marker.get("category_key", "") or "").strip(),
            "edited_at": str(raw_marker.get("edited_at", "") or "").strip(),
            "completed": bool(raw_marker.get("completed")),
            "completed_at": str(raw_marker.get("completed_at", "") or "").strip(),
            "edited_fields": sorted({
                str(field).strip()
                for field in raw_marker.get("edited_fields", [])
                if str(field).strip() in ROW_DATA_EDITABLE_FIELDS
            }) if isinstance(raw_marker.get("edited_fields"), list) else [],
        }
    return result


def load_shipment_date(runtime_root: Path, shipment_id: str) -> str:
    """Load a Topfloor shipment date stored beside the shipment state."""
    clean_shipment_id = str(shipment_id or "").strip()
    if not clean_shipment_id:
        return ""
    path = runtime_root / clean_shipment_id / "shipment-date.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = str(payload.get("shipment_date", "") if isinstance(payload, dict) else "").strip()
        date.fromisoformat(value)
        return value
    except Exception:
        return ""


def load_admin_change_revision(runtime_root: Path) -> str:
    """Load the revision bumped by an Admin Manufacturing display edit."""
    path = runtime_root / "admin-change.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("revision", "") if isinstance(payload, dict) else "").strip()
    except Exception:
        return ""


