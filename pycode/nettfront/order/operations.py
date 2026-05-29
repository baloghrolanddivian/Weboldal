"""Request-level operations for the NettFront order workflow.

The functions in this module validate stock uploads, build order suggestions,
persist approvals, and control the shared NettFront import helper process.
"""

from __future__ import annotations

from .config import default_avg_path
from .engine import build_order_suggestions
from .import_helper import launch_procurement_helper, stop_procurement_helper
from .jobs import (
    _load_nettfront_parts_list_from_bytes,
    _normalize_nettfront_part_number,
    _nettfront_order_display_part_number,
    _nettfront_order_part_number_aliases,
    _order_parse_quantity_input,
    _order_safe_number,
    _persist_nettfront_order_approval,
    _read_nettfront_order_rows,
    _write_nettfront_order_job,
    read_order_job,
)
from .pages import render_nettfront_order_form, render_nettfront_order_result


def process_order_upload(files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes]:
    stock_file = files.get("stock_file")
    parts_file = files.get("parts_file")

    if stock_file is None:
        return 400, render_nettfront_order_form("A rakt?r Excel felt?lt?se k?telez?.")

    stock_name, stock_bytes = stock_file
    if not stock_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        return 400, render_nettfront_order_form("A rakt?rf?jl csak XLSX, XLSM vagy CSV lehet.")

    uploaded_parts_name = ""
    uploaded_parts_bytes: bytes | None = None
    uploaded_parts_count = 0
    if parts_file is not None:
        uploaded_parts_name, uploaded_parts_bytes = parts_file
        if uploaded_parts_name and not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
            return 400, render_nettfront_order_form("A friss alkatr?szlista csak XLSX, XLSM vagy CSV lehet.")
        try:
            uploaded_parts_count = len(_load_nettfront_parts_list_from_bytes(uploaded_parts_bytes or b"", uploaded_parts_name))
        except Exception as exc:
            return 400, render_nettfront_order_form(f"A friss alkatr?szlista feldolgoz?sa nem siker?lt: {exc}")
        if uploaded_parts_count == 0:
            return 400, render_nettfront_order_form("A friss alkatr?szlista ?res, ?gy nem tudom felhaszn?lni a j?v?hagy?sn?l.")

    try:
        result = build_order_suggestions(stock_bytes, default_avg_path=default_avg_path())
        job_id, metadata = _write_nettfront_order_job(
            result,
            stock_name,
            stock_bytes,
            uploaded_parts_name,
            uploaded_parts_bytes,
            uploaded_parts_count,
        )
    except Exception as exc:
        return 400, render_nettfront_order_form(f"Hiba a rendel?si javaslat k?sz?t?se k?zben: {exc}")

    return 200, render_nettfront_order_result(
        job_id,
        metadata,
        message="A rendel?si javaslat elk?sz?lt.",
        success=True,
    )


def approve_order_job(job_id: str, form_data: dict[str, str]) -> tuple[int, bytes] | None:
    job_dir, metadata = read_order_job(job_id)
    if job_dir is None or metadata is None:
        return None

    rows = _read_nettfront_order_rows(job_dir)
    if not rows:
        return 400, render_nettfront_order_result(
            job_id,
            metadata,
            message="Ehhez a fut?shoz nem tal?lok szerkeszthet? rendel?si javaslatot.",
        )

    invalid_rows: list[str] = []
    for row in rows:
        field_name = f"qty__{row.row_id}"
        raw_value = form_data.get(field_name, "")
        parsed_value, ok = _order_parse_quantity_input(raw_value)
        if not ok:
            invalid_rows.append(row.description or row.part_number or row.row_id)
            continue
        row.order_qty = parsed_value

    if invalid_rows:
        invalid_preview = ", ".join(invalid_rows[:3])
        if len(invalid_rows) > 3:
            invalid_preview += f" ?s m?g {len(invalid_rows) - 3} t?tel"
        return 400, render_nettfront_order_result(
            job_id,
            metadata,
            message=f"Hib?s mennyis?get kaptam ezekn?l a t?telekn?l: {invalid_preview}.",
        )

    source_parts_file = str(metadata.get("source_parts_file", "")).strip() or str(metadata.get("source_average_file", "")).strip()
    if source_parts_file:
        parts_path = job_dir / source_parts_file
        if not parts_path.exists():
            return 400, render_nettfront_order_result(
                job_id,
                metadata,
                message="A felt?lt?tt friss alkatr?szlist?t nem tal?lom, ez?rt a j?v?hagy?st most nem tudom ellen?rizni.",
            )

        try:
            allowed_parts = {
                _normalize_nettfront_part_number(item)
                for item in _load_nettfront_parts_list_from_bytes(parts_path.read_bytes(), parts_path.name)
            }
        except Exception as exc:
            return 400, render_nettfront_order_result(
                job_id,
                metadata,
                message=f"A friss alkatr?szlista ellen?rz?se nem siker?lt: {exc}",
            )

        missing_parts: list[str] = []
        seen_missing: set[str] = set()
        for row in rows:
            if _order_safe_number(row.order_qty) <= 0:
                continue
            aliases = _nettfront_order_part_number_aliases(row.part_number)
            if not aliases:
                continue
            if any(alias in allowed_parts for alias in aliases):
                continue
            display_part = _nettfront_order_display_part_number(row.part_number) or row.part_number or row.description or row.row_id
            normalized_display = _normalize_nettfront_part_number(display_part)
            if normalized_display in seen_missing:
                continue
            seen_missing.add(normalized_display)
            missing_parts.append(display_part)

        if missing_parts:
            missing_preview = ", ".join(missing_parts[:4])
            if len(missing_parts) > 4:
                missing_preview += f" ?s m?g {len(missing_parts) - 4} t?tel"
            return 400, render_nettfront_order_result(
                job_id,
                metadata,
                message=(
                    "A j?v?hagy?s most nem ment v?gig, mert ezek a cikksz?mok nem szerepelnek a friss alkatr?szlist?ban: "
                    f"{missing_preview}."
                ),
            )

    try:
        metadata = _persist_nettfront_order_approval(job_dir, metadata, rows)
    except Exception as exc:
        return 500, render_nettfront_order_result(
            job_id,
            metadata,
            message=f"A k?sz rendel?s ment?se nem siker?lt: {exc}",
        )

    return 200, render_nettfront_order_result(
        job_id,
        metadata,
        message="A k?sz rendel?s elk?sz?lt.",
        success=True,
    )


def launch_order_job(job_id: str) -> tuple[int, bytes] | None:
    job_dir, metadata = read_order_job(job_id)
    if job_dir is None or metadata is None:
        return None

    if not str(metadata.get("approved_file", "")).strip():
        return 400, render_nettfront_order_result(
            job_id,
            metadata,
            message="El?bb j?v? kell hagynod a rendel?st, ?s csak ut?na ind?that? a bev?telez?s.",
        )

    try:
        success, messages = launch_procurement_helper(job_dir)
        message = " ".join(messages) if messages else "A bev?telez?si seg?d elindult."
        body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
    except Exception as exc:
        body = render_nettfront_order_result(
            job_id,
            metadata,
            message=f"A bev?telez?si seg?d ind?t?sa nem siker?lt: {exc}",
        )
    return 200, body


def stop_order_job(job_id: str) -> tuple[int, bytes] | None:
    job_dir, metadata = read_order_job(job_id)
    if job_dir is None or metadata is None:
        return None

    try:
        success, messages = stop_procurement_helper(job_dir)
        message = " ".join(messages) if messages else "A bev?telez?si seg?d le?llt."
        body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
    except Exception as exc:
        body = render_nettfront_order_result(
            job_id,
            metadata,
            message=f"A le?ll?t?s nem siker?lt: {exc}",
        )
    return 200, body
