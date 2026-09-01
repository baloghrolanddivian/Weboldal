"""Request-level operations for the NettFront comparison workflow.

The functions here validate uploaded files, invoke the comparison engine, and
return HTTP-style status/body pairs for the route dispatcher.

This module is included in the pydoc surface for the NettFront comparison workflow."""

from __future__ import annotations

from nettfront.engine import build_compare_artifacts

from .jobs import write_compare_job
from .pages import render_nettfront_compare_form, render_nettfront_compare_result


def process_compare_upload(files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes]:
    """Validate comparison uploads and build the comparison result page.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    invoice_file = files.get("invoice_pdf")
    order_file = files.get("order_file")

    if invoice_file is None or order_file is None:
        return 400, render_nettfront_compare_form("A számla PDF és a meglévő rendelési fájl feltöltése is kötelező.")

    invoice_name, invoice_bytes = invoice_file
    if not invoice_name.lower().endswith(".pdf"):
        return 400, render_nettfront_compare_form("Csak PDF számla tölthető fel.")

    order_name, order_bytes = order_file
    allowed_order_extensions = (".xls", ".xlsx", ".xlsm", ".csv")
    if not order_name.lower().endswith(allowed_order_extensions):
        return 400, render_nettfront_compare_form("A meglévő rendelés csak XLS, XLSX, XLSM vagy CSV fájl lehet.")

    try:
        artifacts = build_compare_artifacts(invoice_bytes, order_bytes)
        job_id, metadata = write_compare_job(artifacts)
    except Exception as exc:
        return 400, render_nettfront_compare_form(f"Hiba az összehasonlítás során: {exc}")

    return 200, render_nettfront_compare_result(job_id, metadata)
