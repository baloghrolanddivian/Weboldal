"""Regression checks for the ten-piece storage replenishment rule."""

import unittest
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from nettfront.order import engine
from nettfront.order import jobs, operations, pages


class OrderQuantityTests(unittest.TestCase):
    def test_ten_piece_capacity_allows_at_most_two_extra_fronts(self):
        for current, expected in [(6, 5), (5, 5), (4, 5), (3, 5), (2, 10), (1, 10), (0, 10), (-3, 15)]:
            with self.subTest(current=current):
                quantity = engine.calculate_order_qty(current, 10, safe_stock=7)
                self.assertEqual(quantity, expected)
                self.assertLessEqual(current + quantity, 12)

    def test_other_capacity_and_existing_exceptions_are_preserved(self):
        self.assertEqual(engine.calculate_order_qty(16, 20, safe_stock=17), 0)
        self.assertEqual(engine.calculate_order_qty(1, 2, safe_stock=1), 1)
        self.assertEqual(engine.calculate_order_qty(-3, 10, "Egyedi f. front", 7), 3)
        self.assertEqual(engine.calculate_order_qty(6, 10), 0)

    def test_builder_applies_rule_to_normal_and_super_matt_below_threshold(self):
        headers = ["Alkatr.-szám", "Alkatr.-leírás", "Rend.áll", "Biztonsági készlet", "Tárolh.menny."]
        stock_rows = [
            ("NFA_NORMAL", "Normal front", 6, 7, 10),
            ("NFA_SM", "SM. front", 6, 7, 10),
            ("NFA_THRESHOLD", "At threshold", 7, 7, 10),
            ("NFA_SM_THRESHOLD", "SM. at threshold", 7, 7, 10),
        ]
        with (
            patch.object(engine, "_load_stock_headers_and_rows", return_value=(headers, stock_rows)),
            patch.object(engine, "load_avg_by_part", return_value={}),
            patch.object(engine, "rows_to_suggestion_workbook", return_value=b""),
        ):
            result = engine.build_order_suggestions(b"")
        self.assertEqual({row.part_number: row.order_qty for row in result.rows}, {"NFA_NORMAL": 5, "NFA_SM": 5})


class ReviewBlockTests(unittest.TestCase):
    headers = ["Alkatr.-szám", "Alkatr.-leírás", "Rend.áll.rakt.készl. ME", "Rend.áll",
               "Visszaigazolt igény", "Nyitott beszerzés", "Biztonsági készlet", "Tárolh.menny."]

    def build(self, rows):
        with (
            patch.object(engine, "_load_stock_headers_and_rows", return_value=(self.headers, rows)),
            patch.object(engine, "load_avg_by_part", return_value={}),
        ):
            return engine.build_order_suggestions(b"")

    def test_special_rows_are_retained_with_reasons_and_zero_default(self):
        result = self.build([
            ("NORMAL", "Normal front", 6, 6, 0, 0, 7, 10),
            ("ENOUGH", "Enough stock", 10, 10, 0, 0, 7, 10),
            ("NFAYU_CUSTOM", "Egyedi f. Custom glass", 0, -2, 2, 0, 0, 0),
            ("NFAY_ZERO", "Egyedi f. zero result", 0, 0, 2, 0, 0, 0),
            ("NFA_ANT_KAF_718x597", "Old Antonia", 0, -2, 2, 0, 0, 0),
            ("OLD", "RÉGI front 700x400", 2, 2, 0, 0, 3, 5),
            ("MATT", "Laura matt front", 0, 0, 0, 0, 7, 10),
            ("SHORT", "Uncovered shortage", 0, -2, 2, 0, 0, 0),
            ("ZERO", "Rounded to zero", 16, 16, 0, 0, 17, 20),
            ("BAD", "Invalid data", 0, "bad", 0, 0, 7, 10),
            ("PENDING", "Awaiting purchase", 0, 10, 5, 15, 7, 10),
        ])
        by_part = {row.part_number: row for row in result.rows}
        self.assertNotIn("ENOUGH", by_part)
        self.assertEqual(by_part["NORMAL"].order_qty, 5)
        for part in ("NFAY_ZERO", "NFA_ANT_KAF_718x597", "OLD", "MATT", "SHORT", "ZERO", "BAD", "PENDING"):
            self.assertNotIn(part, by_part)
        for part in ("NFAYU_CUSTOM",):
            with self.subTest(part=part):
                self.assertTrue(by_part[part].review_reasons)
                self.assertEqual(by_part[part].order_qty, 0)
        workbook = engine.ox.load_workbook(io.BytesIO(result.suggestion_workbook))
        self.assertEqual(workbook["rendeles"].max_row, 2)
        self.assertEqual(workbook["Egyedi döntés"].max_row, 2)

    def test_duplicate_parts_and_descriptions_do_not_disappear(self):
        result = self.build([
            ("NFAY_DUP", "First", 0, -1, 1, 0, 7, 10),
            ("NFAY_DUP", "Second", 0, -2, 2, 0, 7, 10),
            ("SM1", "SM. same", 0, -1, 1, 0, 7, 10),
            ("SM2", "SM. same", 0, -2, 2, 0, 7, 10),
        ])
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len({row.row_id for row in result.rows}), 2)
        self.assertTrue(all(row.part_number == "NFAY_DUP" for row in result.rows))
        self.assertTrue(all(row.review_reasons and row.order_qty == 0 for row in result.rows))

    def test_matt_review_stock_and_demand_conditions(self):
        result = self.build([
            ("DEMAND", "Laura matt demand", 0, 0, 2, 2, 7, 10),
            ("NEGATIVE", "Laura matt negative", -1, -1, 0, 0, 7, 10),
            ("RESERVED", "Laura matt reserved", 2, -1, 3, 0, 7, 10),
            ("EMPTY", "Laura matt empty", 0, 0, 0, 0, 7, 10),
            ("STOCKED", "Laura matt stocked", 2, 1, 1, 0, 7, 10),
            ("SM", "SM. front", 0, -1, 1, 0, 0, 0),
            ("EXCEPTION", "Antónia kasmír matt", 0, -1, 1, 0, 0, 0),
            ("NFAY_CUSTOM", "Custom front", 5, 5, 0, 0, 7, 10),
        ])
        self.assertEqual({row.part_number for row in result.rows},
                         {"NEGATIVE", "RESERVED"})

    def test_custom_fronts_require_uncovered_demand_or_negative_stock(self):
        cases = [
            (5, 5, 0, False), (0, 0, 0, False), (None, None, None, False),
            (5, 5, 2, False), (0, 0, 2, False),
            (1, None, 1, False), (2, 0, 2, False), (1, 0, 2, False),
            (None, None, 2, False),
            (-1, 0, 0, False), (0, -1, 0, True),
        ]
        for stock, current, demand, expected in cases:
            with self.subTest(stock=stock, current=current, demand=demand):
                source = ("NFAY_CUSTOM", "Egyedi f. front", stock, current, demand, 0, 0, 0)
                self.assertEqual(bool(self.build([source]).rows), expected)
                saved_row = jobs._nettfront_order_row_from_dict({
                    "part_number": source[0], "description": source[1],
                    "stock_unit": stock, "current_stock": current, "confirmed_demand": demand,
                    "review_reasons": ["Egyedi ajtófront"],
                    "suggested_qty": engine.calculate_order_qty(current or 0, 0, source[1], 0),
                })
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder)
                    jobs._write_nettfront_order_rows(path, [saved_row])
                    self.assertEqual(bool(jobs._read_nettfront_order_rows(path)), expected)

    def test_blendes_are_excluded_from_new_and_saved_review_rows(self):
        for stock in (0, -2):
            row = engine.NettfrontOrderRow(
                row_id="blende", confirmed_demand=2, open_procurement=0,
                safe_stock=0, capacity=0, order_qty=0, color="Beige", length=125, width=796,
                part_number="NFAYB_ZI_BGF_125X796_KA_NO_U",
                description="Blende (mellvéd) f. Zille Beige fóliás 125x796x18",
                current_stock=stock, stock_unit=stock,
                review_reasons=["Egyedi ajtófront"],
            )
            self.assertFalse(engine.is_requested_review_row(row))
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)
                jobs._write_nettfront_order_rows(path, [row])
                self.assertEqual(jobs._read_nettfront_order_rows(path), [])
            self.assertEqual(self.build([
                (row.part_number, row.description, stock, stock, 2, 0, 0, 0),
            ]).rows, [])

    def test_approval_includes_only_manually_entered_review_quantities(self):
        result = self.build([
            ("NORMAL", "Normal front", 6, 6, 0, 0, 7, 10),
            ("NFAY_CUSTOM", "Egyedi f. front", 0, -2, 2, 0, 0, 0),
            ("OLD", "Egyedi f. régi front", 0, -1, 1, 1, 0, 0),
        ])
        normal, custom, old = result.rows
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            jobs._write_nettfront_order_rows(path, result.rows)
            with (
                patch.object(operations, "read_order_job", return_value=(path, {})),
                patch.object(operations, "render_nettfront_order_result", return_value=b"ok"),
            ):
                status, _ = operations.approve_order_job("test", {f"qty__{custom.row_id}": "2"})
            self.assertEqual(status, 200)
            saved = jobs._read_nettfront_order_rows(path)
            self.assertEqual([row.order_qty for row in saved], [5, 2, 0])
            self.assertEqual(saved[1].review_reasons, custom.review_reasons)
            exported = (path / "rendeles_sima.csv").read_text(encoding="utf-8-sig")
            self.assertIn("NFAY_CUSTOM;2", exported)
            self.assertNotIn("OLD;", exported)
            approved = engine.ox.load_workbook(path / "rendeles-jovahagyott.xlsx")
            self.assertEqual(approved.active.max_row, 3)

    def test_old_saved_rows_remain_compatible_and_invalid_quantities_fail(self):
        row = jobs._nettfront_order_row_from_dict({"part_number": "OLD_JOB", "order_qty": 5})
        self.assertEqual(row.review_reasons, [])
        self.assertEqual(row.order_qty, 5)
        for value in ("nan", "inf", "-inf"):
            self.assertFalse(jobs._order_parse_quantity_input(value)[1])

    def test_missing_identity_cannot_be_exported_and_review_only_page_renders(self):
        result = self.build([(None, "Egyedi f. front", 0, -2, 2, 0, 0, 0)])
        row = result.rows[0]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            jobs._write_nettfront_order_rows(path, result.rows)
            with (
                patch.object(operations, "read_order_job", return_value=(path, {})),
                patch.object(operations, "render_nettfront_order_result", return_value=b"error"),
                patch.object(operations, "_persist_nettfront_order_approval") as persist,
            ):
                status, _ = operations.approve_order_job("test", {f"qty__{row.row_id}": "2"})
            self.assertEqual(status, 400)
            persist.assert_not_called()
            with (
                patch.object(pages, "read_order_job", return_value=(path, {})),
                patch.object(pages, "get_procurement_helper_state", return_value={"running": False}),
                patch.object(pages, "render_layout", side_effect=lambda **kwargs: kwargs["content_html"].encode()),
            ):
                page = pages.render_nettfront_order_result("test", {}).decode()
            self.assertIn('class="order-review-divider"', page)
            self.assertEqual(page.count('<table '), 1)
            self.assertNotIn('order-review-reason', page)
            self.assertNotIn('order-review-facts', page)
            self.assertNotIn('order-review-search', page)
            self.assertIn(f'name="qty__{row.row_id}"', page)
            self.assertIn("Egyedi döntést igénylő frontok", page)
            self.assertEqual(page.count('<form '), 1)


if __name__ == "__main__":
    unittest.main()
