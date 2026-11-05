"""Load a scanned part's bill of materials through one Shopfloor session."""

from __future__ import annotations

import json

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
    """Run procedures 1, 3, 2, keeping procedure 1's context for both follow-ups."""
    client = ShopfloorApiClient.for_endpoint("part_workstation")
    scan_rows = _run(client, 1, {"scan": barcode, "cptId": SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID, "venId": None})
    if not scan_rows or any(field not in scan_rows[0] for field in SCAN_FIELDS):
        raise RuntimeError("A Shopfloor válaszából hiányoznak a beolvasott elem azonosítói.")
    context = {field: scan_rows[0][field] for field in SCAN_FIELDS}
    context.update({"cptId": SHOPFLOOR_PART_WORKSTATION_CHECKPOINT_ID, "venId": None})
    _run(client, 3, dict(context))
    rows = _run(client, 2, dict(context))
    if any(not {"itmItemNumber", "itmDescription", "qty"} <= row.keys() for row in rows):
        raise RuntimeError("A Shopfloor darabjegyzékéből hiányoznak a tételadatok.")
    return [
        {
            "part_number": row["itmItemNumber"],
            "description": row["itmDescription"],
            "quantity": row["qty"],
        }
        for row in rows
    ]


def _run(client: ShopfloorApiClient, procedure_id: int, payload: dict) -> list[dict]:
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
    array = response.get("array")
    rows = array.get("data") if isinstance(array, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError(f"{label}: érvénytelen adatlista.")
    return rows
