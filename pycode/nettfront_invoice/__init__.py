"""Public API for the NettFront invoice receiving module."""

from __future__ import annotations

NETTFRONT_INVOICE_ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo", "hriroda"})
NETTFRONT_INVOICE_CHECK_ACCESS_USER_IDS = NETTFRONT_INVOICE_ACCESS_USER_IDS
NETTFRONT_INVOICE_ADMIN_ACCESS_USER_IDS = frozenset()

from .engine import build_invoice_from_batch, build_invoice_workbook, parse_batch_xml
from .camera import CameraBusyError, CameraReadError, trigger_camera_read
from .pages import invoice_item_display, render_admin, render_check, render_home, render_invoice, render_reader
from .routes import *
from .store import (
    DuplicateInvoiceError,
    attach_batch_xml,
    close_invoice,
    configure_nettfront_invoice,
    create_invoice,
    list_invoices,
    load_invoice,
    normalize_invoice_code,
    record_open,
    record_scan_failure,
    reopen_invoice,
    scan_invoice_icn,
)

__all__ = [name for name in globals() if name.startswith("NETTFRONT_")] + [
    "CameraBusyError", "CameraReadError", "DuplicateInvoiceError", "build_invoice_from_batch", "build_invoice_workbook", "close_invoice", "configure_nettfront_invoice",
    "attach_batch_xml", "create_invoice", "list_invoices", "load_invoice", "normalize_invoice_code", "parse_batch_xml",
    "invoice_item_display", "record_open", "record_scan_failure", "render_admin", "render_check", "render_home", "render_invoice", "render_reader", "reopen_invoice", "scan_invoice_icn", "trigger_camera_read",
]
