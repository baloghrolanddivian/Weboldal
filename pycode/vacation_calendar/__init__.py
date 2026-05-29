from __future__ import annotations

from .config import (
    VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE,
    VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE,
    VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE,
    VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE,
    VACATION_CALENDAR_LEAVE_DELETE_ROUTE,
    VACATION_CALENDAR_LEAVE_SAVE_ROUTE,
    VACATION_CALENDAR_ROUTE,
    configure_vacation_calendar,
)
from .page import render_vacation_calendar
from .routes import (
    handle_vacation_department_delete,
    handle_vacation_department_save,
    handle_vacation_employee_delete,
    handle_vacation_employee_save,
    handle_vacation_leave_delete,
    handle_vacation_leave_save,
    render_vacation_calendar_request,
)

__all__ = [
    "VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE",
    "VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE",
    "VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE",
    "VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE",
    "VACATION_CALENDAR_LEAVE_DELETE_ROUTE",
    "VACATION_CALENDAR_LEAVE_SAVE_ROUTE",
    "VACATION_CALENDAR_ROUTE",
    "configure_vacation_calendar",
    "handle_vacation_department_delete",
    "handle_vacation_department_save",
    "handle_vacation_employee_delete",
    "handle_vacation_employee_save",
    "handle_vacation_leave_delete",
    "handle_vacation_leave_save",
    "render_vacation_calendar_request",
    "render_vacation_calendar",
]
