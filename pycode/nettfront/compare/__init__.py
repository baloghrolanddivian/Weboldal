"""Public API for the NettFront invoice comparison workflow."""

from __future__ import annotations

from .config import compare_runtime_dir, configure_nettfront_compare
from .jobs import compare_download_payload, read_compare_job, write_compare_job
from .operations import process_compare_upload
from .pages import render_nettfront_compare_form, render_nettfront_compare_result
from .routes import NETTFRONT_COMPARE_DOWNLOAD_PREFIX, NETTFRONT_COMPARE_PROCESS_ROUTE, NETTFRONT_COMPARE_ROUTE

__all__ = [
    "NETTFRONT_COMPARE_DOWNLOAD_PREFIX",
    "NETTFRONT_COMPARE_PROCESS_ROUTE",
    "NETTFRONT_COMPARE_ROUTE",
    "compare_download_payload",
    "compare_runtime_dir",
    "configure_nettfront_compare",
    "process_compare_upload",
    "read_compare_job",
    "render_nettfront_compare_form",
    "render_nettfront_compare_result",
    "write_compare_job",
]
