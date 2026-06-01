"""Calendar grid construction for the vacation calendar module."""

from __future__ import annotations

import calendar as month_calendar
from datetime import date, timedelta

from .dates import _vacation_month_bounds, _vacation_parse_date

def _vacation_build_calendar(month_start: date, leaves: list[dict]) -> tuple[list[list[dict]], int]:
    """Build week/cell data for the requested month and count limited days."""
    month_end = _vacation_month_bounds(month_start)[1]
    day_map: dict[date, list[dict]] = {}
    limit_day_count = 0

    for leave_entry in leaves:
        leave_start = _vacation_parse_date(leave_entry["start_date"])
        leave_end = _vacation_parse_date(leave_entry["end_date"])
        if leave_start is None or leave_end is None:
            continue
        current_day = max(leave_start, month_start)
        final_day = min(leave_end, month_end)
        while current_day <= final_day:
            day_map.setdefault(current_day, []).append(leave_entry)
            current_day += timedelta(days=1)

    weeks: list[list[dict]] = []
    month_weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    for week in month_weeks:
        week_cells: list[dict] = []
        for day in week:
            entries = sorted(day_map.get(day, []), key=lambda item: item["employee_name"].lower())
            department_loads: dict[int, dict] = {}
            for entry in entries:
                for department in entry["departments"]:
                    info = department_loads.setdefault(
                        int(department["id"]),
                        {
                            "id": int(department["id"]),
                            "name": str(department["name"]),
                            "count": 0,
                            "max_absent": int(department["max_absent"]),
                        },
                    )
                    info["count"] += 1
            loads = sorted(department_loads.values(), key=lambda item: item["name"].lower())
            if day.month == month_start.month and any(item["count"] >= item["max_absent"] for item in loads):
                limit_day_count += 1
            week_cells.append(
                {
                    "date": day,
                    "is_current_month": day.month == month_start.month,
                    "entries": entries,
                    "loads": loads,
                }
            )
        weeks.append(week_cells)
    return weeks, limit_day_count

