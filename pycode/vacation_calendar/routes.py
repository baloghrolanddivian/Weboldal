from __future__ import annotations

from .forms import _vacation_form_value, _vacation_form_values, _vacation_parse_form, _vacation_parse_int, _vacation_query_params
from .operations import (
    _vacation_delete_department,
    _vacation_delete_employee,
    _vacation_delete_leave,
    _vacation_save_department,
    _vacation_save_employee,
    _vacation_save_leave,
)
from .page import render_vacation_calendar


def render_vacation_calendar_request(raw_path: str) -> tuple[int, bytes]:
    query = _vacation_query_params(raw_path)
    body = render_vacation_calendar(
        month_value=query.get("month", ""),
        edit_department_id=_vacation_parse_int(query.get("edit_department", "")),
        edit_employee_id=_vacation_parse_int(query.get("edit_employee", "")),
        edit_leave_id=_vacation_parse_int(query.get("edit_leave", "")),
    )
    return 200, body


def handle_vacation_department_save(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_save_department(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
        edit_department_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "department_id")),
        department_draft=None
        if success
        else {
            "id": _vacation_form_value(form_data, "department_id"),
            "name": _vacation_form_value(form_data, "name"),
            "max_absent": _vacation_form_value(form_data, "max_absent") or "1",
        },
    )
    return 200 if success else 400, body


def handle_vacation_department_delete(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_delete_department(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
    )
    return 200 if success else 400, body


def handle_vacation_employee_save(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_save_employee(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
        edit_employee_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "employee_id")),
        employee_draft=None
        if success
        else {
            "id": _vacation_form_value(form_data, "employee_id"),
            "name": _vacation_form_value(form_data, "name"),
            "department_ids": [
                department_id
                for raw_value in _vacation_form_values(form_data, "department_ids")
                for department_id in [_vacation_parse_int(raw_value)]
                if department_id is not None
            ],
        },
    )
    return 200 if success else 400, body


def handle_vacation_employee_delete(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_delete_employee(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
    )
    return 200 if success else 400, body


def handle_vacation_leave_save(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_save_leave(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
        edit_leave_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "leave_id")),
        leave_draft=None
        if success
        else {
            "id": _vacation_form_value(form_data, "leave_id"),
            "employee_id": _vacation_form_value(form_data, "employee_id"),
            "start_date": _vacation_form_value(form_data, "start_date"),
            "end_date": _vacation_form_value(form_data, "end_date"),
            "note": _vacation_form_value(form_data, "note"),
        },
    )
    return 200 if success else 400, body


def handle_vacation_leave_delete(raw_body: bytes) -> tuple[int, bytes]:
    form_data = _vacation_parse_form(raw_body)
    success, message = _vacation_delete_leave(form_data)
    body = render_vacation_calendar(
        month_value=_vacation_form_value(form_data, "return_month"),
        message=message,
        success=success,
    )
    return 200 if success else 400, body
