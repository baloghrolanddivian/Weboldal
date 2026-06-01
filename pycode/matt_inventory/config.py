"""Runtime configuration for the Matt inventory value workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

_runtime_dir = Path("runtime") / "matt-raktarertek"
_layout_renderer: Callable[..., bytes] | None = None


def configure_matt_inventory(runtime_dir: Path, layout_renderer: Callable[..., bytes]) -> None:
    """Configure configure matt inventory runtime settings."""
    global _runtime_dir, _layout_renderer
    _runtime_dir = runtime_dir
    _layout_renderer = layout_renderer


def runtime_dir() -> Path:
    """Provide runtime dir behavior."""
    return _runtime_dir


def report_path() -> Path:
    """Provide report path behavior."""
    return _runtime_dir / "latest-report.json"


def price_meta_path() -> Path:
    """Provide price meta path behavior."""
    return _runtime_dir / "latest-price.json"


def stock_meta_path() -> Path:
    """Provide stock meta path behavior."""
    return _runtime_dir / "latest-stock.json"


def alert_workbook_path() -> Path:
    """Provide alert workbook path behavior."""
    return _runtime_dir / "matt-keszlet-riport.xlsx"


def render_layout(**kwargs: object) -> bytes:
    """Render render layout output."""
    if _layout_renderer is None:
        raise RuntimeError("Matt inventory layout renderer is not configured.")
    return _layout_renderer(**kwargs)
