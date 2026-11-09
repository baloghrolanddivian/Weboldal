"""Landscape tablet workstation for scanned production parts."""

from .page import ACCESS_USER_IDS, ROUTE, SCAN_ROUTE, render_page
from .store import empty_state, register_scan

__all__ = [
    "ACCESS_USER_IDS",
    "ROUTE",
    "SCAN_ROUTE",
    "empty_state",
    "register_scan",
    "render_page",
]
