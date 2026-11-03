"""Regression tests for the inventory router's closure and recount interfaces."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from leltar.recount import inventory_row_values, recount_rows, send_group_to_recount, set_recount_closed, set_recount_selection
from leltar.types.front import session_transaction, save_session_to_path
from leltar.types.front.engine import build_front_inventory_view_model
from leltar.types.material.engine import build_material_inventory_view_model


class RecountClosureTests(unittest.TestCase):
    def setUp(self):
        self.row = {"row_id": "a", "category": "718x297", "icg_code": "white", "stock_qty": 10, "book_qty": 10, "input_qty": "8", "is_serial": True, "part_number": "NFA_TEST", "description": "Front", "is_excluded": False}
        self.session = {"phase": "counting", "rows": [self.row]}

    def test_matching_initial_or_recount_quantities_close_automatically(self):
        self.assertFalse(inventory_row_values(self.row, "front")["closed"])
        self.row["input_qty"] = "10"
        self.assertTrue(inventory_row_values(self.row, "front")["auto_closed"])
        self.assertFalse(set_recount_closed(self.session, "a", False, "front")[0])
        self.row.update(initial_count_qty="8", recount_input_qty="10")
        self.assertTrue(inventory_row_values(self.row, "front")["closed"])

    def test_manual_closure_and_reopening(self):
        self.assertTrue(set_recount_closed(self.session, "a", True, "front")[0])
        self.assertFalse(set_recount_selection(self.session, "a", True, "check", "front")[0])
        self.assertTrue(set_recount_closed(self.session, "a", False, "front")[0])
        self.assertTrue(set_recount_selection(self.session, "a", True, "check", "front")[0])
        self.session["phase"] = "finalized"
        self.assertFalse(set_recount_closed(self.session, "a", True, "front")[0])

    def test_review_selection_and_resend_are_separate_from_initial_selection(self):
        self.row.update(recount_send_count=1, recount_input_qty="7", recount_selected=False)
        self.assertTrue(set_recount_selection(self.session, "a", True, "recount", "front")[0])
        self.assertTrue(recount_rows(self.session, "front", "recount")[0]["selected"])
        self.assertFalse(recount_rows(self.session, "front", "check")[0]["selected"])
        ok, _, count = send_group_to_recount(self.session, "718x297", "front", "recount")
        self.assertTrue(ok)
        self.assertEqual(count, 1)
        self.assertEqual(self.row["recount_send_count"], 2)
        self.assertEqual(self.row["recount_input_qty"], "")
        self.assertFalse(self.row["recount_review_selected"])

    def test_worker_views_can_hide_manually_closed_rows(self):
        set_recount_closed(self.session, "a", True, "front")
        self.assertEqual(build_front_inventory_view_model(self.session, hide_closed=True)["visible_rows"], [])
        self.assertEqual(build_material_inventory_view_model(self.session, hide_closed=True)["visible_rows"], [])
        self.assertEqual(len(build_material_inventory_view_model(self.session)["visible_rows"]), 1)

    def test_transaction_serializes_read_modify_write(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            save_session_to_path(path, {"counter": 0, "rows": []})
            def increment(_):
                with session_transaction(path) as state:
                    state["counter"] += 1
                    save_session_to_path(path, state)
            with patch("leltar.types.front.engine._repair_session", return_value=False):
                with ThreadPoolExecutor(max_workers=6) as pool:
                    list(pool.map(increment, range(30)))
                with session_transaction(path) as state:
                    self.assertEqual(state["counter"], 30)
