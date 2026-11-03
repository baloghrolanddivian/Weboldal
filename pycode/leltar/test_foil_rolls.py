from __future__ import annotations

import math
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from leltar.foil_rolls import (
    apply_action,
    build_session,
    calculate_roll_meters,
    configure_foil_rolls,
    parse_thickness_mm,
    render_page,
    save_session,
)


class FoilRollInventoryTests(unittest.TestCase):
    def test_extracts_editable_thickness_from_description(self) -> None:
        self.assertEqual(parse_thickness_mm("Élzáró - Antracit - 21x0,4mm - NATB3856GXY2104"), 0.4)
        self.assertEqual(parse_thickness_mm("ABS 42 × 1.2 mm"), 1.2)
        self.assertIsNone(parse_thickness_mm("Nincs méret"))

    def test_calculates_annulus_length_in_metres(self) -> None:
        result = calculate_roll_meters(380, 90, 0.4)
        expected = math.pi * (380**2 - 90**2) / (4 * 0.4 * 1000)
        self.assertAlmostEqual(result, expected)

    def test_builds_session_and_adds_manual_and_roll_metres(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Alkatr.-szám", "Alkatr.-leírás"])
        sheet.append(["F-1", "Élzáró - Antracit - 21x0,4mm - NATB3856GXY2104"])
        payload = BytesIO()
        workbook.save(payload)
        session = build_session("foliak.xlsx", payload.getvalue())
        row = session["rows"][0]

        apply_action(session, {"action": "set_value", "row_id": row["row_id"], "field": "manual_meters", "value": "600"})
        summary = apply_action(
            session,
            {
                "action": "add_roll",
                "row_id": row["row_id"],
                "outer_diameter_mm": "380",
                "inner_diameter_mm": "90",
            },
        )

        self.assertEqual(row["thickness_mm"], "0,4")
        self.assertEqual(len(summary["rolls"]), 1)
        self.assertGreater(float(summary["total_meters"].replace(",", ".")), 600)

    def test_rejects_an_outer_diameter_smaller_than_core(self) -> None:
        with self.assertRaisesRegex(ValueError, "nagyobbnak"):
            calculate_roll_meters(80, 90, 0.4)

    def test_thickness_edit_recalculates_existing_roll(self) -> None:
        session = {
            "rows": [
                {
                    "row_id": "row-1",
                    "thickness_mm": "0,4",
                    "manual_meters": "600",
                    "rolls": [
                        {
                            "roll_id": "roll-1",
                            "outer_diameter_mm": "380",
                            "inner_diameter_mm": "90",
                            "meters": "267,6",
                        }
                    ],
                }
            ]
        }
        summary = apply_action(
            session,
            {"action": "set_value", "row_id": "row-1", "field": "thickness_mm", "value": "0,8"},
        )
        self.assertAlmostEqual(float(summary["rolls"][0]["meters"].replace(",", ".")), 133.8, places=1)
        self.assertAlmostEqual(float(summary["total_meters"].replace(",", ".")), 733.8, places=1)

    def test_persisted_session_renders_admin_and_worker_views(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Alkatr.-szám", "Alkatr.-leírás"])
        sheet.append(["F-1", "Élzáró - Antracit - 21x0,4mm - NATB3856GXY2104"])
        payload = BytesIO()
        workbook.save(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            configure_foil_rolls(Path(temp_dir))
            save_session(build_session("foliak.xlsx", payload.getvalue()))
            admin_html = render_page(admin=True).decode("utf-8")
            worker_html = render_page(admin=False).decode("utf-8")

        self.assertIn("Aktuális fóliák feltöltése", admin_html)
        self.assertIn("Élzáró - Antracit", worker_html)
        self.assertIn('value="0,4"', worker_html)
        self.assertIn("Egész tekercsek", worker_html)
        self.assertIn("Darab tekercsek", worker_html)
        self.assertNotIn("A leírásból előtöltve", worker_html)
        self.assertIn(".foil-entry-row>.foil-add-roll", worker_html)
        self.assertIn("border:1px solid rgba(15,118,110,.28)", worker_html)
        self.assertIn("Külső átmérő", worker_html)


if __name__ == "__main__":
    unittest.main()
