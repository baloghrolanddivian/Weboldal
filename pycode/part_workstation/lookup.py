"""Load a scanned part's identity and BOM through one Shopfloor session."""

from __future__ import annotations

import json
import re

from tools.shopfloor import (
    SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID,
    SHOPFLOOR_PART_WORKSTATION_TAB_ID,
    ShopfloorApiClient,
    shopfloor_response_error,
)


SCAN_FIELDS = (
    "message", "messageType", "instruction", "scan_Num", "scan", "conId",
    "olnId", "olnIdInstance",
)


def lookup_bom(barcode: str) -> list[dict]:
    """Load just the BOM rows for callers that do not need the scan context."""
    return lookup_scan(barcode)["bom"]


def lookup_scan(barcode: str) -> dict:
    """Run procedures 1, 3, 2, keeping procedure 1's context for both follow-ups."""
    client = ShopfloorApiClient.for_endpoint("part_workstation")
    scan_rows = _run(client, 1, {"scan": barcode, "cptId": SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID, "venId": None})
    if not scan_rows or any(field not in scan_rows[0] for field in SCAN_FIELDS):
        raise RuntimeError("A Shopfloor válaszából hiányoznak a beolvasott elem azonosítói.")
    # Preserve new output parameters too: API 3 needs API 1's prdId input.
    context = dict(scan_rows[0])
    context.update({"cptId": SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID, "venId": None})
    production_response = _run_response(client, 3, dict(context))
    production_number = _production_number(production_response)
    rows = _run(client, 2, dict(context))
    if any(not {"itmItemNumber", "itmDescription", "qty"} <= row.keys() for row in rows):
        raise RuntimeError("A Shopfloor darabjegyzékéből hiányoznak a tételadatok.")
    bom = [
        {
            "part_number": row["itmItemNumber"],
            "description": row["itmDescription"],
            "quantity": row["qty"],
        }
        for row in rows
    ]
    return {"bom": bom, "scan": context, "production_number": production_number}


def _run(client: ShopfloorApiClient, procedure_id: int, payload: dict) -> list[dict]:
    response = _run_response(client, procedure_id, payload)
    array = response.get("array")
    rows = array.get("data") if isinstance(array, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError(f"Shopfloor darabjegyzék ({procedure_id}. eljárás): érvénytelen adatlista.")
    return rows


def _production_number(response: dict) -> str:
    """Read API 3's output parameters, accepting the earlier array-row form too."""
    parameters = response.get("parameters")
    candidates = [parameters.get("data") if isinstance(parameters, dict) else None, response.get("data")]
    array = response.get("array")
    rows = array.get("data") if isinstance(array, dict) else None
    if isinstance(rows, list) and len(rows) == 1:
        candidates.append(rows[0])
    message = "A Shopfloor 3. eljárásának válaszában hiányzik vagy érvénytelen a prdId gyártási azonosító."
    for data in candidates:
        if not isinstance(data, dict):
            continue
        for key in ("prdId", "prdID"):
            if key not in data:
                continue
            number = str(data[key] or "").strip()
            if re.fullmatch(r"[0-9]+", number) and int(number) > 0:
                return number
            raise RuntimeError(message)
    raise RuntimeError(message)


def _run_response(client: ShopfloorApiClient, procedure_id: int, payload: dict) -> dict:
    status, body = client.run_procedure(
        SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID,
        SHOPFLOOR_PART_WORKSTATION_TAB_ID,
        procedure_id,
        payload,
    )
    label = f"Shopfloor darabjegyzék ({procedure_id}. eljárás)"
    error = shopfloor_response_error(body)
    if not 200 <= status < 300 or error:
        raise RuntimeError(f"{label}: {error or f'HTTP {status}'}")
    try:
        response = json.loads(body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label}: érvénytelen JSON válasz.") from exc
    if not isinstance(response, dict) or response.get("returnValue") != 0:
        raise RuntimeError(f"{label}: sikertelen eljárás.")
    return response
