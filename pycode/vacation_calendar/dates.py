"""Date parsing, formatting, and month navigation helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta

VACATION_MONTH_NAMES = (
    "",
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)
VACATION_WEEKDAY_LABELS = ("H", "K", "Sze", "Cs", "P", "Szo", "V")

def _vacation_parse_month(month_value: str) -> date:
    """Parse a YYYY-MM month value, defaulting to the current month."""
    clean_value = month_value.strip()
    if clean_value:
        try:
            parsed = datetime.strptime(clean_value, "%Y-%m")
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass
    today = date.today()
    return date(today.year, today.month, 1)

def _vacation_month_value(month_start: date) -> str:
    """Format a month start date as an HTML month input value."""
    return month_start.strftime("%Y-%m")

def _vacation_month_label(month_start: date) -> str:
    """Format a Hungarian month label for display."""
    return f"{month_start.year}. {VACATION_MONTH_NAMES[month_start.month]}"

def _vacation_next_month(month_start: date, offset: int) -> date:
    """Return the first day of the month at offset from month_start."""
    year = month_start.year + ((month_start.month - 1 + offset) // 12)
    month = ((month_start.month - 1 + offset) % 12) + 1
    return date(year, month, 1)

def _vacation_month_bounds(month_start: date) -> tuple[date, date]:
    """Return the inclusive first and last day for a month."""
    next_month = _vacation_next_month(month_start, 1)
    return month_start, next_month - timedelta(days=1)

def _vacation_parse_date(value: str) -> date | None:
    """Parse a supported date string into a date, or None for empty/invalid input."""
    clean_value = value.strip()
    if not clean_value:
        return None
    for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(clean_value, pattern).date()
        except ValueError:
            continue
    return None

def _vacation_date_value(day: date) -> str:
    """Format a date as an ISO value for forms and storage."""
    return day.isoformat()

def _vacation_date_label(day: date) -> str:
    """Format a date as a Hungarian display label."""
    return day.strftime("%Y.%m.%d")

def _vacation_now_stamp() -> str:
    """Return the current timestamp for persistence metadata."""
    return datetime.now().isoformat(timespec="seconds")

