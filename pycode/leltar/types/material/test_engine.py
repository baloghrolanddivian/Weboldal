"""Regression tests for material-like inventory workbook imports."""

from __future__ import annotations

import unittest
from io import BytesIO

from openpyxl import Workbook

from leltar.types.material import build_semifinished_inventory_session


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


if __name__ == "__main__":
    unittest.main()
