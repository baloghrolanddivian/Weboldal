from __future__ import annotations

import html
import hashlib
import io
import json
import ssl
import base64
import mimetypes
import os
import sqlite3
import re
import subprocess
import sys
import time
import threading
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import uuid
import zipfile
import zlib
import csv
import calendar as month_calendar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import winreg
except Exception:  # pragma: no cover - Windows-only optional import
    winreg = None

from nettfront_module import (
    build_compare_artifacts,
    build_procurement_artifacts,
    create_bundle_archive,
    load_alkatresz_map,
    load_alkatresz_map_from_bytes,
)
from nettfront_order_module import (
    NettfrontOrderRow,
    build_order_suggestions,
    calc_total_m2_from_rows,
    rows_to_approved_workbook,
    rows_to_suggestion_workbook,
)
from manufacturing_module import (
    _pdf_lines as manufacturing_pdf_lines,
    available_production_entries,
    available_production_numbers,
    latest_production_number,
    load_partial_quantity_state,
    load_production_bundle,
    load_selection_state,
    production_folder as manufacturing_production_folder,
    save_partial_quantity_state,
    save_selection_state,
)
from manufacturing_view import render_manufacturing_page
from matt_inventory_module import (
    MattInventoryReport,
    build_matt_inventory_alert_workbook,
    build_matt_inventory_report,
    file_name_allowed as matt_inventory_file_name_allowed,
    load_report_from_path as load_matt_inventory_report_from_path,
    read_bytes_if_exists as matt_inventory_read_bytes_if_exists,
    save_report_to_path as save_matt_inventory_report_to_path,
    write_runtime_upload as write_matt_inventory_runtime_upload,
)
from front_inventory_module import (
    build_front_inventory_insight_artifacts,
    build_inventory_check_workbook,
    build_front_inventory_session,
    summarize_missing_inputs,
    build_front_inventory_view_model,
    file_name_allowed as front_inventory_file_name_allowed,
    finalize_inventory,
    load_session_from_path as load_front_inventory_session_from_path,
    read_bytes_if_exists as front_inventory_read_bytes_if_exists,
    run_inventory_check,
    save_session_to_path as save_front_inventory_session_to_path,
    update_row_input,
    write_runtime_upload as write_front_inventory_runtime_upload,
)
from material_inventory_module import (
    build_material_inventory_insight_workbook,
    build_material_inventory_session,
    build_material_inventory_summary_workbook,
    build_material_inventory_view_model,
    build_semifinished_front_inventory_session,
    build_semifinished_inventory_session,
    file_name_allowed as material_inventory_file_name_allowed,
    finalize_material_inventory,
    load_session_from_path as load_material_inventory_session_from_path,
    save_session_to_path as save_material_inventory_session_to_path,
    update_material_row_input,
    write_runtime_upload as write_material_inventory_runtime_upload,
)
from procurement_helper import (
    get_procurement_helper_state,
    launch_procurement_helper,
    stop_procurement_helper,
)

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency handling
    PdfReader = None

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - optional dependency handling
    load_workbook = None


HOST = "0.0.0.0"
PORT = int(os.getenv("DIVIAN_HUB_PORT", "5000"))
NO_DATA = "Nincs adat"
BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
SAVED_SELLER_VAT_NUMBERS = {
    "kronospan": "SK2020070866",
}
DEV_RELOAD_ROUTE = "/__dev__/events"
DEV_CHILD_ENV = "DIVIAN_HUB_DEV_CHILD"
DEV_RELOAD_TOKEN_ENV = "DIVIAN_HUB_RELOAD_TOKEN"
DEV_RELOAD_ENABLED = os.getenv("DIVIAN_HUB_DEV_RELOAD", "1") != "0"
DEV_WATCH_INTERVAL_SECONDS = 0.75
DEV_EVENT_HEARTBEAT_SECONDS = 10
WATCHED_EXTENSIONS = {".py", ".html", ".css", ".js", ".json", ".xlsx", ".xlsm", ".csv"}
WATCHED_FILES = {"requirements.txt"}
WATCH_IGNORED_DIRS = {".git", "__pycache__", "runtime", ".venv", "venv", "node_modules"}


def _normalize_path(raw_path: str) -> str:
    """Return the decoded request path without query string."""
    return urllib.parse.unquote(urllib.parse.urlsplit(raw_path).path)


def _load_static_asset(path: str) -> tuple[bytes, str] | None:
    if path in {"", "/"}:
        file_path = BASE_DIR / "index.html"
    else:
        relative = path.lstrip("/")
        if not relative or ".." in Path(relative).parts:
            return None
        file_path = (BASE_DIR / relative).resolve()
        try:
            file_path.relative_to(BASE_DIR)
        except ValueError:
            return None

    if not file_path.is_file():
        return None

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if file_path.suffix.lower() in {".html", ".css", ".js", ".json", ".txt", ".svg"}:
        content_type = f"{content_type}; charset=utf-8"
    return file_path.read_bytes(), content_type


def _extract_uploaded_file_parts(headers, body: bytes) -> list[tuple[str, str, bytes]]:
    content_type = headers.get("Content-Type", "")
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
    if "multipart/form-data" not in content_type or not boundary_match:
        return []

    boundary = boundary_match.group(1).encode()
    parts: list[tuple[str, str, bytes]] = []
    for part in body.split(b"--" + boundary):
        header, _, payload = part.partition(b"\r\n\r\n")
        if not payload:
            continue

        payload = payload.rsplit(b"\r\n", 1)[0]
        field_match = re.search(br'name="([^"]+)"', header)
        if not field_match:
            continue

        field_name = field_match.group(1).decode("utf-8", errors="ignore")
        name_match = re.search(br'filename="([^"]*)"', header)
        file_name = name_match.group(1).decode("utf-8", errors="ignore") if name_match else ""
        if file_name and payload:
            parts.append((field_name, file_name, payload))

    return parts


def _extract_uploaded_files(headers, body: bytes) -> dict[str, tuple[str, bytes]]:
    files: dict[str, tuple[str, bytes]] = {}
    for field_name, file_name, payload in _extract_uploaded_file_parts(headers, body):
        if field_name not in files:
            files[field_name] = (file_name, payload)
    return files


APP_ROUTE = "/apps/szamla-magyarito"
GENERATE_ROUTE = f"{APP_ROUTE}/generate"
NETTFRONT_ROUTE = "/apps/nettfront-olvaso"
NETTFRONT_PROCESS_ROUTE = f"{NETTFRONT_ROUTE}/process"
NETTFRONT_DOWNLOAD_PREFIX = f"{NETTFRONT_ROUTE}/download"
NETTFRONT_LAUNCH_PREFIX = f"{NETTFRONT_ROUTE}/launch"
NETTFRONT_PROCUREMENT_ROUTE = "/apps/nettfront-beszerzes"
NETTFRONT_PROCUREMENT_PROCESS_ROUTE = f"{NETTFRONT_PROCUREMENT_ROUTE}/process"
NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/download"
NETTFRONT_PROCUREMENT_LAUNCH_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/launch"
NETTFRONT_PROCUREMENT_STOP_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/stop"
NETTFRONT_PROCUREMENT_PARTS_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/alkatreszlista"
NETTFRONT_COMPARE_ROUTE = "/apps/nettfront-ellenorzes"
NETTFRONT_COMPARE_PROCESS_ROUTE = f"{NETTFRONT_COMPARE_ROUTE}/process"
NETTFRONT_COMPARE_DOWNLOAD_PREFIX = f"{NETTFRONT_COMPARE_ROUTE}/download"
NETTFRONT_ORDER_ROUTE = "/apps/nettfront-rendeles"
NETTFRONT_ORDER_PROCESS_ROUTE = f"{NETTFRONT_ORDER_ROUTE}/process"
NETTFRONT_ORDER_APPROVE_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/approve"
NETTFRONT_ORDER_DOWNLOAD_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/download"
NETTFRONT_ORDER_LAUNCH_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/launch"
NETTFRONT_ORDER_STOP_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/stop"
NETTFRONT_RUNTIME_DIR = RUNTIME_DIR / "nettfront"
NETTFRONT_PROCUREMENT_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "procurement"
NETTFRONT_COMPARE_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "compare"
NETTFRONT_ORDER_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "order"
NETTFRONT_ORDER_DEFAULT_AVG_PATH = BASE_DIR / "data" / "nettfront-rendeles-atlag.xlsx"
COMMON_SCRIPT_TAG = '<script src="/script.js"></script>'
VACATION_CALENDAR_ROUTE = "/apps/szabadsag-naptar"
VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/mentes"
VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/torles"
VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/mentes"
VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/torles"
VACATION_CALENDAR_LEAVE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/mentes"
VACATION_CALENDAR_LEAVE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/torles"
MANUFACTURING_ROUTE = "/apps/gyartasi-papirok"
MANUFACTURING_STATE_ROUTE = f"{MANUFACTURING_ROUTE}/state"
MANUFACTURING_PARTIAL_QTY_ROUTE = f"{MANUFACTURING_ROUTE}/partial-qty"
MANUFACTURING_REPORT_READY_ROUTE = f"{MANUFACTURING_ROUTE}/report-ready"
SHOPFLOOR_BASE_URL = os.getenv("SHOPFLOOR_BASE_URL", "https://app01.internal.divian.hu:9000").rstrip("/")
SHOPFLOOR_USERNAME = os.getenv("SHOPFLOOR_USERNAME", "alkatresz")
SHOPFLOOR_PASSWORD = os.getenv("SHOPFLOOR_PASSWORD", "PPddaa1234")
SHOPFLOOR_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_CHECKPOINT_ID", "103"))
SHOPFLOOR_TAB_ID = int(os.getenv("SHOPFLOOR_TAB_ID", "178"))
SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID", "104"))
SHOPFLOOR_ASSEMBLY_TAB_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_TAB_ID", "181"))
SHOPFLOOR_PROCESS_PAYLOAD = {
    "allowAnonymousInventory": False,
    "cdsmId": 4,
    "coPromptForScanQty": False,
    "coSequence": 2,
    "conId": 0,
    "contId": 2,
    "contextId": 1,
    "cptSubAltOperations": True,
    "doLoadConfirm": False,
    "doPromptForScanQty": False,
    "enableWorkOrderOperations": True,
    "isAnonymousInventory": None,
    "isDuplicateScan": False,
    "lcId": None,
    "manualIssueXml": None,
    "needsConfirmation": True,
    "oprId": 153,
    "oprIdAlt": 0,
    "oprIdSub": 0,
    "sttId": 3003,
    "validateData": None,
}
MATT_INVENTORY_ROUTE = "/apps/matt-raktarertek"
MATT_INVENTORY_PROCESS_ROUTE = f"{MATT_INVENTORY_ROUTE}/process"
MATT_INVENTORY_DOWNLOAD_ROUTE = f"{MATT_INVENTORY_ROUTE}/download/excel"
FRONT_INVENTORY_ROUTE = "/apps/front-leltar"
FRONT_INVENTORY_PROCESS_ROUTE = f"{FRONT_INVENTORY_ROUTE}/process"
FRONT_INVENTORY_STATE_ROUTE = f"{FRONT_INVENTORY_ROUTE}/state"
FRONT_INVENTORY_CHECK_ROUTE = f"{FRONT_INVENTORY_ROUTE}/ellenorzes"
FRONT_INVENTORY_FINALIZE_ROUTE = f"{FRONT_INVENTORY_ROUTE}/veglegesites"
FRONT_INVENTORY_PRESENCE_ROUTE = f"{FRONT_INVENTORY_ROUTE}/presence"
FRONT_INVENTORY_MISSING_ROUTE = f"{FRONT_INVENTORY_ROUTE}/hianyzo-darabszamok"
FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE = f"{FRONT_INVENTORY_ROUTE}/download/ellenorzes"
FRONT_INVENTORY_INSIGHT_EXCEL_DOWNLOAD_ROUTE = f"{FRONT_INVENTORY_ROUTE}/download/insight-excel"
FRONT_INVENTORY_INSIGHT_SCRIPT_DOWNLOAD_ROUTE = f"{FRONT_INVENTORY_ROUTE}/download/insight-script"
FRONT_INVENTORY_ALERT_CLEAR_ROUTE = f"{FRONT_INVENTORY_ROUTE}/alert-clear"
MATERIAL_INVENTORY_ROUTE = "/apps/anyag-raktar"
MATERIAL_INVENTORY_PROCESS_ROUTE = f"{MATERIAL_INVENTORY_ROUTE}/process"
MATERIAL_INVENTORY_STATE_ROUTE = f"{MATERIAL_INVENTORY_ROUTE}/state"
MATERIAL_INVENTORY_FINALIZE_ROUTE = f"{MATERIAL_INVENTORY_ROUTE}/veglegesites"
MATERIAL_INVENTORY_INSIGHT_DOWNLOAD_ROUTE = f"{MATERIAL_INVENTORY_ROUTE}/download/insight"
MATERIAL_INVENTORY_SUMMARY_DOWNLOAD_ROUTE = f"{MATERIAL_INVENTORY_ROUTE}/download/osszesito"
SEMIFINISHED_INVENTORY_ROUTE = "/apps/felkesz-raktar"
SEMIFINISHED_INVENTORY_PROCESS_ROUTE = f"{SEMIFINISHED_INVENTORY_ROUTE}/process"
SEMIFINISHED_INVENTORY_STATE_ROUTE = f"{SEMIFINISHED_INVENTORY_ROUTE}/state"
SEMIFINISHED_INVENTORY_FINALIZE_ROUTE = f"{SEMIFINISHED_INVENTORY_ROUTE}/veglegesites"
SEMIFINISHED_INVENTORY_INSIGHT_DOWNLOAD_ROUTE = f"{SEMIFINISHED_INVENTORY_ROUTE}/download/insight"
SEMIFINISHED_INVENTORY_SUMMARY_DOWNLOAD_ROUTE = f"{SEMIFINISHED_INVENTORY_ROUTE}/download/osszesito"
SEMIFINISHED_FRONT_INVENTORY_ROUTE = "/apps/felkesz-front"
SEMIFINISHED_FRONT_INVENTORY_PROCESS_ROUTE = f"{SEMIFINISHED_FRONT_INVENTORY_ROUTE}/process"
SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE = f"{SEMIFINISHED_FRONT_INVENTORY_ROUTE}/state"
SEMIFINISHED_FRONT_INVENTORY_FINALIZE_ROUTE = f"{SEMIFINISHED_FRONT_INVENTORY_ROUTE}/veglegesites"
SEMIFINISHED_FRONT_INVENTORY_INSIGHT_DOWNLOAD_ROUTE = f"{SEMIFINISHED_FRONT_INVENTORY_ROUTE}/download/insight"
SEMIFINISHED_FRONT_INVENTORY_SUMMARY_DOWNLOAD_ROUTE = f"{SEMIFINISHED_FRONT_INVENTORY_ROUTE}/download/osszesito"
VACATION_CALENDAR_RUNTIME_DIR = RUNTIME_DIR / "szabadsag-naptar"
VACATION_CALENDAR_DB = VACATION_CALENDAR_RUNTIME_DIR / "calendar.db"
MANUFACTURING_RUNTIME_DIR = RUNTIME_DIR / "gyartasi-papirok"
MATT_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "matt-raktarertek"
MATT_INVENTORY_REPORT_PATH = MATT_INVENTORY_RUNTIME_DIR / "latest-report.json"
MATT_INVENTORY_PRICE_META_PATH = MATT_INVENTORY_RUNTIME_DIR / "latest-price.json"
MATT_INVENTORY_STOCK_META_PATH = MATT_INVENTORY_RUNTIME_DIR / "latest-stock.json"
MATT_INVENTORY_ALERT_WORKBOOK_PATH = MATT_INVENTORY_RUNTIME_DIR / "matt-keszlet-riport.xlsx"
FRONT_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "front-leltar"
FRONT_INVENTORY_SESSION_PATH = FRONT_INVENTORY_RUNTIME_DIR / "session.json"
FRONT_INVENTORY_STOCK_META_PATH = FRONT_INVENTORY_RUNTIME_DIR / "latest-stock.json"
FRONT_INVENTORY_PRESENCE_PATH = FRONT_INVENTORY_RUNTIME_DIR / "presence.json"
FRONT_INVENTORY_CHECK_REPORT_PATH = FRONT_INVENTORY_RUNTIME_DIR / "ellenorzes-riport.xlsx"
FRONT_INVENTORY_CHECK_REPORT_META_PATH = FRONT_INVENTORY_RUNTIME_DIR / "ellenorzes-riport.json"
FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH = FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
FRONT_INVENTORY_INSIGHT_SCRIPT_PATH = FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.ahk"
FRONT_INVENTORY_INSIGHT_META_PATH = FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
MATERIAL_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "anyag-raktar"
MATERIAL_INVENTORY_SESSION_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "session.json"
MATERIAL_INVENTORY_STOCK_META_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "latest-stock.json"
MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
MATERIAL_INVENTORY_INSIGHT_META_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
MATERIAL_INVENTORY_SUMMARY_META_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "osszesito.json"
SEMIFINISHED_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "felkesz-raktar"
SEMIFINISHED_INVENTORY_SESSION_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "session.json"
SEMIFINISHED_INVENTORY_STOCK_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "latest-stock.json"
SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
SEMIFINISHED_INVENTORY_INSIGHT_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
SEMIFINISHED_INVENTORY_SUMMARY_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "osszesito.json"
SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "felkesz-front"
SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "session.json"
SEMIFINISHED_FRONT_INVENTORY_STOCK_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "latest-stock.json"
SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "osszesito.json"
MANUFACTURING_BUNDLE_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_BUNDLE_CACHE_LOCK = threading.Lock()
MANUFACTURING_BUNDLE_FAST_TTL_SECONDS = 900.0
MANUFACTURING_SIGNATURE_CACHE_TTL_SECONDS = 180.0
MANUFACTURING_SIGNATURE_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_BUNDLE_DISK_CACHE_DIR = MANUFACTURING_RUNTIME_DIR / "bundle-cache"
MANUFACTURING_BUNDLE_SCHEMA_VERSION = "2026-05-20-cnc-xml-default-v62"
MANUFACTURING_OPERATION_STATE_KEYS_CACHE: dict[tuple[str, str], dict[str, object]] = {}
MANUFACTURING_PRIME_SYNC_ON_START = False


def _dev_reload_token() -> str:
    return os.getenv(DEV_RELOAD_TOKEN_ENV, "dev-static")


def _read_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    if os.name == "nt" and winreg is not None:
        registry_paths = (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        )
        for root, subkey in registry_paths:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    stored_value, _ = winreg.QueryValueEx(key, name)
                if stored_value:
                    return str(stored_value)
            except OSError:
                continue

    return default


def _should_watch_path(path: Path) -> bool:
    if any(part in WATCH_IGNORED_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in WATCHED_EXTENSIONS or path.name in WATCHED_FILES


def _build_watch_snapshot() -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for file_path in BASE_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(BASE_DIR)
        if not _should_watch_path(relative_path):
            continue
        stat = file_path.stat()
        snapshot[str(relative_path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _spawn_dev_child(reload_token: str) -> subprocess.Popen:
    env = os.environ.copy()
    env[DEV_CHILD_ENV] = "1"
    env[DEV_RELOAD_TOKEN_ENV] = reload_token
    return subprocess.Popen([sys.executable, __file__], cwd=BASE_DIR, env=env)


def _run_dev_supervisor() -> None:
    reload_counter = 0
    snapshot = _build_watch_snapshot()
    child = _spawn_dev_child(f"reload-{reload_counter}")
    print(f"Dev reload supervisor active on http://localhost:{PORT}")

    try:
        while True:
            time.sleep(DEV_WATCH_INTERVAL_SECONDS)
            next_snapshot = _build_watch_snapshot()
            changed = next_snapshot != snapshot
            child_exited = child is not None and child.poll() is not None

            if not changed:
                if child is None:
                    continue
                if not child_exited:
                    continue
                print("A fejlesztoi szerver leallt. A kovetkezo modositasnal ujraindul.")
                child = None
                continue

            snapshot = next_snapshot
            reload_counter += 1
            print("Valtozas eszlelve, szerver ujrainditas...")

            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

            child = _spawn_dev_child(f"reload-{reload_counter}")
    except KeyboardInterrupt:
        print("\nFejlesztoi szerver leallitva.")
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


VACATION_MONTH_NAMES = (
    "",
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)
VACATION_WEEKDAY_LABELS = ("H", "K", "Sze", "Cs", "P", "Szo", "V")


def _vacation_db_connection() -> sqlite3.Connection:
    VACATION_CALENDAR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(VACATION_CALENDAR_DB)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS vacation_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            max_absent INTEGER NOT NULL DEFAULT 1 CHECK (max_absent >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employee_departments (
            employee_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            PRIMARY KEY (employee_id, department_id),
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES vacation_departments(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS vacation_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE
        );
        """
    )
    return connection


def _vacation_parse_month(month_value: str) -> date:
    clean_value = month_value.strip()
    if clean_value:
        try:
            parsed = datetime.strptime(clean_value, "%Y-%m")
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass
    today = date.today()
    return date(today.year, today.month, 1)


def _vacation_month_value(month_start: date) -> str:
    return month_start.strftime("%Y-%m")


def _vacation_month_label(month_start: date) -> str:
    return f"{month_start.year}. {VACATION_MONTH_NAMES[month_start.month]}"


def _vacation_next_month(month_start: date, offset: int) -> date:
    year = month_start.year + ((month_start.month - 1 + offset) // 12)
    month = ((month_start.month - 1 + offset) % 12) + 1
    return date(year, month, 1)


def _vacation_month_bounds(month_start: date) -> tuple[date, date]:
    next_month = _vacation_next_month(month_start, 1)
    return month_start, next_month - timedelta(days=1)


def _vacation_parse_date(value: str) -> date | None:
    clean_value = value.strip()
    if not clean_value:
        return None
    for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(clean_value, pattern).date()
        except ValueError:
            continue
    return None


def _vacation_date_value(day: date) -> str:
    return day.isoformat()


def _vacation_date_label(day: date) -> str:
    return day.strftime("%Y.%m.%d")


def _vacation_now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _vacation_parse_int(value: str, default: int | None = None) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError, AttributeError):
        return default


def _vacation_parse_form(raw_body: bytes) -> dict[str, list[str]]:
    parsed = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return {key: value for key, value in parsed.items()}


def _parse_urlencoded_body(body: bytes) -> dict[str, str]:
    try:
        payload = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        payload = urllib.parse.parse_qs(body.decode("latin1"), keep_blank_values=True)
    return {key: values[-1] for key, values in payload.items() if values}


def _vacation_form_value(form_data: dict[str, list[str]], name: str) -> str:
    values = form_data.get(name, [])
    return values[-1].strip() if values else ""


def _vacation_form_values(form_data: dict[str, list[str]], name: str) -> list[str]:
    return [value.strip() for value in form_data.get(name, []) if value.strip()]


def _vacation_fetch_departments(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            d.id,
            d.name,
            d.max_absent,
            COUNT(ed.employee_id) AS employee_count
        FROM vacation_departments d
        LEFT JOIN vacation_employee_departments ed ON ed.department_id = d.id
        GROUP BY d.id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "max_absent": int(row["max_absent"]),
            "employee_count": int(row["employee_count"] or 0),
        }
        for row in rows
    ]


def _vacation_fetch_department(connection: sqlite3.Connection, department_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT id, name, max_absent
        FROM vacation_departments
        WHERE id = ?
        """,
        (department_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": int(row["id"]), "name": str(row["name"]), "max_absent": int(row["max_absent"])}


def _vacation_employee_department_map(connection: sqlite3.Connection) -> dict[int, list[dict]]:
    rows = connection.execute(
        """
        SELECT
            ed.employee_id,
            d.id AS department_id,
            d.name,
            d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    mapping: dict[int, list[dict]] = {}
    for row in rows:
        mapping.setdefault(int(row["employee_id"]), []).append(
            {
                "id": int(row["department_id"]),
                "name": str(row["name"]),
                "max_absent": int(row["max_absent"]),
            }
        )
    return mapping


def _vacation_fetch_employees(connection: sqlite3.Connection) -> list[dict]:
    department_map = _vacation_employee_department_map(connection)
    rows = connection.execute(
        """
        SELECT
            e.id,
            e.name,
            COUNT(v.id) AS vacation_count
        FROM vacation_employees e
        LEFT JOIN vacation_entries v ON v.employee_id = e.id
        GROUP BY e.id
        ORDER BY e.name COLLATE NOCASE
        """
    ).fetchall()
    employees: list[dict] = []
    for row in rows:
        department_items = department_map.get(int(row["id"]), [])
        employees.append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "vacation_count": int(row["vacation_count"] or 0),
                "departments": department_items,
                "department_ids": [int(item["id"]) for item in department_items],
                "department_names": [str(item["name"]) for item in department_items],
            }
        )
    return employees


def _vacation_fetch_employee(connection: sqlite3.Connection, employee_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT id, name
        FROM vacation_employees
        WHERE id = ?
        """,
        (employee_id,),
    ).fetchone()
    if row is None:
        return None

    department_rows = connection.execute(
        """
        SELECT d.id, d.name, d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        WHERE ed.employee_id = ?
        ORDER BY d.name COLLATE NOCASE
        """,
        (employee_id,),
    ).fetchall()
    departments = [
        {"id": int(item["id"]), "name": str(item["name"]), "max_absent": int(item["max_absent"])}
        for item in department_rows
    ]
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "departments": departments,
        "department_ids": [int(item["id"]) for item in departments],
        "department_names": [str(item["name"]) for item in departments],
    }


def _vacation_fetch_leave(connection: sqlite3.Connection, leave_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.id = ?
        """,
        (leave_id,),
    ).fetchone()
    if row is None:
        return None

    employee = _vacation_fetch_employee(connection, int(row["employee_id"]))
    return {
        "id": int(row["id"]),
        "employee_id": int(row["employee_id"]),
        "employee_name": str(row["employee_name"]),
        "start_date": str(row["start_date"]),
        "end_date": str(row["end_date"]),
        "note": str(row["note"] or ""),
        "departments": employee["departments"] if employee else [],
    }


def _vacation_fetch_leaves_in_range(connection: sqlite3.Connection, start_day: date, end_day: date) -> list[dict]:
    employee_map = {item["id"]: item for item in _vacation_fetch_employees(connection)}
    rows = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.start_date <= ? AND v.end_date >= ?
        ORDER BY v.start_date, e.name COLLATE NOCASE
        """,
        (_vacation_date_value(end_day), _vacation_date_value(start_day)),
    ).fetchall()

    leaves: list[dict] = []
    for row in rows:
        employee = employee_map.get(int(row["employee_id"]), {})
        leaves.append(
            {
                "id": int(row["id"]),
                "employee_id": int(row["employee_id"]),
                "employee_name": str(row["employee_name"]),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "note": str(row["note"] or ""),
                "departments": employee.get("departments", []),
                "department_names": employee.get("department_names", []),
            }
        )
    return leaves


def _vacation_overlaps_existing_leave(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> bool:
    query = """
        SELECT 1
        FROM vacation_entries
        WHERE employee_id = ?
          AND start_date <= ?
          AND end_date >= ?
    """
    params: list[object] = [employee_id, _vacation_date_value(end_day), _vacation_date_value(start_day)]
    if exclude_leave_id is not None:
        query += " AND id <> ?"
        params.append(exclude_leave_id)
    row = connection.execute(query, params).fetchone()
    return row is not None


def _vacation_validate_department_limits(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> tuple[bool, str]:
    employee = _vacation_fetch_employee(connection, employee_id)
    if employee is None:
        return False, "A kiválasztott kolléga nem található."
    if not employee["departments"]:
        return False, "A kollégához legalább egy részleget be kell állítani."

    current_day = start_day
    while current_day <= end_day:
        day_value = _vacation_date_value(current_day)
        for department in employee["departments"]:
            absent_row = connection.execute(
                """
                SELECT COUNT(DISTINCT v.employee_id) AS absent_count
                FROM vacation_entries v
                JOIN vacation_employee_departments ed ON ed.employee_id = v.employee_id
                WHERE ed.department_id = ?
                  AND v.start_date <= ?
                  AND v.end_date >= ?
                  AND (? IS NULL OR v.id <> ?)
                """,
                (department["id"], day_value, day_value, exclude_leave_id, exclude_leave_id),
            ).fetchone()
            absent_count = int(absent_row["absent_count"] or 0) if absent_row else 0
            if absent_count + 1 > int(department["max_absent"]):
                return (
                    False,
                    f"A(z) {department['name']} részlegen {_vacation_date_label(current_day)} napon már elértétek a szabadságlimitet.",
                )
        current_day += timedelta(days=1)
    return True, ""


def _vacation_save_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    max_absent = _vacation_parse_int(_vacation_form_value(form_data, "max_absent"), default=1)

    if not name:
        return False, "A részleg neve kötelező."
    if max_absent is None or max_absent < 0:
        return False, "A részleg limitje 0 vagy nagyobb szám lehet."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            if department_id:
                exists = _vacation_fetch_department(connection, department_id)
                if exists is None:
                    return False, "A kiválasztott részleg nem található."
                connection.execute(
                    """
                    UPDATE vacation_departments
                    SET name = ?, max_absent = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, max_absent, now_stamp, department_id),
                )
                return True, f"Frissítve: {name}"

            connection.execute(
                """
                INSERT INTO vacation_departments (name, max_absent, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, max_absent, now_stamp, now_stamp),
            )
            return True, f"Létrehozva: {name}"
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű részleg már létezik."


def _vacation_delete_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    if department_id is None:
        return False, "A törlendő részleg nem azonosítható."

    with _vacation_db_connection() as connection:
        department = _vacation_fetch_department(connection, department_id)
        if department is None:
            return False, "A törlendő részleg nem található."

        assigned_row = connection.execute(
            "SELECT COUNT(*) AS count FROM vacation_employee_departments WHERE department_id = ?",
            (department_id,),
        ).fetchone()
        if assigned_row and int(assigned_row["count"] or 0) > 0:
            return False, "A részleg még kollégákhoz van rendelve. Előbb vedd le onnan."

        connection.execute("DELETE FROM vacation_departments WHERE id = ?", (department_id,))
    return True, f"Törölve: {department['name']}"


def _vacation_save_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    department_ids = sorted(
        {
            department_id
            for raw_value in _vacation_form_values(form_data, "department_ids")
            for department_id in [_vacation_parse_int(raw_value)]
            if department_id is not None
        }
    )

    if not name:
        return False, "A kolléga neve kötelező."
    if not department_ids:
        return False, "A kollégához legalább egy részleget válassz ki."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            valid_departments = {
                int(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM vacation_departments WHERE id IN ({','.join('?' for _ in department_ids)})",
                    department_ids,
                ).fetchall()
            }
            if len(valid_departments) != len(department_ids):
                return False, "A kiválasztott részlegek között van érvénytelen."

            if employee_id:
                employee = _vacation_fetch_employee(connection, employee_id)
                if employee is None:
                    return False, "A kiválasztott kolléga nem található."
                connection.execute(
                    """
                    UPDATE vacation_employees
                    SET name = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, now_stamp, employee_id),
                )
                connection.execute("DELETE FROM vacation_employee_departments WHERE employee_id = ?", (employee_id,))
                target_id = employee_id
                message = f"Frissítve: {name}"
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO vacation_employees (name, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (name, now_stamp, now_stamp),
                )
                target_id = int(cursor.lastrowid)
                message = f"Létrehozva: {name}"

            connection.executemany(
                """
                INSERT INTO vacation_employee_departments (employee_id, department_id)
                VALUES (?, ?)
                """,
                [(target_id, department_id) for department_id in department_ids],
            )
            return True, message
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű kolléga már létezik."


def _vacation_delete_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    if employee_id is None:
        return False, "A törlendő kolléga nem azonosítható."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A törlendő kolléga nem található."
        connection.execute("DELETE FROM vacation_employees WHERE id = ?", (employee_id,))
    return True, f"Törölve: {employee['name']}"


def _vacation_save_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    start_day = _vacation_parse_date(_vacation_form_value(form_data, "start_date"))
    end_day = _vacation_parse_date(_vacation_form_value(form_data, "end_date"))
    note = _clean_spaces(_vacation_form_value(form_data, "note"))

    if employee_id is None:
        return False, "A szabadsághoz válassz ki egy kollégát."
    if start_day is None or end_day is None:
        return False, "A szabadság kezdete és vége kötelező."
    if end_day < start_day:
        return False, "A szabadság vége nem lehet korábbi, mint a kezdete."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A kiválasztott kolléga nem található."
        if not employee["departments"]:
            return False, "A kollégához nincs részleg beállítva, ezért nem ellenőrizhető a limit."
        if _vacation_overlaps_existing_leave(connection, employee_id, start_day, end_day, exclude_leave_id=leave_id):
            return False, "Ehhez a kollégához már van átfedő szabadság felvéve."

        valid, message = _vacation_validate_department_limits(
            connection,
            employee_id,
            start_day,
            end_day,
            exclude_leave_id=leave_id,
        )
        if not valid:
            return False, message

        now_stamp = _vacation_now_stamp()
        if leave_id:
            existing = _vacation_fetch_leave(connection, leave_id)
            if existing is None:
                return False, "A kiválasztott szabadság nem található."
            connection.execute(
                """
                UPDATE vacation_entries
                SET employee_id = ?, start_date = ?, end_date = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, leave_id),
            )
            return True, f"Frissítve: {employee['name']} szabadsága"

        connection.execute(
            """
            INSERT INTO vacation_entries (employee_id, start_date, end_date, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, now_stamp),
        )
        return True, f"Felvéve: {employee['name']} szabadsága"


def _vacation_delete_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    if leave_id is None:
        return False, "A törlendő szabadság nem azonosítható."

    with _vacation_db_connection() as connection:
        leave_entry = _vacation_fetch_leave(connection, leave_id)
        if leave_entry is None:
            return False, "A törlendő szabadság nem található."
        connection.execute("DELETE FROM vacation_entries WHERE id = ?", (leave_id,))
    return True, f"Törölve: {leave_entry['employee_name']} szabadsága"


def _vacation_build_calendar(month_start: date, leaves: list[dict]) -> tuple[list[list[dict]], int]:
    month_end = _vacation_month_bounds(month_start)[1]
    day_map: dict[date, list[dict]] = {}
    limit_day_count = 0

    for leave_entry in leaves:
        leave_start = _vacation_parse_date(leave_entry["start_date"])
        leave_end = _vacation_parse_date(leave_entry["end_date"])
        if leave_start is None or leave_end is None:
            continue
        current_day = max(leave_start, month_start)
        final_day = min(leave_end, month_end)
        while current_day <= final_day:
            day_map.setdefault(current_day, []).append(leave_entry)
            current_day += timedelta(days=1)

    weeks: list[list[dict]] = []
    month_weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    for week in month_weeks:
        week_cells: list[dict] = []
        for day in week:
            entries = sorted(day_map.get(day, []), key=lambda item: item["employee_name"].lower())
            department_loads: dict[int, dict] = {}
            for entry in entries:
                for department in entry["departments"]:
                    info = department_loads.setdefault(
                        int(department["id"]),
                        {
                            "id": int(department["id"]),
                            "name": str(department["name"]),
                            "count": 0,
                            "max_absent": int(department["max_absent"]),
                        },
                    )
                    info["count"] += 1
            loads = sorted(department_loads.values(), key=lambda item: item["name"].lower())
            if day.month == month_start.month and any(item["count"] >= item["max_absent"] for item in loads):
                limit_day_count += 1
            week_cells.append(
                {
                    "date": day,
                    "is_current_month": day.month == month_start.month,
                    "entries": entries,
                    "loads": loads,
                }
            )
        weeks.append(week_cells)
    return weeks, limit_day_count


def _vacation_query_params(raw_path: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}


def _json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _manufacturing_query_params(raw_path: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}


def _manufacturing_normalize_number(value: object) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))


def _manufacturing_signature_key(signature: tuple[tuple[str, int, int], ...]) -> str:
    payload = json.dumps(
        {"schema": MANUFACTURING_BUNDLE_SCHEMA_VERSION, "signature": list(signature)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _manufacturing_disk_cache_path(production_number: str) -> Path:
    return MANUFACTURING_BUNDLE_DISK_CACHE_DIR / f"{production_number}.json"


def _read_manufacturing_disk_cache(production_number: str, signature: tuple[tuple[str, int, int], ...]) -> dict | None:
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


def _write_manufacturing_disk_cache(production_number: str, signature: tuple[tuple[str, int, int], ...], bundle: dict) -> None:
    try:
        MANUFACTURING_BUNDLE_DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _manufacturing_disk_cache_path(production_number)
        payload = {
            "signature_key": _manufacturing_signature_key(signature),
            "bundle": bundle,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _manufacturing_bundle_signature(production_number: str) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    normalized = _manufacturing_normalize_number(production_number)
    if not normalized:
        return "", tuple()

    now = time.time()
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached_signature = MANUFACTURING_SIGNATURE_CACHE.get(normalized)
        if cached_signature and (now - float(cached_signature.get("created_at", 0.0) or 0.0)) < MANUFACTURING_SIGNATURE_CACHE_TTL_SECONDS:
            return normalized, tuple(cached_signature.get("signature", tuple()))

    folder = manufacturing_production_folder(normalized)
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

    bundle = load_production_bundle(normalized)
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
            row_state_key = str(row.get("state_key", "")).strip() or str(row.get("row_id", "")).strip()
            if row_state_key:
                row_state_keys.append(row_state_key)
    return tuple(sorted(set(row_state_keys)))


def _manufacturing_operation_state_keys(production_number: str, operation_key: str) -> tuple[str, ...]:
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


MANUFACTURING_OPERATION_DEFINITIONS = (
    ("korpusz_osszekeszites", "Korpusz összekészítés"),
    ("front_osszekeszites", "Front összekészítés"),
    ("cnc_furas", "CNC fúrás"),
    ("pantolas", "Pántolás"),
)
MANUFACTURING_OPERATION_HINTS = {
    "korpusz_osszekeszites": "A jelenlegi korpusz nézet és a piros listák.",
    "front_osszekeszites": "A front összekészítő PDF sorai és kategóriái.",
    "cnc_furas": "CNC, alsó, felső és fiókelő/front fúrás egy közös műveleti nézetben.",
    "pantolas": "A Pántoló papír sorai eredeti sorrendben, zöld/piros jelöléssel.",
}
MANUFACTURING_SOURCE_LABELS = {
    "osszekeszito": "Összekészítő",
    "alkatresz_kesz": "Alkatrész kész",
    "front_osszekeszito": "Front összekészítő",
    "front_etikett": "Etikett frontok",
    "cnc": "CNC",
    "fiokelo_furas": "Fiókelő fúrás",
    "pantolo": "Pántoló",
}


def _manufacturing_state_key(production_number: str, row_id: str) -> str:
    normalized_number = _manufacturing_normalize_number(production_number)
    return f"{normalized_number}::{str(row_id or '').strip()}"


def _manufacturing_normalize_operation(value: object) -> str:
    normalized = str(value or "").strip().lower()
    allowed_keys = {key for key, _label in MANUFACTURING_OPERATION_DEFINITIONS}
    return normalized if normalized in allowed_keys else ""


def _manufacturing_selection_state_payload(production_number: str, raw_state: dict[str, str]) -> dict[str, str]:
    normalized_number = _manufacturing_normalize_number(production_number)
    result: dict[str, str] = {}
    for row_id, state in raw_state.items():
        clean_state = str(state or "").strip().lower()
        if clean_state not in {"green", "red", "done"}:
            continue
        result[_manufacturing_state_key(normalized_number, row_id)] = clean_state
    return result


def _manufacturing_row_with_context(row: dict, production_number: str, detail_suffix: str = "") -> dict:
    row_payload = dict(row)
    detail_text = str(row_payload.get("detail", "")).strip()
    if detail_suffix:
        row_payload["detail"] = f"{detail_text} · {detail_suffix}" if detail_text else detail_suffix
    row_payload["production_number"] = _manufacturing_normalize_number(production_number)
    row_payload["state_key"] = _manufacturing_state_key(production_number, str(row_payload.get("row_id", "")))
    return row_payload


def _manufacturing_local_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "szakasz"


def _shopfloor_auth_header() -> str:
    auth_raw = f"{SHOPFLOOR_USERNAME}:{SHOPFLOOR_PASSWORD}"
    auth_b64 = base64.b64encode(auth_raw.encode("utf-8", errors="ignore")).decode("ascii", errors="ignore")
    return f"Basic {auth_b64}"


def _shopfloor_negotiate_connection_id(auth_header: str) -> str:
    encoded_auth = urllib.parse.quote(auth_header, safe="")
    negotiate_url = f"{SHOPFLOOR_BASE_URL}/api/hubs/mainhub/negotiate?authorize={encoded_auth}&negotiateVersion=1"
    req = urllib.request.Request(
        negotiate_url,
        method="POST",
    )
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=context, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    connection_id = str(payload.get("connectionId", "")).strip()
    if not connection_id:
        raise RuntimeError("A shopfloor negotiate válaszban nincs connectionId.")
    return connection_id


def _shopfloor_process_payload(con_id: int, validate_data: object | None = None) -> bytes:
    payload = dict(SHOPFLOOR_PROCESS_PAYLOAD)
    payload["conId"] = con_id
    if validate_data is not None:
        payload["validateData"] = validate_data
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _shopfloor_extract_validate_data(response_body: str) -> object | None:
    try:
        payload = json.loads(response_body or "null")
    except json.JSONDecodeError:
        return None
    if payload is None:
        return None
    if isinstance(payload, dict):
        for key in ("validateData", "data", "result"):
            value = payload.get(key)
            if value is not None:
                return value
    return payload


def _shopfloor_report_con_ready(con_code: str, *, use_assembly_validate: bool = False) -> tuple[int, str, str]:
    con_text = str(con_code or "").strip().upper()
    match = re.fullmatch(r"CON(\d{1,12})", con_text)
    if not match:
        raise ValueError(f"Érvénytelen CON azonosító: {con_code}")
    con_id = int(match.group(1))

    auth_header = _shopfloor_auth_header()
    connection_id = _shopfloor_negotiate_connection_id(auth_header)
    checkpoint_id = SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID if use_assembly_validate else SHOPFLOOR_CHECKPOINT_ID
    tab_id = SHOPFLOOR_ASSEMBLY_TAB_ID if use_assembly_validate else SHOPFLOOR_TAB_ID
    quoted_connection_id = urllib.parse.quote(connection_id, safe="")
    request_body = _shopfloor_process_payload(con_id)
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    context = ssl._create_unverified_context()

    def endpoint_url(endpoint_name: str) -> str:
        return (
            f"{SHOPFLOOR_BASE_URL}/api/shopfloor/checkpoints/{checkpoint_id}"
            f"/tabs/{tab_id}/{endpoint_name}/{con_text}?connectionId={quoted_connection_id}"
        )

    def submit(endpoint_name: str, data: bytes) -> tuple[int, str]:
        req = urllib.request.Request(
            endpoint_url(endpoint_name),
            method="POST",
            data=data,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, context=context, timeout=20) as response:
                body = response.read().decode("utf-8", errors="ignore")
                return int(response.getcode() or 0), body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            return int(exc.code or 0), body

    if use_assembly_validate:
        validate_status_code, validate_response_body = submit("validatescan", request_body)
        if not 200 <= int(validate_status_code) < 300:
            return validate_status_code, validate_response_body, "validatescan"
        validate_data = _shopfloor_extract_validate_data(validate_response_body)
        process_body = _shopfloor_process_payload(con_id, validate_data)
        process_status_code, process_response_body = submit("processscan", process_body)
        return process_status_code, process_response_body, "processscan"

    status_code, response_body = submit("processscan", request_body)
    return status_code, response_body, "processscan"


def _extract_con_code(value: object) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"\bCON\D*?(\d{6,})\b", text)
    return f"CON{match.group(1)}" if match else ""


def _manufacturing_uses_assembly_ready_endpoint(category_key: object) -> bool:
    return str(category_key or "").strip() == "korpusz-osszekeszito"


def _manufacturing_document_sections(bundle: dict, production_number: str, allowed_document_keys: tuple[str, ...], include_source_prefix: bool = True) -> tuple[list[dict], int]:
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


def _manufacturing_korpusz_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    return _manufacturing_document_sections(bundle, production_number, ("osszekeszito", "alkatresz_kesz"), include_source_prefix=False)


def _manufacturing_front_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    raw_sections, row_count = _manufacturing_document_sections(bundle, production_number, ("front_osszekeszito", "front_etikett"))

    def folded(value: object) -> str:
        text = str(value or "").strip().lower()
        for source, target in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ö", "o"), ("ő", "o"), ("ú", "u"), ("ü", "u"), ("ű", "u"), ("õ", "o"), ("û", "u")):
            text = text.replace(source, target)
        return text

    def clean_text(value: object) -> str:
        text = (
            str(value or "")
            .strip()
            .replace("õ", "ő")
            .replace("Õ", "Ő")
            .replace("û", "ű")
            .replace("Û", "Ű")
        )
        fixes = {
            "fehé r": "fehér",
            "fehé r fóliás": "fehér fóliás",
            "kas mír": "kasmír",
            "kas mír fóliás": "kasmír fóliás",
            "prov ance": "provance",
            "prov ance fóliás": "provance fóliás",
            "beig e": "beige",
            "beig e fóliás": "beige fóliás",
            "Sonom a": "Sonoma",
            "sonom a": "sonoma",
            "capucci no": "cappuccino",
            "SM.fehé r": "SM.fehér",
            "SM.kas mír": "SM.kasmír",
            "SM.pro vance": "SM.provance",
            "SM.beig e": "SM.beige",
            "Mf. fehé r": "Mf. fehér",
            "Mf. capucci no": "Mf. cappuccino",
        }
        for source, target in fixes.items():
            text = text.replace(source, target)
        return text

    def size_sort_key(size_label: str) -> tuple[int, ...]:
        parts = [
            int(part.strip())
            for part in re.split(r"[xX]", str(size_label or ""))
            if part.strip().isdigit()
        ]
        return tuple(parts or [9999, 9999, 9999])

    def front_group_size_label(row: dict, size_label: str, type_label: str) -> str:
        source = " ".join(
            [
                str(row.get("section_label", "")).strip().lower(),
                str(row.get("name", "")).strip().lower(),
                str(type_label or "").strip().lower(),
            ]
        )
        if "as takar" not in source:
            return str(size_label or "").strip()

        parts = [part.strip() for part in re.split(r"[xX]", str(size_label or "")) if part.strip()]
        if len(parts) < 3:
            return str(size_label or "").strip()

        pair_values = {"81", "165"}
        if parts[0] in pair_values and parts[1] not in pair_values:
            parts[0] = "81/165"
        elif parts[1] in pair_values and parts[0] not in pair_values:
            parts[1] = "81/165"

        return " x ".join(parts)

    def front_material_label(row: dict) -> str:
        source = clean_text(f"{row.get('color', '')} {row.get('name', '')} {row.get('detail', '')}").lower()
        if "mf." in source or "sm." in source or "matt" in source:
            return "Fóliás"
        return "Bútorlapos"

    def display_row_name(row: dict) -> str:
        name = clean_text(row.get("name"))
        color = clean_text(row.get("color"))
        if not name:
            return "Front"
        if not color:
            return name
        name_parts = [part for part in name.split() if part]
        color_parts = [part for part in color.split() if part]
        if len(name_parts) > len(color_parts):
            if [folded(part) for part in name_parts[-len(color_parts):]] == [folded(part) for part in color_parts]:
                trimmed = " ".join(name_parts[:-len(color_parts)]).strip()
                if trimmed:
                    return trimmed
        return name

    def front_type_label(row: dict) -> str:
        section_label = clean_text(row.get("section_label"))
        parts = [clean_text(part) for part in section_label.split(" - ") if clean_text(part)]
        if parts and folded(parts[0]).startswith("front "):
            parts = parts[1:]
        if parts and re.fullmatch(r"[12]-es", folded(parts[0])):
            parts = parts[1:]
        color = clean_text(row.get("color"))
        if parts and color and folded(parts[-1]) == folded(color):
            parts = parts[:-1]
        return " - ".join(parts) if parts else display_row_name(row)

    def front_box_type_label(type_label: str) -> str:
        clean_type = clean_text(type_label)
        if "alsó kihúzható" in folded(clean_type):
            return "Fiókelő"
        for suffix in (" - Oldalra", " - Nincs"):
            if clean_type.endswith(suffix):
                return clean_type[: -len(suffix)].strip()
        return clean_type

    def front_model_label(row: dict) -> str:
        detail_text = clean_text(row.get("detail"))
        if "·" in detail_text:
            return clean_text(detail_text.split("·", 1)[0])
        if "-" in detail_text:
            return clean_text(detail_text.split("-", 1)[0])
        return ""

    def is_glass_row(row: dict, type_label: str) -> bool:
        combined = " ".join(
            [
                clean_text(row.get("name")),
                clean_text(row.get("detail")),
                clean_text(row.get("section_label")),
                clean_text(type_label),
            ]
        )
        return "uveges" in folded(combined) or "uveg" in folded(combined)

    def front_trait_label(row: dict, type_label: str) -> str:
        combined = " ".join(
            [
                clean_text(row.get("name")),
                clean_text(row.get("detail")),
                clean_text(row.get("section_label")),
                clean_text(type_label),
            ]
        )
        if "blende" in folded(combined):
            return "Blende"

        size_text = clean_text(row.get("size"))
        code_text = clean_text(row.get("code"))
        compact_size = re.sub(r"[^0-9X]", "", size_text.upper().replace("x", "X"))
        compact_code = re.sub(r"\s+", "", code_text).upper()
        if compact_size and re.search(re.escape(compact_size) + r"[JB]", compact_code):
            return "Íves"
        return "-"

    def is_curved_front_row(row: dict) -> bool:
        size_text = clean_text(row.get("size"))
        code_text = clean_text(row.get("code"))
        compact_size = re.sub(r"[^0-9X]", "", size_text.upper().replace("x", "X"))
        compact_code = re.sub(r"\s+", "", code_text).upper()
        if compact_size == "655X397X18":
            return True
        if compact_size == "718X297X18":
            combined = " ".join(
                [
                    clean_text(row.get("name")),
                    clean_text(row.get("detail")),
                    clean_text(row.get("section_label")),
                    clean_text(row.get("code")),
                ]
            ).upper()
            return "FZN" in combined
        return bool(compact_size and re.search(re.escape(compact_size) + r"[JB]", compact_code))

    grouped_sections: dict[str, dict] = {}
    for section in raw_sections:
        section_key_text = str(section.get("key", "")).strip().lower()
        row_source = "etikett" if section_key_text.startswith("front_etikett::") else "front"
        for raw_row in section.get("rows", []):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            size = clean_text(row.get("size")) or "Méret nélkül"
            material = front_material_label(row)
            type_label = front_type_label(row)
            box_type_label = front_box_type_label(type_label)
            group_size = front_group_size_label(row, size, box_type_label) or size
            section_key = f"{group_size}::{material}::{box_type_label}"
            section_slug = _manufacturing_local_slug(section_key)
            if section_slug not in grouped_sections:
                grouped_sections[section_slug] = {
                    "key": f"front_osszekeszito::{section_slug}",
                    "label": f"{size} · {material} · {box_type_label}",
                    "rows": [],
                }
            grouped_sections[section_slug]["label"] = f"{group_size} · {material} · {box_type_label}"
            row["name"] = clean_text(raw_row.get("name")) or display_row_name(row)
            row["detail"] = type_label
            row["modelLabel"] = front_model_label(raw_row)
            row["frontTrait"] = front_trait_label(raw_row, type_label)
            row["isCurved"] = is_curved_front_row(raw_row)
            row["hideSubtitle"] = True
            row["isGlass"] = is_glass_row(row, type_label)
            row["columnLayout"] = "front-standard"
            row["frontSource"] = row_source
            grouped_sections[section_slug]["rows"].append(row)

    material_order = {"Fóliás": 0, "Bútorlapos": 1}
    sorted_sections = list(grouped_sections.values())
    for section in sorted_sections:
        rows = [row for row in section.get("rows", []) if isinstance(row, dict)]
        rows.sort(
            key=lambda row: (
                str(row.get("color", "")).lower(),
                str(row.get("frontTrait", "")).lower(),
                str(row.get("modelLabel", "")).lower(),
                str(row.get("name", "")).lower(),
                size_sort_key(str(row.get("size", "")).strip()),
                str(row.get("detail", "")).lower(),
                str(row.get("code", "")).lower(),
            )
        )
        section["rows"] = rows

    sorted_sections.sort(
        key=lambda section: (
            size_sort_key(str(section.get("label", "")).split("·", 1)[0].strip()),
            material_order.get(str(section.get("label", "")).split("·", 2)[1].strip(), 9)
            if "·" in str(section.get("label", ""))
            else 9,
            str(section.get("label", "")).split("·", 2)[2].strip().lower()
            if str(section.get("label", "")).count("·") >= 2
            else "",
            str(section.get("label", "")),
        )
    )
    return sorted_sections, row_count


def _manufacturing_pantolo_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    raw_sections, _ = _manufacturing_document_sections(
        bundle,
        production_number,
        ("pantolo",),
        include_source_prefix=False,
    )

    def clean_text(value: object) -> str:
        return str(value or "").strip()

    def folded(value: object) -> str:
        text = clean_text(value).lower()
        for source, target in (
            ("á", "a"),
            ("é", "e"),
            ("í", "i"),
            ("ó", "o"),
            ("ö", "o"),
            ("ő", "o"),
            ("ú", "u"),
            ("ü", "u"),
            ("ű", "u"),
            ("Ăˇ", "a"),
            ("Ă©", "e"),
            ("Ă­", "i"),
            ("Ăł", "o"),
            ("Ă¶", "o"),
            ("Ĺ‘", "o"),
            ("Ăş", "u"),
            ("ĂĽ", "u"),
            ("Ĺ±", "u"),
            ("Ăµ", "o"),
            ("Ă»", "u"),
            ("õ", "o"),
            ("û", "u"),
        ):
            text = text.replace(source, target)
        return text

    opening_tokens = {
        "bal": "Bal",
        "balos": "Balos",
        "jobb": "Jobb",
        "jobbos": "Jobbos",
        "nincs": "Nincs",
        "felnyilo": "Felnyíló",
        "felnyíló": "Felnyíló",
    }

    def normalize_token(token: object) -> str:
        return folded(str(token or "").strip().strip(".,;:|/_-()[]{}"))

    def is_nincs_token(token: object) -> bool:
        return normalize_token(token) == "nincs"

    def normalize_nincs_text(value: object) -> str:
        text = clean_text(value)
        if not text:
            return ""
        tokens = [clean_text(part) for part in text.split() if clean_text(part)]
        if not tokens:
            return ""
        if all(is_nincs_token(part) for part in tokens):
            return "Nincs"
        if len(tokens) >= 2 and is_nincs_token(tokens[0]) and is_nincs_token(tokens[1]):
            tail = " ".join(tokens[2:]).strip()
            return f"Nincs {tail}".strip()
        return text

    def strip_leading_nincs(value: object) -> str:
        text = normalize_nincs_text(value)
        while text and normalize_token(text.split(" ", 1)[0]) == "nincs" and " " in text:
            text = clean_text(text.split(" ", 1)[1])
        return text or "Nincs"

    def normalize_pant_label(value: object) -> str:
        label = clean_text(value)
        if not label:
            return "Nincs"
        folded_label = folded(label)
        folded_compact = re.sub(r"\s+", " ", folded_label).strip()
        # OCR variánsok: "ráüt.165°-os klipp", "raut 165 klipp", stb.
        if "165" in folded_compact and "klipp" in folded_compact:
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact in {"raut", "raut.", "ráüt", "ráüt."}:
            return "Ráüt."
        if folded_compact.startswith("raut.tip") or folded_compact.startswith("ráüt.tip"):
            return "Ráüt.tip."
        if folded_compact.startswith("csill. raut. 165") or folded_compact.startswith("csill. ráüt. 165"):
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact.startswith("csill.raut.165") or folded_compact.startswith("csill.ráüt.165"):
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact.startswith("csill.raut") or folded_compact.startswith("csill.ráüt"):
            return "Csill.ráüt."
        if folded_compact.startswith("raut.csill. 3d-s") or folded_compact.startswith("ráüt.csill. 3d-s"):
            return "Ráüt.csill. 3D-s"
        return label

    def canonical_pantolo_color(value: object) -> tuple[str, bool]:
        raw = re.sub(r"\s+", " ", clean_text(value)).strip()
        if not raw:
            return "-", False
        tokens = [clean_text(part) for part in raw.split() if clean_text(part)]
        if not tokens:
            return "-", False
        had_hutos = False
        filtered: list[str] = []
        for token in tokens:
            if normalize_token(token) == "hutos":
                had_hutos = True
                continue
            filtered.append(token)
        final_text = re.sub(r"\s+", " ", " ".join(filtered)).strip() or raw
        return final_text, had_hutos

    def strip_model_prefix_from_color(color_value: object, model_value: object) -> str:
        color_text = clean_text(color_value)
        model_text = clean_text(model_value)
        if not color_text or not model_text:
            return color_text
        color_fold = folded(color_text)
        model_fold = folded(model_text)
        color_parts = [normalize_token(part) for part in color_fold.split() if normalize_token(part)]
        if not color_parts:
            return color_text
        if color_parts[0] == normalize_token(model_fold):
            original_parts = [clean_text(part) for part in color_text.split() if clean_text(part)]
            if len(original_parts) >= 2:
                stripped = " ".join(original_parts[1:]).strip()
                if stripped:
                    return stripped
        if color_fold.startswith(model_fold + " "):
            stripped = color_text[len(model_text):].strip()
            if stripped:
                return stripped
        return color_text

    def is_generic_pantolo_color(value: object) -> bool:
        color = folded(clean_text(value))
        if not color or color == "-":
            return True
        generic_tokens = {
            "folias",
            "fóliás",
            "matt",
            "sm",
            "mf",
        }
        parts = [normalize_token(part) for part in color.split() if normalize_token(part)]
        if not parts:
            return True
        if len(parts) == 1 and parts[0] in generic_tokens:
            return True
        return False

    def normalize_handle_type(drill_value: object, handle_value: object) -> str:
        handle = normalize_nincs_text(handle_value)
        if not handle:
            return "-"
        drill_norm = normalize_token(drill_value)
        parts = [clean_text(part) for part in handle.split() if clean_text(part)]
        if not parts:
            return "-"
        # OCR/parse csúszás esetén: "Fúrva Szabina fekete" ne maradjon a fogantyú típus elején,
        # ha a furat oszlop már "Nincs".
        if drill_norm == "nincs":
            while parts and normalize_token(parts[0]) in {"furva", "nincs"}:
                parts = parts[1:]
        return " ".join(parts).strip() or "Nincs"

    def parse_front_type(detail_text: object) -> tuple[str, list[str]]:
        detail = clean_text(detail_text)
        parts = [clean_text(part) for part in detail.split("·") if clean_text(part)]
        front_type = ""
        if parts and folded(parts[0]).startswith("front tipus:"):
            front_type = clean_text(parts[0].split(":", 1)[1] if ":" in parts[0] else parts[0].replace("Front tipus", ""))
            parts = parts[1:]
        return front_type or "-", parts

    drill_tokens = {"furva", "fúrva", "nincs"}

    def parse_tail_fields(parts: list[str]) -> tuple[str, str, str, str]:
        if not parts:
            return "-", "-", "-", "-"
        tail_tokens: list[str] = []
        for piece in parts:
            tail_tokens.extend([token for token in clean_text(piece).split() if token])
        tokens = tail_tokens
        if not tokens:
            return "-", "-", "-", "-"
        lowered = [normalize_token(token) for token in tokens]

        drill_index = -1
        for probe in range(min(len(tokens), 4)):
            if lowered[probe] in drill_tokens:
                drill_index = probe
                break
        if drill_index == -1:
            for probe, token in enumerate(lowered):
                if token in drill_tokens:
                    drill_index = probe
                    break

        drill = "-"
        remaining: list[str]
        if drill_index == -1:
            remaining = tokens
        else:
            drill_norm = lowered[drill_index]
            drill = "Fúrva" if drill_norm == "furva" else "Nincs"
            remaining = tokens[drill_index + 1 :]

        # OCR/parse zaj: "Nincs Nincs Balos FSL" jellegű soroknál az első
        # "Nincs" nem nyitásirány, csak töltelék token a furat után.
        # Ilyenkor a nyitásirány valójában a következő token (Balos/Jobb/Bal...).
        if drill == "Nincs":
            while (
                len(remaining) >= 2
                and normalize_token(remaining[0]) == "nincs"
                and normalize_token(remaining[1]) in opening_tokens
                and normalize_token(remaining[1]) != "nincs"
            ):
                remaining = remaining[1:]

        if not remaining:
            return drill, "-", "-", "-"

        opening_index = -1
        opening_label = "-"
        for index, token in enumerate(remaining):
            normalized = normalize_token(token)
            if normalized in opening_tokens:
                opening_index = index
                opening_label = opening_tokens[normalized]
                break

        if opening_index == -1:
            handle_type = normalize_handle_type(drill, " ".join(remaining)) or "-"
            if normalize_token(handle_type) == "nincs":
                return drill, "Nincs", "Nincs", "Nincs"
            return drill, handle_type, "-", "-"

        handle_type = normalize_handle_type(drill, " ".join(remaining[:opening_index])) or "-"
        door_type = normalize_nincs_text(" ".join(remaining[opening_index + 1 :])) or "-"
        if door_type and normalize_token(door_type.split(" ", 1)[0]) == "nincs" and " " in door_type:
            door_type = clean_text(door_type.split(" ", 1)[1]) or "Nincs"
        if normalize_token(door_type) == "nincs":
            door_type = "Nincs"
        if handle_type == "Nincs Nincs":
            handle_type = "Nincs"
        return drill, handle_type, opening_label, door_type

    grouped_sections: dict[str, dict] = {}
    grouped_order: list[str] = []
    row_count = 0
    last_valid_color_by_front_model: dict[tuple[str, str], str] = {}
    last_valid_color_by_front: dict[str, str] = {}
    unresolved_rows_by_front_model: dict[tuple[str, str], list[dict]] = {}

    for section in raw_sections:
        for raw_row in section.get("rows", []):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            model_label = clean_text(row.get("name")) or "-"
            color, _had_hutos_in_color = canonical_pantolo_color(row.get("color"))
            color = strip_model_prefix_from_color(color, model_label)
            size_label = clean_text(row.get("size")) or "-"
            quantity_value = int(row.get("quantity") or 0)
            front_type, tail_parts = parse_front_type(row.get("detail"))
            front_type = clean_text(front_type) or "-"
            model_label = clean_text(row.get("name")) or "-"
            color_key = (front_type, model_label)
            if is_generic_pantolo_color(color):
                fallback_color = last_valid_color_by_front_model.get(color_key)
                if not fallback_color:
                    fallback_color = last_valid_color_by_front.get(front_type)
                if fallback_color:
                    color = fallback_color
                else:
                    color = "-"
            else:
                last_valid_color_by_front_model[color_key] = color
                last_valid_color_by_front[front_type] = color
            first_tail = clean_text(tail_parts[0]) if tail_parts else ""
            first_tail_token = clean_text(first_tail.split(" ", 1)[0]) if first_tail else ""
            first_tail_norm = normalize_token(first_tail_token)
            if first_tail_norm in drill_tokens:
                if first_tail_norm == "nincs":
                    # "Nincs · Fúrva ..." mintánál az első "Nincs" a pánt oszlophoz tartozik,
                    # a furatot a következő rész adja.
                    next_token_norm = ""
                    if len(tail_parts) > 1:
                        next_token = clean_text(tail_parts[1]).split(" ", 1)[0]
                        next_token_norm = normalize_token(next_token)
                    if next_token_norm in drill_tokens:
                        pant_type = "Nincs"
                        row["_pantolo_explicit_nincs"] = True
                        row["_pantolo_missing_pant"] = False
                        tail_payload = tail_parts[1:]
                    else:
                        pant_type = "Nincs"
                        row["_pantolo_explicit_nincs"] = True
                        row["_pantolo_missing_pant"] = False
                        tail_payload = tail_parts
                else:
                    # Ha "Fúrva"-val indul a sor, tipikusan hiányzik a pánttoken (parser törés),
                    # ezt inferenciával pótoljuk később.
                    pant_type = "-"
                    row["_pantolo_explicit_nincs"] = False
                    row["_pantolo_missing_pant"] = True
                    tail_payload = tail_parts
            else:
                pant_type = first_tail or "Nincs"
                row["_pantolo_explicit_nincs"] = False
                row["_pantolo_missing_pant"] = False
                tail_payload = tail_parts[1:] if len(tail_parts) > 1 else []
            drill_label, handle_type, opening_dir, door_type = parse_tail_fields(tail_payload)
            group_label = f"Front típus: {front_type} | {color} | {model_label}"
            group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            if group_key not in grouped_sections:
                grouped_sections[group_key] = {
                    "key": f"pantolo::{group_key}",
                    "label": group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                grouped_order.append(group_key)
            row["name"] = color
            row["color"] = color
            row["detail"] = ""
            row["frontType"] = front_type
            row["modelLabel"] = model_label
            row["color23"] = "-"
            row["pantType"] = normalize_pant_label(pant_type or "Nincs")
            row["handleDrill"] = drill_label or "-"
            row["handleType"] = handle_type or "-"
            row["openingDir"] = opening_dir or "-"
            row["doorType"] = door_type or "-"
            row["meValue"] = quantity_value
            row["columnLayout"] = "pantolo"
            row["hideSubtitle"] = True
            grouped_sections[group_key]["rows"].append(row)
            if color == "-":
                unresolved_rows_by_front_model.setdefault(color_key, []).append(row)
            else:
                for pending_row in unresolved_rows_by_front_model.pop(color_key, []):
                    pending_row["name"] = color
            row_count += quantity_value

    # Rebuild groups after color backfill so rows that were initially "-" can
    # move into their correct color box once the real color appears later.
    rebuilt_sections: dict[str, dict] = {}
    rebuilt_order: list[str] = []
    for group_key in grouped_order:
        section_rows = grouped_sections.get(group_key, {}).get("rows", [])
        for row in section_rows:
            if not isinstance(row, dict):
                continue
            front_type = clean_text(row.get("frontType")) or "-"
            color = clean_text(row.get("name")) or "-"
            model_label = clean_text(row.get("modelLabel")) or "-"
            rebuilt_group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            rebuilt_group_label = f"Front típus: {front_type} | {color} | {model_label}"
            if rebuilt_group_key not in rebuilt_sections:
                rebuilt_sections[rebuilt_group_key] = {
                    "key": f"pantolo::{rebuilt_group_key}",
                    "label": rebuilt_group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                rebuilt_order.append(rebuilt_group_key)
            rebuilt_sections[rebuilt_group_key]["rows"].append(row)

    sections = [rebuilt_sections[key] for key in rebuilt_order]
    all_pantolo_rows = [row for section in sections for row in section.get("rows", []) if isinstance(row, dict)]

    def apply_hutos_suffix(base_color: str, has_hutos: bool) -> str:
        color_text = clean_text(base_color) or "-"
        if color_text == "-" or not has_hutos:
            return color_text
        if "hutos" in folded(color_text):
            return color_text
        return f"{color_text} Hűtős"

    def is_bad_pantolo_section_color(row: dict) -> bool:
        color_text = clean_text(row.get("name"))
        if is_generic_pantolo_color(color_text):
            return True
        stripped = strip_model_prefix_from_color(color_text, row.get("modelLabel"))
        return clean_text(stripped) != color_text

    def resolve_nearest_section_color(index: int) -> str:
        current = all_pantolo_rows[index]
        front_type = clean_text(current.get("frontType")) or "-"
        model_label = clean_text(current.get("modelLabel")) or "-"
        previous_match: tuple[int, str] | None = None
        next_match: tuple[int, str] | None = None
        for probe in range(index - 1, -1, -1):
            candidate = all_pantolo_rows[probe]
            if clean_text(candidate.get("frontType")) != front_type:
                continue
            if clean_text(candidate.get("modelLabel")) != model_label:
                continue
            candidate_color = clean_text(candidate.get("name"))
            candidate_color = strip_model_prefix_from_color(candidate_color, candidate.get("modelLabel"))
            if is_generic_pantolo_color(candidate_color):
                continue
            previous_match = (index - probe, candidate_color)
            break
        for probe in range(index + 1, len(all_pantolo_rows)):
            candidate = all_pantolo_rows[probe]
            if clean_text(candidate.get("frontType")) != front_type:
                continue
            if clean_text(candidate.get("modelLabel")) != model_label:
                continue
            candidate_color = clean_text(candidate.get("name"))
            candidate_color = strip_model_prefix_from_color(candidate_color, candidate.get("modelLabel"))
            if is_generic_pantolo_color(candidate_color):
                continue
            next_match = (probe - index, candidate_color)
            break
        if previous_match and next_match:
            if clean_text(previous_match[1]) == clean_text(next_match[1]):
                return previous_match[1]
            return previous_match[1] if previous_match[0] <= next_match[0] else next_match[1]
        if previous_match:
            return previous_match[1]
        if next_match:
            return next_match[1]
        return "-"

    needs_color_regroup = False
    for index, row in enumerate(all_pantolo_rows):
        if not is_bad_pantolo_section_color(row):
            continue
        resolved_color = resolve_nearest_section_color(index)
        original_color, had_hutos = canonical_pantolo_color(row.get("color"))
        resolved_color = strip_model_prefix_from_color(resolved_color, row.get("modelLabel"))
        resolved_color = apply_hutos_suffix(resolved_color, had_hutos)
        if clean_text(resolved_color) and clean_text(resolved_color) != clean_text(row.get("name")):
            row["name"] = resolved_color
            row["color"] = resolved_color
            needs_color_regroup = True

    if needs_color_regroup:
        regrouped_sections: dict[str, dict] = {}
        regrouped_order: list[str] = []
        for row in all_pantolo_rows:
            front_type = clean_text(row.get("frontType")) or "-"
            color = clean_text(row.get("name")) or "-"
            model_label = clean_text(row.get("modelLabel")) or "-"
            regrouped_group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            regrouped_group_label = f"Front típus: {front_type} | {color} | {model_label}"
            if regrouped_group_key not in regrouped_sections:
                regrouped_sections[regrouped_group_key] = {
                    "key": f"pantolo::{regrouped_group_key}",
                    "label": regrouped_group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                regrouped_order.append(regrouped_group_key)
            regrouped_sections[regrouped_group_key]["rows"].append(row)
        sections = [regrouped_sections[key] for key in regrouped_order]
        all_pantolo_rows = [row for section in sections for row in section.get("rows", []) if isinstance(row, dict)]

    for row in all_pantolo_rows:
        row["color"] = clean_text(row.get("name")) or "-"

    def canonical_pantolo_door(value: object) -> str:
        text = folded(clean_text(value))
        compact = re.sub(r"[^a-z0-9]+", "", text)
        if "sar" in text and "fel" in text:
            return "sarok_felso"
        if "sar" in text and "als" in text:
            return "sarok_also"
        if "felso" in compact and "uv" in compact:
            return "felso_uv"
        return compact or "-"

    def infer_pant_from_global_context(target_row: dict) -> str | None:
        if bool(target_row.get("_pantolo_explicit_nincs")):
            return None
        current_pant = folded(clean_text(target_row.get("pantType")))
        if current_pant not in {"", "-"}:
            return None
        if folded(clean_text(target_row.get("handleDrill"))) != "furva":
            return None

        target_size = clean_text(target_row.get("size"))
        target_opening = folded(clean_text(target_row.get("openingDir")))
        target_door = canonical_pantolo_door(target_row.get("doorType"))
        if not target_size or not target_opening or target_opening in {"-", "nincs"}:
            return None

        candidate_pants: set[str] = set()
        for row in all_pantolo_rows:
            if row is target_row:
                continue
            pant = clean_text(row.get("pantType"))
            if not pant or folded(pant) in {"-", "nincs"}:
                continue
            if clean_text(row.get("size")) != target_size:
                continue
            if folded(clean_text(row.get("openingDir"))) != target_opening:
                continue
            if canonical_pantolo_door(row.get("doorType")) != target_door:
                continue
            candidate_pants.add(pant)
        if len(candidate_pants) == 1:
            return next(iter(candidate_pants))
        return None

    def infer_pant_from_door_dominance(target_row: dict) -> str | None:
        """Fallback hiányzó pántnál: ajtó-típus alapú domináns pánt."""
        if bool(target_row.get("_pantolo_explicit_nincs")):
            return None
        if folded(clean_text(target_row.get("handleDrill"))) != "furva":
            return None

        target_door = canonical_pantolo_door(target_row.get("doorType"))
        target_opening = folded(clean_text(target_row.get("openingDir")))
        if target_door in {"", "-"}:
            return None

        def collect_counts(match_opening: bool) -> dict[str, int]:
            counts: dict[str, int] = {}
            for candidate in all_pantolo_rows:
                if candidate is target_row:
                    continue
                if bool(candidate.get("_pantolo_missing_pant")):
                    continue
                candidate_pant = clean_text(candidate.get("pantType"))
                if not candidate_pant or folded(candidate_pant) in {"", "-", "nincs"}:
                    continue
                if folded(clean_text(candidate.get("handleDrill"))) != "furva":
                    continue
                if canonical_pantolo_door(candidate.get("doorType")) != target_door:
                    continue
                if match_opening and folded(clean_text(candidate.get("openingDir"))) != target_opening:
                    continue
                counts[candidate_pant] = counts.get(candidate_pant, 0) + 1
            return counts

        def pick_if_dominant(counts: dict[str, int], min_advantage: int) -> str | None:
            if not counts:
                return None
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if len(ordered) == 1:
                return ordered[0][0]
            if ordered[0][1] >= ordered[1][1] + min_advantage:
                return ordered[0][0]
            return None

        by_door_opening = collect_counts(match_opening=True)
        inferred = pick_if_dominant(by_door_opening, min_advantage=2)
        if inferred:
            return inferred

        by_door = collect_counts(match_opening=False)
        return pick_if_dominant(by_door, min_advantage=3)

    for section in sections:
        rows = [row for row in section.get("rows", []) if isinstance(row, dict)]
        pant_counts: dict[str, int] = {}
        pant_rows_non_nincs: list[dict] = []
        for row in rows:
            pant_value = clean_text(row.get("pantType"))
            if not pant_value or pant_value == "-":
                continue
            pant_counts[pant_value] = pant_counts.get(pant_value, 0) + 1
            if folded(pant_value) != "nincs":
                pant_rows_non_nincs.append(row)
        if not pant_counts:
            for row in rows:
                row["pantType"] = "Nincs" if bool(row.get("_pantolo_explicit_nincs")) else "-"
            continue

        def infer_pant_type(target_row: dict) -> str | None:
            if not pant_rows_non_nincs:
                return None
            scored: list[tuple[tuple[int, int, int, int, int], str]] = []
            for candidate_row in pant_rows_non_nincs:
                candidate_pant = clean_text(candidate_row.get("pantType"))
                if not candidate_pant:
                    continue
                # Prioritás: fogantyú típus + fogantyú furat > nyitás irány > ajtó típus > méret.
                # Ez stabilabb azokra az első sorokra, ahol a pánt mező hiányos a PDF-ből.
                feature_score = (
                    int(clean_text(candidate_row.get("handleType")) == clean_text(target_row.get("handleType"))),
                    int(clean_text(candidate_row.get("handleDrill")) == clean_text(target_row.get("handleDrill"))),
                    int(clean_text(candidate_row.get("openingDir")) == clean_text(target_row.get("openingDir"))),
                    int(clean_text(candidate_row.get("doorType")) == clean_text(target_row.get("doorType"))),
                    int(clean_text(candidate_row.get("size")) == clean_text(target_row.get("size"))),
                )
                scored.append((feature_score, candidate_pant))
            if not scored:
                return None
            scored.sort(reverse=True)
            best_score = scored[0][0]
            if best_score <= (0, 0, 0, 0, 0):
                unique_pants = sorted({pant for _feature_score, pant in scored})
                return unique_pants[0] if len(unique_pants) == 1 else None
            best_pants = sorted({pant for feature_score, pant in scored if feature_score == best_score})
            if len(best_pants) != 1:
                return None
            inferred = best_pants[0]
            target_opening = folded(clean_text(target_row.get("openingDir")))
            # Ne keverjük: Felnyíló soroknál a hiányzó pánttípus tipikusan "Ráüt.",
            # nem "Ráüt.tip.".
            if target_opening == "felnyilo" and folded(inferred).startswith("raut.tip"):
                return "Ráüt."
            return inferred

        def dominant_section_pant() -> str | None:
            counts: dict[str, int] = {}
            for row in pant_rows_non_nincs:
                pant = clean_text(row.get("pantType"))
                if not pant:
                    continue
                counts[pant] = counts.get(pant, 0) + 1
            if not counts:
                return None
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if len(ordered) == 1:
                return ordered[0][0]
            # Csak markáns többségnél használjuk fallbackként.
            if ordered[0][1] >= ordered[1][1] + 2:
                return ordered[0][0]
            return None

        dominant_pant = dominant_section_pant()

        def can_use_dominant_for_missing(target_row: dict) -> bool:
            opening = folded(clean_text(target_row.get("openingDir")))
            door_key = canonical_pantolo_door(target_row.get("doorType"))
            if opening in {"felnyilo", "nincs", "-"}:
                return False
            # Ezeknél gyakori az eltérő pánt (vagy explicit Nincs), ezért itt nem domináns-tippelünk.
            if door_key in {"sarok_felso", "sarok_also", "fsl", "felso_uv", "-"}:
                return False
            return True

        def infer_pant_type_strict_first_row(target_row: dict, row_index: int) -> str | None:
            # Csak az első sorra: 3-lépcsős kontroll, hogy ne maradjon hibás "Nincs".
            if row_index != 0:
                return None
            if not pant_rows_non_nincs:
                return None
            current_pant = clean_text(target_row.get("pantType"))
            current_drill = clean_text(target_row.get("handleDrill"))
            if folded(current_pant) not in {"nincs", "-"}:
                return None
            if folded(current_drill) != "furva":
                return None

            def row_pant(candidate: dict) -> str:
                return clean_text(candidate.get("pantType"))

            def non_nincs(candidate: dict) -> bool:
                pant = row_pant(candidate)
                return bool(pant and folded(pant) not in {"nincs", "-"})

            candidates = [candidate for candidate in rows if isinstance(candidate, dict) and candidate is not target_row and non_nincs(candidate)]
            if not candidates:
                return None

            # 1) Erős egyezés: fogantyú típus + furat + nyitás + ajtó típus
            strict = [
                candidate
                for candidate in candidates
                if clean_text(candidate.get("handleType")) == clean_text(target_row.get("handleType"))
                and clean_text(candidate.get("handleDrill")) == clean_text(target_row.get("handleDrill"))
                and clean_text(candidate.get("openingDir")) == clean_text(target_row.get("openingDir"))
                and clean_text(candidate.get("doorType")) == clean_text(target_row.get("doorType"))
            ]
            strict_pants = sorted({row_pant(candidate) for candidate in strict if row_pant(candidate)})
            if len(strict_pants) == 1:
                return strict_pants[0]

            # 2) Közepes egyezés: fogantyú típus + furat
            medium = [
                candidate
                for candidate in candidates
                if clean_text(candidate.get("handleType")) == clean_text(target_row.get("handleType"))
                and clean_text(candidate.get("handleDrill")) == clean_text(target_row.get("handleDrill"))
            ]
            medium_pants = sorted({row_pant(candidate) for candidate in medium if row_pant(candidate)})
            if len(medium_pants) == 1:
                return medium_pants[0]

            # 3) Közeli sorok többségi pántja (2-3 következő sorból)
            nearby = []
            for index, candidate in enumerate(rows):
                if not isinstance(candidate, dict) or candidate is target_row or not non_nincs(candidate):
                    continue
                if index in {1, 2, 3}:
                    nearby.append(candidate)
            if nearby:
                counts: dict[str, int] = {}
                for candidate in nearby:
                    pant = row_pant(candidate)
                    if not pant:
                        continue
                    counts[pant] = counts.get(pant, 0) + 1
                if counts:
                    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                    top_pant, top_count = ordered[0]
                    if top_count >= 2 or len(ordered) == 1:
                        return top_pant

            return None

        def infer_missing_pant_from_section_pairs(target_row: dict) -> str | None:
            """Hiányzó pántot csak ugyanazon box biztos párjából örököljünk."""
            target_size = clean_text(target_row.get("size"))
            target_door = canonical_pantolo_door(target_row.get("doorType"))
            target_handle = clean_text(target_row.get("handleType"))
            target_drill = folded(clean_text(target_row.get("handleDrill")))
            target_opening = folded(clean_text(target_row.get("openingDir")))
            if not target_size or target_door in {"", "-"} or target_drill != "furva":
                return None

            candidate_pants: set[str] = set()
            for candidate in rows:
                if candidate is target_row or not isinstance(candidate, dict):
                    continue
                candidate_pant = clean_text(candidate.get("pantType"))
                if not candidate_pant or folded(candidate_pant) in {"", "-", "nincs"}:
                    continue
                if clean_text(candidate.get("size")) != target_size:
                    continue
                if canonical_pantolo_door(candidate.get("doorType")) != target_door:
                    continue
                if clean_text(candidate.get("handleType")) != target_handle:
                    continue
                if folded(clean_text(candidate.get("handleDrill"))) != target_drill:
                    continue
                candidate_opening = folded(clean_text(candidate.get("openingDir")))
                # előny: ellentétes nyitású pár sor
                if target_opening in {"bal", "jobb"} and candidate_opening in {"bal", "jobb"}:
                    if candidate_opening == target_opening:
                        continue
                candidate_pants.add(candidate_pant)
            if len(candidate_pants) == 1:
                return next(iter(candidate_pants))
            return None

        def infer_missing_pant_business_rule(target_row: dict) -> str | None:
            """Gyártási szabály: Sarok alsó + Fém rúd esetén pánt = Pillér."""
            door_key = canonical_pantolo_door(target_row.get("doorType"))
            handle_type = folded(clean_text(target_row.get("handleType")))
            drill = folded(clean_text(target_row.get("handleDrill")))
            if door_key == "sarok_also" and "fem rud" in handle_type and drill == "furva":
                return "Pillér"
            return None

        # Csak egyértelmű esetben pótolunk, hogy a "Ráüt." és "Ráüt.tip." ne keveredjen.
        for row_index, row in enumerate(rows):
            pant_value = clean_text(row.get("pantType"))
            if not pant_value or pant_value == "-":
                row["pantType"] = "Nincs" if bool(row.get("_pantolo_explicit_nincs")) else "-"

        # Nincs második/harmadik pánt-korrekciós passz: nincs találgatás.

        for row in rows:
            if "_pantolo_explicit_nincs" in row:
                row.pop("_pantolo_explicit_nincs", None)
            if "_pantolo_missing_pant" in row:
                row.pop("_pantolo_missing_pant", None)

    return sections, row_count


def _manufacturing_cnc_sections(bundle: dict, production_number: str) -> tuple[list[dict], int, list[dict], str]:
    raw_sections, _ = _manufacturing_document_sections(bundle, production_number, ("cnc", "fiokelo_furas"))
    using_xml_cnc_source = False

    def folded(value: object) -> str:
        text = str(value or "").strip().lower()
        for source, target in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ö", "o"), ("ő", "o"), ("ú", "u"), ("ü", "u"), ("ű", "u"), ("õ", "o"), ("û", "u")):
            text = text.replace(source, target)
        return text

    def clean_text(value: object) -> str:
        return (
            str(value or "")
            .strip()
            .replace("õ", "ő")
            .replace("Õ", "Ő")
            .replace("û", "ű")
            .replace("Û", "Ű")
        )

    def cnc_xml_source_sections() -> tuple[list[dict], bool]:
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return [], False
        folder = Path(folder_text)
        xml_path = folder / "CNC.xml"
        if not xml_path.is_file():
            try:
                xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "cnc.xml"), xml_path)
            except OSError:
                return [], False
        if not xml_path.is_file():
            return [], False

        try:
            import xml.etree.ElementTree as ET

            root = ET.parse(xml_path).getroot()
        except Exception:
            return [], True

        def local_name(tag: object) -> str:
            return str(tag or "").rsplit("}", 1)[-1].strip()

        def folded_ascii(value: object) -> str:
            text = unicodedata.normalize("NFKD", clean_text(value))
            text = "".join(char for char in text if not unicodedata.combining(char))
            return re.sub(r"\s+", " ", text).strip().lower()

        def tag_key(tag: object) -> str:
            return re.sub(r"[^a-z0-9]+", "", folded_ascii(local_name(tag)))

        def whole_number(value: object) -> str:
            text = clean_text(value).replace(",", ".")
            if not text:
                return ""
            try:
                return str(int(Decimal(text).to_integral_value(rounding=ROUND_HALF_UP)))
            except (InvalidOperation, ValueError):
                match = re.search(r"-?\d+(?:\.\d+)?", text)
                if not match:
                    return ""
                try:
                    return str(int(Decimal(match.group(0)).to_integral_value(rounding=ROUND_HALF_UP)))
                except Exception:
                    return ""

        def quantity_value(value: object) -> int:
            number_text = whole_number(value)
            if not number_text:
                return 1
            try:
                return int(number_text)
            except ValueError:
                return 1

        def drawer_drill_value(value: object) -> str:
            code = re.sub(r"[^a-z0-9]+", "", folded_ascii(value)).upper()
            if code == "N":
                return "Nincs"
            if code == "T":
                return "Teleszkóp"
            if code == "BH":
                return "Box Hettich"
            return ""

        def con_fields(con_element: object) -> dict[str, str]:
            fields: dict[str, str] = {}
            for child in list(con_element):
                key = tag_key(getattr(child, "tag", ""))
                if key and key not in fields:
                    fields[key] = clean_text(getattr(child, "text", ""))
            return fields

        def field_value(fields: dict[str, str], *names: str) -> str:
            for name in names:
                value = fields.get(tag_key(name), "")
                if value:
                    return value
            return ""

        section_rows: dict[str, list[dict]] = {}
        row_index = 0
        for con_element in root.iter():
            if tag_key(getattr(con_element, "tag", "")) != "con":
                continue
            fields = con_fields(con_element)
            section_label = field_value(fields, "KorpTipPer")
            section_folded = folded_ascii(section_label)
            is_lower_xml_section = "als" in section_folded
            is_upper_xml_section = "fels" in section_folded
            if not is_lower_xml_section and not is_upper_xml_section:
                continue

            length = whole_number(field_value(fields, "Hossz"))
            width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
            thickness = whole_number(field_value(fields, "Vastag"))
            size_parts_for_label = [part for part in (length, width, thickness) if part]
            size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
            name = field_value(fields, "Leiras", "Leírás") or "Tétel"
            color = field_value(fields, "Szin", "Szín")
            edge = field_value(fields, "Elzaras", "Élzárás") or "-"
            side_type = field_value(fields, "Oldal_Tip", "Oldal Tip")
            hardware_type = field_value(fields, "VASALAT_TIP", "Vasalat Tip")
            cnc_tag_value = field_value(fields, "CNC")
            cnc_detail = "" if re.sub(r"[^a-z0-9]+", "", folded_ascii(cnc_tag_value)).upper() == "N" else cnc_tag_value
            drawer_drill = drawer_drill_value(field_value(fields, "FIOKSIN_FURAS", "Fióksín Fúrás"))
            quantity = quantity_value(field_value(fields, "conQuantity"))
            detail = clean_text(" ".join(part for part in (drawer_drill if is_lower_xml_section else "", side_type, edge, cnc_detail, hardware_type) if part and part != "-"))
            row_index += 1
            row_id = hashlib.sha1(
                f"cnc-xml|{production_number}|{row_index}|{section_label}|{name}|{size_label}|{color}|{edge}|{side_type}|{drawer_drill}|{quantity}".encode("utf-8")
            ).hexdigest()[:16]
            section_rows.setdefault(section_label, []).append(
                {
                    "row_id": row_id,
                    "state_key": _manufacturing_state_key(production_number, row_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": name,
                    "source_name": name,
                    "size": size_label,
                    "color": color,
                    "drawer_drill": drawer_drill,
                    "side_type": side_type,
                    "hardware_type": hardware_type,
                    "edge": edge,
                    "quantity": quantity,
                    "detail": detail,
                    "code": f"CNCXML-{row_index:04d}",
                    "doc_key": "cnc",
                    "section_key": _manufacturing_local_slug(section_label),
                    "section_label": section_label,
                    "page_number": 1,
                }
            )

        sections: list[dict] = []
        for section_label, rows in section_rows.items():
            if not rows:
                continue
            sections.append(
                {
                    "key": f"cnc::{_manufacturing_local_slug(section_label)}",
                    "label": section_label,
                    "rows": rows,
                }
            )
        return sections, True

    xml_cnc_sections, xml_cnc_available = cnc_xml_source_sections()
    if xml_cnc_available:
        raw_sections = [
            section
            for section in raw_sections
            if not str(section.get("key", "")).startswith("cnc::")
        ] + xml_cnc_sections
        using_xml_cnc_source = True
    cnc_source_type = "XML" if using_xml_cnc_source else "PDF"

    def size_parts(size_label: object) -> tuple[int, ...]:
        parts = [int(part.strip()) for part in re.split(r"[xX]", str(size_label or "")) if part.strip().isdigit()]
        return tuple(parts or [9999, 9999, 9999])

    def canonical_side_type(value: object) -> str:
        text = clean_text(value)
        folded_text = re.sub(r"\s+", " ", folded(text)).strip()
        if not folded_text:
            return ""
        if "ar golyos" in folded_text:
            return "AR golyós tel."
        if "aaf fiokos ajtos" in folded_text:
            return "AAF fiókos ajtós"
        if "af 1+2" in folded_text or "af 1 + 2" in folded_text:
            return "AF 1+2 fiókos"
        if "pultos" in folded_text:
            return "Pultos nor. al."
        if "as vt" in folded_text:
            return "AS VT"
        if "as magic" in folded_text:
            return "AS MAGIC"
        if re.search(r"\batf\b", folded_text):
            return "ATF"
        if "aszb" in folded_text and "szemetes" in folded_text:
            return "ASZB kihúzható szemetes"
        if "aszhs" in folded_text:
            return "ASZHS"
        if "aszb" in folded_text:
            return "ASZB kihúzható szemetes"
        if re.search(r"\bakl\b", folded_text):
            return "AKL"
        if "jolly" in folded_text:
            return "Jolly"
        if re.search(r"\bkira\b", folded_text):
            return "Kira"
        if re.search(r"\bar\b", folded_text):
            return "AR"
        if "nyitott" in folded_text:
            return "Nyitott"
        if "normal" in folded_text:
            return "Normáls alsó"
        return text

    def normalize_side_type(value: object) -> str:
        return re.sub(r"\s+", " ", folded(canonical_side_type(value))).strip()

    def cnc_display_name(name: object) -> str:
        text = clean_text(name)
        folded_text = folded(text)
        if "hatlap also" in folded_text or "tlap als" in folded_text:
            return "Hátlap alsó"
        vegzaro_folded_match = re.search(r"vegzaro\s+also\s+oldal(?:\s+([bj]))?", folded_text)
        if vegzaro_folded_match:
            suffix = str(vegzaro_folded_match.group(1) or "").upper()
            return clean_text(f"Végzáró alsó oldal {suffix}")
        hatlap_match = re.search(r"h[aá]tlap\s+als[oó]", text, flags=re.IGNORECASE)
        if hatlap_match and hatlap_match.start() > 0:
            return clean_text(text[hatlap_match.start():])
        vegzaro_match = re.search(r"v[eé]gz[aá]r[oó]\s+als[oó]\s+oldal(?:\s+[BJ])?", text, flags=re.IGNORECASE)
        if vegzaro_match and vegzaro_match.start() > 0:
            return clean_text(text[vegzaro_match.start():])
        if folded_text == "also oldal":
            return "Alsó oldal"
        if folded_text == "felso oldal":
            return "Felső oldal"
        if folded_text == "also fenek":
            return "Alsó fenék"
        if "fiokelo" in folded_text:
            return "Fiókelő"
        if "blende" in folded_text:
            return "Blende"
        return text or "Tétel"

    def parse_lower_detail(detail: object) -> tuple[str, str, str, str]:
        text = clean_text(detail)
        if not text:
            return "", "", "", ""
        drawer_drill = ""
        remainder = text
        if text.startswith("Nincs "):
            drawer_drill = "Nincs"
            remainder = clean_text(text[6:].strip())
        if text.startswith("Teleszkóp "):
            drawer_drill = "Teleszkópos"
            remainder = clean_text(text[len("Teleszkóp "):].strip())
        if text.startswith("Teleszkópos "):
            drawer_drill = "Teleszkópos"
            remainder = clean_text(text[len("Teleszkópos "):].strip())
        if text.startswith("AVZ "):
            tokens = [clean_text(token) for token in text.split() if clean_text(token)]
            avz_suffix = tokens[1] if len(tokens) > 1 and tokens[1] in {"B", "J", "N"} else ""
            side_type = clean_text(" ".join(["AVZ", avz_suffix]))
            tail_tokens = tokens[2:] if avz_suffix else tokens[1:]
            edge_pattern = re.compile(r"^\d+H(?:\dR)?$")
            parsed_edge = ""
            hardware_type = ""
            if tail_tokens and edge_pattern.fullmatch(tail_tokens[0]):
                parsed_edge = tail_tokens[0]
                tail_tokens = tail_tokens[1:]
            if tail_tokens:
                hardware_type = clean_text(" ".join(tail_tokens))
            return "", side_type, parsed_edge, hardware_type
        if text.startswith("Box Hettich "):
            drawer_drill = "Box Hettich"
            remainder = clean_text(text[len("Box Hettich "):].strip())
        known_side_types = {
            "Normál alsó",
            "Normáls alsó",
            "AS MAGIC",
            "AKL",
            "AR",
            "Jolly",
            "Kira",
            "Nyitott",
            "ATF",
            "ASZHS/ASZB",
            "ASZHS",
            "ASZB kihúzható szemetes",
            "AS VT",
            "AAF fiókos ajtós",
            "AF 1+2 fiókos",
        }
        if remainder in known_side_types:
            return drawer_drill, canonical_side_type(remainder), "", ""
        tokens = [clean_text(token) for token in remainder.split() if clean_text(token)]
        hardware_type = ""
        parsed_edge = ""
        edge_pattern = re.compile(r"^\d+H(?:\dR)?$")
        # Some rows (especially Box Hettich) contain "SIDE EDGE EXTRA..." format,
        # e.g. "KF60F 1H 176FI N". Keep side type isolated in its own column.
        edge_index = next((idx for idx, token in enumerate(tokens) if edge_pattern.fullmatch(token)), -1)
        if edge_index > 0:
            parsed_edge = tokens[edge_index]
            remainder = clean_text(" ".join(tokens[:edge_index]))
            trailing_tokens = tokens[edge_index + 1 :]
            if trailing_tokens:
                hardware_type = clean_text(" ".join(trailing_tokens))
            return drawer_drill, canonical_side_type(remainder), parsed_edge, hardware_type
        if drawer_drill == "AVZ" and len(tokens) == 1 and tokens[0] in {"N", "KESB", "GTEL", "B", "J"}:
            return drawer_drill, "", "", tokens[0]
        if len(tokens) >= 2 and edge_pattern.fullmatch(tokens[-2]) and tokens[-1] in {"N", "KESB", "GTEL", "B", "TE", "RI", "JO"}:
            parsed_edge = tokens[-2]
            hardware_type = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-2]))
        elif len(tokens) >= 1 and edge_pattern.fullmatch(tokens[-1]):
            parsed_edge = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-1]))
        elif len(tokens) >= 1 and tokens[-1] in {"N", "KESB", "GTEL", "B", "TE", "RI", "JO"} and drawer_drill:
            hardware_type = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-1]))
        return drawer_drill, canonical_side_type(remainder), parsed_edge, hardware_type

    def split_lower_color_and_side_v2(color: object, side_type: object) -> tuple[str, str]:
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        if not color_text:
            return color_text, side_text

        # Keep already parsed side types intact.
        if side_text and side_text not in {"-", ""}:
            return color_text, canonical_side_type(side_text)

        # Some PDF rows append side-type code to color, e.g. "Antracit kr. K60R".
        # Move trailing code-like token into the side-type column.
        match = re.match(r"^(.*\S)\s+(K\d{1,2}[A-Z0-9]{0,6})$", color_text, flags=re.IGNORECASE)
        if match:
            parsed_color = clean_text(match.group(1))
            parsed_side = clean_text(match.group(2)).upper()
            if parsed_color:
                return parsed_color, parsed_side

        return color_text, side_text

    def parse_upper_detail(detail: object) -> tuple[str, str]:
        text = clean_text(detail)
        if not text:
            return "", ""
        for marker in ("Felső oldal", "Felső végzáró", "Tető-fenék mart", "EFT fenék excenteres"):
            marker_index = text.find(marker)
            if marker_index > 0:
                text = clean_text(text[:marker_index])
                break
        text = re.sub(r"\b\d+H(?:\dR)?\s+\d+\b", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text).strip()
        if not text:
            return "", ""
        hardware_codes = {"N", "KESB", "GTEL", "TE", "RI", "JO"}
        if text in hardware_codes:
            return "", text
        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in hardware_codes:
            return clean_text(parts[0]), parts[1]
        return text, ""

    def split_upper_color_and_side(color: object, side_type: object) -> tuple[str, str]:
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        patterns = [
            (r"\s+Sarok\s+fels[őo]$", "Sarok felső"),
            (r"\s+Fels[őo]\s+felny[ií]l[oó]s$", "Felnyíló"),
            (r"\s+F_?2A$", "F2A"),
            (r"\s+EF60_?72$", "EF60_72"),
            (r"\s+EF60$", "EF60"),
            (r"\s+FNY$", "FNY"),
            (r"\s+EFT$", "EFT"),
            (r"\s+FVZ$", "FVZ"),
            (r"\s+FMFS$", "FMFS"),
            (r"\s+FMF$", "FMF"),
            (r"\s+FKF\s+Tiplis$", "FKF Tiplis"),
            (r"\s+FKF$", "FKF"),
            (r"\s+FZN$", "FZN"),
            (r"\s+FÜF$", "FÜF"),
            (r"\s+FUF$", "FÜF"),
            (r"\s+Fels[őo]$", "Normál"),
        ]
        detected_side = side_text
        stripped_color = color_text
        changed = True
        while changed and stripped_color:
            changed = False
            for pattern, candidate_side in patterns:
                if re.search(pattern, stripped_color, flags=re.IGNORECASE):
                    stripped_color = re.sub(pattern, "", stripped_color, flags=re.IGNORECASE).strip(" -")
                    if not detected_side:
                        detected_side = candidate_side
                    changed = True
                    break
        return stripped_color or color_text, detected_side

    def parse_upper_detail_v2(detail: object) -> tuple[str, str]:
        text = clean_text(detail)
        if not text:
            return "", ""
        folded_text = folded(text)
        marker_positions = []
        for marker in ("felso oldal", "felso vegzaro", "teto-fenek mart", "eft fenek excenteres"):
            marker_index = folded_text.find(marker)
            if marker_index > 0:
                marker_positions.append(marker_index)
        if marker_positions:
            text = clean_text(text[:min(marker_positions)])
        text = re.sub(r"\b\d+H(?:\dR)?\s+\d+\b", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text).strip()
        if not text:
            return "", ""
        hardware_codes = {"N", "KESB", "GTEL", "TE", "RI", "JO"}
        if text in hardware_codes:
            return "", text
        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in hardware_codes:
            return clean_text(parts[0]), parts[1]
        return text, ""

    def split_upper_color_and_side_v2(color: object, side_type: object) -> tuple[str, str]:
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        patterns = [
            (r"\s+Sarok\s+fels[őo]\b.*$", "Sarok felső"),
            (r"\s+Fels[őo]\s+felny[ií]l[oó]s\b.*$", "Felnyíló"),
            (r"\s+F_?2A\b.*$", "F2A"),
            (r"\s+EF60_?72\b.*$", "EF60_72"),
            (r"\s+EF60\b.*$", "EF60"),
            (r"\s+FNY\b.*$", "FNY"),
            (r"\s+EFT\b.*$", "EFT"),
            (r"\s+FVZ\b.*$", "FVZ"),
            (r"\s+FMFS\b.*$", "FMFS"),
            (r"\s+FMF\b.*$", "FMF"),
            (r"\s+FKF\s+Tiplis\b.*$", "FKF Tiplis"),
            (r"\s+FKF\b.*$", "FKF"),
            (r"\s+FZN\b.*$", "FZN"),
            (r"\s+FÜF\b.*$", "FÜF"),
            (r"\s+FUF\b.*$", "FÜF"),
            (r"\s+Fels[őo]\b.*$", "Normál"),
        ]
        detected_side = side_text
        stripped_color = color_text
        changed = True
        while changed and stripped_color:
            changed = False
            for pattern, candidate_side in patterns:
                if re.search(pattern, stripped_color, flags=re.IGNORECASE):
                    stripped_color = re.sub(pattern, "", stripped_color, flags=re.IGNORECASE).strip(" -")
                    if not detected_side or detected_side in {"-", ""}:
                        detected_side = candidate_side
                    changed = True
                    break
        return stripped_color or color_text, detected_side

    def extract_embedded_upper_rows(raw_row: dict, source_group: str) -> list[dict]:
        detail_text = clean_text(raw_row.get("detail"))
        if not detail_text:
            return []
        embedded_rows: list[dict] = []
        segments = re.findall(
            r"(Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18.*?)(?=(?:Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18)|$)",
            detail_text,
            flags=re.IGNORECASE,
        )
        for segment in segments:
            match = re.match(
                r"(Fels[őo] oldal)\s+(1H(?:2R)?)\s+(360 x (?:330|550) x 18)\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű\. ]+?)\s+([A-Z0-9ÁÉÍÓÖŐÚÜŰa-záéíóöőúüű]+)(?:\s+(1H(?:2R)?))?(?:\s+(\d+))?\s+(N|KESB|GTEL)\s*$",
                clean_text(segment),
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            name, edge, size, color, side_type, maybe_edge, maybe_qty, hardware_type = match.groups()
            normalized_color, normalized_side_type = split_upper_color_and_side_v2(color, side_type)
            embedded_rows.append(
                {
                    "sourceGroup": source_group,
                    "name": cnc_display_name(name),
                    "source_name": clean_text(name),
                    "size": clean_text(size),
                    "color": normalized_color,
                    "hardware_type": clean_text(hardware_type),
                    "side_type": clean_text(normalized_side_type or side_type),
                    "edge": clean_text(maybe_edge or edge or "-") or "-",
                    "quantity": int(maybe_qty or 2),
                    "detail": "",
                    "columnLayout": "cnc-upper",
                }
            )
        return embedded_rows

    def clean_upper_detail_for_display(detail: object, side_type: object, hardware_type: object) -> str:
        text = clean_text(detail)
        if not text:
            return ""
        side_text = clean_text(side_type)
        hardware_text = clean_text(hardware_type)
        if side_text and hardware_text and side_text != "-" and hardware_text != "-":
            # Remove helper fragments like: "Sarok felső 1H2R 13 N"
            text = re.sub(
                rf"{re.escape(side_text)}\s+\S+\s+\d{{1,3}}\s+{re.escape(hardware_text)}\b",
                "",
                text,
                flags=re.IGNORECASE,
            )
        text = re.sub(
            r"Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18.*?(?=(?:Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18)|$)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = clean_text(text)
        candidates = {
            "",
            side_text,
            hardware_text,
            clean_text(f"{side_text} {hardware_text}"),
            clean_text(f"{hardware_text} {side_text}"),
        }
        if text in candidates:
            return ""
        return text

    def upper_quantity_hint_from_detail(detail: object, edge: object, side_type: object, hardware_type: object) -> int:
        text = clean_text(detail)
        edge_text = clean_text(edge)
        side_text = clean_text(side_type)
        hardware_text = clean_text(hardware_type)
        if not text or not edge_text:
            return 0
        folded_text = folded(text)
        marker_positions = []
        for marker in ("felso oldal", "felso vegzaro", "teto-fenek mart", "eft fenek excenteres"):
            marker_index = folded_text.find(marker)
            if marker_index > 0:
                marker_positions.append(marker_index)
        scan_text = clean_text(text[:min(marker_positions)]) if marker_positions else text
        if not scan_text:
            scan_text = text
        candidates: list[int] = []
        patterns = [
            # "1H2R 13 N"
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(side_text)}\b" if side_text and side_text != "-" else "",
            # "1H2R N 13"
            rf"{re.escape(edge_text)}\s*{re.escape(side_text)}\s*(\d{{1,3}})\b" if side_text and side_text != "-" else "",
            # "1H2R 13 N" where N is hardware type
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(hardware_text)}\b" if hardware_text and hardware_text != "-" else "",
            # "1H2R N 13" where N is hardware type
            rf"{re.escape(edge_text)}\s*{re.escape(hardware_text)}\s*(\d{{1,3}})\b" if hardware_text and hardware_text != "-" else "",
            # merged OCR token: "1H2R13N"
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(side_text)}" if side_text and side_text != "-" else "",
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(hardware_text)}" if hardware_text and hardware_text != "-" else "",
        ]
        for pattern in patterns:
            if not pattern:
                continue
            for match in re.finditer(pattern, scan_text, flags=re.IGNORECASE):
                try:
                    value = int(match.group(1))
                except Exception:
                    continue
                if 1 <= value <= 999:
                    candidates.append(value)
        return max(candidates) if candidates else 0

    def upper_sarok_quantity_hint(detail: object, edge: object) -> int:
        text = clean_text(detail)
        edge_text = clean_text(edge)
        if not text or not edge_text:
            return 0
        lowered = folded(text)
        if "sarok fels" not in lowered:
            return 0
        pattern = rf"sarok\s+fels[őo]\s+{re.escape(edge_text)}\s+(\d{{1,3}})\s+(?:N|KESB|GTEL|TE|RI|JO)\b"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return 0
        try:
            value = int(match.group(1))
        except Exception:
            return 0
        return value if 1 <= value <= 999 else 0

    def is_kamra_row(name: str, color: str, side_type: str) -> bool:
        combined = " ".join([folded(name), folded(color), normalize_side_type(side_type)])
        return "kamra" in combined or "k40" in combined or "k60" in combined or "kmth" in combined or "kmtb" in combined or "ktb60" in combined

    def is_non_nutos_text(value: object) -> bool:
        text = clean_text(value).strip().lower()
        folded_text = folded(text)
        return "nem nútos" in text or "nem nutos" in folded_text

    def is_fiokos_family(row: dict) -> bool:
        combined = " ".join(
            [
                folded(row.get("source_name")),
                folded(row.get("name")),
                normalize_side_type(row.get("side_type")),
                folded(row.get("detail")),
            ]
        )
        return "fiokos" in combined or "aaf" in combined or "af 1+2" in combined or "af 1 + 2" in combined


    def build_lower_rows(source_sections: list[dict]) -> list[dict]:
        merged: dict[tuple[str, str, str, str, str, str, str], dict] = {}
        for section in source_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                source_name = clean_text(raw_row.get("name"))
                name = cnc_display_name(raw_row.get("name"))
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                raw_edge = clean_text(raw_row.get("edge")) or "-"
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(raw_row.get("detail"))
                direct_drawer_drill = clean_text(raw_row.get("drawer_drill"))
                direct_side_type = clean_text(raw_row.get("side_type"))
                direct_hardware_type = clean_text(raw_row.get("hardware_type"))
                if direct_drawer_drill or direct_side_type or direct_hardware_type:
                    drawer_drill = direct_drawer_drill
                    side_type = canonical_side_type(direct_side_type)
                    hardware_type = direct_hardware_type
                color, side_type = split_lower_color_and_side_v2(color, side_type)

                folded_name = folded(name)
                if "takarolap as" in folded_name:
                    # OCR sometimes emits "alsó 1H 1 Takarólap AS" as name and
                    # "Normál alsó" in detail. This is not a Normál oldalelem.
                    # Normalize it so it stays in AS takarósáv sections.
                    name = "Takarólap AS"
                    drawer_drill = ""
                    side_type = ""
                    hardware_type = ""

                edge = parsed_edge or raw_edge
                if is_kamra_row(name, color, side_type):
                    folded_drill = folded(drawer_drill)
                    if folded_drill.startswith("box hettich"):
                        drawer_drill = "Box Hettich"
                    elif folded_drill.startswith("teleszk"):
                        drawer_drill = "Teleszkóp"
                    elif folded_drill.startswith("nincs"):
                        drawer_drill = "Nincs"
                merge_key = (name, size, color, drawer_drill, side_type, edge, hardware_type)
                quantity = int(raw_row.get("quantity", 0) or 0)
                existing = merged.get(merge_key)
                if existing is None:
                    merged_id = hashlib.sha1(
                        f"cnc-lower|{production_number}|{name}|{size}|{color}|{drawer_drill}|{side_type}|{edge}|{hardware_type}".encode("utf-8")
                    ).hexdigest()[:16]
                    source_row_id = str(raw_row.get("row_id", "")).strip()
                    merged[merge_key] = {
                        "row_id": merged_id,
                        "state_key": _manufacturing_state_key(production_number, merged_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": name,
                        "source_name": source_name,
                        "size": size,
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": edge,
                        "quantity": quantity,
                        "detail": clean_text(raw_row.get("detail")),
                        "columnLayout": "cnc-lower",
                        "isMuted": is_non_nutos_text(name) or is_non_nutos_text(source_name),
                        "sourceRowIds": [source_row_id] if source_row_id else [],
                    }
                else:
                    existing["quantity"] = int(existing.get("quantity", 0) or 0) + quantity
                    if source_name:
                        existing["source_name"] = f"{existing.get('source_name', '')} · {source_name}".strip(" ·")
                    existing["isMuted"] = bool(existing.get("isMuted")) or is_non_nutos_text(name) or is_non_nutos_text(source_name)
                    source_row_id = str(raw_row.get("row_id", "")).strip()
                    if source_row_id:
                        source_row_ids = list(existing.get("sourceRowIds", []))
                        if source_row_id not in source_row_ids:
                            source_row_ids.append(source_row_id)
                        existing["sourceRowIds"] = source_row_ids
        return list(merged.values())

    def upper_source_group(section_label: object) -> str:
        text = clean_text(section_label)
        folded_text = folded(text)
        if "1-es" in folded_text:
            return "1-es"
        if "2-es" in folded_text:
            return "2-es"
        return text or "egyeb"

    def build_expected_upper_excenter_counts() -> dict[tuple[str, str, str, str, str, str, str], int]:
        if using_xml_cnc_source:
            return {}
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return {}
        cnc_path = Path(folder_text) / "CNC.pdf"
        if not cnc_path.is_file():
            return {}
        try:
            pages = manufacturing_pdf_lines(cnc_path)
        except Exception:
            return {}

        expected: dict[tuple[str, str, str, str, str, str, str], int] = {}
        current_label = ""
        for lines in pages:
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                token_folded = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", token_folded) or re.fullmatch(r"[12]-es\s+fels.*", token_folded):
                    current_label = token
                    index += 1
                    continue
                if "fels" not in folded(current_label):
                    index += 1
                    continue
                if token_folded not in {"eft fenek", "eft fenek excenteres"}:
                    index += 1
                    continue

                cursor = index + 1
                if cursor < len(lines) and folded(clean_text(lines[cursor])) == "excenteres":
                    cursor += 1
                if cursor + 7 >= len(lines):
                    index += 1
                    continue

                size_tokens = [clean_text(lines[cursor + offset]) for offset in range(5)]
                if not (
                    size_tokens[0].isdigit()
                    and size_tokens[1].lower() == "x"
                    and size_tokens[2].isdigit()
                    and size_tokens[3].lower() == "x"
                    and size_tokens[4].isdigit()
                ):
                    index += 1
                    continue

                size_label = f"{size_tokens[0]} x {size_tokens[2]} x {size_tokens[4]}"
                color = clean_text(lines[cursor + 5])
                edge = clean_text(lines[cursor + 6]) or "-"
                quantity_token = clean_text(lines[cursor + 7])
                if not re.fullmatch(r"-?\d+", quantity_token):
                    index += 1
                    continue

                quantity = int(quantity_token)
                source_group = upper_source_group(current_label)
                key = (
                    source_group,
                    "EFT fenék excenteres",
                    size_label,
                    color,
                    "",
                    "",
                    edge,
                )
                expected[key] = int(expected.get(key, 0) or 0) + quantity
                index = cursor + 8
        return expected

    def build_upper_rows(source_sections: list[dict]) -> list[dict]:
        merged: dict[tuple[str, str, str, str, str, str, str], dict] = {}
        def add_upper_row(parsed_row: dict, raw_row: dict | None = None) -> None:
            source_group = clean_text(parsed_row.get("sourceGroup"))
            name = clean_text(parsed_row.get("name"))
            source_name = clean_text(parsed_row.get("source_name"))
            size = clean_text(parsed_row.get("size"))
            color = clean_text(parsed_row.get("color"))
            hardware_type = clean_text(parsed_row.get("hardware_type"))
            side_type = clean_text(parsed_row.get("side_type"))
            edge = clean_text(parsed_row.get("edge")) or "-"
            quantity = int(parsed_row.get("quantity", 0) or 0)
            merge_key = (source_group, name, size, color, hardware_type, side_type, edge)
            existing = merged.get(merge_key)
            source_row_id = ""
            if raw_row is not None:
                source_row_id = str(raw_row.get("row_id", "")).strip()
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-upper|{production_number}|{source_group}|{name}|{size}|{color}|{hardware_type}|{side_type}|{edge}".encode("utf-8")
                ).hexdigest()
                merged[merge_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "sourceGroup": source_group,
                    "name": name,
                    "source_name": source_name,
                    "size": size,
                    "color": color,
                    "hardware_type": hardware_type,
                    "side_type": side_type,
                    "edge": edge,
                    "quantity": quantity,
                    "detail": clean_text(parsed_row.get("detail")),
                    "columnLayout": "cnc-upper",
                    "sourceRowIds": [source_row_id] if source_row_id else [],
                }
            else:
                existing["quantity"] = int(existing.get("quantity", 0) or 0) + quantity
                if source_name:
                    existing["source_name"] = f"{existing.get('source_name', '')} · {source_name}".strip(" ·")
                if source_row_id:
                    source_row_ids = list(existing.get("sourceRowIds", []))
                    if source_row_id not in source_row_ids:
                        source_row_ids.append(source_row_id)
                    existing["sourceRowIds"] = source_row_ids

        for section in source_sections:
            source_group = upper_source_group(section.get("label"))
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                source_name = clean_text(raw_row.get("name"))
                name = cnc_display_name(raw_row.get("name"))
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                edge = clean_text(raw_row.get("edge")) or "-"
                side_type, hardware_type = parse_upper_detail_v2(raw_row.get("detail"))
                direct_side_type = clean_text(raw_row.get("side_type"))
                direct_hardware_type = clean_text(raw_row.get("hardware_type"))
                if direct_side_type or direct_hardware_type:
                    side_type = direct_side_type
                    hardware_type = direct_hardware_type
                color, side_type = split_upper_color_and_side_v2(color, side_type)
                raw_quantity = int(raw_row.get("quantity", 0) or 0)
                quantity_hint = upper_quantity_hint_from_detail(raw_row.get("detail"), edge, side_type, hardware_type)
                sarok_quantity_hint = upper_sarok_quantity_hint(raw_row.get("detail"), edge)
                if quantity_hint > raw_quantity:
                    raw_quantity = quantity_hint
                if sarok_quantity_hint > raw_quantity:
                    raw_quantity = sarok_quantity_hint
                add_upper_row(
                    {
                        "sourceGroup": source_group,
                        "name": name,
                        "source_name": source_name,
                        "size": size,
                        "color": color,
                        "hardware_type": hardware_type,
                        "side_type": side_type,
                        "edge": edge,
                        "quantity": raw_quantity,
                        "detail": clean_upper_detail_for_display(raw_row.get("detail"), side_type, hardware_type),
                    },
                    raw_row,
                )
                for embedded_row in extract_embedded_upper_rows(raw_row, source_group):
                    add_upper_row(embedded_row)

        expected_excenter_counts = build_expected_upper_excenter_counts()
        if expected_excenter_counts:
            actual_excenter_counts: dict[tuple[str, str, str, str, str, str, str], int] = {}
            for row in merged.values():
                row_name_folded = folded(row.get("name"))
                if row_name_folded != "eft fenek excenteres":
                    continue
                key = (
                    clean_text(row.get("sourceGroup")),
                    clean_text(row.get("name")),
                    clean_text(row.get("size")),
                    clean_text(row.get("color")),
                    clean_text(row.get("hardware_type")),
                    clean_text(row.get("side_type")),
                    clean_text(row.get("edge")) or "-",
                )
                actual_excenter_counts[key] = int(actual_excenter_counts.get(key, 0) or 0) + int(row.get("quantity", 0) or 0)

            for key, expected_qty in expected_excenter_counts.items():
                actual_qty = int(actual_excenter_counts.get(key, 0) or 0)
                if expected_qty <= actual_qty:
                    continue
                source_group, name, size, color, hardware_type, side_type, edge = key
                add_upper_row(
                    {
                        "sourceGroup": source_group,
                        "name": name,
                        "source_name": name,
                        "size": size,
                        "color": color,
                        "hardware_type": hardware_type,
                        "side_type": side_type,
                        "edge": edge,
                        "quantity": expected_qty - actual_qty,
                        "detail": "",
                    }
                )
        return list(merged.values())

    def build_front_rows(source_sections: list[dict]) -> list[dict]:
        palette = ("blue", "violet", "amber", "cyan", "slate", "orange", "rose", "lime", "teal")
        explicit_model_tones = {
            "anna": "blue",
            "kinga": "amber",
            "antonia": "violet",
            "laura": "cyan",
            "zille": "slate",
            "kata": "orange",
            "doroti": "rose",
            "kira": "lime",
            "klio": "teal",
        }
        known_models = {"anna", "kinga", "antonia", "laura", "zille", "kata", "doroti", "kira", "klio"}
        invalid_model_tokens = {"", "-", "nincs", "front", "frontos", "furva", "fura", "fio", "fiok"}

        def fiokelo_group_label(section_label: object) -> str:
            text = clean_text(section_label)
            folded_text = folded(text)
            if re.search(r"\b1-es\b", folded_text):
                return "1-es"
            if re.search(r"\b2-es\b", folded_text):
                return "2-es"
            return text or "Egyéb"

        def fiokelo_model_label(detail: object) -> str:
            text = clean_text(detail)
            if not text:
                return "Ismeretlen modell"
            prefix = clean_text(text.split(" - ", 1)[0])
            prefix = re.sub(r"\bNincs\b", "", prefix, flags=re.IGNORECASE).strip(" -")
            first_token = clean_text(prefix.split()[0] if prefix else "")
            return first_token or prefix or "Ismeretlen modell"

        def parse_fiokelo_detail(detail: object) -> tuple[str, str, str, str]:
            text = clean_text(detail)
            if not text:
                return "-", "-", "-", "-"
            parts = [clean_text(part) for part in text.split(" - ") if clean_text(part)]
            prefix = clean_text(parts[0]) if parts else ""
            suffix = clean_text(" - ".join(parts[1:])) if len(parts) > 1 else ""

            # Some PDF extracts split across lines and produce a leading technical token
            # ("Nincs", "Fúrva", "front"), while the real model+color starts in the next chunk.
            leading_token = re.sub(r"[^a-z0-9]+", "", folded(prefix))
            if len(parts) >= 2 and leading_token in {"nincs", "furva", "front", "frontos", "fio", "fiok"}:
                prefix = clean_text(parts[1])
                tail_parts = []
                if parts[0]:
                    tail_parts.append(parts[0])
                if len(parts) > 2:
                    tail_parts.extend(parts[2:])
                suffix = clean_text(" - ".join(tail_parts))

            prefix_tokens = [token for token in prefix.split() if token]
            # Some PDF extracts keep a broken leading token from "Fiókelő"
            # (for example only "ó"), which would shift model/color columns.
            while prefix_tokens:
                lead_normalized = re.sub(r"[^a-z0-9]+", "", folded(prefix_tokens[0]))
                if lead_normalized in {"fiokelo", "fiokelofuras", "fiok", "fio", "io", "front", "frontos", "frontfuras"}:
                    prefix_tokens.pop(0)
                    continue
                if len(prefix_tokens) > 1 and lead_normalized in {"o", "a"}:
                    prefix_tokens.pop(0)
                    continue
                break
            model_index = -1
            for idx, token in enumerate(prefix_tokens):
                normalized = re.sub(r"[^a-z0-9]+", "", folded(token))
                if normalized in known_models:
                    model_index = idx
                    break

            if model_index != -1:
                model_label = clean_text(prefix_tokens[model_index]) or "Ismeretlen modell"
                netfront_color = clean_text(" ".join(prefix_tokens[model_index + 1 :])).strip(" -")
            else:
                model_label = clean_text(prefix_tokens[0]) if prefix_tokens else "Ismeretlen modell"
                netfront_color = clean_text(" ".join(prefix_tokens[1:])).strip(" -")
            if folded(netfront_color) == "nincs":
                netfront_color = ""

            suffix_tokens = [token for token in suffix.split() if token]
            drawer_type = ""
            if suffix_tokens and re.fullmatch(r"[A-Z]{1,4}", suffix_tokens[-1]):
                drawer_type = suffix_tokens.pop()
            drill_text = clean_text(" ".join(suffix_tokens))
            folded_drill_text = folded(drill_text)
            if "furva" in folded_drill_text:
                drill_label = "Fúrva"
            elif "nincs" in folded_drill_text:
                drill_label = "Nincs"
            else:
                drill_label = "-"
            return (
                model_label or "Ismeretlen modell",
                netfront_color or "-",
                drill_label or "-",
                drawer_type or "-",
            )

        def fiokelo_model_tone(model_label: object) -> str:
            token = folded(model_label)
            if not token:
                return "slate"
            normalized_token = re.sub(r"[^a-z0-9]+", "", token)
            if normalized_token in explicit_model_tones:
                return explicit_model_tones[normalized_token]
            return palette[sum(ord(char) for char in token) % len(palette)]

        def normalized_color_key(value: object) -> str:
            return re.sub(r"[^a-z0-9]+", " ", folded(clean_text(value))).strip()

        color_fallback_map = {
            "sm feher folias": "Pure White",
            "sm kasmir folias": "Dune Beige",
            "sm provance folias": "Cedar Green",
            "sm beige folias": "Palo Santo Beige",
            "mf feher": "Mf. Fehér",
            "mf capuccino": "Mf. Latte",
            "mf beige": "Mf. Krém",
            "feher fenyes evogloss": "Magasfényű fehér",
            "matt grafit folias": "Matt antracit",
            "beige folias": "Uni beige",
            "canyon tolgy": "Canyon tölgy",
            "sonoma tolgy": "Sonoma tölgy",
            "kasmir": "Kasmír",
            "antracit kr": "Antracit kr.",
        }

        parsed_rows: list[dict] = []

        def split_model_color_token(value: object) -> tuple[str, str]:
            text = clean_text(value)
            if not text:
                return "", ""
            tokens = [token for token in text.split() if token]
            if not tokens:
                return "", ""
            first_norm = re.sub(r"[^a-z0-9]+", "", folded(tokens[0]))
            if first_norm in known_models:
                model = clean_text(tokens[0])
                color = clean_text(" ".join(tokens[1:]))
                return model, color
            return "", ""

        def is_invalid_model(value: object) -> bool:
            normalized = re.sub(r"[^a-z0-9]+", "", folded(clean_text(value)))
            return normalized in invalid_model_tokens

        for section in source_sections:
            group_label = fiokelo_group_label(section.get("label"))
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                name = cnc_display_name(raw_row.get("name"))
                if folded(name) == "blende":
                    continue
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                edge = clean_text(raw_row.get("edge")) or "-"
                detail = clean_text(raw_row.get("detail"))
                model_label, netfront_color, drill_label, drawer_type = parse_fiokelo_detail(detail)

                # PDF extraction sometimes shifts model into color/netfront fields (e.g. "Kira Fehér").
                # Recover model + color before rendering so model column never shows technical placeholders.
                model_from_color, color_without_model = split_model_color_token(color)
                model_from_netfront, netfront_without_model = split_model_color_token(netfront_color)

                if is_invalid_model(model_label):
                    if model_from_color:
                        model_label = model_from_color
                    elif model_from_netfront:
                        model_label = model_from_netfront

                if model_from_color:
                    model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_label))
                    color_model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_from_color))
                    if is_invalid_model(model_label) or model_norm == color_model_norm:
                        color = color_without_model or color

                if model_from_netfront:
                    model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_label))
                    netfront_model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_from_netfront))
                    if is_invalid_model(model_label) or model_norm == netfront_model_norm:
                        netfront_color = netfront_without_model or netfront_color

                model_tone = fiokelo_model_tone(model_label)
                parsed_rows.append(
                    {
                        "groupLabel": group_label,
                        "name": name,
                        "size": size,
                        "color": color,
                        "edge": edge,
                        "detail": detail,
                        "modelLabel": model_label,
                        "netfrontColor": netfront_color,
                        "drillLabel": drill_label,
                        "drawerType": drawer_type,
                        "modelTone": model_tone,
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                    }
                )

        explicit_model_color_map: dict[tuple[str, str], str] = {}
        explicit_color_map: dict[str, str] = {}
        for row in parsed_rows:
            netfront_color = clean_text(row.get("netfrontColor"))
            if not netfront_color or netfront_color == "-":
                continue
            model_key = folded(row.get("modelLabel"))
            color_key = normalized_color_key(row.get("color"))
            if model_key and color_key:
                explicit_model_color_map[(model_key, color_key)] = netfront_color
            if color_key:
                explicit_color_map[color_key] = netfront_color

        rendered_rows: list[dict] = []
        for index, row in enumerate(parsed_rows):
            model_label = clean_text(row.get("modelLabel"))
            color = clean_text(row.get("color"))
            color_key = normalized_color_key(color)
            model_key = folded(model_label)
            netfront_color = clean_text(row.get("netfrontColor"))
            folded_color = folded(color)
            is_nettfront_front = ("folias" in folded_color) or bool(re.search(r"\bmf\b", folded_color))

            if is_nettfront_front and (not netfront_color or netfront_color == "-"):
                netfront_color = (
                    explicit_model_color_map.get((model_key, color_key))
                    or explicit_color_map.get(color_key)
                    or color_fallback_map.get(color_key)
                    or color
                    or "-"
                )
            elif not is_nettfront_front:
                netfront_color = "-"

            row_id = hashlib.sha1(
                f"cnc-front|{production_number}|{index}|{row.get('groupLabel','')}|{row.get('name','')}|{model_label}|{color}|{row.get('size','')}|{netfront_color}|{row.get('drillLabel','')}|{row.get('drawerType','')}|{row.get('quantity',0)}".encode("utf-8")
            ).hexdigest()[:16]
            rendered_rows.append(
                {
                    "row_id": row_id,
                    "state_key": _manufacturing_state_key(production_number, row_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": row.get("name", ""),
                    "size": row.get("size", ""),
                    "color": color,
                    "edge": row.get("edge", ""),
                    "quantity": int(row.get("quantity", 0) or 0),
                    "detail": row.get("detail", ""),
                    "fiokeloGroup": row.get("groupLabel", ""),
                    "modelLabel": model_label,
                    "netfrontColor": netfront_color,
                    "drillLabel": row.get("drillLabel", ""),
                    "drawerType": row.get("drawerType", ""),
                    "modelTone": row.get("modelTone", "slate"),
                    "hideSubtitle": True,
                }
            )
        return rendered_rows

    also_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("cnc::") and "als" in folded(section.get("label", ""))
    ]
    felso_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("cnc::") and "fels" in folded(section.get("label", ""))
    ]
    front_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("fiokelo_furas::")
    ]

    lower_rows = build_lower_rows(also_source_sections)
    upper_rows = build_upper_rows(felso_source_sections)
    front_rows = build_front_rows(front_source_sections)

    lower_box_order = {
        "pultos nor. al.": 0,
        "as vt": 1,
        "as magic": 2,
        "atf": 3,
        "aszb kihuzhato szemetes": 4,
        "aszhs": 4,
        "akl": 5,
        "ar": 6,
        "ar golyos tel.": 6,
        "kira": 7,
        "nyitott": 8,
    }
    upper_side_order = {"N": 0, "KESB": 1, "GTEL": 2, "TE": 3, "RI": 4, "JO": 5}

    lower_box_sections: list[dict] = []

    def clone_row(row: dict, **updates: object) -> dict:
        cloned = dict(row)
        cloned.update(updates)
        return cloned

    def add_lower_section(label: str, rows: list[dict], key_suffix: str, *, hide_side_type: bool = False) -> None:
        if not rows:
            return
        lower_box_sections.append(
            {
                "key": f"cnc-also::{key_suffix}",
                "label": label,
                "rows": rows,
                "columnLayout": "cnc-lower",
                "hideSideTypeColumn": hide_side_type,
            }
        )

    def hide_lower_subtitles(rows: list[dict]) -> None:
        for row in rows:
            if isinstance(row, dict):
                row["hideSubtitle"] = True

    def set_kinga_anna_subtitles(rows: list[dict]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            row["detail"] = clean_text(" ".join(
                part
                for part in (clean_text(row.get("drawer_drill")), clean_text(row.get("side_type")))
                if part and part != "-"
            ))
            row.pop("hideSubtitle", None)

    def aggregate_lower_rows(rows: list[dict], group_fields: tuple[str, ...], *, hide_subtitle: bool = False) -> list[dict]:
        grouped: dict[tuple[str, ...], dict] = {}
        for row in rows:
            group_key = tuple(clean_text(row.get(field)) for field in group_fields)
            existing = grouped.get(group_key)
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-lower-box|{production_number}|{'|'.join(group_key)}".encode("utf-8")
                ).hexdigest()[:16]
                source_row_ids = [
                    source_row_id
                    for source_row_id in (
                        str(source_id).strip()
                        for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                    )
                    if source_row_id
                ]
                grouped[group_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": clean_text(row.get("name")),
                    "size": clean_text(row.get("size")),
                    "color": clean_text(row.get("color")),
                    "drawer_drill": clean_text(row.get("drawer_drill")),
                    "side_type": clean_text(row.get("side_type")),
                    "hardware_type": clean_text(row.get("hardware_type")),
                    "edge": clean_text(row.get("edge")) or "-",
                    "quantity": int(row.get("quantity", 0) or 0),
                    "detail": "",
                    "columnLayout": "cnc-lower",
                    "hideSubtitle": hide_subtitle,
                    "isMuted": bool(row.get("isMuted")),
                    "sourceRowIds": source_row_ids,
                    "_colors": {clean_text(row.get("color"))},
                    "_drills": {clean_text(row.get("drawer_drill"))},
                    "_edges": {clean_text(row.get("edge")) or "-"},
                    "_hardware": {clean_text(row.get("hardware_type"))},
                }
                continue
            existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
            existing["isMuted"] = bool(existing.get("isMuted")) or bool(row.get("isMuted"))
            existing["_colors"].add(clean_text(row.get("color")))
            existing["_drills"].add(clean_text(row.get("drawer_drill")))
            existing["_edges"].add(clean_text(row.get("edge")) or "-")
            existing["_hardware"].add(clean_text(row.get("hardware_type")))
            source_row_ids = list(existing.get("sourceRowIds", []))
            for source_row_id in (
                str(source_id).strip()
                for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
            ):
                if source_row_id and source_row_id not in source_row_ids:
                    source_row_ids.append(source_row_id)
            existing["sourceRowIds"] = source_row_ids

        aggregated_rows: list[dict] = []
        for item in grouped.values():
            item["color"] = next(iter(item["_colors"])) if len(item["_colors"]) == 1 else "Vegyes"
            item["drawer_drill"] = next(iter(item["_drills"])) if len(item["_drills"]) == 1 else "Vegyes"
            item["edge"] = next(iter(item["_edges"])) if len(item["_edges"]) == 1 else "Vegyes"
            item["hardware_type"] = next(iter(item["_hardware"])) if len(item["_hardware"]) == 1 else "Vegyes"
            item.pop("_colors", None)
            item.pop("_drills", None)
            item.pop("_edges", None)
            item.pop("_hardware", None)
            aggregated_rows.append(item)
        return aggregated_rows

    def is_boxos_side_type(row: dict) -> bool:
        return normalize_side_type(row.get("side_type")) in {"aaf fiokos ajtos", "af 1+2 fiokos"}

    def is_as_takarosav_row(row: dict) -> bool:
        name_text = folded(row.get("name"))
        return "as takarosav" in name_text or "takarolap as" in name_text

    def is_takarolap_as_row(row: dict) -> bool:
        return "takarolap as" in folded(row.get("name"))

    def is_normal_also_row(row: dict) -> bool:
        return (
            folded(row.get("name")) == "also oldal"
            and normalize_side_type(row.get("side_type")) == "normals also"
            and not is_as_takarosav_row(row)
            and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        )

    def is_boxos_target_row(row: dict) -> bool:
        size_label = clean_text(row.get("size"))
        source_name_folded = folded(row.get("source_name"))
        return (
            size_label in {"724 x 505 x 18", "725 x 505 x 18"}
            and ("fiokos" in source_name_folded or is_boxos_side_type(row))
            and folded(row.get("name")) == "also oldal"
            and not is_as_takarosav_row(row)
            and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        )

    def is_boxos_box_hettich_row(row: dict) -> bool:
        return is_boxos_target_row(row) and folded(row.get("drawer_drill")) == "box hettich"

    def is_boxos_teleszkop_row(row: dict) -> bool:
        return is_boxos_target_row(row) and folded(row.get("drawer_drill")).startswith("teleszk")

    def build_raw_normal_also_box_rows() -> list[dict]:
        if using_xml_cnc_source:
            return []
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return []
        cnc_path = Path(folder_text) / "CNC.pdf"
        if not cnc_path.is_file():
            return []
        try:
            pages = manufacturing_pdf_lines(cnc_path)
        except Exception:
            return []

        def is_boundary(token: str) -> bool:
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                clean_token == "Alsó oldal"
                or clean_token.startswith("AS takarósáv")
                or clean_token.startswith("Kamra")
                or clean_token.startswith("Takarólap AS")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                if "als" not in folded(current_label) or token != "Alsó oldal":
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                if size_tokens != ["724", "x", "505", "x", "18"]:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                if normalize_side_type(side_type) != "normals also":
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-normal|{production_number}|{page_number}|{index}|{color}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": "724 x 505 x 18",
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "hideSubtitle": True,
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_kinga_anna_box_rows() -> list[dict]:
        if using_xml_cnc_source:
            return []
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return []
        cnc_path = Path(folder_text) / "CNC.pdf"
        if not cnc_path.is_file():
            return []
        try:
            pages = manufacturing_pdf_lines(cnc_path)
        except Exception:
            return []

        def is_boundary(token: str) -> bool:
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                "also oldal" in folded(clean_token)
                or folded(clean_token).startswith("as takarosav")
                or clean_token.startswith("Kamra")
                or folded(clean_token).startswith("takarolap as")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                if "als" not in folded(current_label) or folded(token) != "also oldal":
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                if size_tokens != ["824", "x", "505", "x", "18"]:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                side_type_normalized = normalize_side_type(side_type)
                if side_type_normalized not in {"normals also", "aaf fiokos ajtos", "af 1+2 fiokos"}:
                    index = cursor
                    continue
                normalized_drill = drawer_drill
                if folded(normalized_drill).startswith("teleszk"):
                    normalized_drill = "Teleszkópos"
                elif folded(normalized_drill).startswith("nincs"):
                    normalized_drill = "Nincs"
                else:
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-824|{production_number}|{page_number}|{index}|{color}|{normalized_drill}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": "824 x 505 x 18",
                        "color": color,
                        "drawer_drill": normalized_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_boxos_box_rows() -> list[dict]:
        if using_xml_cnc_source:
            return []
        alkatresz_sections, _ = _manufacturing_document_sections(
            bundle,
            production_number,
            ("alkatresz_kesz",),
            include_source_prefix=False,
        )
        raw_rows: list[dict] = []
        for section in alkatresz_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                size_label = clean_text(raw_row.get("size"))
                if size_label not in {"724 x 505 x 18", "725 x 505 x 18"}:
                    continue
                if folded(raw_row.get("name")) != "also oldal":
                    continue
                detail = clean_text(raw_row.get("detail"))
                if not detail:
                    continue
                detail_parts = [clean_text(part) for part in detail.split("_") if clean_text(part)]
                detail_folded = [folded(part) for part in detail_parts]
                if "aaf" in detail_folded:
                    side_type = "AAF fiókos ajtós"
                elif "af" in detail_folded:
                    side_type = "AF 1+2 fiókos"
                else:
                    continue
                drawer_drill = ""
                if "bh" in detail_folded:
                    drawer_drill = "Box Hettich"
                elif "t" in detail_folded:
                    drawer_drill = "Teleszkópos"
                elif "n" in detail_folded:
                    drawer_drill = "Nincs"
                if drawer_drill != "Box Hettich":
                    continue
                row_id = hashlib.sha1(
                    f"cnc-raw-boxos|{production_number}|{detail}|{raw_row.get('color')}|{raw_row.get('quantity')}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": clean_text(raw_row.get("color")),
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": "",
                        "edge": clean_text(raw_row.get("edge")) or "-",
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
        return raw_rows

    def build_raw_boxos_teleszkop_rows() -> list[dict]:
        alkatresz_sections, _ = _manufacturing_document_sections(
            bundle,
            production_number,
            ("alkatresz_kesz",),
            include_source_prefix=False,
        )
        raw_rows: list[dict] = []
        for section in alkatresz_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                size_label = clean_text(raw_row.get("size"))
                if size_label not in {"724 x 505 x 18", "725 x 505 x 18"}:
                    continue
                if folded(raw_row.get("name")) != "also oldal":
                    continue
                detail = clean_text(raw_row.get("detail"))
                if not detail:
                    continue
                detail_parts = [clean_text(part) for part in detail.split("_") if clean_text(part)]
                detail_folded = [folded(part) for part in detail_parts]
                if "aaf" not in detail_folded and "af" not in detail_folded:
                    continue
                if "t" not in detail_folded:
                    continue
                row_id = hashlib.sha1(
                    f"cnc-raw-boxos-teleszkop|{production_number}|{detail}|{raw_row.get('color')}|{raw_row.get('quantity')}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": clean_text(raw_row.get("color")),
                        "drawer_drill": "Teleszkópos",
                        "side_type": "Normáls alsó",
                        "hardware_type": "",
                        "edge": clean_text(raw_row.get("edge")) or "-",
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "hideSubtitle": True,
                        "isMuted": False,
                    }
                )
        return raw_rows

    def build_raw_egyebek_box_rows() -> list[dict]:
        if using_xml_cnc_source:
            return []
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return []
        cnc_path = Path(folder_text) / "CNC.pdf"
        if not cnc_path.is_file():
            return []
        try:
            pages = manufacturing_pdf_lines(cnc_path)
        except Exception:
            return []

        def is_boundary(token: str) -> bool:
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                folded_token in {"also oldal", "alsó oldal"}
                or "also oldal" in folded_token
                or "alsó oldal" in folded_token
                or folded_token.startswith("as takarosav")
                or folded_token.startswith("as takarósáv")
                or clean_token.startswith("Kamra")
                or folded(clean_token).startswith("takarolap as")
                or folded(clean_token).startswith("takarólap as")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                token_folded = folded(token)
                if "also oldal" not in token_folded and "alsó oldal" not in token_folded:
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                size_label = " ".join(size_tokens)
                if size_label not in {"724 x 505 x 18", "724 x 520 x 18", "724 x 550 x 18", "824 x 505 x 18"}:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                if folded(drawer_drill) == "avz" or re.search(r"\bavz\b", folded(detail)):
                    index = cursor
                    continue
                side_type_normalized = normalize_side_type(side_type)
                if (
                    size_label in {"724 x 505 x 18", "824 x 505 x 18"}
                    and side_type_normalized == "normals also"
                ) or is_boxos_side_type({"side_type": side_type}) or is_as_takarosav_row({"name": "Alsó oldal"}) or is_kamra_row("Alsó oldal", color, side_type):
                    index = cursor
                    continue
                if side_type_normalized not in {
                    "pultos nor. al.",
                    "as vt",
                    "as magic",
                    "atf",
                    "aszb kihuzhato szemetes",
                    "aszhs",
                    "akl",
                    "ar",
                    "kira",
                    "nyitott",
                } and size_label not in {"724 x 505 x 18", "724 x 520 x 18", "724 x 550 x 18", "824 x 505 x 18"}:
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-egyebek|{production_number}|{page_number}|{index}|{color}|{drawer_drill}|{side_type}|{quantity}".encode('utf-8')
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_takarolap_rows() -> list[dict]:
        if using_xml_cnc_source:
            return []
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return []
        cnc_path = Path(folder_text) / "CNC.pdf"
        if not cnc_path.is_file():
            return []
        try:
            pages = manufacturing_pdf_lines(cnc_path)
        except Exception:
            return []

        def is_boundary(token: str) -> bool:
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                folded_token.startswith("takarolap as")
                or folded_token.startswith("as takarosav")
                or folded_token == "also oldal"
                or folded_token.startswith("vegzaro")
                or folded_token.startswith("kamra")
                or folded_token == "felso oldal"
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if not folded_token.startswith("takarolap as"):
                    index += 1
                    continue

                source_name = token
                cursor = index + 1
                if cursor < len(lines):
                    maybe_suffix = clean_text(lines[cursor])
                    if folded(maybe_suffix) == "165 melle":
                        source_name = clean_text(f"{token} {maybe_suffix}")
                        cursor += 1

                if cursor + 4 >= len(lines):
                    index += 1
                    continue

                size_tokens = [clean_text(lines[cursor + offset]) for offset in range(0, 5)]
                if not (
                    size_tokens[0].isdigit()
                    and size_tokens[1].lower() == "x"
                    and size_tokens[2].isdigit()
                    and size_tokens[3].lower() == "x"
                    and size_tokens[4].isdigit()
                ):
                    index += 1
                    continue
                size_label = " ".join(size_tokens)
                cursor += 5

                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if tail_tokens and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1

                if len(tail_tokens) < 2:
                    index = max(index + 1, cursor)
                    continue

                qty_index = -1
                for pos in range(len(tail_tokens) - 1, -1, -1):
                    if re.fullmatch(r"-?\d+", clean_text(tail_tokens[pos])):
                        qty_index = pos
                        break
                if qty_index <= 0:
                    index = cursor
                    continue

                quantity = int(clean_text(tail_tokens[qty_index]))
                edge = clean_text(tail_tokens[qty_index - 1]) or "-"
                payload_tokens = [clean_text(item) for item in tail_tokens[: qty_index - 1] if clean_text(item)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for pos, item in enumerate(payload_tokens):
                    if folded(item).startswith("normal"):
                        detail_start = pos
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start])) if detail_start > 0 else clean_text(" ".join(payload_tokens))
                detail = clean_text(" ".join(payload_tokens[detail_start:])) if detail_start < len(payload_tokens) else ""

                row_id = hashlib.sha1(
                    f"cnc-raw-takarolap|{production_number}|{page_number}|{index}|{size_label}|{color}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Takarólap AS",
                        "source_name": source_name,
                        "size": size_label,
                        "color": color,
                        "drawer_drill": "",
                        "side_type": "",
                        "hardware_type": "",
                        "edge": edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def is_fvz_row(row: dict) -> bool:
        combined = " ".join(
            [
                folded(row.get("name")),
                folded(row.get("source_name")),
                folded(row.get("color")),
                folded(row.get("side_type")),
                folded(row.get("hardware_type")),
                folded(row.get("detail")),
            ]
        )
        return "fvz" in combined

    def is_avz_lower_row(row: dict) -> bool:
        combined = " ".join(
            [
                folded(row.get("side_type")),
                folded(row.get("drawer_drill")),
                folded(row.get("detail")),
            ]
        )
        return bool(re.search(r"\bavz\b", combined))

    box_avz_source_rows = [row for row in lower_rows if is_avz_lower_row(row)]
    box_avz_ids = {str(row.get("row_id", "")) for row in box_avz_source_rows}
    box_avz_rows = aggregate_lower_rows(
        box_avz_source_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )

    box1_source_rows = [
        row for row in lower_rows
        if is_normal_also_row(row) and clean_text(row.get("size")) == "724 x 505 x 18"
        and str(row.get("row_id", "")) not in box_avz_ids
    ]
    box1_extra_rows = build_raw_boxos_teleszkop_rows()
    box1_display_rows = (build_raw_normal_also_box_rows() or box1_source_rows) + box1_extra_rows
    box1_rows = aggregate_lower_rows(
        box1_display_rows,
        ("name", "size", "color", "side_type"),
        hide_subtitle=True,
    )
    box1_rows.sort(key=lambda row: (folded(row.get("color")), folded(row.get("name"))))
    box1_ids = {str(row.get("row_id", "")) for row in box1_source_rows}
    if using_xml_cnc_source and box1_extra_rows:
        box1_ids.update(
            str(row.get("row_id", ""))
            for row in lower_rows
            if is_boxos_teleszkop_row(row)
        )
    box2_source_rows = [
        row for row in lower_rows
        if is_boxos_box_hettich_row(row)
        and str(row.get("row_id", "")) not in box_avz_ids
    ]
    box2_display_rows = build_raw_boxos_box_rows() or box2_source_rows
    box2_rows = aggregate_lower_rows(
        box2_display_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    box2_ids = {str(row.get("row_id", "")) for row in box2_source_rows}
    box3_rows = [
        row for row in lower_rows
        if row.get("size") == "824 x 505 x 18"
        and normalize_side_type(row.get("side_type")) in {"normals also", "aaf fiokos ajtos", "af 1+2 fiokos"}
        and str(row.get("row_id", "")) not in box_avz_ids
        and str(row.get("row_id", "")) not in box1_ids
        and str(row.get("row_id", "")) not in box2_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and not is_fvz_row(row)
    ]
    box3_ids = {str(row.get("row_id", "")) for row in box3_rows}
    box3_display_rows = build_raw_kinga_anna_box_rows() or box3_rows
    box3_rows = [dict(row) for row in box3_display_rows if isinstance(row, dict)]
    box_fvz_source_rows = [
        row for row in lower_rows
        if is_fvz_row(row)
        and str(row.get("row_id", "")) not in box_avz_ids
        and str(row.get("row_id", "")) not in box1_ids
        and str(row.get("row_id", "")) not in box2_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and not is_as_takarosav_row(row)
    ]
    box_fvz_ids = {str(row.get("row_id", "")) for row in box_fvz_source_rows}
    box_fvz_rows = aggregate_lower_rows(
        box_fvz_source_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    box4_source_rows = [
        row for row in lower_rows
        if str(row.get("row_id", "")) not in box_avz_ids and str(row.get("row_id", "")) not in box1_ids and str(row.get("row_id", "")) not in box2_ids and str(row.get("row_id", "")) not in box3_ids
        and not is_fvz_row(row)
        and not is_as_takarosav_row(row)
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and normalize_side_type(row.get("side_type")) in lower_box_order
    ]
    box4_ids = {str(row.get("row_id", "")) for row in box4_source_rows}
    box4_display_rows = build_raw_egyebek_box_rows() or box4_source_rows
    box4_rows = aggregate_lower_rows(
        box4_display_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    for row in box4_rows:
        side_norm = normalize_side_type(row.get("side_type"))
        detail_folded = folded(row.get("detail"))
        source_folded = folded(row.get("source_name"))
        if side_norm == "ar golyos tel." or "ar golyos" in detail_folded or "ar golyos" in source_folded:
            row["side_type"] = "AR golyós tel."
        elif side_norm == "ar":
            row["side_type"] = "AR"
    box5_rows = [
        row for row in lower_rows
        if str(row.get("row_id", "")) not in box_avz_ids
        and is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
    ]
    box5_ids = {str(row.get("row_id", "")) for row in box5_rows}
    box6_source_rows = [
        row for row in lower_rows
        if is_as_takarosav_row(row)
        and str(row.get("row_id", "")) not in box_avz_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
    ]
    box6_ids = {str(row.get("row_id", "")) for row in box6_source_rows}
    box6_rows = list(box6_source_rows)
    box6_takarolap_rows = [row for row in box6_rows if is_takarolap_as_row(row)]
    raw_takarolap_rows = build_raw_takarolap_rows()
    if raw_takarolap_rows:
        box6_takarolap_rows = aggregate_lower_rows(
            raw_takarolap_rows,
            ("name", "size", "color", "drawer_drill", "side_type", "edge"),
        )
    box6_rows = [row for row in box6_rows if not is_takarolap_as_row(row)]
    categorized_lower_ids = {
        row_id
        for row_id in (
            box_avz_ids
            | box1_ids
            | box2_ids
            | box3_ids
            | box_fvz_ids
            | box4_ids
            | box5_ids
            | box6_ids
        )
        if row_id
    }
    uncategorized_lower_rows = [
        row for row in lower_rows
        if using_xml_cnc_source
        and str(row.get("row_id", ""))
        and str(row.get("row_id", "")) not in categorized_lower_ids
    ]
    for row in uncategorized_lower_rows:
        row["hideSubtitle"] = True

    box2_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            clean_text(row.get("name")),
        )
    )
    # Kinga/Anna: keep original PDF row order, no merge and no additional sorting.
    box4_rows.sort(
        key=lambda row: (
            lower_box_order.get(normalize_side_type(row.get("side_type")), 99),
            1 if "ar goly" in folded(row.get("side_type")) else 0,
            normalize_side_type(row.get("side_type")),
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
        )
    )
    box_fvz_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box_avz_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box5_rows.sort(
        key=lambda row: (
            0 if clean_text(row.get("size")) != "2017 x 550 x 18" else 1,
            clean_text(row.get("color")),
            0 if "n?tos" in folded(row.get("name")) and "nem n?tos" not in folded(row.get("name")) else 1,
            {"nincs": 0, "teleszkop": 1, "box hettich": 2}.get(folded(row.get("drawer_drill")), 9),
            clean_text(row.get("side_type")),
            clean_text(row.get("hardware_type")),
            clean_text(row.get("name")),
            size_parts(row.get("size")),
        )
    )
    box6_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box6_takarolap_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )

    set_kinga_anna_subtitles(box3_rows)
    for rows_without_subtitles in (box1_rows, box2_rows, box_fvz_rows, box_avz_rows, box4_rows):
        hide_lower_subtitles(rows_without_subtitles)

    add_lower_section("Normáls alsó · 724 x 505 x 18", box1_rows, "box1")
    add_lower_section("Boxosok", box2_rows, "box2")
    add_lower_section("Kinga/Anna", box3_rows, "box3", hide_side_type=True)
    add_lower_section("FVZ", box_fvz_rows, "box-fvz")
    add_lower_section("Alsó Végzáró", box_avz_rows, "box-avz")
    add_lower_section("Egyebek", box4_rows, "box4")
    add_lower_section("Kamrák", box5_rows, "box5")
    add_lower_section("AS takarósávok · Takarólap AS, 165 mellé", box6_takarolap_rows, "box6-takarolap")
    add_lower_section("AS takarósávok", box6_rows, "box6")

    def upper_combined_text(row: dict) -> str:
        return " ".join(
            [
                folded(row.get("name")),
                folded(row.get("color")),
                folded(row.get("hardware_type")),
                folded(row.get("side_type")),
                folded(row.get("detail")),
            ]
        )

    def is_upper_normal_or_fny(row: dict) -> bool:
        combined = upper_combined_text(row)
        return "normal" in combined or "fny" in combined

    def is_upper_felnyilo_group(row: dict) -> bool:
        combined = upper_combined_text(row)
        return (
            "felnyilo" in combined
            or "f_2a" in combined
            or "f2a" in combined
            or "ffm" in combined
            or "ef60" in combined
        )

    def is_upper_zille(row: dict) -> bool:
        combined = upper_combined_text(row)
        return "zille" in combined or "fuf" in combined or "fzn" in combined

    def is_upper_sarok(row: dict) -> bool:
        combined = upper_combined_text(row)
        size = clean_text(row.get("size"))
        return (
            "sarok" in combined
            or (size == "360 x 330 x 18" and ("fmf" in combined or "fmfs" in combined or "fkf" in combined))
            or (size == "360 x 550 x 18" and ("fmf" in combined or "fmfs" in combined or "fkf" in combined))
        )

    def is_upper_595_eft(row: dict) -> bool:
        return clean_text(row.get("size")).startswith("595 x ") and "eft" in upper_combined_text(row)

    def is_upper_any_eft(row: dict) -> bool:
        return "eft" in upper_combined_text(row) or folded(row.get("name")) == "eft fenek excenteres"

    def is_upper_680(row: dict) -> bool:
        return clean_text(row.get("size")).startswith("680 x ")

    def is_upper_360(row: dict) -> bool:
        return clean_text(row.get("size")).startswith("360 x ")

    def aggregate_upper_rows(rows: list[dict]) -> list[dict]:
        grouped: dict[tuple[str, ...], dict] = {}
        for row in rows:
            group_key = (
                clean_text(row.get("name")),
                clean_text(row.get("size")),
                clean_text(row.get("color")),
                clean_text(row.get("hardware_type")),
                clean_text(row.get("side_type")),
                clean_text(row.get("edge")) or "-",
            )
            existing = grouped.get(group_key)
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-upper-box|{production_number}|{'|'.join(group_key)}".encode("utf-8")
                ).hexdigest()
                source_row_ids = [
                    source_row_id
                    for source_row_id in (
                        str(source_id).strip()
                        for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                    )
                    if source_row_id
                ]
                grouped[group_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": clean_text(row.get("name")),
                    "size": clean_text(row.get("size")),
                    "color": clean_text(row.get("color")),
                    "hardware_type": clean_text(row.get("hardware_type")),
                    "side_type": clean_text(row.get("side_type")),
                    "edge": clean_text(row.get("edge")) or "-",
                    "quantity": int(row.get("quantity", 0) or 0),
                    "detail": clean_text(row.get("detail")),
                    "columnLayout": "cnc-upper",
                    "sourceRowIds": source_row_ids,
                }
            else:
                existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
                source_row_ids = list(existing.get("sourceRowIds", []))
                for source_row_id in (
                    str(source_id).strip()
                    for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                ):
                    if source_row_id and source_row_id not in source_row_ids:
                        source_row_ids.append(source_row_id)
                existing["sourceRowIds"] = source_row_ids
        return list(grouped.values())

    def sort_upper_rows(rows: list[dict], mode: str) -> list[dict]:
        if mode == "normal":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    0 if "normal" in upper_combined_text(row) else 1,
                    0 if "fny" in upper_combined_text(row) else 1,
                    size_parts(row.get("size")),
                )
            )
        elif mode == "felnyilo":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    0 if "felnyilo" in upper_combined_text(row) else 1,
                    0 if "f2a" in upper_combined_text(row) or "f_2a" in upper_combined_text(row) else 1,
                    0 if "ffm" in upper_combined_text(row) else 1,
                    0 if "ef60" in upper_combined_text(row) else 1,
                    size_parts(row.get("size")),
                )
            )
        elif mode == "rack1-other":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    0 if is_upper_595_eft(row) else 1,
                    0 if is_upper_360(row) else 1,
                    0 if is_upper_680(row) else 1,
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        elif mode == "rack2-other":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    0 if clean_text(row.get("size")).startswith("595 x ") else 1,
                    0 if is_upper_360_special(row) else 1,
                    0 if is_upper_680(row) else 1,
                    0 if is_upper_zille(row) else 1,
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        elif mode == "sarok":
            rows.sort(
                key=lambda row: (
                    0 if is_upper_sarok(row) else 1,
                    0 if clean_text(row.get("size")) == "360 x 290 x 18" else 1,
                    1 if clean_text(row.get("size")) == "360 x 550 x 18" else 0,
                    clean_text(row.get("color")),
                    clean_text(row.get("hardware_type")),
                )
            )
        else:
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        return rows

    upper_sections = []

    def add_upper_section(label: str, rows: list[dict], key_suffix: str, sort_mode: str) -> None:
        if not rows:
            return
        section_rows = sort_upper_rows(aggregate_upper_rows(rows), sort_mode)
        for section_row in section_rows:
            base_row_id = str(section_row.get("row_id", "")).strip()
            if not base_row_id:
                continue
            scoped_row_id = hashlib.sha1(
                f"cnc-upper-section|{production_number}|{key_suffix}|{base_row_id}".encode("utf-8")
            ).hexdigest()
            section_row["row_id"] = scoped_row_id
            section_row["state_key"] = _manufacturing_state_key(production_number, scoped_row_id)
            section_row["hideSubtitle"] = True
        upper_sections.append(
            {
                "key": f"cnc-felso::{key_suffix}",
                "label": label,
                "rows": section_rows,
                "columnLayout": "cnc-upper",
            }
        )

    def upper_source_group(row: dict) -> str:
        return clean_text(row.get("sourceGroup"))

    def is_upper_zille_target(row: dict) -> bool:
        combined = upper_combined_text(row)
        return "zille" in combined and ("fuf" in combined or "fzn" in combined or "f\u00fcf" in combined)

    def is_upper_fuf_or_fzn(row: dict) -> bool:
        combined = upper_combined_text(row)
        return "fzn" in combined or "fuf" in combined or "f\u00fcf" in combined

    def is_upper_360_special(row: dict) -> bool:
        if not is_upper_360(row):
            return False
        combined = upper_combined_text(row)
        return "fmf" in combined or "fmfs" in combined or "fkf" in combined

    def is_upper_360_fmf(row: dict) -> bool:
        if not is_upper_360(row):
            return False
        combined = upper_combined_text(row)
        return "fmf" in combined or "fmfs" in combined

    def is_upper_360_fkf(row: dict) -> bool:
        return is_upper_360(row) and "fkf" in upper_combined_text(row)

    def is_upper_sarok_bucket_size(row: dict) -> bool:
        size_text = clean_text(row.get("size"))
        return size_text.startswith("360 x 550") or size_text.startswith("360 x 290")

    def is_upper_360x330(row: dict) -> bool:
        return clean_text(row.get("size")).startswith("360 x 330")

    def upper_row_id(row: dict) -> str:
        return str(row.get("row_id", "")).strip()

    non_fvz_upper_rows = [row for row in upper_rows if not is_fvz_row(row)]
    vegzaro_raklap_rows = [row for row in upper_rows if is_fvz_row(row)]
    rack1_source_rows = [row for row in non_fvz_upper_rows if upper_source_group(row) == "2-es"]
    rack2_source_rows = [row for row in non_fvz_upper_rows if upper_source_group(row) == "1-es"]
    zille_rows = [row for row in non_fvz_upper_rows if is_upper_zille_target(row)]

    rack1_box1_rows = [
        row
        for row in rack1_source_rows
        if is_upper_normal_or_fny(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
    ]
    rack1_box1_ids = {upper_row_id(row) for row in rack1_box1_rows}
    rack1_box2_rows = [
        row
        for row in rack1_source_rows
        if is_upper_felnyilo_group(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
    ]
    rack1_box2_ids = {upper_row_id(row) for row in rack1_box2_rows}
    rack1_box3_rows = [
        row for row in rack1_source_rows
        if upper_row_id(row) not in rack1_box1_ids
        and upper_row_id(row) not in rack1_box2_ids
        and not is_upper_360x330(row)
        and not is_upper_sarok(row)
    ]
    rack1_box3_ids = {upper_row_id(row) for row in rack1_box3_rows}

    rack2_box1_rows = [
        row
        for row in rack2_source_rows
        if is_upper_normal_or_fny(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
    ]
    rack2_box1_ids = {upper_row_id(row) for row in rack2_box1_rows}
    rack2_box2_rows = [
        row
        for row in rack2_source_rows
        if is_upper_felnyilo_group(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
    ]
    rack2_box2_ids = {upper_row_id(row) for row in rack2_box2_rows}
    rack2_primary_assigned_ids = {row_id for row_id in (rack2_box1_ids | rack2_box2_ids) if row_id}
    rack2_box3_rows = [
        row for row in rack2_source_rows
        if upper_row_id(row) not in rack2_primary_assigned_ids
        and not is_upper_360x330(row)
        and (not is_upper_sarok_bucket_size(row) or is_upper_360_fmf(row))
        and (
            clean_text(row.get("size")).startswith("595 x ")
            or is_upper_360_special(row)
            or is_upper_680(row)
            or is_upper_fuf_or_fzn(row)
        )
    ]
    all_360_fmf_rows = [
        row for row in non_fvz_upper_rows
        if is_upper_360_fmf(row) and not is_upper_360x330(row)
    ]
    for row in all_360_fmf_rows:
        if row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    fkf_360_rows = [
        row for row in rack2_source_rows
        if is_upper_360_fkf(row) and not is_upper_sarok_bucket_size(row)
    ]
    for row in fkf_360_rows:
        if row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    for row in zille_rows:
        if row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    rack2_box3_ids = {upper_row_id(row) for row in rack2_box3_rows}
    rack1_box360_rows = [row for row in rack1_source_rows if is_upper_360x330(row)]
    rack2_box360_rows = [row for row in rack2_source_rows if is_upper_360x330(row)]
    rack1_box360_ids = {upper_row_id(row) for row in rack1_box360_rows}
    rack2_box360_ids = {upper_row_id(row) for row in rack2_box360_rows}
    rack2_box4_rows = [
        row for row in non_fvz_upper_rows
        if (
            ((is_upper_sarok(row) and not is_upper_360_fmf(row)) and not is_upper_360x330(row))
            or ((is_upper_sarok_bucket_size(row) and not is_upper_360_fmf(row)) and not is_upper_360x330(row))
            or (
                upper_row_id(row) not in rack1_box1_ids
                and upper_row_id(row) not in rack1_box2_ids
                and upper_row_id(row) not in rack1_box3_ids
                and upper_row_id(row) not in rack1_box360_ids
                and upper_row_id(row) not in rack2_primary_assigned_ids
                and upper_row_id(row) not in rack2_box360_ids
                and upper_row_id(row) not in rack2_box3_ids
                and row not in zille_rows
            )
        )
    ]
    recovered_rack1_360_rows = [
        row for row in rack2_box4_rows
        if upper_source_group(row) == "2-es" and is_upper_360(row) and not is_upper_sarok(row) and not is_upper_360x330(row)
    ]
    for row in recovered_rack1_360_rows:
        if upper_row_id(row) not in rack1_box3_ids:
            rack1_box3_rows.append(row)
            rack1_box3_ids.add(upper_row_id(row))
    rack2_box4_rows = [
        row for row in rack2_box4_rows
        if upper_row_id(row) not in rack1_box3_ids and upper_row_id(row) not in rack2_box3_ids
    ]
    rack1_box3_rows = [row for row in rack1_box3_rows if upper_row_id(row) not in rack2_box3_ids]
    rack1_box3_ids = {upper_row_id(row) for row in rack1_box3_rows}
    upper_assigned_ids = {
        str(row.get("row_id", ""))
        for bucket in (
            rack1_box1_rows,
            rack1_box2_rows,
            rack1_box360_rows,
            rack1_box3_rows,
            rack2_box1_rows,
            rack2_box2_rows,
            rack2_box360_rows,
            rack2_box3_rows,
            rack2_box4_rows,
            vegzaro_raklap_rows,
        )
        for row in bucket
        if str(row.get("row_id", ""))
    }
    upper_unassigned_rows = [
        row for row in upper_rows
        if str(row.get("row_id", "")) and str(row.get("row_id", "")) not in upper_assigned_ids
    ]

    add_upper_section("1-es raklap · Normál és FNY", rack1_box1_rows, "rack1-box1", "normal")
    add_upper_section("1-es raklap · Felnyíló / F2A / FFM / EF60", rack1_box2_rows, "rack1-box2", "felnyilo")
    add_upper_section("1-es raklap · 360-as elemek", rack1_box360_rows, "rack1-box360", "default")
    add_upper_section("1-es raklap · EFT / 360 / 680 / Egyéb", rack1_box3_rows, "rack1-box3", "rack1-other")
    add_upper_section("2-es raklap · Normál és FNY", rack2_box1_rows, "rack2-box1", "normal")
    add_upper_section("2-es raklap · Felnyíló / F2A / FFM / EF60", rack2_box2_rows, "rack2-box2", "felnyilo")
    add_upper_section("2-es raklap · 360-as elemek", rack2_box360_rows, "rack2-box360", "default")
    add_upper_section("2-es raklap · EFT / 360 / 680 / Zille", rack2_box3_rows, "rack2-box3", "rack2-other")
    add_upper_section("2-es raklap · Sarok", rack2_box4_rows, "rack2-box4", "sarok")
    add_upper_section("Teszt · Nem besorolt", upper_unassigned_rows, "upper-unassigned", "default")
    add_upper_section("Végzáró raklap", vegzaro_raklap_rows, "vegzaro-raklap", "default")

    upper_sections = []
    add_upper_section("1-es raklap · Normál és FNY", rack1_box1_rows, "rack1-box1", "normal")
    add_upper_section("1-es raklap · Felnyíló / F2A / FFM / EF60", rack1_box2_rows, "rack1-box2", "felnyilo")
    add_upper_section("1-es raklap · 360-as elemek", rack1_box360_rows, "rack1-box360", "default")
    add_upper_section("1-es raklap · Minden más 2-es konyha", rack1_box3_rows, "rack1-box3", "rack1-other")
    add_upper_section("2-es raklap · Normál és FNY", rack2_box1_rows, "rack2-box1", "normal")
    add_upper_section("2-es raklap · Felnyíló / F2A / FFM / EF60", rack2_box2_rows, "rack2-box2", "felnyilo")
    add_upper_section("2-es raklap · 360-as elemek", rack2_box360_rows, "rack2-box360", "default")
    add_upper_section("2-es raklap · 595 / 360 FMF / 680 / Zille", rack2_box3_rows, "rack2-box3", "rack2-other")
    add_upper_section("2-es raklap · Sarok és maradék", rack2_box4_rows, "rack2-box4", "sarok")
    add_upper_section("Teszt · Nem besorolt", upper_unassigned_rows, "upper-unassigned", "default")
    add_upper_section("Végzáró raklap", vegzaro_raklap_rows, "vegzaro-raklap", "default")

    front_sections = []
    if front_rows:
        grouped_front_rows: dict[str, list[dict]] = {}
        for row in front_rows:
            grouped_front_rows.setdefault(str(row.get("fiokeloGroup", "Egyéb")), []).append(row)
        preferred_order = {"1-es": 0, "2-es": 1}
        for group_label, rows in sorted(grouped_front_rows.items(), key=lambda item: (preferred_order.get(item[0], 9), item[0])):
            rows.sort(
                key=lambda row: (
                    size_parts(row.get("size")),
                    clean_text(row.get("modelLabel")),
                    clean_text(row.get("color")),
                    clean_text(row.get("netfrontColor")),
                    clean_text(row.get("drillLabel")),
                    clean_text(row.get("drawerType")),
                )
            )
            front_sections.append(
                {
                    "key": f"cnc-front::{_manufacturing_local_slug(group_label)}",
                    "label": group_label,
                    "rows": rows,
                    "columnLayout": "cnc-fiokelo",
                }
            )

    main_sections = []
    if lower_rows:
        main_sections.append(
            {
                "key": "cnc-main::also",
                "label": "Alsó",
                "rows": lower_rows,
                "columnLayout": "cnc-lower",
            }
        )
    if upper_rows:
        main_sections.append(
            {
                "key": "cnc-main::felso",
                "label": "Felső",
                "rows": upper_rows,
                "columnLayout": "cnc-upper",
            }
        )
    if front_rows:
        main_sections.append(
            {
                "key": "cnc-main::front",
                "label": "Fiókelő fúrás",
                "rows": front_rows,
                "columnLayout": "cnc-fiokelo",
            }
        )

    row_count = sum(len(section.get("rows", [])) for section in main_sections)
    special_views = [
        {
            "key": "cnc-also",
            "label": "Alsó",
            "count": sum(len(section.get("rows", [])) for section in lower_box_sections),
            "sections": lower_box_sections,
        },
        {
            "key": "cnc-felso",
            "label": "Felső",
            "count": sum(len(section.get("rows", [])) for section in upper_sections),
            "sections": upper_sections,
        },
        {
            "key": "cnc-front",
            "label": "Fiókelő fúrás",
            "count": sum(len(section.get("rows", [])) for section in front_sections),
            "sections": front_sections,
        },
    ]
    if uncategorized_lower_rows:
        special_views.append(
            {
                "key": "cnc-uncategorized-overview",
                "label": "Kategorizálatlan",
                "count": len(uncategorized_lower_rows),
                "sections": [
                    {
                        "key": "cnc-overview::uncategorized",
                        "label": "Kategorizálatlan",
                        "rows": uncategorized_lower_rows,
                        "columnLayout": "cnc-lower",
                    }
                ],
                "overviewOnly": True,
                "hideTab": True,
            }
        )
    return main_sections, row_count, special_views, cnc_source_type


def _manufacturing_red_state_numbers(runtime_root: Path) -> list[str]:
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
    sections: list[dict] = []
    selection_state: dict[str, str] = {}
    for production_number in _manufacturing_red_state_numbers(MANUFACTURING_RUNTIME_DIR):
        raw_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, production_number)
        red_row_ids = {str(row_id).strip() for row_id, state in raw_state.items() if state == "red"}
        if not red_row_ids:
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
                if str(row.get("row_id", "")).strip() not in red_row_ids:
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
    return {
        "key": key,
        "label": label,
        "file_name": "",
        "sections": [],
        "row_count": 0,
        "placeholderMessage": f"A {label.lower()} PDF feldolgozási logikája még nincs kialakítva.",
        "specialViews": [],
    }


def _manufacturing_view_bundle(
    raw_bundle: dict,
    production_number: str,
    current_selection_state: dict[str, str],
    *,
    include_all_red_view: bool = True,
) -> tuple[dict, dict[str, str]]:
    current_number = _manufacturing_normalize_number(production_number)
    documents: list[dict] = []
    selection_state_payload = _manufacturing_selection_state_payload(current_number, current_selection_state)

    korpusz_sections, korpusz_row_count = _manufacturing_korpusz_sections(raw_bundle, current_number)
    korpusz_osszekeszito_sections, korpusz_osszekeszito_count = _manufacturing_document_sections(
        raw_bundle, current_number, ("osszekeszito",), include_source_prefix=False
    )
    korpusz_alkatresz_sections, korpusz_alkatresz_count = _manufacturing_document_sections(
        raw_bundle, current_number, ("alkatresz_kesz",), include_source_prefix=False
    )
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
    front_folias_sections = [dict(section) for section in front_sections if "· Fóliás" in str(section.get("label", ""))]
    front_butorlapos_sections = [dict(section) for section in front_sections if "· Bútorlapos" in str(section.get("label", ""))]

    def _filter_front_sections_by_source(sections: list[dict], source: str) -> list[dict]:
        filtered_sections: list[dict] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            rows = [row for row in section.get("rows", []) if isinstance(row, dict) and str(row.get("frontSource", "")).strip().lower() == source]
            if not rows:
                continue
            cloned = dict(section)
            cloned["rows"] = rows
            filtered_sections.append(cloned)
        return filtered_sections

    front_etikett_sections = _filter_front_sections_by_source(front_sections, "etikett")
    documents.append(
        {
            "key": "front_osszekeszites",
            "label": "Front összekészítés",
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
                {
                    "key": "front-etikett",
                    "label": "Etikett frontok",
                    "count": sum(len(section.get("rows", [])) for section in front_etikett_sections),
                    "sections": front_etikett_sections,
                },
            ],
            "allowSplit": False,
            "singleColumnOverview": True,
        }
    )

    cnc_sections, cnc_row_count, cnc_special_views, cnc_source_type = _manufacturing_cnc_sections(raw_bundle, current_number)
    documents.append(
        {
            "key": "cnc_furas",
            "label": "CNC fúrás",
            "sourceType": cnc_source_type,
            "sourceLabel": f"Beolvasva: {cnc_source_type}",
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
    documents.append(
        {
            "key": "pantolas",
            "label": "Pántolás",
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

    existing_keys = {str(document.get("key", "")).strip() for document in documents}
    for operation_key, operation_label in MANUFACTURING_OPERATION_DEFINITIONS:
        if operation_key in existing_keys:
            continue
        documents.append(_manufacturing_placeholder_document(operation_key, operation_label))

    return (
        {
            "production_number": current_number,
            "folder": str(raw_bundle.get("folder", "")),
            "documents": documents,
        },
        selection_state_payload,
    )


ITEM_PATTERN_FULL = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)
ITEM_PATTERN_SIMPLE = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)


@dataclass
class InvoiceItem:
    row_no: str = ""
    article_code: str = ""
    description: str = ""
    pallet_qty: str = ""
    package_qty: str = ""
    pcs_total: str = ""
    total_qty: str = ""
    unit: str = ""
    unit_price: str = ""
    net_value: str = ""


@dataclass
class InvoiceData:
    invoice_profile: str = ""
    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    payment_method: str = ""
    payment_term: str = ""
    delivery_term: str = ""
    transport_mode: str = ""
    order_confirmation_no: str = ""
    client_ref_no: str = ""
    delivery_note_no: str = ""
    truck_number: str = ""
    currency: str = ""
    supplier_lines: list[str] = field(default_factory=list)
    buyer_lines: list[str] = field(default_factory=list)
    items: list[InvoiceItem] = field(default_factory=list)
    total_net: str = ""
    vat_0: str = ""
    vat_19: str = ""
    discount_amount: str = ""
    discount_percent: str = ""
    total_gross: str = ""
    total_pcs: str = ""
    total_m2: str = ""
    total_m3: str = ""
    total_net_weight: str = ""
    total_gross_weight: str = ""
    origin_country: str = ""


@dataclass
class InvoiceChunk:
    invoice_hint: str
    text: str
    page_from: int
    page_to: int


class MissingInvoiceDataError(ValueError):
    pass


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _value_or_default(value: str) -> str:
    return _clean_spaces(value) if value else NO_DATA


def _parse_invoice_date(value: str) -> datetime | None:
    clean_value = _clean_spaces(value)
    if not clean_value:
        return None

    for pattern in (
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(clean_value, pattern)
        except ValueError:
            continue
    return None


def _format_invoice_date(value: str) -> str:
    parsed = _parse_invoice_date(value)
    if parsed is None:
        return _clean_spaces(value)
    return parsed.strftime("%Y.%m.%d")


def _item_value_or_default(value: str, placeholder: str = NO_DATA) -> str:
    cleaned = _clean_spaces(value)
    return cleaned if cleaned else placeholder


def _is_number_token(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9][0-9.,]*", value))


def _is_integer_token(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def _parse_eu_number(value: str) -> float | None:
    cleaned = value.strip().replace(" ", "")
    if not cleaned:
        return None
    if not re.fullmatch(r"-?[0-9.,]+", cleaned):
        return None
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _format_eu_number(value: float, decimals: int = 2) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_rounded_weight(raw_value: str) -> str:
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return ""
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        rounded = Decimal(normalized).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return raw_value
    return f"{int(rounded):,}".replace(",", ".")


def _normalize_kronospan_weight(raw_value: str) -> str:
    value = _parse_eu_number(raw_value)
    if value is None:
        return raw_value
    # Kronospan totalsorban a gross/net weight tipikusan tonnában jelenik meg,
    # a felületen viszont kg-ban mutatjuk.
    if value < 1000:
        value *= 1000
    return _format_eu_number(value, 0)


def _fix_hungarian_mojibake(value: str) -> str:
    return value.translate(str.maketrans({"õ": "ő", "û": "ű", "Õ": "Ő", "Û": "Ű"}))


def _find_index(lines: list[str], pattern: str, start: int = 0) -> int:
    for idx in range(start, len(lines)):
        if re.search(pattern, lines[idx], re.IGNORECASE):
            return idx
    return -1


def _extract_block(lines: list[str], start_pattern: str, end_patterns: list[str]) -> list[str]:
    start_idx = _find_index(lines, start_pattern)
    if start_idx == -1:
        return []

    end_idx = len(lines)
    for end_pattern in end_patterns:
        match_idx = _find_index(lines, end_pattern, start_idx + 1)
        if match_idx != -1:
            end_idx = min(end_idx, match_idx)

    block = lines[start_idx + 1 : end_idx]
    return [line for line in block if line]


def _match_first(text: str, patterns: list[str], flags: int = re.IGNORECASE | re.MULTILINE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean_spaces(match.group(1))
    return ""


def _saved_seller_vat_number(profile: str, supplier_name: str = "") -> str:
    normalized_profile = _clean_spaces(profile).lower()
    if normalized_profile in SAVED_SELLER_VAT_NUMBERS:
        return SAVED_SELLER_VAT_NUMBERS[normalized_profile]

    normalized_supplier = _clean_spaces(supplier_name).lower()
    for key, vat_number in SAVED_SELLER_VAT_NUMBERS.items():
        if key in normalized_supplier:
            return vat_number
    return ""


def _party_has_vat_number(lines: list[str]) -> bool:
    joined = "\n".join(_clean_spaces(line) for line in lines if _clean_spaces(line))
    return bool(
        re.search(
            r"\b(?:VAT\s*(?:ID\s*)?(?:NO\.?|NUMBER)|TAX\s*NO\.?|AD[ÓO]SZ[ÁA]M)\b",
            joined,
            re.IGNORECASE,
        )
    )


def _extract_party_vat_number(lines: list[str]) -> str:
    vat_label_pattern = r"\b(?:VAT\s*(?:ID\s*)?(?:NO\.?|NUMBER)|TAX\s*NO\.?|AD[ÓO]SZ[ÁA]M)\b"
    for idx, line in enumerate(lines):
        cleaned = _clean_spaces(line)
        if not cleaned:
            continue

        label_match = re.search(vat_label_pattern, cleaned, re.IGNORECASE)
        if not label_match:
            continue

        value = cleaned[label_match.end() :].strip(" :.-#")
        if value:
            return value

        for candidate in lines[idx + 1 : idx + 3]:
            candidate_value = _clean_spaces(candidate).strip(" :.-#")
            if candidate_value:
                return candidate_value

    return ""


def _require_party_vat_numbers(data: InvoiceData) -> None:
    missing: list[str] = []
    if not _party_has_vat_number(data.supplier_lines):
        missing.append("eladó VAT Number")
    if not _party_has_vat_number(data.buyer_lines):
        missing.append("vevő VAT Number")
    if missing:
        raise MissingInvoiceDataError(f"Adat nem található: {', '.join(missing)}")


def _pdf_unescape(value: str) -> str:
    value = value.replace(r"\n", " ").replace(r"\r", " ").replace(r"\t", " ")
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return value


def _looks_like_human_text(text: str) -> bool:
    if len(text.strip()) < 40:
        return False
    indicator_hits = sum(token in text for token in (" endobj", " stream", " xref", "/Type", "FlateDecode"))
    if indicator_hits >= 3 and text.count("\n") < 8:
        return False
    alpha_ratio = sum(ch.isalpha() for ch in text) / max(len(text), 1)
    return alpha_ratio > 0.15


def _fallback_extract_text_from_pdf(pdf_bytes: bytes) -> str:
    raw_text = pdf_bytes.decode("latin1", errors="ignore")
    chunks: list[str] = []

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        stream_data = match.group(1)
        candidates = [stream_data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                candidates.append(zlib.decompress(stream_data, wbits))
            except Exception:
                pass

        for candidate in candidates:
            decoded = candidate.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", decoded, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", decoded, re.DOTALL):
                chunks.extend(_pdf_unescape(part) for part in re.findall(r"\((.*?)\)", arr, re.DOTALL))
        for cand in candidates:
            text = cand.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", text, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
                parts = re.findall(r"\((.*?)\)", arr, re.DOTALL)
                chunks.extend(_pdf_unescape(p) for p in parts)

    extracted = " ".join(chunks).strip()
    if extracted:
        return re.sub(r"\s+", " ", extracted)

    rough = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.,:/ ]{4,}", raw_text)
    return " ".join(rough[:800])


def _extract_text_pages_from_pdf(pdf_bytes: bytes) -> list[str]:
    if PdfReader is None:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception:
        return []


# Image OCR extractor kept here for later targeted use. Do not wire this into the
# invoice module as a general fallback; Kronospan seller VAT is stored explicitly.
#
# def _pdf_filter_names(raw_filter) -> set[str]:
#     if raw_filter is None:
#         return set()
#     if isinstance(raw_filter, (list, tuple)):
#         return {str(item) for item in raw_filter}
#     return {str(raw_filter)}
#
#
# def _ocr_image_file(image_path: Path) -> str:
#     if os.name != "nt":
#         return ""
#
#     ocr_script = BASE_DIR / "tools" / "windows_ocr.ps1"
#     if not ocr_script.exists():
#         return ""
#
#     try:
#         completed = subprocess.run(
#             [
#                 "powershell",
#                 "-ExecutionPolicy",
#                 "Bypass",
#                 "-File",
#                 str(ocr_script),
#                 "-Path",
#                 str(image_path.resolve()),
#             ],
#             capture_output=True,
#             encoding="utf-8",
#             errors="replace",
#             text=True,
#             timeout=20,
#             check=False,
#         )
#     except Exception:
#         return ""
#
#     if completed.returncode != 0:
#         return ""
#     return _clean_spaces(completed.stdout)
#
#
# def _extract_pdf_dct_image_ocr_pages(pdf_bytes: bytes) -> list[str]:
#     if PdfReader is None or os.name != "nt":
#         return []
#
#     try:
#         reader = PdfReader(io.BytesIO(pdf_bytes))
#     except Exception:
#         return []
#
#     RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
#     image_text_by_hash: dict[str, str] = {}
#     page_ocr_texts: list[str] = []
#
#     for page in reader.pages:
#         page_parts: list[str] = []
#         try:
#             resources = page.get("/Resources") or {}
#             xobjects = resources.get("/XObject") or {}
#             if hasattr(xobjects, "get_object"):
#                 xobjects = xobjects.get_object()
#         except Exception:
#             page_ocr_texts.append("")
#             continue
#
#         for image_object in xobjects.values():
#             try:
#                 obj = image_object.get_object() if hasattr(image_object, "get_object") else image_object
#                 if str(obj.get("/Subtype")) != "/Image":
#                     continue
#                 if "/DCTDecode" not in _pdf_filter_names(obj.get("/Filter")):
#                     continue
#                 image_data = obj.get_data()
#             except Exception:
#                 continue
#
#             digest = hashlib.sha256(image_data).hexdigest()
#             if digest not in image_text_by_hash:
#                 temp_path = RUNTIME_DIR / f"pdf-ocr-{digest[:16]}-{uuid.uuid4().hex[:8]}.jpg"
#                 try:
#                     temp_path.write_bytes(image_data)
#                     image_text_by_hash[digest] = _ocr_image_file(temp_path)
#                 except Exception:
#                     image_text_by_hash[digest] = ""
#                 finally:
#                     try:
#                         temp_path.unlink(missing_ok=True)
#                     except Exception:
#                         pass
#
#             if image_text_by_hash[digest]:
#                 page_parts.append(image_text_by_hash[digest])
#
#         page_ocr_texts.append("\n".join(page_parts))
#
#     return page_ocr_texts


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    page_text = _extract_text_pages_from_pdf(pdf_bytes)
    if page_text:
        joined = "\n".join(chunk for chunk in page_text if chunk).strip()
        if _looks_like_human_text(joined):
            return joined

    return _fallback_extract_text_from_pdf(pdf_bytes)


def _extract_invoice_number_hint(text: str) -> str:
    lines = [_clean_spaces(line) for line in text.splitlines() if _clean_spaces(line)]
    normalized = "\n".join(lines)

    for pattern in (
        r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
        r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"SZÁMLA\s*SZÁMA[\s\S]{0,120}?(\d{5,})",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    idx = _find_index(lines, r"^Invoice number$")
    if idx != -1:
        for candidate in lines[idx + 1 : idx + 12]:
            if re.fullmatch(r"\d{4,}", candidate):
                return candidate

    return ""


def split_pdf_by_invoice(pdf_bytes: bytes) -> list[InvoiceChunk]:
    page_texts = _extract_text_pages_from_pdf(pdf_bytes)
    if not page_texts:
        text = extract_text_from_pdf(pdf_bytes)
        return [InvoiceChunk(invoice_hint=_extract_invoice_number_hint(text), text=text, page_from=1, page_to=1)]

    groups: list[InvoiceChunk] = []
    current_hint = ""
    current_pages: list[tuple[int, str]] = []

    for page_index, raw_text in enumerate(page_texts, start=1):
        page_text = raw_text.strip()
        hint = _extract_invoice_number_hint(page_text) if page_text else ""

        if not current_pages:
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        should_split = bool(hint and current_hint and hint != current_hint)
        if should_split:
            from_page = current_pages[0][0]
            to_page = current_pages[-1][0]
            joined_text = "\n".join(text for _, text in current_pages if text).strip()
            groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        if hint and not current_hint:
            current_hint = hint
        current_pages.append((page_index, page_text))

    if current_pages:
        from_page = current_pages[0][0]
        to_page = current_pages[-1][0]
        joined_text = "\n".join(text for _, text in current_pages if text).strip()
        groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))

    # Ha nem sikerült jól szétbontani (pl. mind üres), maradjon egy blokk.
    valid_groups = [group for group in groups if group.text]
    return valid_groups or [InvoiceChunk(invoice_hint="", text=extract_text_from_pdf(pdf_bytes), page_from=1, page_to=len(page_texts))]


def _parse_items(lines: list[str]) -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 7 or not _is_integer_token(tokens[0]):
            continue

        # A sor végétől bontunk, mert a leírás maga is tartalmazhat számokat.
        if (
            len(tokens) >= 10
            and _is_number_token(tokens[-1])
            and _is_number_token(tokens[-2])
            and _is_number_token(tokens[-4])
            and re.fullmatch(r"[A-Za-z0-9]{1,8}", tokens[-3])
        ):
            if len(tokens) >= 14 and all(_is_integer_token(tokens[idx]) for idx in (-5, -6, -7)):
                description = " ".join(tokens[2:-7]).strip()
                if not description:
                    continue
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        pallet_qty=tokens[-7],
                        package_qty=tokens[-6],
                        pcs_total=tokens[-5],
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

            description = " ".join(tokens[2:-5]).strip()
            if description:
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

        full_match = ITEM_PATTERN_FULL.match(line)
        if full_match:
            row_no, code, desc, pallet, package_qty, pcs, qty, unit, unit_price, net_value = full_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    pallet_qty=pallet,
                    package_qty=package_qty,
                    pcs_total=pcs,
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )
            continue

        simple_match = ITEM_PATTERN_SIMPLE.match(line)
        if simple_match:
            row_no, code, desc, qty, unit, unit_price, net_value = simple_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )

    return items


def _detect_invoice_profile(lines: list[str], text: str) -> str:
    upper_text = text.upper()
    if "KASTAMONU" in upper_text:
        return "kastamonu"

    if "GAMET SP. Z O.O." in upper_text or "GAMET SP. Z O.O." in upper_text.replace("Ł", "L"):
        return "gamet"

    krono_hits = 0
    for marker in ("KRONOSPAN", "DESPATCH ADDRESS", "SPLIT_PDF_MARK", "PAYMENT DUE", "DELIVERY NOTE NO."):
        if marker in upper_text:
            krono_hits += 1
    if krono_hits >= 2:
        return "kronospan"

    if ("DIVIAN-MEGA KFT" in upper_text or "/DIVI" in upper_text) and (
        "SZÁMLA SZÁMA" in upper_text or "ÁRUÉRTÉK" in upper_text or "TRAILER:" in upper_text
    ):
        return "divian"

    return "generic"


def _extract_decimal_from_token(token: str) -> str:
    match = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", token)
    if match:
        return match.group(0)
    match = re.search(r"-?\d+,\d{2}", token)
    if match:
        return match.group(0)
    return ""


def _infer_unit_from_line(line: str) -> str:
    upper = line.upper()
    if "LFM" in upper:
        return "lfm"
    if "M2" in upper:
        return "m2"
    if "PCS" in upper:
        return "pcs"
    return ""


def _parse_kronospan_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if not any(token in upper_line for token in ("P2EN", "WORKTOP", "SPLASHBACK", "MF PB", "VP P2")):
            i += 1
            continue

        kronospan_marker = ""
        if "SPLASHBACK" in upper_line:
            kronospan_marker = "SPLASHBACK"
        elif "WORKTOP" in upper_line or "WORK TOP" in upper_line or "KITCHEN TOP" in upper_line:
            kronospan_marker = "WORKTOP"
        elif "MF PB" in upper_line:
            kronospan_marker = "MF PB"
        elif "VP P2" in upper_line:
            kronospan_marker = "VP P2"
        elif "P2EN" in upper_line:
            kronospan_marker = "P2EN"

        item = InvoiceItem(row_no=str(len(items) + 1))
        position_code = start_match.group(1)
        payload = start_match.group(2)
        item.unit = _infer_unit_from_line(line)

        payload_tokens = payload.split()
        comma_tokens = [token for token in payload_tokens if "," in token]
        if comma_tokens:
            item.net_value = _extract_decimal_from_token(comma_tokens[0])
        if len(comma_tokens) > 1:
            item.unit_price = _extract_decimal_from_token(comma_tokens[1])

        code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{3,})\b", payload)
        if code_match:
            item.article_code = code_match.group(1)
        else:
            item.article_code = position_code

        description_lines: list[str] = []
        quantity_line = ""
        code_line = ""
        packs_line = ""
        pcs_line = ""

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.match(r"^T\s*o\s*t\s*a\s*l:", next_line, re.IGNORECASE):
                break
            if re.fullmatch(r"\d+\s+\d+/", next_line):
                break
            if "SPLIT_PDF_MARK" in next_line.upper():
                j += 1
                continue
            if "C A R R Y" in next_line.upper() or "CARRY" in next_line.upper():
                break
            if next_line.upper().startswith("COUNTRY OF ORIGIN") or next_line.upper().startswith("CUSTOM TARIFF"):
                j += 1
                continue

            if "/" in next_line and "HTTP" not in next_line.upper():
                description_lines.append(next_line)
            elif re.fullmatch(r"-?[0-9][0-9.,]*", next_line):
                if not quantity_line:
                    quantity_line = next_line
            elif re.fullmatch(r"\d+\s+\d+", next_line):
                pcs_line = next_line
            elif re.search(r"PACK\(S\)", next_line, re.IGNORECASE):
                packs_line = next_line
            elif re.fullmatch(r"(?=.*[A-Z])[0-9A-Z ]{6,}", next_line):
                code_line = next_line

            j += 1

        if quantity_line:
            item.total_qty = quantity_line

        if code_line:
            refined_code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{2,}|\d{4})\b", code_line)
            if refined_code_match:
                item.article_code = refined_code_match.group(1)

        if description_lines:
            description_parts = description_lines + ([code_line] if code_line else [])
            description_text = " | ".join(description_parts)
            if kronospan_marker and kronospan_marker not in description_text.upper():
                description_text = f"{kronospan_marker} | {description_text}"
            item.description = description_text
        else:
            item.description = payload

        if packs_line:
            packs_match = re.search(r"(\d+)\s*Pack\(s\)", packs_line, re.IGNORECASE)
            if packs_match:
                item.package_qty = packs_match.group(1)

        if pcs_line:
            parts = pcs_line.split()
            if len(parts) == 2:
                if not item.package_qty:
                    item.package_qty = parts[0]
                item.pcs_total = parts[1]

        if not item.net_value and total_net_fallback and len(items) == 0:
            item.net_value = total_net_fallback

        if item.total_qty and item.net_value and not item.unit_price:
            quantity_value = _parse_eu_number(item.total_qty)
            net_value_num = _parse_eu_number(item.net_value)
            if quantity_value and net_value_num and quantity_value > 0:
                item.unit_price = _format_eu_number(net_value_num / quantity_value, 2)

        items.append(item)
        i = j

    return items


def _parse_kastamonu_or_generic_invoice_data(lines: list[str]) -> InvoiceData:
    normalized_text = "\n".join(lines)
    profile = "kastamonu" if "KASTAMONU" in normalized_text.upper() else "generic"
    data = InvoiceData(invoice_profile=profile)

    data.supplier_lines = _extract_block(lines, r"^(SELLER|SUPPLIER)\b", [r"^INVOICE\b", r"^DATE\b"])
    data.buyer_lines = _extract_block(
        lines,
        r"^(BUYER|CUSTOMER|BILL TO)\b",
        [r"^CONSIGNEE\b", r"^DELIVERY TERM\b", r"^NR\.?$", r"^ARTICLE\b"],
    )

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
            r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
            r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"\bDATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"INVOICE\s*DATE\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(normalized_text, [r"DUE\s*DATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.payment_method = _match_first(normalized_text, [r"PAYMENT\s*METHOD\s*:\s*(.+)"])
    data.payment_term = _match_first(normalized_text, [r"PAYMENT\s*TERM\s*:\s*(.+)"])
    data.delivery_term = _match_first(normalized_text, [r"DELIVERY\s*TERM\s*:\s*(.+)"])
    data.transport_mode = _match_first(normalized_text, [r"MEAN\s*OF\s*TRANSPORT\s*:\s*(.+)"])
    data.order_confirmation_no = _match_first(normalized_text, [r"ORDER\s*CONFIRMATION\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.client_ref_no = _match_first(normalized_text, [r"CLIENT'?S\s*REF\s*NO\s*:\s*(.+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"TRUCK\s*NUMBER\s*:\s*([A-Z0-9/\- ]+)"])
    data.currency = _match_first(
        normalized_text,
        [
            r"TOTAL\s*\(([A-Z]{3})\)",
            r"VALUE\s*\(([A-Z]{3})\)",
            r"PRICE/UM\s*\(([A-Z]{3})\)",
            r"CURRENCY\s*:\s*([A-Z]{3})",
        ],
    )

    data.total_net = _match_first(
        normalized_text,
        [
            r"^TOTAL\s+\d+\s+\d+\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"^TOTAL\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"NET\s*(?:VALUE|AMOUNT)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_gross = _match_first(
        normalized_text,
        [
            r"^TOTAL\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"GROSS\s*(?:VALUE|AMOUNT|TOTAL)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_m2 = _match_first(normalized_text, [r"TOTAL\s*M2\s*:\s*([0-9][0-9.,]*)"])
    data.total_m3 = _match_first(normalized_text, [r"TOTAL\s*M3\s*:\s*([0-9][0-9.,]*)"])
    data.total_net_weight = _match_first(normalized_text, [r"TOTAL\s*NET\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.total_gross_weight = _match_first(normalized_text, [r"TOTAL\s*GROSS\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.origin_country = _match_first(
        normalized_text,
        [r"ORIGIN\s*OF\s*THE\s*GOODS\s*:\s*(.+)", r"COUNTRY\s*OF\s*ORIGIN\s*:\s*(.+)"],
    )

    for idx, line in enumerate(lines):
        vat_match = re.search(r"VAT\(([\d.,]+)%\)\s*([0-9][0-9.,]*)?$", line, re.IGNORECASE)
        if not vat_match:
            continue

        rate = vat_match.group(1).replace(",", ".").strip()
        amount = vat_match.group(2) or ""
        if not amount and idx + 1 < len(lines) and re.fullmatch(r"[0-9][0-9.,]*", lines[idx + 1]):
            amount = lines[idx + 1]
        if not amount:
            amount = "0,00"

        if rate == "0":
            data.vat_0 = amount
        elif rate == "19":
            data.vat_19 = amount

    if not data.vat_0:
        data.vat_0 = _match_first(normalized_text, [r"VAT\(?0%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])
    if not data.vat_19:
        data.vat_19 = _match_first(normalized_text, [r"VAT\(?19%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])

    data.items = _parse_items(lines)
    if data.supplier_lines:
        data.supplier_name = data.supplier_lines[0]
    return data


def _parse_gamet_items(lines: list[str]) -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d+)\s+([A-Z0-9-]+)\s*$", line)
        if not start_match:
            i += 1
            continue

        row_no = start_match.group(1)
        article_code = start_match.group(2)
        description = ""
        total_qty = ""
        unit = ""
        unit_price = ""
        net_value = ""

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^\d+\s+[A-Z0-9-]+\s*$", next_line):
                break
            if next_line.startswith("Total according to VAT rates") or next_line == "Total":
                break
            if next_line.startswith("GTIN No:"):
                j += 1
                continue
            if next_line.startswith("Delivery Note(s):"):
                j += 1
                continue

            qty_match = re.match(
                r"^([0-9]+(?:\.[0-9]+)?)\s+(\S+)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Z]{3})\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+%)\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)$",
                next_line,
            )
            if qty_match:
                total_qty = qty_match.group(1)
                unit = qty_match.group(2)
                unit_price = qty_match.group(3)
                net_value = qty_match.group(5)
                j += 1
                continue

            if not description:
                description = next_line
            else:
                description = f"{description} | {next_line}"
            j += 1

        items.append(
            InvoiceItem(
                row_no=row_no,
                article_code=article_code,
                description=description,
                total_qty=total_qty,
                unit=unit,
                unit_price=unit_price,
                net_value=net_value,
            )
        )
        i = j

    return items


def _parse_gamet_invoice_data(lines: list[str], text: str) -> InvoiceData:
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="gamet", supplier_name="GAMET Sp. z o.o.")

    data.invoice_number = _match_first(normalized_text, [r"Invoice No\s*\n\s*([A-Z0-9/\-]+)"])
    data.invoice_date = _match_first(normalized_text, [r"Invoice date\s*\n\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.due_date = _match_first(normalized_text, [r"Due date:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.payment_method = _match_first(normalized_text, [r"Payment:\s*\n\s*(.+)"])
    data.payment_term = data.payment_method
    data.delivery_term = _match_first(normalized_text, [r"Delivery Terms:\s*(.+)"])
    data.transport_mode = _match_first(normalized_text, [r"Ship Via:\s*(.+)"])
    data.currency = _match_first(normalized_text, [r"Total\s*\n\s*([A-Z]{3})\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+"])
    data.total_net = _match_first(normalized_text, [r"Total\s*\n\s*[A-Z]{3}\s+([0-9.]+)\s+[0-9.]+\s+[0-9.]+"])
    data.total_gross = _match_first(normalized_text, [r"Total\s*\n\s*[A-Z]{3}\s+[0-9.]+\s+[0-9.]+\s+([0-9.]+)"])
    data.vat_0 = _match_first(normalized_text, [r"0%\s+[A-Z]{3}\s+[0-9.]+\s+([0-9.]+)\s+[0-9.]+"])
    data.total_gross_weight = _match_first(normalized_text, [r"Gross weight including transport packaging:\s*([0-9]+)\s*kgs"])
    data.order_confirmation_no = _match_first(normalized_text, [r"Order Number:\s*([A-Z0-9/\-]+)"])

    seller_block = _extract_block(lines, r"^Seller:", [r"^Buyer:"])
    buyer_block = _extract_block(lines, r"^Buyer:", [r"^Terms of", r"^Payment:"])
    data.supplier_lines = ["GAMET Sp. z o.o."] + [line for line in seller_block if not line.startswith("Address:")]
    data.buyer_lines = ["DIVIAN MEGA Kft."] + [line for line in buyer_block if not line.startswith("Address:")]

    if seller_block:
        data.supplier_lines = [lines[_find_index(lines, r"^Seller:")]] + seller_block
    if buyer_block:
        data.buyer_lines = [lines[_find_index(lines, r"^Buyer:")]] + buyer_block

    data.items = _parse_gamet_items(lines)
    return data


def _parse_kronospan_invoice_data(lines: list[str], text: str) -> InvoiceData:
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="kronospan", supplier_name="KRONOSPAN, s.r.o.")

    data.invoice_number = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)"])
    if not data.invoice_number:
        idx = _find_index(lines, r"^Invoice number$")
        if idx != -1:
            for candidate in lines[idx + 1 : idx + 12]:
                if re.fullmatch(r"\d{4,}", candidate):
                    data.invoice_number = candidate
                    break

    data.invoice_date = _match_first(
        normalized_text,
        [
            r"DATE\s*OF\s*INVOICE\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"\bDate\b[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(
        normalized_text,
        [r"PAYMENT\s*DUE\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"],
    )

    payment_idx = _find_index(lines, r"^Payment Terms")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        data.payment_term = lines[payment_idx + 1]

    data.delivery_term = _match_first(
        normalized_text,
        [r"((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)", r"TERMS\s*OF\s*DEL\.?\s*[:\-]?\s*(.+)"],
    )
    data.payment_method = "Banki átutalás"
    data.truck_number = _match_first(normalized_text, [r"TRAILER\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*([A-Z0-9/\-]+)"])

    order_idx = _find_index(lines, r"^Order Number$")
    if order_idx != -1:
        strict_match = ""
        for candidate in lines[order_idx + 1 : order_idx + 10]:
            if re.fullmatch(r"\d{5,}", candidate):
                strict_match = candidate
                break
        if strict_match:
            data.order_confirmation_no = strict_match
        else:
            for candidate in lines[order_idx + 1 : order_idx + 10]:
                if re.fullmatch(r"[A-Z0-9/\-]{4,}", candidate) and not re.fullmatch(
                    r"\d{1,2}\.\d{1,2}\.\d{2,4}",
                    candidate,
                ):
                    data.order_confirmation_no = candidate
                    break

    ref_idx = _find_index(lines, r"^Your Reference$")
    if ref_idx != -1:
        for candidate in lines[ref_idx + 1 : ref_idx + 8]:
            if "/" in candidate and "ORDER DATE" not in candidate.upper():
                data.client_ref_no = candidate
                break

    vat_no = _match_first(normalized_text, [r"VAT\s*-\s*NO\.?\s*([A-Z0-9]+?)(?:DELIVERY|\s|$)"])
    seller_vat_id = _match_first(
        normalized_text,
        [r"VAT\s*ID\s*NO[\W_:.]*([A-Z]{2}\s*\d[\d\s]{5,})"],
    ).replace(" ", "")
    if not seller_vat_id:
        seller_vat_id = _saved_seller_vat_number(data.invoice_profile, data.supplier_name)
    tax_idx = _find_index(lines, r"^Tax No\.")
    if tax_idx != -1:
        data.buyer_lines = [line for line in lines[max(0, tax_idx - 4) : tax_idx] if line]
    else:
        despatch_idx = _find_index(lines, r"^Despatch Address")
        if despatch_idx != -1 and despatch_idx + 1 < len(lines):
            data.buyer_lines = [lines[despatch_idx + 1]]
    if vat_no:
        data.buyer_lines.append(f"VAT NUMBER: {vat_no}")
    data.buyer_lines = list(dict.fromkeys(data.buyer_lines))

    data.supplier_lines = [data.supplier_name]
    if seller_vat_id:
        data.supplier_lines.append(f"VAT ID No.: {seller_vat_id}")
    for label in ("BANK:", "IBAN:", "SWIFT:"):
        idx = _find_index(lines, f"^{re.escape(label)}")
        if idx != -1:
            data.supplier_lines.append(lines[idx])

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[-0-9.,]+\s*VALUE\s*OF\s*GOODS",
            r"\b(EUR)\s*[-0-9.,]+\s*TOTAL\s*AMOUNT",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*VALUE\s*OF\s*GOODS"])
    data.total_gross = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*TOTAL\s*AMOUNT"])

    discount_match = re.search(r"EUR\s*([-0-9.,]+)\s*([0-9]+,[0-9]{2})?\s*DISCOUNT\s*%", normalized_text, re.IGNORECASE)
    if discount_match:
        discount_blob = (discount_match.group(1) or "").strip()
        percent = (discount_match.group(2) or "").strip()
        split_match = re.fullmatch(r"(-?[0-9.]+,[0-9]{2})([0-9]+,[0-9]{2})", discount_blob)
        if split_match and not percent:
            data.discount_amount = split_match.group(1)
            data.discount_percent = split_match.group(2)
        else:
            data.discount_amount = discount_blob
            data.discount_percent = percent

    totals_idx = _find_index(lines, r"^T\s*o\s*t\s*a\s*l:")
    if totals_idx != -1:
        totals_line = lines[totals_idx]
        m_pcs = re.search(r"pcs\.\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m2 = re.search(r"m2\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m3 = re.search(r"m3\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_gross_weight = re.search(r"gross\s*to\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if m_pcs:
            data.total_pcs = m_pcs.group(1)
        if m_m2:
            data.total_m2 = m_m2.group(1)
        if m_m3:
            data.total_m3 = m_m3.group(1)
        if m_gross_weight:
            data.total_gross_weight = _normalize_kronospan_weight(m_gross_weight.group(1))

    if not data.total_m2:
        data.total_m2 = _match_first(normalized_text, [r"\bm2\s*:\s*([0-9][0-9.,]*)"])
    if not data.total_m3:
        data.total_m3 = _match_first(normalized_text, [r"\bm3\s*:\s*([0-9][0-9.,]*)"])
    data.origin_country = _match_first(normalized_text, [r"COUNTRY\s*OF\s*ORIGIN\s*:\s*([A-Z]{2,})"])

    if "VAT EXEMPT" in normalized_text.upper():
        data.vat_0 = "0,00"
        data.vat_19 = "0,00"

    data.items = _parse_kronospan_items(lines, total_net_fallback=data.total_net)
    if data.total_pcs and data.items:
        has_any_pcs = any(item.pcs_total for item in data.items)
        if not has_any_pcs and len(data.items) == 1:
            data.items[0].pcs_total = data.total_pcs

    return data


def _parse_divian_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if "Á T V I T E L" in upper_line or "ÁT VITEL" in upper_line:
            i += 1
            continue
        if "STCK" not in upper_line and "M2" not in upper_line:
            i += 1
            continue

        item = InvoiceItem(row_no=str(len(items) + 1))
        payload = start_match.group(2)
        item.article_code = start_match.group(1)

        quantity_match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", line)
        if quantity_match:
            item.total_qty = quantity_match.group(0)
        if "M2" in upper_line:
            item.unit = "m2"
        elif "STCK" in upper_line:
            item.unit = "stck"

        description_parts: list[str] = []
        base_description = re.sub(r"\d{1,3}(?:\.\d{3})*,\d{2}.*$", "", payload).strip()
        if base_description:
            description_parts.append(base_description)

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            upper_next = next_line.upper()

            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.search(r"nettó\s*to:", next_line, re.IGNORECASE):
                break
            if "Á T V I T E L" in upper_next or "ÁT VITEL" in upper_next:
                break
            if upper_next.startswith("MINDEN TÉTEL") or upper_next.startswith("A KITERJESZTETT GYÁRTÓI"):
                break

            if upper_next.startswith("EAN:") or upper_next.startswith("RÉSZSZ.:"):
                j += 1
                continue
            if upper_next.startswith("SZÁRMAZÁSI ORSZÁG") or upper_next.startswith("VÁMTARIFASZÁM"):
                j += 1
                continue

            if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", next_line):
                if not item.net_value:
                    item.net_value = next_line
                j += 1
                continue

            article_match = re.match(r"^(\d{4})\s+([A-Z0-9]{2,})$", next_line, re.IGNORECASE)
            if article_match:
                item.article_code = article_match.group(1)
                j += 1
                continue

            pcs_match = re.fullmatch(r"(\d+)\s+([0-9.]+)", next_line)
            if pcs_match:
                item.package_qty = pcs_match.group(1)
                item.pcs_total = pcs_match.group(2)
                j += 1
                continue

            package_match = re.search(
                r"(\d+)\s*csomag\(ok\)\s*a\s*([0-9.]+)\s*darab",
                next_line,
                re.IGNORECASE,
            )
            if package_match:
                item.package_qty = package_match.group(1)
                if not item.pcs_total:
                    try:
                        packages = int(package_match.group(1))
                        per_package = int(package_match.group(2).replace(".", ""))
                        item.pcs_total = str(packages * per_package)
                    except ValueError:
                        pass
                j += 1
                continue

            if "/" in next_line or re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{3,}", next_line):
                description_parts.append(next_line)

            j += 1

        unique_descriptions: list[str] = []
        for part in description_parts:
            cleaned_part = _fix_hungarian_mojibake(_clean_spaces(part))
            if cleaned_part and cleaned_part not in unique_descriptions:
                unique_descriptions.append(cleaned_part)

        if unique_descriptions:
            item.description = " | ".join(unique_descriptions[:3])
        else:
            item.description = _fix_hungarian_mojibake(_clean_spaces(payload))

        if not item.net_value and total_net_fallback and not items:
            item.net_value = total_net_fallback

        items.append(item)
        i = j

    return items


def _parse_divian_invoice_data(lines: list[str], text: str) -> InvoiceData:
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="divian")

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"Számla\s*száma[\s\S]{0,120}?(\d{5,})",
            r"\b(\d{5,}/DIVI\d+)\b",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"számla\s*dátuma\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"Kiállítás\s*dátuma[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.order_confirmation_no = _match_first(
        normalized_text,
        [
            r"\b(WO\d{4,})\b",
            r"Rendelésszám[\s\S]{0,80}?([A-Z0-9/\-]{4,})",
        ],
    )
    data.delivery_note_no = _match_first(normalized_text, [r"Út\s*száma\s*([A-Z0-9/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"Trailer\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_term = _match_first(
        normalized_text,
        [r"\b((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)\b"],
    )

    payment_idx = _find_index(lines, r"^Fizetési feltétel:?$")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        payment_value = _fix_hungarian_mojibake(lines[payment_idx + 1])
        data.payment_term = payment_value
        data.payment_method = payment_value

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[0-9][0-9.,]*\s*Áruérték",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Áruérték"])
    data.total_gross = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Végső\s*összeg"])

    vat_match = re.search(
        r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*([0-9]{1,2},[0-9]{2})\s*ÁFA",
        normalized_text,
        re.IGNORECASE,
    )
    if vat_match:
        vat_amount = vat_match.group(1)
        vat_rate = vat_match.group(2).replace(",", ".")
        if vat_rate.startswith("0"):
            data.vat_0 = vat_amount
        else:
            data.vat_19 = vat_amount

    totals_line = ""
    for line in lines:
        if re.search(r"nettó\s*to:", line, re.IGNORECASE) and re.search(r"bruttó\s*to:", line, re.IGNORECASE):
            totals_line = line
            break

    if totals_line:
        net_weight_match = re.search(r"nettó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        gross_weight_match = re.search(r"bruttó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        pcs_match = re.search(r"Stck:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m2_match = re.search(r"m2:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m3_match = re.search(r"m3:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if net_weight_match:
            data.total_net_weight = net_weight_match.group(1)
        if gross_weight_match:
            data.total_gross_weight = gross_weight_match.group(1)
        if pcs_match:
            data.total_pcs = pcs_match.group(1)
        if m2_match:
            data.total_m2 = m2_match.group(1)
        if m3_match:
            data.total_m3 = m3_match.group(1)

    data.origin_country = _match_first(normalized_text, [r"Származási ország\s*:\s*([A-Z]{2,})"])

    company_blocks: list[list[str]] = []
    seller_candidates: list[tuple[int, list[str]]] = []
    for idx, line in enumerate(lines):
        if "DIVIAN-MEGA KFT" not in line.upper():
            continue

        buyer_block = [line]
        for candidate in lines[idx + 1 : idx + 6]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("RENDELÉSI ADATOK") or upper_candidate.startswith("ADÓSZÁM"):
                break
            if upper_candidate.startswith("CÉGJEGYZÉKSZÁM") or upper_candidate.startswith("EUR "):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            buyer_block.append(candidate)
            if len(buyer_block) >= 3:
                break
        if len(buyer_block) >= 2:
            fixed_buyer_block = [_fix_hungarian_mojibake(entry) for entry in buyer_block]
            company_blocks.append(list(dict.fromkeys(fixed_buyer_block)))

        seller_block = [line]
        seller_score = 0
        for candidate in lines[idx + 1 : idx + 9]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("EUR ") or upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            if upper_candidate.startswith("MNB ÁRFOLYAM") or upper_candidate.startswith("Ö S S Z E S E N"):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("SZÁMLA") or upper_candidate.startswith("OLDAL"):
                break
            seller_block.append(candidate)
            if upper_candidate.startswith("ADÓSZÁM"):
                seller_score += 3
            elif upper_candidate.startswith("CÉGJEGYZÉKSZÁM"):
                seller_score += 2
            elif re.search(r"\b\d{4}\s+[A-ZÁÉÍÓÖŐÚÜŰ]", upper_candidate):
                seller_score += 1

        fixed_seller_block = [_fix_hungarian_mojibake(entry) for entry in seller_block if _clean_spaces(entry)]
        if len(fixed_seller_block) >= 2:
            deduped_seller_block = list(dict.fromkeys(fixed_seller_block[:5]))
            seller_candidates.append((seller_score + len(deduped_seller_block), deduped_seller_block))

    if company_blocks:
        preferred_block = next((b for b in company_blocks if re.search(r"\b\d{4}\b", " ".join(b))), company_blocks[0])
        data.buyer_lines = preferred_block

    if seller_candidates:
        seller_candidates.sort(key=lambda x: x[0], reverse=True)
        data.supplier_lines = seller_candidates[0][1]
        data.supplier_name = data.supplier_lines[0]
    elif company_blocks:
        data.supplier_lines = company_blocks[0]
        data.supplier_name = data.supplier_lines[0]

    data.items = _parse_divian_items(lines, total_net_fallback=data.total_net)
    return data


def parse_invoice_data(text: str) -> InvoiceData:
    lines = [_clean_spaces(raw) for raw in text.splitlines() if _clean_spaces(raw)]
    profile = _detect_invoice_profile(lines, text)
    if profile == "kronospan":
        return _parse_kronospan_invoice_data(lines, text)
    if profile == "gamet":
        return _parse_gamet_invoice_data(lines, text)
    if profile == "divian":
        return _parse_divian_invoice_data(lines, text)
    return _parse_kastamonu_or_generic_invoice_data(lines)


def parse_fields(text: str) -> dict[str, str]:
    data = parse_invoice_data(text)
    return {
        "invoice_number": data.invoice_number,
        "invoice_date": data.invoice_date,
        "supplier": " | ".join(data.supplier_lines),
        "customer": " | ".join(data.buyer_lines),
        "total_amount": data.total_gross or data.total_net,
        "vat_amount": data.vat_19 or data.vat_0,
    }


def _to_invoice_data(parsed: InvoiceData | dict[str, str]) -> InvoiceData:
    if isinstance(parsed, InvoiceData):
        return parsed

    data = InvoiceData()
    data.invoice_profile = parsed.get("invoice_profile", "")
    data.supplier_name = parsed.get("supplier_name", "")
    data.invoice_number = parsed.get("invoice_number", "")
    data.invoice_date = parsed.get("invoice_date", "")
    supplier = parsed.get("supplier", "")
    customer = parsed.get("customer", "")
    data.supplier_lines = [line.strip() for line in supplier.split("|") if line.strip()]
    data.buyer_lines = [line.strip() for line in customer.split("|") if line.strip()]
    data.total_gross = parsed.get("total_amount", "")
    data.vat_19 = parsed.get("vat_amount", "")
    return data


def _html_text(value: str) -> str:
    return html.escape(_value_or_default(value))


def _html_party(lines: list[str]) -> str:
    if not lines:
        return html.escape(NO_DATA)
    html_lines: list[str] = []
    for line in lines:
        cleaned = _clean_spaces(line)
        if not cleaned:
            continue
        html_lines.append(html.escape(cleaned))
    return "<br>".join(html_lines)


def _html_table_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(f"<tr><th>{html.escape(label)}</th><td>{_html_text(value)}</td></tr>" for label, value in rows)


def _non_empty_rows(rows: list[tuple[str, str]], keep_labels: set[str] | None = None) -> list[tuple[str, str]]:
    if keep_labels is None:
        keep_labels = set()
    filtered: list[tuple[str, str]] = []
    for label, value in rows:
        if label in keep_labels:
            filtered.append((label, value))
            continue
        if _clean_spaces(value):
            filtered.append((label, value))
    return filtered


def _split_vehicle_plates(raw_value: str) -> tuple[str, str]:
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return "", ""

    direct_parts = [part.strip() for part in re.split(r"\s*/\s*|\s*;\s*|\s+\|\s+", cleaned) if part.strip()]
    if len(direct_parts) >= 2:
        return direct_parts[0], direct_parts[1]

    plate_like = re.findall(r"\b[A-Z]{1,4}\d{1,4}[A-Z]{0,3}\b", cleaned.upper())
    if len(plate_like) >= 2:
        return plate_like[0], plate_like[1]

    tokens = cleaned.split()
    if len(tokens) >= 2:
        return tokens[0], tokens[1]

    return cleaned, ""


def _is_takarotabla_item(description: str) -> bool:
    normalized = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    return normalized.startswith("PAL BRUT")


def _detect_product_type(description: str, article_code: str = "", invoice_profile: str = "") -> str:
    normalized_description = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    normalized_code = _fix_hungarian_mojibake(_clean_spaces(article_code)).upper()
    normalized_profile = _fix_hungarian_mojibake(_clean_spaces(invoice_profile)).lower()
    text = f"{normalized_description} {normalized_code}".upper()
    description_prefix = normalized_description.split(" ", 1)[0] if normalized_description else ""
    code_prefix = normalized_code.split(" ", 1)[0] if normalized_code else ""

    if _is_takarotabla_item(description):
        return "takarótábla"
    if normalized_profile == "gamet" and (normalized_code == "TRANSPORT" or "KOSZT TRANSPORTU" in normalized_description):
        return "szállítás"
    if normalized_profile == "gamet":
        return "fogantyú"
    if normalized_profile == "kronospan":
        if "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
            return "munkalap"
        if "SPLASHBACK" in text:
            return "falipanel"
        if "MF PB" in text or "VP P2" in text or "P2EN" in text:
            return "bútorlap"
    if description_prefix.startswith("SP") or code_prefix.startswith("SP"):
        return "falipanel"
    if (
        description_prefix.startswith("WT")
        or description_prefix.startswith("NT")
        or code_prefix.startswith("WT")
        or code_prefix.startswith("NT")
    ):
        return "munkalap"
    if description_prefix.startswith("NFC") or code_prefix.startswith("NFC"):
        return "bútorlap"
    if "EVOGLOSS" in text or "EVGLS" in text:
        return "evogloss lap"
    if "MUNKALAP" in text or "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
        return "munkalap"
    if (
        "HÁTFAL" in text
        or "HATFAL" in text
        or "HDF THIN" in text
        or "THIN PLUS" in text
        or "BACKWALL" in text
        or "BACK WALL" in text
        or "BACKPANEL" in text
        or "BACK PANEL" in text
    ):
        return "hátfal"
    if "FALIPANEL" in text or ("WALL" in text and "PANEL" in text):
        return "falipanel"
    return "bútorlap"


def _render_invoice_item_row(item: InvoiceItem, invoice_profile: str = "") -> str:
    product_type = _detect_product_type(item.description, item.article_code, invoice_profile=invoice_profile)
    missing_placeholder = "-" if product_type == "takarótábla" else NO_DATA
    if _fix_hungarian_mojibake(_clean_spaces(invoice_profile)).lower() == "gamet":
        return (
            "<tr>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.row_no, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.article_code, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(product_type)}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.total_qty, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.unit, missing_placeholder))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price, missing_placeholder))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.net_value, missing_placeholder))}</td>"
            "</tr>"
        )
    return (
        "<tr>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.row_no, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.article_code, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(product_type)}</td>"
        f"<td>{html.escape(_item_value_or_default(item.description, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.package_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.pcs_total, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.total_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.unit, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.net_value, missing_placeholder))}</td>"
        "</tr>"
    )


def _render_invoice_total_row(data: InvoiceData) -> str:
    total_value = _item_value_or_default(data.total_gross or data.total_net)
    if _fix_hungarian_mojibake(_clean_spaces(data.invoice_profile)).lower() == "gamet":
        colspan = "6"
    else:
        colspan = "9"
    return (
        "<tr class='total-row'>"
        f"<td colspan='{colspan}'><strong>Végösszeg</strong></td>"
        f"<td class='right'><strong>{html.escape(total_value)}</strong></td>"
        "</tr>"
    )


def create_printable_html(parsed: InvoiceData | dict[str, str], source_filename: str = "") -> bytes:
    data = _to_invoice_data(parsed)
    truck_plate, trailer_plate = _split_vehicle_plates(data.truck_number)
    vehicle_plates = ""
    if truck_plate and trailer_plate:
        vehicle_plates = f"{truck_plate} - {trailer_plate}"
    elif truck_plate:
        vehicle_plates = truck_plate
    elif trailer_plate:
        vehicle_plates = trailer_plate

    rounded_net_weight = _format_rounded_weight(data.total_net_weight) if data.total_net_weight else ""
    rounded_gross_weight = _format_rounded_weight(data.total_gross_weight) if data.total_gross_weight else ""
    invoice_date_display = _format_invoice_date(data.invoice_date)
    due_date_display = _format_invoice_date(data.due_date)
    source_label = html.escape(source_filename) if source_filename else "feltöltött PDF"
    compact_mode = len(data.items) >= 10 or (len(data.supplier_lines) + len(data.buyer_lines)) >= 12
    body_class = "compact" if compact_mode else ""
    profile_label = {
        "kastamonu": "Kastamonu sablon",
        "kronospan": "Kronospan sablon",
        "gamet": "Gamet sablon",
        "divian": "DIVI sablon",
        "generic": "Általános sablon",
        "": "Általános sablon",
    }.get(data.invoice_profile, "Általános sablon")

    supplier_vat_number = _extract_party_vat_number(data.supplier_lines)
    buyer_vat_number = _extract_party_vat_number(data.buyer_lines)
    important_fields = [
        ("Eladó VAT szám", supplier_vat_number),
        ("Vevő VAT szám", buyer_vat_number),
        ("Számlaszám", data.invoice_number),
        ("Számla dátuma", invoice_date_display),
        ("Pénznem", data.currency),
        ("Összeg", data.total_net),
    ]
    important_rows = _html_table_rows(important_fields)

    info_field_rows = [
        ("Számlaszám", data.invoice_number),
        ("Számla dátuma", invoice_date_display),
        ("Fizetési határidő", due_date_display),
        ("Fizetési mód", data.payment_method),
        ("Szállítólevél száma", data.delivery_note_no),
    ]
    keep_labels = {"Számlaszám", "Számla dátuma"}
    if data.invoice_profile != "gamet":
        info_field_rows.append(("Gépjármű azonosító", vehicle_plates))
        keep_labels.add("Gépjármű azonosító")
    info_fields = _non_empty_rows(info_field_rows, keep_labels=keep_labels)
    info_rows = _html_table_rows(info_fields)

    discount_label = "Engedmény"
    if data.discount_percent:
        discount_label = f"Engedmény ({data.discount_percent}%)"

    summary_fields_raw: list[tuple[str, str]] = [
        ("Pénznem", data.currency),
        ("Összeg", data.total_net),
        (discount_label, data.discount_amount),
        ("Kedvezményes összeg", data.total_gross),
    ]
    summary_fields_raw.extend(
        [
            ("Nettó tömeg (kg)", rounded_net_weight),
            ("Bruttó tömeg (kg)", rounded_gross_weight),
            ("Származási ország", data.origin_country),
        ]
    )
    summary_fields = _non_empty_rows(
        summary_fields_raw,
        keep_labels={"Pénznem", "Összeg", "Kedvezményes összeg"},
    )
    summary_rows = _html_table_rows(summary_fields)

    if data.items:
        item_rows = "".join(
            _render_invoice_item_row(item, data.invoice_profile)
            for item in data.items
        )
        item_rows += _render_invoice_total_row(data)
    else:
        empty_colspan = "7" if data.invoice_profile == "gamet" else "10"
        item_rows = f"<tr><td colspan='{empty_colspan}'>Nem sikerült tételsorokat felismerni.</td></tr>"

    if data.invoice_profile == "gamet":
        items_header = """
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikkszám</th>
          <th class="center">Termék típus</th>
          <th class="right">Mennyiség</th>
          <th class="center">ME</th>
          <th class="right">Egységár</th>
          <th class="right">Nettó érték</th>
        </tr>
        """
    else:
        items_header = """
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikkszám</th>
          <th class="center">Termék típus</th>
          <th>Megnevezés</th>
          <th class="center">Rakat</th>
          <th class="center">Össz. db</th>
          <th class="right">Mennyiség</th>
          <th class="center">ME</th>
          <th class="right">Egységár</th>
          <th class="right">Nettó érték</th>
        </tr>
        """

    important_box_html = f"""
    <section class="important-box">
      <h2>Fontos Adatok</h2>
      <table class="important-grid">
        <tbody>{important_rows}</tbody>
      </table>
    </section>
"""

    parties_html = f"""
    <section class="parties">
      <article class="panel">
        <h2>Eladó</h2>
        <p>{_html_party(data.supplier_lines)}</p>
      </article>
      <article class="panel">
        <h2>Vevő</h2>
        <p>{_html_party(data.buyer_lines)}</p>
      </article>
    </section>
"""
    identity_html = f"""
    <section class="identity-grid">
      {parties_html}
      {important_box_html}
    </section>
"""

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Nyomtatható számlakivonat</title>
  <style>
    :root {{
      --bg: #061018;
      --bg-soft: #0b1a26;
      --ink: #11202b;
      --ink-deep: #08131b;
      --muted: #58717c;
      --line: #cfdee2;
      --surface: #ffffff;
      --accent: #36d7c3;
      --accent-strong: #149c90;
      --accent-soft: #e3fff8;
      --accent-warm: #c7ff7a;
      --paper: #eff5f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 1rem 1rem 1.25rem;
      background:
        radial-gradient(900px 360px at 0% 0%, rgba(54, 215, 195, .18), transparent 60%),
        radial-gradient(760px 320px at 100% 0%, rgba(199, 255, 122, .12), transparent 55%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.32;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .toolbar {{
      max-width: 210mm;
      margin: 0 auto .65rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
      padding: 0 .15rem;
    }}
    .toolbar-group {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
    }}
    .toolbar-note {{
      color: rgba(237, 247, 247, .72);
      font-size: .76rem;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .toolbar button,
    .toolbar a {{
      border: 1px solid rgba(54, 215, 195, .22);
      background: rgba(7, 17, 26, .72);
      color: #edf7f7;
      padding: .55rem .86rem;
      border-radius: 999px;
      cursor: pointer;
      font-size: .84rem;
      font-weight: 700;
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
      backdrop-filter: blur(12px);
    }}
    .toolbar a {{
      color: #edf7f7;
    }}
    .toolbar button {{
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      border-color: transparent;
      color: #041017;
    }}
    .toolbar button:hover,
    .toolbar a:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 22px rgba(0, 0, 0, .2);
      border-color: rgba(54, 215, 195, .4);
    }}
    .sheet {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto .8rem;
      background: var(--surface);
      padding: 8.5mm 8.5mm 8mm;
      border: 1px solid #d6e7e8;
      border-top: 6px solid var(--accent-strong);
      border-radius: 18px;
      box-shadow: 0 24px 50px rgba(0, 0, 0, .28);
      position: relative;
      overflow: hidden;
    }}
    .sheet::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(135deg, rgba(54, 215, 195, .08), transparent 28%),
        linear-gradient(180deg, transparent, rgba(54, 215, 195, .03));
      pointer-events: none;
    }}
    .head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.2rem;
      border-bottom: 1px solid #d9e7e8;
      padding-bottom: .55rem;
      margin-bottom: .75rem;
      position: relative;
      z-index: 1;
    }}
    .head-copy {{
      max-width: 62%;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: .38rem;
      padding: .24rem .5rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      letter-spacing: .12em;
      text-transform: uppercase;
      font-size: .64rem;
      font-weight: 800;
      margin-bottom: .45rem;
    }}
    .head h1 {{
      margin: 0;
      font-size: 1.14rem;
      letter-spacing: .12px;
      color: var(--ink-deep);
    }}
    .head-copy p {{
      margin: .3rem 0 0;
      color: var(--muted);
      font-size: .78rem;
    }}
    .meta {{
      min-width: 220px;
      display: grid;
      gap: .34rem;
    }}
    .meta div {{
      padding: .44rem .58rem;
      border: 1px solid #d9e7e8;
      border-radius: 10px;
      background: linear-gradient(180deg, #fcfefe 0%, #f5fbfb 100%);
      font-size: .73rem;
      color: var(--muted);
    }}
    .meta strong {{
      display: block;
      margin-top: .08rem;
      color: var(--ink-deep);
      font-size: .82rem;
    }}
    .parties {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .6rem;
      margin-bottom: .62rem;
      position: relative;
      z-index: 1;
    }}
    .identity-grid {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(72mm, .92fr);
      gap: .6rem;
      align-items: stretch;
      margin-bottom: .62rem;
      position: relative;
      z-index: 1;
    }}
    .identity-grid .parties,
    .identity-grid .important-box {{
      margin-bottom: 0;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .5rem;
      margin-bottom: .48rem;
      align-items: start;
      position: relative;
      z-index: 1;
    }}
    .meta-card {{
      min-width: 0;
    }}
    .important-box {{
      margin: 0 0 .62rem;
      padding: .46rem .54rem;
      border: 1px solid #d5e5e6;
      border-left: 4px double var(--ink-deep);
      border-radius: 12px;
      background: linear-gradient(180deg, #fefefe 0%, #f4fbfb 100%);
      position: relative;
      z-index: 1;
    }}
    .important-box h2 {{
      margin: 0 0 .24rem 0;
      font-size: .76rem;
      color: var(--accent-strong);
      text-transform: uppercase;
      letter-spacing: .14em;
    }}
    .important-grid {{
      margin: 0;
      table-layout: fixed;
      font-size: .79rem;
    }}
    .important-grid th,
    .important-grid td {{
      padding: 6px;
      line-height: 1.28;
    }}
    .important-grid th {{
      width: 44%;
      white-space: nowrap;
    }}
    .important-grid td {{
      font-size: .86rem;
      font-weight: 800;
      color: var(--ink-deep);
    }}
    .panel {{
      border: 1px solid #d5e5e6;
      border-radius: 12px;
      padding: .46rem .54rem;
      background: linear-gradient(180deg, #fefefe 0%, #f4fbfb 100%);
    }}
    .panel h2 {{
      margin: 0 0 .24rem 0;
      font-size: .74rem;
      color: var(--accent-strong);
      text-transform: uppercase;
      letter-spacing: .14em;
    }}
    .panel p {{
      margin: 0;
      white-space: normal;
      font-size: .8rem;
    }}
    h3 {{
      margin: .58rem 0 .24rem 0;
      font-size: .76rem;
      text-transform: uppercase;
      letter-spacing: .14em;
      color: var(--accent-strong);
      border-left: 3px solid var(--accent);
      padding-left: .42rem;
      position: relative;
      z-index: 1;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .74rem;
      margin-bottom: .42rem;
      position: relative;
      z-index: 1;
    }}
    th,
    td {{
      border: 1px solid var(--line);
      padding: .18rem .24rem;
      vertical-align: top;
    }}
    th {{
      background: linear-gradient(180deg, #f3fefb 0%, #e9faf6 100%);
      font-weight: 700;
      text-align: left;
    }}
    .kv {{
      table-layout: fixed;
      margin-bottom: 0;
    }}
    .meta-card .kv {{
      font-size: .79rem;
    }}
    .meta-card .kv th,
    .meta-card .kv td {{
      padding: 6px;
      line-height: 1.28;
    }}
    .meta-card .kv th {{
      width: 58%;
      white-space: nowrap;
    }}
    .meta-card .kv td {{
      font-weight: 600;
    }}
    .items td:nth-child(4) {{ line-height: 1.2; }}
    .items tbody tr:nth-child(even) {{
      background: #f8fcfb;
    }}
    .center {{ text-align: center; }}
    .right {{ text-align: right; }}
    .footnote {{
      margin-top: .38rem;
      border-top: 1px dashed #b7cfd0;
      padding-top: .32rem;
      font-size: .68rem;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }}
    body.compact .sheet {{
      padding: 7.8mm 8mm 7.4mm;
    }}
    body.compact .head h1 {{
      font-size: 1.02rem;
    }}
    body.compact .meta {{
      gap: .3rem;
    }}
    body.compact .meta div {{
      font-size: .7rem;
      padding: .38rem .5rem;
    }}
    body.compact .panel p {{
      font-size: .76rem;
    }}
    body.compact h3 {{
      margin: .42rem 0 .2rem 0;
      font-size: .74rem;
    }}
    body.compact table {{
      font-size: .72rem;
      margin-bottom: .34rem;
    }}
    body.compact th,
    body.compact td {{
      padding: .14rem .18rem;
    }}
    body.compact .meta-card .kv {{
      font-size: .74rem;
    }}
    body.compact .meta-card .kv th,
    body.compact .meta-card .kv td {{
      padding: 5px;
      line-height: 1.22;
    }}
    body.compact .meta-card .kv th {{
      width: 55%;
    }}
    @media (max-width: 860px) {{
      body {{
        padding: .65rem;
      }}
      .toolbar {{
        justify-content: center;
      }}
      .toolbar-note {{
        width: 100%;
        text-align: center;
      }}
      .meta-grid {{
        grid-template-columns: 1fr;
      }}
      .identity-grid {{
        grid-template-columns: 1fr;
      }}
      .parties {{
        grid-template-columns: 1fr;
      }}
      .head {{
        flex-direction: column;
      }}
      .head-copy {{
        max-width: none;
      }}
      .meta {{
        width: 100%;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @page {{
      size: 210mm 297mm;
      margin: 6mm;
    }}
    @media print {{
      html {{
        width: 100%;
        min-height: 297mm;
      }}
      body {{
        width: 100%;
        min-height: 285mm;
        padding: 0;
        background: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .toolbar {{ display: none; }}
      .sheet {{
        margin: 0 auto;
        width: 198mm;
        max-width: 198mm;
        min-height: auto;
        padding: 8.8mm 9mm 8.2mm;
        border: 1px solid #d6e7e8;
        border-top: 6px solid var(--accent-strong);
        border-radius: 0;
        box-shadow: none;
        transform: none;
      }}
      .identity-grid {{
        grid-template-columns: minmax(0, 2fr) minmax(72mm, .92fr);
        align-items: stretch;
      }}
      .meta-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .identity-grid .parties,
      .parties {{
        grid-template-columns: 1fr 1fr;
      }}
      .identity-grid .important-box,
      .identity-grid .parties {{
        margin-bottom: 0;
      }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body class="{body_class}">
  <div class="toolbar">
    <span class="toolbar-note">Divian-HUB // nyomtatható kivonat</span>
    <div class="toolbar-group">
      <a href="/">Főoldal</a>
      <a href="{APP_ROUTE}">Új számla</a>
      <button onclick="window.print()">Nyomtatás / Mentés PDF-be</button>
    </div>
  </div>
  <main class="sheet">
    <header class="head">
      <div class="head-copy">
        <div class="eyebrow">Divian-HUB kimenet</div>
        <h1>Külföldi számla magyar fordítása</h1>
        <p>Automatikusan generált, nyomtatható kivonat egységes vállalati megjelenéssel.</p>
      </div>
      <div class="meta">
        <div>Gyártó<strong>{html.escape(data.supplier_name or NO_DATA)}</strong></div>
        <div>Sablon<strong>{profile_label}</strong></div>
        <div>Forrás<strong>{source_label}</strong></div>
      </div>
    </header>

{identity_html}

    <section class="meta-grid">
      <article class="meta-card">
        <h3>Számla adatok</h3>
        <table class="kv">
          <tbody>{info_rows}</tbody>
        </table>
      </article>
      <article class="meta-card">
        <h3>Összesítés</h3>
        <table class="kv">
          <tbody>{summary_rows}</tbody>
        </table>
      </article>
    </section>

    <h3>Tételek</h3>
    <table class="items">
      <thead>
        {items_header}
      </thead>
      <tbody>{item_rows}</tbody>
    </table>

    <div class="footnote">
      Ez egy automatikusan generált, nyomtatható fordítási kivonat.
    </div>
  </main>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")


def render_form(message: str = "") -> bytes:
    msg_html = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Számla magyarító</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <style>
    :root {{
      --bg: #040b12;
      --bg-soft: #09131c;
      --panel: rgba(8, 18, 28, 0.84);
      --panel-strong: rgba(10, 22, 33, 0.94);
      --border: rgba(84, 191, 214, 0.18);
      --line: rgba(84, 191, 214, 0.12);
      --text: #f3fbff;
      --muted: #8ea8b8;
      --accent: #43decf;
      --accent-strong: #1197a2;
      --accent-warm: #ff8b64;
      --danger-bg: rgba(88, 27, 28, 0.78);
      --danger-line: rgba(255, 139, 100, 0.34);
      --shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-width: 320px;
      font-family: "Manrope", sans-serif;
      background:
        radial-gradient(circle at 14% 16%, rgba(67, 222, 207, 0.2), transparent 24%),
        radial-gradient(circle at 82% 10%, rgba(255, 139, 100, 0.15), transparent 18%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
      color: var(--text);
      overflow-x: hidden;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    button,
    input {{
      font: inherit;
    }}
    .site {{
      position: relative;
      min-height: 100vh;
      padding: 20px 24px 36px;
    }}
    .site::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(84, 191, 214, 0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(84, 191, 214, 0.04) 1px, transparent 1px);
      background-size: 72px 72px;
      mask-image: radial-gradient(circle at center, black 35%, transparent 85%);
      pointer-events: none;
      z-index: -1;
    }}
    .topbar,
    .content {{
      width: min(1080px, calc(100vw - 48px));
      margin-inline: auto;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 16px 20px;
      background: rgba(7, 16, 24, 0.76);
      border: 1px solid var(--border);
      backdrop-filter: blur(18px);
      border-radius: 999px;
      box-shadow: var(--shadow);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-mark {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 35% 35%, #ffffff, transparent 28%),
        radial-gradient(circle, var(--accent-warm), var(--accent-strong));
      box-shadow:
        0 0 0 8px rgba(67, 222, 207, 0.08),
        0 0 28px rgba(67, 222, 207, 0.22);
    }}
    .brand-text {{
      display: grid;
      gap: 3px;
    }}
    .brand-text strong,
    h1,
    h2,
    .surface-title strong {{
      font-family: "Space Grotesk", sans-serif;
    }}
    .brand-text strong {{
      font-size: 0.98rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .brand-text small {{
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .nav {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      justify-content: center;
      gap: 18px;
      color: var(--muted);
      font-weight: 600;
    }}
    .nav a {{
      transition: color 180ms ease;
    }}
    .nav a:hover,
    .nav a:focus-visible {{
      color: var(--text);
    }}
    .ghost-link,
    .nav-cta,
    .button,
    .primary-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 20px;
      border-radius: 999px;
      font-weight: 700;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        background 180ms ease,
        color 180ms ease;
    }}
    .ghost-link {{
      border: 1px solid var(--border);
      color: var(--text);
      background: rgba(255, 255, 255, 0.06);
    }}
    .button,
    .primary-button {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      cursor: pointer;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .nav-cta {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      font-weight: 800;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .ghost-link:hover,
    .nav-cta:hover,
    .button:hover,
    .primary-button:hover,
    .nav-cta:focus-visible {{
      transform: translateY(-2px);
    }}
    .content {{
      display: grid;
      gap: 18px;
      padding-top: 28px;
      align-items: start;
    }}
    .hero-card,
    .upload-card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }}
    .hero-card::before,
    .upload-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, transparent, rgba(255, 139, 100, 0.06));
      pointer-events: none;
    }}
    .hero-card {{
      padding: 26px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) 240px;
      gap: 20px;
      align-items: center;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 13px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.06);
      color: var(--accent);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.72rem;
    }}
    .eyebrow::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-warm);
      box-shadow: 0 0 16px rgba(255, 142, 110, 0.45);
    }}
    h1 {{
      margin: 18px 0 14px;
      font-size: clamp(2.6rem, 5vw, 4.5rem);
      line-height: 0.94;
      letter-spacing: -0.05em;
      max-width: 9ch;
    }}
    h1 span {{
      display: block;
      color: transparent;
      background: linear-gradient(135deg, var(--accent-strong) 0%, var(--accent) 48%, var(--accent-warm) 100%);
      -webkit-background-clip: text;
      background-clip: text;
    }}
    .lead,
    .surface-title p,
    .file-state small,
    .inline-note,
    .alert {{
      color: var(--muted);
    }}
    .lead {{
      max-width: 40ch;
      font-size: 1.02rem;
      line-height: 1.7;
      margin: 0;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-visual {{
      position: relative;
      width: 250px;
      height: 200px;
      margin-left: auto;
    }}
    .visual-doc,
    .visual-arrow,
    .visual-lang {{
      position: absolute;
    }}
    .visual-doc {{
      width: 122px;
      height: 156px;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.04));
      box-shadow: 0 18px 30px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(14px);
    }}
    .visual-doc::before {{
      content: "";
      position: absolute;
      left: 14px;
      right: 14px;
      top: 18px;
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.6), rgba(255, 139, 100, 0.45));
    }}
    .visual-doc::after {{
      content: "";
      position: absolute;
      left: 14px;
      right: 20px;
      top: 42px;
      height: 72px;
      border-radius: 18px;
      background:
        linear-gradient(rgba(255, 255, 255, 0.14) 0 0) 0 0 / 100% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.1) 0 0) 0 18px / 86% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 36px / 92% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 54px / 70% 1px no-repeat;
    }}
    .doc-source {{
      left: 2px;
      top: 26px;
      transform: rotate(-6deg);
    }}
    .doc-target {{
      right: 0;
      top: 18px;
      transform: rotate(6deg);
      border-color: rgba(67, 222, 207, 0.26);
    }}
    .visual-arrow {{
      left: 99px;
      top: 84px;
      width: 52px;
      height: 20px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(90deg, rgba(255, 139, 100, 0.12), rgba(67, 222, 207, 0.12));
      display: grid;
      place-items: center;
      color: var(--accent);
      font-size: 1rem;
      font-weight: 700;
      backdrop-filter: blur(8px);
    }}
    .visual-lang {{
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.06);
      font-size: 0.7rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--text);
    }}
    .lang-source {{
      left: 0;
      top: 0;
    }}
    .lang-target {{
      right: 0;
      bottom: 0;
      color: var(--accent);
    }}
    .upload-card {{
      padding: 22px;
    }}
    .alert {{
      padding: 14px 16px;
      border-radius: var(--radius-md);
      border: 1px solid var(--danger-line);
      background: var(--danger-bg);
      line-height: 1.55;
      margin-bottom: 14px;
    }}
    .surface-title {{
      margin-bottom: 14px;
    }}
    .surface-title strong {{
      display: block;
      font-size: 1.05rem;
      margin-bottom: 4px;
    }}
    .surface-title p {{
      margin: 0;
    }}
    .upload-shell {{
      display: grid;
      gap: 14px;
    }}
    .upload-shell.is-dragover {{
      box-shadow: 0 0 0 1px rgba(69, 224, 207, 0.22) inset;
    }}
    .file-input {{
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }}
    .upload-surface {{
      display: grid;
      gap: 16px;
      min-height: 188px;
      padding: 22px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top left, rgba(67, 222, 207, 0.08), transparent 32%),
        rgba(255, 255, 255, 0.04);
      cursor: pointer;
    }}
    .upload-top {{
      display: grid;
      grid-template-columns: 70px 1fr;
      gap: 16px;
      align-items: center;
    }}
    .upload-badge {{
      width: 70px;
      height: 70px;
      border-radius: 22px;
      display: grid;
      place-items: center;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.05rem;
      color: #041017;
      background: linear-gradient(135deg, var(--accent), var(--accent-warm));
      box-shadow: 0 16px 34px rgba(67, 222, 207, 0.18);
    }}
    .upload-copy strong {{
      display: block;
      font-size: 1.16rem;
      margin-bottom: 4px;
    }}
    .upload-copy p {{
      margin: 0;
      line-height: 1.65;
      color: var(--muted);
    }}
    .upload-rail {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .upload-rail span {{
      color: var(--text);
    }}
    .upload-rail i {{
      width: 22px;
      height: 1px;
      background: linear-gradient(90deg, var(--accent), var(--accent-warm));
      display: block;
    }}
    .file-state {{
      padding-top: 2px;
    }}
    .file-state strong {{
      display: block;
      font-size: 0.96rem;
      margin-bottom: 4px;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .inline-note {{
      font-size: 0.88rem;
    }}
    .support-footer {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.8rem;
    }}
    .support-footer strong {{
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .support-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    @media (max-width: 1100px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
      .hero-visual {{
        margin-inline: auto;
      }}
    }}
    @media (max-width: 760px) {{
      .site {{
        padding: 14px 14px 28px;
      }}
      .topbar {{
        border-radius: 28px;
        justify-content: center;
        text-align: center;
        flex-wrap: wrap;
      }}
      .nav {{
        width: 100%;
      }}
      .content,
      .topbar {{
        width: min(100vw - 28px, 1080px);
      }}
      .hero-card,
      .upload-card {{
        padding: 22px;
      }}
      h1 {{
        max-width: none;
      }}
      .hero-visual {{
        width: 180px;
        height: 180px;
      }}
      .visual-core {{
        inset: 60px;
      }}
      .surface-title {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .upload-top {{
        grid-template-columns: 1fr;
      }}
      .action-row {{
        align-items: stretch;
      }}
    }}
  </style>
</head>
<body>
  <div class="site">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Divian-HUB főoldal">
        <span class="brand-mark"></span>
        <span class="brand-text">
          <strong>Divian-HUB</strong>
          <small>Számla magyarító</small>
        </span>
      </a>

      <nav class="nav">
        <a href="/">Főoldal</a>
        <a href="/#modules">Modulok</a>
      </nav>

      <a class="nav-cta" href="/#modules">Modulok</a>
    </header>

    <main class="content">
      <section class="hero-card">
        <div class="hero-grid">
          <div class="hero-copy">
            <div class="eyebrow">Számla magyarító</div>
            <h1>PDF számla <span>kész fordítás</span></h1>
            <p class="lead">
              Tölts fel egy PDF számlát, és a rendszer elkészíti a fordított, nyomtatható változatot.
            </p>
            <div class="hero-actions">
              <a class="button" href="#feltoltes">Feltöltés</a>
              <a class="ghost-link" href="/">Modulok</a>
            </div>
          </div>

          <div class="hero-visual" aria-hidden="true">
            <div class="visual-lang lang-source">Forrás</div>
            <div class="visual-doc doc-source"></div>
            <div class="visual-arrow">→</div>
            <div class="visual-doc doc-target"></div>
            <div class="visual-lang lang-target">Magyar</div>
          </div>
        </div>
      </section>

      <section class="upload-card" id="feltoltes">
        <div class="surface-title">
          <strong>Feltöltés</strong>
          <p>Fájl kiválasztása, majd indítás.</p>
        </div>

        {msg_html}

        <form method="post" action="{GENERATE_ROUTE}" enctype="multipart/form-data" target="_blank" id="invoice-form">
          <div class="upload-shell" id="upload-shell">
            <input
              class="file-input"
              id="invoice_file"
              type="file"
              name="invoice_file"
              accept="application/pdf"
              required
            />

            <label class="upload-surface" for="invoice_file">
              <div class="upload-top">
                <div class="upload-badge">PDF</div>
                <div class="upload-copy">
                  <strong>Számla kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                </div>
              </div>

              <div class="upload-rail" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>Magyar nézet</span>
              </div>

              <div class="file-state">
                <strong id="file-name">Még nincs kiválasztott fájl</strong>
                <small id="file-meta">Támogatott formátum: .pdf</small>
              </div>
            </label>

            <div class="action-row">
              <button class="primary-button" type="submit" id="submit-button">Fordítás indítása</button>
              <span class="inline-note">Az eredmény külön lapon jelenik meg.</span>
            </div>
          </div>
        </form>

        <div class="support-footer">
          <strong>Működik jelenleg:</strong>
          <span class="support-pill">Kronospan</span>
          <span class="support-pill">Kastamonu</span>
        </div>
      </section>
    </main>
  </div>

  <script>
    const fileInput = document.getElementById("invoice_file");
    const fileName = document.getElementById("file-name");
    const fileMeta = document.getElementById("file-meta");
    const uploadShell = document.getElementById("upload-shell");
    const form = document.getElementById("invoice-form");
    const submitButton = document.getElementById("submit-button");

    const updateFileState = () => {{
      const file = fileInput.files && fileInput.files[0];
      if (!file) {{
        fileName.textContent = "Még nincs kiválasztott fájl";
        fileMeta.textContent = "Támogatott formátum: .pdf";
        return;
      }}

      fileName.textContent = file.name;
      fileMeta.textContent = `${{(file.size / 1024 / 1024).toFixed(2)}} MB`;
    }};

    ["dragenter", "dragover"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.add("is-dragover");
      }});
    }});

    ["dragleave", "drop"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.remove("is-dragover");
      }});
    }});

    fileInput.addEventListener("change", updateFileState);

    form.addEventListener("submit", () => {{
      submitButton.textContent = "Feldolgozás indul...";
      submitButton.disabled = true;
      window.setTimeout(() => {{
        submitButton.textContent = "Fordítás indítása";
        submitButton.disabled = false;
      }}, 2000);
    }});
  </script>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")


def _render_nettfront_layout(
    *,
    heading: str,
    lead: str,
    intro_label: str,
    content_html: str,
    side_html: str,
    notice_html: str = "",
    extra_script: str = "",
    single_column: bool = False,
    module_root_id: str = "",
) -> bytes:
    workflow_class = "workflow-grid is-single-column" if single_column else "workflow-grid"
    side_column_html = ""
    if side_html.strip() and not single_column:
        side_column_html = f"""
          <aside class="stack-column reveal is-visible">
            {side_html}
          </aside>
        """
    hero_html = ""
    module_root_open = f'<div id="{html.escape(module_root_id)}" class="module-root-shell">' if module_root_id else ""
    module_root_close = "</div>" if module_root_id else ""
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | NettFront modul</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <link rel="stylesheet" href="/styles.css" />
  <style>
    .module-shell {{
      padding-top: 42px;
      padding-bottom: 64px;
    }}
    .module-root-shell {{
      display: block;
      transition: opacity 180ms ease, transform 180ms ease;
    }}
    .module-root-shell.is-loading {{
      opacity: 0.66;
      transform: translateY(2px);
      pointer-events: none;
    }}
    .module-hero {{
      max-width: 760px;
      margin-bottom: 24px;
    }}
    .workflow-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr);
      gap: 22px;
    }}
    .workflow-grid.is-single-column {{
      grid-template-columns: minmax(0, 1fr);
    }}
    .workflow-panel,
    .stack-card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }}
    .workflow-panel::before,
    .stack-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, transparent, rgba(255, 139, 100, 0.06));
      pointer-events: none;
    }}
    .workflow-panel {{
      padding: 24px;
    }}
    .stack-column {{
      display: grid;
      gap: 18px;
    }}
    .stack-card {{
      padding: 20px;
    }}
    .stack-card h3,
    .workflow-panel h2,
    .summary-card strong {{
      font-family: "Space Grotesk", sans-serif;
    }}
    .workflow-panel h2,
    .stack-card h3 {{
      margin: 0 0 12px;
      font-size: 1.3rem;
      line-height: 1.08;
    }}
    .muted-copy,
    .stack-card p,
    .stack-card li,
    .field-hint,
    .summary-card span,
    .download-card p,
    .notice-banner,
    .status-note {{
      color: var(--muted);
    }}
    .muted-copy,
    .stack-card p {{
      line-height: 1.65;
    }}
    .inline-note {{
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.55;
    }}
    .notice-banner {{
      width: var(--content-width);
      margin: 0 auto 18px;
      padding: 16px 18px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(255, 122, 122, 0.26);
      background: rgba(97, 34, 31, 0.42);
      line-height: 1.6;
    }}
    .notice-banner.success {{
      border-color: rgba(67, 222, 207, 0.22);
      background: rgba(16, 74, 63, 0.38);
    }}
    .upload-grid,
    .summary-grid,
    .download-grid,
    .route-grid {{
      display: grid;
      gap: 16px;
    }}
    .upload-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 20px;
    }}
    .upload-field {{
      display: grid;
      gap: 10px;
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
    }}
    .upload-field strong,
    .summary-card strong,
    .download-card strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 1rem;
    }}
    .upload-field input[type="file"] {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px dashed var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
    }}
    .field-hint {{
      font-size: 0.9rem;
      line-height: 1.55;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }}
    .summary-grid {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 18px;
    }}
    .summary-card,
    .download-card,
    .result-card {{
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
    }}
    .summary-card span {{
      display: block;
      margin-top: 8px;
      font-size: 0.9rem;
    }}
    .summary-card strong {{
      font-size: 1.9rem;
    }}
    .download-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }}
    .route-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 20px;
    }}
    .download-card {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .route-card {{
      display: grid;
      gap: 12px;
      padding: 22px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: inherit;
      text-decoration: none;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        box-shadow 180ms ease;
    }}
    .route-card:hover {{
      transform: translateY(-3px);
      border-color: rgba(67, 222, 207, 0.24);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.24);
    }}
    .route-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .download-card p {{
      margin: 0;
      line-height: 1.55;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(67, 222, 207, 0.08);
      color: var(--accent);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.7rem;
      font-weight: 700;
    }}
    .tag::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-warm);
      box-shadow: 0 0 16px rgba(167, 255, 112, 0.8);
    }}
    .status-list {{
      margin: 14px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 10px;
    }}
    .status-note {{
      margin-top: 10px;
      line-height: 1.6;
    }}
    .knowledge-shell {{
      display: grid;
      gap: 18px;
    }}
    .knowledge-hero {{
      position: relative;
      overflow: hidden;
      padding: 24px;
      border-radius: 30px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.18), transparent 30%),
        radial-gradient(circle at bottom left, rgba(167, 255, 112, 0.1), transparent 24%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 24px 48px rgba(0, 0, 0, 0.16);
    }}
    .knowledge-hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) 260px;
      gap: 24px;
      align-items: center;
    }}
    .knowledge-hero-copy h2 {{
      margin: 10px 0 8px;
      font-size: clamp(1.8rem, 2vw, 2.35rem);
      line-height: 1.08;
      letter-spacing: -0.04em;
    }}
    .knowledge-hero-copy p {{
      margin: 0;
      max-width: 560px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .knowledge-stat-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    .knowledge-mini-stat {{
      min-width: 120px;
      padding: 10px 14px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.04);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
    }}
    .knowledge-mini-stat strong {{
      display: block;
      margin-bottom: 3px;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.14rem;
    }}
    .knowledge-mini-stat span {{
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.4;
    }}
    .knowledge-visual {{
      position: relative;
      min-height: 220px;
      overflow: hidden;
      border-radius: 28px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background:
        radial-gradient(circle at 50% 48%, rgba(67, 222, 207, 0.18), transparent 28%),
        radial-gradient(circle at 50% 50%, rgba(167, 255, 112, 0.08), transparent 36%),
        linear-gradient(180deg, rgba(8, 16, 28, 0.96), rgba(5, 10, 18, 0.92));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 18px 44px rgba(0, 0, 0, 0.22);
    }}
    .knowledge-visual-gridline {{
      position: absolute;
      inset: 16px;
      border-radius: 26px;
      background:
        radial-gradient(circle at center, rgba(67, 222, 207, 0.12), transparent 32%),
        radial-gradient(circle at center, rgba(255, 255, 255, 0.06) 0 1px, transparent 1px);
      background-size: auto, 24px 24px;
      opacity: 0.42;
    }}
    .knowledge-visual-core {{
      position: absolute;
      top: 50%;
      left: 50%;
      width: 186px;
      transform: translate(-50%, -50%);
      padding: 22px 20px 18px;
      display: grid;
      gap: 10px;
      justify-items: center;
      text-align: center;
      border-radius: 30px;
      border: 1px solid rgba(67, 222, 207, 0.24);
      background:
        radial-gradient(circle at top left, rgba(255, 255, 255, 0.16), transparent 40%),
        linear-gradient(180deg, rgba(21, 52, 66, 0.96), rgba(7, 22, 34, 0.98));
      box-shadow:
        0 22px 42px rgba(0, 0, 0, 0.28),
        0 0 42px rgba(67, 222, 207, 0.14),
        inset 0 1px 0 rgba(255, 255, 255, 0.08);
      animation: knowledgeCorePulse 6.2s ease-in-out infinite;
      z-index: 2;
    }}
    .knowledge-visual-core::before {{
      content: "";
      position: absolute;
      inset: -12px;
      border-radius: 40px;
      border: 1px solid rgba(67, 222, 207, 0.12);
      opacity: 0.85;
    }}
    .knowledge-visual-core::after {{
      content: "";
      position: absolute;
      inset: auto 28px -20px;
      height: 30px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.18);
      filter: blur(20px);
      opacity: 0.8;
    }}
    .knowledge-visual-kicker {{
      position: relative;
      z-index: 1;
      color: rgba(228, 250, 255, 0.72);
      font-size: 0.74rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .knowledge-visual-core strong {{
      position: relative;
      z-index: 1;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.28rem;
      line-height: 1;
      letter-spacing: -0.04em;
    }}
    .knowledge-visual-scan {{
      position: relative;
      z-index: 1;
      width: 82px;
      height: 4px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.06);
    }}
    .knowledge-visual-scan::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent, rgba(167, 255, 112, 0.96), transparent);
      transform: translateX(-100%);
      animation: knowledgeScanLine 2.8s ease-in-out infinite;
    }}
    .knowledge-visual-caption {{
      position: relative;
      z-index: 1;
      color: var(--muted);
      line-height: 1.35;
      font-size: 0.74rem;
      max-width: 128px;
    }}
    @keyframes knowledgeCorePulse {{
      0%, 100% {{
        transform: translate(-50%, -50%) scale(0.985);
      }}
      50% {{
        transform: translate(-50%, -50%) scale(1.015);
      }}
    }}
    @keyframes knowledgeScanLine {{
      0% {{
        transform: translateX(-100%);
      }}
      55%,
      100% {{
        transform: translateX(100%);
      }}
    }}
    .knowledge-upload {{
      display: grid;
      gap: 16px;
      padding: 18px;
      border-radius: 28px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02)),
        rgba(7, 16, 27, 0.6);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }}
    .knowledge-upload-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .knowledge-upload-copy strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 1rem;
    }}
    .knowledge-upload-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .knowledge-upload {{
      position: relative;
    }}
    .knowledge-upload-badge {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 64px;
      padding: 9px 12px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: rgba(67, 222, 207, 0.1);
      color: var(--accent);
      font-size: 0.74rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .knowledge-dropzone {{
      position: relative;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: center;
      padding: 20px;
      border-radius: 24px;
      border: 1px dashed rgba(67, 222, 207, 0.18);
      background: rgba(7, 16, 27, 0.46);
      cursor: pointer;
      transition:
        border-color 180ms ease,
        background 180ms ease,
        transform 180ms ease;
    }}
    .knowledge-dropzone.is-dragover {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.62);
      transform: translateY(-2px);
    }}
    .knowledge-dropzone:hover {{
      border-color: rgba(67, 222, 207, 0.3);
      background: rgba(10, 22, 35, 0.56);
      transform: translateY(-2px);
    }}
    .knowledge-dropzone:focus-within {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.6);
    }}
    .knowledge-dropzone-copy strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .knowledge-dropzone-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .knowledge-dropzone-action {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .knowledge-dropzone-cta {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.14), rgba(9, 47, 61, 0.5));
      color: var(--text);
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }}
    .knowledge-dropzone-note {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .knowledge-dropzone input[type="file"] {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      opacity: 0;
      cursor: pointer;
    }}
    .knowledge-file-state {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .knowledge-file-state::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.7);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.5);
    }}
    .knowledge-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .knowledge-chip {{
      display: inline-flex;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .knowledge-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }}
    .knowledge-bottom {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 14px;
    }}
    .knowledge-list-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .knowledge-section-head {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 14px;
    }}
    .knowledge-section-head h3 {{
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.16rem;
    }}
    .knowledge-section-head p {{
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .knowledge-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .knowledge-list li {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
    }}
    .knowledge-list strong {{
      font-size: 0.96rem;
    }}
    .knowledge-list span {{
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
    }}
    .knowledge-list-side {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .knowledge-list-meta {{
      text-align: right;
      white-space: nowrap;
    }}
    .knowledge-list-badge {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.76rem;
      white-space: nowrap;
    }}
    .knowledge-list-badge.is-pending {{
      border-color: rgba(255, 184, 76, 0.18);
      background: rgba(255, 184, 76, 0.1);
    }}
    .knowledge-list-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .knowledge-list-actions form {{
      margin: 0;
    }}
    .knowledge-action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
      text-decoration: none;
      cursor: pointer;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .knowledge-action:hover {{
      border-color: rgba(67, 222, 207, 0.2);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .knowledge-action.is-danger {{
      border-color: rgba(255, 107, 107, 0.18);
      background: rgba(255, 107, 107, 0.08);
    }}
    .knowledge-empty {{
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px dashed rgba(255, 255, 255, 0.08);
      color: var(--muted);
      background: rgba(255, 255, 255, 0.02);
    }}
    .missing-list {{
      margin: 12px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
      max-height: 220px;
      overflow: auto;
    }}
    .stack-card ul {{
      margin: 12px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
    }}
    .launch-form {{
      margin-top: 18px;
    }}
    .launch-form .button-secondary {{
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      box-shadow: none;
    }}
    .procurement-shell {{
      display: grid;
      gap: 18px;
    }}
    .procurement-hero-card,
    .procurement-upload-card {{
      position: relative;
      overflow: hidden;
      border-radius: 28px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.028));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.03),
        0 18px 42px rgba(0, 0, 0, 0.18);
    }}
    .procurement-hero-card {{
      padding: 24px;
    }}
    .procurement-hero-card::before,
    .procurement-upload-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(120deg, rgba(67, 222, 207, 0.08), transparent 42%);
      pointer-events: none;
    }}
    .procurement-hero-grid {{
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 240px;
      gap: 24px;
      align-items: center;
    }}
    .procurement-copy {{
      display: grid;
      gap: 14px;
    }}
    .procurement-copy strong {{
      display: block;
      max-width: 15ch;
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(2rem, 4.5vw, 3.15rem);
      line-height: 0.98;
      letter-spacing: -0.04em;
    }}
    .procurement-copy p {{
      margin: 0;
      max-width: 34ch;
      color: var(--muted);
      line-height: 1.65;
    }}
    .procurement-flow {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      width: fit-content;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
    }}
    .procurement-flow i {{
      width: 22px;
      height: 1px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.2), rgba(167, 255, 112, 0.8));
      display: block;
    }}
    .procurement-visual {{
      position: relative;
      min-height: 220px;
      border-radius: 28px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background:
        radial-gradient(circle at 50% 18%, rgba(67, 222, 207, 0.18), transparent 34%),
        linear-gradient(180deg, rgba(7, 16, 27, 0.76), rgba(7, 16, 27, 0.42));
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }}
    .procurement-visual::before {{
      content: "";
      position: absolute;
      inset: 18px;
      border-radius: 22px;
      border: 1px solid rgba(67, 222, 207, 0.08);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent),
        repeating-linear-gradient(
          180deg,
          transparent 0,
          transparent 16px,
          rgba(255, 255, 255, 0.02) 16px,
          rgba(255, 255, 255, 0.02) 17px
        );
    }}
    .procurement-orbit {{
      position: absolute;
      inset: 36px;
      border-radius: 28px;
      border: 1px dashed rgba(67, 222, 207, 0.14);
    }}
    .procurement-doc {{
      position: absolute;
      width: 88px;
      height: 112px;
      padding: 14px 12px;
      border-radius: 22px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 18px 24px rgba(0, 0, 0, 0.2);
      backdrop-filter: blur(12px);
    }}
    .procurement-doc.is-source {{
      left: 34px;
      top: 54px;
    }}
    .procurement-doc.is-target {{
      right: 34px;
      top: 54px;
      border-color: rgba(167, 255, 112, 0.14);
    }}
    .procurement-doc-label {{
      display: block;
      margin-bottom: 12px;
      color: var(--text);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .procurement-doc-lines {{
      display: grid;
      gap: 8px;
    }}
    .procurement-doc-lines span {{
      display: block;
      height: 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
    }}
    .procurement-doc-lines span:nth-child(2) {{
      width: 78%;
    }}
    .procurement-doc-lines span:nth-child(3) {{
      width: 62%;
    }}
    .procurement-transfer {{
      position: absolute;
      left: 50%;
      top: 50%;
      width: 82px;
      height: 82px;
      transform: translate(-50%, -50%);
      border-radius: 50%;
      border: 1px solid rgba(67, 222, 207, 0.18);
      background: radial-gradient(circle, rgba(67, 222, 207, 0.18), rgba(8, 22, 36, 0.12));
      box-shadow: 0 0 34px rgba(67, 222, 207, 0.18);
    }}
    .procurement-transfer::before {{
      content: "";
      position: absolute;
      left: 24px;
      right: 24px;
      top: 50%;
      height: 2px;
      transform: translateY(-50%);
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.16), rgba(167, 255, 112, 0.9));
    }}
    .procurement-transfer::after {{
      content: "";
      position: absolute;
      right: 22px;
      top: 50%;
      width: 10px;
      height: 10px;
      transform: translateY(-50%) rotate(45deg);
      border-top: 2px solid rgba(167, 255, 112, 0.9);
      border-right: 2px solid rgba(167, 255, 112, 0.9);
    }}
    .procurement-upload-card {{
      padding: 22px;
    }}
    .procurement-surface-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .procurement-surface-title strong {{
      font-size: 1rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .procurement-surface-title p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .procurement-upload-shell {{
      display: grid;
      gap: 16px;
    }}
    .procurement-upload-shell.is-dragover .procurement-upload-surface {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.64);
      transform: translateY(-2px);
    }}
    .procurement-file-input {{
      position: absolute;
      inset: 0;
      opacity: 0;
      pointer-events: none;
    }}
    .procurement-upload-surface {{
      position: relative;
      overflow: hidden;
      display: grid;
      gap: 14px;
      padding: 24px;
      border-radius: 26px;
      border: 1px dashed rgba(67, 222, 207, 0.18);
      background: rgba(7, 16, 27, 0.48);
      cursor: pointer;
      transition:
        border-color 180ms ease,
        background 180ms ease,
        transform 180ms ease;
    }}
    .procurement-upload-surface:hover {{
      border-color: rgba(67, 222, 207, 0.28);
      background: rgba(10, 22, 35, 0.56);
      transform: translateY(-2px);
    }}
    .procurement-upload-top {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 14px;
      align-items: center;
    }}
    .procurement-upload-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 54px;
      min-height: 54px;
      padding: 0 16px;
      border-radius: 18px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.14), rgba(9, 47, 61, 0.44));
      color: var(--text);
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .procurement-upload-copy strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .procurement-upload-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-upload-rail {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
    }}
    .procurement-upload-rail i {{
      width: 20px;
      height: 1px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.18), rgba(167, 255, 112, 0.8));
      display: block;
    }}
    .procurement-file-state {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .procurement-file-state::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.72);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.5);
    }}
    .procurement-action-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }}
    .procurement-action-row .button {{
      min-width: 220px;
    }}
    .procurement-action-row .inline-note {{
      margin-left: auto;
      text-align: right;
    }}
    .procurement-output-footer {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      padding-top: 14px;
      margin-top: 4px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.8rem;
    }}
    .procurement-output-footer strong {{
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .procurement-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    .procurement-result-shell {{
      display: grid;
      gap: 18px;
    }}
    .procurement-result-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .procurement-result-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .procurement-result-card strong {{
      display: block;
      margin-bottom: 8px;
      font-size: 1.04rem;
    }}
    .procurement-result-copy {{
      margin: 12px 0 0;
      color: var(--muted);
      line-height: 1.6;
      font-size: 0.9rem;
    }}
    .procurement-warning-modal {{
      position: fixed;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(3, 8, 16, 0.74);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transition: opacity 180ms ease, visibility 180ms ease;
      z-index: 40;
    }}
    .procurement-warning-modal.is-visible {{
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
    }}
    .procurement-warning-card {{
      width: min(100%, 520px);
      padding: 24px;
      border-radius: 28px;
      border: 1px solid rgba(255, 184, 76, 0.18);
      background:
        radial-gradient(circle at top right, rgba(255, 184, 76, 0.14), transparent 34%),
        rgba(8, 16, 28, 0.96);
      box-shadow: 0 28px 80px rgba(0, 0, 0, 0.36);
    }}
    .procurement-warning-card strong {{
      display: block;
      margin-bottom: 10px;
      font-size: 1.14rem;
    }}
    .procurement-warning-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }}
    .procurement-warning-actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: 18px;
    }}
    .procurement-result-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 10px;
    }}
    .procurement-result-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.82rem;
    }}
    .procurement-result-pill.is-alert {{
      border-color: rgba(255, 139, 100, 0.18);
      background: rgba(255, 139, 100, 0.08);
    }}
    .procurement-code-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .procurement-code-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.07);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    .procurement-preview-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.08), transparent 34%),
        rgba(7, 16, 27, 0.44);
    }}
    .procurement-preview-head {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .procurement-preview-head strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .procurement-preview-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.55;
    }}
    .procurement-preview-table-wrap {{
      overflow: auto;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .procurement-preview-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 320px;
    }}
    .procurement-preview-table th,
    .procurement-preview-table td {{
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.9rem;
    }}
    .procurement-preview-table th {{
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.04em;
    }}
    .procurement-preview-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .procurement-preview-empty {{
      padding: 16px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .procurement-launch-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .procurement-launch-row form {{
      margin: 0;
    }}
    .procurement-launch-row .button {{
      min-width: 240px;
    }}
    .procurement-remap-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 139, 100, 0.16);
      background:
        radial-gradient(circle at top left, rgba(255, 139, 100, 0.08), transparent 32%),
        rgba(255, 255, 255, 0.035);
    }}
    .procurement-remap-card strong {{
      display: block;
      margin-bottom: 8px;
      font-size: 1.02rem;
    }}
    .procurement-remap-card p {{
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-remap-form {{
      display: grid;
      gap: 12px;
    }}
    .procurement-remap-input {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px dashed rgba(255, 255, 255, 0.14);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
    }}
    .procurement-remap-meta {{
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.55;
    }}
    .procurement-side-card {{
      display: grid;
      gap: 12px;
    }}
    .procurement-side-card h3 {{
      margin: 0;
      font-size: 1.16rem;
    }}
    .procurement-side-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-side-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .procurement-side-list li {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text);
    }}
    .procurement-side-list li::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: linear-gradient(180deg, var(--accent), var(--accent-warm));
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.36);
      flex: 0 0 auto;
    }}
    .vacation-shell {{
      display: grid;
      gap: 16px;
    }}
    .vacation-hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 248px;
      gap: 12px;
      align-items: stretch;
    }}
    .vacation-hero-card {{
      display: grid;
      gap: 12px;
      padding: 18px;
    }}
    .vacation-hero-copy {{
      display: grid;
      gap: 6px;
    }}
    .vacation-hero-copy h2 {{
      margin: 0;
      font-size: clamp(1.56rem, 1.8vw, 1.92rem);
      line-height: 1.04;
    }}
    .vacation-hero-copy p {{
      margin: 0;
      max-width: 56ch;
      font-size: 0.92rem;
      line-height: 1.45;
    }}
    .vacation-stat-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .vacation-stat {{
      padding: 10px 12px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .vacation-stat strong {{
      display: block;
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.14rem;
      line-height: 1;
    }}
    .vacation-stat span {{
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.35;
    }}
    .vacation-visual-card {{
      display: grid;
      align-content: stretch;
      padding: 14px;
    }}
    .vacation-visual {{
      position: relative;
      min-height: 100%;
      display: grid;
      gap: 10px;
      align-content: center;
    }}
    .vacation-visual::before {{
      content: "";
      position: absolute;
      inset: 18px 26px auto auto;
      width: 120px;
      height: 120px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(67, 222, 207, 0.24), transparent 72%);
      filter: blur(6px);
      pointer-events: none;
    }}
    .vacation-visual::after {{
      content: "";
      position: absolute;
      inset: auto auto 8px 18px;
      width: 110px;
      height: 110px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 184, 76, 0.12), transparent 72%);
      filter: blur(10px);
      pointer-events: none;
    }}
    .vacation-visual-board {{
      position: relative;
      z-index: 1;
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background:
        linear-gradient(180deg, rgba(10, 22, 36, 0.92), rgba(7, 15, 27, 0.86)),
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.12), transparent 38%);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }}
    .vacation-visual-topbar {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .vacation-visual-topbar span {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.18);
    }}
    .vacation-visual-topbar span:first-child {{
      background: rgba(255, 184, 76, 0.84);
    }}
    .vacation-visual-topbar span:nth-child(2) {{
      background: rgba(67, 222, 207, 0.84);
    }}
    .vacation-visual-week {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-visual-week span {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
    }}
    .vacation-visual-days {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 5px;
    }}
    .vacation-visual-day {{
      height: 18px;
      border-radius: 9px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.04);
    }}
    .vacation-visual-day.is-accent {{
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.34), rgba(67, 222, 207, 0.14));
      border-color: rgba(67, 222, 207, 0.28);
      box-shadow: 0 0 20px rgba(67, 222, 207, 0.16);
    }}
    .vacation-visual-day.is-warm {{
      background: linear-gradient(180deg, rgba(255, 184, 76, 0.3), rgba(255, 184, 76, 0.12));
      border-color: rgba(255, 184, 76, 0.28);
    }}
    .vacation-visual-roster {{
      display: grid;
      gap: 6px;
      padding-top: 1px;
    }}
    .vacation-visual-row {{
      display: grid;
      grid-template-columns: 9px minmax(0, 1fr) 42px;
      align-items: center;
      gap: 8px;
    }}
    .vacation-visual-avatar {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.92), rgba(255, 184, 76, 0.9));
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.3);
    }}
    .vacation-visual-bar {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      overflow: hidden;
      position: relative;
    }}
    .vacation-visual-bar::after {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 58%;
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.84), rgba(67, 222, 207, 0.36));
    }}
    .vacation-visual-bar.is-mid::after {{
      width: 74%;
    }}
    .vacation-visual-bar.is-warm::after {{
      width: 92%;
      background: linear-gradient(90deg, rgba(255, 184, 76, 0.92), rgba(255, 184, 76, 0.4));
    }}
    .vacation-visual-count {{
      justify-self: end;
      padding: 3px 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.62rem;
    }}
    .vacation-visual-chip-row {{
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-visual-chip {{
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.64rem;
      letter-spacing: 0.02em;
    }}
    .vacation-visual-chip::before {{
      content: "";
      width: 8px;
      height: 8px;
      margin-right: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.24);
    }}
    .vacation-visual-chip.is-accent::before {{
      background: var(--accent);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.34);
    }}
    .vacation-visual-chip.is-warm::before {{
      background: var(--accent-warm);
      box-shadow: 0 0 12px rgba(255, 184, 76, 0.3);
    }}
    .vacation-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      padding: 11px 14px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-month-nav {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .vacation-month-title {{
      min-width: 158px;
      font-family: "Space Grotesk", sans-serif;
      font-size: 0.92rem;
    }}
    .vacation-month-form {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .vacation-month-form input[type="month"] {{
      min-width: 170px;
      padding: 8px 11px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
    }}
    .vacation-toolbar .knowledge-action,
    .vacation-item-actions .knowledge-action,
    .vacation-form-actions .button {{
      min-width: 0;
      padding: 8px 12px;
      border-radius: 12px;
      font-size: 0.78rem;
      line-height: 1.1;
    }}
    .vacation-calendar-stage {{
      position: relative;
      display: grid;
      gap: 0;
      scroll-margin-top: 88px;
    }}
    .vacation-calendar-card {{
      display: grid;
      gap: 12px;
      padding: 16px;
    }}
    .vacation-calendar-wrap {{
      overflow: visible;
      min-width: 0;
      padding-bottom: 2px;
    }}
    .vacation-calendar-grid {{
      min-width: 0;
      width: 100%;
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-weekday,
    .vacation-day {{
      border-radius: 20px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-weekday {{
      padding: 7px 8px;
      text-align: center;
      font-size: 0.7rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .vacation-day {{
      min-height: 88px;
      padding: 7px;
      display: grid;
      align-content: start;
      gap: 5px;
      position: relative;
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
    }}
    .vacation-day[data-vacation-day] {{
      cursor: pointer;
    }}
    .vacation-day[data-vacation-day]:hover {{
      transform: translateY(-1px);
      border-color: rgba(67, 222, 207, 0.18);
      box-shadow: 0 18px 34px rgba(2, 10, 18, 0.24);
    }}
    .vacation-day[data-vacation-day]:focus-visible {{
      outline: none;
      box-shadow: 0 0 0 1px rgba(67, 222, 207, 0.36), 0 16px 28px rgba(2, 10, 18, 0.2);
    }}
    .vacation-day.is-other-month {{
      opacity: 0.42;
    }}
    .vacation-day.is-busy {{
      border-color: rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.06), rgba(255, 255, 255, 0.03));
    }}
    .vacation-day.is-limited {{
      border-color: rgba(255, 184, 76, 0.22);
      background: linear-gradient(180deg, rgba(255, 184, 76, 0.08), rgba(255, 255, 255, 0.03));
    }}
    .vacation-day.is-today {{
      box-shadow: inset 0 0 0 1px rgba(67, 222, 207, 0.28);
    }}
    .vacation-day-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }}
    .vacation-day-number {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 26px;
      min-height: 26px;
      padding: 0 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.04);
      font-size: 0.76rem;
      font-weight: 700;
    }}
    .vacation-day.is-today .vacation-day-number {{
      background: rgba(67, 222, 207, 0.14);
      color: var(--text);
    }}
    .vacation-day-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 0.62rem;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.04);
    }}
    .vacation-day-list {{
      display: grid;
      gap: 4px;
    }}
    .vacation-entry {{
      display: inline-flex;
      align-items: center;
      justify-content: flex-start;
      width: 100%;
      max-width: 100%;
      padding: 4px 7px;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      font-size: 0.68rem;
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .vacation-entry:hover {{
      border-color: rgba(67, 222, 207, 0.18);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .vacation-entry:focus-visible {{
      outline: none;
      border-color: rgba(67, 222, 207, 0.28);
      background: rgba(67, 222, 207, 0.1);
    }}
    .vacation-entry-more {{
      color: var(--muted);
      font-size: 0.66rem;
    }}
    .vacation-load-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .vacation-load {{
      display: inline-flex;
      align-items: center;
      padding: 3px 6px;
      border-radius: 999px;
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.6rem;
    }}
    .vacation-load.is-limit {{
      background: rgba(255, 184, 76, 0.12);
    }}
    .vacation-insight-grid,
    .vacation-section-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      align-items: start;
    }}
    .vacation-list-card.is-wide {{
      grid-column: 1 / -1;
    }}
    .vacation-list-card {{
      display: grid;
      gap: 8px;
      padding: 16px;
    }}
    .vacation-list-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .vacation-list-head h3 {{
      margin: 0;
      font-size: 0.94rem;
    }}
    .vacation-list-head p {{
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 0.74rem;
      line-height: 1.45;
    }}
    .vacation-list {{
      display: grid;
      gap: 7px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .vacation-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-item-main {{
      display: grid;
      gap: 5px;
    }}
    .vacation-item-main strong {{
      font-size: 0.88rem;
    }}
    .vacation-item-main span {{
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.45;
    }}
    .vacation-item-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-item-actions form {{
      margin: 0;
    }}
    .vacation-mini-badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .vacation-mini-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.64rem;
    }}
    .vacation-form-stack {{
      display: grid;
      gap: 12px;
    }}
    .vacation-form-card {{
      display: grid;
      gap: 10px;
      padding: 18px;
    }}
    .vacation-form-card h3 {{
      margin: 0;
      font-size: 0.94rem;
    }}
    .vacation-form-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .vacation-form-grid {{
      display: grid;
      gap: 7px;
    }}
    .vacation-form-grid.is-split {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .vacation-field.is-full,
    .vacation-form-actions.is-full {{
      grid-column: 1 / -1;
    }}
    .vacation-field {{
      display: grid;
      gap: 6px;
    }}
    .vacation-field label,
    .vacation-field strong {{
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .vacation-field input[type="text"],
    .vacation-field input[type="number"],
    .vacation-field input[type="date"],
    .vacation-field select,
    .vacation-field textarea {{
      width: 100%;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
      font: inherit;
    }}
    .vacation-field textarea {{
      min-height: 56px;
      resize: vertical;
    }}
    .vacation-field-hint {{
      color: var(--muted);
      font-size: 0.7rem;
      line-height: 1.45;
    }}
    .vacation-checkbox-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-check {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
      cursor: pointer;
    }}
    .vacation-check span {{
      font-size: 0.74rem;
      line-height: 1.35;
    }}
    .vacation-check input {{
      accent-color: var(--accent);
    }}
    .vacation-form-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-card-divider {{
      height: 1px;
      background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02));
      margin: 2px 0;
    }}
    .vacation-modal-backdrop {{
      position: absolute;
      inset: 8px;
      z-index: 12;
      display: none;
      align-items: flex-start;
      justify-content: center;
      padding: 14px;
      border-radius: 26px;
      background: rgba(3, 10, 18, 0.7);
      backdrop-filter: blur(10px);
      overflow-y: auto;
    }}
    .vacation-modal-backdrop.is-open {{
      display: flex;
    }}
    .vacation-modal-card {{
      position: relative;
      width: min(520px, calc(100% - 12px));
      max-height: min(720px, calc(100vh - 180px));
      overflow: auto;
      display: grid;
      align-content: start;
      gap: 10px;
      padding: 16px;
      border-radius: 20px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background:
        linear-gradient(180deg, rgba(11, 21, 35, 0.96), rgba(7, 15, 27, 0.94)),
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.1), transparent 36%);
      box-shadow: 0 32px 80px rgba(0, 0, 0, 0.4);
    }}
    .vacation-modal-close {{
      position: absolute;
      top: 12px;
      right: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
    }}
    .vacation-modal-head {{
      display: grid;
      gap: 6px;
      padding-right: 40px;
    }}
    .vacation-modal-head h3 {{
      margin: 0;
      font-size: 1.04rem;
    }}
    .vacation-modal-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .vacation-modal-day-panel {{
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-modal-day-summary {{
      display: grid;
      gap: 3px;
    }}
    .vacation-modal-day-summary strong {{
      font-size: 0.92rem;
    }}
    .vacation-modal-day-summary span {{
      color: var(--muted);
      font-size: 0.72rem;
    }}
    .vacation-modal-day-list {{
      display: grid;
      gap: 7px;
    }}
    .vacation-modal-day-entry {{
      display: grid;
      gap: 3px;
      width: 100%;
      padding: 8px 10px;
      border-radius: 14px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      text-align: left;
      cursor: pointer;
      font: inherit;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .vacation-modal-day-entry:hover {{
      border-color: rgba(67, 222, 207, 0.18);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .vacation-modal-day-entry.is-active {{
      border-color: rgba(67, 222, 207, 0.24);
      background: rgba(67, 222, 207, 0.1);
      box-shadow: inset 0 0 0 1px rgba(67, 222, 207, 0.18);
    }}
    .vacation-modal-day-entry strong {{
      font-size: 0.82rem;
    }}
    .vacation-modal-day-entry span,
    .vacation-modal-day-entry small {{
      color: var(--muted);
      font-size: 0.72rem;
      line-height: 1.4;
    }}
    .vacation-modal-form {{
      margin: 0;
    }}
    .vacation-modal-actions {{
      justify-content: space-between;
    }}
    .vacation-modal-delete {{
      display: flex;
      justify-content: flex-end;
      margin: 0;
    }}
    .vacation-inline-link {{
      color: var(--muted);
      font-size: 0.74rem;
      text-decoration: none;
    }}
    .vacation-inline-link:hover {{
      color: var(--text);
    }}
    .vacation-empty {{
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px dashed rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.02);
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    @media (max-width: 1020px) {{
      .workflow-grid,
      .upload-grid,
      .summary-grid,
      .download-grid,
      .route-grid,
      .knowledge-hero-grid,
      .procurement-result-grid {{
        grid-template-columns: 1fr;
      }}
      .procurement-hero-grid {{
        grid-template-columns: 1fr;
      }}
      .knowledge-upload-head,
      .knowledge-section-head {{
        grid-template-columns: 1fr;
        display: grid;
      }}
      .vacation-hero-grid,
      .vacation-checkbox-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-toolbar,
      .vacation-insight-grid,
      .vacation-section-grid {{
        align-items: flex-start;
      }}
      .vacation-form-grid.is-split {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .vacation-calendar-stage {{
        scroll-margin-top: 74px;
      }}
      .procurement-hero-card,
      .procurement-upload-card {{
        padding: 20px;
      }}
      .procurement-visual {{
        min-height: 200px;
      }}
      .procurement-doc {{
        width: 78px;
        height: 102px;
      }}
      .procurement-doc.is-source {{
        left: 24px;
      }}
      .procurement-doc.is-target {{
        right: 24px;
      }}
      .procurement-transfer {{
        width: 70px;
        height: 70px;
      }}
      .procurement-upload-surface {{
        padding: 20px;
      }}
      .procurement-action-row {{
        align-items: stretch;
      }}
      .procurement-action-row .button {{
        width: 100%;
        min-width: 0;
      }}
      .procurement-action-row .inline-note {{
        margin-left: 0;
        text-align: left;
      }}
      .procurement-launch-row .button {{
        width: 100%;
        min-width: 0;
      }}
      .procurement-preview-head {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .procurement-upload-top {{
        grid-template-columns: 1fr;
        align-items: flex-start;
      }}
      .procurement-surface-title {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .knowledge-hero,
      .knowledge-upload,
      .knowledge-list-card {{
        padding: 20px;
      }}
      .knowledge-visual {{
        min-height: 216px;
      }}
      .knowledge-visual-core {{
        width: 170px;
        padding: 20px 16px 16px;
      }}
      .knowledge-visual-caption {{
        max-width: 118px;
      }}
      .knowledge-dropzone {{
        grid-template-columns: 1fr;
        justify-items: flex-start;
      }}
      .knowledge-dropzone-action,
      .knowledge-footer,
      .knowledge-list li,
      .knowledge-list-side {{
        justify-content: flex-start;
      }}
      .knowledge-list li {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .knowledge-list-meta {{
        text-align: left;
        white-space: normal;
      }}
      .vacation-calendar-card,
      .vacation-hero-card,
      .vacation-visual-card,
      .vacation-list-card,
      .vacation-form-card {{
        padding: 14px;
      }}
      .vacation-toolbar {{
        gap: 10px;
        padding: 10px 12px;
      }}
      .vacation-visual {{
        min-height: 160px;
      }}
      .vacation-stat-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .vacation-toolbar,
      .vacation-month-nav,
      .vacation-month-form,
      .vacation-form-actions,
      .vacation-modal-actions,
      .vacation-item,
      .vacation-item-actions {{
        align-items: flex-start;
      }}
      .vacation-month-nav,
      .vacation-month-form {{
        width: 100%;
        justify-content: space-between;
      }}
      .vacation-month-title {{
        min-width: 0;
        flex: 1 1 auto;
        text-align: center;
        font-size: 0.84rem;
      }}
      .vacation-month-form input[type="month"] {{
        min-width: 0;
        width: 100%;
      }}
      .vacation-month-form .knowledge-action {{
        width: 100%;
      }}
      .vacation-weekday {{
        padding: 5px 2px;
        font-size: 0.55rem;
        letter-spacing: 0.04em;
      }}
      .vacation-day {{
        min-height: 64px;
        padding: 4px;
        gap: 3px;
        border-radius: 14px;
      }}
      .vacation-day-number {{
        min-width: 22px;
        min-height: 22px;
        padding: 0 5px;
        font-size: 0.68rem;
      }}
      .vacation-day-badge,
      .vacation-load-row {{
        display: none;
      }}
      .vacation-day-list {{
        gap: 3px;
      }}
      .vacation-entry {{
        padding: 2px 4px;
        border-radius: 8px;
        font-size: 0.58rem;
      }}
      .vacation-entry-more {{
        font-size: 0.58rem;
      }}
      .vacation-insight-grid,
      .vacation-section-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-checkbox-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-modal-backdrop {{
        inset: 6px;
        padding: 8px;
        border-radius: 18px;
      }}
      .vacation-modal-card {{
        width: 100%;
        max-height: calc(100dvh - 28px);
        padding: 12px;
        border-radius: 18px;
      }}
      .vacation-modal-head {{
        gap: 4px;
        padding-right: 28px;
      }}
      .vacation-modal-head h3 {{
        font-size: 0.96rem;
      }}
      .vacation-modal-head p,
      .vacation-modal-day-summary span,
      .vacation-modal-day-entry span,
      .vacation-modal-day-entry small {{
        font-size: 0.7rem;
      }}
      .vacation-modal-day-panel {{
        padding: 10px;
        border-radius: 14px;
      }}
      .vacation-modal-day-entry {{
        padding: 7px 8px;
        border-radius: 12px;
      }}
      .vacation-modal-actions .button,
      .vacation-modal-actions .knowledge-action,
      .vacation-modal-delete .knowledge-action {{
        width: 100%;
        justify-content: center;
      }}
      .vacation-modal-close {{
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
      }}
    }}
  </style>
</head>
<body>
  <div class="site-shell">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>
    <div class="grid-overlay"></div>

    <header class="topbar">
      <a class="brand" href="/" aria-label="Divian-HUB főoldal">
        <span class="brand-mark"></span>
        <span class="brand-text">
          <strong>Divian-HUB</strong>
          <small>Céges modulplatform</small>
        </span>
      </a>

      <nav class="nav">
        <a href="/">Főoldal</a>
        <a href="/#modules">Modulok</a>
      </nav>

      <a class="nav-cta" href="/#modules">Modulok</a>
    </header>

    {module_root_open}
      {notice_html}

      <main class="section module-shell">
        {hero_html}

        <div class="{workflow_class}">
          <section class="workflow-panel reveal is-visible">
            {content_html}
          </section>

          {side_column_html}
        </div>
      </main>
    {module_root_close}
  </div>
  {COMMON_SCRIPT_TAG}
  {extra_script}
</body>
</html>"""
    return page.encode("utf-8")


def render_nettfront_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">PDF -> fordítás -> procurement</div>
      <h2>NettFront számla beolvasó és beszerzési előkészítés</h2>
      <p class="muted-copy">
        Töltsd fel a NettFront számlát PDF-ben. Opcionálisan megadhatsz egy aktuális rendelési fájlt is,
        ekkor a rendszer összehasonlító Excel riportot is készít. A feldolgozás után letölthető lesz az
        invoice CSV, a beszerzési CSV és az összesített ZIP.
      </p>

      <form id="nettfront-upload-form" class="upload-grid" method="post" action="{NETTFRONT_PROCESS_ROUTE}" enctype="multipart/form-data">
        <label class="upload-field">
          <strong>Számla PDF</strong>
          <span class="field-hint">Kötelező bemenet. Ebből készül a fordított cikktörzs és a beszerzési CSV.</span>
          <input id="nettfront-invoice" type="file" name="invoice_pdf" accept=".pdf,application/pdf" required />
          <span class="field-hint" id="nettfront-invoice-state">Támogatott formátum: PDF</span>
        </label>

        <label class="upload-field">
          <strong>Aktuális rendelés</strong>
          <span class="field-hint">Nem kötelező. XLSX, XLSM vagy CSV esetén összehasonlító report is készül.</span>
          <input id="nettfront-order" type="file" name="order_file" accept=".xlsx,.xlsm,.csv" />
          <span class="field-hint" id="nettfront-order-state">Opcionális feltöltés</span>
        </label>
      </form>

      <div class="action-row">
        <button class="button button-primary" type="submit" form="nettfront-upload-form">Procurement csomag készítése</button>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Mit gyárt a modul?</h3>
        <ul>
          <li>Fordított számla sorok `invoice-output.csv` formában.</li>
          <li>Kész Beszerzés lista a következő lépéshez.</li>
          <li>Opcionálisan összehasonlító `compare-output.xlsx` riport.</li>
          <li>Egyben letölthető ZIP csomag.</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Launch workflow</h3>
        <p>
          A feldolgozás után egy külön gombbal elindítható az import-segéd. A beszerzési
          ablakban a `Shift + Space` billentyűkombináció indítja el a tényleges importot.
        </p>
      </article>

      <article class="stack-card">
        <h3>Megjegyzés</h3>
        <p>
          A module reuse-olja az eredeti repo fordítási tábláját és az alkatrész-mapet, így a procurement
          kimenet ugyanazon szabályok szerint készül, mint a meglévő projektben.
        </p>
      </article>
    """

    extra_script = """
<script>
  const bindFileState = (inputId, stateId, emptyText) => {
    const input = document.getElementById(inputId);
    const state = document.getElementById(stateId);
    if (!input || !state) return;

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyText;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    });
  };

  bindFileState("nettfront-invoice", "nettfront-invoice-state", "Támogatott formátum: PDF");
  bindFileState("nettfront-order", "nettfront-order-state", "Opcionális feltöltés");
</script>"""

    return _render_nettfront_layout(
        heading="NettFront számlaolvasó egy egységes platform alatt",
        lead="PDF-feldolgozás, fordítás, procurement CSV és opcionális összehasonlító Excel ugyanabban a Divian-HUB élményben.",
        intro_label="Második éles modul",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
        extra_script=extra_script,
    )


def render_nettfront_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    compare_button = ""
    if metadata.get("has_compare"):
        compare_button = f"""
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/compare-xlsx">
            Compare Excel letöltése
          </a>
        """

    missing_html = "<p class='status-note'>Minden cikkkódhoz találtunk procurement mappinget.</p>"
    missing_codes = metadata.get("missing_codes") or []
    if missing_codes:
        missing_items = "".join(f"<li>{html.escape(code)}</li>" for code in missing_codes)
        missing_html = f"<ul class='missing-list'>{missing_items}</ul>"

    order_note = "Nem töltöttél fel rendelési fájlt, ezért most csak az invoice/procurement kimenetek készültek el."
    if metadata.get("has_compare"):
        order_note = "Az aktuális rendelés összehasonlító riportja is elkészült a csomagban."

    content_html = f"""
      <div class="tag">Feldolgozás kész</div>
      <h2>NettFront procurement csomag elkészült</h2>
      <p class="muted-copy">{html.escape(order_note)}</p>

      <div class="summary-grid">
        <article class="summary-card">
          <strong>{metadata.get("invoice_row_count", 0)}</strong>
          <span>felismert számlasor</span>
        </article>
        <article class="summary-card">
          <strong>{metadata.get("order_row_count", 0)}</strong>
          <span>beolvasott rendelési sor</span>
        </article>
        <article class="summary-card">
          <strong>{len(missing_codes)}</strong>
          <span>hiányzó procurement mapping</span>
        </article>
      </div>

      <div class="download-grid">
        <article class="download-card">
          <strong>Invoice CSV</strong>
          <p>Fordított és kódolt számlasorok a rendszerből.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/invoice-csv">invoice-output.csv</a>
        </article>

        <article class="download-card">
          <strong>Beszerzési CSV</strong>
          <p>Az a kimenet, amivel az importfolyamat továbbvihető.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/procurement-csv">rendeles_sima.csv</a>
        </article>

        <article class="download-card">
          <strong>Teljes csomag</strong>
          <p>Minden generált fájl egyetlen ZIP-ben.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/bundle-zip">nettfront-output.zip</a>
        </article>

        <article class="download-card">
          <strong>Összehasonlító riport</strong>
          <p>Csak akkor érhető el, ha rendelési fájlt is feltöltöttél.</p>
          {compare_button or "<span class='status-note'>Ebben a futásban nem készült összehasonlító Excel.</span>"}
        </article>
      </div>

      <form class="launch-form" method="post" action="{NETTFRONT_LAUNCH_PREFIX}/{job_id}">
        <div class="action-row">
          <button class="button button-primary" type="submit">Beszerzési folyamat indítása</button>
          <a class="button button-secondary" href="{NETTFRONT_ROUTE}">Új feldolgozás</a>
        </div>
      </form>
    """

    side_html = f"""
      <article class="stack-card">
        <h3>Állapot</h3>
        <ul class="status-list">
          <li>Invoice sorok: {metadata.get("invoice_row_count", 0)}</li>
          <li>Rendelési sorok: {metadata.get("order_row_count", 0)}</li>
          <li>Összehasonlító riport: {"igen" if metadata.get("has_compare") else "nem"}</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Hiányzó kódok</h3>
        {missing_html}
      </article>

      <article class="stack-card">
        <h3>Launch információ</h3>
        <p>
          A launch gomb egy import-segédet indít el. Nyisd meg a beszerzési ablakot,
          majd a `Shift + Space` billentyűkombinációval indítsd az importot.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="A NettFront feldolgozás elkészült",
        lead="Innen indítható az import-segéd, az import pedig Shift + Space-re indul.",
        intro_label="Procurement output ready",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _render_file_bind_script(bindings: list[tuple[str, str, str]]) -> str:
    lines = [
        "<script>",
        "  const bindFileState = (inputId, stateId, emptyText) => {",
        "    const input = document.getElementById(inputId);",
        "    const state = document.getElementById(stateId);",
        "    if (!input || !state) return;",
        "",
        "    input.addEventListener(\"change\", () => {",
        "      const file = input.files && input.files[0];",
        "      if (!file) {",
        "        state.textContent = emptyText;",
        "        return;",
        "      }",
        "      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;",
        "    });",
        "  };",
        "",
    ]
    for input_id, state_id, empty_text in bindings:
        lines.append(f'  bindFileState("{input_id}", "{state_id}", "{empty_text}");')
    lines.extend(["</script>"])
    return "\n".join(lines)


def render_nettfront_hub(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">NettFront workflow split</div>
      <h2>Három külön felület a három külön feladatra</h2>
      <p class="muted-copy">
        A korábbi közös modult szétválasztottam. Az egyik nézet a számlából készít procurement kimenetet,
        a másik pedig a már meglévő beszerzést hasonlítja össze a számlával.
      </p>

      <div class="route-grid">
        <a class="route-card" href="{NETTFRONT_PROCUREMENT_ROUTE}">
          <div class="tag">Procurement</div>
          <strong>Számla -> beszerzés</strong>
          <p>Invoice CSV, Beszerzés lista, ZIP csomag és külön indítható import-segéd.</p>
        </a>

        <a class="route-card" href="{NETTFRONT_ORDER_ROUTE}">
          <div class="tag">Order suggestion</div>
          <strong>Excel -> rendelési javaslat</strong>
          <p>Raktár Excelből kész javaslat, szerkeszthető mennyiségekkel és jóváhagyható kész rendeléssel.</p>
        </a>

        <a class="route-card" href="{NETTFRONT_COMPARE_ROUTE}">
          <div class="tag">Compare</div>
          <strong>Számla vs. meglévő beszerzés</strong>
          <p>Számla és rendelési fájl összehasonlítása két munkalapos, színezett Excel riporttal.</p>
        </a>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Mi változott?</h3>
        <ul>
          <li>A három külön workflow most külön felületet kapott.</li>
          <li>A rendelési javaslat most külön Excel-alapú modul.</li>
          <li>Az összehasonlítás továbbra is önálló, célzott belépési pont.</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mi maradt?</h3>
        <p>
          A fordítási tábla, az alkatrész-mapping és az alap PDF-feldolgozási logika változatlanul az eredeti
          projektből jön, csak az élmény és a folyamatok lettek rendezettebbek.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="NettFront modulok egységes, sötét kezelőfelületen",
        lead="Válaszd ki, hogy számlából beszerzést készítesz, raktár Excelből rendelési javaslatot kérsz, vagy egy meglévő rendelést ellenőrzöl.",
        intro_label="Split workflow",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _order_safe_number(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _order_parse_quantity_input(value: str) -> tuple[float, bool]:
    text = str(value or "").strip()
    if not text:
        return 0.0, True
    sanitized = text.replace(" ", "")
    if "," in sanitized and "." in sanitized:
        if sanitized.rfind(",") > sanitized.rfind("."):
            sanitized = sanitized.replace(".", "").replace(",", ".")
        else:
            sanitized = sanitized.replace(",", "")
    elif "," in sanitized:
        sanitized = sanitized.replace(",", ".")
    try:
        return max(0.0, float(sanitized)), True
    except ValueError:
        return 0.0, False


def _format_order_metric(value) -> str:
    if value in (None, ""):
        return "—"
    raw = str(value).strip()
    if not raw:
        return "—"
    if not any(char.isdigit() for char in raw):
        return raw
    number = _order_safe_number(value)
    decimals = 0 if abs(number - round(number)) < 1e-9 else 2
    return _format_eu_number(number, decimals)


def _format_order_input_value(value) -> str:
    number = _order_safe_number(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _count_positive_order_rows(rows: list[NettfrontOrderRow]) -> int:
    return sum(1 for row in rows if _order_safe_number(row.order_qty) > 0)


def _nettfront_order_row_to_dict(row: NettfrontOrderRow) -> dict:
    return {
        "row_id": row.row_id,
        "part_number": row.part_number,
        "description": row.description,
        "stock_unit": row.stock_unit,
        "current_stock": row.current_stock,
        "confirmed_demand": row.confirmed_demand,
        "open_procurement": row.open_procurement,
        "safe_stock": row.safe_stock,
        "capacity": row.capacity,
        "order_qty": row.order_qty,
        "color": row.color,
        "length": row.length,
        "width": row.width,
        "is_super_matt": row.is_super_matt,
    }


def _nettfront_order_row_from_dict(payload: dict) -> NettfrontOrderRow:
    return NettfrontOrderRow(
        row_id=str(payload.get("row_id", "")).strip(),
        part_number=str(payload.get("part_number", "")).strip(),
        description=str(payload.get("description", "")).strip(),
        stock_unit=payload.get("stock_unit"),
        current_stock=payload.get("current_stock"),
        confirmed_demand=payload.get("confirmed_demand"),
        open_procurement=payload.get("open_procurement"),
        safe_stock=payload.get("safe_stock"),
        capacity=payload.get("capacity"),
        order_qty=_order_safe_number(payload.get("order_qty")),
        color=str(payload.get("color", "")).strip(),
        length=_order_safe_number(payload.get("length")),
        width=_order_safe_number(payload.get("width")),
        is_super_matt=bool(payload.get("is_super_matt")),
    )


def _read_nettfront_order_rows(job_dir: Path) -> list[NettfrontOrderRow]:
    rows_path = job_dir / "suggestions.json"
    if not rows_path.exists():
        return []
    try:
        payload = json.loads(rows_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [_nettfront_order_row_from_dict(item) for item in payload if isinstance(item, dict)]


def _write_nettfront_order_rows(job_dir: Path, rows: list[NettfrontOrderRow]) -> None:
    payload = [_nettfront_order_row_to_dict(row) for row in rows]
    (job_dir / "suggestions.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _nettfront_order_quantity_text(value: float) -> str:
    number = _order_safe_number(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _normalize_nettfront_part_number(value: object) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "", text)


def _nettfront_parts_list_header_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", _normalize_nettfront_part_number(value))


def _nettfront_order_part_number_aliases(value: object) -> list[str]:
    normalized = _normalize_nettfront_part_number(value)
    if not normalized:
        return []

    aliases = [normalized]
    for base_tag, secondary_tag, merged_tag in (("KAF", "KAFS", "KAFU"), ("PRA", "PRAS", "PRAU")):
        match = re.match(rf"^(NFA[^_]*_ANT)_{merged_tag}_(.+)$", normalized)
        if not match:
            continue
        base = match.group(1)
        suffix = match.group(2)
        aliases.extend(
            [
                f"{base}_{base_tag}_{suffix}",
                f"{base}_{secondary_tag}_{suffix}",
            ]
        )
        break

    unique_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        unique_aliases.append(alias)
    return unique_aliases


def _nettfront_order_display_part_number(value: object) -> str:
    aliases = _nettfront_order_part_number_aliases(value)
    if not aliases:
        return ""
    if len(aliases) >= 2 and aliases[0] != aliases[1]:
        return aliases[1]
    return aliases[0]


def _load_nettfront_parts_list_from_bytes(payload: bytes, file_name: str) -> list[str]:
    file_name = str(file_name or "").strip().lower()
    values: list[str] = []

    if file_name.endswith((".xlsx", ".xlsm")):
        if load_workbook is None:
            raise ValueError("Az Excel feldolgozáshoz hiányzik az openpyxl csomag.")
        workbook = load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        worksheet = workbook.active
        for row in worksheet.iter_rows(values_only=True):
            first_value = None
            for cell in row:
                if cell not in (None, ""):
                    first_value = cell
                    break
            normalized = _normalize_nettfront_part_number(first_value)
            if normalized:
                values.append(normalized)
    elif file_name.endswith(".csv"):
        decoded = None
        for encoding in ("utf-8-sig", "cp1250", "cp1252", "latin-1"):
            try:
                decoded = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("A CSV fájl kódolását nem tudtam beolvasni.")
        for row in csv.reader(io.StringIO(decoded)):
            first_value = next((cell for cell in row if str(cell).strip()), "")
            normalized = _normalize_nettfront_part_number(first_value)
            if normalized:
                values.append(normalized)
    else:
        raise ValueError("A friss alkatrészlista csak XLSX, XLSM vagy CSV lehet.")

    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not unique_values and _nettfront_parts_list_header_key(value) in {
            "ALKATRESZ",
            "ALKATRESZSZAM",
            "ALKATRSZAM",
            "CIKKSZAM",
            "PARTNUMBER",
            "PARTNUM",
        }:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _build_nettfront_order_import_csv(rows: list[NettfrontOrderRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    for row in rows:
        if _order_safe_number(row.order_qty) <= 0:
            continue
        part_number = _nettfront_order_display_part_number(row.part_number) or row.part_number.strip()
        if not part_number:
            continue
        writer.writerow([part_number, _nettfront_order_quantity_text(row.order_qty)])
    return buffer.getvalue().encode("utf-8-sig")


def _write_nettfront_order_bundle(job_dir: Path, metadata: dict) -> None:
    bundle_name = str(metadata.get("bundle_name", "nettfront-rendeles-output.zip")).strip() or "nettfront-rendeles-output.zip"
    bundle_files: list[str] = ["metadata.json", "suggestions.json", "rendelesi-javaslat.xlsx"]

    source_stock_file = str(metadata.get("source_stock_file", "")).strip()
    if source_stock_file:
        bundle_files.append(source_stock_file)

    source_parts_file = str(metadata.get("source_parts_file", "")).strip()
    if source_parts_file:
        bundle_files.append(source_parts_file)

    source_avg_file = str(metadata.get("source_average_file", "")).strip()
    if source_avg_file:
        bundle_files.append(source_avg_file)

    approved_file = str(metadata.get("approved_file", "")).strip()
    if approved_file:
        bundle_files.append(approved_file)

    import_file = str(metadata.get("import_file", "")).strip()
    if import_file:
        bundle_files.append(import_file)

    seen: set[str] = set()
    existing_files = []
    for file_name in bundle_files:
        if file_name in seen:
            continue
        seen.add(file_name)
        if (job_dir / file_name).exists():
            existing_files.append(file_name)

    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, existing_files))


def _write_nettfront_order_job(
    result,
    stock_name: str,
    stock_bytes: bytes,
    parts_name: str = "",
    parts_bytes: bytes | None = None,
    parts_count: int = 0,
) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir("order") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    stock_suffix = Path(stock_name).suffix.lower() or ".xlsx"
    source_stock_file = f"source-stock{stock_suffix}"
    (job_dir / source_stock_file).write_bytes(stock_bytes)
    (job_dir / "rendelesi-javaslat.xlsx").write_bytes(result.suggestion_workbook)
    _write_nettfront_order_rows(job_dir, result.rows)

    metadata = {
        "job_id": job_id,
        "job_type": "order",
        "bundle_name": "nettfront-rendeles-output.zip",
        "source_stock_name": stock_name,
        "source_stock_file": source_stock_file,
        "suggestion_row_count": len(result.rows),
        "merged_variant_count": result.merged_variant_count,
        "filtered_stock_count": result.filtered_stock_count,
        "added_super_matt_count": result.added_super_matt_count,
        "total_m2": result.total_m2,
        "avg_row_count": result.avg_row_count,
        "approved_row_count": 0,
        "approved_total_m2": 0.0,
        "approved_file": "",
        "approved_generated_at": "",
    }

    if parts_name and parts_bytes is not None:
        parts_suffix = Path(parts_name).suffix.lower() or ".xlsx"
        parts_file = f"source-parts{parts_suffix}"
        (job_dir / parts_file).write_bytes(parts_bytes)
        metadata["source_parts_name"] = parts_name
        metadata["source_parts_file"] = parts_file
        metadata["source_parts_count"] = max(0, int(parts_count))

    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_nettfront_order_bundle(job_dir, metadata)
    return job_id, metadata


def _persist_nettfront_order_approval(job_dir: Path, metadata: dict, rows: list[NettfrontOrderRow]) -> dict:
    suggestion_workbook = rows_to_suggestion_workbook(rows)
    approved_title = f"Divian-Mega Kft. Rendelés {datetime.now().strftime('%Y.%m.%d.')}"
    approved_workbook = rows_to_approved_workbook(rows, approved_title)
    import_csv = _build_nettfront_order_import_csv(rows)

    (job_dir / "rendelesi-javaslat.xlsx").write_bytes(suggestion_workbook)
    (job_dir / "rendeles-jovahagyott.xlsx").write_bytes(approved_workbook)
    (job_dir / "rendeles_sima.csv").write_bytes(import_csv)
    _write_nettfront_order_rows(job_dir, rows)

    updated_metadata = {
        **metadata,
        "suggestion_row_count": len(rows),
        "total_m2": calc_total_m2_from_rows(rows),
        "approved_row_count": _count_positive_order_rows(rows),
        "approved_total_m2": calc_total_m2_from_rows(rows),
        "approved_file": "rendeles-jovahagyott.xlsx",
        "import_file": "rendeles_sima.csv",
        "approved_generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (job_dir / "metadata.json").write_text(json.dumps(updated_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_nettfront_order_bundle(job_dir, updated_metadata)
    return updated_metadata


def render_nettfront_order_form(message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    content_html = f"""
      <div class="order-shell">
        <section class="order-hero-card">
          <div class="order-hero-grid">
            <div class="order-copy">
              <div class="tag">Excel -> rendelési javaslat</div>
              <strong>NettFront rendelési javaslat.</strong>
              <p>Feltöltöd a raktár Excelt, átnézed a javasolt darabszámokat, majd jóváhagyod a kész rendelést.</p>
              <div class="order-flow" aria-hidden="true">
                <span>Excel</span>
                <i></i>
                <span>Javaslat</span>
                <i></i>
                <span>Kész rendelés</span>
              </div>
            </div>

            <div class="order-visual" aria-hidden="true">
              <div class="order-visual-list">
                <div class="order-visual-row">
                  <span>Excel</span>
                  <i></i>
                  <strong>Beolvasás</strong>
                </div>
                <div class="order-visual-row">
                  <span>Javaslat</span>
                  <i></i>
                  <strong>Ellenőrzés</strong>
                </div>
                <div class="order-visual-row">
                  <span>Rendelés</span>
                  <i></i>
                  <strong>Jóváhagyás</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="order-upload-card">
          <div class="order-upload-head">
            <strong>Feltöltés</strong>
            <p>Egy raktár Excel kell. A rendszer kiszámolja a rendelési javaslatot.</p>
          </div>

          <form id="nettfront-order-form" class="order-upload-form" method="post" action="{NETTFRONT_ORDER_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="order-dropzone" id="nettfront-order-dropzone">
              <input
                id="nettfront-order-stock"
                class="order-file-input"
                type="file"
                name="stock_file"
                accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                required
              />
              <label class="order-dropzone-surface" for="nettfront-order-stock">
                <div class="order-dropzone-copy">
                  <span class="order-dropzone-chip">Excel</span>
                  <strong>Raktárfájl kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                  <div class="order-columns-note">
                    <span class="order-columns-title">Szükséges oszlopok</span>
                    <span><code>Alkatr.szám</code>, <code>Alkatr.leírás</code>, <code>Rend.áll.rakt.készl. ME</code>, <code>Rend.áll</code>, <code>Biztonsági készlet</code>, <code>Tárolh.menny.</code></span>
                  </div>
                </div>
                <span class="order-file-state" id="nettfront-order-stock-state">Támogatott formátum: XLSX, XLSM, CSV</span>
              </label>
            </div>

            <div class="order-optional-upload">
              <div class="order-optional-copy">
                <strong>Friss alkatrészlista</strong>
                <p>Opcionális egyoszlopos lista. A jóváhagyásnál ebből ellenőrizzük a kiválasztott cikkszámokat, hogy a kész rendelés bevételezhető legyen.</p>
              </div>

              <div class="order-dropzone is-secondary" id="nettfront-order-parts-dropzone">
                <input
                  id="nettfront-order-parts"
                  class="order-file-input"
                  type="file"
                  name="parts_file"
                  accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                />
                <label class="order-dropzone-surface" for="nettfront-order-parts">
                  <div class="order-dropzone-copy">
                    <span class="order-dropzone-chip">Opcionális</span>
                    <strong>Friss lista kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                    <div class="order-columns-note">
                      <span class="order-columns-title">Elvárt tartalom</span>
                      <span>Egyszerű, egyoszlopos cikkszámlista. Az első oszlopban csak az alkatrészszámok szerepeljenek.</span>
                    </div>
                  </div>
                  <span class="order-file-state" id="nettfront-order-parts-state">Támogatott formátum: XLSX, XLSM, CSV</span>
                </label>
              </div>
            </div>

            <div class="order-action-row">
              <button class="button button-primary" type="submit" id="nettfront-order-submit">Javaslat készítése</button>
              <span class="inline-note">A kész lista külön oldalon nyílik meg, ott tudod jóváhagyni.</span>
            </div>
          </form>
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-shell {
    display: grid;
    gap: 16px;
  }
  .order-hero-card,
  .order-upload-card {
    position: relative;
    overflow: hidden;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-hero-card::before,
  .order-upload-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top left, rgba(67, 222, 207, 0.1), transparent 32%);
    pointer-events: none;
  }
  .order-hero-grid {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
    gap: 16px;
    align-items: stretch;
    padding: 24px;
  }
  .order-copy {
    display: grid;
    gap: 12px;
    align-content: start;
  }
  .order-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.7rem, 3.8vw, 2.5rem);
    line-height: 1;
  }
  .order-copy p,
  .order-upload-head p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    max-width: 58ch;
  }
  .order-flow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 2px;
    color: var(--muted);
    font-size: 0.84rem;
  }
  .order-flow span {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.035);
  }
  .order-flow i {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.18), rgba(67, 222, 207, 0.62));
  }
  .order-visual {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 212px;
    padding: 18px;
    border-radius: 22px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.02));
  }
  .order-visual-list {
    display: grid;
    gap: 12px;
    width: min(100%, 240px);
  }
  .order-visual-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    align-items: center;
    min-height: 56px;
    padding: 0 16px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-visual-row span {
    color: var(--muted);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-visual-row i {
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.16), rgba(67, 222, 207, 0.56));
  }
  .order-visual-row strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.94rem;
    font-weight: 600;
  }
  .order-upload-card {
    padding: 22px;
  }
  .order-upload-head {
    display: grid;
    gap: 6px;
    margin-bottom: 14px;
  }
  .order-upload-head strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-upload-form {
    display: grid;
    gap: 16px;
  }
  .order-optional-upload {
    display: grid;
    gap: 12px;
    padding: 16px;
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.025);
  }
  .order-optional-copy {
    display: grid;
    gap: 6px;
  }
  .order-optional-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.96rem;
  }
  .order-optional-copy p {
    margin: 0;
    color: var(--muted);
    line-height: 1.5;
  }
  .order-dropzone {
    position: relative;
  }
  .order-dropzone.is-secondary .order-dropzone-surface {
    min-height: 138px;
    padding: 18px 20px;
    border-radius: 20px;
    border-style: solid;
    border-color: rgba(255, 255, 255, 0.1);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.012));
  }
  .order-file-input {
    position: absolute;
    inset: 0;
    opacity: 0;
    pointer-events: none;
  }
  .order-dropzone-surface {
    display: grid;
    gap: 14px;
    min-height: 176px;
    padding: 22px;
    border-radius: 24px;
    border: 1px dashed rgba(67, 222, 207, 0.24);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.016));
    cursor: pointer;
    transition:
      border-color 180ms ease,
      transform 180ms ease,
      box-shadow 180ms ease;
  }
  .order-dropzone.is-dragover .order-dropzone-surface,
  .order-dropzone-surface:hover {
    border-color: rgba(67, 222, 207, 0.42);
    transform: translateY(-1px);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.22);
  }
  .order-dropzone-copy {
    display: grid;
    gap: 8px;
    justify-items: start;
  }
  .order-columns-note {
    display: grid;
    gap: 4px;
    margin-top: 4px;
    padding: 10px 12px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.45;
  }
  .order-columns-title {
    color: var(--text);
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .order-dropzone-chip {
    display: inline-flex;
    align-items: center;
    min-height: 30px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.04);
    color: var(--muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .order-dropzone-copy strong {
    font-size: 1rem;
  }
  .order-file-state {
    font-size: 0.9rem;
    color: var(--muted);
  }
  .order-action-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  @media (max-width: 960px) {
    .order-hero-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-hero-grid,
    .order-upload-card {
      padding: 18px;
    }
    .order-dropzone-surface {
      min-height: 156px;
      padding: 18px;
    }
    .order-action-row {
      align-items: stretch;
      flex-direction: column;
    }
    .order-action-row .button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const stockInput = document.getElementById("nettfront-order-stock");
    const stockState = document.getElementById("nettfront-order-stock-state");
    const stockDropzone = document.getElementById("nettfront-order-dropzone");
    const partsInput = document.getElementById("nettfront-order-parts");
    const partsState = document.getElementById("nettfront-order-parts-state");
    const partsDropzone = document.getElementById("nettfront-order-parts-dropzone");
    const form = document.getElementById("nettfront-order-form");
    const submitButton = document.getElementById("nettfront-order-submit");
    if (!stockInput || !stockState || !stockDropzone || !partsInput || !partsState || !partsDropzone || !form || !submitButton) return;

    const updateState = (input, state, emptyLabel) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyLabel;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    const bindDropzone = (dropzone) => {
      ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.add("is-dragover");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.remove("is-dragover");
        });
      });
    };

    bindDropzone(stockDropzone);
    bindDropzone(partsDropzone);

    stockInput.addEventListener("change", () => updateState(stockInput, stockState, "Támogatott formátum: XLSX, XLSM, CSV"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLSX, XLSM, CSV"));
    form.addEventListener("submit", () => {
      submitButton.textContent = "Javaslat készül...";
      submitButton.disabled = true;
    });
  })();
</script>
"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_order_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    job_dir, _ = _read_nettfront_job("order", job_id)
    rows = _read_nettfront_order_rows(job_dir) if job_dir is not None else []
    suggestion_count = len(rows)
    positive_count = _count_positive_order_rows(rows)
    total_m2 = calc_total_m2_from_rows(rows)
    approved_file = str(metadata.get("approved_file", "")).strip()
    approved_ready = bool(approved_file and job_dir is not None and (job_dir / approved_file).exists())
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    import_file = str(metadata.get("import_file", "")).strip()
    import_ready = bool(import_file and job_dir is not None and (job_dir / import_file).exists())
    source_stock_name = str(metadata.get("source_stock_name", "")).strip() or "Feltöltött raktárfájl"
    source_parts_name = str(metadata.get("source_parts_name", "")).strip() or str(metadata.get("source_average_name", "")).strip()
    source_parts_count = int(metadata.get("source_parts_count", 0) or 0)

    table_html = """
      <div class="order-empty-state">
        <strong>Nincs rendelési javaslat.</strong>
        <p>A feltöltött fájl alapján most nem találtam rendelésre váró tételt.</p>
      </div>
    """
    if rows:
        row_html = []
        for row in rows:
            description = html.escape(row.description or "Megnevezés nélkül")
            display_part_number = _nettfront_order_display_part_number(row.part_number)
            part_number = html.escape(display_part_number or row.part_number or "Nincs cikkszám")
            color_value = html.escape(row.color.strip() or "Nincs színadat")
            current_stock = html.escape(_format_order_metric(row.current_stock))
            safe_stock = html.escape(_format_order_metric(row.safe_stock))
            capacity = html.escape(_format_order_metric(row.capacity))
            qty_value = html.escape(_format_order_input_value(row.order_qty))
            super_matt_html = '<span class="order-inline-badge">SM</span>' if row.is_super_matt else ""
            row_html.append(
                f"""
                <tr>
                  <td>
                    <div class="order-item-main">
                      <strong>{description}</strong>
                      <span>{part_number}</span>
                    </div>
                  </td>
                  <td>
                    <div class="order-color-stack">
                      <span class="order-color-text">{color_value}</span>
                      {super_matt_html}
                    </div>
                  </td>
                  <td class="is-metric">{current_stock}</td>
                  <td class="is-metric">{safe_stock}</td>
                  <td class="is-metric">{capacity}</td>
                  <td>
                    <input
                      class="order-qty-input"
                      type="text"
                      inputmode="decimal"
                      name="qty__{html.escape(row.row_id)}"
                      value="{qty_value}"
                    />
                  </td>
                </tr>
                """
            )
        table_html = f"""
          <form method="post" action="{NETTFRONT_ORDER_APPROVE_PREFIX}/{job_id}">
            <div class="order-table-wrap">
              <table class="order-table">
                <thead>
                  <tr>
                    <th>Tétel</th>
                    <th>Szín</th>
                    <th class="is-metric">Rend.áll</th>
                    <th class="is-metric">Biztonsági</th>
                    <th class="is-metric">Tárolható</th>
                    <th class="is-metric">Rendelés</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(row_html)}
                </tbody>
              </table>
            </div>

            <div class="order-approve-bar">
              <span class="inline-note">A 0 mennyiség azt jelenti, hogy az adott tétel nem kerül be a kész rendelésbe.</span>
              <button class="button button-primary" type="submit">Jóváhagyás és kész rendelés</button>
            </div>
          </form>
        """

    helper_action_html = ""
    helper_hint_html = ""
    if approved_ready and import_ready:
        if helper_running:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_STOP_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Leállítás</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A bevételezési segéd fut. Nyisd meg a bevételezési ablakot, majd Shift + Space indítja az importot. Kilépés: ESC.</p>'
        else:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_LAUNCH_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Bevételezés indítása</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A kész rendelés bevételezhető. Indítsd a segédet, majd a bevételezési ablakban Shift + Space indítja az importot. Kilépés: ESC.</p>'

    content_html = f"""
      <div class="order-result-shell">
        <section class="order-result-card">
          <div class="order-result-head">
            <div class="tag">Rendelési javaslat</div>
            <strong>Átnézés után egy gombbal kész rendelés lesz belőle.</strong>
            <p>{html.escape(source_stock_name)}</p>
          </div>

          <div class="order-summary-grid">
            <article class="order-summary-card">
              <strong>{suggestion_count}</strong>
              <span>javasolt tétel</span>
            </article>
            <article class="order-summary-card">
              <strong>{positive_count}</strong>
              <span>jóváhagyásra kész sor</span>
            </article>
            <article class="order-summary-card">
              <strong>{html.escape(_format_order_metric(total_m2))}</strong>
              <span>becsült összes m²</span>
            </article>
          </div>

          <div class="order-meta-strip">
            <span>Összevont variánsok: {metadata.get("merged_variant_count", 0)}</span>
            <span>Küszöb alatti tételek: {metadata.get("filtered_stock_count", 0)}</span>
            <span>SM sorok: {metadata.get("added_super_matt_count", 0)}</span>
            <span>Átlagolt alkatrészek: {metadata.get("avg_row_count", 0)}</span>
            {"<span>Friss alkatrészlista: " + html.escape(source_parts_name) + (f' • {source_parts_count} tétel' if source_parts_count else '') + "</span>" if source_parts_name else ""}
            {"<span>Bevételezési segéd fut</span>" if helper_running else ""}
          </div>

          <div class="order-toolbar">
            <button class="button button-secondary order-toggle-button" type="button" id="order-table-toggle">Javaslat megmutatása</button>
            <a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/suggestion-xlsx">Javaslat letöltése</a>
            {f'<a class="button button-primary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/approved-xlsx">Kész rendelés letöltése</a>' if approved_ready else ''}
            {f'<a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/import-csv">Bevételezési lista</a>' if import_ready else ''}
            {helper_action_html}
            <a class="button button-secondary" href="{NETTFRONT_ORDER_ROUTE}">Új feltöltés</a>
          </div>
          {helper_hint_html}
        </section>

        <section class="order-table-card" id="order-table-card" hidden>
          <div class="order-result-head">
            <strong>Rendelési javaslat</strong>
            <p>Itt módosíthatod a mennyiségeket, majd jóváhagyhatod a kész rendelést.</p>
          </div>
          {table_html}
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-result-card,
  .order-table-card {
    position: relative;
    overflow: hidden;
    padding: 22px;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-result-shell {
    display: grid;
    gap: 16px;
  }
  .order-result-head,
  .order-item-main,
  .order-empty-state {
    display: grid;
    gap: 6px;
  }
  .order-result-head strong,
  .order-summary-card strong,
  .order-item-main strong,
  .order-empty-state strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-result-head p,
  .order-summary-card span,
  .order-meta-strip span,
  .order-item-main span,
  .order-empty-state p {
    margin: 0;
    color: var(--muted);
  }
  .order-summary-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 6px;
  }
  .order-summary-card {
    padding: 16px 18px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-summary-card strong {
    display: block;
    margin-bottom: 4px;
    font-size: 1.65rem;
    line-height: 1;
  }
  .order-meta-strip,
  .order-toolbar,
  .order-approve-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .order-meta-strip {
    gap: 8px 14px;
    padding-top: 2px;
    color: var(--muted);
  }
  .order-meta-strip span {
    font-size: 0.88rem;
  }
  .order-toolbar {
    margin-top: 4px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .order-helper-copy {
    margin: 10px 0 0;
    color: var(--muted);
    line-height: 1.55;
  }
  .order-toggle-button {
    min-width: 200px;
  }
  .order-table-wrap {
    overflow: auto;
    margin-top: 14px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(7, 12, 20, 0.84);
  }
  .order-table {
    width: 100%;
    min-width: 860px;
    border-collapse: collapse;
    background: transparent;
  }
  .order-table th,
  .order-table td {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.045);
    text-align: left;
    vertical-align: middle;
  }
  .order-table th {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-soft);
    font-size: 0.76rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-table th.is-metric,
  .order-table td.is-metric {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .order-table tbody tr:nth-child(odd) td {
    background: rgba(255, 255, 255, 0.012);
  }
  .order-table tbody tr:nth-child(even) td {
    background: rgba(255, 255, 255, 0.022);
  }
  .order-table tbody tr:hover {
    background: transparent;
  }
  .order-table tbody tr:hover td {
    background: rgba(255, 255, 255, 0.05);
  }
  .order-item-main strong {
    font-size: 0.96rem;
    line-height: 1.35;
  }
  .order-item-main span {
    font-size: 0.82rem;
  }
  .order-color-stack {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .order-color-text {
    color: var(--text);
    line-height: 1.45;
  }
  .order-inline-badge {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 0 8px;
    border-radius: 999px;
    background: rgba(67, 222, 207, 0.1);
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .order-qty-input {
    width: 96px;
    min-height: 42px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
    font: inherit;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .order-qty-input:focus {
    outline: none;
    border-color: rgba(67, 222, 207, 0.48);
    box-shadow: 0 0 0 4px rgba(67, 222, 207, 0.12);
  }
  .order-empty-state {
    padding: 20px;
    border-radius: 18px;
    border: 1px dashed rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-approve-bar {
    justify-content: space-between;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  @media (max-width: 960px) {
    .order-summary-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-result-card,
    .order-table-card {
      padding: 18px;
    }
    .order-toolbar,
    .order-approve-bar {
      align-items: stretch;
      flex-direction: column;
    }
    .order-toolbar .button,
    .order-approve-bar .button,
    .order-toggle-button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const button = document.getElementById("order-table-toggle");
    const card = document.getElementById("order-table-card");
    if (!button || !card) return;

    const sync = () => {
      button.textContent = card.hidden ? "Javaslat megmutatása" : "Javaslat elrejtése";
    };

    button.addEventListener("click", () => {
      card.hidden = !card.hidden;
      sync();
      if (!card.hidden) {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

    sync();
  })();
</script>
"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_procurement_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="procurement-shell">
        <section class="procurement-hero-card">
          <div class="procurement-hero-grid">
            <div class="procurement-copy">
              <div class="tag">Invoice -> beszerzés</div>
              <strong>NettFront számlából beszerzés.</strong>
              <p>Egy feltöltés után elkészül minden fájl, ami kell a következő lépéshez.</p>
              <div class="procurement-flow" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>CSV</span>
              </div>
            </div>

            <div class="procurement-visual" aria-hidden="true">
              <div class="procurement-orbit"></div>
              <div class="procurement-doc is-source">
                <span class="procurement-doc-label">Számla</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
              <div class="procurement-transfer"></div>
              <div class="procurement-doc is-target">
                <span class="procurement-doc-label">Beszerzés</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="procurement-upload-card" id="feltoltes">
          <div class="procurement-surface-title">
            <strong>Feltöltés</strong>
            <p>Fájl kiválasztása, majd indítás.</p>
          </div>

          <form id="nettfront-procurement-form" method="post" action="{NETTFRONT_PROCUREMENT_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="procurement-upload-shell" id="nettfront-procurement-shell">
              <input
                class="procurement-file-input"
                id="nettfront-procurement-invoice"
                type="file"
                name="invoice_pdf"
                accept=".pdf,application/pdf"
                required
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-invoice">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">PDF</div>
                  <div class="procurement-upload-copy">
                    <strong>Számla kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Számla</span>
                  <i></i>
                  <span>Feldolgozás</span>
                  <i></i>
                  <span>Beszerzési csomag</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-invoice-state">Támogatott formátum: PDF</span>
              </label>

              <input
                class="procurement-file-input"
                id="nettfront-procurement-parts"
                type="file"
                name="parts_file"
                accept=".xlsx,.xlsm,.csv,text/csv"
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-parts">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">XLSX</div>
                  <div class="procurement-upload-copy">
                    <strong>Friss alkatrészlista</strong>
                    <p>Opcionális. Ha most feltöltöd, már ebből építjük a Beszerzést.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Alkatrészlista</span>
                  <i></i>
                  <span>Kódfrissítés</span>
                  <i></i>
                  <span>Pontosabb Beszerzés</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-parts-state">Támogatott formátum: XLSX, XLSM, CSV</span>
              </label>

              <div class="procurement-action-row">
                <button class="button button-primary" type="submit" id="nettfront-procurement-submit">Beszerzés készítése</button>
                <span class="inline-note">Az eredmény külön oldalon nyílik meg.</span>
              </div>
            </div>
          </form>

          <div class="procurement-output-footer">
            <strong>Elkészül</strong>
            <span class="procurement-pill">invoice-output.csv</span>
            <span class="procurement-pill">Beszerzés</span>
            <span class="procurement-pill">ZIP csomag</span>
          </div>
        </section>
      </div>
    """

    extra_script = """
<script>
  (() => {
    const invoiceInput = document.getElementById("nettfront-procurement-invoice");
    const invoiceState = document.getElementById("nettfront-procurement-invoice-state");
    const partsInput = document.getElementById("nettfront-procurement-parts");
    const partsState = document.getElementById("nettfront-procurement-parts-state");
    const shell = document.getElementById("nettfront-procurement-shell");
    const form = document.getElementById("nettfront-procurement-form");
    const submitButton = document.getElementById("nettfront-procurement-submit");
    if (!invoiceInput || !invoiceState || !partsInput || !partsState || !shell || !form || !submitButton) return;

    const updateState = (input, state, emptyText) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyText;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    ["dragenter", "dragover"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.add("is-dragover");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.remove("is-dragover");
      });
    });

    invoiceInput.addEventListener("change", () => updateState(invoiceInput, invoiceState, "Támogatott formátum: PDF"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLSX, XLSM, CSV"));

    form.addEventListener("submit", () => {
      submitButton.textContent = "Beszerzés készül...";
      submitButton.disabled = true;
    });
  })();
</script>"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def _read_procurement_preview_rows(job_id: str, limit: int | None = None) -> tuple[list[list[str]], int]:
    job_dir, _ = _read_nettfront_job("procurement", job_id)
    if job_dir is None:
        return [], 0

    csv_path = job_dir / "rendeles_sima.csv"
    if not csv_path.exists():
        return [], 0

    raw_bytes = csv_path.read_bytes()
    text = raw_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows: list[list[str]] = []
    total_rows = 0
    for row in reader:
        clean_row = [str(value).strip() for value in row[:2]]
        if not any(clean_row):
            continue
        total_rows += 1
        if limit is None or len(rows) < limit:
            rows.append(clean_row)
    return rows, total_rows


def render_nettfront_procurement_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        lowered_message = message.casefold()
        helper_message = (
            "import-segéd" in lowered_message
            or "import-seged" in lowered_message
            or "shift + space" in lowered_message
            or "esc" in lowered_message
        )
        if not helper_message:
            extra_class = " success" if success else ""
            notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    missing_codes = metadata.get("missing_codes") or []
    job_dir = _job_runtime_dir("procurement") / job_id
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    preview_rows, preview_total = _read_procurement_preview_rows(job_id)
    uploaded_parts_name = str(metadata.get("uploaded_parts_name", "")).strip()
    missing_html = '<div class="procurement-result-meta"><span class="procurement-result-pill">Nincs hiányzó kód</span></div>'
    if missing_codes:
        visible_codes = missing_codes[:10]
        more_count = len(missing_codes) - len(visible_codes)
        code_chips = "".join(f'<span class="procurement-code-chip">{html.escape(code)}</span>' for code in visible_codes)
        more_html = f'<span class="procurement-code-chip">+{more_count} további</span>' if more_count > 0 else ""
        missing_html = f"""
          <div class="procurement-result-meta">
            <span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>
          </div>
          <div class="procurement-code-list">
            {code_chips}
            {more_html}
          </div>
        """

    preview_html = '<div class="procurement-preview-empty">A Beszerzés most nem elérhető.</div>'
    if preview_rows:
        preview_rows_html = "".join(
            f"<tr><td>{html.escape(row[0] if len(row) > 0 else '')}</td><td>{html.escape(row[1] if len(row) > 1 else '')}</td></tr>"
            for row in preview_rows
        )
        preview_html = f"""
          <div class="procurement-preview-table-wrap">
            <table class="procurement-preview-table">
              <thead>
                <tr>
                  <th>Cikkszám</th>
                  <th>Mennyiség</th>
                </tr>
              </thead>
              <tbody>
                {preview_rows_html}
              </tbody>
            </table>
          </div>
        """

    helper_status_pill = '<span class="procurement-result-pill">Import-segéd nincs elindítva</span>'
    helper_status_copy = "A Beszerzés elkészült. Indítsd a segédet, majd Shift + Space-re elindul az import."
    action_html = f"""
      <form class="launch-form" method="post" action="{NETTFRONT_PROCUREMENT_LAUNCH_PREFIX}/{job_id}">
        <div class="procurement-launch-row">
          <button class="button button-primary" type="submit">Beszerzés indítása</button>
          <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
        </div>
      </form>
    """
    if missing_codes:
        uploaded_meta_html = ""
        if uploaded_parts_name:
            uploaded_meta_html = f'<div class="procurement-remap-meta">Utolsó feltöltött lista: {html.escape(uploaded_parts_name)}</div>'
        helper_status_pill = f'<span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>'
        helper_status_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
        action_html = f"""
          <article class="procurement-remap-card">
            <strong>Alkatrészlista feltöltése</strong>
            <p>Hiányzó kódokat találtunk. Tölts fel egy friss alkatrészlistát, és újraépítjük a Beszerzést.</p>
            {uploaded_meta_html}
            <form class="procurement-remap-form" method="post" action="{NETTFRONT_PROCUREMENT_PARTS_PREFIX}/{job_id}" enctype="multipart/form-data">
              <input class="procurement-remap-input" type="file" name="parts_file" accept=".xlsx,.xlsm,.csv,text/csv" required />
              <div class="procurement-launch-row">
                <button class="button button-primary" type="submit">Alkatrészlista feltöltése</button>
                <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
              </div>
            </form>
          </article>
        """
    elif helper_running:
        helper_status_pill = '<span class="procurement-result-pill">Import-segéd fut</span>'
        helper_status_copy = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megszakítja."
        action_html = f"""
          <div class="procurement-launch-row">
            <form method="post" action="{NETTFRONT_PROCUREMENT_STOP_PREFIX}/{job_id}">
              <button class="button button-primary" type="submit">Leállítás</button>
            </form>
            <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
          </div>
        """

    lead_copy = "A Beszerzés elkészült. Ha minden kód megvan, a segéd automatikusan elindul."
    if missing_codes:
        lead_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
    elif helper_running:
        lead_copy = "A segéd fut: Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."
    elif message and "automatikus indítása nem sikerült" in message:
        lead_copy = "Az automatikus indítás most nem sikerült. Nyomd meg a Beszerzés indítása gombot."

    warning_modal_html = ""
    extra_script = ""
    if not missing_codes:
        warning_modal_html = f"""
          <div class="procurement-warning-modal" id="procurement-warning-modal" aria-hidden="true">
            <div class="procurement-warning-card" role="dialog" aria-modal="true" aria-labelledby="procurement-warning-title">
              <strong id="procurement-warning-title">Figyelem</strong>
              <p>
                A beszerzést a gép billentyűkkel fogja kezelni az InSight-ban. Csak akkor indítsd el,
                ha biztosan tudod mit csinálsz. Nyiss egy üres beszerzést az InSight-ban, majd nyomd meg a
                <strong>Shift + Space</strong> billentyűkombinációt. Ha baj van, a <strong>Leállítás</strong>
                gomb azonnal megszakítja a segédet.
              </p>
              <div class="procurement-warning-actions">
                <button class="button button-primary" type="button" id="procurement-warning-close">Értem</button>
              </div>
            </div>
          </div>
        """
        extra_script = f"""
<script>
  (() => {{
    const modal = document.getElementById("procurement-warning-modal");
    const closeButton = document.getElementById("procurement-warning-close");
    if (!modal || !closeButton) return;

    const storageKey = "divian-procurement-warning:{job_id}";
    if (!window.sessionStorage.getItem(storageKey)) {{
      modal.classList.add("is-visible");
      modal.setAttribute("aria-hidden", "false");
    }}

    const closeModal = () => {{
      modal.classList.remove("is-visible");
      modal.setAttribute("aria-hidden", "true");
      window.sessionStorage.setItem(storageKey, "1");
    }};

    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) {{
        closeModal();
      }}
    }});
  }})();
</script>"""

    content_html = f"""
      <div class="procurement-result-shell">
        <div class="tag">Procurement ready</div>
        <h2>A beszerzés elő van készítve</h2>
        <p class="muted-copy">{lead_copy}</p>

        <div class="procurement-result-grid">
          <article class="procurement-result-card">
            <strong>Állapot</strong>
            <div class="procurement-result-meta">
              <span class="procurement-result-pill">{metadata.get("invoice_row_count", 0)} számlasor</span>
              <span class="procurement-result-pill">{preview_total} beszerzési sor</span>
              {helper_status_pill}
            </div>
            <p class="procurement-result-copy">{helper_status_copy}</p>
          </article>

          <article class="procurement-result-card">
            <strong>Hiányzó kódok</strong>
            {missing_html}
          </article>
        </div>

        <article class="procurement-preview-card">
          <div class="procurement-preview-head">
            <div>
              <strong>Beszerzés</strong>
              <p>Előnézet a kész beszerzési listából.</p>
            </div>
            <p>{preview_total} / {preview_total} sor látszik</p>
          </div>
          {preview_html}
        </article>

        {action_html}
      </div>
      {warning_modal_html}
    """

    layout_lead = "A kész Beszerzésnél a segéd automatikusan indul. Ha baj van, a Leállítás gombbal azonnal megállítható."
    if missing_codes:
        layout_lead = "Hiányzó kódoknál tölts fel alkatrészlistát, és a rendszer újraépíti a Beszerzést."
    elif helper_running:
        layout_lead = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."

    return _render_nettfront_layout(
        heading="Beszerzés kész",
        lead=layout_lead,
        intro_label="Procurement ready",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_compare_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Invoice vs procurement</div>
      <h2>NettFront számla és meglévő beszerzés összehasonlítása</h2>
      <p class="muted-copy">
        Töltsd fel a számlát és a meglévő rendelési fájlt. A rendszer elkészít egy két munkalapos,
        színezett Excel riportot, amiből gyorsan látszik minden eltérés.
      </p>

      <form id="nettfront-compare-form" class="upload-grid" method="post" action="{NETTFRONT_COMPARE_PROCESS_ROUTE}" enctype="multipart/form-data">
        <label class="upload-field">
          <strong>Számla PDF</strong>
          <span class="field-hint">Kötelező. Ebből készül az invoice sorstruktúra.</span>
          <input id="nettfront-compare-invoice" type="file" name="invoice_pdf" accept=".pdf,application/pdf" required />
          <span class="field-hint" id="nettfront-compare-invoice-state">Támogatott formátum: PDF</span>
        </label>

        <label class="upload-field">
          <strong>Meglévő rendelés</strong>
          <span class="field-hint">Kötelező. XLSX, XLSM vagy CSV formátum.</span>
          <input id="nettfront-compare-order" type="file" name="order_file" accept=".xlsx,.xlsm,.csv" required />
          <span class="field-hint" id="nettfront-compare-order-state">Támogatott formátum: XLSX, XLSM, CSV</span>
        </label>
      </form>

      <div class="action-row">
        <button class="button button-primary" type="submit" form="nettfront-compare-form">Összehasonlító riport készítése</button>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Kimenetek</h3>
        <ul>
          <li>`compare-output.xlsx` két munkalappal</li>
          <li>`invoice-output.csv` a visszakövetéshez</li>
          <li>egyben letölthető ZIP</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mire jó?</h3>
        <p>
          Akkor hasznos, ha a beszerzés már létezik, és a számlával akarod kontrollálni, hogy a kódok,
          mennyiségek és árak ténylegesen egyeznek-e.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="Meglévő beszerzés és számla összehasonlítása",
        lead="Külön felület csak az ellenőrzésre, hogy a már kész rendelés és az érkező számla pontosan összevethető legyen.",
        intro_label="Comparison module",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
        extra_script=_render_file_bind_script(
            [
                ("nettfront-compare-invoice", "nettfront-compare-invoice-state", "Támogatott formátum: PDF"),
                ("nettfront-compare-order", "nettfront-compare-order-state", "Támogatott formátum: XLSX, XLSM, CSV"),
            ]
        ),
    )


def render_nettfront_compare_result(job_id: str, metadata: dict, message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Comparison output ready</div>
      <h2>Az összehasonlító riport elkészült</h2>
      <p class="muted-copy">
        Elkészült a számla és a meglévő beszerzés összevetése. Innen letölthető a színezett Excel riport és a kapcsolódó fájlok.
      </p>

      <div class="summary-grid">
        <article class="summary-card">
          <strong>{metadata.get("invoice_row_count", 0)}</strong>
          <span>felismert számlasor</span>
        </article>
        <article class="summary-card">
          <strong>{metadata.get("order_row_count", 0)}</strong>
          <span>beolvasott rendelési sor</span>
        </article>
        <article class="summary-card">
          <strong>Excel</strong>
          <span>két munkalapos riport</span>
        </article>
      </div>

      <div class="download-grid">
        <article class="download-card">
          <strong>Compare Excel</strong>
          <p>Színezett riport két összevetési nézettel.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/compare-xlsx">compare-output.xlsx</a>
        </article>

        <article class="download-card">
          <strong>Invoice CSV</strong>
          <p>A feldolgozott számlasorok külön is letölthetők.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/invoice-csv">invoice-output.csv</a>
        </article>

        <article class="download-card">
          <strong>Teljes csomag</strong>
          <p>Minden generált fájl egy ZIP-ben.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/bundle-zip">compare-output.zip</a>
        </article>
      </div>

      <div class="action-row">
        <a class="button button-primary" href="{NETTFRONT_COMPARE_ROUTE}">Új összehasonlítás</a>
        <a class="button button-secondary" href="{NETTFRONT_ROUTE}">Vissza a NettFront modulokhoz</a>
      </div>
    """

    side_html = f"""
      <article class="stack-card">
        <h3>Állapot</h3>
        <ul class="status-list">
          <li>Invoice sorok: {metadata.get("invoice_row_count", 0)}</li>
          <li>Rendelési sorok: {metadata.get("order_row_count", 0)}</li>
          <li>Riport: elkészült</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mit kapsz?</h3>
        <p>
          A compare Excel külön munkalapokon mutatja az order->invoice és invoice->order nézetet, így gyorsan
          látszanak a hiányzó vagy eltérő sorok.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="Az összehasonlítás lefutott",
        lead="A meglévő rendelés és a számla közötti eltérések most már külön riportban átnézhetők.",
        intro_label="Compare ready",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _vacation_route(month_value: str, **params: object) -> str:
    query: dict[str, str] = {}
    if month_value:
        query["month"] = month_value
    for key, value in params.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        if clean_value:
            query[key] = clean_value
    suffix = urllib.parse.urlencode(query)
    return f"{VACATION_CALENDAR_ROUTE}?{suffix}" if suffix else VACATION_CALENDAR_ROUTE


def _vacation_render_calendar_cell(cell: dict) -> str:
    classes = ["vacation-day"]
    if not cell["is_current_month"]:
        classes.append("is-other-month")
    if cell["entries"]:
        classes.append("is-busy")
    if any(load["count"] >= load["max_absent"] for load in cell["loads"]):
        classes.append("is-limited")
    if cell["date"] == date.today():
        classes.append("is-today")

    day_value = _vacation_date_value(cell["date"])
    interactive_attrs = (
        f' data-vacation-day="{html.escape(day_value)}" tabindex="0" role="button"'
        if cell["is_current_month"]
        else ""
    )
    day_badge = ""
    entry_html = "".join(
        f'<button class="vacation-entry" type="button" data-vacation-leave-id="{entry["id"]}" '
        f'data-vacation-day="{html.escape(day_value)}">{html.escape(entry["employee_name"])}</button>'
        for entry in cell["entries"][:3]
    )
    if len(cell["entries"]) > 3:
        entry_html += f'<span class="vacation-entry-more">+{len(cell["entries"]) - 3} további</span>'

    load_html = ""

    return f"""
      <div class="{' '.join(classes)}"{interactive_attrs}>
        <div class="vacation-day-head">
          <span class="vacation-day-number">{cell["date"].day}</span>
          {day_badge}
        </div>
        <div class="vacation-day-list">{entry_html}</div>
        {load_html}
      </div>
    """


def _vacation_render_leave_item(leave_entry: dict, month_value: str) -> str:
    start_day = _vacation_parse_date(leave_entry["start_date"])
    end_day = _vacation_parse_date(leave_entry["end_date"])
    if start_day and end_day:
        range_label = _vacation_date_label(start_day) if start_day == end_day else f"{_vacation_date_label(start_day)} - {_vacation_date_label(end_day)}"
    else:
        range_label = f"{leave_entry['start_date']} - {leave_entry['end_date']}"
    department_label = ", ".join(leave_entry["department_names"]) or "Nincs részleg"
    note_html = f"<span>{html.escape(leave_entry['note'])}</span>" if leave_entry["note"] else ""
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(leave_entry["employee_name"])}</strong>
          <span>{html.escape(range_label)} · {html.escape(department_label)}</span>
          {note_html}
        </div>
      </li>
    """


def _vacation_render_employee_item(employee: dict, month_value: str) -> str:
    badges = "".join(
        f'<span class="vacation-mini-badge">{html.escape(name)}</span>'
        for name in employee["department_names"]
    )
    edit_href = _vacation_route(month_value, edit_employee=employee["id"]) + "#employee-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(employee["name"])}</strong>
          <span>{len(employee["department_names"])} részleg · {employee["vacation_count"]} rögzített szabadság</span>
          <div class="vacation-mini-badge-row">{badges}</div>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE}">
            <input type="hidden" name="employee_id" value="{employee["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """


def _vacation_render_department_item(department: dict, month_value: str) -> str:
    edit_href = _vacation_route(month_value, edit_department=department["id"]) + "#department-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(department["name"])}</strong>
          <span>{department["employee_count"]} kolléga · max. {department["max_absent"]} fő lehet egyszerre szabadságon</span>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE}">
            <input type="hidden" name="department_id" value="{department["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """


def render_vacation_calendar(
    *,
    month_value: str = "",
    message: str = "",
    success: bool = False,
    edit_department_id: int | None = None,
    edit_employee_id: int | None = None,
    edit_leave_id: int | None = None,
    department_draft: dict | None = None,
    employee_draft: dict | None = None,
    leave_draft: dict | None = None,
) -> bytes:
    notice_html = ""
    if message:
        notice_class = "notice-banner success" if success else "notice-banner"
        notice_html = f'<div class="{notice_class}">{html.escape(message)}</div>'

    month_start = _vacation_parse_month(month_value)
    month_value = _vacation_month_value(month_start)
    month_end = _vacation_month_bounds(month_start)[1]

    with _vacation_db_connection() as connection:
        departments = _vacation_fetch_departments(connection)
        employees = _vacation_fetch_employees(connection)
        leaves = _vacation_fetch_leaves_in_range(connection, month_start, month_end)
        edit_department = _vacation_fetch_department(connection, edit_department_id) if edit_department_id else None
        edit_employee = _vacation_fetch_employee(connection, edit_employee_id) if edit_employee_id else None
        edit_leave = _vacation_fetch_leave(connection, edit_leave_id) if edit_leave_id else None

    weeks, limit_day_count = _vacation_build_calendar(month_start, leaves)
    month_label = _vacation_month_label(month_start)
    prev_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, -1)))
    next_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, 1)))
    cancel_href = _vacation_route(month_value)
    current_view_url = _vacation_route(
        month_value,
        edit_department=edit_department_id,
        edit_employee=edit_employee_id,
    )

    department_state = {
        "id": str((department_draft or {}).get("id", edit_department["id"] if edit_department else "")),
        "name": str((department_draft or {}).get("name", edit_department["name"] if edit_department else "")),
        "max_absent": str((department_draft or {}).get("max_absent", edit_department["max_absent"] if edit_department else 1)),
    }
    employee_state = {
        "id": str((employee_draft or {}).get("id", edit_employee["id"] if edit_employee else "")),
        "name": str((employee_draft or {}).get("name", edit_employee["name"] if edit_employee else "")),
        "department_ids": [
            int(value)
            for value in (employee_draft or {}).get("department_ids", edit_employee["department_ids"] if edit_employee else [])
        ],
    }
    leave_state = {
        "id": str((leave_draft or {}).get("id", edit_leave["id"] if edit_leave else "")),
        "employee_id": str((leave_draft or {}).get("employee_id", edit_leave["employee_id"] if edit_leave else "")),
        "start_date": str((leave_draft or {}).get("start_date", edit_leave["start_date"] if edit_leave else _vacation_date_value(date.today()))),
        "end_date": str((leave_draft or {}).get("end_date", edit_leave["end_date"] if edit_leave else _vacation_date_value(date.today()))),
        "note": str((leave_draft or {}).get("note", edit_leave["note"] if edit_leave else "")),
    }
    leave_modal_should_open = edit_leave is not None or leave_draft is not None
    leave_modal_date = leave_state["start_date"] or _vacation_date_value(date.today())
    leave_modal_leave_id = leave_state["id"]

    weekday_html = "".join(f'<div class="vacation-weekday">{label}</div>' for label in VACATION_WEEKDAY_LABELS)
    calendar_html = weekday_html + "".join(_vacation_render_calendar_cell(cell) for week in weeks for cell in week)

    employee_list_html = "".join(_vacation_render_employee_item(item, month_value) for item in employees)
    employee_list_html = f'<ul class="vacation-list">{employee_list_html}</ul>' if employee_list_html else '<div class="vacation-empty">Először hozz létre legalább egy részleget, utána add fel a kollégákat.</div>'

    department_list_html = "".join(_vacation_render_department_item(item, month_value) for item in departments)
    department_list_html = f'<ul class="vacation-list">{department_list_html}</ul>' if department_list_html else '<div class="vacation-empty">Még nincs részleg felvéve.</div>'

    department_checks_html = "".join(
        f"""
        <label class="vacation-check">
          <input type="checkbox" name="department_ids" value="{department["id"]}"{" checked" if department["id"] in employee_state["department_ids"] else ""} />
          <span>{html.escape(department["name"])} · max. {department["max_absent"]} fő</span>
        </label>
        """
        for department in departments
    )
    if not department_checks_html:
        department_checks_html = '<div class="vacation-empty">Előbb hozz létre legalább egy részleget.</div>'

    employee_options_html = '<option value="">Válassz kollégát</option>' + "".join(
        f'<option value="{employee["id"]}"{" selected" if str(employee["id"]) == leave_state["employee_id"] else ""}>{html.escape(employee["name"])}</option>'
        for employee in employees
    )
    leave_payload_json = json.dumps(
        [
            {
                "id": item["id"],
                "employeeId": item["employee_id"],
                "employeeName": item["employee_name"],
                "startDate": item["start_date"],
                "endDate": item["end_date"],
                "note": item["note"],
                "departmentNames": item["department_names"],
            }
            for item in leaves
        ],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    employee_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#employee-form">Mégse</a>' if employee_state["id"] else ""
    department_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#department-form">Mégse</a>' if department_state["id"] else ""
    leave_modal_html = f"""
        <div class="vacation-modal-backdrop" data-vacation-modal aria-hidden="true" hidden>
          <article class="vacation-modal-card" role="dialog" aria-modal="true" aria-labelledby="vacation-modal-title">
            <button class="vacation-modal-close" type="button" data-vacation-close aria-label="Bezárás">×</button>
            <div class="vacation-modal-head">
              <h3 id="vacation-modal-title" data-vacation-modal-title>Új szabadság</h3>
              <p data-vacation-modal-subtitle>Válaszd ki a kollégát és a dátumot.</p>
            </div>

            <div class="vacation-modal-day-panel">
              <div class="vacation-modal-day-summary">
                <strong data-vacation-modal-day-label></strong>
                <span data-vacation-modal-day-meta></span>
              </div>
              <div class="vacation-modal-day-list" data-vacation-day-list></div>
            </div>

            <form class="vacation-form-grid is-split vacation-modal-form" method="post" action="{VACATION_CALENDAR_LEAVE_SAVE_ROUTE}">
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-leave-id-field />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <div class="vacation-field">
                <label for="modal-leave-employee">Kolléga</label>
                <select id="modal-leave-employee" name="employee_id"{" disabled" if not employees else ""} required>{employee_options_html}</select>
              </div>
              <div class="vacation-field">
                <label for="modal-leave-start">Kezdete</label>
                <input id="modal-leave-start" type="date" name="start_date" value="{html.escape(leave_state['start_date'])}" required />
              </div>
              <div class="vacation-field">
                <label for="modal-leave-end">Vége</label>
                <input id="modal-leave-end" type="date" name="end_date" value="{html.escape(leave_state['end_date'])}" required />
              </div>
              <div class="vacation-field is-full">
                <label for="modal-leave-note">Megjegyzés</label>
                <textarea id="modal-leave-note" name="note" placeholder="Opcionális">{html.escape(leave_state['note'])}</textarea>
              </div>
              <div class="vacation-form-actions is-full vacation-modal-actions">
                <button class="button button-secondary" type="submit" data-vacation-save{" disabled" if not employees else ""}>{'Mentés' if leave_state['id'] else 'Felvétel'}</button>
                <button class="knowledge-action" type="button" data-vacation-new{" hidden" if not employees else ""}>Új szabadság</button>
              </div>
            </form>

            <form class="vacation-modal-delete" method="post" action="{VACATION_CALENDAR_LEAVE_DELETE_ROUTE}" data-vacation-delete-form{" hidden" if not leave_state['id'] else ""}>
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-delete-id />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <button class="knowledge-action is-danger" type="submit">Szabadság törlése</button>
            </form>
          </article>
        </div>
    """

    employee_panel_html = f"""
      <article class="stack-card vacation-list-card" id="employee-form">
        <div class="vacation-list-head">
          <div>
            <h3>Kollégák</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {employee_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Kolléga szerkesztése' if employee_state['id'] else 'Új kolléga'}</h3>
          <p>{'Név és részlegek módosítása.' if employee_state['id'] else 'Név és részlegek megadása.'}</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE}">
          <input type="hidden" name="employee_id" value="{html.escape(employee_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="employee-name">Név</label>
            <input id="employee-name" type="text" name="name" value="{html.escape(employee_state['name'])}" placeholder="Kiss Péter" required />
          </div>
          <div class="vacation-field">
            <strong>Részlegek</strong>
            <div class="vacation-checkbox-grid">{department_checks_html}</div>
            <span class="vacation-field-hint">Minden kijelölt részleg limitjét figyeli.</span>
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if employee_state['id'] else 'Felvétel'}</button>
            {employee_cancel_html}
          </div>
        </form>
      </article>
    """
    department_panel_html = f"""
      <article class="stack-card vacation-list-card" id="department-form">
        <div class="vacation-list-head">
          <div>
            <h3>Részlegek</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {department_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Részleg szerkesztése' if department_state['id'] else 'Új részleg'}</h3>
          <p>Írd be, egyszerre hány fő lehet távol.</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE}">
          <input type="hidden" name="department_id" value="{html.escape(department_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="department-name">Részleg neve</label>
            <input id="department-name" type="text" name="name" value="{html.escape(department_state['name'])}" placeholder="Beszerzés" required />
          </div>
          <div class="vacation-field">
            <label for="department-max-absent">Max. szabadságon egyszerre</label>
            <input id="department-max-absent" type="number" min="0" name="max_absent" value="{html.escape(department_state['max_absent'])}" required />
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if department_state['id'] else 'Felvétel'}</button>
            {department_cancel_html}
          </div>
        </form>
      </article>
    """

    content_html = f"""
      <div
        class="vacation-shell"
        data-current-url="{html.escape(current_view_url)}"
        data-leave-modal-open="{'true' if leave_modal_should_open else 'false'}"
        data-leave-modal-date="{html.escape(leave_modal_date)}"
        data-leave-modal-id="{html.escape(leave_modal_leave_id)}"
      >
        <div class="vacation-calendar-stage" data-vacation-calendar-stage>
          <article class="stack-card vacation-calendar-card">
            <div class="vacation-toolbar">
              <div class="vacation-month-nav">
                <a class="knowledge-action" href="{prev_month_href}">Előző</a>
                <div class="vacation-month-title">{html.escape(month_label)}</div>
                <a class="knowledge-action" href="{next_month_href}">Következő</a>
              </div>

              <form class="vacation-month-form" method="get" action="{VACATION_CALENDAR_ROUTE}">
                <input type="month" name="month" value="{html.escape(month_value)}" />
                <button class="knowledge-action" type="submit">Ugrás</button>
              </form>
            </div>

            <div class="vacation-calendar-wrap">
              <div class="vacation-calendar-grid">{calendar_html}</div>
            </div>
          </article>
          {leave_modal_html}
        </div>

        <div class="vacation-section-grid">
          {employee_panel_html}
          {department_panel_html}
        </div>

        <script type="application/json" data-vacation-leaves>{leave_payload_json}</script>
      </div>
    """

    combined_content_html = content_html
    extra_script = f"""
<script>
(() => {{
  if (window.__vacationCalendarAsyncBound) return;
  window.__vacationCalendarAsyncBound = true;

  const ROOT_ID = "vacation-module-root";
  const ROUTE_PREFIX = "{VACATION_CALENDAR_ROUTE}";
  let requestToken = 0;
  const longDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }});
  const shortDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    month: "short",
    day: "numeric",
  }});

  const getRoot = () => document.getElementById(ROOT_ID);
  const getShell = () => getRoot()?.querySelector(".vacation-shell") || null;
  const getStage = () => getRoot()?.querySelector("[data-vacation-calendar-stage]") || null;
  const getModal = () => getRoot()?.querySelector("[data-vacation-modal]") || null;
  const shouldHandleUrl = (url) => url.origin === window.location.origin && url.pathname.startsWith(ROUTE_PREFIX);
  const escapeHtml = (value) =>
    String(value ? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[char] || char);
  const parseVacationDate = (value) => new Date(`${{value}}T12:00:00`);
  const formatLongDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : longDateFormatter.format(parsed);
  }};
  const formatShortDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : shortDateFormatter.format(parsed);
  }};
  const formatLeaveRange = (startDate, endDate) => {{
    if (!startDate || !endDate) return "";
    return startDate === endDate ? formatLongDate(startDate) : `${{formatShortDate(startDate)}} - ${{formatShortDate(endDate)}}`;
  }};
  const readVacationLeaves = () => {{
    const node = getRoot()?.querySelector("[data-vacation-leaves]");
    if (!node) return [];
    try {{
      const parsed = JSON.parse(node.textContent || "[]");
      return Array.isArray(parsed) ? parsed : [];
    }} catch (_error) {{
      return [];
    }}
  }};
  const getDayLeaves = (dayValue) =>
    readVacationLeaves()
      .filter((item) => item.startDate <= dayValue && item.endDate >= dayValue)
      .sort((left, right) => left.employeeName.localeCompare(right.employeeName, "hu"));
  const hasVacationEmployees = () => {{
    const select = getModal()?.querySelector('select[name="employee_id"]');
    if (!(select instanceof HTMLSelectElement)) return false;
    return Array.from(select.options).some((option) => option.value);
  }};
  const closeVacationModal = () => {{
    const modal = getModal();
    if (!modal) return;
    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("is-open");
    modal.hidden = true;
  }};
  const revealVacationStage = () => {{
    const stage = getStage();
    if (!stage) return;
    stage.scrollIntoView({{ behavior: "smooth", block: "start" }});
  }};
  const renderVacationDayEntries = (modal, dayValue, activeLeaveId) => {{
    const list = modal.querySelector("[data-vacation-day-list]");
    const dayLabel = modal.querySelector("[data-vacation-modal-day-label]");
    const dayMeta = modal.querySelector("[data-vacation-modal-day-meta]");
    if (!(list instanceof HTMLElement) || !(dayLabel instanceof HTMLElement) || !(dayMeta instanceof HTMLElement)) {{
      return;
    }}

    const entries = getDayLeaves(dayValue);
    dayLabel.textContent = formatLongDate(dayValue) || dayValue;
    dayMeta.textContent = entries.length
      ? `${{entries.length}} rögzített szabadság ezen a napon.`
      : "Erre a napra még nincs szabadság felvéve.";

    if (!entries.length) {{
      list.innerHTML = '<div class="vacation-empty">Erre a napra még nincs szabadság.</div>';
      return;
    }}

    list.innerHTML = entries
      .map((entry) => {{
        const departmentLabel = Array.isArray(entry.departmentNames) && entry.departmentNames.length
          ? entry.departmentNames.join(", ")
          : "Nincs részleg";
        const noteHtml = entry.note ? `<small>${{escapeHtml(entry.note)}}</small>` : "";
        return `
          <button
            class="vacation-modal-day-entry${{String(entry.id) === String(activeLeaveId) ? " is-active" : ""}}"
            type="button"
            data-vacation-leave-id="${{entry.id}}"
            data-vacation-day="${{dayValue}}"
          >
            <strong>${{escapeHtml(entry.employeeName)}}</strong>
            <span>${{escapeHtml(formatLeaveRange(entry.startDate, entry.endDate))}} · ${{escapeHtml(departmentLabel)}}</span>
            ${{noteHtml}}
          </button>
        `;
      }})
      .join("");
  }};
  const populateVacationModal = (options = {{}}) => {{
    const modal = getModal();
    if (!modal) return;

    const shell = getShell();
    const leaves = readVacationLeaves();
    const selectedLeave = options.leaveId ? leaves.find((item) => String(item.id) === String(options.leaveId)) || null : null;
    const dayValue = options.dayValue || selectedLeave?.startDate || shell?.dataset.leaveModalDate || "";
    const saveForm = modal.querySelector(".vacation-modal-form");
    const deleteForm = modal.querySelector("[data-vacation-delete-form]");
    const title = modal.querySelector("[data-vacation-modal-title]");
    const subtitle = modal.querySelector("[data-vacation-modal-subtitle]");
    const leaveIdField = modal.querySelector("[data-vacation-leave-id-field]");
    const deleteIdField = modal.querySelector("[data-vacation-delete-id]");
    const saveButton = modal.querySelector("[data-vacation-save]");
    const newButton = modal.querySelector("[data-vacation-new]");
    if (!(saveForm instanceof HTMLFormElement) || !(title instanceof HTMLElement) || !(subtitle instanceof HTMLElement)) {{
      return;
    }}

    modal.dataset.dayValue = dayValue;
    renderVacationDayEntries(modal, dayValue, selectedLeave?.id ? "");

    const employeeField = saveForm.querySelector('select[name="employee_id"]');
    const startField = saveForm.querySelector('input[name="start_date"]');
    const endField = saveForm.querySelector('input[name="end_date"]');
    const noteField = saveForm.querySelector('textarea[name="note"]');
    if (leaveIdField instanceof HTMLInputElement) {{
      leaveIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (deleteIdField instanceof HTMLInputElement) {{
      deleteIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.value = selectedLeave ? String(selectedLeave.employeeId) : "";
    }}
    if (startField instanceof HTMLInputElement) {{
      startField.value = selectedLeave ? selectedLeave.startDate : dayValue;
    }}
    if (endField instanceof HTMLInputElement) {{
      endField.value = selectedLeave ? selectedLeave.endDate : dayValue;
    }}
    if (noteField instanceof HTMLTextAreaElement) {{
      noteField.value = selectedLeave?.note || "";
    }}

    const canSave = hasVacationEmployees();
    if (saveButton instanceof HTMLButtonElement) {{
      saveButton.disabled = !canSave;
      saveButton.textContent = selectedLeave ? "Mentés" : "Felvétel";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.disabled = !canSave;
    }}

    if (selectedLeave) {{
      title.textContent = "Szabadság szerkesztése";
      subtitle.textContent = `${{selectedLeave.employeeName}} szabadsága. Módosíthatod vagy törölheted is.`;
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = false;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = !canSave;
      }}
    }} else {{
      title.textContent = "Új szabadság";
      subtitle.textContent = canSave
        ? "Kattints egy napra, és innen rögtön felveheted a szabadságot."
        : "Előbb vegyél fel legalább egy kollégát, utána rögzíthető szabadság.";
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = true;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = true;
      }}
    }}

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("is-open");
    modal.hidden = false;
    revealVacationStage();
  }};
  const syncVacationModalFromRoot = () => {{
    const shell = getShell();
    if (!shell) return;
    if (shell.dataset.leaveModalOpen === "true") {{
      populateVacationModal({{
        dayValue: shell.dataset.leaveModalDate || "",
        leaveId: shell.dataset.leaveModalId || "",
      }});
      return;
    }}
    closeVacationModal();
  }};

  const serializeForm = (form, submitter) => {{
    const formData = new FormData(form);
    if (submitter?.name) {{
      formData.append(submitter.name, submitter.value);
    }}
    const body = new URLSearchParams();
    for (const [key, value] of formData.entries()) {{
      body.append(key, String(value));
    }}
    return body;
  }};

  const updateHistory = (mode, nextRoot, fallbackUrl) => {{
    if (mode === "none") return;
    const nextUrl = nextRoot.querySelector(".vacation-shell")?.dataset.currentUrl || fallbackUrl;
    if (!nextUrl) return;
    if (mode === "replace") {{
      window.history.replaceState({{ vacationCalendar: true }}, "", nextUrl);
      return;
    }}
    window.history.pushState({{ vacationCalendar: true }}, "", nextUrl);
  }};

  const swapRoot = (htmlText, fallbackUrl, historyMode, hash) => {{
    const parser = new DOMParser();
    const documentNode = parser.parseFromString(htmlText, "text/html");
    const nextRoot = documentNode.getElementById(ROOT_ID);
    const currentRoot = getRoot();
    if (!nextRoot || !currentRoot) {{
      throw new Error("A szabadságnaptár nézet nem frissíthető részlegesen.");
    }}
    currentRoot.replaceWith(nextRoot);
    if (documentNode.title) {{
      document.title = documentNode.title;
    }}
    updateHistory(historyMode, nextRoot, fallbackUrl);
    syncVacationModalFromRoot();
    if (hash) {{
      window.requestAnimationFrame(() => {{
        const target = document.querySelector(hash);
        if (target) {{
          target.scrollIntoView({{ behavior: "smooth", block: "start" }});
        }}
      }});
    }}
  }};

  const fetchAndSwap = async (url, options = {{}}, historyMode = "push", hash = "") => {{
    const root = getRoot();
    if (!root) return;

    const requestId = ++requestToken;
    root.classList.add("is-loading");
    root.setAttribute("aria-busy", "true");

    try {{
      const response = await fetch(url, {{
        ...options,
        headers: {{
          Accept: "text/html",
          ...(options.headers || {{}}),
        }},
      }});
      const htmlText = await response.text();
      if (requestId !== requestToken) return;
      swapRoot(htmlText, typeof url === "string" ? url : url.toString(), historyMode, hash);
    }} catch (_error) {{
      window.location.assign(typeof url === "string" ? url : url.toString());
    }} finally {{
      const nextRoot = getRoot();
      if (nextRoot) {{
        nextRoot.classList.remove("is-loading");
        nextRoot.removeAttribute("aria-busy");
      }}
    }}
  }};

  document.addEventListener("click", (event) => {{
    const root = getRoot();
    const target = event.target instanceof Element ? event.target : null;
    if (!root || !target || !root.contains(target)) {{
      return;
    }}

    if (target === getModal()) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const closeButton = target.closest("[data-vacation-close]");
    if (closeButton) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const newButton = target.closest("[data-vacation-new]");
    if (newButton) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: getModal()?.dataset.dayValue || getShell()?.dataset.leaveModalDate || "" }});
      return;
    }}

    const leaveButton = target.closest("[data-vacation-leave-id]");
    if (leaveButton) {{
      event.preventDefault();
      populateVacationModal({{
        leaveId: leaveButton.getAttribute("data-vacation-leave-id") || "",
        dayValue:
          leaveButton.getAttribute("data-vacation-day") ||
          leaveButton.closest("[data-vacation-day]")?.getAttribute("data-vacation-day") ||
          "",
      }});
      return;
    }}

    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {{
      return;
    }}

    const dayCell = target.closest("[data-vacation-day]");
    if (dayCell) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
      return;
    }}

    const link = target.closest("a");
    if (!link || !root.contains(link)) {{
      return;
    }}
    if (link.target && link.target !== "_self") {{
      return;
    }}
    const url = new URL(link.href, window.location.href);
    if (!shouldHandleUrl(url)) {{
      return;
    }}
    event.preventDefault();
    const requestUrl = new URL(url.toString());
    requestUrl.hash = "";
    fetchAndSwap(requestUrl.toString(), {{ method: "GET" }}, "push", url.hash);
  }});

  document.addEventListener("keydown", (event) => {{
    const modal = getModal();
    if (event.key === "Escape" && modal?.classList.contains("is-open")) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const target = event.target instanceof Element ? event.target : null;
    const dayCell = target?.closest("[data-vacation-day]");
    if (!dayCell || !getRoot()?.contains(dayCell)) {{
      return;
    }}
    if (event.key === "Enter" || event.key === " ") {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
    }}
  }});

  document.addEventListener("submit", (event) => {{
    const root = getRoot();
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !root || !root.contains(form)) {{
      return;
    }}
    const actionUrl = new URL(form.action || window.location.href, window.location.href);
    if (!shouldHandleUrl(actionUrl)) {{
      return;
    }}

    event.preventDefault();
    const method = (form.method || "get").toUpperCase();
    const body = serializeForm(form, event.submitter);

    if (method === "GET") {{
      actionUrl.search = body.toString();
      fetchAndSwap(actionUrl.toString(), {{ method: "GET" }}, "push", actionUrl.hash);
      return;
    }}

    fetchAndSwap(actionUrl.toString(), {{ method: "POST", body }}, "replace");
  }});

  window.addEventListener("popstate", () => {{
    const root = getRoot();
    const currentUrl = new URL(window.location.href);
    if (!root || !shouldHandleUrl(currentUrl)) {{
      return;
    }}
    fetchAndSwap(currentUrl.toString(), {{ method: "GET" }}, "none", currentUrl.hash);
  }});

  syncVacationModalFromRoot();
}})();
</script>"""

    return _render_nettfront_layout(
        heading="Szabadságnaptár",
        lead="Részlegenként követhető szabadságkezelés egy helyen.",
        intro_label="Calendar",
        content_html=combined_content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
        module_root_id="vacation-module-root",
    )


def render_manufacturing_module(
    production_number: str = "",
    operation: str = "",
    message: str = "",
    success: bool = False,
) -> bytes:
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
    if requested_number and requested_number not in recent_numbers and not lightweight_operation_picker:
        combined_prefix = f"A {requested_number} gyártásban nem található meg mindkét szükséges PDF, ezért a legfrissebb használható gyártást nyitottam meg."
        message = f"{combined_prefix} {message}".strip() if message else combined_prefix
        success = False

    def is_complete_production(entry_number: str, operation_key: str) -> bool:
        operation_filter = _manufacturing_normalize_operation(operation_key)
        if not operation_filter:
            return False
        normalized_number = _manufacturing_normalize_number(entry_number)
        if not normalized_number:
            return False
        try:
            required_state_keys = _manufacturing_operation_state_keys(normalized_number, operation_filter)
            saved_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, normalized_number)
            view_state = _manufacturing_selection_state_payload(normalized_number, saved_state)
        except Exception:
            return False
        if not required_state_keys:
            return False
        for row_state_key in required_state_keys:
            state_value = str(view_state.get(row_state_key, "")).strip().lower()
            if state_value not in {"green", "done"}:
                return False
        return True

    recent_productions = [
        {
            **dict(entry),
            "is_complete": is_complete_production(str(entry.get("number", "")), selected_operation),
        }
        for entry in recent_productions
    ]

    bundle: dict | None = None
    selection_state: dict[str, str] = {}
    partial_quantity_state: dict[str, str] = {}
    combined_message = message
    combined_success = success

    if not selected_number:
        combined_message = "Nem találok használható gyártási mappát a beállított gyártási útvonalon."
        combined_success = False
    elif not lightweight_operation_picker:
        try:
            raw_bundle = _load_manufacturing_bundle_cached(selected_number)
            current_selection_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, selected_number)
            partial_quantity_state = load_partial_quantity_state(MANUFACTURING_RUNTIME_DIR, selected_number)
            bundle, selection_state = _manufacturing_view_bundle(
                raw_bundle,
                selected_number,
                current_selection_state,
                include_all_red_view=True,
            )
        except Exception as exc:
            combined_message = f"A gyártási papírok betöltése nem sikerült: {exc}"
            combined_success = False

    if bundle is None:
        bundle = {
            "production_number": selected_number,
            "folder": str(manufacturing_production_folder(selected_number)) if selected_number else "",
            "documents": [],
        }

    return render_manufacturing_page(
        route=MANUFACTURING_ROUTE,
        state_route=MANUFACTURING_STATE_ROUTE,
        partial_qty_route=MANUFACTURING_PARTIAL_QTY_ROUTE,
        report_ready_route=MANUFACTURING_REPORT_READY_ROUTE,
        selected_number=selected_number,
        operations=operations,
        selected_operation=selected_operation,
        recent_productions=recent_productions,
        bundle=bundle,
        selection_state=selection_state,
        partial_quantity_state=partial_quantity_state,
        message=combined_message,
        success=combined_success,
    )


def _matt_inventory_read_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _matt_inventory_write_meta(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _matt_inventory_saved_price_payload() -> tuple[str, bytes] | None:
    meta = _matt_inventory_read_meta(MATT_INVENTORY_PRICE_META_PATH)
    stored_name = str(meta.get("stored_name", "")).strip()
    original_name = str(meta.get("original_name", "")).strip() or stored_name
    if not stored_name:
        return None
    payload = matt_inventory_read_bytes_if_exists(MATT_INVENTORY_RUNTIME_DIR / stored_name)
    if payload is None:
        return None
    return original_name, payload


def _matt_inventory_saved_price_name() -> str:
    meta = _matt_inventory_read_meta(MATT_INVENTORY_PRICE_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _matt_inventory_saved_stock_name() -> str:
    meta = _matt_inventory_read_meta(MATT_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _matt_inventory_format_money(value: Decimal | float | int) -> str:
    number = float(value or 0)
    return f"{_format_eu_number(number, 0)} Ft"


def _matt_inventory_format_quantity(value: Decimal | float | int) -> str:
    number = float(value or 0)
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number))} db"
    return f"{_format_eu_number(number, 2)} db"


def _matt_inventory_format_generated_at(value: str) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    try:
        parsed = datetime.fromisoformat(clean_value)
    except ValueError:
        return clean_value
    return parsed.strftime("%Y.%m.%d. %H:%M")


def render_matt_inventory_form(message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    report = load_matt_inventory_report_from_path(MATT_INVENTORY_REPORT_PATH)
    saved_price_name = _matt_inventory_saved_price_name()
    saved_stock_name = _matt_inventory_saved_stock_name()

    report_html = """
      <section class="matt-report-card is-empty">
        <div class="matt-report-empty">
          <strong>Még nincs napi matt készletérték.</strong>
          <p>Töltsd fel a fix ártáblát és az aktuális készletfájlt, utána itt jelenik meg a kompakt összesítő.</p>
        </div>
      </section>
    """
    if report is not None:
        rows_html = "".join(
            f"""
              <tr>
                <td>
                  <strong>{html.escape(group.family)}</strong>
                </td>
                <td><span class="matt-color-cell">{html.escape(group.color)}</span></td>
                <td>{html.escape(_matt_inventory_format_quantity(group.quantity))}</td>
                <td class="value-cell">{html.escape(_matt_inventory_format_money(group.total_value))}</td>
              </tr>
            """
            for group in report.groups
        )
        missing_html = ""
        if report.missing_codes:
            preview = ", ".join(html.escape(code) for code in report.missing_codes[:6])
            extra = ""
            if len(report.missing_codes) > 6:
                extra = f" +{len(report.missing_codes) - 6} további"
            missing_html = f"""
              <div class="matt-warning">
                <strong>Hiányzó anyagköltség</strong>
                <p>Ezekhez a cikkszámokhoz nincs ár a fix táblában: {preview}{html.escape(extra)}</p>
              </div>
            """

        report_html = f"""
          <section class="matt-report-card">
            <div class="matt-report-head">
              <div class="matt-head-copy">
                <span class="matt-tag">Napi összesítő</span>
                <strong>Matt front raktárérték</strong>
                <p>Forrás: {html.escape(report.stock_source_name)} · Árforrás: {html.escape(report.price_source_name)}</p>
              </div>
              <div class="matt-head-side">
                <div class="matt-report-stamp">{html.escape(_matt_inventory_format_generated_at(report.generated_at))}</div>
                <div class="matt-head-caption">Napi készletből frissítve</div>
              </div>
            </div>

            <div class="matt-stats">
              <article>
                <span>Összérték</span>
                <strong>{html.escape(_matt_inventory_format_money(report.total_value))}</strong>
              </article>
              <article>
                <span>Összes darab</span>
                <strong>{html.escape(_matt_inventory_format_quantity(report.total_quantity))}</strong>
              </article>
              <article>
                <span>Színcsoport</span>
                <strong>{len(report.groups)}</strong>
              </article>
              <article>
                <span>Talált cikkszám</span>
                <strong>{report.matched_row_count}</strong>
              </article>
            </div>

            <div class="matt-thresholds">
              <article class="matt-threshold-card is-safety">
                <span>Biztonsági készlet felett</span>
                <strong>{report.safety_exceeded_count} front</strong>
                <p>Azok a frontok, ahol a bent maradt készlet már a biztonsági szint fölött van.</p>
              </article>
              <article class="matt-threshold-card is-storage">
                <span>Tárolható mennyiség felett</span>
                <strong>{report.storage_exceeded_count} front</strong>
                <p>Azok a frontok, amelyekből több van bent, mint a tárolható mennyiség.</p>
              </article>
              <article class="matt-threshold-card is-action">
                <span>Küszöbriport</span>
                <strong>Excel export</strong>
                <p>Két munkalapon adja le a biztonsági és tárolható mennyiség feletti frontokat.</p>
                <a class="button button-primary matt-download-button" href="{MATT_INVENTORY_DOWNLOAD_ROUTE}">Riport letöltése</a>
              </article>
            </div>

            <div class="matt-table-wrap">
              <table class="matt-table">
                <thead>
                  <tr>
                    <th>Modell</th>
                    <th>Szín</th>
                    <th>Darabszám</th>
                    <th>Raktárérték</th>
                  </tr>
                </thead>
                <tbody>
                  {rows_html}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Összesen</td>
                    <td>—</td>
                    <td>{html.escape(_matt_inventory_format_quantity(report.total_quantity))}</td>
                    <td class="value-cell">{html.escape(_matt_inventory_format_money(report.total_value))}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            {missing_html}
            <div class="matt-generated-by">generated by Divian-HUB</div>
          </section>
        """

    price_meta_html = ""
    if saved_price_name:
        price_meta_html = f'<div class="matt-meta-chip">Aktív fix árforrás: {html.escape(saved_price_name)}</div>'

    stock_meta_html = ""
    if saved_stock_name:
        stock_meta_html = f'<div class="matt-meta-chip">Utolsó készletállás: {html.escape(saved_stock_name)}</div>'

    content_html = f"""
      <div class="matt-shell">
        <section class="matt-upload-card">
          <div class="matt-upload-head">
            <div class="matt-copy">
              <span class="matt-tag">Napi készletérték</span>
              <strong>Matt front raktárérték.</strong>
              <p>Feltöltöd a fix anyagköltség táblát és a napi készletállást, a rendszer pedig front- és színszinten összesíti a bent maradt értéket.</p>
            </div>
            <div class="matt-visual" aria-hidden="true">
              <div class="matt-visual-pill">Fix ár</div>
              <div class="matt-visual-line"></div>
              <div class="matt-visual-pill">Napi állás</div>
              <div class="matt-visual-line"></div>
              <div class="matt-visual-pill is-strong">Érték</div>
            </div>
          </div>

          <div class="matt-meta-row">
            {price_meta_html}
            {stock_meta_html}
          </div>

          <form class="matt-upload-form" method="post" action="{MATT_INVENTORY_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="matt-upload-grid">
              <label class="matt-field">
                <span>Fix ártábla</span>
                <strong>Alkatrészszám + anyagköltség</strong>
                <input type="file" name="price_file" accept=".xlsx,.xlsm,.csv" />
                <small>Első alkalommal kötelező. Utána csak akkor töltsd újra, ha frissült.</small>
              </label>

              <label class="matt-field">
                <span>Napi készlet</span>
                <strong>Alkatrészszám + leírás + mennyiség + szín</strong>
                <input type="file" name="stock_file" accept=".xlsx,.xlsm,.csv" required />
                <small>Ezt elég naponta frissíteni az aktuális állással.</small>
              </label>
            </div>

            <div class="matt-action-row">
              <span class="inline-note">A fix árforrás megmarad, így napi használatra elég az aktuális készletfájlt feltölteni.</span>
              <button class="button button-primary matt-submit-button" type="submit">Érték kiszámítása</button>
            </div>
          </form>
        </section>

        {report_html}
      </div>
    """

    extra_script = """
<style>
  .matt-shell {
    display: grid;
    gap: 18px;
  }
  .matt-upload-card,
  .matt-report-card {
    position: relative;
    overflow: hidden;
    border-radius: 28px;
    border: 1px solid rgba(7, 16, 24, 0.08);
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    color: #0f172a;
    box-shadow: 0 20px 44px rgba(10, 18, 30, 0.08);
  }
  .matt-upload-card::before,
  .matt-report-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top right, rgba(15, 23, 42, 0.04), transparent 28%);
    pointer-events: none;
  }
  .matt-upload-card {
    padding: 22px;
  }
  .matt-upload-head {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
    gap: 20px;
  }
  .matt-copy {
    display: grid;
    gap: 10px;
    max-width: 660px;
  }
  .matt-copy strong,
  .matt-report-head strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.35rem, 2.8vw, 2rem);
    line-height: 1;
    color: #0f172a;
  }
  .matt-copy p,
  .matt-report-head p,
  .matt-field small,
  .matt-report-stamp,
  .matt-generated-by,
  .matt-warning p {
    margin: 0;
    color: #5b6777;
    line-height: 1.55;
  }
  .matt-tag {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    min-height: 28px;
    padding: 0 12px;
    border-radius: 999px;
    background: #eef2ff;
    color: #243b53;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-visual {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-visual-pill {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid rgba(15, 23, 42, 0.1);
    background: #ffffff;
    color: #334155;
    font-size: 0.82rem;
    font-weight: 700;
  }
  .matt-visual-pill.is-strong {
    background: #0f172a;
    border-color: #0f172a;
    color: #ffffff;
  }
  .matt-visual-line {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(15, 23, 42, 0.2), rgba(15, 23, 42, 0.55));
  }
  .matt-meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 16px;
  }
  .matt-meta-chip {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    background: #f8fafc;
    border: 1px solid rgba(15, 23, 42, 0.08);
    color: #475569;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .matt-upload-form {
    display: grid;
    gap: 14px;
    margin-top: 18px;
  }
  .matt-upload-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }
  .matt-field {
    display: grid;
    gap: 8px;
    padding: 16px 18px;
    border-radius: 20px;
    background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-field span {
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-field strong {
    color: #0f172a;
    font-size: 1rem;
  }
  .matt-field input[type="file"] {
    width: 100%;
    min-height: 54px;
    padding: 14px 16px;
    border-radius: 16px;
    border: 1px dashed rgba(15, 23, 42, 0.18);
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    color: #0f172a;
  }
  .matt-action-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 4px;
    padding: 6px 2px 0;
  }
  .matt-submit-button {
    min-width: 210px;
    min-height: 52px;
    border-radius: 16px;
    box-shadow: 0 14px 28px rgba(15, 23, 42, 0.18);
  }
  .matt-report-card {
    padding: 22px;
  }
  .matt-report-head {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
  }
  .matt-report-stamp {
    white-space: nowrap;
    font-size: 0.85rem;
    font-weight: 700;
  }
  .matt-head-copy {
    display: grid;
    gap: 10px;
  }
  .matt-head-side {
    display: grid;
    justify-items: end;
    gap: 6px;
    padding: 10px 14px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(15, 23, 42, 0.08);
  }
  .matt-head-caption {
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .matt-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .matt-stats article {
    padding: 16px;
    border-radius: 20px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: grid;
    gap: 6px;
  }
  .matt-stats span {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .matt-stats strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.18rem;
  }
  .matt-table-wrap {
    margin-top: 16px;
    overflow: auto;
    border-radius: 20px;
    border: 1px solid rgba(15, 23, 42, 0.08);
    background: #ffffff;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 640px;
  }
  .matt-table thead th {
    padding: 14px 18px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.08);
    background: #f8fafc;
    color: #475569;
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-align: left;
    white-space: nowrap;
  }
  .matt-table tbody td,
  .matt-table tfoot td {
    padding: 16px 18px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    color: #0f172a;
    vertical-align: middle;
  }
  .matt-table tbody tr:nth-child(2n) {
    background: rgba(248, 250, 252, 0.7);
  }
  .matt-table tbody td:first-child strong {
    display: block;
    font-size: 0.98rem;
  }
  .matt-color-cell {
    display: inline-block;
    color: #64748b;
    font-size: 0.92rem;
    font-weight: 600;
  }
  .matt-table .value-cell {
    font-weight: 800;
    white-space: nowrap;
  }
  .matt-table tfoot td {
    background: #f8fafc;
    font-weight: 800;
  }
  .matt-warning {
    margin-top: 14px;
    padding: 14px 16px;
    border-radius: 18px;
    border: 1px solid rgba(220, 38, 38, 0.16);
    background: rgba(254, 242, 242, 0.9);
  }
  .matt-warning strong {
    display: block;
    margin-bottom: 4px;
    color: #991b1b;
  }
  .matt-generated-by {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px dashed rgba(15, 23, 42, 0.12);
    text-align: right;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-thresholds {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;
  }
  .matt-threshold-card {
    padding: 14px 16px;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: grid;
    gap: 5px;
    align-content: start;
    min-height: 148px;
  }
  .matt-threshold-card span {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .matt-threshold-card strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.02rem;
  }
  .matt-threshold-card p {
    margin: 0;
    color: #64748b;
    line-height: 1.45;
    font-size: 0.86rem;
  }
  .matt-threshold-card.is-safety {
    background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  }
  .matt-threshold-card.is-storage {
    background: linear-gradient(180deg, #ffffff 0%, #fffaf5 100%);
  }
  .matt-threshold-card.is-action {
    background: linear-gradient(180deg, #0f172a 0%, #162033 100%);
    border-color: rgba(15, 23, 42, 0.55);
  }
  .matt-threshold-card.is-action span,
  .matt-threshold-card.is-action strong,
  .matt-threshold-card.is-action p {
    color: #ffffff;
  }
  .matt-download-button {
    min-height: 50px;
    width: 100%;
    justify-content: center;
    margin-top: 10px;
    border-radius: 14px;
    box-shadow: 0 16px 28px rgba(15, 23, 42, 0.18);
  }
  .matt-report-card.is-empty {
    padding: 32px 24px;
  }
  .matt-report-empty {
    display: grid;
    gap: 8px;
  }
  .matt-report-empty strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.2rem;
  }
  @media (max-width: 900px) {
    .matt-upload-head,
    .matt-report-head {
      grid-template-columns: minmax(0, 1fr);
      display: grid;
    }
    .matt-upload-grid,
    .matt-thresholds {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-visual {
      flex-wrap: wrap;
      width: fit-content;
    }
    .matt-stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .matt-head-side {
      justify-items: start;
    }
  }
  @media (max-width: 640px) {
    .matt-upload-card,
    .matt-report-card {
      border-radius: 22px;
    }
    .matt-upload-card {
      padding: 18px;
    }
    .matt-report-card {
      padding: 18px;
    }
    .matt-stats {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-upload-grid {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-action-row .button {
      width: 100%;
    }
    .matt-download-button {
      width: 100%;
      justify-content: center;
    }
    .matt-submit-button {
      min-width: 0;
    }
  }
</style>
"""

    return _render_nettfront_layout(
        heading="Napi matt front készletérték",
        lead="Fix árforrásból és napi készletállásból kiszámolt, kompakt raktárérték összesítő.",
        intro_label="Value snapshot",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def _front_inventory_saved_stock_name() -> str:
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _front_inventory_saved_check_report_name() -> str:
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_CHECK_REPORT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _front_inventory_saved_insight_meta() -> dict:
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_INSIGHT_META_PATH)
    return meta if isinstance(meta, dict) else {}


def _front_inventory_saved_insight_workbook_name() -> str:
    return str(_front_inventory_saved_insight_meta().get("workbook_name", "")).strip()


def _front_inventory_saved_insight_script_name() -> str:
    return str(_front_inventory_saved_insight_meta().get("script_name", "")).strip()


def _front_inventory_clear_generated_artifacts() -> None:
    for path in (
        FRONT_INVENTORY_CHECK_REPORT_PATH,
        FRONT_INVENTORY_CHECK_REPORT_META_PATH,
        FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH,
        FRONT_INVENTORY_INSIGHT_SCRIPT_PATH,
        FRONT_INVENTORY_INSIGHT_META_PATH,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _front_inventory_store_insight_artifacts(session: dict) -> str:
    insight_artifacts = build_front_inventory_insight_artifacts(session)
    workbook_body = insight_artifacts.get("workbook")
    script_body = insight_artifacts.get("script")
    if not isinstance(workbook_body, (bytes, bytearray)) or not isinstance(script_body, (bytes, bytearray)):
        raise ValueError("Az inSight export ures maradt.")

    FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.write_bytes(bytes(workbook_body))
    FRONT_INVENTORY_INSIGHT_SCRIPT_PATH.write_bytes(bytes(script_body))
    missing_parts = list(insight_artifacts.get("missing_parts", []) or [])
    _matt_inventory_write_meta(
        FRONT_INVENTORY_INSIGHT_META_PATH,
        {
            "workbook_name": str(insight_artifacts.get("workbook_name", "")).strip(),
            "script_name": str(insight_artifacts.get("script_name", "")).strip(),
            "row_count": int(insight_artifacts.get("row_count", 0) or 0),
            "matched_count": int(insight_artifacts.get("matched_count", 0) or 0),
            "missing_count": len(missing_parts),
            "template_name": str(insight_artifacts.get("template_name", "")).strip(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    if missing_parts:
        return f" {len(missing_parts)} alkatrész nem szerepel a mintában, ezeket külön munkalapra tettem."
    return ""


def _front_inventory_ensure_insight_artifacts(session: dict | None) -> None:
    if session is None or str(session.get("phase")) != "finalized":
        return
    if FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.exists() and FRONT_INVENTORY_INSIGHT_SCRIPT_PATH.exists():
        return
    try:
        _front_inventory_store_insight_artifacts(session)
    except Exception:
        return


def _material_inventory_saved_stock_name() -> str:
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _material_inventory_saved_insight_name() -> str:
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _material_inventory_saved_summary_name() -> str:
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _material_inventory_clear_generated_artifacts() -> None:
    for path in (
        MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH,
        MATERIAL_INVENTORY_INSIGHT_META_PATH,
        MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH,
        MATERIAL_INVENTORY_SUMMARY_META_PATH,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _material_inventory_store_exports(session: dict) -> None:
    insight_body, insight_name, insight_count = build_material_inventory_insight_workbook(session)
    summary_body, summary_name, summary_count = build_material_inventory_summary_workbook(session)
    MATERIAL_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH.write_bytes(insight_body)
    MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH.write_bytes(summary_body)
    now_value = datetime.now().isoformat(timespec="seconds")
    _matt_inventory_write_meta(
        MATERIAL_INVENTORY_INSIGHT_META_PATH,
        {"download_name": insight_name, "row_count": insight_count, "updated_at": now_value},
    )
    _matt_inventory_write_meta(
        MATERIAL_INVENTORY_SUMMARY_META_PATH,
        {"download_name": summary_name, "row_count": summary_count, "updated_at": now_value},
    )


def _material_inventory_hydrate_book_qty(session: dict | None) -> bool:
    if not isinstance(session, dict):
        return False
    rows = session.get("rows")
    if not isinstance(rows, list) or not rows:
        return False
    if any(str(row.get("book_qty", "")).strip() for row in rows if isinstance(row, dict)):
        return False

    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_STOCK_META_PATH)
    stored_name = str(meta.get("stored_name", "")).strip()
    original_name = str(meta.get("original_name", "")).strip() or stored_name
    if not stored_name:
        return False
    stock_path = MATERIAL_INVENTORY_RUNTIME_DIR / stored_name
    if not stock_path.is_file():
        return False

    try:
        source_session = build_material_inventory_session(original_name, stock_path.read_bytes())
    except Exception:
        return False

    book_by_key: dict[tuple[str, str], str] = {}
    for source_row in source_session.get("rows", []):
        if not isinstance(source_row, dict):
            continue
        key = (str(source_row.get("part_number", "")), str(source_row.get("icg_code", "")))
        book_by_key[key] = str(source_row.get("book_qty", "") or "")

    changed = False
    for row in rows:
        if not isinstance(row, dict) or str(row.get("book_qty", "")).strip():
            continue
        key = (str(row.get("part_number", "")), str(row.get("icg_code", "")))
        book_qty = book_by_key.get(key, "")
        if book_qty:
            row["book_qty"] = book_qty
            changed = True
    return changed


def _semifinished_inventory_saved_stock_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _semifinished_inventory_saved_insight_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_inventory_saved_summary_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_inventory_clear_generated_artifacts() -> None:
    for path in (
        SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH,
        SEMIFINISHED_INVENTORY_INSIGHT_META_PATH,
        SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH,
        SEMIFINISHED_INVENTORY_SUMMARY_META_PATH,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _semifinished_inventory_store_exports(session: dict) -> None:
    insight_body, insight_name, insight_count = build_material_inventory_insight_workbook(session)
    summary_body, summary_name, summary_count = build_material_inventory_summary_workbook(session)
    SEMIFINISHED_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH.write_bytes(insight_body)
    SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH.write_bytes(summary_body)
    now_value = datetime.now().isoformat(timespec="seconds")
    _matt_inventory_write_meta(
        SEMIFINISHED_INVENTORY_INSIGHT_META_PATH,
        {"download_name": insight_name, "row_count": insight_count, "updated_at": now_value},
    )
    _matt_inventory_write_meta(
        SEMIFINISHED_INVENTORY_SUMMARY_META_PATH,
        {"download_name": summary_name, "row_count": summary_count, "updated_at": now_value},
    )


def _semifinished_front_inventory_saved_stock_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _semifinished_front_inventory_saved_insight_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_front_inventory_saved_summary_name() -> str:
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_front_inventory_clear_generated_artifacts() -> None:
    for path in (
        SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH,
        SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH,
        SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH,
        SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _semifinished_front_inventory_store_exports(session: dict) -> None:
    insight_body, insight_name, insight_count = build_material_inventory_insight_workbook(session)
    summary_body, summary_name, summary_count = build_material_inventory_summary_workbook(session)
    SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.write_bytes(insight_body)
    SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH.write_bytes(summary_body)
    now_value = datetime.now().isoformat(timespec="seconds")
    _matt_inventory_write_meta(
        SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH,
        {"download_name": insight_name, "row_count": insight_count, "updated_at": now_value},
    )
    _matt_inventory_write_meta(
        SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH,
        {"download_name": summary_name, "row_count": summary_count, "updated_at": now_value},
    )


def _material_inventory_normalize_view(value: str) -> str:
    return "leltar" if str(value or "").strip().lower() == "leltar" else "admin"


def render_material_inventory_form(
    message: str = "",
    success: bool = False,
    selected_category: str = "",
    view_mode: str = "admin",
    auto_download_href: str = "",
    inventory_kind: str = "material",
) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="matinv-notice{extra_class}">{html.escape(message)}</div>'

    clean_inventory_kind = str(inventory_kind).strip().lower()
    is_semifinished = clean_inventory_kind in {"semifinished", "semifinished_front"}
    is_semifinished_front = clean_inventory_kind == "semifinished_front"
    if is_semifinished_front:
        route = SEMIFINISHED_FRONT_INVENTORY_ROUTE
        process_route = SEMIFINISHED_FRONT_INVENTORY_PROCESS_ROUTE
        state_route = SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE
        finalize_route = SEMIFINISHED_FRONT_INVENTORY_FINALIZE_ROUTE
        insight_download_route = SEMIFINISHED_FRONT_INVENTORY_INSIGHT_DOWNLOAD_ROUTE
        summary_download_route = SEMIFINISHED_FRONT_INVENTORY_SUMMARY_DOWNLOAD_ROUTE
        session_path = SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH
        saved_stock_name = _semifinished_front_inventory_saved_stock_name()
        saved_insight_name = _semifinished_front_inventory_saved_insight_name()
        saved_summary_name = _semifinished_front_inventory_saved_summary_name()
    elif is_semifinished:
        route = SEMIFINISHED_INVENTORY_ROUTE
        process_route = SEMIFINISHED_INVENTORY_PROCESS_ROUTE
        state_route = SEMIFINISHED_INVENTORY_STATE_ROUTE
        finalize_route = SEMIFINISHED_INVENTORY_FINALIZE_ROUTE
        insight_download_route = SEMIFINISHED_INVENTORY_INSIGHT_DOWNLOAD_ROUTE
        summary_download_route = SEMIFINISHED_INVENTORY_SUMMARY_DOWNLOAD_ROUTE
        session_path = SEMIFINISHED_INVENTORY_SESSION_PATH
        saved_stock_name = _semifinished_inventory_saved_stock_name()
        saved_insight_name = _semifinished_inventory_saved_insight_name()
        saved_summary_name = _semifinished_inventory_saved_summary_name()
    else:
        route = MATERIAL_INVENTORY_ROUTE
        process_route = MATERIAL_INVENTORY_PROCESS_ROUTE
        state_route = MATERIAL_INVENTORY_STATE_ROUTE
        finalize_route = MATERIAL_INVENTORY_FINALIZE_ROUTE
        insight_download_route = MATERIAL_INVENTORY_INSIGHT_DOWNLOAD_ROUTE
        summary_download_route = MATERIAL_INVENTORY_SUMMARY_DOWNLOAD_ROUTE
        session_path = MATERIAL_INVENTORY_SESSION_PATH
        saved_stock_name = _material_inventory_saved_stock_name()
        saved_insight_name = _material_inventory_saved_insight_name()
        saved_summary_name = _material_inventory_saved_summary_name()
    session = load_material_inventory_session_from_path(session_path)
    if not is_semifinished and _material_inventory_hydrate_book_qty(session):
        save_material_inventory_session_to_path(MATERIAL_INVENTORY_SESSION_PATH, session)
    active_view = _material_inventory_normalize_view(view_mode)
    color_page_title = "Félkész front leltár" if is_semifinished_front else "Félkész raktár leltár"
    color_board_title = "Félkész front számolás" if is_semifinished_front else "Félkész raktár számolás"
    color_upload_title = "Félkész front leltár." if is_semifinished_front else "Félkész raktár leltár."
    page_title = color_page_title if is_semifinished else "Anyagraktár leltár"
    board_title = color_board_title if is_semifinished else "Anyagraktár számolás"
    upload_title = color_upload_title if is_semifinished else "Anyagraktár leltár."
    required_columns = "Alkatr.-szám · Alkatr.-leírás · SZIN · SZIN.Desc" if is_semifinished else "Alkatr.-szám · Alkatr.-leírás · Könyvelési mennyiség · ICG kód"
    category_help = "Csak a számoláshoz szükséges felület. Szín szerint válassz kategóriát." if is_semifinished else "Csak a számoláshoz szükséges felület. ICG kód szerint válassz kategóriát."
    upload_copy = "Feltöltés után a leltár szín szerint szétbontva jelenik meg. A véglegesítés InSight listát és összesítőt készít." if is_semifinished else "Feltöltés után a leltár ICG kód szerint szétbontva jelenik meg. A véglegesítés InSight listát és összesítőt készít."
    color_upload_button = "Félkész front leltár indítása" if is_semifinished_front else "Félkész raktár leltár indítása"
    color_empty_copy = "Töltsd fel a leltározandó félkész front listát, utána színek szerint külön kategóriákban lehet számolni." if is_semifinished_front else "Töltsd fel a leltározandó félkész listát, utána színek szerint külön kategóriákban lehet számolni."
    upload_button = color_upload_button if is_semifinished else "Anyagraktár leltár indítása"
    empty_copy = color_empty_copy if is_semifinished else "Töltsd fel a leltározandó anyaglistát, utána ICG kód szerint külön kategóriákban lehet számolni."
    admin_href = route
    inventory_href = route if session is None else f"{route}?view=leltar"
    if active_view == "leltar":
        view_switch_html = """
          <div class="matinv-view-switch is-worker-only">
            <span class="matinv-view-tab is-active">Leltár nézet</span>
          </div>
        """
    else:
        view_switch_html = f"""
          <div class="matinv-view-switch">
            <a class="matinv-view-tab is-active" href="{admin_href}">Kezelő</a>
            <a class="matinv-view-tab" href="{inventory_href}">Leltár nézet</a>
          </div>
        """

    stock_meta_html = ""
    if saved_stock_name:
        stock_meta_html = f'<span class="matinv-meta-chip">Aktív forrás: {html.escape(saved_stock_name)}</span>'

    admin_session_html = ""
    inventory_html = f"""
      <section class="matinv-board is-empty">
        <strong>Még nincs aktív {html.escape(page_title.lower())}.</strong>
        <p>{empty_copy}</p>
      </section>
    """
    if session:
        view_model = build_material_inventory_view_model(session, selected_category)
        categories_html = "".join(
            f"""
              <a class="matinv-chip{' is-complete' if item.get('complete') else ''}{' is-active' if item['key'] == view_model['selected_category'] else ''}"
                 href="{route}?view=leltar&category={urllib.parse.quote(item['key'])}">
                <span>{html.escape(str(item['label']))}</span>
                <strong>{int(item['count'])}</strong>
              </a>
            """
            for item in view_model["categories"]
        )
        finalized = bool(view_model.get("finalized"))
        rows_html = "".join(
            f"""
              <tr class="matinv-row{' is-counted' if str(row.get('input_qty', '')).strip() or finalized else ''}">
                <td class="is-description">{html.escape(str(row.get('description', '')))}</td>
                {f'<td class="is-color">{html.escape(str(row.get("icg_code", "") or "-"))}</td>' if is_semifinished else ''}
                {'' if is_semifinished else f'<td class="is-book-qty">{html.escape(str(row.get("book_qty", "") or "-"))}</td>'}
                <td class="is-total"><span data-matinv-total>{html.escape(str(row.get('counted_qty', row.get('input_qty', '')) or '0'))}</span></td>
                <td class="is-adjust">
                  <div class="matinv-adjust">
                    <label><span>+</span><input class="matinv-input" data-matinv-input data-mode="add" data-row-id="{html.escape(str(row.get('row_id', '')))}" inputmode="decimal" placeholder="0" {'disabled' if finalized else ''} /></label>
                    <label><span>-</span><input class="matinv-input" data-matinv-input data-mode="subtract" data-row-id="{html.escape(str(row.get('row_id', '')))}" inputmode="decimal" placeholder="0" {'disabled' if finalized else ''} /></label>
                    <label><span>=</span><input class="matinv-input" data-matinv-input data-mode="set" data-row-id="{html.escape(str(row.get('row_id', '')))}" inputmode="decimal" value="{html.escape(str(row.get('counted_qty', row.get('input_qty', '')) or ''))}" placeholder="Felülír" {'disabled' if finalized else ''} /></label>
                  </div>
                </td>
              </tr>
            """
            for row in view_model["visible_rows"]
        )
        if not rows_html:
            rows_html = '<tr><td colspan="4" class="matinv-empty-row">Ebben a kategóriában nincs tétel.</td></tr>'

        download_html = ""
        if finalized:
            download_html = f"""
              <div class="matinv-downloads">
                {'<a class="button button-secondary" href="' + insight_download_route + '">InSight lista</a>' if saved_insight_name else ''}
                {'<a class="button button-secondary" href="' + summary_download_route + '">Összesítő</a>' if saved_summary_name else ''}
              </div>
            """

        finalize_html = ""
        if finalized:
            finalize_html = f"""
              <div class="matinv-callout is-done">
                <strong>Leltár lezárva</strong>
                <span>Lezárás ideje: {html.escape(_front_inventory_format_timestamp(str(view_model.get('finalized_at', ''))))}</span>
              </div>
            """
        else:
            finalize_html = f"""
              <form class="matinv-finalize-form" method="post" action="{finalize_route}">
                <button class="button button-primary" type="submit">Véglegesítés és export</button>
              </form>
            """

        admin_session_html = f"""
          <section class="matinv-board matinv-admin-board">
            <div class="matinv-board-head">
              <div>
                <span class="matinv-tag">Kezelő felület</span>
                <strong>Aktív anyagraktár leltár</strong>
                <p>Forrás: {html.escape(str(session.get('source_name', '')))} · Kitöltve: {int(view_model['counted_rows'])} · Hiányzik: {int(view_model['missing_rows'])}</p>
              </div>
              <div class="matinv-board-stamp">{html.escape(str(view_model.get('phase_label', 'Számlálás')))}</div>
            </div>
            <div class="matinv-stats">
              <article><span>Összes tétel</span><strong>{int(view_model['total_rows'])}</strong></article>
              <article><span>{'Szín kategória' if is_semifinished else 'ICG kategória'}</span><strong>{int(view_model['category_count'])}</strong></article>
              <article><span>Kitöltve</span><strong>{int(view_model['counted_rows'])}</strong></article>
              <article><span>Hiányzik</span><strong>{int(view_model['missing_rows'])}</strong></article>
            </div>
            <div class="matinv-admin-actions">
              <a class="button button-secondary" href="{inventory_href}">Leltár nézet megnyitása</a>
              {download_html}
              {finalize_html}
            </div>
          </section>
        """

        inventory_html = f"""
          <section class="matinv-board{' is-semifinished' if is_semifinished else ''}" data-material-inventory-root data-state-route="{state_route}">
            <div class="matinv-board-head">
              <div>
                <span class="matinv-tag">Leltár nézet</span>
                <strong>{board_title}</strong>
                <p>{category_help}</p>
              </div>
              <div class="matinv-board-stamp">{html.escape(str(view_model.get('phase_label', 'Számlálás')))}</div>
            </div>
            <div class="matinv-category-row">{categories_html}</div>
            <label class="matinv-search">
              <span>{'Keresés leírás és szín alapján' if is_semifinished else 'Keresés leírás alapján'}</span>
              <input type="search" data-matinv-search placeholder="{'Írj be részletet a leírásból vagy színből...' if is_semifinished else 'Írj be részletet a leírásból...'}" autocomplete="off" />
            </label>
            <div class="matinv-table-wrap">
              <table class="matinv-table">
                <colgroup>
                  <col class="matinv-col-description" />
                  {f'<col class="matinv-col-color" />' if is_semifinished else ''}
                  {'' if is_semifinished else '<col class="matinv-col-book" />'}
                  <col class="matinv-col-total" />
                  <col class="matinv-col-adjust" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Leírás</th>
                    {f'<th>Szín</th>' if is_semifinished else ''}
                    {'' if is_semifinished else '<th>Könyvelési menny.</th>'}
                    <th>Összesen</th>
                    <th>Korrekció</th>
                  </tr>
                </thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
          </section>
        """

    upload_html = f"""
      <section class="matinv-upload-card">
        <div class="matinv-upload-head">
          <div>
            <span class="matinv-tag">Új modul</span>
            <strong>{upload_title}</strong>
            <p>{upload_copy}</p>
          </div>
          <div class="matinv-upload-note">
            <b>Szükséges oszlopok</b>
            <span>{required_columns}</span>
          </div>
        </div>
        <div class="matinv-meta-row">{stock_meta_html}</div>
        <form class="matinv-upload-form" method="post" action="{process_route}" enctype="multipart/form-data">
          <label class="matinv-field">
            <span>Leltározandó lista</span>
            <input type="file" name="stock_file" accept=".xlsx,.xlsm,.csv" required />
          </label>
          <button class="button button-primary" type="submit">{upload_button}</button>
        </form>
      </section>
    """

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | {page_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
  <style>
    :root {{ --text:#0f172a; --muted:#64748b; --line:#d8e0ea; --accent:#0c8d57; --accent2:#12a566; --bg:#eef3f7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; background:
      radial-gradient(circle at 8% 4%, rgba(18,165,102,.16), transparent 28rem),
      linear-gradient(180deg,#f8fbfc 0%, var(--bg) 42%, #e9f0f5 100%);
      color:var(--text); font-family:Manrope, sans-serif; }}
    .matinv-shell {{ width:min(1280px, calc(100% - 28px)); margin:16px auto 42px; display:grid; gap:16px; }}
    .matinv-top {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:22px 24px; border-radius:28px; background:linear-gradient(135deg,#fff 0%,#f7fffb 100%); box-shadow:0 22px 55px rgba(15,23,42,.10); border:1px solid rgba(255,255,255,.8); }}
    .matinv-top h1 {{ margin:6px 0 0; font:800 1.55rem/1.05 "Space Grotesk", sans-serif; letter-spacing:-.03em; }}
    .matinv-top a {{ display:inline-flex; align-items:center; min-height:42px; padding:0 15px; border-radius:999px; color:#0f172a; text-decoration:none; font-weight:900; background:#fff; border:1px solid var(--line); }}
    .matinv-upload-card,.matinv-board {{ position:relative; overflow:hidden; border:1px solid rgba(15,23,42,.07); border-radius:28px; background:rgba(255,255,255,.94); box-shadow:0 24px 58px rgba(15,23,42,.09); }}
    .matinv-upload-card::before,.matinv-board::before {{ content:""; position:absolute; inset:0 0 auto 0; height:5px; background:linear-gradient(90deg,var(--accent2),#86efac,#dbeafe); }}
    .matinv-view-switch {{ display:flex; gap:7px; padding:7px; border-radius:999px; background:rgba(255,255,255,.82); border:1px solid rgba(203,213,225,.9); box-shadow:0 14px 30px rgba(15,23,42,.08); width:max-content; backdrop-filter:blur(10px); }}
    .matinv-view-tab {{ display:inline-flex; align-items:center; justify-content:center; min-height:40px; padding:0 18px; border-radius:999px; color:var(--text); text-decoration:none; font-weight:900; transition:.18s ease; }}
    .matinv-view-tab:hover {{ background:#f1f5f9; }}
    .matinv-view-switch.is-worker-only .matinv-view-tab:hover {{ background:#0f172a; }}
    .matinv-view-tab.is-active {{ background:#0f172a; color:#fff; box-shadow:0 10px 22px rgba(15,23,42,.22); }}
    .matinv-upload-card {{ padding:24px 20px 20px; }}
    .matinv-upload-head,.matinv-board-head {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:start; }}
    .matinv-upload-head strong,.matinv-board-head strong {{ display:block; margin-top:8px; font:800 1.45rem/1.1 "Space Grotesk", sans-serif; }}
    .matinv-upload-head p,.matinv-board-head p,.matinv-callout span,.matinv-board.is-empty p {{ margin:7px 0 0; color:var(--muted); line-height:1.55; }}
    .matinv-tag,.matinv-meta-chip {{ display:inline-flex; align-items:center; min-height:28px; padding:0 11px; border-radius:999px; background:#edf7f2; color:#0c7650; font-size:.75rem; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }}
    .matinv-upload-note {{ display:grid; gap:5px; min-width:290px; padding:16px 18px; border-radius:20px; background:linear-gradient(180deg,#f8fafc,#eef7f3); border:1px solid #cfe0d8; color:var(--muted); box-shadow:inset 0 1px 0 rgba(255,255,255,.8); }}
    .matinv-upload-note b {{ color:var(--text); font-size:1rem; }}
    .matinv-meta-row {{ margin-top:14px; display:flex; flex-wrap:wrap; gap:10px; }}
    .matinv-upload-form {{ margin-top:16px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:end; }}
    .matinv-field {{ display:grid; gap:8px; font-weight:800; }}
    .matinv-field input {{ min-height:52px; padding:12px 14px; border:1px solid #cbd8e4; border-radius:18px; background:#f8fafc; font-weight:800; }}
    .matinv-field input::file-selector-button {{ margin-right:12px; border:0; border-radius:999px; padding:10px 14px; background:#0f172a; color:#fff; font-weight:900; cursor:pointer; }}
    .button {{ display:inline-flex; align-items:center; justify-content:center; min-height:50px; padding:0 20px; border-radius:999px; border:1px solid var(--line); font-weight:900; text-decoration:none; cursor:pointer; transition:.18s ease; }}
    .button:hover {{ transform:translateY(-1px); box-shadow:0 12px 24px rgba(15,23,42,.10); }}
    .button-primary {{ background:linear-gradient(180deg,var(--accent2),var(--accent)); color:#fff; border-color:transparent; box-shadow:0 12px 24px rgba(12,141,87,.20); }}
    .button-secondary {{ background:#fff; color:var(--text); }}
    .matinv-board {{ padding:20px 16px 16px; overflow:hidden; }}
    .matinv-board.is-empty {{ padding:28px; }}
    .matinv-category-row {{ margin-top:14px; display:flex; gap:8px; overflow-x:auto; padding-bottom:10px; }}
    .matinv-chip {{ flex:0 0 auto; display:inline-flex; align-items:center; gap:8px; min-height:42px; padding:0 13px; border-radius:999px; border:1px solid var(--line); background:#fff; color:var(--text); text-decoration:none; font-weight:800; }}
    .matinv-chip strong {{ color:var(--muted); }}
    .matinv-chip.is-active {{ border-color:#0f172a; box-shadow:inset 0 0 0 1px #0f172a; }}
    .matinv-chip.is-complete {{ background:#ecfdf5; border-color:rgba(22,163,74,.35); color:#047857; }}
    .matinv-search {{ margin-top:10px; display:grid; grid-template-columns:auto minmax(220px, 420px); align-items:center; justify-content:start; gap:10px; color:#475569; font-size:.78rem; font-weight:900; text-transform:uppercase; letter-spacing:.04em; }}
    .matinv-search input {{ min-height:42px; width:100%; padding:0 15px; border:1px solid var(--line); border-radius:999px; background:#fff; color:var(--text); font:800 .95rem/1 Manrope, sans-serif; text-transform:none; letter-spacing:0; }}
    .matinv-search input:focus {{ outline:none; border-color:#0f172a; box-shadow:0 0 0 3px rgba(15,23,42,.08); }}
    .matinv-callout {{ margin-top:4px; display:flex; justify-content:space-between; align-items:center; gap:12px; padding:12px 14px; border-radius:16px; background:#f8fafc; border:1px solid var(--line); }}
    .matinv-callout.is-done {{ background:#ecfdf5; border-color:rgba(22,163,74,.32); }}
    .matinv-finalize-form {{ margin-top:4px; display:flex; justify-content:flex-end; }}
    .matinv-downloads {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }}
    .matinv-board-stamp {{ display:inline-flex; align-items:center; min-height:42px; padding:0 15px; border-radius:999px; background:#f8fafc; border:1px solid var(--line); color:#475569; font-weight:900; }}
    .matinv-stats {{ margin-top:16px; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
    .matinv-stats article {{ padding:16px; border-radius:20px; background:linear-gradient(180deg,#fbfdff,#f3f7fb); border:1px solid #d7e1eb; box-shadow:inset 0 1px 0 rgba(255,255,255,.9); }}
    .matinv-stats span {{ display:block; color:var(--muted); font-size:.78rem; font-weight:800; text-transform:uppercase; }}
    .matinv-stats strong {{ display:block; margin-top:6px; font:800 1.45rem/1 "Space Grotesk", sans-serif; }}
    .matinv-admin-actions {{ margin-top:20px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:flex-end; padding-top:16px; border-top:1px solid rgba(15,23,42,.08); }}
    .matinv-admin-actions form {{ margin:0; }}
    .matinv-table-wrap {{ margin-top:14px; overflow:hidden; border:1px solid var(--line); border-radius:20px; background:#fff; }}
    .matinv-table {{ width:100%; min-width:0; border-collapse:collapse; table-layout:fixed; }}
    .matinv-table th {{ padding:10px 10px; background:#f8fafc; color:#475569; text-align:left; font-size:.72rem; font-weight:800; text-transform:uppercase; }}
    .matinv-table td {{ padding:10px 10px; border-top:1px solid rgba(15,23,42,.07); font-weight:700; vertical-align:middle; }}
    .matinv-col-description {{ width:26%; }}
    .matinv-col-book {{ width:14%; }}
    .matinv-col-total {{ width:10%; }}
    .matinv-col-adjust {{ width:50%; }}
    .matinv-board.is-semifinished .matinv-col-description {{ width:30%; }}
    .matinv-board.is-semifinished .matinv-col-color {{ width:18%; }}
    .matinv-board.is-semifinished .matinv-col-total {{ width:12%; }}
    .matinv-board.is-semifinished .matinv-col-adjust {{ width:40%; }}
    .matinv-row.is-counted {{ background:#ecfdf5; }}
    .matinv-table .is-description {{ width:auto; }}
    .matinv-table .is-color {{ color:#0f766e; font-weight:900; }}
    .matinv-table .is-book-qty {{ color:#475569; font-weight:900; }}
    .matinv-table .is-total {{ }}
    .matinv-table .is-total span {{ display:inline-flex; align-items:center; justify-content:center; min-width:58px; min-height:34px; padding:0 10px; border-radius:999px; background:#0f172a; color:#fff; font-weight:900; }}
    .matinv-table .is-adjust {{ }}
    .matinv-adjust {{ display:grid; grid-template-columns:1fr 1fr 1.2fr; gap:10px; align-items:center; }}
    .matinv-adjust label {{ display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:4px; color:#64748b; font-size:.76rem; font-weight:900; }}
    .matinv-input {{ width:100%; min-height:40px; padding:0 8px; border-radius:13px; border:1px solid var(--line); background:#fff; font-size:.95rem; font-weight:900; text-align:center; }}
    .matinv-input:focus {{ outline:none; border-color:#0f172a; box-shadow:0 0 0 3px rgba(15,23,42,.08); }}
    .matinv-input.is-error {{ border-color:#ef4444; box-shadow:0 0 0 3px rgba(239,68,68,.14); }}
    .matinv-empty-row {{ text-align:center; color:var(--muted); padding:24px !important; }}
    .matinv-notice {{ padding:13px 16px; border-radius:16px; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; font-weight:800; }}
    .matinv-notice.success {{ background:#ecfdf5; color:#047857; border-color:#bbf7d0; }}
    @media (max-width: 900px) {{
      .matinv-shell {{ width:calc(100% - 16px); margin:10px auto 28px; gap:12px; }}
      .matinv-board {{ padding:16px 10px 12px; border-radius:22px; }}
      .matinv-board-head {{ grid-template-columns:1fr auto; gap:10px; }}
      .matinv-board-head strong {{ font-size:1.2rem; }}
      .matinv-board-head p {{ font-size:.86rem; }}
      .matinv-board-stamp {{ min-height:36px; padding:0 11px; font-size:.88rem; }}
      .matinv-search {{ grid-template-columns:1fr; gap:6px; }}
      .matinv-table th {{ padding:8px 6px; font-size:.62rem; letter-spacing:.02em; }}
      .matinv-table td {{ padding:8px 6px; font-size:.84rem; }}
      .matinv-col-description {{ width:28%; }}
      .matinv-col-book {{ width:14%; }}
      .matinv-col-total {{ width:10%; }}
      .matinv-col-adjust {{ width:48%; }}
      .matinv-board.is-semifinished .matinv-col-description {{ width:30%; }}
      .matinv-board.is-semifinished .matinv-col-color {{ width:18%; }}
      .matinv-board.is-semifinished .matinv-col-total {{ width:12%; }}
      .matinv-board.is-semifinished .matinv-col-adjust {{ width:40%; }}
      .matinv-table .is-total span {{ min-width:46px; min-height:30px; padding:0 8px; }}
      .matinv-adjust {{ grid-template-columns:1fr 1fr 1.08fr; gap:5px; }}
      .matinv-adjust label {{ gap:3px; font-size:.68rem; }}
      .matinv-input {{ min-height:36px; padding:0 5px; font-size:.88rem; border-radius:11px; }}
    }}
    @media (max-width: 780px) {{ .matinv-upload-head,.matinv-board-head,.matinv-upload-form {{ grid-template-columns:1fr; }} .matinv-top {{ align-items:flex-start; flex-direction:column; }} .matinv-stats {{ grid-template-columns:1fr 1fr; }} .button {{ width:100%; }} }}
  </style>
</head>
<body>
  <main class="matinv-shell">
    <header class="matinv-top">
      <div>
        <span class="matinv-tag">Divian-HUB</span>
        <h1>{page_title}</h1>
      </div>
      <a href="/">Vissza a modulokhoz</a>
    </header>
    {notice_html}
    {view_switch_html}
    {upload_html if active_view == 'admin' else ''}
    {admin_session_html if active_view == 'admin' and session else ''}
    {inventory_html if active_view == 'leltar' else ''}
  </main>
  {f'<iframe hidden src="{html.escape(auto_download_href)}"></iframe>' if auto_download_href and active_view == 'admin' else ''}
  <script>
    (() => {{
      const root = document.querySelector("[data-material-inventory-root]");
      if (!root) return;
      const route = root.getAttribute("data-state-route");
      const normalizeText = (value) => String(value || "")
        .toLocaleLowerCase("hu-HU")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
      const searchInput = root.querySelector("[data-matinv-search]");
      const applySearch = () => {{
        if (!searchInput) return;
        const terms = normalizeText(searchInput.value.trim()).split(/\\s+/).filter(Boolean);
        root.querySelectorAll("tbody .matinv-row").forEach((row) => {{
          const description = normalizeText(row.querySelector(".is-description")?.textContent || "");
          const color = normalizeText(row.querySelector(".is-color")?.textContent || "");
          const searchable = `${{description}} ${{color}}`;
          row.hidden = terms.length > 0 && !terms.every((term) => searchable.includes(term));
        }});
      }};
      const saveInput = (input) => {{
        if (input.dataset.matinvSaving === "1") return;
        const rawValue = input.value.trim();
        const mode = input.getAttribute("data-mode") || "set";
        if (!rawValue) return;
        input.dataset.matinvSaving = "1";
        const row = input.closest("tr");
        const rowId = input.getAttribute("data-row-id") || "";
        const body = new URLSearchParams();
        body.set("row_id", rowId);
        body.set("value", rawValue);
        body.set("mode", mode);
        fetch(route, {{
          method: "POST",
          headers: {{ "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" }},
          body: body.toString(),
          credentials: "same-origin",
          cache: "no-store",
        }})
          .then((response) => {{
            if (!response.ok) throw new Error("save failed");
            return response.json();
          }})
          .then((payload) => {{
            const nextValue = payload.value || "";
            row?.querySelector("[data-matinv-total]")?.replaceChildren(document.createTextNode(nextValue || "0"));
            row?.querySelectorAll('[data-mode="set"]').forEach((setInput) => setInput.value = nextValue);
            if (mode !== "set") input.value = "";
            row?.classList.toggle("is-counted", String(nextValue || "").trim() !== "");
          }})
          .catch(() => {{
            input.classList.add("is-error");
            window.setTimeout(() => input.classList.remove("is-error"), 1200);
          }})
          .finally(() => {{
            input.dataset.matinvSaving = "0";
          }});
      }};
      searchInput?.addEventListener("input", applySearch);
      applySearch();
      root.querySelectorAll("[data-matinv-input]").forEach((input) => {{
        const row = input.closest("tr");
        input.addEventListener("keydown", (event) => {{
          if (event.key === "Enter") {{
            event.preventDefault();
            saveInput(input);
          }}
        }});
        input.addEventListener("blur", () => saveInput(input));
      }});
    }})();
  </script>
</body>
</html>"""
    return page.encode("utf-8")


def _front_inventory_format_timestamp(value: str) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    try:
        parsed = datetime.fromisoformat(clean_value)
    except ValueError:
        return clean_value
    return parsed.strftime("%Y.%m.%d. %H:%M")


def _front_inventory_load_presence() -> dict:
    if not FRONT_INVENTORY_PRESENCE_PATH.exists():
        return {}
    try:
        payload = json.loads(FRONT_INVENTORY_PRESENCE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _front_inventory_save_presence(payload: dict) -> None:
    FRONT_INVENTORY_PRESENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRONT_INVENTORY_PRESENCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _front_inventory_active_presence_categories() -> set[str]:
    snapshot = _front_inventory_load_presence()
    now = datetime.now()
    active_categories: set[str] = set()
    dirty = False
    for token, item in list(snapshot.items()):
        if not isinstance(item, dict):
            snapshot.pop(token, None)
            dirty = True
            continue
        try:
            updated_at = datetime.fromisoformat(str(item.get("updated_at", "")))
        except ValueError:
            snapshot.pop(token, None)
            dirty = True
            continue
        if (now - updated_at).total_seconds() > 20:
            snapshot.pop(token, None)
            dirty = True
            continue
        if str(item.get("view", "")).strip() == "leltar":
            category = str(item.get("category", "")).strip()
            if category:
                active_categories.add(category)
    if dirty:
        _front_inventory_save_presence(snapshot)
    return active_categories


def _front_inventory_touch_presence(token: str, category: str, view_mode: str, clear: bool = False) -> list[str]:
    clean_token = str(token or "").strip()
    snapshot = _front_inventory_load_presence()
    if clean_token:
        if clear:
            snapshot.pop(clean_token, None)
        else:
            snapshot[clean_token] = {
                "category": str(category or "").strip(),
                "view": _front_inventory_normalize_view(view_mode),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

    now = datetime.now()
    active_categories: list[str] = []
    for key, item in list(snapshot.items()):
        if not isinstance(item, dict):
            snapshot.pop(key, None)
            continue
        try:
            updated_at = datetime.fromisoformat(str(item.get("updated_at", "")))
        except ValueError:
            snapshot.pop(key, None)
            continue
        if (now - updated_at).total_seconds() > 20:
            snapshot.pop(key, None)
            continue
        if str(item.get("view", "")).strip() == "leltar":
            category_value = str(item.get("category", "")).strip()
            if category_value:
                active_categories.append(category_value)

    _front_inventory_save_presence(snapshot)
    return sorted(set(active_categories))


def _front_inventory_build_sync_payload(selected_category: str) -> dict:
    session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
    if session is None:
        return {"category_states": {}, "row_inputs": {}, "updated_at": ""}
    view_model = build_front_inventory_view_model(session, selected_category)
    row_inputs: dict[str, str] = {}
    for row in view_model.get("visible_rows", []):
        row_inputs[str(row.get("row_id", ""))] = str(row.get("input_qty", "") or "")
    category_states = {
        str(item.get("key", "")): bool(item.get("complete"))
        for item in view_model.get("categories", [])
    }
    return {
        "category_states": category_states,
        "row_inputs": row_inputs,
        "updated_at": str(session.get("updated_at", "")),
        "worker_alert": session.get("worker_alert") if isinstance(session.get("worker_alert"), dict) else {},
    }


def _front_inventory_normalize_view(value: str) -> str:
    return "leltar" if str(value or "").strip().lower() == "leltar" else "admin"


def render_front_inventory_form(
    message: str = "",
    success: bool = False,
    selected_category: str = "",
    sort_mode: str = "default",
    view_mode: str = "admin",
    missing_summary: dict | None = None,
    auto_download_href: str = "",
) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
    saved_stock_name = _front_inventory_saved_stock_name()
    saved_check_report_name = _front_inventory_saved_check_report_name()
    saved_insight_workbook_name = _front_inventory_saved_insight_workbook_name()
    saved_insight_script_name = _front_inventory_saved_insight_script_name()
    active_view = _front_inventory_normalize_view(view_mode)
    active_presence_categories = _front_inventory_active_presence_categories()

    admin_href = FRONT_INVENTORY_ROUTE if sort_mode == "default" else f"{FRONT_INVENTORY_ROUTE}?sort={urllib.parse.quote(sort_mode)}"
    inventory_href = (
        FRONT_INVENTORY_ROUTE
        if session is None
        else f"{FRONT_INVENTORY_ROUTE}?view=leltar&sort={urllib.parse.quote(sort_mode)}"
    )
    if active_view == "leltar":
        view_switch_html = """
          <div class="frontinv-view-switch is-worker-only">
            <span class="frontinv-view-tab is-active">Leltár nézet</span>
          </div>
        """
    else:
        view_switch_html = f"""
          <div class="frontinv-view-switch">
            <a class="frontinv-view-tab is-active" href="{admin_href}">Kezelő</a>
            <a class="frontinv-view-tab" href="{inventory_href}">Leltár nézet</a>
          </div>
        """

    admin_session_html = ""
    inventory_html = """
      <section class="frontinv-board is-empty">
        <div class="frontinv-empty">
          <strong>Még nincs aktív frontleltár.</strong>
          <p>Töltsd fel a fóliás front leltárlistát, és utána indulhat a külön leltárnézet.</p>
        </div>
      </section>
    """
    if session:
        view_model = build_front_inventory_view_model(session, selected_category, sort_mode)
        phase_value = str(session.get("phase", "0"))
        finalized = view_model["finalized"]
        categories_html = "".join(
            f"""
              <a class="frontinv-chip{' is-complete' if item.get('complete') else ''}{' is-live' if item['key'] in active_presence_categories else ''}{' is-active' if item['key'] == view_model['selected_category'] else ''}"
                  href="{FRONT_INVENTORY_ROUTE}?view=leltar&category={urllib.parse.quote(item['key'])}&sort={urllib.parse.quote(view_model['sort_mode'])}">
                <span>{html.escape(item['label'])}</span>
                <strong>{item['count']}</strong>
              </a>
            """
            for item in view_model["categories"]
            if item["count"] > 0 or item["key"] in {"all", "egyedi"}
        )

        stats_html = f"""
          <article>
            <span>Aktív sor</span>
            <strong>{view_model['active_row_count']}</strong>
          </article>
          <article>
            <span>Méret szerint</span>
            <strong>{view_model['serial_row_count']}</strong>
          </article>
          <article>
            <span>Egyéb</span>
            <strong>{view_model['custom_row_count']}</strong>
          </article>
          <article>
            <span>Állapot</span>
            <strong>{html.escape(str(session.get('phase_label', 'Számlálás')))}</strong>
          </article>
        """

        inventory_open_href = f"{FRONT_INVENTORY_ROUTE}?view=leltar&category={urllib.parse.quote(view_model['selected_category'])}&sort={urllib.parse.quote(view_model['sort_mode'])}"
        current_sort_mode = str(view_model.get("sort_mode", "default") or "default")

        def frontinv_sort_href(sort_key: str) -> str:
            if current_sort_mode == sort_key:
                next_sort = f"{sort_key}_desc"
            elif current_sort_mode == f"{sort_key}_desc":
                next_sort = "default"
            else:
                next_sort = sort_key
            return f"{FRONT_INVENTORY_ROUTE}?view={active_view}&category={urllib.parse.quote(view_model['selected_category'])}&sort={urllib.parse.quote(next_sort)}"

        def frontinv_sort_label(label: str, sort_key: str) -> str:
            indicator = ""
            if current_sort_mode == sort_key:
                indicator = " ↑"
            elif current_sort_mode == f"{sort_key}_desc":
                indicator = " ↓"
            return f'<a class="frontinv-sort-head" href="{frontinv_sort_href(sort_key)}">{html.escape(label)}{indicator}</a>'

        description_header_html = frontinv_sort_label("Alkatrész leírás", "description")
        color_header_html = frontinv_sort_label("Szín", "color")
        count_header_html = frontinv_sort_label("Darabszám", "count")

        missing_html = ""
        if missing_summary and active_view == "admin":
            missing_category_html = "".join(
                f'<span class="frontinv-meta-chip">{html.escape(str(item.get("key", "")))} · {int(item.get("count", 0))} sor</span>'
                for item in missing_summary.get("categories", [])
            )
            missing_rows_html = "".join(
                f"""
                  <tr>
                    <td>{html.escape(str(row.get('category', '')))}</td>
                    <td>{html.escape(str(row.get('description', '')))}</td>
                    <td>{html.escape(str(row.get('color', '') or '-'))}</td>
                  </tr>
                """
                for row in missing_summary.get("rows", [])
            )
            if not missing_rows_html:
                missing_rows_html = '<tr><td colspan="3" class="frontinv-empty-row">Nincs hiányzó darabszám.</td></tr>'
            missing_html = f"""
              <section class="frontinv-board frontinv-admin-board">
                <div class="frontinv-board-head">
                  <div>
                    <span class="frontinv-tag">Hiányellenőrzés</span>
                    <strong>Hiányzó darabszámok</strong>
                    <p>Jelenleg {int(missing_summary.get('total_missing', 0))} frontnál nincs kitöltve a darabszám.</p>
                  </div>
                </div>
                <div class="frontinv-meta-row">
                  {missing_category_html or '<span class="frontinv-meta-chip">Nincs hiányzó sor</span>'}
                </div>
                <div class="frontinv-table-wrap">
                  <table class="frontinv-table frontinv-admin-table">
                    <thead>
                      <tr>
                        <th>Kategória</th>
                        <th>Leírás</th>
                        <th>Szín</th>
                      </tr>
                    </thead>
                    <tbody>
                      {missing_rows_html}
                    </tbody>
                  </table>
                </div>
              </section>
            """

        if finalized:
            finalized_downloads_html = "".join(
                part
                for part in (
                    f'<a class="button button-secondary frontinv-open-button" href="{inventory_open_href}">Leltár nézet</a>',
                    f'<a class="button button-secondary frontinv-open-button" href="{FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE}">Végleges riport</a>' if saved_check_report_name else "",
                    f'<a class="button button-secondary frontinv-open-button" href="{FRONT_INVENTORY_INSIGHT_EXCEL_DOWNLOAD_ROUTE}">inSight Excel</a>' if saved_insight_workbook_name else "",
                    f'<a class="button button-secondary frontinv-open-button" href="{FRONT_INVENTORY_INSIGHT_SCRIPT_DOWNLOAD_ROUTE}">inSight AHK</a>' if saved_insight_script_name else "",
                )
                if part
            )
            admin_action_html = f"""
              <div class="frontinv-phase-callout is-complete">
                <div>
                  <strong>Leltár lezárva</strong>
                  <p>A végleges darabszámok már rögzítve vannak. Lezárás ideje: {html.escape(_front_inventory_format_timestamp(str(session.get('finalized_at', ''))))}</p>
                </div>
                <div class="frontinv-admin-actions">
                  {finalized_downloads_html}
                </div>
              </div>
            """
            rows_html = "".join(
                f"""
                  <tr class="frontinv-row is-final" data-frontinv-row data-frontinv-search-text="{html.escape(' '.join(str(row.get(key, '')) for key in ('description', 'color', 'color_label', 'size', 'category')), quote=True)}">
                    <td class="is-description">{html.escape(str(row.get('description', '')))}</td>
                    <td class="is-color"><span class="frontinv-color-chip">{html.escape(str(row.get('color_label', row.get('color', '')) or '-'))}</span></td>
                    <td class="is-count"><span class="frontinv-count-pill">{int(row.get('counted_qty', 0) or 0)}</span></td>
                  </tr>
                """
                for row in view_model["finalized_rows"]
                if (
                    view_model["selected_category"] == "all"
                    and row.get("is_serial")
                    or view_model["selected_category"] == "egyedi"
                    and not row.get("is_serial")
                    or view_model["selected_category"] not in {"all", "egyedi"}
                    and row.get("category") == view_model["selected_category"]
                )
            )
            if not rows_html:
                rows_html = '<tr><td colspan="3" class="frontinv-empty-row">Ehhez a kategóriához nincs lezárt front.</td></tr>'
            inventory_status_html = f"""
              <div class="frontinv-phase-callout is-complete">
                <div>
                  <strong>Leltár lezárva</strong>
                  <p>A végleges darabszámok már rögzítve vannak. Lezárás ideje: {html.escape(_front_inventory_format_timestamp(str(session.get('finalized_at', ''))))}</p>
                </div>
              </div>
            """
        else:
            rows_html = "".join(
                f"""
                  <tr class="frontinv-row{' is-counted' if str(row.get('input_qty', '')).strip() else ''}" data-frontinv-row data-row-id="{html.escape(str(row.get('row_id', '')))}" data-frontinv-current-value="{html.escape(str(row.get('input_qty', '')), quote=True)}" data-frontinv-search-text="{html.escape(' '.join(str(row.get(key, '')) for key in ('description', 'color', 'color_label', 'size', 'category')), quote=True)}">
                    <td class="is-description">{html.escape(str(row.get('description', '')))}</td>
                    <td class="is-color"><span class="frontinv-color-chip">{html.escape(str(row.get('color_label', row.get('color', '')) or '-'))}</span></td>
                    <td class="is-count">
                      <div class="frontinv-count-control">
                        <span class="frontinv-count-pill" data-frontinv-total>{html.escape(str(row.get('input_qty', '') or '0'))}</span>
                        <div class="frontinv-adjust">
                          <label><span>+</span><input class="frontinv-input" type="number" min="0" inputmode="numeric" autocomplete="off" placeholder="0" data-frontinv-input data-mode="add" data-row-id="{html.escape(str(row.get('row_id', '')))}" /></label>
                          <label><span>-</span><input class="frontinv-input" type="number" min="0" inputmode="numeric" autocomplete="off" placeholder="0" data-frontinv-input data-mode="subtract" data-row-id="{html.escape(str(row.get('row_id', '')))}" /></label>
                        </div>
                      </div>
                    </td>
                  </tr>
                """
                for row in view_model["visible_rows"]
            )
            if not rows_html:
                rows_html = '<tr><td colspan="3" class="frontinv-empty-row">Ehhez a kategóriához most nincs megjeleníthető front.</td></tr>'

            phase_title = "Egykörös számlálás"
            phase_copy = "Írják be a tényleges darabszámot. A leltár itt nem fut több ellenőrzési körön, lezáráskor készül az export."
            action_route = FRONT_INVENTORY_FINALIZE_ROUTE
            action_label = "Leltár lezárása"
            admin_action_html = f"""
              <div class="frontinv-phase-callout">
                <div>
                  <strong>{html.escape(phase_title)}</strong>
                  <p>{html.escape(phase_copy)}</p>
                </div>
                <div class="frontinv-admin-actions">
                  <a class="button button-secondary frontinv-open-button" href="{inventory_open_href}">Leltár nézet</a>
                  <form method="post" action="{action_route}">
                    <input type="hidden" name="selected_view" value="admin" />
                    <input type="hidden" name="sort_mode" value="{html.escape(view_model['sort_mode'])}" />
                    <button class="button button-primary frontinv-action-button" type="submit">{html.escape(action_label)}</button>
                  </form>
                </div>
              </div>
            """
            inventory_status_html = f"""
              <div class="frontinv-phase-callout">
                <div>
                  <strong>{html.escape(phase_title)}</strong>
                  <p>{html.escape(phase_copy)}</p>
                </div>
              </div>
            """

        admin_session_html = f"""
          <section class="frontinv-board frontinv-admin-board">
            <div class="frontinv-board-head">
              <div>
                <span class="frontinv-tag">Kezelő felület</span>
                <strong>Aktív frontleltár</strong>
                <p>Forrás: {html.escape(str(session.get('source_name', '')))} · Utoljára frissítve: {html.escape(_front_inventory_format_timestamp(str(session.get('updated_at', ''))))}</p>
              </div>
              <div class="frontinv-board-stamp">{html.escape(str(session.get('phase_label', 'Számlálás')))}</div>
            </div>

            <div class="frontinv-stats">
              {stats_html}
            </div>

            {admin_action_html}
          </section>
        """

        inventory_html = f"""
          <section class="frontinv-board is-worker" data-front-inventory-root data-state-route="{FRONT_INVENTORY_STATE_ROUTE}" data-presence-route="{FRONT_INVENTORY_PRESENCE_ROUTE}" data-alert-clear-route="{FRONT_INVENTORY_ALERT_CLEAR_ROUTE}" data-category="{html.escape(view_model['selected_category'])}">
            <div class="frontinv-board-head">
              <div>
                <span class="frontinv-tag">Leltár nézet</span>
                <strong>Front számlálás</strong>
                <p>Forrás: {html.escape(str(session.get('source_name', '')))} · Utoljára frissítve: {html.escape(_front_inventory_format_timestamp(str(session.get('updated_at', ''))))}</p>
              </div>
              <div class="frontinv-board-stamp">{html.escape(str(session.get('phase_label', 'Számlálás')))}</div>
            </div>

            <div class="frontinv-category-row">
              {categories_html}
            </div>
            <label class="frontinv-search">
              <span>Keresés leírás, szín vagy méret alapján</span>
              <input type="search" data-frontinv-search placeholder="Írj be részletet..." autocomplete="off" />
            </label>
            {inventory_status_html}

            <div class="frontinv-table-wrap">
                <table class="frontinv-table">
                  <thead>
                    <tr>
                      <th>{description_header_html}</th>
                      <th>{color_header_html}</th>
                      <th>{count_header_html}</th>
                    </tr>
                  </thead>
                <tbody>
                  {rows_html}
                </tbody>
              </table>
            </div>
            <div class="frontinv-generated-by">generated by Divian-HUB</div>
          </section>
          <div class="frontinv-alert-modal" data-frontinv-alert hidden>
            <div class="frontinv-alert-card">
              <strong data-frontinv-alert-title>Ellenőrzés kész</strong>
              <p data-frontinv-alert-message></p>
              <button class="button button-primary" type="button" data-frontinv-alert-close>Rendben</button>
            </div>
          </div>
        """

    stock_meta_html = ""
    if saved_stock_name:
        stock_meta_html = f'<div class="frontinv-meta-chip">Aktív készletforrás: {html.escape(saved_stock_name)}</div>'

    admin_html = f"""
      <section class="frontinv-upload-card">
        <div class="frontinv-upload-head">
          <div class="frontinv-copy">
            <span class="frontinv-tag">Tablet leltár</span>
            <strong>Fóliás front leltározás.</strong>
            <p>Feltöltöd a leltározandó fóliás front listát, a kollégák pedig külön leltár nézetben, méretkategóriák szerint írják a darabszámokat.</p>
          </div>
          <div class="frontinv-visual" aria-hidden="true">
            <div class="frontinv-visual-pill">Készlet</div>
            <div class="frontinv-visual-line"></div>
            <div class="frontinv-visual-pill">Számlálás</div>
            <div class="frontinv-visual-line"></div>
            <div class="frontinv-visual-pill is-strong">Lezárás</div>
          </div>
        </div>

        <div class="frontinv-meta-row">
          {stock_meta_html}
        </div>

        <form class="frontinv-upload-form" method="post" action="{FRONT_INVENTORY_PROCESS_ROUTE}" enctype="multipart/form-data">
          <label class="frontinv-field">
            <span>Leltározandó lista</span>
            <strong>Fóliás front leltárfájl</strong>
            <input type="file" name="stock_file" accept=".xlsx,.xlsm,.csv" required />
            <small>Szükséges oszlopok: Alkatr.-szám, Alkatr.-leírás, SZIN.Desc. A Leltarbol_ki oszlopban jelölt sorok kimaradnak.</small>
          </label>

          <div class="frontinv-action-row">
            <span class="inline-note">A feltöltés után az új leltár azonnal mentődik, és külön gombbal megnyitható a kollégák leltárnézete.</span>
            <button class="button button-primary frontinv-submit-button" type="submit">Új leltár indítása</button>
          </div>
        </form>
      </section>
    """

    content_html = f"""
      <div class="frontinv-shell">
        {view_switch_html}
        {admin_html if active_view == 'admin' else ''}
        {admin_session_html if active_view == 'admin' and session else ''}
        {missing_html if active_view == 'admin' and session else ''}
        {inventory_html if active_view == 'leltar' else ''}
      </div>
      {f'<iframe hidden src="{html.escape(auto_download_href)}"></iframe>' if auto_download_href and active_view == 'admin' else ''}
    """

    extra_script = """
<style>
  :root {
    --frontinv-text: #0f172a;
    --frontinv-muted: #64748b;
    --frontinv-line: #d8e0ea;
    --frontinv-accent: #0c8d57;
    --frontinv-accent-strong: #12a566;
  }
  .frontinv-admin-page {
    margin: 0;
    min-height: 100vh;
    background:
      radial-gradient(circle at 8% 4%, rgba(18, 165, 102, 0.16), transparent 28rem),
      linear-gradient(180deg, #f8fbfc 0%, #eef3f7 42%, #e9f0f5 100%);
    color: var(--frontinv-text);
    font-family: Manrope, sans-serif;
  }
  .frontinv-admin-stage {
    width: min(1280px, calc(100% - 28px));
    margin: 16px auto 42px;
    display: grid;
    gap: 16px;
  }
  .frontinv-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 22px 24px;
    border-radius: 28px;
    background: linear-gradient(135deg, #ffffff 0%, #f7fffb 100%);
    box-shadow: 0 22px 55px rgba(15, 23, 42, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.8);
  }
  .frontinv-top h1 {
    margin: 6px 0 0;
    font: 800 1.55rem/1.05 "Space Grotesk", sans-serif;
    letter-spacing: -0.03em;
  }
  .frontinv-top a {
    display: inline-flex;
    align-items: center;
    min-height: 42px;
    padding: 0 15px;
    border-radius: 999px;
    color: #0f172a;
    text-decoration: none;
    font-weight: 900;
    background: #ffffff;
    border: 1px solid var(--frontinv-line);
  }
  .frontinv-shell {
    display: grid;
    gap: 16px;
  }
  .frontinv-view-switch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    padding: 6px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: 0 10px 24px rgba(10, 18, 30, 0.06);
  }
  .frontinv-view-tab {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 40px;
    padding: 0 18px;
    border-radius: 999px;
    color: #1e293b;
    background: #e2e8f0;
    border: 1px solid rgba(15, 23, 42, 0.1);
    text-decoration: none;
    font-weight: 800;
  }
  .frontinv-view-tab.is-active {
    background: #0f172a;
    color: #ffffff;
  }
  .frontinv-view-switch.is-worker-only .frontinv-view-tab {
    pointer-events: none;
  }
  .frontinv-upload-card,
  .frontinv-board {
    position: relative;
    overflow: hidden;
    border-radius: 26px;
    border: 1px solid rgba(7, 16, 24, 0.08);
    background: rgba(255, 255, 255, 0.94);
    color: #0f172a;
    box-shadow: 0 24px 58px rgba(15, 23, 42, 0.09);
  }
  .frontinv-upload-card::before,
  .frontinv-board::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 5px;
    background: linear-gradient(90deg, var(--frontinv-accent-strong), #86efac, #dbeafe);
    pointer-events: none;
  }
  .frontinv-upload-card {
    padding: 22px;
  }
  .frontinv-upload-head,
  .frontinv-board-head {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 18px;
    align-items: start;
  }
  .frontinv-copy {
    display: grid;
    gap: 10px;
    max-width: 720px;
  }
  .frontinv-copy strong,
  .frontinv-board-head strong,
  .frontinv-empty strong,
  .frontinv-phase-callout strong {
    font-family: "Space Grotesk", sans-serif;
    color: #0f172a;
  }
  .frontinv-copy strong,
  .frontinv-board-head strong {
    font-size: clamp(1.35rem, 2.8vw, 2rem);
    line-height: 1;
  }
  .frontinv-copy p,
  .frontinv-board-head p,
  .frontinv-field small,
  .frontinv-empty p,
  .frontinv-phase-callout p,
  .frontinv-generated-by {
    margin: 0;
    color: #64748b;
    line-height: 1.55;
  }
  .frontinv-tag {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    min-height: 28px;
    padding: 0 12px;
    border-radius: 999px;
    background: #edf7f2;
    color: #0c7650;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .frontinv-visual {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(15, 23, 42, 0.08);
  }
  .frontinv-visual-pill {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid rgba(15, 23, 42, 0.1);
    background: #ffffff;
    color: #334155;
    font-size: 0.82rem;
    font-weight: 700;
  }
  .frontinv-visual-pill.is-strong {
    background: #0f172a;
    border-color: #0f172a;
    color: #ffffff;
  }
  .frontinv-visual-line {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(15, 23, 42, 0.2), rgba(15, 23, 42, 0.55));
  }
  .frontinv-meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 16px;
  }
  .frontinv-meta-chip {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    background: #f8fafc;
    border: 1px solid rgba(15, 23, 42, 0.08);
    color: #475569;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .frontinv-upload-form {
    display: grid;
    gap: 14px;
    margin-top: 18px;
  }
  .frontinv-field {
    display: grid;
    gap: 8px;
    padding: 16px 18px;
    border-radius: 20px;
    background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
    border: 1px solid rgba(15, 23, 42, 0.08);
  }
  .frontinv-field span {
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .frontinv-field strong {
    color: #0f172a;
    font-size: 1rem;
  }
  .frontinv-field input[type="file"] {
    width: 100%;
    min-height: 54px;
    padding: 14px 16px;
    border-radius: 16px;
    border: 1px dashed rgba(15, 23, 42, 0.18);
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    color: #0f172a;
  }
  .frontinv-action-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }
  .frontinv-submit-button,
  .frontinv-action-button {
    min-width: 210px;
    min-height: 52px;
    border-radius: 16px;
    background: linear-gradient(180deg, var(--frontinv-accent-strong), var(--frontinv-accent));
    border-color: transparent;
    color: #ffffff;
    box-shadow: 0 12px 24px rgba(12, 141, 87, 0.20);
  }
  .frontinv-open-button {
    min-width: 190px;
    min-height: 52px;
    border-radius: 16px;
    background: #e2e8f0;
    border: 1px solid rgba(15, 23, 42, 0.12);
    color: #0f172a;
    font-weight: 800;
  }
  .frontinv-open-button:hover,
  .frontinv-open-button:focus-visible {
    background: #cbd5e1;
    color: #020617;
  }
  .frontinv-board {
    padding: 22px;
  }
  .frontinv-board.is-worker {
    min-height: 100dvh;
    border-radius: 0;
    border-left: 0;
    border-right: 0;
    box-shadow: none;
    padding: 18px 20px 24px;
  }
  .frontinv-board.is-worker .frontinv-table-wrap {
    overflow-x: hidden;
  }
  .frontinv-board.is-worker .frontinv-table {
    min-width: 0;
    table-layout: fixed;
  }
  .frontinv-admin-board {
    display: grid;
    gap: 0;
  }
  .frontinv-board-stamp {
    white-space: nowrap;
    font-size: 0.85rem;
    font-weight: 700;
    padding: 10px 14px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(15, 23, 42, 0.08);
    color: #475569;
  }
  .frontinv-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .frontinv-stats article {
    padding: 16px;
    border-radius: 20px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: grid;
    gap: 6px;
  }
  .frontinv-stats span {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .frontinv-stats strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.08rem;
  }
  .frontinv-category-row {
      display: flex;
      gap: 10px;
      margin-top: 14px;
      overflow-x: auto;
      padding-bottom: 4px;
    }
  .frontinv-search {
    display: grid;
    grid-template-columns: auto minmax(220px, 420px);
    align-items: center;
    justify-content: start;
    gap: 10px;
    margin-top: 10px;
    color: #475569;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .frontinv-search input {
    width: 100%;
    min-height: 42px;
    padding: 0 15px;
    border: 1px solid rgba(15, 23, 42, 0.12);
    border-radius: 999px;
    background: #ffffff;
    color: #0f172a;
    font: 800 0.95rem/1 Manrope, sans-serif;
    text-transform: none;
    letter-spacing: 0;
  }
  .frontinv-search input:focus {
    outline: none;
    border-color: #0f172a;
    box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.08);
  }
    .frontinv-chip {
      display: inline-flex;
      align-items: center;
    gap: 10px;
    min-height: 42px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid rgba(15, 23, 42, 0.12);
    background: #ffffff;
    color: #0f172a;
    text-decoration: none;
    white-space: nowrap;
    font-weight: 700;
  }
  .frontinv-chip strong {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 26px;
    height: 26px;
    padding: 0 8px;
    border-radius: 999px;
    background: #f1f5f9;
    font-size: 0.84rem;
  }
  .frontinv-chip.is-active {
    background: #0f172a;
    color: #ffffff;
    border-color: #0f172a;
  }
  .frontinv-chip.is-active strong {
    background: rgba(255, 255, 255, 0.14);
    color: #ffffff;
  }
  .frontinv-chip.is-complete {
    background: rgba(22, 163, 74, 0.12);
    border-color: rgba(22, 163, 74, 0.38);
    color: #166534;
  }
  .frontinv-chip.is-complete strong {
    background: rgba(22, 163, 74, 0.16);
    color: #166534;
  }
  .frontinv-chip.is-complete.is-active {
    background: #166534;
    border-color: #166534;
    color: #ffffff;
  }
  .frontinv-chip.is-complete.is-active strong {
    background: rgba(255, 255, 255, 0.18);
    color: #ffffff;
  }
  .frontinv-chip.is-live:not(.is-active) {
    background: rgba(37, 99, 235, 0.10);
    border-color: rgba(37, 99, 235, 0.34);
    color: #1d4ed8;
  }
    .frontinv-chip.is-live:not(.is-active) strong {
      background: rgba(37, 99, 235, 0.14);
      color: #1d4ed8;
    }
  .frontinv-phase-callout {
    margin-top: 14px;
    padding: 16px 18px;
    border-radius: 20px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 14px;
  }
  .frontinv-admin-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .frontinv-admin-actions form {
    margin: 0;
  }
  .frontinv-phase-callout.is-final {
    background: linear-gradient(180deg, #fffaf5 0%, #ffffff 100%);
  }
  .frontinv-phase-callout.is-complete {
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  }
  .frontinv-table-wrap {
    margin-top: 14px;
    overflow: auto;
    border-radius: 20px;
    border: 1px solid rgba(15, 23, 42, 0.08);
    background: #ffffff;
  }
  .frontinv-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 1040px;
  }
  .frontinv-table thead th {
      padding: 14px 18px;
      border-bottom: 1px solid rgba(15, 23, 42, 0.08);
      background: #f8fafc;
    color: #475569;
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
      text-align: left;
      white-space: nowrap;
    }
    .frontinv-sort-head {
      color: inherit;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .frontinv-table tbody td {
      padding: 14px 18px;
      border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    color: #0f172a;
    vertical-align: middle;
  }
  .frontinv-table tbody tr:nth-child(2n) {
    background: rgba(248, 250, 252, 0.72);
  }
  .frontinv-row.is-counted {
    background: rgba(22, 163, 74, 0.10) !important;
  }
  .frontinv-row.is-final {
    background: rgba(15, 23, 42, 0.03) !important;
  }
  .frontinv-table td.is-code {
    width: 260px;
    font-weight: 700;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 0.9rem;
  }
  .frontinv-table td.is-description {
    min-width: 320px;
    font-weight: 700;
  }
  .frontinv-table td.is-color {
    width: 220px;
  }
  .frontinv-table td.is-count {
    width: 300px;
  }
  .frontinv-board.is-worker .frontinv-table td.is-description {
    min-width: 0;
    width: auto;
  }
  .frontinv-board.is-worker .frontinv-table td.is-color {
    width: 180px;
  }
  .frontinv-board.is-worker .frontinv-table td.is-count {
    width: 280px;
  }
  .frontinv-color-chip {
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    padding: 0 14px;
    border-radius: 999px;
    background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
    border: 1px solid rgba(37, 99, 235, 0.14);
    color: #1d4ed8;
    font-weight: 800;
    white-space: nowrap;
  }
  .frontinv-input {
    width: 100%;
    min-height: 44px;
    padding: 0 10px;
    border-radius: 16px;
    border: 1px solid rgba(15, 23, 42, 0.12);
    background: #ffffff;
    color: #0f172a;
    font-size: 1.1rem;
    font-weight: 800;
    text-align: center;
  }
  .frontinv-count-control {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 10px;
  }
  .frontinv-adjust {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .frontinv-adjust label {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 4px;
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 900;
  }
  .frontinv-input:focus {
    outline: none;
    border-color: #0f172a;
    box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.08);
  }
  .frontinv-input.is-error {
    border-color: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.14);
  }
  .frontinv-count-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 72px;
    min-height: 42px;
    padding: 0 14px;
    border-radius: 999px;
    background: #0f172a;
    color: #ffffff;
    font-weight: 800;
  }
  .frontinv-generated-by {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px dashed rgba(15, 23, 42, 0.12);
    text-align: right;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .frontinv-alert-modal {
    position: fixed;
    inset: 0;
    z-index: 1200;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(15, 23, 42, 0.24);
    backdrop-filter: blur(3px);
  }
  .frontinv-alert-modal[hidden] {
    display: none !important;
  }
  .frontinv-alert-card {
    width: min(100%, 420px);
    padding: 24px 24px 20px;
    border-radius: 24px;
    background: #ffffff;
    box-shadow: 0 28px 60px rgba(15, 23, 42, 0.18);
    display: grid;
    gap: 12px;
    text-align: center;
  }
  .frontinv-alert-card strong {
    color: #0f172a;
    font-size: 1.22rem;
    font-weight: 800;
  }
  .frontinv-alert-card p {
    margin: 0;
    color: #475569;
    font-size: 1rem;
    line-height: 1.55;
  }
  .frontinv-alert-card .button {
    width: 100%;
    justify-content: center;
  }
  .frontinv-empty {
    display: grid;
    gap: 8px;
    padding: 34px 28px;
  }
  .frontinv-empty-row {
    color: #64748b;
    text-align: center;
    padding: 26px 18px !important;
  }
  .frontinv-worker-stage {
    min-height: 100dvh;
    background: #f8fafc;
  }
  @media (orientation: portrait) and (max-width: 1100px) {
    .frontinv-board.is-worker .frontinv-table thead th,
    .frontinv-board.is-worker .frontinv-table tbody td {
      padding: 12px 10px;
    }
    .frontinv-board.is-worker .frontinv-table thead th {
      font-size: 0.7rem;
      letter-spacing: 0.05em;
    }
    .frontinv-board.is-worker .frontinv-table td.is-description {
      font-size: 0.92rem;
      line-height: 1.25;
    }
    .frontinv-board.is-worker .frontinv-table td.is-color {
      width: 146px;
    }
    .frontinv-board.is-worker .frontinv-color-chip {
      min-height: 32px;
      padding: 0 10px;
      font-size: 0.8rem;
      line-height: 1.15;
      white-space: normal;
      text-align: center;
      justify-content: center;
    }
    .frontinv-board.is-worker .frontinv-table td.is-count {
      width: 240px;
    }
    .frontinv-board.is-worker .frontinv-input {
      min-height: 38px;
      font-size: 0.94rem;
      padding: 0 6px;
    }
    .frontinv-count-control {
      gap: 6px;
    }
    .frontinv-adjust {
      gap: 5px;
    }
    .frontinv-adjust label {
      font-size: 0.7rem;
      gap: 3px;
    }
    .frontinv-search {
      grid-template-columns: 1fr;
      gap: 6px;
    }
  }
  @media (max-width: 1100px) {
    .frontinv-admin-stage {
      width: calc(100% - 16px);
      margin: 10px auto 28px;
      gap: 12px;
    }
    .frontinv-top {
      align-items: flex-start;
      flex-direction: column;
    }
    .frontinv-upload-head,
    .frontinv-board-head,
    .frontinv-phase-callout {
      grid-template-columns: minmax(0, 1fr);
      display: grid;
    }
    .frontinv-stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .frontinv-view-switch {
      width: 100%;
    }
  }
  @media (max-width: 720px) {
    .frontinv-upload-card,
    .frontinv-board {
      border-radius: 22px;
    }
    .frontinv-upload-card,
    .frontinv-board {
      padding: 18px;
    }
    .frontinv-stats {
      grid-template-columns: minmax(0, 1fr);
    }
    .frontinv-action-row .button,
    .frontinv-submit-button,
    .frontinv-action-button {
      width: 100%;
      min-width: 0;
    }
    .frontinv-table {
      min-width: 920px;
    }
    .frontinv-board.is-worker {
      padding: 14px 14px 20px;
    }
  }
</style>
<script>
(() => {
  const run = () => {
  const root = document.querySelector("[data-front-inventory-root]");
  if (!root) {
    return;
  }
  const stateRoute = root.getAttribute("data-state-route");
  const presenceRoute = root.getAttribute("data-presence-route");
  const alertClearRoute = root.getAttribute("data-alert-clear-route");
  const categoryValue = root.getAttribute("data-category") || "";
  if (!stateRoute) {
    return;
  }

  const categoryRow = root.querySelector(".frontinv-category-row");
  const categoryChips = Array.from(root.querySelectorAll(".frontinv-chip"));
  const rowElements = Array.from(root.querySelectorAll("[data-frontinv-row]"));
  const inputFields = Array.from(root.querySelectorAll("[data-frontinv-input]"));
  const searchInput = root.querySelector("[data-frontinv-search]");
  const scrollStorageKey = "frontinv-category-scroll";
  const alertModal = document.querySelector("[data-frontinv-alert]");
  const alertTitle = alertModal ? alertModal.querySelector("[data-frontinv-alert-title]") : null;
  const alertMessage = alertModal ? alertModal.querySelector("[data-frontinv-alert-message]") : null;
  const alertClose = alertModal ? alertModal.querySelector("[data-frontinv-alert-close]") : null;
  const alertStorageKey = "frontinv-last-alert-id";
  let currentAlertId = "";
  const currentCategoryChip = categoryRow
    ? Array.from(categoryRow.querySelectorAll(".frontinv-chip")).find((chip) => chip.classList.contains("is-active"))
    : null;
  let audioContext = null;

  const normalizeSearchText = (value) => String(value || "")
    .toLocaleLowerCase("hu-HU")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  const applyFrontInventorySearch = () => {
    if (!searchInput) {
      return;
    }
    const terms = normalizeSearchText(searchInput.value.trim()).split(/\\s+/).filter(Boolean);
    root.querySelectorAll("[data-frontinv-row]").forEach((row) => {
      const searchable = normalizeSearchText(row.getAttribute("data-frontinv-search-text") || row.textContent || "");
      row.hidden = terms.length > 0 && !terms.every((term) => searchable.includes(term));
    });
  };

  const ensureAudioContext = () => {
    if (audioContext) {
      return audioContext;
    }
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) {
      return null;
    }
    try {
      audioContext = new AudioCtor();
    } catch {
      audioContext = null;
    }
    return audioContext;
  };

  const unlockAudio = () => {
    const context = ensureAudioContext();
    if (context && context.state === "suspended") {
      context.resume().catch(() => {});
    }
  };

  const playAlertSound = () => {
    const context = ensureAudioContext();
    if (!context) {
      return;
    }
    if (context.state === "suspended") {
      context.resume().catch(() => {});
    }
    const pattern = [
      { delay: 0.00, duration: 0.16, frequency: 880 },
      { delay: 0.24, duration: 0.16, frequency: 740 },
      { delay: 0.48, duration: 0.24, frequency: 880 },
    ];
    const startAt = context.currentTime + 0.02;
    pattern.forEach((tone) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = tone.frequency;
      gain.gain.setValueAtTime(0.0001, startAt + tone.delay);
      gain.gain.exponentialRampToValueAtTime(0.18, startAt + tone.delay + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + tone.delay + tone.duration);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(startAt + tone.delay);
      oscillator.stop(startAt + tone.delay + tone.duration + 0.04);
    });
  };

  const hideAlert = () => {
    if (alertModal) {
      alertModal.hidden = true;
    }
    if (alertClearRoute && currentAlertId) {
      const formData = new URLSearchParams();
      formData.set("alert_id", currentAlertId);
      fetch(alertClearRoute, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
        body: formData.toString(),
        credentials: "same-origin",
        cache: "no-store",
      }).catch(() => {});
    }
  };

  const showAlert = (payload) => {
    if (!alertModal || !payload || !payload.id) {
      return;
    }
    const nextId = String(payload.id || "");
    if (!nextId || window.sessionStorage.getItem(alertStorageKey) === nextId) {
      return;
    }
    window.sessionStorage.setItem(alertStorageKey, nextId);
    currentAlertId = nextId;
    if (alertTitle) {
      alertTitle.textContent = payload.title || "Ellenőrzés kész";
    }
    if (alertMessage) {
      alertMessage.textContent = payload.message || "";
    }
    alertModal.hidden = false;
    playAlertSound();
  };

  if (alertClose) {
    alertClose.addEventListener("click", hideAlert);
  }
  if (alertModal) {
    alertModal.addEventListener("click", (event) => {
      if (event.target === alertModal) {
        hideAlert();
      }
    });
  }
  window.addEventListener("pointerdown", unlockAudio, { passive: true });
  window.addEventListener("keydown", unlockAudio, { passive: true });

  const getRowId = (input) => input.getAttribute("data-row-id") || input.closest("[data-frontinv-row]")?.getAttribute("data-row-id") || "";
  const getRowCurrentValue = (row) => String(row?.getAttribute("data-frontinv-current-value") || "").trim();
  let countedRowCount = 0;

  const syncRowState = (row) => {
    if (!row) {
      return;
    }
    const isCounted = getRowCurrentValue(row) !== "";
    const wasCounted = row.dataset.frontinvCounted === "1";
    if (isCounted !== wasCounted) {
      countedRowCount += isCounted ? 1 : -1;
    }
    row.dataset.frontinvCounted = isCounted ? "1" : "0";
    row.classList.toggle("is-counted", isCounted);
  };

  const setRowValue = (row, value) => {
    if (!row) {
      return;
    }
    const nextValue = String(value || "").trim();
    row.setAttribute("data-frontinv-current-value", nextValue);
    const total = row.querySelector("[data-frontinv-total]");
    if (total) {
      total.textContent = nextValue || "0";
    }
    syncRowState(row);
  };

  const syncCurrentCategoryState = () => {
    if (!currentCategoryChip) {
      return;
    }
    const hasRows = rowElements.length > 0;
    const isComplete = hasRows && countedRowCount === rowElements.length;
    currentCategoryChip.classList.toggle("is-complete", isComplete);
  };

  const saveAdjustment = (input) => {
    const rowId = getRowId(input);
    const value = input.value.trim();
    const mode = input.getAttribute("data-mode") || "";
    if (!rowId || !value || input.dataset.frontinvSaving === "1") {
      return;
    }
    input.dataset.frontinvSaving = "1";
    input.classList.remove("is-error");
    const formData = new URLSearchParams();
    formData.set("row_id", rowId);
    formData.set("value", value);
    formData.set("mode", mode);
    fetch(stateRoute, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      body: formData.toString(),
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("save failed");
        }
        return response.json();
      })
      .then((payload) => {
        const row = input.closest("[data-frontinv-row]");
        setRowValue(row, payload && Object.prototype.hasOwnProperty.call(payload, "value") ? payload.value : "");
        input.value = "";
        syncCurrentCategoryState();
      })
      .catch(() => {
        input.classList.add("is-error");
        window.setTimeout(() => input.classList.remove("is-error"), 1200);
      })
      .finally(() => {
        input.dataset.frontinvSaving = "0";
      });
  };

  if (categoryRow) {
    const savedScroll = Number(window.sessionStorage.getItem(scrollStorageKey) || "0");
    if (savedScroll > 0) {
      categoryRow.scrollLeft = savedScroll;
    }
    categoryRow.addEventListener("scroll", () => {
      window.sessionStorage.setItem(scrollStorageKey, String(categoryRow.scrollLeft));
    }, { passive: true });
    categoryRow.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        window.sessionStorage.setItem(scrollStorageKey, String(categoryRow.scrollLeft));
      });
    });
  }

  if (presenceRoute && categoryValue) {
    const presenceTokenKey = "frontinv-presence-token";
    let presenceToken = window.sessionStorage.getItem(presenceTokenKey);
    let presenceRequestSeq = 0;
    let lastAppliedPresenceSeq = 0;
    if (!presenceToken) {
      presenceToken = Math.random().toString(36).slice(2) + Date.now().toString(36);
      window.sessionStorage.setItem(presenceTokenKey, presenceToken);
    }

    const applyRemoteState = (payload) => {
      const activeSet = new Set(Array.isArray(payload && payload.active_categories) ? payload.active_categories : []);
      const categoryStates = payload && payload.category_states && typeof payload.category_states === "object"
        ? payload.category_states
        : {};
      categoryChips.forEach((chip) => {
        const href = chip.getAttribute("href") || "";
        let chipCategory = "";
        try {
          chipCategory = new URL(href, window.location.origin).searchParams.get("category") || "all";
        } catch {
          chipCategory = "";
        }
        chip.classList.toggle("is-live", activeSet.has(chipCategory));
        chip.classList.toggle("is-complete", Boolean(categoryStates[chipCategory]));
      });

      const remoteRowInputs = payload && payload.row_inputs && typeof payload.row_inputs === "object"
        ? payload.row_inputs
        : {};
      rowElements.forEach((row) => {
        const rowId = row.getAttribute("data-row-id") || "";
        const nextValue = Object.prototype.hasOwnProperty.call(remoteRowInputs, rowId) ? String(remoteRowInputs[rowId] || "") : "";
        setRowValue(row, nextValue);
      });
      syncCurrentCategoryState();
      showAlert(payload && payload.worker_alert && typeof payload.worker_alert === "object" ? payload.worker_alert : null);
    };

    const syncPresence = (clear = false) => {
      const requestSeq = ++presenceRequestSeq;
      const formData = new URLSearchParams();
      formData.set("token", presenceToken || "");
      formData.set("category", categoryValue);
      formData.set("view", "leltar");
      if (clear) {
        formData.set("clear", "1");
      }
      fetch(presenceRoute, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
        body: formData.toString(),
        credentials: "same-origin",
        cache: "no-store",
        keepalive: clear,
      })
        .then((response) => response.ok ? response.json() : null)
        .then((payload) => {
          if (payload && requestSeq >= lastAppliedPresenceSeq) {
            lastAppliedPresenceSeq = requestSeq;
            applyRemoteState(payload);
          }
        })
        .catch(() => {});
    };

    syncPresence(false);
    const heartbeatId = window.setInterval(() => syncPresence(false), 2500);
    window.addEventListener("pagehide", () => {
      window.clearInterval(heartbeatId);
      syncPresence(true);
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        syncPresence(false);
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFrontInventorySearch);
    applyFrontInventorySearch();
  }

  rowElements.forEach((row) => syncRowState(row));
  inputFields.forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveAdjustment(input);
      }
    });
    input.addEventListener("blur", () => saveAdjustment(input));
    input.addEventListener("change", () => saveAdjustment(input));
  });
  syncCurrentCategoryState();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run, { once: true });
  } else {
    run();
  }
})();
</script>
"""

    if active_view == "leltar":
        worker_page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Front leltár</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <link rel="stylesheet" href="/styles.css" />
  {extra_script}
</head>
<body class="frontinv-worker-page">
  {notice_html}
  <main class="frontinv-worker-stage">
    {inventory_html}
  </main>
</body>
</html>
"""
        return worker_page.encode("utf-8")

    admin_page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Front leltár</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <link rel="stylesheet" href="/styles.css" />
  {extra_script}
</head>
<body class="frontinv-admin-page">
  <main class="frontinv-admin-stage">
    <header class="frontinv-top">
      <div>
        <span class="frontinv-tag">Divian-HUB</span>
        <h1>Fóliás front leltár</h1>
      </div>
      <a href="/">Vissza a modulokhoz</a>
    </header>
    {notice_html}
    {content_html}
  </main>
</body>
</html>
"""
    return admin_page.encode("utf-8")


def _extract_uploaded_pdf(headers, body: bytes) -> tuple[str | None, bytes | None]:
    files = _extract_uploaded_files(headers, body)
    invoice_file = files.get("invoice_file")
    if invoice_file is None:
        return None, None

    return invoice_file


def _is_valid_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{10,32}", job_id))


def _nettfront_job_dir(job_id: str) -> Path | None:
    if not _is_valid_job_id(job_id):
        return None
    return NETTFRONT_RUNTIME_DIR / job_id


def _write_nettfront_job(artifacts) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = NETTFRONT_RUNTIME_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)
    if artifacts.compare_workbook is not None:
        (job_dir / "compare-output.xlsx").write_bytes(artifacts.compare_workbook)

    metadata = {
        "job_id": job_id,
        "invoice_row_count": len(artifacts.invoice_rows),
        "order_row_count": artifacts.order_row_count,
        "has_compare": artifacts.compare_workbook is not None,
        "missing_codes": artifacts.missing_codes,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "nettfront-output.zip").write_bytes(create_bundle_zip(job_dir, include_compare=metadata["has_compare"]))
    return job_id, metadata


def _read_nettfront_metadata(job_id: str) -> tuple[Path | None, dict | None]:
    job_dir = _nettfront_job_dir(job_id)
    if job_dir is None or not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return job_dir, metadata


def _nettfront_download_payload(job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    job_dir, metadata = _read_nettfront_metadata(job_id)
    if job_dir is None or metadata is None:
        return None

    artifact_map = {
        "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
        "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
        "bundle-zip": ("nettfront-output.zip", "application/zip", "nettfront-output.zip"),
    }

    if artifact == "compare-xlsx":
        if not metadata.get("has_compare"):
            return None
        file_path = job_dir / "compare-output.xlsx"
        if not file_path.exists():
            return None
        return (
            file_path.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "compare-output.xlsx",
        )

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name


def _job_runtime_dir(kind: str) -> Path:
    if kind == "procurement":
        return NETTFRONT_PROCUREMENT_RUNTIME_DIR
    if kind == "compare":
        return NETTFRONT_COMPARE_RUNTIME_DIR
    if kind == "order":
        return NETTFRONT_ORDER_RUNTIME_DIR
    raise ValueError(f"Ismeretlen NettFront job típus: {kind}")


def _write_nettfront_job_files(kind: str, files: dict[str, bytes], metadata: dict, bundle_name: str) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir(kind) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        **metadata,
        "job_id": job_id,
        "job_type": kind,
        "bundle_name": bundle_name,
    }

    for file_name, payload in files.items():
        (job_dir / file_name).write_bytes(payload)

    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle_files = list(files.keys()) + ["metadata.json"]
    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return job_id, metadata


def _persist_procurement_job(job_dir: Path, metadata: dict, artifacts, uploaded_parts_name: str = "", uploaded_parts_bytes: bytes | None = None) -> dict:
    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)

    updated_metadata = {
        **metadata,
        "invoice_row_count": len(artifacts.invoice_rows),
        "missing_codes": artifacts.missing_codes,
    }

    if uploaded_parts_name and uploaded_parts_bytes is not None:
        suffix = Path(uploaded_parts_name).suffix.lower() or ".xlsx"
        stored_name = f"alkatreszlista{suffix}"
        (job_dir / stored_name).write_bytes(uploaded_parts_bytes)
        updated_metadata["uploaded_parts_name"] = uploaded_parts_name
        updated_metadata["uploaded_parts_file"] = stored_name

    metadata_path = job_dir / "metadata.json"
    metadata_path.write_text(json.dumps(updated_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle_name = updated_metadata.get("bundle_name", "procurement-output.zip")
    bundle_files = ["invoice-output.csv", "rendeles_sima.csv", "metadata.json"]
    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return updated_metadata


def _write_procurement_job(
    artifacts,
    source_invoice_name: str,
    source_invoice_bytes: bytes,
    uploaded_parts_name: str = "",
    uploaded_parts_bytes: bytes | None = None,
) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir("procurement") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_invoice_file = "source-invoice.pdf"
    (job_dir / source_invoice_file).write_bytes(source_invoice_bytes)

    metadata = {
        "job_id": job_id,
        "job_type": "procurement",
        "bundle_name": "procurement-output.zip",
        "source_invoice_name": source_invoice_name,
        "source_invoice_file": source_invoice_file,
    }
    metadata = _persist_procurement_job(
        job_dir,
        metadata,
        artifacts,
        uploaded_parts_name=uploaded_parts_name,
        uploaded_parts_bytes=uploaded_parts_bytes,
    )
    return job_id, metadata


def _write_compare_job(artifacts) -> tuple[str, dict]:
    return _write_nettfront_job_files(
        "compare",
        {
            "invoice-output.csv": artifacts.invoice_csv,
            "compare-output.xlsx": artifacts.compare_workbook,
        },
        {
            "invoice_row_count": len(artifacts.invoice_rows),
            "order_row_count": artifacts.order_row_count,
        },
        "compare-output.zip",
    )


def _read_nettfront_job(kind: str, job_id: str) -> tuple[Path | None, dict | None]:
    if not _is_valid_job_id(job_id):
        return None, None

    job_dir = _job_runtime_dir(kind) / job_id
    if not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    return job_dir, json.loads(metadata_path.read_text(encoding="utf-8"))


def _download_payload_for_kind(kind: str, job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    job_dir, metadata = _read_nettfront_job(kind, job_id)
    if job_dir is None or metadata is None:
        return None

    if kind == "procurement":
        artifact_map = {
            "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
            "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
            "bundle-zip": (metadata.get("bundle_name", "procurement-output.zip"), "application/zip", metadata.get("bundle_name", "procurement-output.zip")),
        }
    elif kind == "compare":
        artifact_map = {
            "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
            "compare-xlsx": ("compare-output.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "compare-output.xlsx"),
            "bundle-zip": (metadata.get("bundle_name", "compare-output.zip"), "application/zip", metadata.get("bundle_name", "compare-output.zip")),
        }
    else:
        source_stock_file = str(metadata.get("source_stock_file", "")).strip()
        source_stock_name = str(metadata.get("source_stock_name", source_stock_file)).strip() or source_stock_file
        guessed_stock_type = mimetypes.guess_type(source_stock_name)[0] or "application/octet-stream"
        artifact_map = {
            "suggestion-xlsx": (
                "rendelesi-javaslat.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "rendelesi-javaslat.xlsx",
            ),
            "approved-xlsx": (
                metadata.get("approved_file", "rendeles-jovahagyott.xlsx"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                metadata.get("approved_file", "rendeles-jovahagyott.xlsx"),
            ),
            "import-csv": (
                metadata.get("import_file", "rendeles_sima.csv"),
                "text/csv; charset=utf-8",
                metadata.get("import_file", "rendeles_sima.csv"),
            ),
            "source-stock": (
                source_stock_file,
                guessed_stock_type,
                source_stock_name,
            ),
            "bundle-zip": (
                metadata.get("bundle_name", "nettfront-rendeles-output.zip"),
                "application/zip",
                metadata.get("bundle_name", "nettfront-rendeles-output.zip"),
            ),
        }

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name


def _build_invoice_response(file_name: str, file_data: bytes) -> tuple[int, bytes, str, dict[str, str]]:
    chunks = split_pdf_by_invoice(file_data)
    chunk = chunks[0]
    parsed = parse_invoice_data(chunk.text)
    _require_party_vat_numbers(parsed)
    source_label = file_name
    if chunk.page_from != chunk.page_to:
        source_label = f"{file_name} (oldalak: {chunk.page_from}-{chunk.page_to})"
    printable_html = create_printable_html(parsed, source_filename=source_label)
    return 200, printable_html, "text/html; charset=utf-8", {"Cache-Control": "no-store"}


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class InvoiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = _normalize_path(self.path)
        if path == DEV_RELOAD_ROUTE:
            self.respond_dev_reload_stream()
            return

        if path == APP_ROUTE:
            body = render_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ROUTE:
            body = render_nettfront_hub()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_PROCUREMENT_ROUTE:
            body = render_nettfront_procurement_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_COMPARE_ROUTE:
            body = render_nettfront_compare_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ORDER_ROUTE:
            body = render_nettfront_order_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MANUFACTURING_ROUTE:
            query = _manufacturing_query_params(self.path)
            body = render_manufacturing_module(
                production_number=query.get("production", ""),
                operation=query.get("operation", ""),
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATT_INVENTORY_ROUTE:
            body = render_matt_inventory_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATERIAL_INVENTORY_ROUTE:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_view = _material_inventory_normalize_view(str(query.get("view", ["admin"])[0] or "admin"))
            body = render_material_inventory_form(selected_category=selected_category, view_mode=selected_view)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_INVENTORY_ROUTE:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_view = _material_inventory_normalize_view(str(query.get("view", ["admin"])[0] or "admin"))
            body = render_material_inventory_form(
                selected_category=selected_category,
                view_mode=selected_view,
                inventory_kind="semifinished",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_ROUTE:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_view = _material_inventory_normalize_view(str(query.get("view", ["admin"])[0] or "admin"))
            body = render_material_inventory_form(
                selected_category=selected_category,
                view_mode=selected_view,
                inventory_kind="semifinished_front",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_ROUTE:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_view = _front_inventory_normalize_view(str(query.get("view", ["admin"])[0] or "admin"))
            selected_sort = str(query.get("sort", ["default"])[0] or "default").strip()
            _front_inventory_ensure_insight_artifacts(load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH))
            body = render_front_inventory_form(selected_category=selected_category, sort_mode=selected_sort, view_mode=selected_view)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATT_INVENTORY_DOWNLOAD_ROUTE:
            if not MATT_INVENTORY_ALERT_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = MATT_INVENTORY_ALERT_WORKBOOK_PATH.read_bytes()
            download_name = "matt-keszlet-kuszobriport.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATERIAL_INVENTORY_INSIGHT_DOWNLOAD_ROUTE:
            if not MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH.read_bytes()
            download_name = _material_inventory_saved_insight_name() or "anyag-raktar-insight.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATERIAL_INVENTORY_SUMMARY_DOWNLOAD_ROUTE:
            if not MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH.read_bytes()
            download_name = _material_inventory_saved_summary_name() or "anyag-raktar-osszesito.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_INVENTORY_INSIGHT_DOWNLOAD_ROUTE:
            if not SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH.read_bytes()
            download_name = _semifinished_inventory_saved_insight_name() or "felkesz-raktar-insight.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_INVENTORY_SUMMARY_DOWNLOAD_ROUTE:
            if not SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH.read_bytes()
            download_name = _semifinished_inventory_saved_summary_name() or "felkesz-raktar-osszesito.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_INSIGHT_DOWNLOAD_ROUTE:
            if not SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.read_bytes()
            download_name = _semifinished_front_inventory_saved_insight_name() or "felkesz-front-insight.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_SUMMARY_DOWNLOAD_ROUTE:
            if not SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH.read_bytes()
            download_name = _semifinished_front_inventory_saved_summary_name() or "felkesz-front-osszesito.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE:
            if not FRONT_INVENTORY_CHECK_REPORT_PATH.exists():
                self.send_error(404)
                return
            body = FRONT_INVENTORY_CHECK_REPORT_PATH.read_bytes()
            download_name = _front_inventory_saved_check_report_name() or "front-leltar-ellenorzes.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_INSIGHT_EXCEL_DOWNLOAD_ROUTE:
            _front_inventory_ensure_insight_artifacts(load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH))
            if not FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.exists():
                self.send_error(404)
                return
            body = FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.read_bytes()
            download_name = _front_inventory_saved_insight_workbook_name() or "front-leltar-insight-bevetelezes.xlsx"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_INSIGHT_SCRIPT_DOWNLOAD_ROUTE:
            _front_inventory_ensure_insight_artifacts(load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH))
            if not FRONT_INVENTORY_INSIGHT_SCRIPT_PATH.exists():
                self.send_error(404)
                return
            body = FRONT_INVENTORY_INSIGHT_SCRIPT_PATH.read_bytes()
            download_name = _front_inventory_saved_insight_script_name() or "front-leltar-insight-bevetelezes.ahk"
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_ROUTE:
            query = _vacation_query_params(self.path)
            body = render_vacation_calendar(
                month_value=query.get("month", ""),
                edit_department_id=_vacation_parse_int(query.get("edit_department", "")),
                edit_employee_id=_vacation_parse_int(query.get("edit_employee", "")),
                edit_leave_id=_vacation_parse_int(query.get("edit_leave", "")),
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("procurement", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_COMPARE_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_COMPARE_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("compare", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_ORDER_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("order", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        asset = _load_static_asset(path)
        if asset is None:
            self.send_error(404)
            return

        body, content_type = asset
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_dev_reload_stream(self):
        payload = json.dumps({"token": _dev_reload_token()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            self.wfile.write(b"retry: 1000\n")
            self.wfile.write(b"event: reload\n")
            self.wfile.write(b"data: ")
            self.wfile.write(payload)
            self.wfile.write(b"\n\n")
            self.wfile.flush()

            while True:
                time.sleep(DEV_EVENT_HEARTBEAT_SECONDS)
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        path = _normalize_path(self.path)
        if path == MANUFACTURING_STATE_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            production_number = _manufacturing_normalize_number(payload.get("production_number", ""))
            row_id = str(payload.get("row_id", "")).strip()
            extra_row_ids = (
                [str(item).strip() for item in payload.get("row_ids", []) if str(item).strip()]
                if isinstance(payload.get("row_ids"), list)
                else []
            )
            state = str(payload.get("state", "")).strip().lower()

            if not production_number:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a gyártási szám."})
                return
            if not row_id:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a sorazonosító."})
                return
            if state not in {"green", "red", "clear", "none", ""}:
                self.respond_json(400, {"ok": False, "error": "Érvénytelen sorállapot."})
                return

            try:
                target_row_ids: list[str] = []
                for candidate_row_id in [row_id, *extra_row_ids]:
                    if candidate_row_id and candidate_row_id not in target_row_ids:
                        target_row_ids.append(candidate_row_id)
                current_saved_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, production_number)
                locked_done_row_ids = [
                    target_row_id
                    for target_row_id in target_row_ids
                    if str(current_saved_state.get(target_row_id, "")).strip().lower() == "done"
                ]
                if locked_done_row_ids:
                    self.respond_json(
                        409,
                        {
                            "ok": False,
                            "error": "A készre jelentett sor már nem módosítható.",
                            "row_ids": locked_done_row_ids,
                        },
                    )
                    return
                current_state: dict[str, str] = {}
                for target_row_id in target_row_ids:
                    current_state = save_selection_state(MANUFACTURING_RUNTIME_DIR, production_number, target_row_id, state)
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A mentés nem sikerült: {exc}"})
                return

            self.respond_json(
                200,
                {
                    "ok": True,
                    "production_number": production_number,
                    "row_id": row_id,
                    "state": current_state.get(row_id, ""),
                    "row_ids": target_row_ids,
                },
            )
            return

        if path == MANUFACTURING_PARTIAL_QTY_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            production_number = _manufacturing_normalize_number(payload.get("production_number", ""))
            state_key = str(payload.get("state_key", "")).strip()
            value = str(payload.get("value", "")).strip()

            if not production_number:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a gyártási szám."})
                return
            if not state_key:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a sorazonosító."})
                return
            if value and not re.fullmatch(r"\d{1,4}", value):
                self.respond_json(400, {"ok": False, "error": "Csak egész darabszám adható meg."})
                return

            try:
                current_state = save_partial_quantity_state(
                    MANUFACTURING_RUNTIME_DIR,
                    production_number,
                    state_key,
                    value,
                )
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A mentés nem sikerült: {exc}"})
                return

            self.respond_json(
                200,
                {
                    "ok": True,
                    "production_number": production_number,
                    "state_key": state_key,
                    "value": current_state.get(state_key, ""),
                },
            )
            return

        if path == MANUFACTURING_REPORT_READY_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            production_number = _manufacturing_normalize_number(payload.get("production_number", ""))
            category_key = str(payload.get("category_key", "")).strip()
            raw_entries = payload.get("entries")
            if not production_number:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a gyártási szám."})
                return
            if not isinstance(raw_entries, list) or not raw_entries:
                self.respond_json(400, {"ok": False, "error": "Nincs készre jelentendő zöld tétel."})
                return

            entries: list[dict] = []
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                row_id = str(item.get("row_id", "")).strip()
                state_key = str(item.get("state_key", "")).strip()
                code = _extract_con_code(item.get("code", ""))
                entry_category_key = str(item.get("category_key") or category_key).strip()
                source_row_ids = (
                    [str(value).strip() for value in item.get("source_row_ids", []) if str(value).strip()]
                    if isinstance(item.get("source_row_ids"), list)
                    else []
                )
                if not row_id or not state_key or not code:
                    continue
                entries.append(
                    {
                        "row_id": row_id,
                        "state_key": state_key,
                        "code": code,
                        "category_key": entry_category_key,
                        "source_row_ids": source_row_ids,
                    }
                )
            if not entries:
                self.respond_json(400, {"ok": False, "error": "Nem találtam érvényes CON kódot a zöld sorokban."})
                return

            scan_targets = sorted(
                {
                    (
                        str(entry.get("code", "")).strip().upper(),
                        _manufacturing_uses_assembly_ready_endpoint(entry.get("category_key", "")),
                    )
                    for entry in entries
                    if entry.get("code")
                }
            )
            failures: list[dict[str, str | int]] = []
            success_targets: set[tuple[str, bool]] = set()
            for code, use_assembly_validate in scan_targets:
                fallback_endpoint = "validatescan+processscan" if use_assembly_validate else "processscan"
                try:
                    status_code, response_body, endpoint_name = _shopfloor_report_con_ready(
                        code,
                        use_assembly_validate=use_assembly_validate,
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "code": code,
                            "endpoint": fallback_endpoint,
                            "status": 0,
                            "error": str(exc),
                        }
                    )
                    continue
                if 200 <= int(status_code) < 300:
                    success_targets.add((code, use_assembly_validate))
                else:
                    failures.append(
                        {
                            "code": code,
                            "endpoint": endpoint_name,
                            "status": int(status_code),
                            "error": str(response_body or "").strip()[:300],
                        }
                    )

            done_row_ids: list[str] = []
            skipped_row_ids: list[str] = []
            try:
                for entry in entries:
                    entry_code = str(entry.get("code", "")).strip().upper()
                    entry_use_assembly_validate = _manufacturing_uses_assembly_ready_endpoint(entry.get("category_key", ""))
                    target_ids = [
                        str(entry.get("row_id", "")).strip(),
                        *[str(value).strip() for value in entry.get("source_row_ids", []) if str(value).strip()],
                    ]
                    unique_target_ids: list[str] = []
                    for target_id in target_ids:
                        if target_id and target_id not in unique_target_ids:
                            unique_target_ids.append(target_id)
                    if (entry_code, entry_use_assembly_validate) not in success_targets:
                        skipped_row_ids.extend(unique_target_ids)
                        continue
                    for target_id in unique_target_ids:
                        save_selection_state(MANUFACTURING_RUNTIME_DIR, production_number, target_id, "done")
                        done_row_ids.append(target_id)
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A kész állapot mentése nem sikerült: {exc}"})
                return

            unique_done_ids = sorted(set(done_row_ids))
            unique_skipped_ids = sorted(set(skipped_row_ids))
            attempted_count = len(scan_targets)
            success_count = len(success_targets)
            failed_count = max(0, attempted_count - success_count)
            ok = not failures
            error_message = ""
            if failures:
                first_failure = failures[0]
                error_message = (
                    "Shopfloor hívás sikertelen: "
                    f"{first_failure.get('code', '')} "
                    f"{first_failure.get('endpoint', '')} "
                    f"HTTP {first_failure.get('status', 0)}"
                ).strip()
            self.respond_json(
                200 if ok else 207,
                {
                    "ok": ok,
                    "error": error_message,
                    "production_number": production_number,
                    "attempted_count": attempted_count,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "reported_codes": sorted({code for code, _use_assembly_validate in success_targets}),
                    "failed": failures,
                    "done_row_ids": unique_done_ids,
                    "skipped_row_ids": unique_skipped_ids,
                },
            )
            return

        if path == VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_department(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_department_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "department_id")),
                department_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "department_id"),
                    "name": _vacation_form_value(form_data, "name"),
                    "max_absent": _vacation_form_value(form_data, "max_absent") or "1",
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_department(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_employee(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_employee_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "employee_id")),
                employee_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "employee_id"),
                    "name": _vacation_form_value(form_data, "name"),
                    "department_ids": [
                        department_id
                        for raw_value in _vacation_form_values(form_data, "department_ids")
                        for department_id in [_vacation_parse_int(raw_value)]
                        if department_id is not None
                    ],
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_employee(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_LEAVE_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_leave(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_leave_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "leave_id")),
                leave_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "leave_id"),
                    "employee_id": _vacation_form_value(form_data, "employee_id"),
                    "start_date": _vacation_form_value(form_data, "start_date"),
                    "end_date": _vacation_form_value(form_data, "end_date"),
                    "note": _vacation_form_value(form_data, "note"),
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_LEAVE_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_leave(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATT_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            price_file = files.get("price_file")
            stock_file = files.get("stock_file")

            if stock_file is None:
                self.respond_matt_inventory_form("A napi készletfájl feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not matt_inventory_file_name_allowed(stock_name):
                self.respond_matt_inventory_form("A napi készletfájl csak XLSX, XLSM vagy CSV lehet.")
                return

            price_name = ""
            price_bytes: bytes | None = None
            if price_file is not None:
                price_name, price_bytes = price_file
                if not matt_inventory_file_name_allowed(price_name):
                    self.respond_matt_inventory_form("A fix ártábla csak XLSX, XLSM vagy CSV lehet.")
                    return
            else:
                saved_price_payload = _matt_inventory_saved_price_payload()
                if saved_price_payload is None:
                    self.respond_matt_inventory_form("Első alkalommal a fix ártáblát is fel kell tölteni.")
                    return
                price_name, price_bytes = saved_price_payload

            assert price_bytes is not None

            try:
                report = build_matt_inventory_report(
                    price_name=price_name,
                    price_bytes=price_bytes,
                    stock_name=stock_name,
                    stock_bytes=stock_bytes,
                )
                alert_workbook = build_matt_inventory_alert_workbook(
                    price_name=price_name,
                    price_bytes=price_bytes,
                    stock_name=stock_name,
                    stock_bytes=stock_bytes,
                )
            except Exception as exc:
                self.respond_matt_inventory_form(f"A matt készletérték számolása nem sikerült: {exc}")
                return

            MATT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

            if price_file is not None:
                stored_price_path = write_matt_inventory_runtime_upload(
                    MATT_INVENTORY_RUNTIME_DIR / "latest-price",
                    price_name,
                    price_bytes,
                )
                _matt_inventory_write_meta(
                    MATT_INVENTORY_PRICE_META_PATH,
                    {
                        "original_name": Path(price_name).name,
                        "stored_name": stored_price_path.name,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )

            stored_stock_path = write_matt_inventory_runtime_upload(
                MATT_INVENTORY_RUNTIME_DIR / "latest-stock",
                stock_name,
                stock_bytes,
            )
            _matt_inventory_write_meta(
                MATT_INVENTORY_STOCK_META_PATH,
                {
                    "original_name": Path(stock_name).name,
                    "stored_name": stored_stock_path.name,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            save_matt_inventory_report_to_path(MATT_INVENTORY_REPORT_PATH, report)
            MATT_INVENTORY_ALERT_WORKBOOK_PATH.write_bytes(alert_workbook)

            body = render_matt_inventory_form(
                message="A napi matt front készletérték elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATERIAL_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")

            if stock_file is None:
                self.respond_material_inventory_form("Az anyagraktár lista feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not material_inventory_file_name_allowed(stock_name):
                self.respond_material_inventory_form("Az anyagraktár lista csak XLSX, XLSM vagy CSV lehet.")
                return

            try:
                session = build_material_inventory_session(stock_name, stock_bytes)
            except Exception as exc:
                self.respond_material_inventory_form(f"Az anyagraktár leltár előkészítése nem sikerült: {exc}")
                return

            MATERIAL_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            stored_stock_path = write_material_inventory_runtime_upload(
                MATERIAL_INVENTORY_RUNTIME_DIR / "latest-stock",
                stock_name,
                stock_bytes,
            )
            _matt_inventory_write_meta(
                MATERIAL_INVENTORY_STOCK_META_PATH,
                {
                    "original_name": Path(stock_name).name,
                    "stored_name": stored_stock_path.name,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            _material_inventory_clear_generated_artifacts()
            save_material_inventory_session_to_path(MATERIAL_INVENTORY_SESSION_PATH, session)

            body = render_material_inventory_form(
                message="Az anyagraktár leltár nézet elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MATERIAL_INVENTORY_STATE_ROUTE:
            session = load_material_inventory_session_from_path(MATERIAL_INVENTORY_SESSION_PATH)
            if session is None:
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            success, message = update_material_row_input(
                session,
                form_data.get("row_id", ""),
                form_data.get("value", ""),
                form_data.get("mode", "set"),
            )
            if not success:
                payload = message.encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            save_material_inventory_session_to_path(MATERIAL_INVENTORY_SESSION_PATH, session)
            updated_row = next(
                (
                    row
                    for row in session.get("rows", [])
                    if isinstance(row, dict) and str(row.get("row_id", "")) == str(form_data.get("row_id", ""))
                ),
                {},
            )
            payload = json.dumps({"value": str(updated_row.get("input_qty", ""))}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == MATERIAL_INVENTORY_FINALIZE_ROUTE:
            session = load_material_inventory_session_from_path(MATERIAL_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_material_inventory_form("Nincs aktív anyagraktár leltár.")
                return
            success, message = finalize_material_inventory(session, allow_missing=True)
            auto_download_href = ""
            export_warning = ""
            if success:
                try:
                    _material_inventory_store_exports(session)
                    auto_download_href = f"{MATERIAL_INVENTORY_SUMMARY_DOWNLOAD_ROUTE}?t={int(time.time() * 1000)}"
                except Exception as exc:
                    export_warning = f" Az export nem készült el: {exc}"
            save_material_inventory_session_to_path(MATERIAL_INVENTORY_SESSION_PATH, session)
            body = render_material_inventory_form(
                message=f"{message}{export_warning}",
                success=success and not export_warning,
                auto_download_href=auto_download_href,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")

            if stock_file is None:
                self.respond_semifinished_inventory_form("A félkész raktár lista feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not material_inventory_file_name_allowed(stock_name):
                self.respond_semifinished_inventory_form("A félkész raktár lista csak XLSX, XLSM vagy CSV lehet.")
                return

            try:
                session = build_semifinished_inventory_session(stock_name, stock_bytes)
            except Exception as exc:
                self.respond_semifinished_inventory_form(f"A félkész raktár leltár előkészítése nem sikerült: {exc}")
                return

            SEMIFINISHED_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            stored_stock_path = write_material_inventory_runtime_upload(
                SEMIFINISHED_INVENTORY_RUNTIME_DIR / "latest-stock",
                stock_name,
                stock_bytes,
            )
            _matt_inventory_write_meta(
                SEMIFINISHED_INVENTORY_STOCK_META_PATH,
                {
                    "original_name": Path(stock_name).name,
                    "stored_name": stored_stock_path.name,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            _semifinished_inventory_clear_generated_artifacts()
            save_material_inventory_session_to_path(SEMIFINISHED_INVENTORY_SESSION_PATH, session)

            body = render_material_inventory_form(
                message="A félkész raktár leltár nézet elkészült.",
                success=True,
                inventory_kind="semifinished",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_INVENTORY_STATE_ROUTE:
            session = load_material_inventory_session_from_path(SEMIFINISHED_INVENTORY_SESSION_PATH)
            if session is None:
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            success, message = update_material_row_input(
                session,
                form_data.get("row_id", ""),
                form_data.get("value", ""),
                form_data.get("mode", "set"),
            )
            if not success:
                payload = message.encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            save_material_inventory_session_to_path(SEMIFINISHED_INVENTORY_SESSION_PATH, session)
            updated_row = next(
                (
                    row
                    for row in session.get("rows", [])
                    if isinstance(row, dict) and str(row.get("row_id", "")) == str(form_data.get("row_id", ""))
                ),
                {},
            )
            payload = json.dumps({"value": str(updated_row.get("input_qty", ""))}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == SEMIFINISHED_INVENTORY_FINALIZE_ROUTE:
            session = load_material_inventory_session_from_path(SEMIFINISHED_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_semifinished_inventory_form("Nincs aktív félkész raktár leltár.")
                return
            success, message = finalize_material_inventory(session, allow_missing=True)
            auto_download_href = ""
            export_warning = ""
            if success:
                try:
                    _semifinished_inventory_store_exports(session)
                    auto_download_href = f"{SEMIFINISHED_INVENTORY_SUMMARY_DOWNLOAD_ROUTE}?t={int(time.time() * 1000)}"
                except Exception as exc:
                    export_warning = f" Az export nem készült el: {exc}"
            save_material_inventory_session_to_path(SEMIFINISHED_INVENTORY_SESSION_PATH, session)
            body = render_material_inventory_form(
                message=f"{message}{export_warning}",
                success=success and not export_warning,
                auto_download_href=auto_download_href,
                inventory_kind="semifinished",
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")

            if stock_file is None:
                self.respond_semifinished_front_inventory_form("A félkész front lista feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not material_inventory_file_name_allowed(stock_name):
                self.respond_semifinished_front_inventory_form("A félkész front lista csak XLSX, XLSM vagy CSV lehet.")
                return

            try:
                session = build_semifinished_front_inventory_session(stock_name, stock_bytes)
            except Exception as exc:
                self.respond_semifinished_front_inventory_form(f"A félkész front leltár előkészítése nem sikerült: {exc}")
                return

            SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            stored_stock_path = write_material_inventory_runtime_upload(
                SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "latest-stock",
                stock_name,
                stock_bytes,
            )
            _matt_inventory_write_meta(
                SEMIFINISHED_FRONT_INVENTORY_STOCK_META_PATH,
                {
                    "original_name": Path(stock_name).name,
                    "stored_name": stored_stock_path.name,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            _semifinished_front_inventory_clear_generated_artifacts()
            save_material_inventory_session_to_path(SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH, session)

            body = render_material_inventory_form(
                message="A félkész front leltár nézet elkészült.",
                success=True,
                inventory_kind="semifinished_front",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE:
            session = load_material_inventory_session_from_path(SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            success, message = update_material_row_input(
                session,
                form_data.get("row_id", ""),
                form_data.get("value", ""),
                form_data.get("mode", "set"),
            )
            if not success:
                payload = message.encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            save_material_inventory_session_to_path(SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH, session)
            updated_row = next(
                (
                    row
                    for row in session.get("rows", [])
                    if isinstance(row, dict) and str(row.get("row_id", "")) == str(form_data.get("row_id", ""))
                ),
                {},
            )
            payload = json.dumps({"value": str(updated_row.get("input_qty", ""))}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == SEMIFINISHED_FRONT_INVENTORY_FINALIZE_ROUTE:
            session = load_material_inventory_session_from_path(SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_semifinished_front_inventory_form("Nincs aktív félkész front leltár.")
                return
            success, message = finalize_material_inventory(session, allow_missing=True)
            auto_download_href = ""
            export_warning = ""
            if success:
                try:
                    _semifinished_front_inventory_store_exports(session)
                    auto_download_href = f"{SEMIFINISHED_FRONT_INVENTORY_SUMMARY_DOWNLOAD_ROUTE}?t={int(time.time() * 1000)}"
                except Exception as exc:
                    export_warning = f" Az export nem készült el: {exc}"
            save_material_inventory_session_to_path(SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH, session)
            body = render_material_inventory_form(
                message=f"{message}{export_warning}",
                success=success and not export_warning,
                auto_download_href=auto_download_href,
                inventory_kind="semifinished_front",
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")

            if stock_file is None:
                self.respond_front_inventory_form("A fóliás front leltárfájl feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not front_inventory_file_name_allowed(stock_name):
                self.respond_front_inventory_form("A fóliás front leltárfájl csak XLSX, XLSM vagy CSV lehet.")
                return

            try:
                session = build_front_inventory_session(stock_name, stock_bytes)
            except Exception as exc:
                self.respond_front_inventory_form(f"A frontleltár előkészítése nem sikerült: {exc}")
                return

            FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            stored_stock_path = write_front_inventory_runtime_upload(
                FRONT_INVENTORY_RUNTIME_DIR / "latest-stock",
                stock_name,
                stock_bytes,
            )
            _matt_inventory_write_meta(
                FRONT_INVENTORY_STOCK_META_PATH,
                {
                    "original_name": Path(stock_name).name,
                    "stored_name": stored_stock_path.name,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            _front_inventory_clear_generated_artifacts()
            save_front_inventory_session_to_path(FRONT_INVENTORY_SESSION_PATH, session)

            body = render_front_inventory_form(
                message="A frontleltár nézet elkészült.",
                success=True,
                view_mode="admin",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_STATE_ROUTE:
            session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            success, message = update_row_input(
                session,
                form_data.get("row_id", ""),
                form_data.get("value", ""),
                form_data.get("mode", ""),
            )
            if not success:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                payload = message.encode("utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            save_front_inventory_session_to_path(FRONT_INVENTORY_SESSION_PATH, session)
            updated_row = next(
                (
                    row
                    for row in session.get("rows", [])
                    if isinstance(row, dict) and str(row.get("row_id", "")) == str(form_data.get("row_id", ""))
                ),
                {},
            )
            payload = json.dumps({"value": str(updated_row.get("input_qty", ""))}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == FRONT_INVENTORY_PRESENCE_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            active_categories = _front_inventory_touch_presence(
                form_data.get("token", ""),
                form_data.get("category", ""),
                form_data.get("view", "leltar"),
                clear=form_data.get("clear", "") == "1",
            )
            sync_payload = _front_inventory_build_sync_payload(form_data.get("category", ""))
            self.respond_json(200, {"ok": True, "active_categories": active_categories, **sync_payload})
            return

        if path == FRONT_INVENTORY_ALERT_CLEAR_ROUTE:
            session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.send_error(404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            alert_id = str(form_data.get("alert_id", "")).strip()
            current_alert = session.get("worker_alert") if isinstance(session.get("worker_alert"), dict) else None
            if current_alert and (not alert_id or str(current_alert.get("id", "")).strip() == alert_id):
                session.pop("worker_alert", None)
                save_front_inventory_session_to_path(FRONT_INVENTORY_SESSION_PATH, session)
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if path == FRONT_INVENTORY_MISSING_ROUTE:
            session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_front_inventory_form("Nincs aktív frontleltár.")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            summary = summarize_missing_inputs(session)
            success = int(summary.get("total_missing", 0)) == 0
            message = "Nincs hiányzó darabszám." if success else f"Még {int(summary.get('total_missing', 0))} frontnál nincs kitöltve a darabszám."
            selected_sort = str(form_data.get("sort_mode", "default") or "default").strip()
            body = render_front_inventory_form(message=message, success=success, sort_mode=selected_sort, view_mode="admin", missing_summary=summary)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_CHECK_ROUTE:
            session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_front_inventory_form("Nincs aktív frontleltár.")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            selected_view = _front_inventory_normalize_view(form_data.get("selected_view", "admin"))
            selected_sort = str(form_data.get("sort_mode", "default") or "default").strip()
            report_body, report_name, report_count = build_inventory_check_workbook(session, mode="check", treat_missing_as_zero=True)
            auto_download_href = ""
            if report_body:
                FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
                FRONT_INVENTORY_CHECK_REPORT_PATH.write_bytes(report_body)
                _matt_inventory_write_meta(
                    FRONT_INVENTORY_CHECK_REPORT_META_PATH,
                    {
                        "download_name": report_name,
                        "row_count": report_count,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
                auto_download_href = f"{FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE}?t={int(time.time() * 1000)}"
            success, message = run_inventory_check(session, allow_missing=True)
            save_front_inventory_session_to_path(FRONT_INVENTORY_SESSION_PATH, session)
            body = render_front_inventory_form(
                message=message,
                success=success,
                selected_category="",
                sort_mode=selected_sort,
                view_mode=selected_view,
                auto_download_href=auto_download_href,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == FRONT_INVENTORY_FINALIZE_ROUTE:
            session = load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH)
            if session is None:
                self.respond_front_inventory_form("Nincs aktív frontleltár.")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            selected_view = _front_inventory_normalize_view(form_data.get("selected_view", "admin"))
            selected_sort = str(form_data.get("sort_mode", "default") or "default").strip()
            success, message = finalize_inventory(session, allow_missing=True)
            auto_download_href = ""
            report_body = None
            report_name = ""
            report_count = 0
            insight_warning = ""
            if success:
                report_body, report_name, report_count = build_inventory_check_workbook(session, mode="finalize", treat_missing_as_zero=True)
            if report_body:
                FRONT_INVENTORY_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
                FRONT_INVENTORY_CHECK_REPORT_PATH.write_bytes(report_body)
                _matt_inventory_write_meta(
                    FRONT_INVENTORY_CHECK_REPORT_META_PATH,
                    {
                        "download_name": report_name,
                        "row_count": report_count,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
                auto_download_href = f"{FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE}?t={int(time.time() * 1000)}"
            if success:
                try:
                    insight_warning = _front_inventory_store_insight_artifacts(session)
                except Exception as exc:
                    insight_warning = f" Az inSight export nem készült el: {exc}"
            save_front_inventory_session_to_path(FRONT_INVENTORY_SESSION_PATH, session)
            body = render_front_inventory_form(
                message=f"{message}{insight_warning}",
                success=success,
                selected_category="",
                sort_mode=selected_sort,
                view_mode=selected_view,
                auto_download_href=auto_download_href,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ORDER_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")
            parts_file = files.get("parts_file")

            if stock_file is None:
                self.respond_nettfront_order_form("A raktár Excel feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not stock_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                self.respond_nettfront_order_form("A raktárfájl csak XLSX, XLSM vagy CSV lehet.")
                return

            uploaded_parts_name = ""
            uploaded_parts_bytes: bytes | None = None
            uploaded_parts_count = 0
            if parts_file is not None:
                uploaded_parts_name, uploaded_parts_bytes = parts_file
                if uploaded_parts_name and not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                    self.respond_nettfront_order_form("A friss alkatrészlista csak XLSX, XLSM vagy CSV lehet.")
                    return
                try:
                    uploaded_parts_count = len(_load_nettfront_parts_list_from_bytes(uploaded_parts_bytes or b"", uploaded_parts_name))
                except Exception as exc:
                    self.respond_nettfront_order_form(f"A friss alkatrészlista feldolgozása nem sikerült: {exc}")
                    return
                if uploaded_parts_count == 0:
                    self.respond_nettfront_order_form("A friss alkatrészlista üres, így nem tudom felhasználni a jóváhagyásnál.")
                    return

            try:
                result = build_order_suggestions(
                    stock_bytes,
                    default_avg_path=NETTFRONT_ORDER_DEFAULT_AVG_PATH,
                )
                job_id, metadata = _write_nettfront_order_job(
                    result,
                    stock_name,
                    stock_bytes,
                    uploaded_parts_name,
                    uploaded_parts_bytes,
                    uploaded_parts_count,
                )
            except Exception as exc:
                self.respond_nettfront_order_form(f"Hiba a rendelési javaslat készítése közben: {exc}")
                return

            body = render_nettfront_order_result(
                job_id,
                metadata,
                message="A rendelési javaslat elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_APPROVE_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_APPROVE_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            rows = _read_nettfront_order_rows(job_dir)
            if not rows:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message="Ehhez a futáshoz nem találok szerkeszthető rendelési javaslatot.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)

            invalid_rows: list[str] = []
            for row in rows:
                field_name = f"qty__{row.row_id}"
                raw_value = form_data.get(field_name, "")
                parsed_value, ok = _order_parse_quantity_input(raw_value)
                if not ok:
                    invalid_rows.append(row.description or row.part_number or row.row_id)
                    continue
                row.order_qty = parsed_value

            if invalid_rows:
                invalid_preview = ", ".join(invalid_rows[:3])
                if len(invalid_rows) > 3:
                    invalid_preview += f" és még {len(invalid_rows) - 3} tétel"
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"Hibás mennyiséget kaptam ezeknél a tételeknél: {invalid_preview}.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            source_parts_file = str(metadata.get("source_parts_file", "")).strip() or str(metadata.get("source_average_file", "")).strip()
            if source_parts_file:
                parts_path = job_dir / source_parts_file
                if not parts_path.exists():
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message="A feltöltött friss alkatrészlistát nem találom, ezért a jóváhagyást most nem tudom ellenőrizni.",
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                try:
                    allowed_parts = {
                        _normalize_nettfront_part_number(item)
                        for item in _load_nettfront_parts_list_from_bytes(parts_path.read_bytes(), parts_path.name)
                    }
                except Exception as exc:
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message=f"A friss alkatrészlista ellenőrzése nem sikerült: {exc}",
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                missing_parts: list[str] = []
                seen_missing: set[str] = set()
                for row in rows:
                    if _order_safe_number(row.order_qty) <= 0:
                        continue
                    aliases = _nettfront_order_part_number_aliases(row.part_number)
                    if not aliases:
                        continue
                    if any(alias in allowed_parts for alias in aliases):
                        continue
                    display_part = _nettfront_order_display_part_number(row.part_number) or row.part_number or row.description or row.row_id
                    normalized_display = _normalize_nettfront_part_number(display_part)
                    if normalized_display in seen_missing:
                        continue
                    seen_missing.add(normalized_display)
                    missing_parts.append(display_part)

                if missing_parts:
                    missing_preview = ", ".join(missing_parts[:4])
                    if len(missing_parts) > 4:
                        missing_preview += f" és még {len(missing_parts) - 4} tétel"
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message=(
                            "A jóváhagyás most nem ment végig, mert ezek a cikkszámok nem szerepelnek a friss alkatrészlistában: "
                            f"{missing_preview}."
                        ),
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            try:
                metadata = _persist_nettfront_order_approval(job_dir, metadata, rows)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A kész rendelés mentése nem sikerült: {exc}",
                )
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_nettfront_order_result(
                job_id,
                metadata,
                message="A kész rendelés elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_PROCUREMENT_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            invoice_file = files.get("invoice_pdf")
            parts_file = files.get("parts_file")

            if invoice_file is None:
                self.respond_nettfront_procurement_form("A NettFront számla PDF feltöltése kötelező.")
                return

            invoice_name, invoice_bytes = invoice_file
            if not invoice_name.lower().endswith(".pdf"):
                self.respond_nettfront_procurement_form("Csak PDF számla tölthető fel.")
                return

            uploaded_parts_name = ""
            uploaded_parts_bytes: bytes | None = None
            merged_map = None
            if parts_file is not None:
                uploaded_parts_name, uploaded_parts_bytes = parts_file
                if not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                    self.respond_nettfront_procurement_form("Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")
                    return
                try:
                    merged_map = load_alkatresz_map()
                    merged_map.update(load_alkatresz_map_from_bytes(uploaded_parts_bytes, uploaded_parts_name))
                except Exception as exc:
                    self.respond_nettfront_procurement_form(f"Az alkatrészlista feldolgozása nem sikerült: {exc}")
                    return

            try:
                artifacts = build_procurement_artifacts(invoice_bytes, alkatresz_map=merged_map)
                job_id, metadata = _write_procurement_job(
                    artifacts,
                    invoice_name,
                    invoice_bytes,
                    uploaded_parts_name=uploaded_parts_name,
                    uploaded_parts_bytes=uploaded_parts_bytes,
                )
            except Exception as exc:
                self.respond_nettfront_procurement_form(f"Hiba a feldolgozás során: {exc}")
                return

            message = ""
            success = False
            if not metadata.get("missing_codes"):
                job_dir = _job_runtime_dir("procurement") / job_id
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    message = " ".join(messages)
                except Exception as exc:
                    message = f"Az import-segéd automatikus indítása nem sikerült: {exc}"
                    success = False

            body = render_nettfront_procurement_result(job_id, metadata, message=message, success=success)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_LAUNCH_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            if not str(metadata.get("approved_file", "")).strip():
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message="Előbb jóvá kell hagynod a rendelést, és csak utána indítható a bevételezés.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            try:
                success, messages = launch_procurement_helper(job_dir)
                message = " ".join(messages) if messages else "A bevételezési segéd elindult."
                body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A bevételezési segéd indítása nem sikerült: {exc}",
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_STOP_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            try:
                success, messages = stop_procurement_helper(job_dir)
                message = " ".join(messages) if messages else "A bevételezési segéd leállt."
                body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A leállítás nem sikerült: {exc}",
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_PARTS_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_PARTS_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            parts_file = files.get("parts_file")

            if parts_file is None:
                body = render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista feltöltése kötelező.")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            parts_name, parts_bytes = parts_file
            if not parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                body = render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            source_invoice_file = str(metadata.get("source_invoice_file", "source-invoice.pdf")).strip() or "source-invoice.pdf"
            source_invoice_path = job_dir / source_invoice_file
            if not source_invoice_path.exists():
                body = render_nettfront_procurement_result(
                    job_id,
                    metadata,
                    message="Ehhez a korábbi futáshoz nem találom a forrásszámlát. Töltsd fel újra a számlát.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            try:
                merged_map = load_alkatresz_map()
                merged_map.update(load_alkatresz_map_from_bytes(parts_bytes, parts_name))
                artifacts = build_procurement_artifacts(source_invoice_path.read_bytes(), alkatresz_map=merged_map)
                metadata = _persist_procurement_job(job_dir, metadata, artifacts, uploaded_parts_name=parts_name, uploaded_parts_bytes=parts_bytes)
            except Exception as exc:
                body = render_nettfront_procurement_result(job_id, metadata, message=f"Az alkatrészlista feldolgozása nem sikerült: {exc}")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if metadata.get("missing_codes"):
                message = f"Az alkatrészlista bekerült. Még {len(metadata.get('missing_codes', []))} hiányzó kód maradt."
                success = False
            else:
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    message = "Az alkatrészlista bekerült. " + " ".join(messages)
                except Exception as exc:
                    message = f"Az alkatrészlista bekerült, de az import-segéd automatikus indítása nem sikerült: {exc}"
                    success = False

            body = render_nettfront_procurement_result(job_id, metadata, message=message, success=success)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_COMPARE_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            invoice_file = files.get("invoice_pdf")
            order_file = files.get("order_file")

            if invoice_file is None or order_file is None:
                self.respond_nettfront_compare_form("A számla PDF és a meglévő rendelési fájl feltöltése is kötelező.")
                return

            invoice_name, invoice_bytes = invoice_file
            if not invoice_name.lower().endswith(".pdf"):
                self.respond_nettfront_compare_form("Csak PDF számla tölthető fel.")
                return

            order_name, order_bytes = order_file
            allowed_order_extensions = (".xlsx", ".xlsm", ".csv")
            if not order_name.lower().endswith(allowed_order_extensions):
                self.respond_nettfront_compare_form("A meglévő rendelés csak XLSX, XLSM vagy CSV fájl lehet.")
                return

            try:
                artifacts = build_compare_artifacts(invoice_bytes, order_bytes)
                job_id, metadata = _write_compare_job(artifacts)
            except Exception as exc:
                self.respond_nettfront_compare_form(f"Hiba az összehasonlítás során: {exc}")
                return

            body = render_nettfront_compare_result(job_id, metadata)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            if metadata.get("missing_codes"):
                body = render_nettfront_procurement_result(
                    job_id,
                    metadata,
                    message="Hiányzó kódok vannak. Előbb tölts fel alkatrészlistát a Beszerzés újraépítéséhez.",
                )
                status_code = 400
            else:
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
                    status_code = 200
                except Exception as exc:
                    body = render_nettfront_procurement_result(job_id, metadata, message=f"A launch nem sikerült: {exc}")
                    status_code = 500

            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_STOP_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            try:
                success, messages = stop_procurement_helper(job_dir)
                body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
                status_code = 200 if success else 400
            except Exception as exc:
                body = render_nettfront_procurement_result(job_id, metadata, message=f"A leállítás nem sikerült: {exc}")
                status_code = 500

            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path != GENERATE_ROUTE:
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        file_name, file_data = _extract_uploaded_pdf(self.headers, raw_body)

        if not file_data or not file_name:
            self.respond_form("Hibás kérés: hiányzó feltöltési adatok.")
            return

        if not file_name.lower().endswith(".pdf"):
            self.respond_form("Csak PDF fájl tölthető fel.")
            return

        try:
            status, payload, content_type, headers = _build_invoice_response(file_name, file_data)
        except MissingInvoiceDataError as exc:
            self.respond_form(str(exc))
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for header_name, header_value in headers.items():
            self.send_header(header_name, header_value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def respond_form(self, message: str):
        body = render_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_procurement_form(self, message: str):
        body = render_nettfront_procurement_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_order_form(self, message: str):
        body = render_nettfront_order_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_matt_inventory_form(self, message: str):
        body = render_matt_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_material_inventory_form(self, message: str):
        body = render_material_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_semifinished_inventory_form(self, message: str):
        body = render_material_inventory_form(message, inventory_kind="semifinished")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_semifinished_front_inventory_form(self, message: str):
        body = render_material_inventory_form(message, inventory_kind="semifinished_front")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_front_inventory_form(self, message: str):
        body = render_front_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_compare_form(self, message: str):
        body = render_nettfront_compare_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_vacation_calendar(self, message: str, month_value: str = ""):
        body = render_vacation_calendar(month_value=month_value, message=message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)




def _prime_manufacturing_cache_worker(*, include_all_red_view: bool = False, limit: int = 10) -> None:
    try:
        entries = available_production_entries(limit=12, ready_only=True)
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
                current_selection_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, number)
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
    threading.Thread(
        target=_prime_manufacturing_cache_worker,
        kwargs={"include_all_red_view": True, "limit": 10},
        name="manufacturing-prime",
        daemon=True,
    ).start()


if __name__ == "__main__":
    if DEV_RELOAD_ENABLED and os.getenv(DEV_CHILD_ENV) != "1":
        _run_dev_supervisor()
    else:
        if MANUFACTURING_PRIME_SYNC_ON_START:
            _prime_manufacturing_cache_worker(include_all_red_view=False, limit=10)
        _prime_manufacturing_cache_async()
        server = ReusableThreadingHTTPServer((HOST, PORT), InvoiceHandler)
        print(f"Server running on http://localhost:{PORT} (bind: {HOST}:{PORT})")
        server.serve_forever()
