"""Runtime configuration and route constants for the vacation calendar."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

VACATION_CALENDAR_ROUTE = "/apps/szabadsag-naptar"
VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/mentes"
VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/torles"
VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/mentes"
VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/torles"
VACATION_CALENDAR_LEAVE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/mentes"
VACATION_CALENDAR_LEAVE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/torles"

REPO_ROOT = Path(__file__).resolve().parents[2]

_runtime_dir = REPO_ROOT / "runtime" / "szabadsag-naptar"
_layout_renderer: Callable[..., bytes] | None = None


def configure_vacation_calendar(runtime_dir: Path, layout_renderer: Callable[..., bytes]) -> None:
    """Configure the calendar runtime directory and outer layout renderer."""
    global _runtime_dir, _layout_renderer
    _runtime_dir = runtime_dir
    _layout_renderer = layout_renderer


def vacation_runtime_dir() -> Path:
    """Return the configured vacation calendar runtime directory."""
    return _runtime_dir


def vacation_calendar_db() -> Path:
    """Return the SQLite database path for the vacation calendar."""
    return _runtime_dir / "calendar.db"


def render_layout(**kwargs: object) -> bytes:
    """Render a page through the configured application layout callback."""
    if _layout_renderer is None:
        raise RuntimeError("Vacation calendar layout renderer is not configured.")
    return _layout_renderer(**kwargs)
