"""Verify assembly damage reports against the current Shopfloor BOM."""

from manufacturing.assembly_damage import bom_snapshot, record_bom_damage

from .lookup import lookup_scan


def report_bom_damage(payload: dict, *, reported_by: str) -> dict:
    barcode = str(payload.get("barcode") or "").strip()
    index = payload.get("bom_index")
    if not barcode or len(barcode) > 160 or type(index) is not int or index < 0:
        raise ValueError("Érvénytelen beolvasott tétel.")
    expected = bom_snapshot(payload.get("bom_row"))
    result = lookup_scan(barcode)
    if str(payload.get("production_number")) != result["production_number"]:
        raise ValueError("A gyártás időközben megváltozott. Olvasd be újra az elemet.")
    if index >= len(result["bom"]) or bom_snapshot(result["bom"][index]) != expected:
        raise ValueError("A darabjegyzék időközben megváltozott. Olvasd be újra az elemet.")
    return record_bom_damage(result["production_number"], result["scan"].get("scan") or barcode, index, result["bom"][index],
                             request_id=payload.get("request_id"), reported_by=reported_by)
