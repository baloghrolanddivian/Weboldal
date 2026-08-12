"""Page-level HTTP router and application entry point for Divian-HUB."""

from __future__ import annotations

import html
import hashlib
import io
import json
import os
import re
import sys
import time
import threading
import urllib.parse
import zipfile
import csv
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PYCODE_DIR = Path(__file__).resolve().parent / "pycode"
if str(PYCODE_DIR) not in sys.path:
    sys.path.insert(0, str(PYCODE_DIR))

try:
    import winreg
except Exception:  # pragma: no cover - Windows-only optional import
    winreg = None

from manufacturing import (
    MANUFACTURING_ACCESS_USER_IDS,
    MANUFACTURING_ADMIN_REVISION_ROUTE,
    MANUFACTURING_DATA_ROUTE,
    MANUFACTURING_ISSUED_EDIT_COMPLETE_ROUTE,
    MANUFACTURING_OPERATION_DEFINITIONS,
    MANUFACTURING_PARTIAL_QTY_ROUTE,
    MANUFACTURING_PRIME_SYNC_ON_START,
    MANUFACTURING_REPORT_READY_ROUTE,
    MANUFACTURING_ROUTE,
    MANUFACTURING_STATE_ROUTE,
    MANUFACTURING_TOPFLOOR_BOX_ROUTE,
    _load_manufacturing_bundle_cached,
    _manufacturing_is_virtual_unit_row_id,
    _manufacturing_normalize_number,
    _manufacturing_operation_state_keys,
    _manufacturing_query_params,
    _manufacturing_ready_endpoint_key,
    _manufacturing_selection_state_payload,
    _manufacturing_topfloor_aggregate_bundle,
    _manufacturing_view_bundle,
    _prime_manufacturing_cache_async,
    _prime_manufacturing_cache_worker,
    configure_manufacturing,
    complete_issued_row_edit,
    load_partial_quantity_state,
    load_selection_state,
    manufacturing_client_payload,
    manufacturing_module_payload,
    render_manufacturing_module,
    runtime_dir as manufacturing_runtime_dir,
    save_partial_quantity_state,
    save_selection_state,
)
from manufacturing.admin import (
    MANUFACTURING_DATA_ROUTE as ADMIN_MANUFACTURING_DATA_ROUTE,
    MANUFACTURING_ROW_DATA_ROUTE as ADMIN_MANUFACTURING_ROW_DATA_ROUTE,
    MANUFACTURING_SHIPMENT_DATE_ROUTE as ADMIN_MANUFACTURING_SHIPMENT_DATE_ROUTE,
    MANUFACTURING_ROUTE as ADMIN_MANUFACTURING_ROUTE,
    configure_manufacturing as configure_admin_manufacturing,
    manufacturing_client_payload as admin_manufacturing_client_payload,
    manufacturing_module_payload as admin_manufacturing_module_payload,
    load_admin_change_revision as load_admin_manufacturing_change_revision,
    manufacturing_row_requires_edit_alert as admin_manufacturing_row_requires_edit_alert,
    render_manufacturing_module as render_admin_manufacturing_module,
    runtime_dir as admin_manufacturing_runtime_dir,
    save_issued_row_edit_marker as save_admin_manufacturing_issued_row_edit_marker,
    save_row_data as save_admin_manufacturing_row_data,
    save_shipment_date as save_admin_manufacturing_shipment_date,
    signal_admin_change as signal_admin_manufacturing_change,
    topfloor_row_requires_edit_alert as admin_manufacturing_topfloor_row_requires_edit_alert,
)
from matt_inventory import (
    MATT_INVENTORY_ACCESS_USER_IDS,
    MATT_INVENTORY_DOWNLOAD_ROUTE,
    MATT_INVENTORY_PROCESS_ROUTE,
    MATT_INVENTORY_ROUTE,
    configure_matt_inventory,
    matt_inventory_alert_download_payload,
    process_matt_inventory_upload,
    render_matt_inventory_form,
)
from leltar.group_pages import render_inventory_group_page
from leltar.routes import (
    ADMIN_INVENTORY_ACCESS_USER_IDS,
    ADMIN_FRONT_INVENTORY_ROUTE,
    ADMIN_INVENTORY_GROUP_ROUTE,
    ADMIN_MATERIAL_INVENTORY_ROUTE,
    ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE,
    ADMIN_SEMIFINISHED_INVENTORY_ROUTE,
    FRONT_INVENTORY_ALERT_CLEAR_ROUTE,
    FRONT_INVENTORY_CHECK_DOWNLOAD_ROUTE,
    FRONT_INVENTORY_CHECK_ROUTE,
    FRONT_INVENTORY_FINALIZE_ROUTE,
    FRONT_INVENTORY_INSIGHT_EXCEL_DOWNLOAD_ROUTE,
    FRONT_INVENTORY_INSIGHT_SCRIPT_DOWNLOAD_ROUTE,
    FRONT_INVENTORY_LEGACY_WORKER_ROUTE,
    FRONT_INVENTORY_MISSING_ROUTE,
    FRONT_INVENTORY_PRESENCE_ROUTE,
    FRONT_INVENTORY_PROCESS_ROUTE,
    FRONT_INVENTORY_ROUTE,
    FRONT_INVENTORY_STATE_ROUTE,
    FRONT_INVENTORY_WORKER_ROUTE,
    MATERIAL_INVENTORY_FINALIZE_ROUTE,
    MATERIAL_INVENTORY_INSIGHT_DOWNLOAD_ROUTE,
    MATERIAL_INVENTORY_LEGACY_WORKER_ROUTE,
    MATERIAL_INVENTORY_PRESENCE_ROUTE,
    MATERIAL_INVENTORY_PROCESS_ROUTE,
    MATERIAL_INVENTORY_ROUTE,
    MATERIAL_INVENTORY_STATE_ROUTE,
    MATERIAL_INVENTORY_SUMMARY_DOWNLOAD_ROUTE,
    MATERIAL_INVENTORY_WORKER_ROUTE,
    PRODUCTION_INVENTORY_GROUP_ROUTE,
    PRODUCTION_INVENTORY_ACCESS_USER_IDS,
    SEMIFINISHED_FRONT_INVENTORY_FINALIZE_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_INSIGHT_DOWNLOAD_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_LEGACY_WORKER_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_PRESENCE_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_PROCESS_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_SUMMARY_DOWNLOAD_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE,
    SEMIFINISHED_INVENTORY_FINALIZE_ROUTE,
    SEMIFINISHED_INVENTORY_INSIGHT_DOWNLOAD_ROUTE,
    SEMIFINISHED_INVENTORY_LEGACY_WORKER_ROUTE,
    SEMIFINISHED_INVENTORY_PRESENCE_ROUTE,
    SEMIFINISHED_INVENTORY_PROCESS_ROUTE,
    SEMIFINISHED_INVENTORY_ROUTE,
    SEMIFINISHED_INVENTORY_STATE_ROUTE,
    SEMIFINISHED_INVENTORY_SUMMARY_DOWNLOAD_ROUTE,
    SEMIFINISHED_INVENTORY_WORKER_ROUTE,
)
from leltar.types.front import (
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
from leltar.types.material import (
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
from nettfront.procurement import (
    NETTFRONT_PROCUREMENT_ACCESS_USER_IDS,
    NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX,
    NETTFRONT_PROCUREMENT_LAUNCH_PREFIX,
    NETTFRONT_PROCUREMENT_PARTS_PREFIX,
    NETTFRONT_PROCUREMENT_PROCESS_ROUTE,
    NETTFRONT_PROCUREMENT_ROUTE,
    NETTFRONT_PROCUREMENT_STOP_PREFIX,
    configure_nettfront_procurement,
    launch_procurement_job,
    procurement_download_payload,
    process_procurement_upload,
    rebuild_procurement_parts,
    render_nettfront_procurement_form,
    stop_procurement_job,
)
from nettfront.compare import (
    NETTFRONT_COMPARE_ACCESS_USER_IDS,
    NETTFRONT_COMPARE_DOWNLOAD_PREFIX,
    NETTFRONT_COMPARE_PROCESS_ROUTE,
    NETTFRONT_COMPARE_ROUTE,
    compare_download_payload,
    configure_nettfront_compare,
    process_compare_upload,
    render_nettfront_compare_form,
)
from nettfront.order import (
    NETTFRONT_ORDER_ACCESS_USER_IDS,
    NETTFRONT_ORDER_APPROVE_PREFIX,
    NETTFRONT_ORDER_DOWNLOAD_PREFIX,
    NETTFRONT_ORDER_LAUNCH_PREFIX,
    NETTFRONT_ORDER_PROCESS_ROUTE,
    NETTFRONT_ORDER_ROUTE,
    NETTFRONT_ORDER_STOP_PREFIX,
    approve_order_job,
    configure_nettfront_order,
    launch_order_job,
    order_download_payload,
    process_order_upload,
    render_nettfront_order_form,
    stop_order_job,
)
from invoice_translator import (
    APP_ROUTE,
    GENERATE_ROUTE,
    INVOICE_TRANSLATOR_ACCESS_USER_IDS,
    MissingInvoiceDataError,
    build_invoice_response,
    extract_invoice_upload,
    render_form,
)
from hr import (
    APP_ROUTE as HR_APP_ROUTE,
    CONFIRM_ROUTE as HR_CONFIRM_ROUTE,
    HR_ACCESS_USER_IDS,
    HR_COLUMNS as HR_DATA_COLUMNS,
    build_hr_documents,
    read_people,
    render_form as render_hr_form,
    render_review as render_hr_review,
)
from tools.dev_reload import dev_reload_token, run_dev_supervisor
from tools.datetime_format import format_hungarian_timestamp as _front_inventory_format_timestamp
from tools.html_helpers import json_script_payload as _json_script_payload
from tools.html_helpers import render_file_bind_script as _render_file_bind_script
from tools.http import extract_uploaded_files as _extract_uploaded_files
from tools.http import normalize_path as _normalize_path
from tools.http import parse_urlencoded_body as _parse_urlencoded_body
from tools.inventory_sort import inventory_sort_key as _unified_inventory_sort_key
from tools.inventory_sort import normalize_inventory_sort as _unified_inventory_normalize_sort
from tools.json_store import read_json_object as _matt_inventory_read_meta
from tools.json_store import write_json_object as _matt_inventory_write_meta
from tools.login import (
    MAX_PASSWORD_LENGTH,
    AuthUser,
    authenticate_password,
    ensure_login_database,
    make_login_cookie,
    make_logout_cookie,
    user_from_cookie,
)
from tools.shopfloor import extract_con_code as _extract_con_code
from tools.shopfloor import ShopfloorApiClient as _ShopfloorApiClient
from tools.shopfloor import report_con_ready as _shopfloor_report_con_ready
from tools.shopfloor import (
    create_closed_topfloor_category_box as _topfloor_create_category_box,
    issue_topfloor_storage_box as _topfloor_issue_storage_box,
    load_and_close_topfloor_category_box as _topfloor_load_and_close_category_box,
    open_topfloor_category_box as _topfloor_open_category_box,
    reprint_topfloor_category_label as _topfloor_reprint_category_label,
)
from tools.static_assets import load_static_asset

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - optional dependency handling
    load_workbook = None


HOST = "0.0.0.0"
PORT = int(os.getenv("DIVIAN_HUB_PORT", "5000"))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGIN_DB_PATH = DATA_DIR / "login.db"
RUNTIME_DIR = BASE_DIR / "runtime"
LOGIN_ROUTE = "/login"
configure_manufacturing(RUNTIME_DIR / "gyartasi-papirok")
configure_admin_manufacturing(RUNTIME_DIR / "gyartasi-papirok")
ensure_login_database(LOGIN_DB_PATH)
DEV_RELOAD_ROUTE = "/__dev__/events"
DEV_CHILD_ENV = "DIVIAN_HUB_DEV_CHILD"
DEV_RELOAD_TOKEN_ENV = "DIVIAN_HUB_RELOAD_TOKEN"
DEV_RELOAD_ENABLED = os.getenv("DIVIAN_HUB_DEV_RELOAD", "1") != "0"
DEV_WATCH_INTERVAL_SECONDS = 0.75
DEV_EVENT_HEARTBEAT_SECONDS = 10
WATCHED_EXTENSIONS = {".py", ".html", ".css", ".js", ".json", ".xlsx", ".xlsm", ".csv"}
WATCHED_FILES = {"requirements.txt"}
WATCH_IGNORED_DIRS = {".git", "__pycache__", "runtime", ".venv", "venv", "node_modules"}
APP_VERSION = "2.1.6"
STANDARD_ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo"})
ADMIN_MANUFACTURING_ACCESS_USER_IDS = frozenset({"gyartas-vezerlo"})
HR_THEME_USER_ID = "hriroda"
PRODUCTION_CONTROLLER_THEME_USER_ID = "gyartas-vezerlo"
ADMIN_THEME_CLASS = b"admin-theme"
ADMIN_THEME_CLASS_SUFFIX = b" admin-theme"

def apply_user_theme(body: bytes, user) -> bytes:
    """Add the per-user visual theme class to an HTML response body."""
    body_match = re.search(br"<body([^>]*)>", body, flags=re.IGNORECASE)
    if body_match and re.search(
        br'\sdata-theme-scope=(?:"default"|\'default\')',
        body_match.group(1),
        flags=re.IGNORECASE,
    ):
        return body
    theme_class = None
    if user is not None and user.is_admin:
        theme_class = ADMIN_THEME_CLASS
    elif user is not None and user.user_id == HR_THEME_USER_ID:
        theme_class = b"hr-theme"
    elif user is not None and user.user_id == PRODUCTION_CONTROLLER_THEME_USER_ID:
        theme_class = b"production-controller-theme"
    if theme_class is not None:
        if not body_match:
            return body
        attributes = body_match.group(1)
        class_match = re.search(br'\sclass=("[^"]*"|\'[^\']*\')', attributes, flags=re.IGNORECASE)
        if class_match:
            quote = class_match.group(1)[:1]
            existing_classes = class_match.group(1)[1:-1]
            if re.search(br"(?:^|\s)" + re.escape(theme_class) + br"(?:\s|$)", existing_classes):
                return body
            classes = existing_classes + b" " + theme_class
            replacement = attributes[:class_match.start(1)] + quote + classes + quote + attributes[class_match.end(1):]
            return body[:body_match.start(1)] + replacement + body[body_match.end(1):]
        return body[:body_match.end(1)] + b' class="' + theme_class + b'"' + body[body_match.end(1):]
    return body


def apply_hr_theme(body: bytes, user) -> bytes:
    """Backward-compatible HR-only theme helper for HR render paths."""
    if user is not None and user.user_id == HR_THEME_USER_ID:
        return apply_user_theme(body, user)
    return body


class _ThemedResponseWriter:
    """Apply the current user's theme to HTML at the final response boundary."""

    def __init__(self, raw_writer, user):
        self._raw_writer = raw_writer
        self._user = user

    def write(self, body):
        self._raw_writer.write(apply_user_theme(body, self._user))

    def __getattr__(self, name):
        return getattr(self._raw_writer, name)


NETTFRONT_ROUTE = "/apps/nettfront-olvaso"
NETTFRONT_PROCESS_ROUTE = f"{NETTFRONT_ROUTE}/process"
NETTFRONT_DOWNLOAD_PREFIX = f"{NETTFRONT_ROUTE}/download"
NETTFRONT_LAUNCH_PREFIX = f"{NETTFRONT_ROUTE}/launch"
NETTFRONT_RUNTIME_DIR = RUNTIME_DIR / "nettfront"
NETTFRONT_ORDER_DEFAULT_AVG_PATH = BASE_DIR / "data" / "nettfront-rendeles-atlag.xlsx"
COMMON_SCRIPT_TAG = '<script src="/script.js"></script>'
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
MATERIAL_INVENTORY_PRESENCE_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "presence.json"
MATERIAL_INVENTORY_INSIGHT_WORKBOOK_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
MATERIAL_INVENTORY_INSIGHT_META_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
MATERIAL_INVENTORY_SUMMARY_WORKBOOK_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
MATERIAL_INVENTORY_SUMMARY_META_PATH = MATERIAL_INVENTORY_RUNTIME_DIR / "osszesito.json"
SEMIFINISHED_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "felkesz-raktar"
SEMIFINISHED_INVENTORY_SESSION_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "session.json"
SEMIFINISHED_INVENTORY_STOCK_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "latest-stock.json"
SEMIFINISHED_INVENTORY_PRESENCE_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "presence.json"
SEMIFINISHED_INVENTORY_INSIGHT_WORKBOOK_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
SEMIFINISHED_INVENTORY_INSIGHT_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
SEMIFINISHED_INVENTORY_SUMMARY_WORKBOOK_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
SEMIFINISHED_INVENTORY_SUMMARY_META_PATH = SEMIFINISHED_INVENTORY_RUNTIME_DIR / "osszesito.json"
SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR = RUNTIME_DIR / "felkesz-front"
SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "session.json"
SEMIFINISHED_FRONT_INVENTORY_STOCK_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "latest-stock.json"
SEMIFINISHED_FRONT_INVENTORY_PRESENCE_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "presence.json"
SEMIFINISHED_FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.xlsx"
SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "insight-bevetelezes.json"
SEMIFINISHED_FRONT_INVENTORY_SUMMARY_WORKBOOK_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "osszesito.xlsx"
SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH = SEMIFINISHED_FRONT_INVENTORY_RUNTIME_DIR / "osszesito.json"


AUTH_ROUTE_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    (APP_ROUTE, INVOICE_TRANSLATOR_ACCESS_USER_IDS),
    (GENERATE_ROUTE, INVOICE_TRANSLATOR_ACCESS_USER_IDS),
    (HR_APP_ROUTE, HR_ACCESS_USER_IDS),
    (HR_CONFIRM_ROUTE, HR_ACCESS_USER_IDS),
    (MANUFACTURING_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_DATA_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_ISSUED_EDIT_COMPLETE_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_ADMIN_REVISION_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_STATE_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_PARTIAL_QTY_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_REPORT_READY_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MANUFACTURING_TOPFLOOR_BOX_ROUTE, STANDARD_ACCESS_USER_IDS),
    (ADMIN_MANUFACTURING_ROUTE, ADMIN_MANUFACTURING_ACCESS_USER_IDS),
    (PRODUCTION_INVENTORY_GROUP_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_WORKER_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_LEGACY_WORKER_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_STATE_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_PRESENCE_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_ALERT_CLEAR_ROUTE, STANDARD_ACCESS_USER_IDS),
    (FRONT_INVENTORY_MISSING_ROUTE, STANDARD_ACCESS_USER_IDS),
    (MATERIAL_INVENTORY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (MATERIAL_INVENTORY_LEGACY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (MATERIAL_INVENTORY_STATE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (MATERIAL_INVENTORY_PRESENCE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_INVENTORY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_INVENTORY_LEGACY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_INVENTORY_STATE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_INVENTORY_PRESENCE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_FRONT_INVENTORY_LEGACY_WORKER_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_FRONT_INVENTORY_PRESENCE_ROUTE, PRODUCTION_INVENTORY_ACCESS_USER_IDS),
    (ADMIN_INVENTORY_GROUP_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (FRONT_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (ADMIN_FRONT_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (MATERIAL_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (ADMIN_MATERIAL_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (ADMIN_SEMIFINISHED_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (SEMIFINISHED_FRONT_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE, ADMIN_INVENTORY_ACCESS_USER_IDS),
    (NETTFRONT_ROUTE, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_ROUTE, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_PROCESS_ROUTE, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_LAUNCH_PREFIX, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_PARTS_PREFIX, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_PROCUREMENT_STOP_PREFIX, NETTFRONT_PROCUREMENT_ACCESS_USER_IDS),
    (NETTFRONT_COMPARE_ROUTE, NETTFRONT_COMPARE_ACCESS_USER_IDS),
    (NETTFRONT_COMPARE_PROCESS_ROUTE, NETTFRONT_COMPARE_ACCESS_USER_IDS),
    (NETTFRONT_COMPARE_DOWNLOAD_PREFIX, NETTFRONT_COMPARE_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_ROUTE, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_PROCESS_ROUTE, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_DOWNLOAD_PREFIX, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_LAUNCH_PREFIX, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_APPROVE_PREFIX, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (NETTFRONT_ORDER_STOP_PREFIX, NETTFRONT_ORDER_ACCESS_USER_IDS),
    (MATT_INVENTORY_ROUTE, MATT_INVENTORY_ACCESS_USER_IDS),
    (MATT_INVENTORY_PROCESS_ROUTE, MATT_INVENTORY_ACCESS_USER_IDS),
    (MATT_INVENTORY_DOWNLOAD_ROUTE, MATT_INVENTORY_ACCESS_USER_IDS),
)

def _route_matches(path: str, route: str) -> bool:
    """Return whether a request path belongs to a route or route prefix."""
    return path == route or path.startswith(route.rstrip("/") + "/")


def _can_access_path(user: AuthUser, path: str) -> bool:
    """Return whether a user can access a server path."""
    if user.is_admin:
        return True
    if not path.startswith("/apps/"):
        return True
    for route, allowed_user_ids in sorted(AUTH_ROUTE_RULES, key=lambda item: len(item[0]), reverse=True):
        if _route_matches(path, route):
            return user.user_id in allowed_user_ids
    return False


def _login_notice_html(raw_path: str) -> str:
    """Return the login status notice for the home page."""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(raw_path).query)
    status = str(query.get("login", [""])[0] or "")
    if status == "too_long":
        text = "Hibas jelszo."
    elif status == "failed":
        text = "Hibas jelszo."
    elif status == "ok":
        text = "Sikeres belepes."
    elif status == "default":
        text = "Alap felhasznalo aktiv."
    else:
        return ""
    return f'<span class="login-notice">{html.escape(text)}</span>'


def _login_form_html(user: AuthUser, raw_path: str) -> str:
    """Render the compact header login form."""
    user_label = html.escape(user.display_name)
    return f"""
        <form class="login-form" action="{LOGIN_ROUTE}" method="post" autocomplete="off">
          <span class="login-user">Felhasznalo: <strong>{user_label}</strong></span>
          {_login_notice_html(raw_path)}
          <input type="password" name="password" maxlength="{MAX_PASSWORD_LENGTH}" placeholder="Jelszo" aria-label="Jelszo" />
          <button type="submit">Belepes</button>
          <button type="submit" name="logout" value="1">Alap</button>
        </form>
"""


def render_home_page(user: AuthUser, raw_path: str = "/") -> bytes:
    """Render the home page with only the modules available to the user."""
    page = (BASE_DIR / "index.html").read_text(encoding="utf-8")
    if user.user_id == HR_THEME_USER_ID:
        page = page.replace('<body>', '<body class="hr-theme">', 1)
    elif user.user_id == PRODUCTION_CONTROLLER_THEME_USER_ID:
        page = page.replace('<body>', '<body class="production-controller-theme">', 1)
    page = _filter_home_module_cards(page, user)
    page = page.replace("{{APP_VERSION}}", html.escape(APP_VERSION), 1)
    page = page.replace("</header>", _login_form_html(user, raw_path) + "\n      </header>", 1)
    return page.encode("utf-8")


def _filter_home_module_cards(page: str, user: AuthUser) -> str:
    """Remove module cards the current user cannot access."""
    card_pattern = re.compile(r"\s*<article class=\"module-card reveal\">.*?</article>", re.DOTALL)
    kept_any = False

    def replace_card(match: re.Match[str]) -> str:
        nonlocal kept_any
        card = match.group(0)
        href_match = re.search(r'href="([^"]+)"', card)
        href = href_match.group(1) if href_match else ""
        path = urllib.parse.urlsplit(href).path
        if path.startswith("/apps/") and _can_access_path(user, path):
            kept_any = True
            return card
        return ""

    filtered = card_pattern.sub(replace_card, page)
    if kept_any:
        return filtered

    empty_html = """
            <article class="module-card reveal">
              <div class="module-top">
                <div class="module-status">Nincs eleres</div>
                <div class="module-number">--</div>
              </div>
              <h3>Nincs elerheto modul</h3>
              <p>Jelentkezz be olyan jelszoval, amelyhez modul jogosultsag tartozik.</p>
            </article>
"""
    return filtered.replace('<div class="module-grid">', '<div class="module-grid">\n' + empty_html, 1)


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
    """Render the shared NettFront module layout shell."""
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

    }}
    @media (max-width: 760px) {{
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


configure_nettfront_procurement(NETTFRONT_RUNTIME_DIR / "procurement", _render_nettfront_layout)
configure_nettfront_order(NETTFRONT_RUNTIME_DIR / "order", NETTFRONT_ORDER_DEFAULT_AVG_PATH, _render_nettfront_layout)
configure_matt_inventory(RUNTIME_DIR / "matt-raktarertek", _render_nettfront_layout)


def render_nettfront_form(message: str = "") -> bytes:
    """Render the legacy combined NettFront upload form."""
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
    """Render the legacy NettFront processing result page."""
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


configure_nettfront_compare(NETTFRONT_RUNTIME_DIR / "compare", _render_nettfront_layout, _render_file_bind_script)


def render_nettfront_hub(message: str = "") -> bytes:
    """Render the NettFront hub that links to split workflows."""
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









def _front_inventory_saved_stock_name() -> str:
    """Return the original filename for the active front inventory stock upload."""
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _front_inventory_saved_check_report_name() -> str:
    """Return the download name for the generated front inventory check report."""
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_CHECK_REPORT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _front_inventory_saved_insight_meta() -> dict:
    """Return metadata for generated front inventory inSight artifacts."""
    meta = _matt_inventory_read_meta(FRONT_INVENTORY_INSIGHT_META_PATH)
    return meta if isinstance(meta, dict) else {}


def _front_inventory_saved_insight_workbook_name() -> str:
    """Return the generated front inventory inSight workbook filename."""
    return str(_front_inventory_saved_insight_meta().get("workbook_name", "")).strip()


def _front_inventory_saved_insight_script_name() -> str:
    """Return the generated front inventory inSight script filename."""
    return str(_front_inventory_saved_insight_meta().get("script_name", "")).strip()


def _front_inventory_clear_generated_artifacts() -> None:
    """Remove front inventory reports generated from an older session."""
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
    """Build and persist front inventory inSight workbook/script artifacts."""
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
    """Regenerate missing inSight artifacts for a finalized front session."""
    if session is None or str(session.get("phase")) != "finalized":
        return
    if FRONT_INVENTORY_INSIGHT_WORKBOOK_PATH.exists() and FRONT_INVENTORY_INSIGHT_SCRIPT_PATH.exists():
        return
    try:
        _front_inventory_store_insight_artifacts(session)
    except Exception:
        return


def _material_inventory_saved_stock_name() -> str:
    """Return the original filename for the active material stock upload."""
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _material_inventory_saved_insight_name() -> str:
    """Return the generated material inSight workbook filename."""
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _material_inventory_saved_summary_name() -> str:
    """Return the generated material summary workbook filename."""
    meta = _matt_inventory_read_meta(MATERIAL_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _material_inventory_clear_generated_artifacts() -> None:
    """Remove generated material inventory export files and metadata."""
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
    """Build and persist material inventory inSight and summary workbooks."""
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
    """Backfill book quantities from the latest material stock upload."""
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
    """Return the original filename for the active semifinished stock upload."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _semifinished_inventory_saved_insight_name() -> str:
    """Return the generated semifinished inSight workbook filename."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_inventory_saved_summary_name() -> str:
    """Return the generated semifinished summary workbook filename."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_inventory_clear_generated_artifacts() -> None:
    """Remove generated semifinished inventory export files and metadata."""
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
    """Build and persist semifinished inventory export workbooks."""
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
    """Return the original filename for the active semifinished-front upload."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_STOCK_META_PATH)
    return str(meta.get("original_name", "")).strip()


def _semifinished_front_inventory_saved_insight_name() -> str:
    """Return the generated semifinished-front inSight workbook filename."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_INSIGHT_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_front_inventory_saved_summary_name() -> str:
    """Return the generated semifinished-front summary workbook filename."""
    meta = _matt_inventory_read_meta(SEMIFINISHED_FRONT_INVENTORY_SUMMARY_META_PATH)
    return str(meta.get("download_name", "")).strip()


def _semifinished_front_inventory_clear_generated_artifacts() -> None:
    """Remove generated semifinished-front export files and metadata."""
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
    """Build and persist semifinished-front inventory export workbooks."""
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


def _material_inventory_worker_route(inventory_kind: str) -> str:
    """Return the worker/counting route for a material-like inventory kind."""
    clean_inventory_kind = str(inventory_kind or "").strip().lower()
    if clean_inventory_kind == "semifinished_front":
        return SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE
    if clean_inventory_kind == "semifinished":
        return SEMIFINISHED_INVENTORY_WORKER_ROUTE
    return MATERIAL_INVENTORY_WORKER_ROUTE


def _material_inventory_admin_route(inventory_kind: str) -> str:
    """Return the admin route for a material-like inventory kind."""
    clean_inventory_kind = str(inventory_kind or "").strip().lower()
    if clean_inventory_kind == "semifinished_front":
        return ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE
    if clean_inventory_kind == "semifinished":
        return ADMIN_SEMIFINISHED_INVENTORY_ROUTE
    return ADMIN_MATERIAL_INVENTORY_ROUTE


def _material_inventory_normalize_view(value: str) -> str:
    """Normalize material inventory view mode to admin or leltar."""
    return "leltar" if str(value or "").strip().lower() == "leltar" else "admin"


def render_material_inventory_form(
    message: str = "",
    success: bool = False,
    selected_category: str = "",
    view_mode: str = "admin",
    auto_download_href: str = "",
    inventory_kind: str = "material",
) -> bytes:
    """Render the admin page for material, semifinished, or front stock counts."""
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
    worker_route = _material_inventory_worker_route(clean_inventory_kind)
    admin_href = _material_inventory_admin_route(clean_inventory_kind)
    inventory_href = worker_route
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
                 href="{worker_route}?category={urllib.parse.quote(item['key'])}">
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
  <link rel="stylesheet" href="/styles.css" />
  <style>
    :root {{ --accent2:var(--accent-strong); }}
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
<body class="matinv-page"{' data-theme-scope="default"' if active_view == 'leltar' else ''}>
  <main class="matinv-shell">
    <header class="matinv-top">
      <div>
        <span class="matinv-tag">Divian-HUB</span>
        <h1>{page_title}</h1>
      </div>
      <a href="{PRODUCTION_INVENTORY_GROUP_ROUTE if active_view == 'leltar' else ADMIN_INVENTORY_GROUP_ROUTE}">Vissza a modulokhoz</a>
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


def _front_inventory_active_presence_categories() -> set[str]:
    """Return front categories currently opened by worker tablets."""
    snapshot = _matt_inventory_read_meta(FRONT_INVENTORY_PRESENCE_PATH)
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
        _matt_inventory_write_meta(FRONT_INVENTORY_PRESENCE_PATH, snapshot)
    return active_categories


def _front_inventory_touch_presence(token: str, category: str, view_mode: str, clear: bool = False) -> list[str]:
    """Update one front worker presence heartbeat and return active categories."""
    clean_token = str(token or "").strip()
    snapshot = _matt_inventory_read_meta(FRONT_INVENTORY_PRESENCE_PATH)
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

    _matt_inventory_write_meta(FRONT_INVENTORY_PRESENCE_PATH, snapshot)
    return sorted(set(active_categories))


def _front_inventory_build_sync_payload(selected_category: str) -> dict:
    """Return the front worker polling payload for category and row state."""
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


def _unified_inventory_config(kind: str) -> dict:
    """Return route, column, and text configuration for a stock-count kind."""
    clean_kind = str(kind or "").strip().lower()
    configs = {
        "material": {
            "kind": "material",
            "title": "Anyagraktár leltár",
            "board_title": "Anyagraktár számolás",
            "session_path": MATERIAL_INVENTORY_SESSION_PATH,
            "presence_path": MATERIAL_INVENTORY_PRESENCE_PATH,
            "state_route": MATERIAL_INVENTORY_STATE_ROUTE,
            "presence_route": MATERIAL_INVENTORY_PRESENCE_ROUTE,
            "worker_route": MATERIAL_INVENTORY_WORKER_ROUTE,
            "columns": (
                {"key": "description", "label": "Leírás", "class": "is-description", "sort": "description"},
                {"key": "book_qty", "label": "Könyvelési menny.", "class": "is-book-qty", "sort": "book_qty"},
            ),
            "search_label": "Keresés leírás alapján",
            "search_keys": ("description",),
            "empty_text": "Még nincs aktív anyagraktár leltár.",
            "one_cycle": False,
        },
        "semifinished": {
            "kind": "semifinished",
            "title": "Félkész raktár leltár",
            "board_title": "Félkész raktár számolás",
            "session_path": SEMIFINISHED_INVENTORY_SESSION_PATH,
            "presence_path": SEMIFINISHED_INVENTORY_PRESENCE_PATH,
            "state_route": SEMIFINISHED_INVENTORY_STATE_ROUTE,
            "presence_route": SEMIFINISHED_INVENTORY_PRESENCE_ROUTE,
            "worker_route": SEMIFINISHED_INVENTORY_WORKER_ROUTE,
            "columns": (
                {"key": "description", "label": "Leírás", "class": "is-description", "sort": "description"},
                {"key": "icg_code", "label": "Szín", "class": "is-color", "sort": "color"},
            ),
            "search_label": "Keresés leírás vagy szín alapján",
            "search_keys": ("description", "icg_code"),
            "empty_text": "Még nincs aktív félkész raktár leltár.",
            "one_cycle": False,
        },
        "semifinished_front": {
            "kind": "semifinished_front",
            "title": "Félkész front leltár",
            "board_title": "Félkész front számolás",
            "session_path": SEMIFINISHED_FRONT_INVENTORY_SESSION_PATH,
            "presence_path": SEMIFINISHED_FRONT_INVENTORY_PRESENCE_PATH,
            "state_route": SEMIFINISHED_FRONT_INVENTORY_STATE_ROUTE,
            "presence_route": SEMIFINISHED_FRONT_INVENTORY_PRESENCE_ROUTE,
            "worker_route": SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE,
            "columns": (
                {"key": "description", "label": "Leírás", "class": "is-description", "sort": "description"},
                {"key": "icg_code", "label": "Szín", "class": "is-color", "sort": "color"},
            ),
            "search_label": "Keresés leírás vagy szín alapján",
            "search_keys": ("description", "icg_code"),
            "empty_text": "Még nincs aktív félkész front leltár.",
            "one_cycle": False,
        },
    }
    return configs.get(clean_kind, configs["material"])


def _unified_inventory_load_session(config: dict) -> dict | None:
    """Load the active inventory session referenced by a unified config."""
    return load_material_inventory_session_from_path(config["session_path"])


def _unified_inventory_build_view_model(config: dict, selected_category: str, sort_mode: str = "default") -> dict:
    """Build a worker-table view model and apply the requested sort mode."""
    session = _unified_inventory_load_session(config)
    if session is None:
        return {"session": None, "categories": [], "selected_category": "all", "visible_rows": [], "finalized": False}
    if config.get("kind") == "material" and _material_inventory_hydrate_book_qty(session):
        save_material_inventory_session_to_path(config["session_path"], session)
    view_model = build_material_inventory_view_model(session, selected_category)
    active_sort = _unified_inventory_normalize_sort(sort_mode)
    rows = list(view_model.get("visible_rows", []))
    if active_sort != "default":
        reverse = active_sort.endswith("_desc")
        base_sort = active_sort[:-5] if reverse else active_sort
        rows = sorted(rows, key=lambda row: _unified_inventory_sort_key(row, base_sort), reverse=reverse)
    view_model["visible_rows"] = rows
    view_model["sort_mode"] = active_sort
    view_model["session"] = session
    return view_model


def _unified_inventory_touch_presence(config: dict, token: str, category: str, clear: bool = False) -> list[str]:
    """Update a generic inventory worker heartbeat and return active categories."""
    clean_token = str(token or "").strip()
    path = config["presence_path"]
    snapshot = _matt_inventory_read_meta(path)
    if clean_token:
        if clear:
            snapshot.pop(clean_token, None)
        else:
            snapshot[clean_token] = {
                "category": str(category or "").strip(),
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
        category_value = str(item.get("category", "")).strip()
        if category_value:
            active_categories.append(category_value)

    _matt_inventory_write_meta(path, snapshot)
    return sorted(set(active_categories))


def _unified_inventory_sync_payload(config: dict, selected_category: str) -> dict:
    """Return a generic worker polling payload for visible counts and categories."""
    view_model = _unified_inventory_build_view_model(config, selected_category)
    session = view_model.get("session")
    if session is None:
        return {"category_states": {}, "row_inputs": {}, "updated_at": ""}
    row_inputs = {
        str(row.get("row_id", "")): str(row.get("input_qty", "") or "")
        for row in view_model.get("visible_rows", [])
    }
    category_states = {
        str(item.get("key", "")): bool(item.get("complete"))
        for item in view_model.get("categories", [])
    }
    return {"category_states": category_states, "row_inputs": row_inputs, "updated_at": str(session.get("updated_at", ""))}


def render_unified_inventory_worker_page(kind: str, selected_category: str = "", sort_mode: str = "default") -> bytes:
    """Render the tablet-oriented worker page for a stock-count kind."""
    config = _unified_inventory_config(kind)
    view_model = _unified_inventory_build_view_model(config, selected_category, sort_mode)
    session = view_model.get("session")
    current_sort = str(view_model.get("sort_mode", "default") or "default")
    selected = str(view_model.get("selected_category", "all") or "all")

    def sort_href(sort_key: str) -> str:
        """Return the next sort URL for a worker-table column."""
        if current_sort == sort_key:
            next_sort = f"{sort_key}_desc"
        elif current_sort == f"{sort_key}_desc":
            next_sort = "default"
        else:
            next_sort = sort_key
        return f"{config['worker_route']}?category={urllib.parse.quote(selected)}&sort={urllib.parse.quote(next_sort)}"

    def sort_label(label: str, sort_key: str) -> str:
        """Return sortable header HTML with the current direction indicator."""
        indicator = ""
        if current_sort == sort_key:
            indicator = " ↑"
        elif current_sort == f"{sort_key}_desc":
            indicator = " ↓"
        return f'<a class="frontinv-sort-head" href="{sort_href(sort_key)}">{html.escape(label)}{indicator}</a>'

    if session is None:
        content_html = f"""
          <section class="frontinv-board is-worker is-empty">
            <div class="frontinv-empty">
              <strong>{html.escape(config["empty_text"])}</strong>
              <p>Az admin felületen töltsd fel a forrásfájlt, utána ez a teszt nézet ugyanazt az aktív leltárt használja.</p>
            </div>
          </section>
        """
    else:
        categories_html = "".join(
            f"""
              <a class="frontinv-chip{' is-complete' if item.get('complete') else ''}{' is-active' if item['key'] == selected else ''}"
                 href="{config['worker_route']}?category={urllib.parse.quote(str(item['key']))}&sort={urllib.parse.quote(current_sort)}">
                <span>{html.escape(str(item.get('label', '')))}</span>
                <strong>{int(item.get('count', 0))}</strong>
              </a>
            """
            for item in view_model.get("categories", [])
        )
        headers_html = "".join(
            f"<th>{sort_label(str(column['label']), str(column['sort']))}</th>"
            for column in config["columns"]
        )
        colgroup_html = "".join('<col />' for _ in config["columns"]) + '<col class="frontinv-count-col" />'
        rows_html = ""
        finalized = bool(view_model.get("finalized"))
        for row in view_model.get("visible_rows", []):
            search_text = " ".join(str(row.get(key, "")) for key in config["search_keys"])
            row_cells = "".join(
                f'<td class="{html.escape(str(column["class"]))}">{_unified_inventory_cell_html(row, str(column["key"]))}</td>'
                for column in config["columns"]
            )
            current_value = str(row.get("counted_qty", row.get("input_qty", "")) or "")
            rows_html += f"""
              <tr class="frontinv-row{' is-counted' if current_value.strip() or finalized else ''}" data-frontinv-row data-row-id="{html.escape(str(row.get('row_id', '')))}" data-frontinv-current-value="{html.escape(current_value, quote=True)}" data-frontinv-search-text="{html.escape(search_text, quote=True)}">
                {row_cells}
                <td class="is-count">
                  <div class="frontinv-count-control">
                    <span class="frontinv-count-pill" data-frontinv-total>{html.escape(current_value or '0')}</span>
                    <div class="frontinv-adjust">
                      <label><span>+</span><input class="frontinv-input" type="number" min="0" inputmode="decimal" autocomplete="off" placeholder="0" data-frontinv-input data-mode="add" data-row-id="{html.escape(str(row.get('row_id', '')))}" {'disabled' if finalized else ''} /></label>
                      <label><span>-</span><input class="frontinv-input" type="number" min="0" inputmode="decimal" autocomplete="off" placeholder="0" data-frontinv-input data-mode="subtract" data-row-id="{html.escape(str(row.get('row_id', '')))}" {'disabled' if finalized else ''} /></label>
                    </div>
                  </div>
                </td>
              </tr>
            """
        if not rows_html:
            colspan = len(config["columns"]) + 1
            rows_html = f'<tr><td colspan="{colspan}" class="frontinv-empty-row">Ebben a kategóriában nincs tétel.</td></tr>'

        status_html = ""
        if config.get("one_cycle"):
            status_html = """
              <div class="frontinv-phase-callout">
                <div>
                  <strong>Egykörös számlálás</strong>
                  <p>Írják be a tényleges darabszámot. A leltár itt nem fut több ellenőrzési körön, lezáráskor készül az export.</p>
                </div>
              </div>
            """
        content_html = f"""
          <section class="frontinv-board is-worker" data-unified-inventory-root data-front-inventory-root data-state-route="{html.escape(config['state_route'])}" data-presence-route="{html.escape(config['presence_route'])}" data-category="{html.escape(selected)}" data-storage-prefix="unifiedinv-{html.escape(config['kind'])}">
            <div class="frontinv-board-head">
              <div>
                <span class="frontinv-tag">Leltár nézet</span>
                <strong>{html.escape(config["board_title"])}</strong>
                <p>Forrás: {html.escape(str(session.get('source_name', '')))} · Utoljára frissítve: {html.escape(_front_inventory_format_timestamp(str(session.get('updated_at', ''))))}</p>
              </div>
              <div class="frontinv-board-stamp">{html.escape(str(session.get('phase_label', 'Számlálás')))}</div>
            </div>

            <div class="frontinv-category-row">{categories_html}</div>
            <label class="frontinv-search">
              <span>{html.escape(config["search_label"])}</span>
              <input type="search" data-frontinv-search placeholder="Írj be részletet..." autocomplete="off" />
            </label>
            {status_html}

            <div class="frontinv-table-wrap">
              <table class="frontinv-table">
                <colgroup>{colgroup_html}</colgroup>
                <thead>
                  <tr>
                    {headers_html}
                    <th>{sort_label("Darabszám", "count")}</th>
                  </tr>
                </thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
            <div class="frontinv-generated-by">generated by Divian-HUB</div>
          </section>
        """

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | {html.escape(config["title"])} teszt</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/styles.css" />
  {_unified_inventory_style()}
</head>
<body class="frontinv-worker-stage" data-theme-scope="default">
  {content_html}
  {_unified_inventory_script()}
</body>
</html>"""
    return page.encode("utf-8")


def _unified_inventory_cell_html(row: dict, key: str) -> str:
    """Render one escaped worker-table cell, including color chip markup."""
    value = str(row.get(key, "") or "-")
    if key == "icg_code":
        return f'<span class="frontinv-color-chip">{html.escape(value)}</span>'
    return html.escape(value)


def _unified_inventory_style() -> str:
    """Return CSS for the generic inventory worker page."""
    return """
<style>
  :root { --frontinv-text:#0f172a; --frontinv-muted:#64748b; --frontinv-line:#d8e0ea; --frontinv-accent:#0c8d57; --frontinv-accent-strong:#12a566; }
  * { box-sizing:border-box; }
  body.frontinv-worker-stage { margin:0; min-height:100dvh; background:#f8fafc; color:var(--frontinv-text); font-family:Manrope, sans-serif; }
  .frontinv-board { position:relative; overflow:hidden; background:rgba(255,255,255,.96); color:#0f172a; }
  .frontinv-board::before { content:""; position:absolute; inset:0 0 auto 0; height:5px; background:linear-gradient(90deg,var(--frontinv-accent-strong),#86efac,#dbeafe); pointer-events:none; }
  .frontinv-board.is-worker { min-height:100dvh; border-radius:0; border:0; box-shadow:none; padding:18px 20px 24px; }
  .frontinv-board-head { position:relative; z-index:1; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:start; }
  .frontinv-board-head strong,.frontinv-empty strong,.frontinv-phase-callout strong { font-family:"Space Grotesk", sans-serif; color:#0f172a; }
  .frontinv-board-head strong { font-size:clamp(1.35rem,2.8vw,2rem); line-height:1; }
  .frontinv-board-head p,.frontinv-empty p,.frontinv-phase-callout p,.frontinv-generated-by { margin:6px 0 0; color:#64748b; line-height:1.55; }
  .frontinv-tag { display:inline-flex; align-items:center; width:fit-content; min-height:28px; padding:0 12px; border-radius:999px; background:#edf7f2; color:#0c7650; font-size:.78rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
  .frontinv-board-stamp { white-space:nowrap; font-size:.85rem; font-weight:800; padding:10px 14px; border-radius:18px; background:rgba(255,255,255,.86); border:1px solid rgba(15,23,42,.08); color:#475569; }
  .frontinv-category-row { display:flex; gap:10px; margin-top:14px; overflow-x:auto; padding-bottom:4px; }
  .frontinv-chip { display:inline-flex; align-items:center; gap:10px; min-height:42px; padding:0 14px; border-radius:999px; border:1px solid rgba(15,23,42,.12); background:#fff; color:#0f172a; text-decoration:none; white-space:nowrap; font-weight:800; }
  .frontinv-chip strong { display:inline-flex; align-items:center; justify-content:center; min-width:26px; height:26px; padding:0 8px; border-radius:999px; background:#f1f5f9; font-size:.84rem; }
  .frontinv-chip.is-active { background:#0f172a; color:#fff; border-color:#0f172a; }
  .frontinv-chip.is-active strong { background:rgba(255,255,255,.14); color:#fff; }
  .frontinv-chip.is-complete { background:rgba(22,163,74,.12); border-color:rgba(22,163,74,.38); color:#166534; }
  .frontinv-chip.is-complete strong { background:rgba(22,163,74,.16); color:#166534; }
  .frontinv-chip.is-live:not(.is-active) { background:rgba(37,99,235,.10); border-color:rgba(37,99,235,.34); color:#1d4ed8; }
  .frontinv-chip.is-live:not(.is-active) strong { background:rgba(37,99,235,.14); color:#1d4ed8; }
  .frontinv-search { display:grid; grid-template-columns:auto minmax(220px,420px); align-items:center; justify-content:start; gap:10px; margin-top:10px; color:#475569; font-size:.78rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
  .frontinv-search input { width:100%; min-height:42px; padding:0 15px; border:1px solid rgba(15,23,42,.12); border-radius:999px; background:#fff; color:#0f172a; font:800 .95rem/1 Manrope, sans-serif; text-transform:none; letter-spacing:0; }
  .frontinv-search input:focus,.frontinv-input:focus { outline:none; border-color:#0f172a; box-shadow:0 0 0 3px rgba(15,23,42,.08); }
  .frontinv-phase-callout { margin-top:14px; padding:16px 18px; border-radius:20px; background:#fff; border:1px solid rgba(15,23,42,.08); }
  .frontinv-table-wrap { margin-top:14px; overflow-x:hidden; border-radius:20px; border:1px solid rgba(15,23,42,.08); background:#fff; }
  .frontinv-table { width:100%; border-collapse:collapse; min-width:0; table-layout:fixed; }
  .frontinv-table thead th { padding:14px 18px; border-bottom:1px solid rgba(15,23,42,.08); background:#f8fafc; color:#475569; font-size:.8rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; text-align:left; white-space:nowrap; }
  .frontinv-sort-head { color:inherit; text-decoration:none; display:inline-flex; align-items:center; gap:4px; }
  .frontinv-table tbody td { padding:14px 18px; border-bottom:1px solid rgba(15,23,42,.06); color:#0f172a; vertical-align:middle; }
  .frontinv-table tbody tr:nth-child(2n) { background:rgba(248,250,252,.72); }
  .frontinv-row.is-counted { background:rgba(22,163,74,.10) !important; }
  .frontinv-table td.is-description { font-weight:800; }
  .frontinv-table td.is-book-qty { width:180px; color:#475569; font-weight:800; }
  .frontinv-table td.is-color { width:220px; }
  .frontinv-count-col,.frontinv-table td.is-count { width:32%; }
  .frontinv-color-chip { display:inline-flex; align-items:center; min-height:36px; padding:0 14px; border-radius:999px; background:linear-gradient(180deg,#eff6ff 0%,#dbeafe 100%); border:1px solid rgba(37,99,235,.14); color:#1d4ed8; font-weight:800; white-space:nowrap; }
  .frontinv-count-control { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:10px; }
  .frontinv-count-pill { display:inline-flex; align-items:center; justify-content:center; min-width:72px; min-height:42px; padding:0 14px; border-radius:999px; background:#0f172a; color:#fff; font-weight:800; }
  .frontinv-adjust { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .frontinv-adjust label { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:4px; color:#64748b; font-size:.78rem; font-weight:900; }
  .frontinv-input { width:100%; min-height:44px; padding:0 10px; border-radius:16px; border:1px solid rgba(15,23,42,.12); background:#fff; color:#0f172a; font-size:1.1rem; font-weight:800; text-align:center; }
  .frontinv-input.is-error { border-color:#ef4444; box-shadow:0 0 0 3px rgba(239,68,68,.14); }
  .frontinv-empty { display:grid; gap:8px; padding:34px 28px; }
  .frontinv-empty-row { color:#64748b; text-align:center; padding:26px 18px !important; }
  .frontinv-generated-by { margin-top:16px; padding-top:12px; border-top:1px dashed rgba(15,23,42,.12); text-align:right; font-size:.78rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
  @media (orientation:portrait) and (max-width:1100px) {
    .frontinv-board.is-worker .frontinv-table thead th,.frontinv-board.is-worker .frontinv-table tbody td { padding:12px 10px; }
    .frontinv-board.is-worker .frontinv-table thead th { font-size:.7rem; letter-spacing:.05em; }
    .frontinv-board.is-worker .frontinv-table td.is-description { font-size:.92rem; line-height:1.25; }
    .frontinv-board.is-worker .frontinv-color-chip { min-height:32px; padding:0 10px; font-size:.8rem; line-height:1.15; white-space:normal; text-align:center; justify-content:center; }
    .frontinv-input { min-height:38px; font-size:.94rem; padding:0 6px; }
    .frontinv-count-control { gap:6px; }
    .frontinv-adjust { gap:5px; }
    .frontinv-adjust label { font-size:.7rem; gap:3px; }
    .frontinv-search { grid-template-columns:1fr; gap:6px; }
  }
  @media (max-width:720px) {
    .frontinv-board.is-worker { padding:14px 14px 20px; }
    .frontinv-board-head { grid-template-columns:minmax(0,1fr); gap:10px; }
  }
</style>
"""


def _unified_inventory_script() -> str:
    """Return client-side polling and count-entry behavior for worker pages."""
    return """
<script>
(() => {
  const root = document.querySelector("[data-unified-inventory-root]");
  if (!root) return;
  const stateRoute = root.getAttribute("data-state-route") || "";
  const presenceRoute = root.getAttribute("data-presence-route") || "";
  const categoryValue = root.getAttribute("data-category") || "";
  const storagePrefix = root.getAttribute("data-storage-prefix") || "unifiedinv";
  const categoryRow = root.querySelector(".frontinv-category-row");
  const rowElements = Array.from(root.querySelectorAll("[data-frontinv-row]"));
  const searchInput = root.querySelector("[data-frontinv-search]");
  const normalizeSearchText = (value) => String(value || "").toLocaleLowerCase("hu-HU").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
  const applySearch = () => {
    if (!searchInput) return;
    const terms = normalizeSearchText(searchInput.value.trim()).split(/\\s+/).filter(Boolean);
    root.querySelectorAll("[data-frontinv-row]").forEach((row) => {
      const searchable = normalizeSearchText(row.getAttribute("data-frontinv-search-text") || row.textContent || "");
      row.hidden = terms.length > 0 && !terms.every((term) => searchable.includes(term));
    });
  };
  const setRowValue = (row, value) => {
    if (!row) return;
    const nextValue = String(value || "").trim();
    row.setAttribute("data-frontinv-current-value", nextValue);
    const total = row.querySelector("[data-frontinv-total]");
    if (total) total.textContent = nextValue || "0";
    row.classList.toggle("is-counted", nextValue !== "");
  };
  const saveAdjustment = (input) => {
    const rowId = input.getAttribute("data-row-id") || input.closest("[data-frontinv-row]")?.getAttribute("data-row-id") || "";
    const value = input.value.trim();
    const mode = input.getAttribute("data-mode") || "";
    if (!stateRoute || !rowId || !value || input.dataset.frontinvSaving === "1") return;
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
        if (!response.ok) throw new Error("save failed");
        return response.json();
      })
      .then((payload) => {
        setRowValue(input.closest("[data-frontinv-row]"), payload && Object.prototype.hasOwnProperty.call(payload, "value") ? payload.value : "");
        input.value = "";
      })
      .catch(() => {
        input.classList.add("is-error");
        window.setTimeout(() => input.classList.remove("is-error"), 1200);
      })
      .finally(() => {
        input.dataset.frontinvSaving = "0";
      });
  };
  searchInput?.addEventListener("input", applySearch);
  applySearch();
  root.querySelectorAll("[data-frontinv-input]").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveAdjustment(input);
      }
    });
    input.addEventListener("blur", () => saveAdjustment(input));
  });
  if (categoryRow) {
    const scrollStorageKey = `${storagePrefix}-category-scroll`;
    const savedScroll = Number(window.sessionStorage.getItem(scrollStorageKey) || "0");
    if (savedScroll > 0) categoryRow.scrollLeft = savedScroll;
    categoryRow.addEventListener("scroll", () => window.sessionStorage.setItem(scrollStorageKey, String(categoryRow.scrollLeft)), { passive: true });
    categoryRow.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => window.sessionStorage.setItem(scrollStorageKey, String(categoryRow.scrollLeft)));
    });
  }
  if (presenceRoute && categoryValue) {
    const tokenStorageKey = `${storagePrefix}-presence-token`;
    let token = window.sessionStorage.getItem(tokenStorageKey);
    if (!token) {
      token = Math.random().toString(36).slice(2) + Date.now().toString(36);
      window.sessionStorage.setItem(tokenStorageKey, token);
    }
    const applyRemoteState = (payload) => {
      const activeSet = new Set(Array.isArray(payload && payload.active_categories) ? payload.active_categories : []);
      const categoryStates = payload && payload.category_states && typeof payload.category_states === "object" ? payload.category_states : {};
      root.querySelectorAll(".frontinv-chip").forEach((chip) => {
        const href = chip.getAttribute("href") || "";
        let chipCategory = "";
        try { chipCategory = new URL(href, window.location.origin).searchParams.get("category") || "all"; } catch { chipCategory = ""; }
        chip.classList.toggle("is-live", activeSet.has(chipCategory));
        chip.classList.toggle("is-complete", Boolean(categoryStates[chipCategory]));
      });
      const remoteRowInputs = payload && payload.row_inputs && typeof payload.row_inputs === "object" ? payload.row_inputs : {};
      rowElements.forEach((row) => {
        const rowId = row.getAttribute("data-row-id") || "";
        if (Object.prototype.hasOwnProperty.call(remoteRowInputs, rowId)) setRowValue(row, remoteRowInputs[rowId]);
      });
    };
    const touchPresence = (clear = false) => {
      const formData = new URLSearchParams();
      formData.set("token", token);
      formData.set("category", categoryValue);
      if (clear) formData.set("clear", "1");
      const payload = formData.toString();
      if (clear && navigator.sendBeacon) {
        navigator.sendBeacon(presenceRoute, new Blob([payload], { type: "application/x-www-form-urlencoded; charset=UTF-8" }));
        return;
      }
      fetch(presenceRoute, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
        body: payload,
        credentials: "same-origin",
        cache: "no-store",
        keepalive: clear,
      }).then((response) => response.ok ? response.json() : null).then((payload) => {
        if (payload) applyRemoteState(payload);
      }).catch(() => {});
    };
    touchPresence(false);
    const intervalId = window.setInterval(() => touchPresence(false), 5000);
    window.addEventListener("pagehide", () => {
      window.clearInterval(intervalId);
      touchPresence(true);
    });
  }
})();
</script>
"""


def _front_inventory_normalize_view(value: str) -> str:
    """Normalize front inventory view mode to admin or leltar."""
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
    """Render the front inventory admin or worker view."""
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

    admin_href = ADMIN_FRONT_INVENTORY_ROUTE if sort_mode == "default" else f"{ADMIN_FRONT_INVENTORY_ROUTE}?sort={urllib.parse.quote(sort_mode)}"
    inventory_href = (
        FRONT_INVENTORY_WORKER_ROUTE
        if sort_mode == "default"
        else f"{FRONT_INVENTORY_WORKER_ROUTE}?sort={urllib.parse.quote(sort_mode)}"
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
                  href="{FRONT_INVENTORY_WORKER_ROUTE}?category={urllib.parse.quote(item['key'])}&sort={urllib.parse.quote(view_model['sort_mode'])}">
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

        inventory_open_href = f"{FRONT_INVENTORY_WORKER_ROUTE}?category={urllib.parse.quote(view_model['selected_category'])}&sort={urllib.parse.quote(view_model['sort_mode'])}"
        current_sort_mode = str(view_model.get("sort_mode", "default") or "default")

        def frontinv_sort_href(sort_key: str) -> str:
            """Return the next sort URL for a front inventory column."""
            if current_sort_mode == sort_key:
                next_sort = f"{sort_key}_desc"
            elif current_sort_mode == f"{sort_key}_desc":
                next_sort = "default"
            else:
                next_sort = sort_key
            sort_base_route = FRONT_INVENTORY_WORKER_ROUTE if active_view == "leltar" else ADMIN_FRONT_INVENTORY_ROUTE
            sort_view_part = "" if active_view == "leltar" else f"view={urllib.parse.quote(active_view)}&"
            return f"{sort_base_route}?{sort_view_part}category={urllib.parse.quote(view_model['selected_category'])}&sort={urllib.parse.quote(next_sort)}"

        def frontinv_sort_label(label: str, sort_key: str) -> str:
            """Return sortable front inventory header HTML."""
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
<body class="frontinv-worker-page" data-theme-scope="default">
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
      <a href="{ADMIN_INVENTORY_GROUP_ROUTE}">Vissza a modulokhoz</a>
    </header>
    {notice_html}
    {content_html}
  </main>
</body>
</html>
"""
    return admin_page.encode("utf-8")


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that can restart quickly during development."""
    allow_reuse_address = True


class InvoiceHandler(BaseHTTPRequestHandler):
    """Main HTTP router for Divian-HUB pages, APIs, and downloads."""

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "content-type" and "text/html" in value.lower():
            self._uses_platform_font = True
            self._theme_is_html_response = True
        if keyword.lower() == "content-length" and getattr(self, "_theme_is_html_response", False):
            user = getattr(self, "_theme_user", None)
            if user is not None and (
                user.is_admin
                or user.user_id in {HR_THEME_USER_ID, PRODUCTION_CONTROLLER_THEME_USER_ID}
            ):
                # The response writer may add a body class after the original
                # byte length was calculated. Let HTTP delimit the complete
                # response so trailing scripts are never truncated.
                return
        super().send_header(keyword, value)

    def end_headers(self) -> None:
        if getattr(self, "_uses_platform_font", False):
            super().send_header("Link", '</platform-font.css>; rel=stylesheet')
        super().end_headers()

    def current_user(self) -> AuthUser:
        """Return the user represented by the signed client cookie."""
        return user_from_cookie(LOGIN_DB_PATH, self.headers.get("Cookie"))

    def redirect_to_home(self, status: int = 303, suffix: str = "") -> None:
        """Redirect the browser back to the main module page."""
        self.send_response(status)
        self.send_header("Location", "/" + suffix)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def reject_unauthorized_module(self) -> bool:
        """Redirect unauthorized module requests to the home page."""
        path = _normalize_path(self.path)
        if _can_access_path(self.current_user(), path):
            return False
        self.redirect_to_home()
        return True

    def do_GET(self):
        """Route authenticated GET requests to pages, JSON data, or downloads."""
        self._theme_user = self.current_user()
        self.wfile = _ThemedResponseWriter(self.wfile, self._theme_user)
        path = _normalize_path(self.path)
        if path == DEV_RELOAD_ROUTE:
            self.respond_dev_reload_stream()
            return

        if path in {"/", "/index.html"}:
            body = render_home_page(self.current_user(), self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.reject_unauthorized_module():
            return

        if path == MANUFACTURING_ADMIN_REVISION_ROUTE:
            revision = load_admin_manufacturing_change_revision(admin_manufacturing_runtime_dir())
            self.respond_json(200, {"ok": True, "revision": revision})
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

        if path == HR_APP_ROUTE:
            body = apply_hr_theme(render_hr_form(), self.current_user())
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

        if path in {MANUFACTURING_ROUTE, ADMIN_MANUFACTURING_ROUTE}:
            query = _manufacturing_query_params(self.path)
            render_module = render_admin_manufacturing_module if path == ADMIN_MANUFACTURING_ROUTE else render_manufacturing_module
            body = render_module(
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

        if path in {MANUFACTURING_DATA_ROUTE, ADMIN_MANUFACTURING_DATA_ROUTE}:
            query = _manufacturing_query_params(self.path)
            include_client_cache = str(query.get("refresh_cache", "")).strip().lower() in {"1", "true", "yes"}
            try:
                build_payload = admin_manufacturing_module_payload if path == ADMIN_MANUFACTURING_DATA_ROUTE else manufacturing_module_payload
                build_client_payload = admin_manufacturing_client_payload if path == ADMIN_MANUFACTURING_DATA_ROUTE else manufacturing_client_payload
                payload = build_payload(
                    production_number=query.get("production", ""),
                    operation=query.get("operation", ""),
                    include_client_cache=include_client_cache,
                )
                response_payload = {"ok": True, **build_client_payload(payload)}
                if include_client_cache:
                    response_payload["productionClientCache"] = payload.get("productionClientCache", [])
                self.respond_json(200, response_payload)
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A gyártási papírok betöltése nem sikerült: {exc}"})
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

        if path == ADMIN_INVENTORY_GROUP_ROUTE:
            body = render_inventory_group_page("admin")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == PRODUCTION_INVENTORY_GROUP_ROUTE:
            body = render_inventory_group_page("production")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in {
            MATERIAL_INVENTORY_WORKER_ROUTE,
            MATERIAL_INVENTORY_LEGACY_WORKER_ROUTE,
            SEMIFINISHED_INVENTORY_WORKER_ROUTE,
            SEMIFINISHED_INVENTORY_LEGACY_WORKER_ROUTE,
            SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE,
            SEMIFINISHED_FRONT_INVENTORY_LEGACY_WORKER_ROUTE,
        }:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_sort = str(query.get("sort", ["default"])[0] or "default").strip()
            if path in {
                SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE,
                SEMIFINISHED_FRONT_INVENTORY_LEGACY_WORKER_ROUTE,
            }:
                inventory_kind = "semifinished_front"
            elif path in {
                SEMIFINISHED_INVENTORY_WORKER_ROUTE,
                SEMIFINISHED_INVENTORY_LEGACY_WORKER_ROUTE,
            }:
                inventory_kind = "semifinished"
            else:
                inventory_kind = "material"
            body = render_unified_inventory_worker_page(
                inventory_kind,
                selected_category=selected_category,
                sort_mode=selected_sort,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in {MATERIAL_INVENTORY_ROUTE, ADMIN_MATERIAL_INVENTORY_ROUTE}:
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

        if path in {SEMIFINISHED_INVENTORY_ROUTE, ADMIN_SEMIFINISHED_INVENTORY_ROUTE}:
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

        if path in {SEMIFINISHED_FRONT_INVENTORY_ROUTE, ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE}:
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

        if path in {FRONT_INVENTORY_WORKER_ROUTE, FRONT_INVENTORY_LEGACY_WORKER_ROUTE}:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            selected_category = str(query.get("category", [""])[0] or "").strip()
            selected_sort = str(query.get("sort", ["default"])[0] or "default").strip()
            _front_inventory_ensure_insight_artifacts(load_front_inventory_session_from_path(FRONT_INVENTORY_SESSION_PATH))
            body = render_front_inventory_form(selected_category=selected_category, sort_mode=selected_sort, view_mode="leltar")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in {FRONT_INVENTORY_ROUTE, ADMIN_FRONT_INVENTORY_ROUTE}:
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
            payload = matt_inventory_alert_download_payload()
            if payload is None:
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


        if path.startswith(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = procurement_download_payload(job_id, artifact)
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
            payload = compare_download_payload(job_id, artifact)
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
            payload = order_download_payload(job_id, artifact)
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

        asset = load_static_asset(BASE_DIR, path)
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

    def handle_login(self):
        """Authenticate the password field and store login state client-side."""
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = _parse_urlencoded_body(raw_body)
        if payload.get("logout") == "1" or not str(payload.get("password", "")).strip():
            self.send_response(303)
            self.send_header("Location", "/?login=default#modules")
            self.send_header("Set-Cookie", make_logout_cookie())
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        password = str(payload.get("password", ""))
        if len(password) > MAX_PASSWORD_LENGTH:
            self.send_response(303)
            self.send_header("Location", "/?login=too_long#modules")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        user = authenticate_password(LOGIN_DB_PATH, password)
        if user is None:
            self.send_response(303)
            self.send_header("Location", "/?login=failed#modules")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(303)
        self.send_header("Location", "/?login=ok#modules")
        self.send_header("Set-Cookie", make_login_cookie(LOGIN_DB_PATH, user))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def respond_dev_reload_stream(self):
        """Stream development reload events over server-sent events."""
        payload = json.dumps({"token": dev_reload_token(DEV_RELOAD_TOKEN_ENV)}).encode("utf-8")
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
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def manufacturing_state_runtime_root(self, document_key: object = "", state_keys: list[str] | tuple[str, ...] = ()) -> Path:
        """Return the runtime folder used for persisted manufacturing row state."""
        clean_document_key = str(document_key or "").strip()
        if clean_document_key == "topfloor" or any(str(key or "").startswith("topfloor::") for key in state_keys):
            return manufacturing_runtime_dir() / "topfloor"
        return manufacturing_runtime_dir()

    def handle_topfloor_box_simple_action(self, action: str, category_key: str, payload: dict) -> bool:
        """Handle Topfloor box actions that do not write row state."""
        con_description = str(payload.get("con_description", "")).strip()
        if action == "create":
            buyer = str(payload.get("buyer", "")).strip()
            location = str(payload.get("location", "")).strip()
            if not con_description:
                # TODO: Keep this only as a fallback; the UI sends the editable XML-derived default.
                con_description = " ".join(part for part in (buyer, location, date.today().isoformat()) if part)
            result = _topfloor_create_category_box(
                category_key,
                con_description=con_description,
                created_by=str(payload.get("created_by", "")).strip(),
            )
        elif action == "open":
            result = _topfloor_open_category_box(category_key, con_description=con_description)
        elif action == "reprint-label":
            result = _topfloor_reprint_category_label(category_key, con_description=con_description)
        elif action == "issue-storage-box":
            box_type = payload.get("box_type", {})
            if not isinstance(box_type, dict):
                box_type = {}
            result = _topfloor_issue_storage_box(
                category_key,
                box_type_name=str(box_type.get("name", "")).strip(),
                box_type_code=str(box_type.get("code", "")).strip(),
                box_type_id=int(box_type.get("id") or 0),
            )
        else:
            return False
        self.respond_json(200, {"ok": True, "action": action, "box": result})
        return True

    def topfloor_box_restriction_error(self, action: str, category_key: str, payload: dict | None = None) -> str:
        """Return the server-side Topfloor box restriction error, if any."""
        payload = payload if isinstance(payload, dict) else {}
        guard = payload.get("guard")
        if isinstance(guard, dict):
            if not bool(guard.get("target_exists")):
                return "Az Anyagraktár kategória nem található az aktuális oldalon."
            if action != "issue-storage-box" and isinstance(guard.get("unissued_done_box"), dict):
                return self.topfloor_guard_restriction_message(
                    guard.get("unissued_done_box", {}),
                    "Van lezárt, de még ki nem adott Anyagraktár doboz. Add ki ezt a dobozt, mielőtt másik dobozműveletet indítasz.",
                )
            if action in {"create", "open", "reprint-label"} and isinstance(guard.get("open_box"), dict):
                return self.topfloor_guard_restriction_message(
                    guard.get("open_box", {}),
                    "Már van nyitott Anyagraktár doboz. Zárd le ezt, mielőtt másikat nyitsz.",
                )
            if action == "issue-storage-box" and not bool(guard.get("target_ready_to_issue")):
                return "Ezt az Anyagraktár dobozt még nem lehet kiadni: legyen lezárva, és minden sora legyen dobozba rakva."
            print(f"[topfloor-box] restriction-state action={action} category={category_key} source=client-runtime took 0.000s", flush=True)
            return ""

        started_at = time.perf_counter()
        document, selection_state = self.current_topfloor_document_state(category_key)
        sections = [section for section in document.get("sections", []) if isinstance(section, dict)]
        target_section = self.find_topfloor_category_section(sections, category_key)
        print(
            f"[topfloor-box] restriction-state action={action} category={category_key} sections={len(sections)} took {time.perf_counter() - started_at:.3f}s",
            flush=True,
        )
        if target_section is None:
            return "Az Anyagraktár kategória nem található az aktuális XML adatokban."

        if action != "issue-storage-box":
            done_started_at = time.perf_counter()
            done_section = self.find_topfloor_unissued_done_section(sections, selection_state)
            print(
                f"[topfloor-box] restriction-unissued-scan action={action} category={category_key} took {time.perf_counter() - done_started_at:.3f}s",
                flush=True,
            )
            if done_section is not None:
                return self.topfloor_section_restriction_message(
                    done_section,
                    "Van lezárt, de még ki nem adott Anyagraktár doboz. Add ki ezt a dobozt, mielőtt másik dobozműveletet indítasz.",
                )

        if action in {"create", "open", "reprint-label"}:
            open_started_at = time.perf_counter()
            open_section = self.find_topfloor_open_section(sections, category_key)
            print(
                f"[topfloor-box] restriction-open-scan action={action} category={category_key} took {time.perf_counter() - open_started_at:.3f}s",
                flush=True,
            )
            if open_section is not None:
                return self.topfloor_section_restriction_message(
                    open_section,
                    "Már van nyitott Anyagraktár doboz. Zárd le ezt, mielőtt másikat nyitsz.",
                )

        if action == "issue-storage-box" and not self.topfloor_section_ready_to_issue(target_section, selection_state):
            return "Ezt az Anyagraktár dobozt még nem lehet kiadni: legyen lezárva, és minden sora legyen dobozba rakva."
        return ""

    def topfloor_guard_restriction_message(self, box: dict, prefix: str) -> str:
        """Return a user-facing Topfloor restriction message from client runtime guard data."""
        details = [
            prefix,
            f"Szállítmány: {str(box.get('shipment_id', '')).strip()}",
            f"Doboz: {str(box.get('box_id', '')).strip()}",
            f"Kategória: {str(box.get('label', '') or box.get('category_key', '')).strip()}",
            f"Leírás: {str(box.get('description', '')).strip()}",
        ]
        return " ".join(item for item in details if not item.endswith(": "))

    def current_topfloor_document_state(self, category_key: str) -> tuple[dict, dict[str, str]]:
        """Build the current Topfloor document and row state for box guards."""
        started_at = time.perf_counter()
        category_parts = str(category_key or "").split("::")
        category_production = _manufacturing_normalize_number(category_parts[1] if len(category_parts) > 1 else "")
        if not category_production:
            raise RuntimeError("Az Anyagraktár kategória nem tartalmaz gyártási számot.")
        production_numbers = [category_production]
        print(
            f"[topfloor-box] current-state production={category_production} took {time.perf_counter() - started_at:.3f}s",
            flush=True,
        )
        aggregate_started_at = time.perf_counter()
        bundle, selection_state, _partial_quantity_state = _manufacturing_topfloor_aggregate_bundle(production_numbers)
        print(
            f"[topfloor-box] current-state aggregate productions={len(production_numbers)} took {time.perf_counter() - aggregate_started_at:.3f}s",
            flush=True,
        )
        document = next(
            (
                item
                for item in bundle.get("documents", [])
                if isinstance(item, dict) and str(item.get("key", "")).strip() == "topfloor"
            ),
            {},
        )
        if not isinstance(document, dict) or not document.get("sections"):
            raise RuntimeError("Az Anyagraktár XML adatok nem tölthetők be az ellenőrzéshez.")
        print(
            f"[topfloor-box] current-state total category={category_key} took {time.perf_counter() - started_at:.3f}s",
            flush=True,
        )
        return document, selection_state

    def find_topfloor_category_section(self, sections: list[dict], category_key: str) -> dict | None:
        """Find the Topfloor section for a category key or its legacy key."""
        clean_key = str(category_key or "").strip()
        legacy_key = "::".join(clean_key.split("::")[:3]) if len(clean_key.split("::")) >= 4 else clean_key
        for section in sections:
            category = section.get("topfloorCategory") if isinstance(section, dict) else None
            if not isinstance(category, dict):
                continue
            category_keys = {
                str(category.get("categoryKey", "")).strip(),
                str(category.get("boxCategoryKey", "")).strip(),
                str(category.get("legacyBoxCategoryKey", "")).strip(),
            }
            if clean_key in category_keys or legacy_key in category_keys:
                return section
        return None

    def find_topfloor_open_section(self, sections: list[dict], category_key: str) -> dict | None:
        """Return any open Topfloor section other than the submitted category."""
        clean_key = str(category_key or "").strip()
        for section in sections:
            category = section.get("topfloorCategory") if isinstance(section, dict) else None
            if not isinstance(category, dict) or not bool(category.get("boxOpen")):
                continue
            if str(category.get("categoryKey", "")).strip() == clean_key:
                continue
            return section
        return None

    def find_topfloor_unissued_done_section(self, sections: list[dict], selection_state: dict[str, str]) -> dict | None:
        """Return the first closed, loaded, unissued Topfloor category."""
        for section in sections:
            category = section.get("topfloorCategory") if isinstance(section, dict) else None
            if not isinstance(category, dict) or bool(category.get("storageBoxIssued")):
                continue
            if self.topfloor_section_ready_to_issue(section, selection_state):
                return section
        return None

    def topfloor_section_ready_to_issue(self, section: dict, selection_state: dict[str, str]) -> bool:
        """Return whether every row in a closed Topfloor category has a box id."""
        category = section.get("topfloorCategory") if isinstance(section, dict) else None
        rows = section.get("rows", []) if isinstance(section, dict) else []
        if not isinstance(category, dict) or not str(category.get("boxId", "")).strip() or bool(category.get("boxOpen")):
            return False
        if not isinstance(rows, list) or not rows:
            return False
        row_dicts = [row for row in rows if isinstance(row, dict)]
        return bool(row_dicts) and all(self.topfloor_row_done_state(row, selection_state) for row in row_dicts)

    def topfloor_row_done_state(self, row: dict, selection_state: dict[str, str]) -> bool:
        """Return whether a Topfloor row state is a numeric box id."""
        candidate_keys = (
            str(row.get("state_key", "")).strip(),
            str(row.get("state_storage_key", "")).strip(),
            str(row.get("row_id", "")).strip(),
        )
        state = next((str(selection_state.get(key, "")).strip() for key in candidate_keys if key and selection_state.get(key)), "")
        return bool(re.fullmatch(r"\d{1,12}", state))

    def topfloor_section_restriction_message(self, section: dict, prefix: str) -> str:
        """Return a user-facing Topfloor restriction message with box details."""
        category = section.get("topfloorCategory") if isinstance(section, dict) else {}
        if not isinstance(category, dict):
            category = {}
        details = [
            prefix,
            f"Szállítmány: {str(category.get('shipmentID', '')).strip()}",
            f"Doboz: {str(category.get('boxId', '')).strip()}",
            f"Kategória: {str(section.get('label', '')).strip()}",
            f"Leírás: {str(category.get('boxDescription', '') or category.get('defaultBoxDescription', '')).strip()}",
        ]
        return " ".join(item for item in details if not item.endswith(": "))

    def handle_topfloor_box_close_action(self, action: str, category_key: str, payload: dict) -> None:
        """Close a Topfloor box and persist each row as loaded or failed."""
        shipment_id = _manufacturing_normalize_number(payload.get("shipment_id", ""))
        raw_entries = payload.get("entries", [])
        entries = [
            {
                "code": str(item.get("code", "")).strip(),
                "state_storage_key": str(item.get("state_storage_key", "") or item.get("state_key", "")).strip(),
            }
            for item in raw_entries
            if isinstance(item, dict)
        ] if isinstance(raw_entries, list) else []
        entries = [entry for entry in entries if entry["code"] and entry["state_storage_key"]]
        if not shipment_id:
            shipment_id = _manufacturing_normalize_number(category_key.split("::", 1)[0])
        if not shipment_id:
            self.respond_json(400, {"ok": False, "error": "Hiányzik a shipmentID."})
            return

        result = _topfloor_load_and_close_category_box(
            category_key,
            [entry["code"] for entry in entries],
            con_description=str(payload.get("con_description", "")).strip(),
        )
        box_id = str(result.get("conId", "")).strip()
        if not box_id:
            self.respond_json(500, {"ok": False, "error": "A doboz zárása után nincs conId."})
            return

        topfloor_runtime_root = self.manufacturing_state_runtime_root("topfloor")
        failed_barcodes = {
            str(item.get("barcodeId", "")).strip().upper()
            for item in result.get("failedItems", [])
            if isinstance(item, dict) and str(item.get("barcodeId", "")).strip()
        }
        loaded_state_keys: list[str] = []
        failed_state_keys: list[str] = []
        for entry in entries:
            target_state = "red" if str(entry["code"]).strip().upper() in failed_barcodes else box_id
            save_selection_state(
                topfloor_runtime_root,
                shipment_id,
                entry["state_storage_key"],
                target_state,
            )
            if target_state == "red":
                failed_state_keys.append(entry["state_storage_key"])
            else:
                loaded_state_keys.append(entry["state_storage_key"])

        self.respond_json(
            200,
            {
                "ok": True,
                "action": action,
                "box": result,
                "shipment_id": shipment_id,
                "state": box_id,
                "state_keys": loaded_state_keys,
                "failed_state_keys": failed_state_keys,
                "failed_items": result.get("failedItems", []),
            },
        )

    def do_POST(self):
        """Route authenticated POST requests for uploads, state, and actions."""
        self._theme_user = self.current_user()
        self.wfile = _ThemedResponseWriter(self.wfile, self._theme_user)
        path = _normalize_path(self.path)
        if path == LOGIN_ROUTE:
            self.handle_login()
            return

        if self.reject_unauthorized_module():
            return

        if path == ADMIN_MANUFACTURING_SHIPMENT_DATE_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return
            shipment_id = _manufacturing_normalize_number(payload.get("shipment_id", ""))
            shipment_date = str(payload.get("shipment_date", "") or "").strip()
            if not shipment_id:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a szállítmány azonosítója."})
                return
            try:
                saved_date = save_admin_manufacturing_shipment_date(
                    admin_manufacturing_runtime_dir() / "topfloor",
                    shipment_id,
                    shipment_date,
                )
                admin_change_revision = signal_admin_manufacturing_change(
                    admin_manufacturing_runtime_dir(),
                    kind="shipment-date",
                    target=shipment_id,
                )
            except ValueError as exc:
                self.respond_json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A szállítási dátum mentése nem sikerült: {exc}"})
                return
            self.respond_json(
                200,
                {
                    "ok": True,
                    "shipment_id": shipment_id,
                    "shipment_date": saved_date,
                    "admin_change_revision": admin_change_revision,
                },
            )
            return

        if path == ADMIN_MANUFACTURING_ROW_DATA_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return
            production_number = _manufacturing_normalize_number(payload.get("production_number", ""))
            row_key = str(payload.get("row_key", "")).strip()
            document_key = str(payload.get("document_key", "")).strip()
            category_key = str(payload.get("category_key", "")).strip()
            state_keys = payload.get("state_keys", [])
            visible_state = str(payload.get("visible_state", "")).strip().lower()
            fields = payload.get("fields", {})
            if not production_number or not row_key or not isinstance(fields, dict) or not isinstance(state_keys, list):
                self.respond_json(400, {"ok": False, "error": "Hiányos soradat-mentési kérés."})
                return
            runtime_root = admin_manufacturing_runtime_dir()
            is_topfloor_row = document_key == "topfloor" or row_key.startswith("topfloor::")
            if is_topfloor_row:
                runtime_root = runtime_root / "topfloor"
            try:
                requires_edit_alert = bool(
                    admin_manufacturing_topfloor_row_requires_edit_alert(
                        runtime_root,
                        production_number,
                        category_key,
                        row_key,
                    )
                    if is_topfloor_row
                    else admin_manufacturing_row_requires_edit_alert(
                        runtime_root,
                        production_number,
                        row_key,
                        [str(value or "").strip() for value in state_keys],
                        visible_state,
                    )
                )
                saved_fields = save_admin_manufacturing_row_data(
                    runtime_root,
                    production_number,
                    row_key,
                    fields,
                )
                if requires_edit_alert:
                    save_admin_manufacturing_issued_row_edit_marker(
                        runtime_root,
                        production_number,
                        row_key,
                        category_key,
                        set(fields),
                    )
                admin_change_revision = signal_admin_manufacturing_change(
                    admin_manufacturing_runtime_dir(),
                    kind="row-data",
                    target=production_number,
                )
            except ValueError as exc:
                self.respond_json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A soradat mentése nem sikerült: {exc}"})
                return
            self.respond_json(
                200,
                {
                    "ok": True,
                    "production_number": production_number,
                    "row_key": row_key,
                    "fields": saved_fields,
                    "issued_after_edit": requires_edit_alert,
                    "requires_edit_alert": requires_edit_alert,
                    "admin_change_revision": admin_change_revision,
                },
            )
            return

        if _route_matches(path, ADMIN_MANUFACTURING_ROUTE):
            self.respond_json(
                405,
                {"ok": False, "error": "Az Admin Gyártási Papírok modul csak megfigyelésre használható."},
            )
            return

        if path == MANUFACTURING_ISSUED_EDIT_COMPLETE_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return
            production_number = _manufacturing_normalize_number(
                payload.get("production_number", "") or payload.get("shipment_id", "")
            )
            document_key = str(payload.get("document_key", "")).strip()
            row_key = str(payload.get("row_key", "")).strip()
            if not production_number or not row_key:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a gyártás/szállítmány vagy a sorazonosító."})
                return
            try:
                alert_runtime_root = manufacturing_runtime_dir()
                if document_key == "topfloor":
                    alert_runtime_root = alert_runtime_root / "topfloor"
                completed = complete_issued_row_edit(
                    alert_runtime_root,
                    production_number,
                    row_key,
                )
                admin_change_revision = signal_admin_manufacturing_change(
                    manufacturing_runtime_dir(),
                    kind="issued-row-edit-complete",
                    target=production_number,
                )
            except ValueError as exc:
                self.respond_json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A figyelmeztetés lezárása nem sikerült: {exc}"})
                return
            self.respond_json(
                200,
                {
                    "ok": True,
                    "completed": completed,
                    "production_number": production_number,
                    "shipment_id": production_number if document_key == "topfloor" else "",
                    "row_key": row_key,
                    "admin_change_revision": admin_change_revision,
                },
            )
            return

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
            state_key = str(payload.get("state_key", "")).strip()
            extra_state_keys = (
                [str(item).strip() for item in payload.get("state_keys", []) if str(item).strip()]
                if isinstance(payload.get("state_keys"), list)
                else []
            )
            document_key = str(payload.get("document_key", "")).strip()
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
                target_state_keys: list[str] = []
                for candidate_state_key in [state_key, *extra_state_keys]:
                    if candidate_state_key and candidate_state_key not in target_state_keys:
                        target_state_keys.append(candidate_state_key)
                if not target_state_keys:
                    target_state_keys = target_row_ids
                state_runtime_root = self.manufacturing_state_runtime_root(document_key, target_state_keys)
                current_saved_state = load_selection_state(state_runtime_root, production_number)
                locked_done_row_ids = [
                    target_key
                    for target_key in target_state_keys
                    if str(current_saved_state.get(target_key, "")).strip().lower() == "done"
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
                for target_state_key in target_state_keys:
                    current_state = save_selection_state(state_runtime_root, production_number, target_state_key, state)
                for legacy_row_id in target_row_ids:
                    if legacy_row_id not in target_state_keys:
                        current_state = save_selection_state(state_runtime_root, production_number, legacy_row_id, "clear")
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A mentés nem sikerült: {exc}"})
                return

            self.respond_json(
                200,
                {
                    "ok": True,
                    "production_number": production_number,
                    "row_id": row_id,
                    "state_key": target_state_keys[0] if target_state_keys else "",
                    "state": current_state.get(target_state_keys[0], "") if target_state_keys else "",
                    "row_ids": target_row_ids,
                    "state_keys": target_state_keys,
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
                    manufacturing_runtime_dir(),
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

        if path == MANUFACTURING_TOPFLOOR_BOX_ROUTE:
            request_started_at = time.perf_counter()
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            action = str(payload.get("action", "")).strip().lower()
            category_key = str(payload.get("category_key", "")).strip()
            log_status = "ok"
            if not category_key:
                self.respond_json(400, {"ok": False, "error": "Hiányzik az Anyagraktár kategória azonosító."})
                print(
                    f"[topfloor-box] action={action or '-'} category=- status=400 took {time.perf_counter() - request_started_at:.3f}s",
                    flush=True,
                )
                return
            if action not in {"create", "open", "close", "reprint-label", "issue-storage-box"}:
                self.respond_json(400, {"ok": False, "error": "Érvénytelen Anyagraktár doboz művelet."})
                print(
                    f"[topfloor-box] action={action or '-'} category={category_key} status=400 took {time.perf_counter() - request_started_at:.3f}s",
                    flush=True,
                )
                return

            try:
                restriction_error = self.topfloor_box_restriction_error(action, category_key, payload)
                if restriction_error:
                    self.respond_json(409, {"ok": False, "error": restriction_error})
                    log_status = "409"
                    return
                if self.handle_topfloor_box_simple_action(action, category_key, payload):
                    return
                self.handle_topfloor_box_close_action(action, category_key, payload)
                return
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"Az Anyagraktár doboz művelet nem sikerült: {exc}"})
                log_status = "500"
                return
            finally:
                print(
                    f"[topfloor-box] action={action} category={category_key} status={log_status} took {time.perf_counter() - request_started_at:.3f}s",
                    flush=True,
                )

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
            document_key = str(payload.get("document_key", "")).strip()
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
                state_storage_key = str(item.get("state_storage_key", "") or state_key).strip()
                code = _extract_con_code(item.get("code", ""))
                entry_category_key = str(item.get("category_key") or category_key).strip()
                entry_document_key = str(item.get("document_key") or document_key).strip()
                source_row_ids = (
                    [
                        str(value).strip()
                        for value in item.get("source_row_ids", [])
                        if str(value).strip() and not _manufacturing_is_virtual_unit_row_id(value)
                    ]
                    if isinstance(item.get("source_row_ids"), list)
                    else []
                )
                if not row_id or _manufacturing_is_virtual_unit_row_id(row_id) or not state_key or not code:
                    continue
                entries.append(
                    {
                        "row_id": row_id,
                        "state_key": state_key,
                        "state_storage_key": state_storage_key,
                        "code": code,
                        "category_key": entry_category_key,
                        "document_key": entry_document_key,
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
                        _manufacturing_ready_endpoint_key(entry.get("document_key", ""), entry.get("category_key", "")),
                    )
                    for entry in entries
                    if entry.get("code")
                }
            )
            failures: list[dict[str, str | int]] = []
            success_targets: set[tuple[str, str]] = set()
            shopfloor_clients: dict[str, _ShopfloorApiClient] = {}
            for code, ready_endpoint in scan_targets:
                fallback_endpoint = "validatescan+processscan" if ready_endpoint in {"assembly", "front"} else "processscan"
                try:
                    client = shopfloor_clients.get(ready_endpoint)
                    if client is None:
                        client = _ShopfloorApiClient.for_endpoint(ready_endpoint)
                        shopfloor_clients[ready_endpoint] = client
                    status_code, response_body, endpoint_name = _shopfloor_report_con_ready(
                        code,
                        ready_endpoint=ready_endpoint,
                        client=client,
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
                    success_targets.add((code, ready_endpoint))
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
            done_state_keys: list[str] = []
            skipped_row_ids: list[str] = []
            skipped_state_keys: list[str] = []
            try:
                for entry in entries:
                    entry_code = str(entry.get("code", "")).strip().upper()
                    entry_ready_endpoint = _manufacturing_ready_endpoint_key(entry.get("document_key", ""), entry.get("category_key", ""))
                    target_ids = [
                        str(entry.get("row_id", "")).strip(),
                        *[
                            str(value).strip()
                            for value in entry.get("source_row_ids", [])
                            if str(value).strip() and not _manufacturing_is_virtual_unit_row_id(value)
                        ],
                    ]
                    unique_target_ids: list[str] = []
                    for target_id in target_ids:
                        if target_id and target_id not in unique_target_ids:
                            unique_target_ids.append(target_id)
                    source_state_keys = [
                        str(value).strip()
                        for value in entry.get("source_row_ids", [])
                        if str(value).strip() and not _manufacturing_is_virtual_unit_row_id(value)
                    ]
                    target_state_keys = source_state_keys or [
                        str(entry.get("state_storage_key", "") or entry.get("state_key", "") or entry.get("row_id", "")).strip()
                    ]
                    if (entry_code, entry_ready_endpoint) not in success_targets:
                        skipped_row_ids.extend(unique_target_ids)
                        skipped_state_keys.extend([key for key in target_state_keys if key])
                        continue
                    state_runtime_root = self.manufacturing_state_runtime_root(document_key, target_state_keys)
                    for target_id in target_state_keys:
                        if not target_id:
                            continue
                        save_selection_state(state_runtime_root, production_number, target_id, "done")
                        done_state_keys.append(target_id)
                    for target_id in unique_target_ids:
                        if target_id not in target_state_keys:
                            save_selection_state(state_runtime_root, production_number, target_id, "clear")
                        done_row_ids.append(target_id)
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A kész állapot mentése nem sikerült: {exc}"})
                return

            unique_done_ids = sorted(set(done_row_ids))
            unique_done_state_keys = sorted(set(done_state_keys))
            unique_skipped_ids = sorted(set(skipped_row_ids))
            unique_skipped_state_keys = sorted(set(skipped_state_keys))
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
                    "reported_codes": sorted({code for code, _ready_endpoint in success_targets}),
                    "failed": failures,
                    "done_row_ids": unique_done_ids,
                    "done_state_keys": unique_done_state_keys,
                    "skipped_row_ids": unique_skipped_ids,
                    "skipped_state_keys": unique_skipped_state_keys,
                },
            )
            return







        if path == MATT_INVENTORY_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            status, body = process_matt_inventory_upload(files)
            self.send_response(status)
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

        if path in {MATERIAL_INVENTORY_PRESENCE_ROUTE, SEMIFINISHED_INVENTORY_PRESENCE_ROUTE, SEMIFINISHED_FRONT_INVENTORY_PRESENCE_ROUTE}:
            if path == SEMIFINISHED_FRONT_INVENTORY_PRESENCE_ROUTE:
                config = _unified_inventory_config("semifinished_front")
            elif path == SEMIFINISHED_INVENTORY_PRESENCE_ROUTE:
                config = _unified_inventory_config("semifinished")
            else:
                config = _unified_inventory_config("material")
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)
            active_categories = _unified_inventory_touch_presence(
                config,
                form_data.get("token", ""),
                form_data.get("category", ""),
                clear=form_data.get("clear", "") == "1",
            )
            sync_payload = _unified_inventory_sync_payload(config, form_data.get("category", ""))
            self.respond_json(200, {"ok": True, "active_categories": active_categories, **sync_payload})
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
            status_code, body = process_order_upload(_extract_uploaded_files(self.headers, raw_body))
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_APPROVE_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_APPROVE_PREFIX) + 1 :]
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            result = approve_order_job(job_id, _parse_urlencoded_body(raw_body))
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_PROCUREMENT_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            status_code, body = process_procurement_upload(_extract_uploaded_files(self.headers, raw_body))
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_LAUNCH_PREFIX) + 1 :]
            result = launch_order_job(job_id)
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_STOP_PREFIX) + 1 :]
            result = stop_order_job(job_id)
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_PARTS_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_PARTS_PREFIX) + 1 :]
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            result = rebuild_procurement_parts(job_id, _extract_uploaded_files(self.headers, raw_body))
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_COMPARE_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            status_code, body = process_compare_upload(_extract_uploaded_files(self.headers, raw_body))
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX) + 1 :]
            result = launch_procurement_job(job_id)
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_STOP_PREFIX) + 1 :]
            result = stop_procurement_job(job_id)
            if result is None:
                self.send_error(404)
                return

            status_code, body = result
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == HR_APP_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            upload = files.get("people_file")
            if upload is None:
                self.respond_hr_form("Hiányzik az Excel fájl.")
                return
            _name, file_data = upload
            try:
                people = read_people(file_data)
                bosses = json.loads((DATA_DIR / "HR-files" / "bosses.json").read_text(encoding="utf-8"))
                body = apply_hr_theme(render_hr_review(people, bosses), self.current_user())
            except Exception as exc:
                self.respond_hr_form(f"Az Excel beolvasása nem sikerült: {exc}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == HR_CONFIRM_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            form_data = _parse_urlencoded_body(self.rfile.read(content_length))
            try:
                count = int(form_data.get("row_count", "0"))
                selected_indices = [index for index in range(count) if form_data.get(f"p_{index}_selected") == "1"]
                if not selected_indices:
                    raise ValueError("Legalább egy személyt válassz ki a dokumentumgeneráláshoz.")
                people = [{key: str(form_data.get(f"p_{index}_{key}", "")) for key in HR_DATA_COLUMNS} for index in selected_indices]
                required_person_keys = tuple(key for key in HR_DATA_COLUMNS if key != "stayaddress") + ("jobdescription",)
                for row_number, person in zip(selected_indices, people):
                    person["jobdescription"] = str(form_data.get(f"p_{row_number}_jobdescription", ""))
                    missing = [key for key in required_person_keys if not person.get(key, "").strip()]
                    if missing:
                        raise ValueError(f"A(z) {row_number + 1}. kiválasztott sorban minden személyes mezőt ki kell tölteni.")
                    if not person.get("stayaddress", "").strip():
                        person["stayaddress"] = person.get("address", "")
                bosses = json.loads((DATA_DIR / "HR-files" / "bosses.json").read_text(encoding="utf-8"))
                extra_keys = ("workplace", "boss", "workbreak", "breaktype", "orderfromname", "qualification", "requirements")
                extras = []
                for index in selected_indices:
                    person_extra = {key: str(form_data.get(f"p_{index}_{key}", "")) for key in extra_keys}
                    missing_extra = [key for key in extra_keys if not person_extra.get(key, "").strip()]
                    if missing_extra:
                        raise ValueError(f"A(z) {index + 1}. kiválasztott sorban minden további mezőt ki kell tölteni.")
                    person_boss = person_extra.get("boss", "")
                    if person_boss not in bosses:
                        raise ValueError(f"Érvénytelen felettes a(z) {index + 1}. személynél.")
                    person_extra["boss_data"] = bosses[person_boss]
                    extras.append(person_extra)
                payload, download_name = build_hr_documents(people, extras, DATA_DIR / "HR-files")
            except Exception as exc:
                self.respond_hr_form(f"A dokumentumok generálása nem sikerült: {exc}", status=400)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(download_name)}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path != GENERATE_ROUTE:
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        file_name, file_data = extract_invoice_upload(_extract_uploaded_files(self.headers, raw_body))

        if not file_data or not file_name:
            self.respond_form("Hibás kérés: hiányzó feltöltési adatok.")
            return

        if not file_name.lower().endswith(".pdf"):
            self.respond_form("Csak PDF fájl tölthető fel.")
            return

        try:
            status, payload, content_type, headers = build_invoice_response(file_name, file_data)
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
        """Return the invoice translator form with a validation error."""
        body = render_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_hr_form(self, message: str, status: int = 400):
        body = apply_hr_theme(render_hr_form(message), self.current_user())
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_procurement_form(self, message: str):
        """Return the NettFront procurement form with a validation error."""
        body = render_nettfront_procurement_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_matt_inventory_form(self, message: str):
        """Return the Matt inventory form with a validation error."""
        body = render_matt_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_material_inventory_form(self, message: str):
        """Return the material inventory form with a validation error."""
        body = render_material_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_semifinished_inventory_form(self, message: str):
        """Return the semifinished inventory form with a validation error."""
        body = render_material_inventory_form(message, inventory_kind="semifinished")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_semifinished_front_inventory_form(self, message: str):
        """Return the semifinished-front inventory form with a validation error."""
        body = render_material_inventory_form(message, inventory_kind="semifinished_front")
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_front_inventory_form(self, message: str):
        """Return the front inventory form with a validation error."""
        body = render_front_inventory_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


    def respond_json(self, status_code: int, payload: dict):
        """Send a no-store JSON response with UTF-8 encoding."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)








if __name__ == "__main__":
    if DEV_RELOAD_ENABLED and os.getenv(DEV_CHILD_ENV) != "1":
        run_dev_supervisor(
            base_dir=BASE_DIR,
            port=PORT,
            script_path=Path(__file__),
            child_env=DEV_CHILD_ENV,
            reload_token_env=DEV_RELOAD_TOKEN_ENV,
            interval_seconds=DEV_WATCH_INTERVAL_SECONDS,
            watched_extensions=WATCHED_EXTENSIONS,
            watched_files=WATCHED_FILES,
            ignored_dirs=WATCH_IGNORED_DIRS,
        )
    else:
        if MANUFACTURING_PRIME_SYNC_ON_START:
            _prime_manufacturing_cache_worker(include_all_red_view=False, limit=10)
        _prime_manufacturing_cache_async()
        server = ReusableThreadingHTTPServer((HOST, PORT), InvoiceHandler)
        print(f"Server running on http://localhost:{PORT} (bind: {HOST}:{PORT})")
        server.serve_forever()
