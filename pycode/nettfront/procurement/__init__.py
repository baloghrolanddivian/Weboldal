"""Public API for the NettFront procurement workflow.

This module is included in the pydoc surface for the NettFront procurement workflow."""

from __future__ import annotations

NETTFRONT_PROCUREMENT_ACCESS_USER_IDS = frozenset()

from .config import configure_nettfront_procurement, procurement_runtime_dir
from .jobs import (
    persist_procurement_job,
    procurement_download_payload,
    read_procurement_job,
    write_procurement_job,
)
from .operations import (
    launch_procurement_job,
    process_procurement_upload,
    rebuild_procurement_parts,
    stop_procurement_job,
)
from .pages import render_nettfront_procurement_form, render_nettfront_procurement_result
from .routes import (
    NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX,
    NETTFRONT_PROCUREMENT_LAUNCH_PREFIX,
    NETTFRONT_PROCUREMENT_PARTS_PREFIX,
    NETTFRONT_PROCUREMENT_PROCESS_ROUTE,
    NETTFRONT_PROCUREMENT_ROUTE,
    NETTFRONT_PROCUREMENT_STOP_PREFIX,
)

__all__ = [
    "NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX",
    "NETTFRONT_PROCUREMENT_LAUNCH_PREFIX",
    "NETTFRONT_PROCUREMENT_PARTS_PREFIX",
    "NETTFRONT_PROCUREMENT_PROCESS_ROUTE",
    "NETTFRONT_PROCUREMENT_ROUTE",
    "NETTFRONT_PROCUREMENT_STOP_PREFIX",
    "NETTFRONT_PROCUREMENT_ACCESS_USER_IDS",
    "configure_nettfront_procurement",
    "launch_procurement_job",
    "persist_procurement_job",
    "procurement_download_payload",
    "procurement_runtime_dir",
    "process_procurement_upload",
    "read_procurement_job",
    "rebuild_procurement_parts",
    "render_nettfront_procurement_form",
    "render_nettfront_procurement_result",
    "stop_procurement_job",
    "write_procurement_job",
]
