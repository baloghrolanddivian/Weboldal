"""Landscape tablet workstation for scanned production parts."""

from .page import ACCESS_USER_IDS, ADMIN_ACCESS_USER_IDS, ADMIN_DATA_ROUTE, ADMIN_ROUTE, ADMIN_SAVE_ROUTE, DAMAGE_ROUTE, ROUTE, SCAN_ROUTE, render_page
from .damage import report_bom_damage
from .admin_page import render_admin_page
from .admin_store import ProductionConflict, load_production_notes, save_production_notes
from .store import empty_state, register_scan

__all__ = [
    "ACCESS_USER_IDS",
    "DAMAGE_ROUTE",
    "report_bom_damage",
    "ADMIN_ACCESS_USER_IDS",
    "ADMIN_DATA_ROUTE",
    "ADMIN_ROUTE",
    "ADMIN_SAVE_ROUTE",
    "ProductionConflict",
    "load_production_notes",
    "save_production_notes",
    "render_admin_page",
    "ROUTE",
    "SCAN_ROUTE",
    "empty_state",
    "register_scan",
    "render_page",
]
