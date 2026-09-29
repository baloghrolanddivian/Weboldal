from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leltar.cutting_inventory import (
    apply_active_action,
    apply_catalog_action,
    close_inventory,
    configure_cutting_inventory,
    load_state,
    load_catalog,
    render_admin_page,
    render_worker_page,
    start_inventory,
)


class CuttingInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        configure_cutting_inventory(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_starts_inventory_with_reference_catalog(self) -> None:
        session = start_inventory("2026-09-30")
        self.assertEqual(len(session["boards"]), 20)
        self.assertEqual(len(session["worktops"]), 44)
        self.assertEqual(len(session["wall_panels"]), 13)
        self.assertIn("2026.09.30.", render_admin_page().decode("utf-8"))

    def test_board_four_sizes_are_converted_to_square_metres(self) -> None:
        session = start_inventory("2026-09-30")
        row = session["boards"][0]
        result = apply_active_action({"action": "set_board_count", "category": "boards", "row_id": row["row_id"], "size_key": "2800x600", "value": "2"})
        self.assertEqual(result["row"]["total"], "3,36")

    def test_worktop_and_wall_panel_accept_exact_millimetres(self) -> None:
        session = start_inventory("2026-09-30")
        worktop = session["worktops"][0]
        wall_m2 = session["wall_panels"][0]
        wall_m = session["wall_panels"][1]
        worktop_result = apply_active_action({"action": "add_piece", "category": "worktops", "row_id": worktop["row_id"], "length_mm": "1270"})
        wall_m2_result = apply_active_action({"action": "add_piece", "category": "wall_panels", "row_id": wall_m2["row_id"], "length_mm": "1000"})
        wall_m_result = apply_active_action({"action": "add_piece", "category": "wall_panels", "row_id": wall_m["row_id"], "length_mm": "1500"})
        self.assertEqual(worktop_result["row"]["total"], "1,27")
        self.assertEqual(wall_m2_result["row"]["total"], "0,64")
        self.assertEqual(wall_m2_result["row"]["unit"], "m²")
        self.assertEqual(wall_m_result["row"]["total"], "1,50")
        self.assertEqual(wall_m_result["row"]["unit"], "m")

    def test_closing_archives_and_clears_active_inventory(self) -> None:
        start_inventory("2026-09-30")
        closed = close_inventory()
        state = load_state()
        self.assertEqual(closed["status"], "closed")
        self.assertIsNone(state["active"])
        self.assertEqual(len(state["history"]), 1)

    def test_pages_render_management_and_counting_controls(self) -> None:
        start_inventory("2026-09-30")
        admin = render_admin_page().decode("utf-8")
        worker = render_worker_page().decode("utf-8")
        self.assertIn("Leltár lezárása", admin)
        self.assertIn("2800×200", worker)
        self.assertIn("Méret mm-ben", worker)
        self.assertIn("Falipanel", worker)
        self.assertIn("Leltári tételek szerkesztése", admin)

    def test_catalog_items_and_size_columns_can_be_added_and_edited(self) -> None:
        session = start_inventory("2026-09-30")
        apply_catalog_action({"action": "save_size", "width_mm": "3000", "height_mm": "400"})
        apply_catalog_action({"action": "save_item", "category": "boards", "name": "Új bútorlap"})
        apply_catalog_action({"action": "save_item", "category": "worktops", "name": "Új munkalap"})
        apply_catalog_action({"action": "save_item", "category": "wall_panels", "name": "Új falipanel", "unit": "m2", "width_mm": "700"})
        catalog = load_catalog()
        active = load_state()["active"]
        self.assertEqual(len(catalog["board_sizes"]), 5)
        self.assertEqual(len(active["board_sizes"]), 5)
        self.assertEqual(active["boards"][-1]["name"], "Új bútorlap")
        self.assertEqual(active["worktops"][-1]["name"], "Új munkalap")
        self.assertEqual(active["wall_panels"][-1]["width_mm"], 700)
        new_wall = active["wall_panels"][-1]
        result = apply_active_action({"action": "add_piece", "category": "wall_panels", "row_id": new_wall["row_id"], "length_mm": "1000"})
        self.assertEqual(result["row"]["total"], "0,70")

    def test_catalog_rename_preserves_open_inventory_values(self) -> None:
        session = start_inventory("2026-09-30")
        board = session["boards"][0]
        apply_active_action({"action": "set_board_count", "category": "boards", "row_id": board["row_id"], "size_key": "2800x600", "value": "2"})
        apply_catalog_action({"action": "save_item", "category": "boards", "item_id": board["row_id"], "name": "Átnevezett bútorlap"})
        active_board = load_state()["active"]["boards"][0]
        self.assertEqual(active_board["name"], "Átnevezett bútorlap")
        self.assertEqual(active_board["counts"]["2800x600"], "2")


if __name__ == "__main__":
    unittest.main()
