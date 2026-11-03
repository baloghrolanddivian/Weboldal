from __future__ import annotations

import copy
import unittest
from io import BytesIO

from openpyxl import Workbook

from leltar.types.front import refresh_front_inventory_stock_quantities
from leltar.types.material import refresh_material_inventory_book_quantities


def workbook_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class FrozenStockRefreshTests(unittest.TestCase):
    def test_material_refresh_changes_only_book_quantity(self) -> None:
        session = {
            "phase": "counting",
            "rows": [
                {
                    "row_id": "p1",
                    "part_number": "P1",
                    "description": "Material",
                    "icg_code": "ANYAG",
                    "book_qty": "10",
                    "book_unit": "db",
                    "input_qty": "7",
                    "recount_qty": "8",
                    "recount_history": [{"value": "8"}],
                }
            ],
        }
        before_row = copy.deepcopy(session["rows"][0])
        payload = workbook_bytes(
            ["Alkatr.-szám", "Alkatr.-leírás", "Befagyott készlet menny."],
            [["P1", "A leírás eltérhet", -1]],
        )

        result = refresh_material_inventory_book_quantities(session, "frozen.xlsx", payload, "material")

        self.assertEqual(result, {"source_rows": 1, "matched": 1, "changed": 1, "missing": 0})
        self.assertEqual(session["rows"][0]["book_qty"], "-1")
        expected = copy.deepcopy(before_row)
        expected["book_qty"] = "-1"
        self.assertEqual(session["rows"][0], expected)

    def test_semifinished_refresh_keeps_counts_and_matches_only_by_part_number(self) -> None:
        session = {
            "phase": "counting",
            "rows": [
                {"row_id": "a", "part_number": "F1", "description": "Part", "icg_code": "Antracit", "book_qty": "2", "input_qty": "4"},
                {"row_id": "b", "part_number": "F2", "description": "Part", "icg_code": "Feher", "book_qty": "3", "input_qty": "6"},
            ],
        }
        payload = workbook_bytes(
            ["Alkatr.-szám", "Alkatr.-leírás", "Befagyott készlet menny."],
            [["F1", "Más leírás", 12], ["F2", "Szín nélkül is működik", 0]],
        )

        result = refresh_material_inventory_book_quantities(session, "frozen.xlsx", payload, "semifinished")

        self.assertEqual(result["changed"], 2)
        self.assertEqual([row["book_qty"] for row in session["rows"]], ["12", "0"])
        self.assertEqual([row["input_qty"] for row in session["rows"]], ["4", "6"])

    def test_front_refresh_changes_only_stock_quantity(self) -> None:
        session = {
            "phase": 0,
            "rows": [
                {
                    "row_id": "NFA_TEST",
                    "part_number": "NFA_TEST",
                    "description": "Front 716x396",
                    "stock_qty": 5,
                    "input_qty": "9",
                    "status": "pending",
                    "review_level": 0,
                    "recount_history": [{"value": "10"}],
                }
            ],
        }
        before_row = copy.deepcopy(session["rows"][0])
        payload = workbook_bytes(
            ["Alkatr.-szám", "Alkatr.-leírás", "Befagyott készlet menny."],
            [["NFA_TEST", "Eltérő frontleírás", 31]],
        )

        result = refresh_front_inventory_stock_quantities(session, "front-frozen.xlsx", payload)

        self.assertEqual(result, {"source_rows": 1, "matched": 1, "changed": 1, "missing": 0})
        self.assertEqual(session["rows"][0]["stock_qty"], 31)
        expected = copy.deepcopy(before_row)
        expected["stock_qty"] = 31
        self.assertEqual(session["rows"][0], expected)


if __name__ == "__main__":
    unittest.main()
