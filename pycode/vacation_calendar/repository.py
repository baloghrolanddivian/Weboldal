"""SQLite persistence helpers for the vacation calendar."""

from __future__ import annotations

import sqlite3
from datetime import date

from .config import vacation_calendar_db, vacation_runtime_dir
from .dates import _vacation_date_value

def _vacation_db_connection() -> sqlite3.Connection:
    """Open the calendar database, ensure schema exists, and enable foreign keys."""
    vacation_runtime_dir().mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(vacation_calendar_db())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS vacation_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            max_absent INTEGER NOT NULL DEFAULT 1 CHECK (max_absent >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employee_departments (
            employee_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            PRIMARY KEY (employee_id, department_id),
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES vacation_departments(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS vacation_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE
        );
        """
    )
    return connection

def _vacation_fetch_departments(connection: sqlite3.Connection) -> list[dict]:
    """Fetch departments with employee counts for list rendering."""
    rows = connection.execute(
        """
        SELECT
            d.id,
            d.name,
            d.max_absent,
            COUNT(ed.employee_id) AS employee_count
        FROM vacation_departments d
        LEFT JOIN vacation_employee_departments ed ON ed.department_id = d.id
        GROUP BY d.id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "max_absent": int(row["max_absent"]),
            "employee_count": int(row["employee_count"] or 0),
        }
        for row in rows
    ]

def _vacation_fetch_department(connection: sqlite3.Connection, department_id: int) -> dict | None:
    """Fetch one department by id."""
    row = connection.execute(
        """
        SELECT id, name, max_absent
        FROM vacation_departments
        WHERE id = ?
        """,
        (department_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": int(row["id"]), "name": str(row["name"]), "max_absent": int(row["max_absent"])}

def _vacation_employee_department_map(connection: sqlite3.Connection) -> dict[int, list[dict]]:
    """Build an employee-id to department-list mapping."""
    rows = connection.execute(
        """
        SELECT
            ed.employee_id,
            d.id AS department_id,
            d.name,
            d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    mapping: dict[int, list[dict]] = {}
    for row in rows:
        mapping.setdefault(int(row["employee_id"]), []).append(
            {
                "id": int(row["department_id"]),
                "name": str(row["name"]),
                "max_absent": int(row["max_absent"]),
            }
        )
    return mapping

def _vacation_fetch_employees(connection: sqlite3.Connection) -> list[dict]:
    """Fetch employees with departments and vacation counts."""
    department_map = _vacation_employee_department_map(connection)
    rows = connection.execute(
        """
        SELECT
            e.id,
            e.name,
            COUNT(v.id) AS vacation_count
        FROM vacation_employees e
        LEFT JOIN vacation_entries v ON v.employee_id = e.id
        GROUP BY e.id
        ORDER BY e.name COLLATE NOCASE
        """
    ).fetchall()
    employees: list[dict] = []
    for row in rows:
        department_items = department_map.get(int(row["id"]), [])
        employees.append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "vacation_count": int(row["vacation_count"] or 0),
                "departments": department_items,
                "department_ids": [int(item["id"]) for item in department_items],
                "department_names": [str(item["name"]) for item in department_items],
            }
        )
    return employees

def _vacation_fetch_employee(connection: sqlite3.Connection, employee_id: int) -> dict | None:
    """Fetch one employee with department assignments."""
    row = connection.execute(
        """
        SELECT id, name
        FROM vacation_employees
        WHERE id = ?
        """,
        (employee_id,),
    ).fetchone()
    if row is None:
        return None

    department_rows = connection.execute(
        """
        SELECT d.id, d.name, d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        WHERE ed.employee_id = ?
        ORDER BY d.name COLLATE NOCASE
        """,
        (employee_id,),
    ).fetchall()
    departments = [
        {"id": int(item["id"]), "name": str(item["name"]), "max_absent": int(item["max_absent"])}
        for item in department_rows
    ]
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "departments": departments,
        "department_ids": [int(item["id"]) for item in departments],
        "department_names": [str(item["name"]) for item in departments],
    }

def _vacation_fetch_leave(connection: sqlite3.Connection, leave_id: int) -> dict | None:
    """Fetch one leave entry with employee and department details."""
    row = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.id = ?
        """,
        (leave_id,),
    ).fetchone()
    if row is None:
        return None

    employee = _vacation_fetch_employee(connection, int(row["employee_id"]))
    return {
        "id": int(row["id"]),
        "employee_id": int(row["employee_id"]),
        "employee_name": str(row["employee_name"]),
        "start_date": str(row["start_date"]),
        "end_date": str(row["end_date"]),
        "note": str(row["note"] or ""),
        "departments": employee["departments"] if employee else [],
    }

def _vacation_fetch_leaves_in_range(connection: sqlite3.Connection, start_day: date, end_day: date) -> list[dict]:
    """Fetch leave entries intersecting the requested date range."""
    employee_map = {item["id"]: item for item in _vacation_fetch_employees(connection)}
    rows = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.start_date <= ? AND v.end_date >= ?
        ORDER BY v.start_date, e.name COLLATE NOCASE
        """,
        (_vacation_date_value(end_day), _vacation_date_value(start_day)),
    ).fetchall()

    leaves: list[dict] = []
    for row in rows:
        employee = employee_map.get(int(row["employee_id"]), {})
        leaves.append(
            {
                "id": int(row["id"]),
                "employee_id": int(row["employee_id"]),
                "employee_name": str(row["employee_name"]),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "note": str(row["note"] or ""),
                "departments": employee.get("departments", []),
                "department_names": employee.get("department_names", []),
            }
        )
    return leaves

