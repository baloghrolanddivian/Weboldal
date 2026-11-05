"""Reader summaries share invoice counts while keeping diagnostics in history."""

from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from . import store
from .pages import invoice_reader_state, render_invoice, render_reader


class InvoiceReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        import app  # Initialize application configuration before isolating invoice storage.

        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_runtime = store._runtime_dir
        store.configure_nettfront_invoice(Path(self.temp_dir.name))
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(store.configure_nettfront_invoice, self.previous_runtime)
        self.code = "NF2026-12345"
        icns = ["10001", "10002", "10003", "10004"]
        self.record = store.create_invoice(
            {
                "invoice_code": self.code,
                "items": [{
                    "batch_id": "batch-a",
                    "kod": "NFA_ANT_FEA",
                    "meret": "716x396",
                    "our_code": "FRONT-1",
                    "our_description": "Front <test>",
                    "expected_qty": 3,
                    "counted_qty": 0,
                    "available_icns": icns,
                }],
                "icn_index": {icn: 0 for icn in icns},
            },
            b"<invoice />",
            "Operator",
            "invoice.xml",
        )

    def test_recent_scans_keep_three_latest_accepted_reads_including_overcount(self) -> None:
        for icn in ("10001", "10002", "10003", "10004"):
            self.record, _ = store.scan_invoice_icn(self.code, icn, 1, "Operator")
        self.record, failure = store.scan_invoice_icn(self.code, "10004", 1, "Operator")
        state = invoice_reader_state(self.record)
        self.assertEqual(self.record["scan_history"][-2]["result"], "warning")
        self.assertEqual(state["recent_scans"].count("<tr>"), 3)
        self.assertEqual(re.findall(r"<td>(1000\d)</td>", state["recent_scans"]), ["10004", "10003", "10002"])
        self.assertIn("Antónia", state["recent_scans"])
        self.assertIn("Matt Fehér", state["recent_scans"])
        self.assertNotIn(failure["message"], state["recent_scans"])
        self.assertIn("<td>3</td><td>4</td>", state["invoice_items"])
        self.assertIn("Front &lt;test&gt;", state["invoice_items"])
        self.assertEqual(store.load_invoice(self.code)["failed_reads"][-1]["message"], failure["message"])
        self.assertIn(failure["message"], render_invoice(self.record, read_only=True).decode())
        self.assertNotIn(failure["message"], render_reader(self.record).decode())

    def test_reader_and_backlog_use_identical_invoice_rows(self) -> None:
        self.record, _ = store.scan_invoice_icn(self.code, "10001", 2, "Operator")
        reader = render_reader(self.record).decode()
        backlog = render_invoice(self.record, read_only=True).decode()
        pattern = r'<tbody id="invoice-items">(.*?)</tbody>'
        self.assertEqual(re.search(pattern, reader).group(1), re.search(pattern, backlog).group(1))
        self.assertEqual(re.search(pattern, reader).group(1), invoice_reader_state(self.record)["invoice_items"])
        self.assertNotIn("Teljes beolvasási előzmény", reader)

    def test_empty_history_and_invoice_have_table_placeholders(self) -> None:
        state = invoice_reader_state({})
        self.assertIn('colspan="6"', state["recent_scans"])
        self.assertIn('colspan="10"', state["invoice_items"])
        self.assertNotIn("<script", state["recent_scans"])

    def test_recent_scan_fields_are_escaped(self) -> None:
        self.record["scan_history"] = [{
            "time": "<script>alert(1)</script>",
            "icn": "10001",
            "quantity": "<b>2</b>",
            "result": "success",
            "message": "diagnostic should stay in the log",
        }]
        state = invoice_reader_state(self.record)
        self.assertIn("&lt;script&gt;", state["recent_scans"])
        self.assertIn("&lt;b&gt;2&lt;/b&gt;", state["recent_scans"])
        self.assertNotIn("<script>", state["recent_scans"])
        self.assertNotIn("diagnostic should stay in the log", state["recent_scans"])

    def post_scan(self, payload: object, *, form: bool = False, camera_icn: str | None = None) -> Mock:
        import app

        body = payload.encode() if form else json.dumps(payload).encode()
        handler = Mock()
        source = "camera" if camera_icn is not None else "scan"
        handler.path = f"/apps/nettfront-szamla/{source}/{self.code}"
        handler.headers = {
            "Content-Type": "application/x-www-form-urlencoded" if form else "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.current_user.return_value = None
        handler.reject_unauthorized_module.return_value = False
        with patch.object(
            app, "trigger_camera_read",
            return_value={"icn": camera_icn, "raw": camera_icn},
            side_effect=None if camera_icn is not None else AssertionError("Direct scans must not trigger the camera"),
        ) as camera:
            app.InvoiceHandler.do_POST(handler)
            if camera_icn is not None:
                camera.assert_called_once_with()
        return handler

    def test_keyboard_scan_returns_camera_equivalent_feedback_and_persists_quantity(self) -> None:
        handler = self.post_scan({"operator": "Scanner user", "icn": "10001", "quantity": "2"})
        status, payload = handler.respond_json.call_args.args
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scan"]["result"], "success")
        self.assertEqual(payload["item"]["icn"], "10001")
        self.assertEqual(payload["item"]["quantity"], 2)
        self.assertEqual(payload["item"]["our_code"], "FRONT-1")
        record = store.load_invoice(self.code)
        self.assertEqual(record["items"][0]["counted_qty"], 2)
        self.assertEqual(record["scan_history"][-1]["user"], "Scanner user")
        self.assertEqual(payload["reader_state"], invoice_reader_state(record))

    def test_keyboard_scan_rejects_an_icn_already_read_by_the_camera(self) -> None:
        store.scan_invoice_icn(self.code, "10001", 1, "Camera user")
        handler = self.post_scan({"operator": "Scanner user", "icn": "10001", "quantity": 1})
        status, payload = handler.respond_json.call_args.args
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["scan"]["result"], "failed")
        record = store.load_invoice(self.code)
        self.assertEqual(record["items"][0]["counted_qty"], 1)
        self.assertEqual(record["events"][-1]["details"]["reason"], "duplicate_icn")

    def test_camera_and_keyboard_scans_share_counts_and_item_feedback(self) -> None:
        camera_handler = self.post_scan({"operator": "Camera user", "quantity": "1"}, camera_icn="10001")
        camera_status, camera_payload = camera_handler.respond_json.call_args.args
        self.assertEqual(camera_status, 200)
        self.assertEqual(camera_payload["camera_raw"], "10001")
        keyboard_handler = self.post_scan({"operator": "Scanner user", "icn": "10002", "quantity": "2"})
        keyboard_status, keyboard_payload = keyboard_handler.respond_json.call_args.args
        self.assertEqual(keyboard_status, 200)
        for field in ("model", "color", "size", "our_code", "our_description"):
            self.assertEqual(camera_payload["item"][field], keyboard_payload["item"][field])
        self.assertEqual(store.load_invoice(self.code)["items"][0]["counted_qty"], 3)
        overcount_handler = self.post_scan({"operator": "Scanner user", "icn": "10003", "quantity": "1"})
        status, payload = overcount_handler.respond_json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(payload["scan"]["result"], "warning")
        self.assertEqual(store.load_invoice(self.code)["items"][0]["counted_qty"], 4)

    def test_keyboard_scan_validates_icn_and_quantity(self) -> None:
        for icn, quantity, reason in (("bad", "1", "invalid_icn"), ("99999", "1", "not_in_invoice"), ("10001", "0", "invalid_quantity")):
            with self.subTest(reason=reason):
                handler = self.post_scan({"operator": "Scanner user", "icn": icn, "quantity": quantity})
                status, payload = handler.respond_json.call_args.args
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])
                record = store.load_invoice(self.code)
                self.assertEqual(record["items"][0]["counted_qty"], 0)
                self.assertEqual(record["events"][-1]["details"]["reason"], reason)

    def test_keyboard_scan_requires_operator_and_open_invoice(self) -> None:
        handler = self.post_scan({"icn": "10001"})
        self.assertEqual(handler.respond_json.call_args.args[0], 400)
        store.close_invoice(self.code, "Operator")
        handler = self.post_scan({"operator": "Scanner user", "icn": "10001"})
        self.assertEqual(handler.respond_json.call_args.args[0], 409)
        self.assertEqual(store.load_invoice(self.code)["items"][0]["counted_qty"], 0)

    def test_keyboard_scan_rejects_non_object_json(self) -> None:
        for payload in ([], None, "10001"):
            with self.subTest(payload=payload):
                handler = self.post_scan(payload)
                self.assertEqual(handler.respond_json.call_args.args[0], 400)

    def test_existing_form_scan_still_returns_html(self) -> None:
        handler = self.post_scan("operator=Scanner+user&icn=10001&quantity=2", form=True)
        handler.respond_json.assert_not_called()
        handler.send_response.assert_called_once_with(200)
        self.assertEqual(store.load_invoice(self.code)["items"][0]["counted_qty"], 2)
        self.assertIn(b"<!doctype html>", handler.wfile.getvalue())


if __name__ == "__main__":
    unittest.main()
