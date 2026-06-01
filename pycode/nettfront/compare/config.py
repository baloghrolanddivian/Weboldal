"""Runtime configuration for the NettFront comparison workflow.

The application injects runtime paths and renderer callbacks here during
startup so the workflow modules stay decoupled from the main server module.

This module is included in the pydoc surface for the NettFront comparison workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

_runtime_dir: Path | None = None
_layout_renderer: Callable[..., bytes] | None = None
_file_bind_renderer: Callable[[list[tuple[str, str, str]]], str] | None = None


def configure_nettfront_compare(
    runtime_dir: Path,
    layout_renderer: Callable[..., bytes],
    file_bind_renderer: Callable[[list[tuple[str, str, str]]], str],
) -> None:
    """Configure runtime paths and render callbacks for the comparison workflow.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    global _runtime_dir, _layout_renderer, _file_bind_renderer
    _runtime_dir = runtime_dir
    _layout_renderer = layout_renderer
    _file_bind_renderer = file_bind_renderer


def compare_runtime_dir() -> Path:
    """Handle compare runtime dir logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    if _runtime_dir is None:
        raise RuntimeError("NettFront compare runtime directory is not configured")
    return _runtime_dir


def render_layout(**kwargs) -> bytes:
    """Render the layout view.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    if _layout_renderer is None:
        raise RuntimeError("NettFront compare layout renderer is not configured")
    return _layout_renderer(**kwargs)


def render_file_bind_script(bindings: list[tuple[str, str, str]]) -> str:
    """Render the file bind script view.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    if _file_bind_renderer is None:
        raise RuntimeError("NettFront compare file bind renderer is not configured")
    return _file_bind_renderer(bindings)
