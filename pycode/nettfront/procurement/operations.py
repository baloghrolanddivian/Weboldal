"""Request-level operations for the NettFront procurement workflow.

This module validates uploads, invokes procurement package generation, rebuilds
parts mappings, and controls the procurement import helper process.
"""

from __future__ import annotations

from nettfront.engine import (
    build_procurement_artifacts,
    load_alkatresz_map,
    load_alkatresz_map_from_bytes,
)

from .config import procurement_runtime_dir
from .import_helper import launch_procurement_helper, stop_procurement_helper
from .jobs import persist_procurement_job, read_procurement_job, write_procurement_job
from .pages import render_nettfront_procurement_form, render_nettfront_procurement_result


def process_procurement_upload(files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes]:
    invoice_file = files.get("invoice_pdf")
    parts_file = files.get("parts_file")

    if invoice_file is None:
        return 400, render_nettfront_procurement_form("A NettFront sz?mla PDF felt?lt?se k?telez?.")

    invoice_name, invoice_bytes = invoice_file
    if not invoice_name.lower().endswith(".pdf"):
        return 400, render_nettfront_procurement_form("Csak PDF sz?mla t?lthet? fel.")

    uploaded_parts_name = ""
    uploaded_parts_bytes: bytes | None = None
    merged_map = None
    if parts_file is not None:
        uploaded_parts_name, uploaded_parts_bytes = parts_file
        if not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
            return 400, render_nettfront_procurement_form("Az alkatr?szlista csak XLSX, XLSM vagy CSV f?jl lehet.")
        try:
            merged_map = load_alkatresz_map()
            merged_map.update(load_alkatresz_map_from_bytes(uploaded_parts_bytes, uploaded_parts_name))
        except Exception as exc:
            return 400, render_nettfront_procurement_form(f"Az alkatr?szlista feldolgoz?sa nem siker?lt: {exc}")

    try:
        artifacts = build_procurement_artifacts(invoice_bytes, alkatresz_map=merged_map)
        job_id, metadata = write_procurement_job(
            artifacts,
            invoice_name,
            invoice_bytes,
            uploaded_parts_name=uploaded_parts_name,
            uploaded_parts_bytes=uploaded_parts_bytes,
        )
    except Exception as exc:
        return 400, render_nettfront_procurement_form(f"Hiba a feldolgoz?s sor?n: {exc}")

    message = ""
    success = False
    if not metadata.get("missing_codes"):
        job_dir = procurement_runtime_dir() / job_id
        try:
            success, messages = launch_procurement_helper(job_dir)
            message = " ".join(messages)
        except Exception as exc:
            message = f"Az import-seg?d automatikus ind?t?sa nem siker?lt: {exc}"
            success = False

    return 200, render_nettfront_procurement_result(job_id, metadata, message=message, success=success)


def rebuild_procurement_parts(job_id: str, files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes] | None:
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    parts_file = files.get("parts_file")
    if parts_file is None:
        return 400, render_nettfront_procurement_result(job_id, metadata, message="Az alkatr?szlista felt?lt?se k?telez?.")

    parts_name, parts_bytes = parts_file
    if not parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        return 400, render_nettfront_procurement_result(job_id, metadata, message="Az alkatr?szlista csak XLSX, XLSM vagy CSV f?jl lehet.")

    source_invoice_file = str(metadata.get("source_invoice_file", "source-invoice.pdf")).strip() or "source-invoice.pdf"
    source_invoice_path = job_dir / source_invoice_file
    if not source_invoice_path.exists():
        return 400, render_nettfront_procurement_result(
            job_id,
            metadata,
            message="Ehhez a kor?bbi fut?shoz nem tal?lom a forr?ssz?ml?t. T?ltsd fel ?jra a sz?ml?t.",
        )

    try:
        merged_map = load_alkatresz_map()
        merged_map.update(load_alkatresz_map_from_bytes(parts_bytes, parts_name))
        artifacts = build_procurement_artifacts(source_invoice_path.read_bytes(), alkatresz_map=merged_map)
        metadata = persist_procurement_job(job_dir, metadata, artifacts, uploaded_parts_name=parts_name, uploaded_parts_bytes=parts_bytes)
    except Exception as exc:
        return 400, render_nettfront_procurement_result(job_id, metadata, message=f"Az alkatr?szlista feldolgoz?sa nem siker?lt: {exc}")

    if metadata.get("missing_codes"):
        message = f"Az alkatr?szlista beker?lt. M?g {len(metadata.get('missing_codes', []))} hi?nyz? k?d maradt."
        success = False
    else:
        try:
            success, messages = launch_procurement_helper(job_dir)
            message = "Az alkatr?szlista beker?lt. " + " ".join(messages)
        except Exception as exc:
            message = f"Az alkatr?szlista beker?lt, de az import-seg?d automatikus ind?t?sa nem siker?lt: {exc}"
            success = False

    return 200, render_nettfront_procurement_result(job_id, metadata, message=message, success=success)


def launch_procurement_job(job_id: str) -> tuple[int, bytes] | None:
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    if metadata.get("missing_codes"):
        body = render_nettfront_procurement_result(
            job_id,
            metadata,
            message="Hi?nyz? k?dok vannak. El?bb t?lts fel alkatr?szlist?t a Beszerz?s ?jra?p?t?s?hez.",
        )
        return 400, body

    try:
        success, messages = launch_procurement_helper(job_dir)
        body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
        return 200, body
    except Exception as exc:
        body = render_nettfront_procurement_result(job_id, metadata, message=f"A launch nem siker?lt: {exc}")
        return 500, body


def stop_procurement_job(job_id: str) -> tuple[int, bytes] | None:
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    try:
        success, messages = stop_procurement_helper(job_dir)
        body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
        return (200 if success else 400), body
    except Exception as exc:
        body = render_nettfront_procurement_result(job_id, metadata, message=f"A le?ll?t?s nem siker?lt: {exc}")
        return 500, body
