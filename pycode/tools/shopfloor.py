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
from datetime import date
from pathlib import Path

SHOPFLOOR_BASE_URL = os.getenv("SHOPFLOOR_BASE_URL", "https://app01.internal.divian.hu:9000").rstrip("/")
SHOPFLOOR_USERNAME = os.getenv("SHOPFLOOR_USERNAME", "alkatresz")
SHOPFLOOR_PASSWORD = os.getenv("SHOPFLOOR_PASSWORD", "PPddaa1234")
SHOPFLOOR_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_CHECKPOINT_ID", "103"))
SHOPFLOOR_TAB_ID = int(os.getenv("SHOPFLOOR_TAB_ID", "178"))
SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID", "104"))
SHOPFLOOR_ASSEMBLY_TAB_ID = int(os.getenv("SHOPFLOOR_ASSEMBLY_TAB_ID", "181"))
SHOPFLOOR_FRONT_CHECKPOINT_ID = int(os.getenv("SHOPFLOOR_FRONT_CHECKPOINT_ID", "107"))
SHOPFLOOR_FRONT_TAB_ID = int(os.getenv("SHOPFLOOR_FRONT_TAB_ID", "182"))
TOPFLOOR_USERNAME = os.getenv("TOPFLOOR_USERNAME", "elzaras")
TOPFLOOR_PASSWORD = os.getenv("TOPFLOOR_PASSWORD", "PPddaa1234")
TOPFLOOR_BOXING_CHECKPOINT_ID = int(os.getenv("TOPFLOOR_BOXING_CHECKPOINT_ID", "124"))
TOPFLOOR_BOXING_TAB_ID = int(os.getenv("TOPFLOOR_BOXING_TAB_ID", "202"))
TOPFLOOR_UNLOADING_CHECKPOINT_ID = int(os.getenv("TOPFLOOR_UNLOADING_CHECKPOINT_ID", "126"))
TOPFLOOR_UNLOADING_TAB_ID = int(os.getenv("TOPFLOOR_UNLOADING_TAB_ID", "204"))
TOPFLOOR_BOX_CTS_ID = int(os.getenv("TOPFLOOR_BOX_CTS_ID", "24"))
TOPFLOOR_RUNTIME_DIR = Path(os.getenv("TOPFLOOR_RUNTIME_DIR", "runtime/gyartasi-papirok/topfloor"))
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


class ShopfloorApiClient:
    """Small authenticated Shopfloor API client for multi-step workflows."""

    def __init__(self, auth_header: str, connection_id: str):
        self.auth_header = auth_header
        self.connection_id = connection_id
        self.quoted_connection_id = urllib.parse.quote(connection_id, safe="")
        self.context = ssl._create_unverified_context()

    @classmethod
    def for_endpoint(cls, ready_endpoint: str) -> "ShopfloorApiClient":
        """Create an API client with the credentials for an endpoint family."""
        auth_header = _shopfloor_auth_header(*_shopfloor_ready_endpoint_credentials(ready_endpoint))
        return cls(auth_header, _shopfloor_negotiate_connection_id(auth_header))

    def post_json_url(self, url: str, payload: object | None = None, *, timeout: int = 20) -> tuple[int, str]:
        """POST JSON to a Shopfloor URL and return status and body."""
        headers = {"Authorization": self.auth_header, "Content-Type": "application/json"}
        data = json.dumps({} if payload is None else payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, method="POST", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, context=self.context, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
                return int(response.getcode() or 0), body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            return int(exc.code or 0), body

    def run_procedure(
        self,
        checkpoint_id: int,
        tab_id: int,
        procedure_id: int,
        payload: object | None = None,
        *,
        processing_options: int | None = None,
    ) -> tuple[int, str]:
        """Run a Shopfloor tab procedure."""
        query_parts: list[str] = []
        if processing_options is not None:
            query_parts.append(f"processingOptions={int(processing_options)}")
        query_parts.append(f"connectionId={self.quoted_connection_id}")
        query = "&".join(query_parts)
        url = (
            f"{SHOPFLOOR_BASE_URL}/api/shopfloor/checkpoints/{int(checkpoint_id)}"
            f"/tabs/{int(tab_id)}/runprocedure/{int(procedure_id)}?{query}"
        )
        return self.post_json_url(url, payload)

    def scan_endpoint(
        self,
        checkpoint_id: int,
        tab_id: int,
        endpoint_name: str,
        scan_text: str,
        payload: object,
    ) -> tuple[int, str]:
        """Submit a validatescan/processscan request."""
        quoted_scan = urllib.parse.quote(str(scan_text or "").strip(), safe="")
        url = (
            f"{SHOPFLOOR_BASE_URL}/api/shopfloor/checkpoints/{int(checkpoint_id)}"
            f"/tabs/{int(tab_id)}/{endpoint_name}/{quoted_scan}?connectionId={self.quoted_connection_id}"
        )
        return self.post_json_url(url, payload)


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

    checkpoint_id, tab_id, requires_validate = _shopfloor_ready_endpoint_config(ready_endpoint, use_assembly_validate)
    auth_header = _shopfloor_auth_header(*_shopfloor_ready_endpoint_credentials(ready_endpoint))
    connection_id = _shopfloor_negotiate_connection_id(auth_header)
    quoted_connection_id = urllib.parse.quote(connection_id, safe="")
    request_body = _shopfloor_process_payload(con_id)
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    context = ssl._create_unverified_context()

    def endpoint_url(endpoint_name: str) -> str:
        """Provide endpoint url behavior."""
        return (
            f"{SHOPFLOOR_BASE_URL}/api/shopfloor/checkpoints/{checkpoint_id}"
            f"/tabs/{tab_id}/{endpoint_name}/{con_text}?connectionId={quoted_connection_id}"
        )

    def submit(endpoint_name: str, data: bytes) -> tuple[int, str]:
        """Provide submit behavior."""
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


def create_topfloor_box(con_description: str = "", client: ShopfloorApiClient | None = None) -> dict[str, object]:
    """Create a Topfloor box container and persist its draft metadata."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    return _topfloor_create_box(client, con_description=con_description)


def create_closed_topfloor_category_box(
    category_key: str,
    *,
    con_description: str = "",
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Create, close, and assign a Topfloor box to a category."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    box = create_topfloor_box(con_description=con_description, client=client)
    closed = close_topfloor_box_with_items(box, (), client=client)
    _save_topfloor_category_box(category_key, closed, open_state=False)
    return closed


def open_topfloor_box(box: dict[str, object] | int, client: ShopfloorApiClient | None = None) -> dict[str, object]:
    """Open an existing Topfloor box and refresh its state."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    con_id = _topfloor_box_con_id(box)
    _topfloor_open_box(client, con_id)
    return {"conId": con_id, "opened": True}


def open_topfloor_category_box(category_key: str, client: ShopfloorApiClient | None = None) -> dict[str, object]:
    """Open the box assigned to a Topfloor category."""
    _topfloor_require_no_other_open_box(category_key)
    box = _topfloor_category_box(category_key)
    result = open_topfloor_box(box, client=client)
    _save_topfloor_category_box(category_key, box, open_state=True)
    return result


def unload_topfloor_item_into_box(
    box: dict[str, object] | int,
    barcode_id: str,
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Unload one item and add it to an already-open Topfloor box."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    con_id = _topfloor_box_con_id(box)
    scan = str(barcode_id or "").strip()
    if not scan:
        raise ValueError("Hiányzik a Topfloor tétel barcodeId.")
    scan_result = _topfloor_try_scan_unloading_item(client, scan)
    _topfloor_put_item_in_box(client, con_id, scan)
    _topfloor_update_box(client, con_id)
    return {"conId": con_id, "barcodeId": scan, "state": "loaded", "scan": scan_result}


def unload_topfloor_items_into_box(
    box: dict[str, object] | int,
    barcode_ids: list[str] | tuple[str, ...],
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Unload multiple items into an already-open Topfloor box."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    loaded_items: list[str] = []
    failed_items: list[dict[str, str]] = []
    for barcode_id in barcode_ids:
        clean_barcode_id = str(barcode_id or "").strip()
        if not clean_barcode_id:
            continue
        try:
            result = unload_topfloor_item_into_box(box, clean_barcode_id, client=client)
        except Exception as exc:
            failed_items.append({"barcodeId": clean_barcode_id, "error": str(exc)})
            continue
        loaded_items.append(str(result["barcodeId"]))
    return {"conId": _topfloor_box_con_id(box), "items": loaded_items, "failedItems": failed_items}


def close_topfloor_box_with_items(
    box: dict[str, object] | int,
    loaded_barcode_ids: list[str] | tuple[str, ...] = (),
    *,
    con_date: str = "",
    con_description: str = "",
    cts_id: int | None = None,
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Close a Topfloor box after its loaded items are known."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    box_payload = _topfloor_box_payload(box, con_date=con_date, con_description=con_description, cts_id=cts_id)
    _topfloor_close_box(
        client,
        int(box_payload["conId"]),
        str(box_payload["conDate"]),
        str(box_payload["conDescription"]),
        int(box_payload["ctsId"]),
    )
    completed_items = [str(item).strip() for item in loaded_barcode_ids if str(item).strip()]
    return {**box_payload, "items": completed_items, "closed": True}


def close_topfloor_category_box_with_items(
    category_key: str,
    loaded_barcode_ids: list[str] | tuple[str, ...],
    *,
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Close a Topfloor category box with loaded item IDs."""
    box = _topfloor_category_box(category_key)
    result = close_topfloor_box_with_items(box, loaded_barcode_ids, client=client)
    _save_topfloor_category_box(category_key, result, open_state=False)
    return result


def load_and_close_topfloor_category_box(
    category_key: str,
    barcode_ids: list[str] | tuple[str, ...],
    *,
    client: ShopfloorApiClient | None = None,
) -> dict[str, object]:
    """Load items into an open Topfloor category box and close it."""
    client = client or ShopfloorApiClient.for_endpoint("topfloor_boxing")
    box = _topfloor_category_box(category_key)
    loaded = unload_topfloor_items_into_box(box, barcode_ids, client=client)
    result = close_topfloor_category_box_with_items(category_key, loaded["items"], client=client)
    return {**result, "failedItems": loaded.get("failedItems", [])}


def _shopfloor_auth_header(username: str = SHOPFLOOR_USERNAME, password: str = SHOPFLOOR_PASSWORD) -> str:
    """Provide shopfloor auth header behavior."""
    auth_raw = f"{username}:{password}"
    auth_b64 = base64.b64encode(auth_raw.encode("utf-8", errors="ignore")).decode("ascii", errors="ignore")
    return f"Basic {auth_b64}"


def _shopfloor_negotiate_connection_id(auth_header: str) -> str:
    """Provide shopfloor negotiate connection id behavior."""
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
    """Provide shopfloor process payload behavior."""
    payload = dict(SHOPFLOOR_PROCESS_PAYLOAD)
    payload["conId"] = con_id
    if validate_data is not None:
        payload["validateData"] = validate_data
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _shopfloor_extract_validate_data(response_body: str) -> object | None:
    """Provide shopfloor extract validate data behavior."""
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


def _topfloor_create_box(client: ShopfloorApiClient, *, con_description: str = "") -> dict[str, object]:
    """Run the Topfloor create/update sequence for a new box."""
    status_code, response_body = client.run_procedure(
        TOPFLOOR_BOXING_CHECKPOINT_ID,
        TOPFLOOR_BOXING_TAB_ID,
        1,
        processing_options=2,
    )
    _shopfloor_require_success(status_code, response_body, "topfloor create box")
    data = _topfloor_response_data(response_body)
    con_id = int(data.get("conId") or 0)
    cts_id = int(data.get("ctsId") or TOPFLOOR_BOX_CTS_ID)
    if con_id <= 0:
        raise RuntimeError("A Topfloor doboz létrehozási válaszban nincs conId.")
    con_date = date.today().isoformat()
    # TODO: Generate the final Topfloor box description.
    con_desc = str(con_description or "")
    _topfloor_update_box(client, con_id)
    return {
        "conId": con_id,
        "conDate": con_date,
        "conDescription": con_desc,
        "ctsId": cts_id,
        "raw": data,
    }


def _topfloor_open_box(client: ShopfloorApiClient, con_id: int) -> None:
    """Open an existing Topfloor box before item scans."""
    status_code, response_body = client.run_procedure(
        TOPFLOOR_BOXING_CHECKPOINT_ID,
        TOPFLOOR_BOXING_TAB_ID,
        2,
        {"scan": str(int(con_id))},
    )
    _shopfloor_require_success(status_code, response_body, "topfloor open box")
    _topfloor_update_box(client, con_id)


def _topfloor_update_box(client: ShopfloorApiClient, con_id: int) -> None:
    """Refresh Topfloor box state after open/create/item insert."""
    status_code, response_body = client.run_procedure(
        TOPFLOOR_BOXING_CHECKPOINT_ID,
        TOPFLOOR_BOXING_TAB_ID,
        3,
        {"conId": int(con_id)},
    )
    _shopfloor_require_success(status_code, response_body, "topfloor update box")


def _topfloor_put_item_in_box(client: ShopfloorApiClient, con_id: int, barcode_id: str) -> None:
    """Put one unloaded item into an open Topfloor box."""
    status_code, response_body = client.run_procedure(
        TOPFLOOR_BOXING_CHECKPOINT_ID,
        TOPFLOOR_BOXING_TAB_ID,
        4,
        {
            "conId": int(con_id),
            "scan": str(barcode_id),
            "cptId": TOPFLOOR_BOXING_CHECKPOINT_ID,
        },
        processing_options=2,
    )
    _shopfloor_require_success(status_code, response_body, f"topfloor put item {barcode_id}")


def _topfloor_close_box(
    client: ShopfloorApiClient,
    con_id: int,
    con_date: str,
    con_description: str,
    cts_id: int,
) -> None:
    """Close/save a Topfloor box."""
    status_code, response_body = client.run_procedure(
        TOPFLOOR_BOXING_CHECKPOINT_ID,
        TOPFLOOR_BOXING_TAB_ID,
        5,
        {
            "conId": int(con_id),
            "conDate": str(con_date),
            "conDescription": str(con_description),
            "ctsId": int(cts_id),
        },
        processing_options=2,
    )
    _shopfloor_require_success(status_code, response_body, "topfloor close box")


def _topfloor_scan_unloading_item(client: ShopfloorApiClient, barcode_id: str) -> None:
    """Scan one item through the Topfloor unloading validatescan/processscan flow."""
    con_id = _shopfloor_scan_numeric_id(barcode_id)
    scan_text = _shopfloor_scan_text(barcode_id)
    validate_body = _shopfloor_process_payload(con_id)
    status_code, response_body = client.scan_endpoint(
        TOPFLOOR_UNLOADING_CHECKPOINT_ID,
        TOPFLOOR_UNLOADING_TAB_ID,
        "validatescan",
        scan_text,
        json.loads(validate_body.decode("utf-8")),
    )
    _shopfloor_require_success(status_code, response_body, f"topfloor unloading validatescan {barcode_id}")
    validate_data = _shopfloor_extract_validate_data(response_body)
    process_body = _shopfloor_process_payload(con_id, validate_data)
    status_code, response_body = client.scan_endpoint(
        TOPFLOOR_UNLOADING_CHECKPOINT_ID,
        TOPFLOOR_UNLOADING_TAB_ID,
        "processscan",
        scan_text,
        json.loads(process_body.decode("utf-8")),
    )
    _shopfloor_require_success(status_code, response_body, f"topfloor unloading processscan {barcode_id}")


def _topfloor_try_scan_unloading_item(client: ShopfloorApiClient, barcode_id: str) -> dict[str, object]:
    """Best-effort unloading scan before adding an item to a Topfloor box."""
    try:
        _topfloor_scan_unloading_item(client, barcode_id)
    except Exception as exc:
        return {
            "ok": False,
            "skipped": True,
            "error": str(exc),
        }
    return {
        "ok": True,
        "skipped": False,
        "error": "",
    }


def _topfloor_response_data(response_body: str) -> dict[str, object]:
    """Extract the nested Topfloor procedure data object."""
    try:
        payload = json.loads(response_body or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("A Topfloor válasz nem érvényes JSON.") from exc
    parameters = payload.get("parameters") if isinstance(payload, dict) else None
    data = parameters.get("data") if isinstance(parameters, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("A Topfloor válaszban nincs parameters.data objektum.")
    return data


def _topfloor_box_con_id(box: dict[str, object] | int) -> int:
    """Extract a numeric box CON ID from a box payload."""
    if isinstance(box, dict):
        con_id = int(box.get("conId") or 0)
    else:
        con_id = int(box or 0)
    if con_id <= 0:
        raise ValueError("Hiányzik a Topfloor doboz conId.")
    return con_id


def _topfloor_box_payload(
    box: dict[str, object] | int,
    *,
    con_date: str = "",
    con_description: str = "",
    cts_id: int | None = None,
) -> dict[str, object]:
    """Build the closing payload fields for a Topfloor box."""
    source = box if isinstance(box, dict) else {}
    return {
        "conId": _topfloor_box_con_id(box),
        "conDate": str(con_date or source.get("conDate") or date.today().isoformat()),
        "conDescription": str(con_description or source.get("conDescription") or ""),
        "ctsId": int(cts_id or source.get("ctsId") or TOPFLOOR_BOX_CTS_ID),
    }


def _shopfloor_scan_numeric_id(value: object) -> int:
    """Extract the numeric ID needed by the Shopfloor scan payload."""
    text = str(value or "").strip().upper()
    match = re.search(r"\bCON\D*?(\d{1,12})\b", text) or re.search(r"\b(\d{1,12})\b", text)
    if not match:
        raise ValueError(f"Érvénytelen Shopfloor scan azonosító: {value}")
    return int(match.group(1))


def _shopfloor_scan_text(value: object) -> str:
    """Return the scan text used in the URL path."""
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError("Hiányzik a Shopfloor scan azonosító.")
    if text.startswith("CON"):
        return extract_con_code(text) or text
    return text


def _shopfloor_require_success(status_code: int, response_body: str, action: str) -> None:
    """Raise when a Shopfloor step returns a non-success response."""
    if 200 <= int(status_code) < 300:
        return
    error = str(response_body or "").strip()[:300]
    raise RuntimeError(f"{action} sikertelen ({int(status_code)}): {error}")


def _topfloor_category_shipment_id(category_key: str) -> str:
    """Return the shipment ID encoded in a Topfloor category key."""
    shipment_id = str(category_key or "").split("::", 1)[0].strip()
    if not shipment_id:
        raise ValueError("Hiányzik a Topfloor shipmentID.")
    return shipment_id


def _topfloor_state_path(shipment_id: str) -> Path:
    """Return the Topfloor shipment state path."""
    clean_id = _topfloor_category_shipment_id(shipment_id)
    target_dir = TOPFLOOR_RUNTIME_DIR / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "state.json"


def _load_topfloor_state_payload(shipment_id: str) -> dict:
    """Load the raw Topfloor shipment state payload."""
    path = _topfloor_state_path(shipment_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_topfloor_state_payload(shipment_id: str, payload: dict) -> None:
    """Save the raw Topfloor shipment state payload."""
    path = _topfloor_state_path(shipment_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_topfloor_state_boxes(shipment_id: str) -> dict[str, dict]:
    """Load box assignments from one Topfloor shipment state file."""
    payload = _load_topfloor_state_payload(shipment_id)
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict) and str(key).startswith(f"{shipment_id}::")
    }


def _save_topfloor_state_box(category_key: str, box: dict[str, object]) -> None:
    """Save one Topfloor category box into its shipment state file."""
    shipment_id = _topfloor_category_shipment_id(category_key)
    payload = _load_topfloor_state_payload(shipment_id)
    payload[str(category_key)] = dict(box)
    _save_topfloor_state_payload(shipment_id, payload)


def _load_topfloor_categories() -> dict[str, dict]:
    """Load Topfloor category-to-box assignments."""
    result: dict[str, dict] = {}
    for state_path in sorted(TOPFLOOR_RUNTIME_DIR.glob("*/state.json")):
        shipment_id = state_path.parent.name
        result.update(_load_topfloor_state_boxes(shipment_id))
    return result


def _save_topfloor_category_box(category_key: str, box: dict[str, object], *, open_state: bool) -> None:
    """Save one Topfloor category assignment."""
    clean_key = str(category_key or "").strip()
    if not clean_key:
        raise ValueError("Hiányzik a Topfloor kategória azonosító.")
    box_payload = _topfloor_box_payload(box)
    _save_topfloor_state_box(clean_key, {
        "conId": int(box_payload["conId"]),
        "conDate": str(box_payload["conDate"]),
        "conDescription": str(box_payload["conDescription"]),
        "ctsId": int(box_payload["ctsId"]),
        "open": bool(open_state),
    })


def _topfloor_category_box(category_key: str) -> dict[str, object]:
    """Return the assigned Topfloor box for a category."""
    clean_key = str(category_key or "").strip()
    payload = _load_topfloor_categories()
    box = payload.get(clean_key)
    if not isinstance(box, dict) or not box.get("conId"):
        raise ValueError("Ehhez a Topfloor kategóriához nincs mentett doboz.")
    return box


def _topfloor_require_no_other_open_box(category_key: str) -> None:
    """Prevent opening multiple Topfloor boxes at the same time."""
    clean_key = str(category_key or "").strip()
    for open_key, box in _load_topfloor_categories().items():
        if open_key == clean_key or not bool(box.get("open")):
            continue
        shipment_id = _topfloor_category_shipment_id(open_key)
        con_id = str(box.get("conId", "") or "").strip()
        description = str(box.get("conDescription", "") or "").strip()
        details = f"Szállítmány {shipment_id}, {con_id} ({open_key})" if con_id else f"Szállítmány {shipment_id}, {open_key}"
        if description:
            details = f"{details} - {description}"
        raise RuntimeError(f"Már nyitva van egy Anyagraktár doboz: {details}. Zárd le ezt, mielőtt másikat nyitsz.")


def _shopfloor_ready_endpoint_config(ready_endpoint: str, use_assembly_validate: bool) -> tuple[int, int, bool]:
    """Provide shopfloor ready endpoint config behavior."""
    endpoint_key = str(ready_endpoint or "").strip().lower()
    if use_assembly_validate or endpoint_key == "assembly":
        return SHOPFLOOR_ASSEMBLY_CHECKPOINT_ID, SHOPFLOOR_ASSEMBLY_TAB_ID, True
    if endpoint_key == "front":
        return SHOPFLOOR_FRONT_CHECKPOINT_ID, SHOPFLOOR_FRONT_TAB_ID, True
    if endpoint_key in {"topfloor_boxing", "topfloor-boxing", "boxing"}:
        return TOPFLOOR_BOXING_CHECKPOINT_ID, TOPFLOOR_BOXING_TAB_ID, False
    if endpoint_key in {"topfloor_unloading", "topfloor-unloading", "unloading"}:
        return TOPFLOOR_UNLOADING_CHECKPOINT_ID, TOPFLOOR_UNLOADING_TAB_ID, True
    return SHOPFLOOR_CHECKPOINT_ID, SHOPFLOOR_TAB_ID, False


def _shopfloor_ready_endpoint_credentials(ready_endpoint: str) -> tuple[str, str]:
    """Return the internal Divian credentials for a ready endpoint."""
    endpoint_key = str(ready_endpoint or "").strip().lower()
    if endpoint_key in {
        "topfloor_boxing",
        "topfloor-boxing",
        "boxing",
        "topfloor_unloading",
        "topfloor-unloading",
        "unloading",
    }:
        return TOPFLOOR_USERNAME, TOPFLOOR_PASSWORD
    return SHOPFLOOR_USERNAME, SHOPFLOOR_PASSWORD

