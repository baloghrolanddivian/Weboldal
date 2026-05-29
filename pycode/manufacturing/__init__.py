"""Public API for the manufacturing papers workflow."""

from __future__ import annotations

from .common import (
    _pdf_lines,
    available_production_entries,
    available_production_numbers,
    latest_production_number,
    load_partial_quantity_state,
    load_production_bundle,
    load_selection_state,
    production_folder,
    save_partial_quantity_state,
    save_selection_state,
)
from .config import configure_manufacturing, runtime_dir
from .routes import (
    MANUFACTURING_PARTIAL_QTY_ROUTE,
    MANUFACTURING_REPORT_READY_ROUTE,
    MANUFACTURING_ROUTE,
    MANUFACTURING_STATE_ROUTE,
)
from .workflow import (
    MANUFACTURING_OPERATION_DEFINITIONS,
    MANUFACTURING_PRIME_SYNC_ON_START,
    _load_manufacturing_bundle_cached,
    _manufacturing_is_virtual_unit_row_id,
    _manufacturing_normalize_number,
    _manufacturing_normalize_operation,
    _manufacturing_operation_state_keys,
    _manufacturing_query_params,
    _manufacturing_ready_endpoint_key,
    _manufacturing_selection_state_payload,
    _manufacturing_view_bundle,
    _prime_manufacturing_cache_async,
    _prime_manufacturing_cache_worker,
    render_manufacturing_module,
)

__all__ = [
    "MANUFACTURING_OPERATION_DEFINITIONS",
    "MANUFACTURING_PARTIAL_QTY_ROUTE",
    "MANUFACTURING_PRIME_SYNC_ON_START",
    "MANUFACTURING_REPORT_READY_ROUTE",
    "MANUFACTURING_ROUTE",
    "MANUFACTURING_STATE_ROUTE",
    "_load_manufacturing_bundle_cached",
    "_manufacturing_is_virtual_unit_row_id",
    "_manufacturing_normalize_number",
    "_manufacturing_normalize_operation",
    "_manufacturing_operation_state_keys",
    "_manufacturing_query_params",
    "_manufacturing_ready_endpoint_key",
    "_manufacturing_selection_state_payload",
    "_manufacturing_view_bundle",
    "_pdf_lines",
    "_prime_manufacturing_cache_async",
    "_prime_manufacturing_cache_worker",
    "available_production_entries",
    "available_production_numbers",
    "configure_manufacturing",
    "latest_production_number",
    "load_partial_quantity_state",
    "load_production_bundle",
    "load_selection_state",
    "production_folder",
    "render_manufacturing_module",
    "runtime_dir",
    "save_partial_quantity_state",
    "save_selection_state",
]
