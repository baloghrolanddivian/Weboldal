from __future__ import annotations

import unittest
from io import BytesIO

from openpyxl import Workbook

from leltar.types.material import add_material_inventory_row, add_material_inventory_rows_from_file


class ManualMaterialRowsTests(unittest.TestCase):
    def _session(self) -> dict:
        return {
            "phase": "counting",
            "updated_at": "",
            "rows": [
                {
                    "row_id": "existing",
                    "part_number": "P1",
                    "description": "Meglévő tétel",
                    "book_qty": "10",
                    "book_unit": "db",
                    "icg_code": "ANYAG",
                    "input_qty": "4",
                }
            ],
        }

    def test_adds_item_without_changing_existing_counts(self) -> None:
        session = self._session()
        row = add_material_inventory_row(
            session,
            "NATB3856GXY2104",
            "Élzáró - Antracit - 21x0,4mm",
            "ÉLZÁRÓ",
            "600",
            "m",
        )

        self.assertEqual(len(session["rows"]), 2)
        self.assertEqual(next(item for item in session["rows"] if item["row_id"] == "existing")["input_qty"], "4")
        self.assertEqual(row["input_qty"], "")
        self.assertEqual(row["book_unit"], "m")
        self.assertTrue(row["manually_added"])

    def test_rejects_duplicate_in_same_category(self) -> None:
        session = self._session()
        with self.assertRaisesRegex(ValueError, "már szerepel"):
            add_material_inventory_row(session, "p1", "Más név", "anyag")

    def test_rejects_addition_after_finalization(self) -> None:
        session = self._session()
        session["phase"] = "finalized"
        with self.assertRaisesRegex(ValueError, "lezárt"):
            add_material_inventory_row(session, "P2", "Új tétel", "ANYAG")

    def test_adds_compact_excel_list_and_honors_exclusion_column(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Alkatr.-szám", "Alkatr.-leírás", "Leltarbol_ki"])
        sheet.append(["NELZ_ANK_22x04", "Élzáró - Antracit - 21x0,4mm", ""])
        sheet.append(["NELZ_OLD", "Régi élzáró", "igen"])
        output = BytesIO()
        workbook.save(output)
        session = self._session()

        result = add_material_inventory_rows_from_file(session, "élfóliák.xlsx", output.getvalue(), "Élzáró", "m")

        self.assertEqual(result, {"added": 1, "duplicate": 0, "excluded": 1, "invalid": 0})
        added = next(row for row in session["rows"] if row["part_number"] == "NELZ_ANK_22x04")
        self.assertEqual(added["icg_code"], "Élzáró")
        self.assertEqual(added["book_unit"], "m")

    def test_adds_semifinished_list_by_color_without_changing_existing_count(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["alkatresz szam", "alkatresz leiras", "SZIN.Desc", "konyvelesi mennyiseg"])
        sheet.append(["F2", "Uj felkesz tetel", "Antracit", 12])
        sheet.append(["F3", "Masik felkesz tetel", "Feher", 8])
        output = BytesIO()
        workbook.save(output)
        session = self._session()
        session["category_label"] = "Szín"

        result = add_material_inventory_rows_from_file(
            session, "felkesz-plusz.xlsx", output.getvalue(), "", "db"
        )

        self.assertEqual(result["added"], 2)
        self.assertEqual(next(row for row in session["rows"] if row["row_id"] == "existing")["input_qty"], "4")
        added = next(row for row in session["rows"] if row["part_number"] == "F2")
        self.assertEqual(added["icg_code"], "Antracit")
        self.assertEqual(added["input_qty"], "")
        self.assertEqual(next(row for row in session["rows"] if row["part_number"] == "F3")["icg_code"], "Feher")


if __name__ == "__main__":
    unittest.main()
