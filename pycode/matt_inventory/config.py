"""Runtime configuration for the Matt inventory value workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]

_runtime_dir = REPO_ROOT / "runtime" / "matt-raktarertek"
_layout_renderer: Callable[..., bytes] | None = None


def configure_matt_inventory(runtime_dir: Path, layout_renderer: Callable[..., bytes]) -> None:
    """Set Matt inventory runtime storage and the shared layout renderer."""
    global _runtime_dir, _layout_renderer
    _runtime_dir = runtime_dir
    _layout_renderer = layout_renderer


def runtime_dir() -> Path:
    """Return the configured Matt inventory runtime folder."""
    return _runtime_dir


def report_path() -> Path:
    """Return the persisted latest Matt inventory report path."""
    return _runtime_dir / "latest-report.json"


def price_meta_path() -> Path:
    """Return metadata for the most recent uploaded price workbook."""
    return _runtime_dir / "latest-price.json"


def stock_meta_path() -> Path:
    """Return metadata for the most recent uploaded stock workbook."""
    return _runtime_dir / "latest-stock.json"


def alert_workbook_path() -> Path:
    """Return the generated Matt stock alert workbook path."""
    return _runtime_dir / "matt-keszlet-riport.xlsx"


def render_layout(**kwargs: object) -> bytes:
    """Render a Matt inventory page through the configured app layout."""
    if _layout_renderer is None:
        raise RuntimeError("Matt inventory layout renderer is not configured.")
    return _layout_renderer(**kwargs)
