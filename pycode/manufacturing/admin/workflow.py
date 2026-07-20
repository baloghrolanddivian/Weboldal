"""Admin-view adapter for the shared manufacturing workflow.

The manufacturing package owns parsing, caching, state hydration, and bundle
assembly.  This module supplies only the admin view's intentionally different
CNC row builder and page renderer.
"""

from __future__ import annotations

# Admin policy adapter for the unified Manufacturing package.

from manufacturing.base import workflow as _base_workflow
from manufacturing.base.workflow import *  # noqa: F401,F403 - compatibility API

from .page import render_manufacturing_page as _admin_page_renderer
from .routes import MANUFACTURING_ROUTE


def _admin_cnc_sections_builder(bundle: dict, production_number: str):
    """Load the admin CNC builder lazily to avoid its workflow import cycle."""
    from .cnc.sections import _manufacturing_cnc_sections

    return _manufacturing_cnc_sections(bundle, production_number)


def _manufacturing_view_bundle(
    raw_bundle: dict,
    production_number: str,
    current_selection_state: dict[str, str],
    *,
    include_all_red_view: bool = True,
    operation_filter: str = "",
    cnc_sections_builder=None,
):
    """Build a bundle using the admin view's non-merging CNC presentation."""
    return _base_workflow._manufacturing_view_bundle(
        raw_bundle,
        production_number,
        current_selection_state,
        include_all_red_view=include_all_red_view,
        operation_filter=operation_filter,
        cnc_sections_builder=cnc_sections_builder or _admin_cnc_sections_builder,
    )


def manufacturing_module_payload(
    production_number: str = "",
    operation: str = "",
    message: str = "",
    success: bool = False,
    include_client_cache: bool = True,
    route: str = MANUFACTURING_ROUTE,
):
    """Build the shared payload under the admin view policy."""
    return _base_workflow.manufacturing_module_payload(
        production_number=production_number,
        operation=operation,
        message=message,
        success=success,
        include_client_cache=include_client_cache,
        route=route,
        view_mode="admin",
        cnc_sections_builder=_admin_cnc_sections_builder,
    )


def manufacturing_client_payload(module_payload: dict[str, object]):
    """Expose the shared client payload projection."""
    return _base_workflow.manufacturing_client_payload(module_payload)


def render_manufacturing_module(
    production_number: str = "",
    operation: str = "",
    message: str = "",
    success: bool = False,
    route: str = MANUFACTURING_ROUTE,
):
    """Render the shared workflow with the admin-specific page."""
    return _base_workflow.render_manufacturing_module(
        production_number=production_number,
        operation=operation,
        message=message,
        success=success,
        route=route,
        view_mode="admin",
        cnc_sections_builder=_admin_cnc_sections_builder,
        page_renderer=_admin_page_renderer,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
