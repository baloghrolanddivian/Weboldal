"""Request-level operations for the NettFront procurement workflow.

This module validates uploads, invokes procurement package generation, rebuilds
parts mappings, and controls the procurement import helper process.

This module is included in the pydoc surface for the NettFront procurement workflow."""

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
    """Validate procurement uploads and build the procurement result page.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    invoice_file = files.get("invoice_pdf")
    parts_file = files.get("parts_file")

    if invoice_file is None:
        return 400, render_nettfront_procurement_form("A NettFront számla PDF feltöltése kötelező.")

    invoice_name, invoice_bytes = invoice_file
    if not invoice_name.lower().endswith(".pdf"):
        return 400, render_nettfront_procurement_form("Csak PDF számla tölthető fel.")

    uploaded_parts_name = ""
    uploaded_parts_bytes: bytes | None = None
    merged_map = None
    if parts_file is not None:
        uploaded_parts_name, uploaded_parts_bytes = parts_file
        if not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
            return 400, render_nettfront_procurement_form("Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")
        try:
            merged_map = load_alkatresz_map()
            merged_map.update(load_alkatresz_map_from_bytes(uploaded_parts_bytes, uploaded_parts_name))
        except Exception as exc:
            return 400, render_nettfront_procurement_form(f"Az alkatrészlista feldolgozása nem sikerült: {exc}")

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
        return 400, render_nettfront_procurement_form(f"Hiba a feldolgozás során: {exc}")

    message = ""
    success = False
    if not metadata.get("missing_codes"):
        job_dir = procurement_runtime_dir() / job_id
        try:
            success, messages = launch_procurement_helper(job_dir)
            message = " ".join(messages)
        except Exception as exc:
            message = f"Az import-segéd automatikus indítása nem sikerült: {exc}"
            success = False

    return 200, render_nettfront_procurement_result(job_id, metadata, message=message, success=success)


def rebuild_procurement_parts(job_id: str, files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes] | None:
    """Handle rebuild procurement parts logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    parts_file = files.get("parts_file")
    if parts_file is None:
        return 400, render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista feltöltése kötelező.")

    parts_name, parts_bytes = parts_file
    if not parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        return 400, render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")

    source_invoice_file = str(metadata.get("source_invoice_file", "source-invoice.pdf")).strip() or "source-invoice.pdf"
    source_invoice_path = job_dir / source_invoice_file
    if not source_invoice_path.exists():
        return 400, render_nettfront_procurement_result(
            job_id,
            metadata,
            message="Ehhez a korábbi futáshoz nem találom a forrásszámlát. Töltsd fel újra a számlát.",
        )

    try:
        merged_map = load_alkatresz_map()
        merged_map.update(load_alkatresz_map_from_bytes(parts_bytes, parts_name))
        artifacts = build_procurement_artifacts(source_invoice_path.read_bytes(), alkatresz_map=merged_map)
        metadata = persist_procurement_job(job_dir, metadata, artifacts, uploaded_parts_name=parts_name, uploaded_parts_bytes=parts_bytes)
    except Exception as exc:
        return 400, render_nettfront_procurement_result(job_id, metadata, message=f"Az alkatrészlista feldolgozása nem sikerült: {exc}")

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

    return 200, render_nettfront_procurement_result(job_id, metadata, message=message, success=success)


def launch_procurement_job(job_id: str) -> tuple[int, bytes] | None:
    """Launch procurement job processing.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    if metadata.get("missing_codes"):
        body = render_nettfront_procurement_result(
            job_id,
            metadata,
            message="Hiányzó kódok vannak. Előbb tölts fel alkatrészlistát a Beszerzés újraépítéséhez.",
        )
        return 400, body

    try:
        success, messages = launch_procurement_helper(job_dir)
        body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
        return 200, body
    except Exception as exc:
        body = render_nettfront_procurement_result(job_id, metadata, message=f"A launch nem sikerült: {exc}")
        return 500, body


def stop_procurement_job(job_id: str) -> tuple[int, bytes] | None:
    """Stop procurement job processing.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    job_dir, metadata = read_procurement_job(job_id)
    if job_dir is None or metadata is None:
        return None

    try:
        success, messages = stop_procurement_helper(job_dir)
        body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
        return (200 if success else 400), body
    except Exception as exc:
        body = render_nettfront_procurement_result(job_id, metadata, message=f"A leállítás nem sikerült: {exc}")
        return 500, body
