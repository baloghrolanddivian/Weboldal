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
    return month_start.strftime("%Y-%m")

def _vacation_month_label(month_start: date) -> str:
    return f"{month_start.year}. {VACATION_MONTH_NAMES[month_start.month]}"

def _vacation_next_month(month_start: date, offset: int) -> date:
    year = month_start.year + ((month_start.month - 1 + offset) // 12)
    month = ((month_start.month - 1 + offset) % 12) + 1
    return date(year, month, 1)

def _vacation_month_bounds(month_start: date) -> tuple[date, date]:
    next_month = _vacation_next_month(month_start, 1)
    return month_start, next_month - timedelta(days=1)

def _vacation_parse_date(value: str) -> date | None:
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
    return day.isoformat()

def _vacation_date_label(day: date) -> str:
    return day.strftime("%Y.%m.%d")

def _vacation_now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")

