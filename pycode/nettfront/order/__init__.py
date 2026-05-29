from __future__ import annotations

from .config import configure_nettfront_order, default_avg_path, order_runtime_dir
from .jobs import order_download_payload, read_order_job
from .operations import approve_order_job, launch_order_job, process_order_upload, stop_order_job
from .pages import render_nettfront_order_form, render_nettfront_order_result
from .routes import (
    NETTFRONT_ORDER_APPROVE_PREFIX,
    NETTFRONT_ORDER_DOWNLOAD_PREFIX,
    NETTFRONT_ORDER_LAUNCH_PREFIX,
    NETTFRONT_ORDER_PROCESS_ROUTE,
    NETTFRONT_ORDER_ROUTE,
    NETTFRONT_ORDER_STOP_PREFIX,
)

__all__ = [
    "NETTFRONT_ORDER_APPROVE_PREFIX",
    "NETTFRONT_ORDER_DOWNLOAD_PREFIX",
    "NETTFRONT_ORDER_LAUNCH_PREFIX",
    "NETTFRONT_ORDER_PROCESS_ROUTE",
    "NETTFRONT_ORDER_ROUTE",
    "NETTFRONT_ORDER_STOP_PREFIX",
    "approve_order_job",
    "configure_nettfront_order",
    "default_avg_path",
    "launch_order_job",
    "order_download_payload",
    "order_runtime_dir",
    "process_order_upload",
    "read_order_job",
    "render_nettfront_order_form",
    "render_nettfront_order_result",
    "stop_order_job",
]
