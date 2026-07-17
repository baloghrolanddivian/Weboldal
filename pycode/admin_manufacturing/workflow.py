"""Shared workflow orchestration for manufacturing papers.

This module keeps common cache, state, XML row identity, and view assembly logic
outside the operation-specific builders.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from .common import (
    available_production_entries,
    available_production_numbers,
    is_structured_manufacturing_state_key,
    latest_production_number,
    load_partial_quantity_state,
    load_production_bundle,
    load_row_data,
    load_selection_state,
    production_folder,
)
from .page import render_manufacturing_page
from .config import REPO_ROOT, bundle_disk_cache_dir, runtime_dir
from .routes import (
    MANUFACTURING_DATA_ROUTE,
    MANUFACTURING_PARTIAL_QTY_ROUTE,
    MANUFACTURING_REPORT_READY_ROUTE,
    MANUFACTURING_ROUTE,
    MANUFACTURING_STATE_ROUTE,
    MANUFACTURING_TOPFLOOR_BOX_ROUTE,
)

MANUFACTURING_BUNDLE_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_BUNDLE_CACHE_LOCK = threading.Lock()
MANUFACTURING_BUNDLE_FAST_TTL_SECONDS = 900.0
MANUFACTURING_SIGNATURE_CACHE_TTL_SECONDS = 180.0
MANUFACTURING_SIGNATURE_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_BUNDLE_SCHEMA_VERSION = "2026-06-17-xml-source-file-state-v1"
MANUFACTURING_OPERATION_STATE_KEYS_CACHE: dict[tuple[str, str], dict[str, object]] = {}
MANUFACTURING_PRIME_SYNC_ON_START = False
TOPFLOOR_BOX_TYPES_PATH = REPO_ROOT / "data" / "topfloor_box_types.json"
TOPFLOOR_BOX_TYPES_FALLBACK = [
    {"name": "Válassz dobozt!", "code": "", "id": 0},
    {"name": "Nincs", "code": "", "id": 0},
]

MANUFACTURING_OPERATION_DEFINITIONS = (
    ("korpusz_osszekeszites", "Korpusz összekészítés"),
    ("front_osszekeszites", "Front összekészítés"),
    ("cnc_furas", "CNC fúrás"),
    ("pantolas", "Pántolás"),
    ("topfloor", "Anyagrakt\u00e1r"),
)
MANUFACTURING_OPERATION_HINTS = {
    "korpusz_osszekeszites": "A jelenlegi korpusz nézet és a piros listák.",
    "front_osszekeszites": "A front összekészítő XML sorai és kategóriái.",
    "cnc_furas": "CNC, alsó, felső és fiókelő/front fúrás egy közös műveleti nézetben.",
    "pantolas": "A Pántoló papír sorai eredeti sorrendben, zöld/piros jelöléssel.",
    "topfloor": "Anyagrakt\u00e1r Topfloor alaplogika: lerakod\u00e1s \u00e9s dobozol\u00e1s.",
}
MANUFACTURING_SOURCE_LABELS = {
    "osszekeszito": "Összekészítő",
    "alkatresz_kesz": "Alkatrész kész",
    "front_osszekeszito": "Front összekészítő",
    "cnc": "CNC",
    "fiokelo_furas": "Fiókelő fúrás",
    "pantolo": "Pántoló",
}


def _manufacturing_apply_row_data_overrides(bundle: dict, fallback_number: str = "") -> None:
    """Overlay saved display-only row edits without changing state identities."""
    loaded: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    documents = bundle.get("documents", []) if isinstance(bundle, dict) else []
    for document in documents if isinstance(documents, list) else []:
        if not isinstance(document, dict):
            continue
        if str(document.get("key", "")).strip() == "cnc_furas":
            # The admin CNC builder applies overrides after XML placement.
            continue
        is_topfloor = str(document.get("key", "")).strip() == "topfloor"
        override_root = runtime_dir() / "topfloor" if is_topfloor else runtime_dir()
        sections = document.get("sections", [])
        for section in sections if isinstance(sections, list) else []:
            if not isinstance(section, dict):
                continue
            rows = section.get("rows", [])
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                number = _manufacturing_normalize_number(row.get("production_number", "") or fallback_number)
                if not number:
                    continue
                cache_key = (str(override_root), number)
                if cache_key not in loaded:
                    loaded[cache_key] = load_row_data(override_root, number)
                override_map = loaded[cache_key]
                normalized_overrides = {str(key).casefold(): fields for key, fields in override_map.items()}
                row_keys = [
                    str(row.get("state_storage_key", "") or "").strip(),
                    str(row.get("row_id", "") or "").strip(),
                    *([
                        str(value or "").strip()
                        for value in row.get("sourceRowIds", [])
                        if str(value or "").strip()
                    ] if isinstance(row.get("sourceRowIds"), list) else []),
                ]
                for row_key in dict.fromkeys(key for key in row_keys if key):
                    candidate_keys = [row_key]
                    if row_key.endswith("::0"):
                        candidate_keys.append(row_key[:-3])
                    elif row_key.count("::") >= 2:
                        candidate_keys.append(f"{row_key}::0")
                    fields = next(
                        (
                            override_map.get(candidate)
                            or normalized_overrides.get(candidate.casefold())
                            for candidate in candidate_keys
                            if override_map.get(candidate) or normalized_overrides.get(candidate.casefold())
                        ),
                        None,
                    )
                    if fields:
                        original_fields = row.setdefault("_rowDataOriginal", {})
                        edited_fields = set(row.get("_rowDataEditedFields", []))
                        for field, value in fields.items():
                            original_value = original_fields.get(field, row.get(field, ""))
                            original_fields.setdefault(field, original_value)
                            row[field] = value
                            if str(value) != str(original_value):
                                edited_fields.add(field)
                            else:
                                edited_fields.discard(field)
                        row["_rowDataEditedFields"] = sorted(edited_fields)

def _manufacturing_query_params(raw_path: str) -> dict[str, str]:
    """Return the last value for each manufacturing query-string parameter."""
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}

def _manufacturing_normalize_number(value: object) -> str:
    """Return only the numeric digits from a production/shipment identifier."""
    return re.sub(r"[^0-9]", "", str(value or ""))


def _topfloor_storage_box_types() -> list[dict[str, object]]:
    """Load Topfloor storage box type options from data."""
    try:
        payload = json.loads(TOPFLOOR_BOX_TYPES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = []
    if not isinstance(payload, list):
        payload = []
    result: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        try:
            item_id = int(item.get("id", 0) or 0)
        except (TypeError, ValueError):
            item_id = 0
        result.append(
            {
                "name": name,
                "code": str(item.get("code", "") or "").strip(),
                "id": item_id,
            }
        )
    return result or [dict(item) for item in TOPFLOOR_BOX_TYPES_FALLBACK]

def _manufacturing_signature_key(signature: tuple[tuple[str, int, int], ...]) -> str:
    """Return a stable cache key for the parser version and folder signature."""
    payload = json.dumps(
        {"schema": MANUFACTURING_BUNDLE_SCHEMA_VERSION, "signature": list(signature)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()

def _manufacturing_disk_cache_path(production_number: str) -> Path:
    """Return the disk-cache JSON path for a normalized production number."""
    return bundle_disk_cache_dir() / f"{production_number}.json"

def _read_manufacturing_disk_cache(production_number: str, signature: tuple[tuple[str, int, int], ...]) -> dict | None:
    """Read a disk-cached bundle only when its signature still matches."""
    cache_path = _manufacturing_disk_cache_path(production_number)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(payload.get("signature_key", "")) != _manufacturing_signature_key(signature):
        return None
    bundle = payload.get("bundle")
    return bundle if isinstance(bundle, dict) else None

def _read_manufacturing_stale_disk_cache(production_number: str) -> dict | None:
    """Read any disk-cached bundle for fallback after source loading fails."""
    cache_path = _manufacturing_disk_cache_path(production_number)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    bundle = payload.get("bundle")
    return bundle if isinstance(bundle, dict) else None

def _write_manufacturing_disk_cache(production_number: str, signature: tuple[tuple[str, int, int], ...], bundle: dict) -> None:
    """Persist a parsed bundle to disk, ignoring cache-write failures."""
    try:
        bundle_disk_cache_dir().mkdir(parents=True, exist_ok=True)
        cache_path = _manufacturing_disk_cache_path(production_number)
        payload = {
            "signature_key": _manufacturing_signature_key(signature),
            "bundle": bundle,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return

def _manufacturing_bundle_signature(production_number: str) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    """Return the normalized number and source-folder file signature.

    The signature includes file name, mtime, and size for every direct file in
    the production folder. It is cached briefly because the same request path
    can ask for status, payload, and client cache data in quick succession.
    """
    normalized = _manufacturing_normalize_number(production_number)
    if not normalized:
        return "", tuple()

    now = time.time()
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached_signature = MANUFACTURING_SIGNATURE_CACHE.get(normalized)
        if cached_signature and (now - float(cached_signature.get("created_at", 0.0) or 0.0)) < MANUFACTURING_SIGNATURE_CACHE_TTL_SECONDS:
            return normalized, tuple(cached_signature.get("signature", tuple()))

    folder = production_folder(normalized)
    if not folder.exists():
        return normalized, tuple()

    signature_items: list[tuple[str, int, int]] = []
    for entry in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_file():
            continue
        stat = entry.stat()
        signature_items.append((entry.name, stat.st_mtime_ns, stat.st_size))
    signature = tuple(signature_items)
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        MANUFACTURING_SIGNATURE_CACHE[normalized] = {
            "created_at": now,
            "signature": signature,
        }
    return normalized, signature

def _load_manufacturing_bundle_cached(production_number: str) -> dict:
    """Load a production bundle through memory cache, disk cache, then source.

    Fresh signatures prefer parsed bundles from memory or disk. If the source
    folder cannot be loaded, a stale disk bundle is allowed so the UI can still
    show the latest known parsed data instead of failing hard.
    """
    normalized = _manufacturing_normalize_number(production_number)
    if not normalized:
        raise FileNotFoundError("Adj meg egy érvényes gyártási számot.")

    now = time.time()
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached = MANUFACTURING_BUNDLE_CACHE.get(normalized)
        if (
            cached
            and cached.get("parser_version") == MANUFACTURING_BUNDLE_SCHEMA_VERSION
            and (now - float(cached.get("created_at", 0.0) or 0.0)) < MANUFACTURING_BUNDLE_FAST_TTL_SECONDS
        ):
            return dict(cached.get("bundle", {}))

    normalized, signature = _manufacturing_bundle_signature(normalized)
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached = MANUFACTURING_BUNDLE_CACHE.get(normalized)
        if (
            cached
            and cached.get("parser_version") == MANUFACTURING_BUNDLE_SCHEMA_VERSION
            and cached.get("signature") == signature
        ):
            cached["created_at"] = now
            return dict(cached.get("bundle", {}))

    disk_cached_bundle = _read_manufacturing_disk_cache(normalized, signature)
    if disk_cached_bundle:
        with MANUFACTURING_BUNDLE_CACHE_LOCK:
            MANUFACTURING_BUNDLE_CACHE[normalized] = {
                "created_at": now,
                "parser_version": MANUFACTURING_BUNDLE_SCHEMA_VERSION,
                "signature": signature,
                "bundle": disk_cached_bundle,
            }
        return dict(disk_cached_bundle)

    try:
        bundle = load_production_bundle(normalized)
    except Exception:
        stale_bundle = _read_manufacturing_stale_disk_cache(normalized)
        if not stale_bundle:
            raise
        with MANUFACTURING_BUNDLE_CACHE_LOCK:
            MANUFACTURING_BUNDLE_CACHE[normalized] = {
                "created_at": now,
                "parser_version": MANUFACTURING_BUNDLE_SCHEMA_VERSION,
                "signature": signature,
                "bundle": stale_bundle,
            }
        return dict(stale_bundle)
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        MANUFACTURING_BUNDLE_CACHE[normalized] = {
            "created_at": now,
            "parser_version": MANUFACTURING_BUNDLE_SCHEMA_VERSION,
            "signature": signature,
            "bundle": bundle,
        }
    _write_manufacturing_disk_cache(normalized, signature, bundle)
    return dict(bundle)

def _manufacturing_collect_document_state_keys(document: dict) -> tuple[str, ...]:
    """Collect row state keys that decide whether an operation is complete.

    Single-column overview documents use their special-view rows as the source
    of truth. Grouped rows with sourceRowIds contribute those source keys rather
    than the synthetic group row id.
    """
    sections_for_completion: list[dict] = []
    if bool(document.get("singleColumnOverview")):
        for special_view in document.get("specialViews", []):
            if not isinstance(special_view, dict):
                continue
            for section in special_view.get("sections", []):
                if isinstance(section, dict):
                    sections_for_completion.append(section)
    if not sections_for_completion:
        sections_for_completion = [section for section in document.get("sections", []) if isinstance(section, dict)]

    row_state_keys: list[str] = []
    for section in sections_for_completion:
        if not isinstance(section, dict):
            continue
        for row in section.get("rows", []):
            if not isinstance(row, dict):
                continue
            row_production_number = _manufacturing_normalize_number(row.get("production_number", ""))
            source_row_ids = [
                source_id if "::" in source_id or not row_production_number else _manufacturing_state_key(row_production_number, source_id)
                for source_id in [
                    str(source_id).strip()
                    for source_id in row.get("sourceRowIds", [])
                    if str(source_id).strip()
                ]
            ] if isinstance(row.get("sourceRowIds"), list) else []
            if source_row_ids:
                row_state_keys.extend(source_row_ids)
                continue
            row_state_key = str(row.get("state_key", "")).strip() or str(row.get("row_id", "")).strip()
            if row_state_key:
                row_state_keys.append(row_state_key)
    return tuple(sorted(set(row_state_keys)))

def _manufacturing_operation_state_keys(production_number: str, operation_key: str) -> tuple[str, ...]:
    """Return cached completion-relevant state keys for one operation."""
    normalized_number = _manufacturing_normalize_number(production_number)
    normalized_operation = _manufacturing_normalize_operation(operation_key)
    if not normalized_number or not normalized_operation:
        return tuple()

    _normalized_for_signature, signature = _manufacturing_bundle_signature(normalized_number)
    signature_key = _manufacturing_signature_key(signature)
    cache_key = (normalized_number, normalized_operation)
    now = time.time()
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached = MANUFACTURING_OPERATION_STATE_KEYS_CACHE.get(cache_key)
        if (
            cached
            and cached.get("parser_version") == MANUFACTURING_BUNDLE_SCHEMA_VERSION
            and str(cached.get("signature_key", "")) == signature_key
            and (now - float(cached.get("created_at", 0.0) or 0.0)) < MANUFACTURING_BUNDLE_FAST_TTL_SECONDS
        ):
            return tuple(cached.get("state_keys", tuple()))

    raw_bundle = _load_manufacturing_bundle_cached(normalized_number)
    view_bundle, _view_state = _manufacturing_view_bundle(
        raw_bundle,
        normalized_number,
        {},
        include_all_red_view=False,
        operation_filter=normalized_operation,
    )
    target_document: dict | None = next(
        (
            document
            for document in view_bundle.get("documents", [])
            if isinstance(document, dict) and str(document.get("key", "")).strip() == normalized_operation
        ),
        None,
    )
    state_keys = _manufacturing_collect_document_state_keys(target_document) if isinstance(target_document, dict) else tuple()
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        MANUFACTURING_OPERATION_STATE_KEYS_CACHE[cache_key] = {
            "created_at": now,
            "parser_version": MANUFACTURING_BUNDLE_SCHEMA_VERSION,
            "signature_key": signature_key,
            "state_keys": state_keys,
        }
    return state_keys

def _manufacturing_view_row_state(row: dict, view_state: dict[str, str], production_number: str) -> str:
    """Return the visible row state used for header/chip status."""
    row_production_number = _manufacturing_normalize_number(row.get("production_number", "") or production_number)

    def row_state_key() -> str:
        return str(row.get("state_key", "")).strip() or str(row.get("row_id", "")).strip()

    def row_storage_key() -> str:
        return str(row.get("state_storage_key", "")).strip() or str(row.get("row_id", "")).strip()

    def grouped_quantity() -> int:
        try:
            return max(1, int(float(row.get("meValue") or row.get("quantity") or 0)) or 1)
        except (TypeError, ValueError):
            return 1

    def child_unit_row_id(index: int) -> str:
        return f"{str(row.get('row_id', '')).strip()}__child_unit_{index + 1}"

    def child_unit_storage_key(index: int) -> str:
        parent_storage_key = row_storage_key()
        if is_structured_manufacturing_state_key(parent_storage_key):
            return re.sub(r"::\d+$", f"::{index + 1}", parent_storage_key)
        return child_unit_row_id(index)

    def child_unit_state_key(index: int) -> str:
        storage_key = child_unit_storage_key(index)
        if is_structured_manufacturing_state_key(storage_key):
            return storage_key
        return _manufacturing_state_key(row_production_number, storage_key)

    def child_unit_state(index: int, parent_state: str, has_explicit_unit_state: bool) -> str:
        if parent_state == "done":
            return "done"
        unit_key = child_unit_state_key(index)
        if unit_key in view_state:
            return str(view_state.get(unit_key, "")).strip().lower()
        legacy_unit_key = _manufacturing_state_key(row_production_number, child_unit_row_id(index))
        if legacy_unit_key in view_state:
            return str(view_state.get(legacy_unit_key, "")).strip().lower()
        return "" if has_explicit_unit_state else parent_state

    if (
        str(row.get("columnLayout", "")).strip() in {"pantolo", "front-standard"}
        and not bool(row.get("isPantoloUnit"))
        and grouped_quantity() > 1
    ):
        parent_state = str(view_state.get(row_state_key(), "")).strip().lower()
        unit_count = grouped_quantity()
        has_explicit_unit_state = any(
            child_unit_state_key(index) in view_state
            or _manufacturing_state_key(row_production_number, child_unit_row_id(index)) in view_state
            for index in range(unit_count)
        )
        states = [child_unit_state(index, parent_state, has_explicit_unit_state) for index in range(unit_count)]
        if all(not state for state in states):
            return ""
        if all(state == "red" for state in states):
            return "red"
        if all(state == "done" for state in states):
            return "done"
        if all(state in {"green", "done"} for state in states):
            return "green" if "green" in states else "done"
        return "mixed"

    if bool(row.get("isPantoloUnit")):
        explicit_state = str(view_state.get(row_state_key(), "")).strip().lower()
        return explicit_state or str(row.get("inheritedState", "")).strip().lower()

    source_row_ids = [
        source_id if "::" in source_id or not row_production_number else _manufacturing_state_key(row_production_number, source_id)
        for source_id in [
            str(source_id).strip()
            for source_id in row.get("sourceRowIds", [])
            if str(source_id).strip()
        ]
    ] if isinstance(row.get("sourceRowIds"), list) else []
    if source_row_ids:
        source_states = [
            str(view_state.get(source_id, "")).strip().lower()
            for source_id in source_row_ids
            if str(view_state.get(source_id, "")).strip()
        ]
        if not source_states:
            return ""
        if all(state == source_states[0] for state in source_states):
            return source_states[0]
        if all(state in {"green", "done"} for state in source_states):
            return "green" if "green" in source_states else "done"
        return "mixed"

    state_key = row_state_key()
    if not state_key:
        return ""
    return str(view_state.get(state_key, "")).strip().lower()

def _manufacturing_all_tab_section_groups(document: dict | None) -> tuple[tuple[dict, ...], ...]:
    """Return the section source used by the operation's Összes tab."""
    if not isinstance(document, dict):
        return tuple()
    document_key = str(document.get("key", "")).strip()
    if document_key == "korpusz_osszekeszites":
        groups: list[tuple[dict, ...]] = []
        for special_view_key in ("korpusz-osszekeszito", "korpusz-alkatresz-kesz"):
            special_view = next(
                (
                    view
                    for view in document.get("specialViews", [])
                    if isinstance(view, dict) and str(view.get("key", "")).strip() == special_view_key
                ),
                None,
            )
            if isinstance(special_view, dict):
                groups.append(tuple(section for section in special_view.get("sections", []) if isinstance(section, dict)))
        return tuple(groups)
    if document_key == "cnc_furas":
        sections: list[dict] = []
        for special_view in document.get("specialViews", []):
            if not isinstance(special_view, dict):
                continue
            sections.extend(section for section in special_view.get("sections", []) if isinstance(section, dict))
        return (tuple(sections),)
    return (tuple(section for section in document.get("sections", []) if isinstance(section, dict)),)

def _manufacturing_status_from_row_states(row_states: tuple[str, ...]) -> str:
    """Return an Osszes-style status from visible row states."""
    if not row_states:
        return "plain"
    if any(state_value not in {"red", "green", "done"} for state_value in row_states):
        return "plain"
    if any(state_value == "red" for state_value in row_states):
        return "red"
    if all(state_value == "done" for state_value in row_states):
        return "done"
    if all(state_value in {"green", "done"} for state_value in row_states):
        return "green"
    return "plain"

def _manufacturing_combine_all_tab_statuses(statuses: tuple[str, ...]) -> str:
    """Combine multiple Osszes statuses represented by one chip."""
    clean_statuses = tuple(str(status or "").strip().lower() for status in statuses)
    if not clean_statuses or any(status not in {"red", "green", "done"} for status in clean_statuses):
        return "plain"
    if any(status == "red" for status in clean_statuses):
        return "red"
    if all(status == "done" for status in clean_statuses):
        return "done"
    if all(status in {"green", "done"} for status in clean_statuses):
        return "green"
    return "plain"

def _manufacturing_document_all_tab_status(document: dict | None, view_state: dict[str, str], production_number: str) -> str:
    """Return the combined Osszes status represented by one production chip."""
    group_statuses: list[str] = []
    for sections in _manufacturing_all_tab_section_groups(document):
        row_states: list[str] = []
        for section in sections:
            for row in section.get("rows", []):
                if isinstance(row, dict):
                    row_states.append(_manufacturing_view_row_state(row, view_state, production_number))
        group_statuses.append(_manufacturing_status_from_row_states(tuple(row_states)))
    return _manufacturing_combine_all_tab_statuses(tuple(group_statuses))

def _manufacturing_document_row_states(document: dict | None, view_state: dict[str, str], production_number: str) -> tuple[str, ...]:
    """Return the visible row states used by the operation's Összes tab."""
    row_states: list[str] = []
    for sections in _manufacturing_all_tab_section_groups(document):
        for section in sections:
            for row in section.get("rows", []):
                if isinstance(row, dict):
                    row_states.append(_manufacturing_view_row_state(row, view_state, production_number))
    return tuple(row_states)

def _manufacturing_state_key(production_number: str, row_id: str) -> str:
    """Prefix a local row id with the normalized production number."""
    normalized_number = _manufacturing_normalize_number(production_number)
    return f"{normalized_number}::{str(row_id or '').strip()}"

def _manufacturing_normalize_con_code(value: object) -> str:
    """Extract a canonical CON-prefixed barcode from arbitrary text."""
    text = str(value or "").strip().upper()
    match = re.search(r"\bCON\D*?(\d{6,})\b", text)
    if match:
        return f"CON{match.group(1)}"
    match = re.search(r"\b(\d{6,})\b", text)
    return f"CON{match.group(1)}" if match else ""

def _manufacturing_row_con_code(row: dict) -> str:
    """Return the row barcode/con code from known row payload fields."""
    return _manufacturing_normalize_con_code(row.get("Barcode") or row.get("barcode") or row.get("code", ""))

def _manufacturing_xml_source_stem(source_file: object) -> str:
    """Return the XML source filename without extension for state keys."""
    text = str(source_file or "").strip()
    if not text:
        return ""
    return Path(text).stem.strip() or text

def _manufacturing_xml_state_fields(
    production_number: str,
    source_file: object,
    barcode: object,
    child_id: object = 0,
    prd_id: object = "",
    con_id: object = "",
) -> dict:
    """Return XML identity fields used for stable row state persistence.

    When production id, XML source, and barcode are available, the returned
    state keys use source_file::production::CONcode::childId. This keeps state
    stable when display labels or synthetic row ids change.
    """
    con_code = _manufacturing_normalize_con_code(con_id) or _manufacturing_normalize_con_code(barcode)
    normalized_child_id = re.sub(r"[^0-9]", "", str(child_id if child_id is not None else "").strip()) or "0"
    source_stem = _manufacturing_xml_source_stem(source_file)
    fields = {
        "xmlSource": True,
        "xmlSourceFile": source_stem,
        "xmlChildId": normalized_child_id,
    }
    normalized_number = _manufacturing_normalize_number(prd_id) or _manufacturing_normalize_number(production_number)
    if normalized_number and source_stem and con_code:
        state_key = f"{source_stem}::{normalized_number}::{con_code}::{normalized_child_id}"
        fields["state_storage_key"] = state_key
        fields["state_key"] = state_key
    return fields

def _manufacturing_row_state_storage_key(production_number: str, row: dict) -> str:
    """Return the key used when saving row state to runtime JSON.

    XML-backed rows save under their structured XML identity. Older or manually
    built rows fall back to row_id for compatibility.
    """
    normalized_number = _manufacturing_normalize_number(production_number)
    row_id = str(row.get("row_id", "") or "").strip()
    document_key = str(row.get("doc_key", "") or "").strip()
    con_code = _manufacturing_row_con_code(row)
    if normalized_number and con_code:
        if bool(row.get("xmlSource")):
            operation_key = _manufacturing_xml_source_stem(row.get("xmlSourceFile", "") or row.get("xmlOperation", ""))
            child_id = str(row.get("xmlChildId", "0") or "0").strip()
            if operation_key:
                return f"{operation_key}::{normalized_number}::{con_code}::{child_id}"
    return row_id

def _manufacturing_row_state_view_key(production_number: str, row: dict) -> str:
    """Return the key used by the browser state map for this row."""
    storage_key = _manufacturing_row_state_storage_key(production_number, row)
    row_id = str(row.get("row_id", "") or "").strip()
    return storage_key if "::" in storage_key else _manufacturing_state_key(production_number, row_id)

def _manufacturing_legacy_state_prefixes_for_source(source_file: object) -> tuple[str, ...]:
    """Return legacy operation prefixes that used to persist this XML source."""
    source_stem = _manufacturing_xml_source_stem(source_file)
    ascii_stem = unicodedata.normalize("NFKD", source_stem).encode("ascii", "ignore").decode("ascii")
    folded_stem = re.sub(r"[^a-z0-9]+", "_", ascii_stem.strip().lower()).strip("_")
    aliases: list[str] = []
    if folded_stem:
        aliases.append(folded_stem)
    legacy_by_source = {
        "osszekeszito": ("korpusz_osszekeszito",),
        "alkatresz_kesz": ("korpusz_osszekeszito",),
        "front_osszekeszito": ("front_osszekeszito",),
        "cnc": ("cnc",),
        "fiokelo_furas": ("fiokelo_furas",),
        "pantolo": ("pantolo",),
        "topfloor": ("topfloor",),
        "anyagraktar": ("topfloor",),
        "anyagraktar_topfloor": ("topfloor",),
        "szerelveny_dobozolas": ("topfloor",),
    }
    aliases.extend(legacy_by_source.get(folded_stem, tuple()))
    result: list[str] = []
    for alias in aliases:
        if alias and alias not in result:
            result.append(alias)
    return tuple(result)

def _manufacturing_legacy_state_keys_for_row(row: dict, storage_key: str) -> tuple[str, ...]:
    """Return old state keys that should hydrate the row's current storage key."""
    parts = str(storage_key or "").strip().split("::")
    if len(parts) != 4:
        return tuple()
    current_prefix, production_number, con_code, child_id = parts
    candidate_prefixes = list(_manufacturing_legacy_state_prefixes_for_source(row.get("xmlSourceFile", "") or current_prefix))
    document_key = str(row.get("doc_key", "") or "").strip()
    document_fallbacks = {
        "osszekeszito": ("korpusz_osszekeszito",),
        "alkatresz_kesz": ("korpusz_osszekeszito",),
        "front_osszekeszito": ("front_osszekeszito",),
        "cnc": ("cnc",),
        "fiokelo_furas": ("fiokelo_furas",),
        "pantolo": ("pantolo",),
        "topfloor": ("topfloor",),
    }
    candidate_prefixes.extend(document_fallbacks.get(document_key, tuple()))
    result: list[str] = []
    for prefix in candidate_prefixes:
        if not prefix or prefix == current_prefix:
            continue
        legacy_key = f"{prefix}::{production_number}::{con_code}::{child_id}"
        if legacy_key not in result:
            result.append(legacy_key)
        if child_id == "0":
            legacy_key_without_child = f"{prefix}::{production_number}::{con_code}"
            if legacy_key_without_child not in result:
                result.append(legacy_key_without_child)
    return tuple(result)

def _manufacturing_normalize_operation(value: object) -> str:
    """Return a supported operation key from user input, or an empty string."""
    normalized = str(value or "").strip().lower()
    allowed_keys = {key for key, _label in MANUFACTURING_OPERATION_DEFINITIONS}
    return normalized if normalized in allowed_keys else ""

def _manufacturing_selection_state_payload(production_number: str, raw_state: dict[str, str]) -> dict[str, str]:
    """Convert persisted row state to the client-visible state-key mapping.

    Normal states are green/red/done. Topfloor rows may also store a numeric
    box/con id against a structured source_file::shipment::barcode::child key.
    """
    normalized_number = _manufacturing_normalize_number(production_number)
    result: dict[str, str] = {}
    for row_id, state in raw_state.items():
        clean_state = str(state or "").strip().lower()
        clean_key = str(row_id or "").strip()
        if clean_state not in {"green", "red", "done"} and not (is_structured_manufacturing_state_key(clean_key) and re.fullmatch(r"\d{1,12}", clean_state)):
            continue
        if is_structured_manufacturing_state_key(clean_key):
            result[clean_key] = clean_state
        elif normalized_number and clean_key.startswith(f"{normalized_number}::"):
            result[clean_key] = clean_state
        else:
            result[_manufacturing_state_key(normalized_number, clean_key)] = clean_state
    return result


def _manufacturing_load_existing_selection_state(runtime_root: Path, production_number: str) -> dict[str, str]:
    """Load persisted row state without creating a missing runtime folder."""
    normalized_number = _manufacturing_normalize_number(production_number)
    if not normalized_number:
        return {}
    path = runtime_root / normalized_number / "state.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
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


def _manufacturing_document_state_rows(documents: list[dict]) -> list[dict]:
    """Return rows that can contribute persisted manufacturing state."""
    rows: list[dict] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        state_sections = [
            section
            for section in document.get("sections", [])
            if isinstance(section, dict)
        ]
        for special_view in document.get("specialViews", []):
            if not isinstance(special_view, dict):
                continue
            state_sections.extend(
                section
                for section in special_view.get("sections", [])
                if isinstance(section, dict)
            )
        for section in state_sections:
            rows.extend(row for row in section.get("rows", []) if isinstance(row, dict))
    return rows

def _manufacturing_apply_row_state_aliases(documents: list[dict], production_number: str, raw_state: dict[str, str], selection_state: dict[str, str]) -> None:
    """Copy legacy row-id state onto current structured state keys.

    Older saves can be keyed by row_id, production::row_id, or a structured key
    without child id. The UI should only receive the current row state_key.
    """
    normalized_number = _manufacturing_normalize_number(production_number)
    for row in _manufacturing_document_state_rows(documents):
        state_key = str(row.get("state_key", "") or "").strip()
        if not state_key:
            continue
        row_id = str(row.get("row_id", "") or "").strip()
        storage_key = str(row.get("state_storage_key", "") or "").strip()
        candidate_keys = [
            storage_key,
            re.sub(r"::0$", "", storage_key),
            *_manufacturing_legacy_state_keys_for_row(row, storage_key),
            row_id,
            _manufacturing_state_key(normalized_number, row_id) if row_id else "",
        ]
        for candidate_key in candidate_keys:
            clean_value = str(raw_state.get(candidate_key, "") or "").strip()
            clean_state = clean_value.lower()
            if clean_state in {"green", "red", "done"}:
                selection_state[state_key] = clean_state
                break
            if is_structured_manufacturing_state_key(state_key) and re.fullmatch(r"\d{1,12}", clean_value):
                selection_state[state_key] = clean_value
                break

def _manufacturing_row_with_context(row: dict, production_number: str, detail_suffix: str = "") -> dict:
    """Return a row annotated with production-specific display and state keys."""
    row_payload = dict(row)
    detail_text = str(row_payload.get("detail", "")).strip()
    if detail_suffix:
        row_payload["detail"] = f"{detail_text} · {detail_suffix}" if detail_text else detail_suffix
    row_payload["production_number"] = _manufacturing_normalize_number(production_number)
    row_payload["state_storage_key"] = _manufacturing_row_state_storage_key(production_number, row_payload)
    row_payload["state_key"] = _manufacturing_row_state_view_key(production_number, row_payload)
    return row_payload

def _manufacturing_local_slug(value: str) -> str:
    """Return an ASCII-ish section slug, falling back to szakasz."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "szakasz"

def _manufacturing_is_virtual_unit_row_id(value: object) -> bool:
    """Return whether a row id belongs to a generated quantity/unit child."""
    text = str(value or "")
    return "__child_unit_" in text or "__pantolo_unit_" in text

def _manufacturing_uses_assembly_ready_endpoint(category_key: object) -> bool:
    """Return whether a category reports ready state to the assembly endpoint."""
    return str(category_key or "").strip() == "korpusz-osszekeszito"

def _manufacturing_ready_endpoint_key(document_key: object, category_key: object) -> str:
    """Map a UI document/category pair to the Shopfloor ready endpoint key."""
    clean_document_key = str(document_key or "").strip()
    clean_category_key = str(category_key or "").strip().lower().replace("_", "-")
    if clean_document_key == "topfloor":
        if clean_category_key in {"topfloor-boxing", "boxing", "dobozolas", "dobozol\u00e1s"}:
            return "topfloor_boxing"
        if clean_category_key in {"topfloor-unloading", "unloading", "lerakodas", "lerakod\u00e1s"}:
            return "topfloor_unloading"
        return "topfloor_unloading"
    if clean_document_key == "front_osszekeszites":
        return "front"
    if _manufacturing_uses_assembly_ready_endpoint(category_key):
        return "assembly"
    return "default"

def _manufacturing_document_sections(bundle: dict, production_number: str, allowed_document_keys: tuple[str, ...], include_source_prefix: bool = True) -> tuple[list[dict], int]:
    """Flatten selected source documents into generic manufacturing sections."""
    sections: list[dict] = []
    row_count = 0
    for document in bundle.get("documents", []):
        if not isinstance(document, dict):
            continue
        document_key = str(document.get("key", "")).strip()
        if document_key not in allowed_document_keys:
            continue
        source_label = MANUFACTURING_SOURCE_LABELS.get(document_key, str(document.get("label", "")).strip() or document_key)
        document_sections = document.get("sections", [])
        if not isinstance(document_sections, (list, tuple)):
            continue
        for section in document_sections:
            if not isinstance(section, dict):
                continue
            rows = [
                _manufacturing_row_with_context(row, production_number)
                for row in section.get("rows", [])
                if isinstance(row, dict)
            ]
            if not rows:
                continue
            section_label = str(section.get("label", "")).strip() or source_label
            display_label = f"{source_label} - {section_label}" if include_source_prefix else section_label
            sections.append(
                {
                    "key": f"{document_key}::{str(section.get('key', '')).strip() or 'section'}",
                    "label": display_label,
                    "rows": rows,
                }
            )
            row_count += len(rows)
    return sections, row_count

def _manufacturing_red_state_numbers(runtime_root: Path) -> list[str]:
    """Return production numbers that currently have at least one red row."""
    numbers: list[str] = []
    for path in sorted(runtime_root.glob("*/state.json"), key=lambda item: item.parent.name, reverse=True):
        number = _manufacturing_normalize_number(path.parent.name)
        if not number:
            continue
        state = load_selection_state(runtime_root, number)
        if any(value == "red" for value in state.values()):
            numbers.append(number)
    return numbers

def _manufacturing_all_red_special_view(current_number: str) -> tuple[dict, dict[str, str]]:
    """Build the Korpusz special view containing red rows across productions.

    The returned selection-state payload includes the persisted red states for
    those rows so the special view can be rendered without loading each source
    production separately in the browser.
    """
    from .cnc.sections import _manufacturing_cnc_sections
    from .front.sections import _manufacturing_front_sections
    from .korpusz.sections import _manufacturing_korpusz_sections
    from .pantolas.sections import _manufacturing_pantolo_sections, _manufacturing_pantolo_xml_sections

    sections: list[dict] = []
    selection_state: dict[str, str] = {}
    for production_number in _manufacturing_red_state_numbers(runtime_dir()):
        raw_state = load_selection_state(runtime_dir(), production_number)
        red_state_keys = {str(row_id).strip() for row_id, state in raw_state.items() if state == "red"}
        if not red_state_keys:
            continue
        selection_state.update(_manufacturing_selection_state_payload(production_number, raw_state))
        try:
            bundle = _load_manufacturing_bundle_cached(production_number)
        except Exception:
            continue
        korpusz_sections, _ = _manufacturing_korpusz_sections(bundle, production_number)
        rows: list[dict] = []
        for section in korpusz_sections:
            section_label = str(section.get("label", "")).strip()
            for row in section.get("rows", []):
                if not isinstance(row, dict):
                    continue
                storage_key = _manufacturing_row_state_storage_key(production_number, row)
                legacy_storage_key = re.sub(r"::0$", "", storage_key)
                legacy_state_keys = _manufacturing_legacy_state_keys_for_row(row, storage_key)
                if (
                    str(row.get("row_id", "")).strip() not in red_state_keys
                    and storage_key not in red_state_keys
                    and legacy_storage_key not in red_state_keys
                    and not any(legacy_key in red_state_keys for legacy_key in legacy_state_keys)
                ):
                    continue
                suffix_parts = [f"Gyártás {production_number}"]
                if section_label:
                    suffix_parts.append(section_label)
                rows.append(_manufacturing_row_with_context(row, production_number, " · ".join(suffix_parts)))
        if rows:
            section_title = f"Gyártás {production_number}"
            if production_number == _manufacturing_normalize_number(current_number):
                section_title += " (aktuális)"
            sections.append(
                {
                    "key": f"all-red::{production_number}",
                    "label": section_title,
                    "rows": rows,
                }
            )
    return (
        {
            "key": "all-productions-red",
            "label": "Összes gyártás összes piros eleme",
            "count": sum(len(section.get("rows", [])) for section in sections),
            "sections": sections,
        },
        selection_state,
    )

def _manufacturing_placeholder_document(key: str, label: str) -> dict:
    """Return an empty document for an operation without implemented rows."""
    return {
        "key": key,
        "label": label,
        "file_name": "",
        "sections": [],
        "row_count": 0,
        "placeholderMessage": f"A {label.lower()} feldolgozási logikája még nincs kialakítva.",
        "specialViews": [],
    }

def _manufacturing_topfloor_shipment_entries(bundle: dict) -> list[dict[str, object]]:
    """Return shipment-based toolbar entries for the Topfloor operation."""
    documents = bundle.get("documents", []) if isinstance(bundle, dict) else []
    topfloor_document = next(
        (
            document
            for document in documents
            if isinstance(document, dict) and str(document.get("key", "")).strip() == "topfloor"
        ),
        None,
    )
    if not isinstance(topfloor_document, dict):
        return []
    entries: list[dict[str, object]] = []
    sections = topfloor_document.get("sections", [])
    if not isinstance(sections, list):
        sections = []
    shipment_views = topfloor_document.get("topfloorShipmentViews", [])
    if not isinstance(shipment_views, list):
        shipment_views = []
    for view in shipment_views:
        if not isinstance(view, dict):
            continue
        view_key = str(view.get("key", "") or "").strip()
        if not view_key.startswith("shipment::"):
            continue
        shipment_id = view_key.split("::", 1)[1].strip()
        if not shipment_id:
            continue
        is_all_shipments_view = shipment_id == "__all__"
        shipment_label = str(view.get("label", "") or "").strip() or "Nagyautó"
        try:
            category_count = max(0, int(view.get("count", 0) or 0))
        except (TypeError, ValueError):
            category_count = 0
        shipment_categories = [
            section.get("topfloorCategory", {})
            for section in sections
            if (
                isinstance(section, dict)
                and isinstance(section.get("topfloorCategory"), dict)
                and (
                    is_all_shipments_view
                    or str(section["topfloorCategory"].get("shipmentID", "")).strip() == shipment_id
                )
            )
        ]
        shipment_complete = bool(shipment_categories) and all(
            bool(category.get("storageBoxIssued")) for category in shipment_categories
        )
        issued_count = sum(1 for category in shipment_categories if bool(category.get("storageBoxIssued")))
        entries.append(
            {
                "kind": "shipment",
                "number": "Összes" if is_all_shipments_view else shipment_id,
                "count": category_count,
                "issued_count": issued_count,
                "date_label": shipment_label,
                "view_key": view_key,
                "is_active": not entries,
                "is_complete": shipment_complete,
                "state_status": "done" if shipment_complete else "plain",
            }
        )
    return entries

def _manufacturing_topfloor_aggregate_bundle(production_numbers: list[str]) -> tuple[dict, dict[str, str], dict[str, str]]:
    """Build the Topfloor bundle from all recent production folders."""
    from .topfloor.sections import _manufacturing_topfloor_document_from_bundles

    source_bundles: list[tuple[dict, str]] = []
    for production_number in production_numbers:
        normalized_number = _manufacturing_normalize_number(production_number)
        if not normalized_number:
            continue
        source_bundles.append(
            (
                {
                    "production_number": normalized_number,
                    "folder": str(production_folder(normalized_number)),
                },
                normalized_number,
            )
        )

    topfloor_document = _manufacturing_topfloor_document_from_bundles(source_bundles)
    shipment_views = topfloor_document.get("topfloorShipmentViews", [])
    if not isinstance(shipment_views, list):
        shipment_views = []
    shipment_ids = [
        view_key.split("::", 1)[1].strip()
        for view_key in [
            str(view.get("key", "") or "").strip()
            for view in shipment_views
            if isinstance(view, dict)
        ]
        if view_key.startswith("shipment::") and view_key.split("::", 1)[1].strip()
        and view_key.split("::", 1)[1].strip() != "__all__"
    ]
    selection_state: dict[str, str] = {}
    partial_quantity_state: dict[str, str] = {}
    topfloor_runtime_root = runtime_dir() / "topfloor"
    for shipment_id in shipment_ids:
        raw_state = _manufacturing_load_existing_selection_state(topfloor_runtime_root, shipment_id)
        selection_state.update(_manufacturing_selection_state_payload(shipment_id, raw_state))
        _manufacturing_apply_row_state_aliases([topfloor_document], shipment_id, raw_state, selection_state)
    return (
        {
            "production_number": "",
            "folder": "",
            "documents": [topfloor_document],
        },
        selection_state,
        partial_quantity_state,
    )

def _manufacturing_view_bundle(
    raw_bundle: dict,
    production_number: str,
    current_selection_state: dict[str, str],
    *,
    include_all_red_view: bool = True,
    operation_filter: str = "",
) -> tuple[dict, dict[str, str]]:
    """Build operation document bundle and client state payload.

    Operation-specific section builders produce their own row shapes. This
    function assembles them into the shared document schema and hydrates
    current state through legacy aliases. When operation_filter is set, only
    that operation is built so opening one module does not parse every module.
    """
    current_number = _manufacturing_normalize_number(production_number)
    documents: list[dict] = []
    selection_state_payload = _manufacturing_selection_state_payload(current_number, current_selection_state)
    target_operation = _manufacturing_normalize_operation(operation_filter)

    def finalize_filtered_documents(filtered_documents: list[dict]) -> tuple[dict, dict[str, str]]:
        existing_keys = {str(document.get("key", "")).strip() for document in filtered_documents}
        if target_operation and target_operation not in existing_keys:
            operation_label = next(
                (label for operation_key, label in MANUFACTURING_OPERATION_DEFINITIONS if operation_key == target_operation),
                target_operation,
            )
            filtered_documents.append(_manufacturing_placeholder_document(target_operation, operation_label))
        _manufacturing_apply_row_state_aliases(filtered_documents, current_number, current_selection_state, selection_state_payload)
        return (
            {
                "production_number": current_number,
                "folder": str(raw_bundle.get("folder", "")),
                "documents": filtered_documents,
            },
            selection_state_payload,
        )

    if target_operation == "korpusz_osszekeszites":
        from .korpusz.sections import (
            _manufacturing_alkatresz_kesz_xml_sections,
            _manufacturing_korpusz_sections,
            _manufacturing_osszekeszito_xml_sections,
        )

        korpusz_sections, korpusz_row_count = _manufacturing_korpusz_sections(raw_bundle, current_number)
        korpusz_osszekeszito_sections, korpusz_osszekeszito_count, korpusz_osszekeszito_xml_available = _manufacturing_osszekeszito_xml_sections(raw_bundle, current_number)
        korpusz_osszekeszito_source_type = "XML" if korpusz_osszekeszito_xml_available else "Nincs XML"
        korpusz_alkatresz_sections, korpusz_alkatresz_count, korpusz_alkatresz_xml_available = _manufacturing_alkatresz_kesz_xml_sections(raw_bundle, current_number)
        korpusz_alkatresz_source_type = "XML" if korpusz_alkatresz_xml_available else "Nincs XML"
        if include_all_red_view:
            all_red_view, all_red_selection_state = _manufacturing_all_red_special_view(current_number)
            selection_state_payload.update(all_red_selection_state)
        else:
            all_red_view = {
                "key": "all-productions-red",
                "label": "\u00d6sszes gy\u00e1rt\u00e1s \u00f6sszes piros eleme",
                "count": 0,
                "sections": [],
            }
        return finalize_filtered_documents(
            [
                {
                    "key": "korpusz_osszekeszites",
                    "label": "Korpusz \u00f6sszek\u00e9sz\u00edt\u00e9s",
                    "sourceType": korpusz_osszekeszito_source_type,
                    "sourceLabel": f"Beolvasva: {korpusz_osszekeszito_source_type}, {korpusz_alkatresz_source_type}",
                    "file_name": "",
                    "sections": korpusz_sections,
                    "row_count": korpusz_row_count,
                    "placeholderMessage": "Ehhez az opci\u00f3hoz m\u00e9g nincs megjelen\u00edthet\u0151 sor.",
                    "specialViews": [
                        {
                            "key": "korpusz-osszekeszito",
                            "label": "\u00d6sszek\u00e9sz\u00edt\u0151",
                            "count": korpusz_osszekeszito_count,
                            "sections": korpusz_osszekeszito_sections,
                        },
                        {
                            "key": "korpusz-alkatresz-kesz",
                            "label": "Alkatr\u00e9sz k\u00e9sz",
                            "count": korpusz_alkatresz_count,
                            "sections": korpusz_alkatresz_sections,
                        },
                        all_red_view,
                    ],
                    "hideBarcodeColumn": True,
                }
            ]
        )

    if target_operation == "front_osszekeszites":
        from .front.sections import _manufacturing_front_sections

        front_sections, front_row_count = _manufacturing_front_sections(raw_bundle, current_number)
        front_source_type = "Nincs XML"
        front_folder = Path(str(raw_bundle.get("folder", "") or "").strip())
        front_xml_path = front_folder / "Front_osszekeszito.xml"
        if front_xml_path.is_file():
            front_source_type = "XML"
        else:
            try:
                if any(path.is_file() and path.name.lower() == "front_osszekeszito.xml" for path in front_folder.iterdir()):
                    front_source_type = "XML"
            except OSError:
                pass
        front_folias_sections = [dict(section) for section in front_sections if "\u00b7 F\u00f3li\u00e1s" in str(section.get("label", ""))]
        front_butorlapos_sections = [dict(section) for section in front_sections if "\u00b7 B\u00fatorlapos" in str(section.get("label", ""))]
        return finalize_filtered_documents(
            [
                {
                    "key": "front_osszekeszites",
                    "label": "Front \u00f6sszek\u00e9sz\u00edt\u00e9s",
                    "sourceType": front_source_type,
                    "sourceLabel": f"Beolvasva: {front_source_type}",
                    "file_name": "",
                    "sections": front_sections,
                    "row_count": front_row_count,
                    "placeholderMessage": "Ehhez az opci\u00f3hoz m\u00e9g nincs megjelen\u00edthet\u0151 sor.",
                    "specialViews": [
                        {
                            "key": "front-folias",
                            "label": "F\u00f3li\u00e1s",
                            "count": sum(len(section.get("rows", [])) for section in front_folias_sections),
                            "sections": front_folias_sections,
                        },
                        {
                            "key": "front-butorlapos",
                            "label": "B\u00fatorlapos",
                            "count": sum(len(section.get("rows", [])) for section in front_butorlapos_sections),
                            "sections": front_butorlapos_sections,
                        },
                    ],
                    "allowSplit": False,
                    "singleColumnOverview": True,
                }
            ]
        )

    if target_operation == "cnc_furas":
        from .cnc.sections import _manufacturing_cnc_sections

        cnc_sections, cnc_row_count, cnc_special_views, cnc_source_type, cnc_source_label = _manufacturing_cnc_sections(raw_bundle, current_number)
        return finalize_filtered_documents(
            [
                {
                    "key": "cnc_furas",
                    "label": "CNC f\u00far\u00e1s",
                    "sourceType": cnc_source_type,
                    "sourceLabel": cnc_source_label,
                    "file_name": "",
                    "sections": cnc_sections,
                    "row_count": cnc_row_count,
                    "placeholderMessage": "Ehhez az opci\u00f3hoz m\u00e9g nincs megjelen\u00edthet\u0151 sor.",
                    "specialViews": cnc_special_views,
                    "hideBarcodeColumn": True,
                    "allowSplit": False,
                    "singleColumnOverview": True,
                }
            ]
        )

    if target_operation == "pantolas":
        from .pantolas.sections import _manufacturing_pantolo_sections, _manufacturing_pantolo_xml_sections

        pantolo_sections, pantolo_row_count = _manufacturing_pantolo_sections(raw_bundle, current_number)
        _, _, pantolo_xml_available = _manufacturing_pantolo_xml_sections(raw_bundle, current_number)
        pantolo_source_type = "XML" if pantolo_xml_available else "Nincs XML"
        return finalize_filtered_documents(
            [
                {
                    "key": "pantolas",
                    "label": "P\u00e1ntol\u00e1s",
                    "sourceType": pantolo_source_type,
                    "sourceLabel": f"Beolvasva: {pantolo_source_type}",
                    "file_name": "",
                    "sections": pantolo_sections,
                    "row_count": pantolo_row_count,
                    "placeholderMessage": "A kiv\u00e1lasztott gy\u00e1rt\u00e1sban nem tal\u00e1ltam haszn\u00e1lhat\u00f3 P\u00e1ntol\u00f3 sort.",
                    "specialViews": [],
                    "hideBarcodeColumn": True,
                    "allowSplit": False,
                    "singleColumnOverview": True,
                }
            ]
        )

    if target_operation == "topfloor":
        from .topfloor.sections import _manufacturing_topfloor_document

        return finalize_filtered_documents([_manufacturing_topfloor_document(raw_bundle, current_number)])

    from .cnc.sections import _manufacturing_cnc_sections
    from .front.sections import _manufacturing_front_sections
    from .korpusz.sections import (
        _manufacturing_alkatresz_kesz_xml_sections,
        _manufacturing_korpusz_sections,
        _manufacturing_osszekeszito_xml_sections,
    )
    from .pantolas.sections import _manufacturing_pantolo_sections, _manufacturing_pantolo_xml_sections
    from .topfloor.sections import _manufacturing_topfloor_document

    korpusz_sections, korpusz_row_count = _manufacturing_korpusz_sections(raw_bundle, current_number)
    korpusz_osszekeszito_sections, korpusz_osszekeszito_count, korpusz_osszekeszito_xml_available = _manufacturing_osszekeszito_xml_sections(raw_bundle, current_number)
    korpusz_osszekeszito_source_type = "XML" if korpusz_osszekeszito_xml_available else "Nincs XML"
    korpusz_alkatresz_sections, korpusz_alkatresz_count, korpusz_alkatresz_xml_available = _manufacturing_alkatresz_kesz_xml_sections(raw_bundle, current_number)
    korpusz_alkatresz_source_type = "XML" if korpusz_alkatresz_xml_available else "Nincs XML"
    if include_all_red_view:
        all_red_view, all_red_selection_state = _manufacturing_all_red_special_view(current_number)
        selection_state_payload.update(all_red_selection_state)
    else:
        all_red_view = {
            "key": "all-productions-red",
            "label": "Összes gyártás összes piros eleme",
            "count": 0,
            "sections": [],
        }

    documents.append(
        {
            "key": "korpusz_osszekeszites",
            "label": "Korpusz összekészítés",
            "sourceType": korpusz_osszekeszito_source_type,
            "sourceLabel": f"Beolvasva: {korpusz_osszekeszito_source_type}, {korpusz_alkatresz_source_type}",
            "file_name": "",
            "sections": korpusz_sections,
            "row_count": korpusz_row_count,
            "placeholderMessage": "Ehhez az opcióhoz még nincs megjeleníthető sor.",
            "specialViews": [
                {
                    "key": "korpusz-osszekeszito",
                    "label": "Összekészítő",
                    "count": korpusz_osszekeszito_count,
                    "sections": korpusz_osszekeszito_sections,
                },
                {
                    "key": "korpusz-alkatresz-kesz",
                    "label": "Alkatrész kész",
                    "count": korpusz_alkatresz_count,
                    "sections": korpusz_alkatresz_sections,
                },
                all_red_view,
            ],
            "hideBarcodeColumn": True,
        }
    )

    front_sections, front_row_count = _manufacturing_front_sections(raw_bundle, current_number)
    front_source_type = "Nincs XML"
    front_folder = Path(str(raw_bundle.get("folder", "") or "").strip())
    front_xml_path = front_folder / "Front_osszekeszito.xml"
    if front_xml_path.is_file():
        front_source_type = "XML"
    else:
        try:
            if any(path.is_file() and path.name.lower() == "front_osszekeszito.xml" for path in front_folder.iterdir()):
                front_source_type = "XML"
        except OSError:
            pass
    front_folias_sections = [dict(section) for section in front_sections if "· Fóliás" in str(section.get("label", ""))]
    front_butorlapos_sections = [dict(section) for section in front_sections if "· Bútorlapos" in str(section.get("label", ""))]

    documents.append(
        {
            "key": "front_osszekeszites",
            "label": "Front összekészítés",
            "sourceType": front_source_type,
            "sourceLabel": f"Beolvasva: {front_source_type}",
            "file_name": "",
            "sections": front_sections,
            "row_count": front_row_count,
            "placeholderMessage": "Ehhez az opcióhoz még nincs megjeleníthető sor.",
            "specialViews": [
                {
                    "key": "front-folias",
                    "label": "Fóliás",
                    "count": sum(len(section.get("rows", [])) for section in front_folias_sections),
                    "sections": front_folias_sections,
                },
                {
                    "key": "front-butorlapos",
                    "label": "Bútorlapos",
                    "count": sum(len(section.get("rows", [])) for section in front_butorlapos_sections),
                    "sections": front_butorlapos_sections,
                },
            ],
            "allowSplit": False,
            "singleColumnOverview": True,
        }
    )

    cnc_sections, cnc_row_count, cnc_special_views, cnc_source_type, cnc_source_label = _manufacturing_cnc_sections(raw_bundle, current_number)
    documents.append(
        {
            "key": "cnc_furas",
            "label": "CNC fúrás",
            "sourceType": cnc_source_type,
            "sourceLabel": cnc_source_label,
            "file_name": "",
            "sections": cnc_sections,
            "row_count": cnc_row_count,
            "placeholderMessage": "Ehhez az opcióhoz még nincs megjeleníthető sor.",
            "specialViews": cnc_special_views,
            "hideBarcodeColumn": True,
            "allowSplit": False,
            "singleColumnOverview": True,
        }
    )

    pantolo_sections, pantolo_row_count = _manufacturing_pantolo_sections(raw_bundle, current_number)
    _, _, pantolo_xml_available = _manufacturing_pantolo_xml_sections(raw_bundle, current_number)
    pantolo_source_type = "XML" if pantolo_xml_available else "Nincs XML"
    documents.append(
        {
            "key": "pantolas",
            "label": "Pántolás",
            "sourceType": pantolo_source_type,
            "sourceLabel": f"Beolvasva: {pantolo_source_type}",
            "file_name": "",
            "sections": pantolo_sections,
            "row_count": pantolo_row_count,
            "placeholderMessage": "A kiválasztott gyártásban nem találtam használható Pántoló sort.",
            "specialViews": [],
            "hideBarcodeColumn": True,
            "allowSplit": False,
            "singleColumnOverview": True,
        }
    )
    documents.append(_manufacturing_topfloor_document(raw_bundle, current_number))

    existing_keys = {str(document.get("key", "")).strip() for document in documents}
    for operation_key, operation_label in MANUFACTURING_OPERATION_DEFINITIONS:
        if operation_key in existing_keys:
            continue
        documents.append(_manufacturing_placeholder_document(operation_key, operation_label))

    _manufacturing_apply_row_state_aliases(documents, current_number, current_selection_state, selection_state_payload)

    return (
        {
            "production_number": current_number,
            "folder": str(raw_bundle.get("folder", "")),
            "documents": documents,
        },
        selection_state_payload,
    )

def manufacturing_module_payload(
    production_number: str = "",
    operation: str = "",
    message: str = "",
    success: bool = False,
    include_client_cache: bool = True,
    route: str = MANUFACTURING_ROUTE,
) -> dict[str, object]:
    """Build the manufacturing module payload shared by HTML and JSON views."""
    module_route = str(route or MANUFACTURING_ROUTE).rstrip("/")
    data_route = f"{module_route}/data"
    # This duplicated module is observational: it reads persisted state but
    # deliberately exposes no browser mutation endpoints.
    state_route = ""
    partial_qty_route = ""
    report_ready_route = ""
    topfloor_box_route = ""
    row_edit_route = f"{module_route}/row-data"
    requested_number = _manufacturing_normalize_number(production_number)
    selected_operation = _manufacturing_normalize_operation(operation)
    lightweight_operation_picker = not bool(selected_operation)
    if lightweight_operation_picker:
        # Műveletválasztó nézet: ne töltsünk gyártáslistát/bundle-t.
        recent_productions = []
        recent_numbers: list[str] = []
        selected_number = requested_number if requested_number else ""
    else:
        recent_productions = available_production_entries(
            limit=12,
            ready_only=True,
            operation=selected_operation,
        )
        recent_numbers = [str(entry.get("number", "")) for entry in recent_productions]
        selected_number = (
            requested_number
            if (requested_number and requested_number in recent_numbers)
            else (recent_numbers[0] if recent_numbers else "")
        )
    operations = [
        {
            "key": operation_key,
            "label": operation_label,
            "hint": MANUFACTURING_OPERATION_HINTS.get(operation_key, ""),
        }
        for operation_key, operation_label in MANUFACTURING_OPERATION_DEFINITIONS
    ]
    if requested_number and requested_number not in recent_numbers and not lightweight_operation_picker and selected_operation != "topfloor":
        combined_prefix = f"A {requested_number} gyártás nem szerepel a friss használható XML-es gyártási listában, ezért a legfrissebb használható gyártást nyitottam meg."
        message = f"{combined_prefix} {message}".strip() if message else combined_prefix
        success = False

    def production_state_status(entry_number: str, operation_key: str) -> str:
        """Return toolbar status: plain, red, green, or done."""
        operation_filter = _manufacturing_normalize_operation(operation_key)
        if not operation_filter:
            return "plain"
        normalized_number = _manufacturing_normalize_number(entry_number)
        if not normalized_number:
            return "plain"
        try:
            saved_state = load_selection_state(runtime_dir(), normalized_number)
            raw_bundle = _load_manufacturing_bundle_cached(normalized_number)
            view_bundle, view_state = _manufacturing_view_bundle(
                raw_bundle,
                normalized_number,
                saved_state,
                include_all_red_view=False,
                operation_filter=operation_filter,
            )
            target_document = next(
                (
                    document
                    for document in view_bundle.get("documents", [])
                    if isinstance(document, dict) and str(document.get("key", "")).strip() == operation_filter
                ),
                None,
            )
            return _manufacturing_document_all_tab_status(target_document, view_state, normalized_number)
        except Exception:
            return "plain"

    def production_entry_with_status(entry: dict) -> dict:
        production_status = production_state_status(str(entry.get("number", "")), selected_operation)
        return {
            **dict(entry),
            "state_status": production_status,
            "is_complete": production_status in {"green", "done"},
        }

    if selected_operation == "topfloor":
        recent_productions = [{**dict(entry), "is_complete": False, "state_status": "plain"} for entry in recent_productions]
        selected_number = ""
    else:
        recent_productions = [production_entry_with_status(dict(entry)) for entry in recent_productions]

    bundle: dict | None = None
    selection_state: dict[str, str] = {}
    partial_quantity_state: dict[str, str] = {}
    combined_message = message
    combined_success = success

    if selected_operation == "topfloor" and not lightweight_operation_picker:
        try:
            bundle, selection_state, partial_quantity_state = _manufacturing_topfloor_aggregate_bundle(recent_numbers)
            recent_productions = _manufacturing_topfloor_shipment_entries(bundle)
            if not recent_productions:
                combined_message = "Nem találok megjeleníthető Anyagraktár szállítmányt a legutóbbi gyártási mappákban."
                combined_success = False
        except Exception as exc:
            combined_message = f"Az Anyagraktár XML-ek betöltése nem sikerült: {exc}"
            combined_success = False
    elif not selected_number:
        combined_message = "Nem találok használható gyártási mappát a beállított gyártási útvonalon."
        combined_success = False
    elif not lightweight_operation_picker:
        try:
            raw_bundle = _load_manufacturing_bundle_cached(selected_number)
            current_selection_state = load_selection_state(runtime_dir(), selected_number)
            partial_quantity_state = load_partial_quantity_state(runtime_dir(), selected_number)
            bundle, selection_state = _manufacturing_view_bundle(
                raw_bundle,
                selected_number,
                current_selection_state,
                include_all_red_view=True,
                operation_filter=selected_operation,
            )
        except Exception as exc:
            combined_message = f"A gyártási papírok betöltése nem sikerült: {exc}"
            combined_success = False

    if bundle is None:
        bundle = {
            "production_number": selected_number,
            "folder": str(production_folder(selected_number)) if selected_number else "",
            "documents": [],
        }

    _manufacturing_apply_row_data_overrides(bundle, selected_number)

    production_client_cache: list[dict[str, object]] = []
    topfloor_storage_box_types = _topfloor_storage_box_types()
    if include_client_cache and selected_operation and recent_productions and selected_operation != "topfloor":
        for entry in recent_productions:
            cache_number = _manufacturing_normalize_number(entry.get("number", ""))
            if not cache_number:
                continue
            try:
                if cache_number == selected_number:
                    cache_bundle = bundle
                    cache_selection_state = selection_state
                    cache_partial_quantity_state = partial_quantity_state
                else:
                    cache_raw_bundle = _load_manufacturing_bundle_cached(cache_number)
                    cache_saved_state = load_selection_state(runtime_dir(), cache_number)
                    cache_partial_quantity_state = load_partial_quantity_state(runtime_dir(), cache_number)
                    cache_bundle, cache_selection_state = _manufacturing_view_bundle(
                        cache_raw_bundle,
                        cache_number,
                        cache_saved_state,
                        include_all_red_view=True,
                        operation_filter=selected_operation,
                    )
                    _manufacturing_apply_row_data_overrides(cache_bundle, cache_number)
                production_client_cache.append(
                    manufacturing_client_payload(
                        {
                            "route": module_route,
                            "dataRoute": data_route,
                            "stateRoute": state_route,
                            "partialQtyRoute": partial_qty_route,
                            "reportReadyRoute": report_ready_route,
                            "topfloorBoxRoute": topfloor_box_route,
                            "rowEditRoute": row_edit_route,
                            "topfloorStorageBoxTypes": topfloor_storage_box_types,
                            "productionNumber": cache_number,
                            "selectedOperation": selected_operation,
                            "recentProductions": recent_productions,
                            "bundle": cache_bundle,
                            "selectionState": cache_selection_state,
                            "partialQuantityState": cache_partial_quantity_state,
                            "message": "",
                            "success": False,
                        }
                    )
                )
            except Exception:
                continue

    return {
        "route": module_route,
        "dataRoute": data_route,
        "stateRoute": state_route,
        "partialQtyRoute": partial_qty_route,
        "reportReadyRoute": report_ready_route,
        "topfloorBoxRoute": topfloor_box_route,
        "rowEditRoute": row_edit_route,
        "topfloorStorageBoxTypes": topfloor_storage_box_types,
        "productionNumber": selected_number,
        "operations": operations,
        "selectedOperation": selected_operation,
        "recentProductions": recent_productions,
        "bundle": bundle,
        "selectionState": selection_state,
        "partialQuantityState": partial_quantity_state,
        "productionClientCache": production_client_cache,
        "message": combined_message,
        "success": combined_success,
    }

def manufacturing_client_payload(module_payload: dict[str, object]) -> dict[str, object]:
    """Return the compact browser payload for one selected manufacturing operation."""
    bundle = module_payload.get("bundle", {}) if isinstance(module_payload.get("bundle"), dict) else {}
    selected_operation = _manufacturing_normalize_operation(module_payload.get("selectedOperation", ""))
    documents = [document for document in bundle.get("documents", []) if isinstance(document, dict)]
    active_document = next(
        (
            document
            for document in documents
            if str(document.get("key", "")).strip() == selected_operation
        ),
        None,
    )
    visible_documents = [active_document] if isinstance(active_document, dict) else documents
    return {
        "productionNumber": str(module_payload.get("productionNumber", "")),
        "route": str(module_payload.get("route", MANUFACTURING_ROUTE)),
        "dataRoute": str(module_payload.get("dataRoute", MANUFACTURING_DATA_ROUTE)),
        "folder": str(bundle.get("folder", "")),
        "documents": visible_documents,
        "currentDocumentKey": selected_operation,
        "recentProductions": module_payload.get("recentProductions", []) if isinstance(module_payload.get("recentProductions"), list) else [],
        "selectionState": module_payload.get("selectionState", {}) if isinstance(module_payload.get("selectionState"), dict) else {},
        "stateRoute": str(module_payload.get("stateRoute", MANUFACTURING_STATE_ROUTE)),
        "partialQuantityState": module_payload.get("partialQuantityState", {}) if isinstance(module_payload.get("partialQuantityState"), dict) else {},
        "partialQtyRoute": str(module_payload.get("partialQtyRoute", MANUFACTURING_PARTIAL_QTY_ROUTE)),
        "reportReadyRoute": str(module_payload.get("reportReadyRoute", MANUFACTURING_REPORT_READY_ROUTE)),
        "topfloorBoxRoute": str(module_payload.get("topfloorBoxRoute", MANUFACTURING_TOPFLOOR_BOX_ROUTE)),
        "rowEditRoute": str(module_payload.get("rowEditRoute", "")),
        "topfloorStorageBoxTypes": (
            module_payload.get("topfloorStorageBoxTypes", [])
            if isinstance(module_payload.get("topfloorStorageBoxTypes"), list)
            else []
        ),
        "message": str(module_payload.get("message", "")),
        "success": bool(module_payload.get("success", False)),
    }

def render_manufacturing_module(
    production_number: str = "",
    operation: str = "",
    message: str = "",
    success: bool = False,
    route: str = MANUFACTURING_ROUTE,
) -> bytes:
    """Render the manufacturing HTML page for the selected operation."""
    payload = manufacturing_module_payload(
        production_number=production_number,
        operation=operation,
        message=message,
        success=success,
        route=route,
    )
    return render_manufacturing_page(
        route=str(payload.get("route", MANUFACTURING_ROUTE)),
        data_route=str(payload.get("dataRoute", MANUFACTURING_DATA_ROUTE)),
        state_route=str(payload.get("stateRoute", MANUFACTURING_STATE_ROUTE)),
        partial_qty_route=str(payload.get("partialQtyRoute", MANUFACTURING_PARTIAL_QTY_ROUTE)),
        report_ready_route=str(payload.get("reportReadyRoute", MANUFACTURING_REPORT_READY_ROUTE)),
        topfloor_box_route=str(payload.get("topfloorBoxRoute", MANUFACTURING_TOPFLOOR_BOX_ROUTE)),
        row_edit_route=str(payload.get("rowEditRoute", "")),
        topfloor_storage_box_types=payload.get("topfloorStorageBoxTypes", []) if isinstance(payload.get("topfloorStorageBoxTypes"), list) else [],
        selected_number=str(payload.get("productionNumber", "")),
        operations=payload.get("operations", []) if isinstance(payload.get("operations"), list) else [],
        selected_operation=str(payload.get("selectedOperation", "")),
        recent_productions=payload.get("recentProductions", []) if isinstance(payload.get("recentProductions"), list) else [],
        production_client_cache=payload.get("productionClientCache", []) if isinstance(payload.get("productionClientCache"), list) else [],
        bundle=payload.get("bundle", {}) if isinstance(payload.get("bundle"), dict) else {},
        selection_state=payload.get("selectionState", {}) if isinstance(payload.get("selectionState"), dict) else {},
        partial_quantity_state=payload.get("partialQuantityState", {}) if isinstance(payload.get("partialQuantityState"), dict) else {},
        message=str(payload.get("message", "")),
        success=bool(payload.get("success", False)),
    )

def _prime_manufacturing_cache_worker(*, include_all_red_view: bool = False, limit: int = 10) -> None:
    """Warm bundle, view, and operation-state-key caches in the background."""
    try:
        entries_by_number: dict[str, dict[str, str]] = {}
        for operation_key, _operation_label in MANUFACTURING_OPERATION_DEFINITIONS:
            for entry in available_production_entries(limit=12, ready_only=True, operation=operation_key):
                normalized_number = _manufacturing_normalize_number(entry.get("number", ""))
                if normalized_number and normalized_number not in entries_by_number:
                    entries_by_number[normalized_number] = dict(entry)
        entries = list(entries_by_number.values())
        numbers = [
            _manufacturing_normalize_number(item.get("number", ""))
            for item in entries
            if _manufacturing_normalize_number(item.get("number", ""))
        ]
        if not numbers:
            latest_number = latest_production_number()
            if latest_number:
                numbers = [latest_number]
        # Warm recent productions so switching between them is noticeably faster.
        for number in numbers[: max(1, int(limit))]:
            try:
                raw_bundle = _load_manufacturing_bundle_cached(number)
                current_selection_state = load_selection_state(runtime_dir(), number)
                _manufacturing_view_bundle(
                    raw_bundle,
                    number,
                    current_selection_state,
                    include_all_red_view=include_all_red_view,
                )
                for operation_key, _operation_label in MANUFACTURING_OPERATION_DEFINITIONS:
                    _manufacturing_operation_state_keys(number, operation_key)
            except Exception:
                continue
    except Exception:
        pass

def _prime_manufacturing_cache_async() -> None:
    """Start asynchronous manufacturing cache priming."""
    threading.Thread(
        target=_prime_manufacturing_cache_worker,
        kwargs={"include_all_red_view": True, "limit": 10},
        name="manufacturing-prime",
        daemon=True,
    ).start()


__all__ = [name for name in globals() if not name.startswith("__")]
