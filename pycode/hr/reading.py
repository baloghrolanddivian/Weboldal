"""Read HR spreadsheets without writing the uploaded contents to disk."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover
    load_workbook = None

HR_COLUMNS = (
    "name", "vat", "address", "job", "birthname", "birthplace", "birthday",
    "momname", "taj", "entry", "payment", "stayaddress", "email", "phone",
)


def _value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y.%m.%d.")
    return str(value).strip()


def read_people(file_data: bytes) -> list[dict[str, str]]:
    """Parse rows from memory; the upload is never persisted by this module."""
    if load_workbook is None:
        raise RuntimeError("Az Excel feldolgozásához az openpyxl csomag szükséges.")
    workbook = load_workbook(BytesIO(file_data), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    people = []
    # Row 1 is the spreadsheet header/description row and must never become an employee.
    for row in rows[1:]:
        values = [_value(row[index] if index < len(row) else "") for index in range(len(HR_COLUMNS))]
        if not any(values):
            continue
        people.append(dict(zip(HR_COLUMNS, values)))
    if not people:
        raise ValueError("Az Excel nem tartalmaz feldolgozható személy sort.")
    return people
