from __future__ import annotations

from nettfront.engine import build_compare_artifacts

from .jobs import write_compare_job
from .pages import render_nettfront_compare_form, render_nettfront_compare_result


def process_compare_upload(files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes]:
    invoice_file = files.get("invoice_pdf")
    order_file = files.get("order_file")

    if invoice_file is None or order_file is None:
        return 400, render_nettfront_compare_form("A sz?mla PDF ?s a megl?v? rendel?si f?jl felt?lt?se is k?telez?.")

    invoice_name, invoice_bytes = invoice_file
    if not invoice_name.lower().endswith(".pdf"):
        return 400, render_nettfront_compare_form("Csak PDF sz?mla t?lthet? fel.")

    order_name, order_bytes = order_file
    allowed_order_extensions = (".xlsx", ".xlsm", ".csv")
    if not order_name.lower().endswith(allowed_order_extensions):
        return 400, render_nettfront_compare_form("A megl?v? rendel?s csak XLSX, XLSM vagy CSV f?jl lehet.")

    try:
        artifacts = build_compare_artifacts(invoice_bytes, order_bytes)
        job_id, metadata = write_compare_job(artifacts)
    except Exception as exc:
        return 400, render_nettfront_compare_form(f"Hiba az ?sszehasonl?t?s sor?n: {exc}")

    return 200, render_nettfront_compare_result(job_id, metadata)
