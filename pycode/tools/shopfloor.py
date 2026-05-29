"""Shopfloor API helpers for reporting CON readiness."""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

SHOPFLOOR_BASE_URL = os.getenv("SHOPFLOOR_BASE_URL", "https://app01.internal.divian.hu:9000").rstrip("/")
SHOPFLOOR_USERNAME = os.getenv("SHOPFLOOR_USERNAME", "alkatresz")
SHOPFLOOR_PASSWORD = os.getenv("SHOPFLOOR_PASSWORD", "PPddaa1234")
SHOPFLOOR_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_CHECKPOINT_ID", "103"))
SHOPFLOOR_TAB_ID = int(os.getenv("SHOPFLOOR_TAB_ID", "178"))
SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID", "104"))
SHOPFLOOR_ASSEMBLY_TAB_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_TAB_ID", "181"))
SHOPFLOOR_FRONT_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_FRONT_CHECKPOINT_ID", "107"))
SHOPFLOOR_FRONT_TAB_ID = int(os.getenv("SHOPFLOOR_FRONT_TAB_ID", "182"))
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


def extract_con_code(value: object) -> str:
    """Extract a normalized CON code from free text."""
    text = str(value or "").strip().upper()
    match = re.search(r"\bCON\D*?(\d{6,})\b", text)
    return f"CON{match.group(1)}" if match else ""


def report_con_ready(
    con_code: str,
    *,
    use_assembly_validate: bool = False,
    ready_endpoint: str = "default",
) -> tuple[int, str, str]:
    """Report a CON as ready through the configured Shopfloor endpoint."""
    con_text = str(con_code or "").strip().upper()
    match = re.fullmatch(r"CON(\d{1,12})", con_text)
    if not match:
        raise ValueError(f"Érvénytelen CON azonosító: {con_code}")
    con_id = int(match.group(1))

    auth_header = _shopfloor_auth_header()
    connection_id = _shopfloor_negotiate_connection_id(auth_header)
    checkpoint_id, tab_id, requires_validate = _shopfloor_ready_endpoint_config(ready_endpoint, use_assembly_validate)
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
        req = urllib.request.Request(endpoint_url(endpoint_name), method="POST", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, context=context, timeout=20) as response:
                body = response.read().decode("utf-8", errors="ignore")
                return int(response.getcode() or 0), body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            return int(exc.code or 0), body

    if requires_validate:
        validate_status_code, validate_response_body = submit("validatescan", request_body)
        if not 200 <= int(validate_status_code) < 300:
            return validate_status_code, validate_response_body, "validatescan"
        validate_data = _shopfloor_extract_validate_data(validate_response_body)
        process_body = _shopfloor_process_payload(con_id, validate_data)
        process_status_code, process_response_body = submit("processscan", process_body)
        return process_status_code, process_response_body, "processscan"

    status_code, response_body = submit("processscan", request_body)
    return status_code, response_body, "processscan"


def _shopfloor_auth_header() -> str:
    auth_raw = f"{SHOPFLOOR_USERNAME}:{SHOPFLOOR_PASSWORD}"
    auth_b64 = base64.b64encode(auth_raw.encode("utf-8", errors="ignore")).decode("ascii", errors="ignore")
    return f"Basic {auth_b64}"


def _shopfloor_negotiate_connection_id(auth_header: str) -> str:
    encoded_auth = urllib.parse.quote(auth_header, safe="")
    negotiate_url = f"{SHOPFLOOR_BASE_URL}/api/hubs/mainhub/negotiate?authorize={encoded_auth}&negotiateVersion=1"
    req = urllib.request.Request(negotiate_url, method="POST")
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


def _shopfloor_ready_endpoint_config(ready_endpoint: str, use_assembly_validate: bool) -> tuple[int, int, bool]:
    endpoint_key = str(ready_endpoint or "").strip().lower()
    if use_assembly_validate or endpoint_key == "assembly":
        return SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID, SHOPFLOOR_ASSEMBLY_TAB_ID, True
    if endpoint_key == "front":
        return SHOPFLOOR_FRONT_CHECKPOINT_ID, SHOPFLOOR_FRONT_TAB_ID, True
    return SHOPFLOOR_CHECKPOINT_ID, SHOPFLOOR_TAB_ID, False

