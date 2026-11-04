"""Reader summaries share invoice counts while keeping diagnostics in history."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from . import store
from .pages import invoice_reader_state, render_invoice, render_reader


class InvoiceReaderTests(unittest.TestCase):
    def setUp(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
