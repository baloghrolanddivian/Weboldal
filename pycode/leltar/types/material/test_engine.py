"""Regression tests for material-like inventory workbook imports."""

from __future__ import annotations

import unittest
from io import BytesIO

from openpyxl import Workbook

from leltar.types.material import build_material_inventory_session, build_semifinished_inventory_session


class SemifinishedInventoryImportTests(unittest.TestCase):
    def _workbook(self, stock_header: str) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Félkész raktár"
        sheet.append(
            [
                "Alkatr.-szám",
                "Alkatr.-leírás",
                "Alkatr.-Család",
                stock_header,
                "Raktári ME",
                "SZIN",
                "SZIN.Desc",
            ]
        )
        sheet.append(["AFE_163x505_ANK", "A.fen. 163x505x18", "Fenék", 124, "DB", "ANK", "Antracit kr."])
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def test_accepts_available_warehouse_stock_header_from_uploaded_export(self) -> None:
        for stock_header in ("Rend.áll.rakt.készl.", "Rend.\ufffdll.rakt.k\ufffdszl."):
            with self.subTest(stock_header=stock_header):
                session = build_semifinished_inventory_session(
                    "Félkész raktár.xlsx",
                    self._workbook(stock_header),
                )
                self.assertEqual(len(session["rows"]), 1)
                self.assertEqual(session["rows"][0]["part_number"], "AFE_163x505_ANK")
                self.assertEqual(session["rows"][0]["book_qty"], "124")
                self.assertEqual(session["rows"][0]["icg_code"], "Antracit kr.")

    def test_accepts_bookkeeping_unit_without_treating_it_as_stock_quantity(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Alkatr.-szám", "Alkatr.-leírás", "Könyvelés ME", "ICG kód"])
        sheet.append(["P1", "Tesztanyag", "KG", "ANYAG"])
        output = BytesIO()
        workbook.save(output)

        session = build_material_inventory_session("könyvelési mennyiség.xlsx", output.getvalue())

        self.assertEqual(len(session["rows"]), 1)
        self.assertEqual(session["rows"][0]["book_qty"], "")
        self.assertEqual(session["rows"][0]["book_unit"], "kg")


if __name__ == "__main__":
    unittest.main()
