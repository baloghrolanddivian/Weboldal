from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

from .dates import _vacation_date_label, _vacation_date_value, _vacation_now_stamp, _vacation_parse_date
from .forms import _vacation_form_value, _vacation_form_values, _vacation_parse_int
from .repository import (
    _vacation_db_connection,
    _vacation_fetch_department,
    _vacation_fetch_employee,
    _vacation_fetch_leave,
)


def _clean_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _vacation_overlaps_existing_leave(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> bool:
    query = """
        SELECT 1
        FROM vacation_entries
        WHERE employee_id = ?
          AND start_date <= ?
          AND end_date >= ?
    """
    params: list[object] = [employee_id, _vacation_date_value(end_day), _vacation_date_value(start_day)]
    if exclude_leave_id is not None:
        query += " AND id <> ?"
        params.append(exclude_leave_id)
    row = connection.execute(query, params).fetchone()
    return row is not None

def _vacation_validate_department_limits(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> tuple[bool, str]:
    employee = _vacation_fetch_employee(connection, employee_id)
    if employee is None:
        return False, "A kiválasztott kolléga nem található."
    if not employee["departments"]:
        return False, "A kollégához legalább egy részleget be kell állítani."

    current_day = start_day
    while current_day <= end_day:
        day_value = _vacation_date_value(current_day)
        for department in employee["departments"]:
            absent_row = connection.execute(
                """
                SELECT COUNT(DISTINCT v.employee_id) AS absent_count
                FROM vacation_entries v
                JOIN vacation_employee_departments ed ON ed.employee_id = v.employee_id
                WHERE ed.department_id = ?
                  AND v.start_date <= ?
                  AND v.end_date >= ?
                  AND (? IS NULL OR v.id <> ?)
                """,
                (department["id"], day_value, day_value, exclude_leave_id, exclude_leave_id),
            ).fetchone()
            absent_count = int(absent_row["absent_count"] or 0) if absent_row else 0
            if absent_count + 1 > int(department["max_absent"]):
                return (
                    False,
                    f"A(z) {department['name']} részlegen {_vacation_date_label(current_day)} napon már elértétek a szabadságlimitet.",
                )
        current_day += timedelta(days=1)
    return True, ""

def _vacation_save_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    max_absent = _vacation_parse_int(_vacation_form_value(form_data, "max_absent"), default=1)

    if not name:
        return False, "A részleg neve kötelező."
    if max_absent is None or max_absent < 0:
        return False, "A részleg limitje 0 vagy nagyobb szám lehet."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            if department_id:
                exists = _vacation_fetch_department(connection, department_id)
                if exists is None:
                    return False, "A kiválasztott részleg nem található."
                connection.execute(
                    """
                    UPDATE vacation_departments
                    SET name = ?, max_absent = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, max_absent, now_stamp, department_id),
                )
                return True, f"Frissítve: {name}"

            connection.execute(
                """
                INSERT INTO vacation_departments (name, max_absent, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, max_absent, now_stamp, now_stamp),
            )
            return True, f"Létrehozva: {name}"
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű részleg már létezik."

def _vacation_delete_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    if department_id is None:
        return False, "A törlendő részleg nem azonosítható."

    with _vacation_db_connection() as connection:
        department = _vacation_fetch_department(connection, department_id)
        if department is None:
            return False, "A törlendő részleg nem található."

        assigned_row = connection.execute(
            "SELECT COUNT(*) AS count FROM vacation_employee_departments WHERE department_id = ?",
            (department_id,),
        ).fetchone()
        if assigned_row and int(assigned_row["count"] or 0) > 0:
            return False, "A részleg még kollégákhoz van rendelve. Előbb vedd le onnan."

        connection.execute("DELETE FROM vacation_departments WHERE id = ?", (department_id,))
    return True, f"Törölve: {department['name']}"

def _vacation_save_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    department_ids = sorted(
        {
            department_id
            for raw_value in _vacation_form_values(form_data, "department_ids")
            for department_id in [_vacation_parse_int(raw_value)]
            if department_id is not None
        }
    )

    if not name:
        return False, "A kolléga neve kötelező."
    if not department_ids:
        return False, "A kollégához legalább egy részleget válassz ki."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            valid_departments = {
                int(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM vacation_departments WHERE id IN ({','.join('?' for _ in department_ids)})",
                    department_ids,
                ).fetchall()
            }
            if len(valid_departments) != len(department_ids):
                return False, "A kiválasztott részlegek között van érvénytelen."

            if employee_id:
                employee = _vacation_fetch_employee(connection, employee_id)
                if employee is None:
                    return False, "A kiválasztott kolléga nem található."
                connection.execute(
                    """
                    UPDATE vacation_employees
                    SET name = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, now_stamp, employee_id),
                )
                connection.execute("DELETE FROM vacation_employee_departments WHERE employee_id = ?", (employee_id,))
                target_id = employee_id
                message = f"Frissítve: {name}"
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO vacation_employees (name, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (name, now_stamp, now_stamp),
                )
                target_id = int(cursor.lastrowid)
                message = f"Létrehozva: {name}"

            connection.executemany(
                """
                INSERT INTO vacation_employee_departments (employee_id, department_id)
                VALUES (?, ?)
                """,
                [(target_id, department_id) for department_id in department_ids],
            )
            return True, message
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű kolléga már létezik."

def _vacation_delete_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    if employee_id is None:
        return False, "A törlendő kolléga nem azonosítható."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A törlendő kolléga nem található."
        connection.execute("DELETE FROM vacation_employees WHERE id = ?", (employee_id,))
    return True, f"Törölve: {employee['name']}"

def _vacation_save_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    start_day = _vacation_parse_date(_vacation_form_value(form_data, "start_date"))
    end_day = _vacation_parse_date(_vacation_form_value(form_data, "end_date"))
    note = _clean_spaces(_vacation_form_value(form_data, "note"))

    if employee_id is None:
        return False, "A szabadsághoz válassz ki egy kollégát."
    if start_day is None or end_day is None:
        return False, "A szabadság kezdete és vége kötelező."
    if end_day < start_day:
        return False, "A szabadság vége nem lehet korábbi, mint a kezdete."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A kiválasztott kolléga nem található."
        if not employee["departments"]:
            return False, "A kollégához nincs részleg beállítva, ezért nem ellenőrizhető a limit."
        if _vacation_overlaps_existing_leave(connection, employee_id, start_day, end_day, exclude_leave_id=leave_id):
            return False, "Ehhez a kollégához már van átfedő szabadság felvéve."

        valid, message = _vacation_validate_department_limits(
            connection,
            employee_id,
            start_day,
            end_day,
            exclude_leave_id=leave_id,
        )
        if not valid:
            return False, message

        now_stamp = _vacation_now_stamp()
        if leave_id:
            existing = _vacation_fetch_leave(connection, leave_id)
            if existing is None:
                return False, "A kiválasztott szabadság nem található."
            connection.execute(
                """
                UPDATE vacation_entries
                SET employee_id = ?, start_date = ?, end_date = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, leave_id),
            )
            return True, f"Frissítve: {employee['name']} szabadsága"

        connection.execute(
            """
            INSERT INTO vacation_entries (employee_id, start_date, end_date, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, now_stamp),
        )
        return True, f"Felvéve: {employee['name']} szabadsága"

def _vacation_delete_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    if leave_id is None:
        return False, "A törlendő szabadság nem azonosítható."

    with _vacation_db_connection() as connection:
        leave_entry = _vacation_fetch_leave(connection, leave_id)
        if leave_entry is None:
            return False, "A törlendő szabadság nem található."
        connection.execute("DELETE FROM vacation_entries WHERE id = ?", (leave_id,))
    return True, f"Törölve: {leave_entry['employee_name']} szabadsága"

