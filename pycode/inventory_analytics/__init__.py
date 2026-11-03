"""Admin inventory intelligence module."""

from .engine import configure_inventory_analytics, dashboard, import_erp_exports, import_workbook, set_discontinued
from .page import render_inventory_analytics
from .routes import (
    INVENTORY_ANALYTICS_DISCONTINUED_ROUTE,
    INVENTORY_ANALYTICS_DOORS_DISCONTINUED_ROUTE,
    INVENTORY_ANALYTICS_DOORS_ROUTE,
    INVENTORY_ANALYTICS_DOORS_UPLOAD_ROUTE,
    INVENTORY_ANALYTICS_ROUTE,
    INVENTORY_ANALYTICS_TEMPLATE_ROUTE,
    INVENTORY_ANALYTICS_UPLOAD_ROUTE,
)

__all__ = [
    "INVENTORY_ANALYTICS_ROUTE",
    "INVENTORY_ANALYTICS_TEMPLATE_ROUTE",
    "INVENTORY_ANALYTICS_UPLOAD_ROUTE",
    "INVENTORY_ANALYTICS_DISCONTINUED_ROUTE",
    "INVENTORY_ANALYTICS_DOORS_ROUTE",
    "INVENTORY_ANALYTICS_DOORS_UPLOAD_ROUTE",
    "INVENTORY_ANALYTICS_DOORS_DISCONTINUED_ROUTE",
    "configure_inventory_analytics",
    "dashboard",
    "import_erp_exports",
    "import_workbook",
    "render_inventory_analytics",
    "set_discontinued",
]
