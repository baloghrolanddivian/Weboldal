"""Tests for the scanned-part workstation."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from .lookup import lookup_bom
from .page import render_page
from .store import configure_part_workstation, load_user_state, register_scan, reset_user_state


class PartWorkstationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        configure_part_workstation(Path(self.temp_dir.name))
        lookup_patch = patch("part_workstation.store.lookup_bom", return_value=[])
        self.lookup = lookup_patch.start()
        self.addCleanup(lookup_patch.stop)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scans_are_isolated_by_user(self) -> None:
        register_scan("worker-a", "ABC-123")
        register_scan("worker-b", "XYZ-987")
        self.assertEqual(load_user_state("worker-a")["barcode"], "ABC-123")
        self.assertEqual(load_user_state("worker-b")["barcode"], "XYZ-987")

    def test_reset_only_clears_requested_user(self) -> None:
        register_scan("worker-a", "A")
        register_scan("worker-b", "B")
        reset_user_state("worker-a")
        self.assertEqual(load_user_state("worker-a")["lookup_status"], "waiting_for_scan")
        self.assertEqual(load_user_state("worker-b")["barcode"], "B")

    def test_rejects_empty_barcode(self) -> None:
        with self.assertRaises(ValueError):
            register_scan("worker-a", " \n ")
        self.lookup.assert_not_called()

    def test_persists_entire_bom_including_zero_and_fractional_quantities(self) -> None:
        rows = [
            {"part_number": "PART", "description": "Alkatrész", "quantity": qty}
            for qty in [0, 0.055, *range(110)]
        ]
        self.lookup.return_value = rows
        state = register_scan("worker-a", " CON1396379\r\n")
        self.lookup.assert_called_once_with("CON1396379")
        self.assertEqual(state["lookup_status"], "ready")
        self.assertEqual(load_user_state("worker-a")["bom"], rows)

    def test_lookup_failure_clears_previous_bom_and_preserves_other_user(self) -> None:
        self.lookup.return_value = [{"part_number": "OLD", "quantity": 2}]
        register_scan("worker-a", "A")
        register_scan("worker-b", "B")
        self.lookup.side_effect = TimeoutError("Shopfloor timeout")
        with self.assertRaisesRegex(RuntimeError, "Shopfloor timeout"):
            register_scan("worker-a", "NEW")
        state = load_user_state("worker-a")
        self.assertEqual(state["barcode"], "NEW")
        self.assertEqual(state["lookup_status"], "error")
        self.assertEqual(state["bom"], [])
        self.assertEqual(state["error_message"], "Shopfloor timeout")
        self.assertEqual(load_user_state("worker-b")["bom"], self.lookup.return_value)

    def test_page_contains_three_regions_and_escaped_user(self) -> None:
        body = render_page(load_user_state("worker-a"), "Teszt <Felhasználó>").decode("utf-8")
        self.assertIn("3D elemnézet", body)
        self.assertIn("Beolvasott elem adatai", body)
        self.assertIn("Darabjegyzék", body)
        self.assertIn("Teszt &lt;Felhasználó&gt;", body)


class PartWorkstationLookupTests(unittest.TestCase):
    scan = {
        "message": "Üzenet", "messageType": 2,
        "instruction": "Darablista megjelenítés", "scan_Num": 1396379,
        "scan": "CON1396379", "conId": 11, "olnId": 1207826, "olnIdInstance": 1,
    }

    @staticmethod
    def response(rows: list, **overrides) -> tuple[int, str]:
        return 200, json.dumps({"array": {"data": rows}, "returnValue": 0, **overrides})

    def test_authenticated_workflow_uses_one_connection_and_original_scan_context(self) -> None:
        from tools.shopfloor import SHOPFLOOR_BASE_URL, ShopfloorApiClient

        rows = [
            {"itmItemNumber": "BC_FGBOXR", "itmDescription": "Takaró", "qty": qty}
            for qty in (0, 0.055, 4)
        ]
        calls = []

        def post(client, url, payload, **kwargs):
            calls.append((client, url, dict(payload)))
            return [self.response([self.scan]), self.response([{"olnId": 999}]), self.response(rows)][len(calls) - 1]

        with patch("tools.shopfloor._shopfloor_negotiate_connection_id", return_value="fresh/connection+") as negotiate:
            with patch.object(ShopfloorApiClient, "post_json_url", autospec=True, side_effect=post):
                result = lookup_bom("RAW-SCAN")

        auth_header = negotiate.call_args.args[0]
        username = base64.b64decode(auth_header.split()[1]).decode().split(":", 1)[0]
        self.assertEqual(username, "alkatresz")
        negotiate.assert_called_once()
        context = {**self.scan, "cptId": 140, "venId": None}
        for (client, url, payload), procedure, expected_payload in zip(
            calls, (1, 3, 2), ({"scan": "RAW-SCAN", "cptId": 140, "venId": None}, context, context)
        ):
            self.assertIs(client, calls[0][0])
            self.assertEqual(client.auth_header, auth_header)
            self.assertEqual(url, f"{SHOPFLOOR_BASE_URL}/api/shopfloor/checkpoints/140/tabs/237/runprocedure/{procedure}?connectionId=fresh%2Fconnection%2B")
            self.assertEqual(payload, expected_payload)
        self.assertEqual(result, [
            {"part_number": row["itmItemNumber"], "description": row["itmDescription"], "quantity": row["qty"]}
            for row in rows
        ])

    def test_failures_stop_the_workflow(self) -> None:
        failures = [
            (500, "Server error"),
            (200, "not json"),
            self.response([], returnValue=1),
            (200, json.dumps({"severity": 16, "message": "Ismeretlen vonalkód"})),
            self.response([None]),
            (200, json.dumps({"returnValue": 0, "array": {}})),
        ]
        for failure in failures:
            for stage in range(3):
                with self.subTest(failure=failure, stage=stage):
                    client = Mock()
                    client.run_procedure.side_effect = [self.response([self.scan])] * stage + [failure]
                    with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                        with self.assertRaises(RuntimeError):
                            lookup_bom("CON1396379")
                    self.assertEqual(client.run_procedure.call_count, stage + 1)

    def test_scan_must_supply_complete_context_before_followup(self) -> None:
        for rows in ([], [{"scan": "CON1396379"}]):
            with self.subTest(rows=rows):
                client = Mock()
                client.run_procedure.return_value = self.response(rows)
                with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                    with self.assertRaises(RuntimeError):
                        lookup_bom("CON1396379")
                client.run_procedure.assert_called_once()

    def test_empty_bom_is_a_successful_lookup(self) -> None:
        client = Mock()
        client.run_procedure.side_effect = [self.response([self.scan]), self.response([]), self.response([])]
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            self.assertEqual(lookup_bom("CON1396379"), [])


if __name__ == "__main__":
    unittest.main()
