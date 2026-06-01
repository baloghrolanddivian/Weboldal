"""Compatibility wrapper for NettFront order import helper controls.

The order workflow uses the same helper process as procurement, so this module
re-exports the shared process-management API from the procurement package.

This module is included in the pydoc surface for the NettFront order suggestion workflow."""

from __future__ import annotations

from nettfront.procurement.import_helper import (
    get_procurement_helper_state,
    launch_procurement_helper,
    stop_procurement_helper,
)

__all__ = [
    "get_procurement_helper_state",
    "launch_procurement_helper",
    "stop_procurement_helper",
]
