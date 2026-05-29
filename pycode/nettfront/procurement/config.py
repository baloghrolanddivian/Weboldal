"""Runtime configuration for the NettFront procurement workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

_runtime_dir: Path | None = None
_layout_renderer: Callable[..., bytes] | None = None


def configure_nettfront_procurement(runtime_dir: Path, layout_renderer: Callable[..., bytes]) -> None:
    global _runtime_dir, _layout_renderer
    _runtime_dir = runtime_dir
    _layout_renderer = layout_renderer


def procurement_runtime_dir() -> Path:
    if _runtime_dir is None:
        raise RuntimeError("NettFront procurement runtime directory is not configured")
    return _runtime_dir


def render_layout(**kwargs) -> bytes:
    if _layout_renderer is None:
        raise RuntimeError("NettFront procurement layout renderer is not configured")
    return _layout_renderer(**kwargs)
