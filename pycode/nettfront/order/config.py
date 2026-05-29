from __future__ import annotations

from pathlib import Path
from typing import Callable

_runtime_dir: Path | None = None
_default_avg_path: Path | None = None
_layout_renderer: Callable[..., bytes] | None = None


def configure_nettfront_order(runtime_dir: Path, default_avg_path: Path, layout_renderer: Callable[..., bytes]) -> None:
    global _runtime_dir, _default_avg_path, _layout_renderer
    _runtime_dir = runtime_dir
    _default_avg_path = default_avg_path
    _layout_renderer = layout_renderer


def order_runtime_dir() -> Path:
    if _runtime_dir is None:
        raise RuntimeError("NettFront order runtime directory is not configured")
    return _runtime_dir


def default_avg_path() -> Path:
    if _default_avg_path is None:
        raise RuntimeError("NettFront order average path is not configured")
    return _default_avg_path


def render_layout(**kwargs) -> bytes:
    if _layout_renderer is None:
        raise RuntimeError("NettFront order layout renderer is not configured")
    return _layout_renderer(**kwargs)
