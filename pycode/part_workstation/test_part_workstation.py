"""Tests for the scanned-part workstation."""

from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from .lookup import lookup_bom, lookup_scan
from .page import render_page
from .production_xml import empty_xml_metadata
from .store import empty_state, register_scan


class PartWorkstationScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        lookup_patch = patch("part_workstation.store.lookup_scan", return_value={"bom": [], "scan": {}, "production_number": "14545"})
        self.lookup = lookup_patch.start()
        self.addCleanup(lookup_patch.stop)
        xml_patch = patch("part_workstation.store.lookup_xml_item", return_value=empty_xml_metadata())
        self.xml_lookup = xml_patch.start()
        self.addCleanup(xml_patch.stop)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_concurrent_scans_return_independent_request_state(self) -> None:
        barrier = threading.Barrier(2)

        def lookup(barcode):
            barrier.wait(timeout=5)
            return {"bom": [{"part_number": barcode, "quantity": 1}], "scan": {"scan": barcode}, "production_number": "14546"}

        self.lookup.side_effect = lookup
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = list(executor.map(register_scan, ("DEVICE-A", "DEVICE-B")))
        self.assertEqual(first["barcode"], "DEVICE-A")
        self.assertEqual(second["barcode"], "DEVICE-B")
        self.assertEqual(first["bom"][0]["part_number"], "DEVICE-A")
        self.assertEqual(second["bom"][0]["part_number"], "DEVICE-B")
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [])

    def test_fresh_page_state_is_empty_and_does_not_clear_another_scan(self) -> None:
        scanned = register_scan("DEVICE-A")
        fresh = empty_state()
        self.assertEqual(fresh["lookup_status"], "waiting_for_scan")
        self.assertEqual(fresh["barcode"], "")
        self.assertEqual(scanned["barcode"], "DEVICE-A")

    def test_rejects_empty_barcode(self) -> None:
        with self.assertRaises(ValueError):
            register_scan(" \n ")
        self.lookup.assert_not_called()

    def test_returns_entire_bom_including_zero_and_fractional_quantities(self) -> None:
        rows = [
            {"part_number": "PART", "description": "Alkatrész", "quantity": qty}
            for qty in [0, 0.055, *range(110)]
        ]
        self.lookup.return_value["bom"] = rows
        state = register_scan(" CON1396379\r\n")
        self.lookup.assert_called_once_with("CON1396379")
        self.assertEqual(state["lookup_status"], "ready")
        self.assertEqual(state["bom"], rows)

    def test_failed_request_does_not_change_another_request_result(self) -> None:
        self.lookup.return_value["bom"] = [{"part_number": "OLD", "quantity": 2}]
        first = register_scan("A")
        self.lookup.side_effect = TimeoutError("Shopfloor timeout")
        with self.assertRaisesRegex(TimeoutError, "Shopfloor timeout"):
            register_scan("NEW")
        self.assertEqual(first["barcode"], "A")
        self.assertEqual(first["lookup_status"], "ready")
        self.assertEqual(first["bom"], self.lookup.return_value["bom"])

    def test_xml_metadata_uses_api_scan_identity(self) -> None:
        self.lookup.return_value["scan"] = {"scan": "CON1396379", "olnId": 1207826}
        metadata = empty_xml_metadata()
        metadata.update(lookup_status="ready", production_number="14545")
        metadata["fields"].update(Barcode="CON1396379", Korpusztipus="2A", pdCode="AF40", pdvDescription="Alsó 1+2 fiók 40-es")
        metadata["features"]["Front típus"] = "Laura"
        self.xml_lookup.return_value = metadata
        state = register_scan("RAW-SCAN")
        self.xml_lookup.assert_called_once_with("CON1396379", production_number="14545", oln_id=1207826)
        self.assertEqual(state["item"]["part_number"], "AF40")
        self.assertEqual(state["item"]["description"], "Alsó 1+2 fiók 40-es")
        self.assertEqual(state["production_xml"], metadata)

    def test_missing_production_xml_does_not_discard_bom(self) -> None:
        self.lookup.return_value["bom"] = [{"part_number": "PART", "quantity": 2}]
        self.xml_lookup.return_value.update(lookup_status="unavailable", error_message="XML nem található")
        state = register_scan("CON1396379")
        self.assertEqual(state["lookup_status"], "ready")
        self.assertEqual(state["bom"], self.lookup.return_value["bom"])
        self.assertEqual(state["production_xml"]["lookup_status"], "unavailable")

    def test_api3_production_drives_xml_selection_on_each_scan(self) -> None:
        from .production_xml import XML_FILENAME, lookup_xml_item
        from .test_production_xml import SAMPLE_XML

        root = Path(self.temp_dir.name) / "productions"
        for number, code in (("14545", "FIRST"), ("14546", "SECOND")):
            folder = root / number
            folder.mkdir(parents=True)
            (folder / XML_FILENAME).write_text(SAMPLE_XML.replace("<pdCode>AF40</pdCode>", f"<pdCode>{code}</pdCode>"), encoding="utf-8")
        client = Mock()
        client.run_procedure.side_effect = [
            response
            for number in (14545, "14546")
            for response in (
                PartWorkstationLookupTests.response([PartWorkstationLookupTests.scan]),
                PartWorkstationLookupTests.response([{"instruction": "Darablista megjelenítés"}], parameters={"data": {"prdId": number}}),
                PartWorkstationLookupTests.response([]),
            )
        ]
        self.lookup.side_effect = lookup_scan
        self.xml_lookup.side_effect = lookup_xml_item
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            with patch("part_workstation.production_xml.production_folder", side_effect=lambda number: root / number):
                first = register_scan("CON1396379")
                second = register_scan("CON1396379")
        self.assertEqual(first["item"]["part_number"], "FIRST")
        self.assertEqual(first["production_xml"]["production_number"], "14545")
        self.assertEqual(second["item"]["part_number"], "SECOND")
        self.assertEqual(second["production_xml"]["production_number"], "14546")
        self.assertEqual([call.args[2] for call in client.run_procedure.call_args_list], [1, 3, 2, 1, 3, 2])

    def test_page_contains_item_details_and_bom_and_escaped_user(self) -> None:
        body = render_page(empty_state(), "Teszt <Felhasználó>").decode("utf-8")
        self.assertNotIn("3D elemnézet", body)
        self.assertNotIn("modelWidth", body)
        self.assertIn("Beolvasott elem adatai", body)
        self.assertIn("Darabjegyzék", body)
        self.assertIn("Teszt &lt;Felhasználó&gt;", body)

    def test_display_details_use_xml_features_and_convert_dimensions_to_mm(self) -> None:
        metadata = empty_xml_metadata()
        metadata["lookup_status"] = "ready"
        metadata["fields"].update(Korpusztipus="2A", Korp_tip_nev="2-es alsó", Korp_Szin="Antracit kr.")
        metadata["features"].update({
            "J/B": "Jobb", "Nyitási irány": "Bal", "Front színe": "SM.provance fóliás", "Keretléc szín": "Fehér",
            "Front típus": "Laura", "Láb típusa": "Műa. áll.100-as", "Munkalap szín": "Nincs",
            "Hézagtakaró szélessége": "82",
            "Fogantyú furat": "64 / 96",
            "Front szín felső": "Artizán tölgy",
            "Beép.mag.cm": "82.4", "Beép.szél.cm": "40.000000", "Beép.mélys.cm": "60.000000",
        })
        self.xml_lookup.return_value = metadata
        item = register_scan("CON1")["item"]
        self.assertEqual(item["cabinet"], "2A | 2-es alsó")
        self.assertEqual(item["handing"], "Jobb")
        self.assertEqual(item["front"], "SM.provance fóliás | Laura")
        self.assertEqual(item["color"], "Antracit kr.")
        self.assertEqual(item["legs"], "Műa. áll.100-as")
        self.assertEqual(item["worktop"], "Nincs")
        self.assertEqual(item["filler_width"], "82")
        self.assertEqual(item["handle_drilling"], "64 / 96")
        self.assertEqual(item["dimensions"], "824 × 400 × 600 mm")

        metadata["features"].update({"J/B": "", "Front színe": "", "Beép.mag.cm": "82,45", "Hézagtakaró szélessége": "", "Fogantyú furat": ""})
        next_item = register_scan("CON2")["item"]
        self.assertEqual(next_item["front"], "Artizán tölgy | Laura")
        self.assertEqual(next_item["handing"], "Bal")
        self.assertEqual(next_item["filler_width"], "")
        self.assertEqual(next_item["handle_drilling"], "")
        self.assertEqual(next_item["dimensions"], "824.5 × 400 × 600 mm")
        metadata["features"]["Nyitási irány"] = ""
        metadata["features"]["Front szín felső"] = ""
        third_item = register_scan("CON3")["item"]
        self.assertEqual(third_item["handing"], "")
        self.assertEqual(third_item["front"], "Fehér | Laura")

    def test_missing_and_invalid_dimensions_never_become_invented_measurements(self) -> None:
        metadata = empty_xml_metadata()
        metadata["lookup_status"] = "ready"
        metadata["features"].update({"Beép.mag.cm": "Méret", "Beép.szél.cm": "NaN", "Beép.mélys.cm": ""})
        self.xml_lookup.return_value = metadata
        self.assertEqual(register_scan("CON1")["item"]["dimensions"], "")
        metadata["features"]["Beép.mag.cm"] = "0"
        self.assertEqual(register_scan("CON2")["item"]["dimensions"], "0 × — × — mm")


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
            return [self.response([self.scan]), self.response([{"olnId": 999, "prdID": 14546}]), self.response(rows)][len(calls) - 1]

        with patch("tools.shopfloor._shopfloor_negotiate_connection_id", return_value="fresh/connection+") as negotiate:
            with patch.object(ShopfloorApiClient, "post_json_url", autospec=True, side_effect=post):
                result = lookup_scan("RAW-SCAN")

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
        self.assertEqual(result["production_number"], "14546")
        self.assertEqual(result["bom"], [
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
                    prefix = [self.response([self.scan]), self.response([{"prdID": 14546}])]
                    client.run_procedure.side_effect = prefix[:stage] + [failure]
                    with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                        with self.assertRaises(RuntimeError):
                            lookup_bom("CON1396379")
                    self.assertEqual(client.run_procedure.call_count, stage + 1)

    def test_full_api3_example_is_separate_from_api2_bom(self) -> None:
        api3 = json.loads((Path(__file__).parent / "testdata" / "api3_response.json").read_text(encoding="utf-8"))
        scan = {**self.scan, "scan": "CON1416241", "scan_Num": 1416241, "olnId": 1219888}
        bom_row = {"itmItemNumber": "ONLY-API2", "itmDescription": "Darabjegyzék tétel", "qty": 2}
        client = Mock()
        client.run_procedure.side_effect = [
            self.response([scan]),
            (200, json.dumps(api3)),
            self.response([bom_row], parameters={"data": {"prdId": 99999}}),
        ]
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            result = lookup_scan("CON1416241")
        calls = client.run_procedure.call_args_list
        self.assertEqual([call.args[2] for call in calls], [1, 3, 2])
        self.assertTrue(all(call.args[:2] == (140, 237) for call in calls))
        expected_context = {**scan, "cptId": 140, "venId": None}
        self.assertEqual(calls[1].args[3], expected_context)
        self.assertEqual(calls[2].args[3], expected_context)
        self.assertEqual(result["production_number"], "14635")
        self.assertEqual(result["bom"], [{"part_number": "ONLY-API2", "description": "Darabjegyzék tétel", "quantity": 2}])

    def test_api1_production_parameter_is_forwarded_to_api3_and_api2(self) -> None:
        api3 = json.loads((Path(__file__).parent / "testdata" / "api3_response.json").read_text(encoding="utf-8"))
        scan = {**self.scan, "scan": "CON1416241", "scan_Num": 1416241, "olnId": 1219888, "prdId": 14635}

        def run(checkpoint, tab, procedure, payload):
            if procedure == 1:
                return self.response([scan])
            if procedure == 3:
                # The real API returns zero when prdId is missing from its input.
                response = json.loads(json.dumps(api3))
                number = payload.get("prdId", 0)
                response["array"]["data"][0]["prdId"] = number
                response["parameters"]["data"] = dict(payload)
                return 200, json.dumps(response)
            self.assertEqual(payload["prdId"], 14635)
            return self.response([])

        client = Mock()
        client.run_procedure.side_effect = run
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            result = lookup_scan("CON1416241")
        calls = client.run_procedure.call_args_list
        self.assertEqual([call.args[2] for call in calls], [1, 3, 2])
        self.assertEqual(calls[1].args[3]["prdId"], 14635)
        self.assertEqual(calls[2].args[3]["prdId"], 14635)
        self.assertEqual(result["production_number"], "14635")

    def test_scan_must_supply_complete_context_before_followup(self) -> None:
        for rows in ([], [{"scan": "CON1396379"}]):
            with self.subTest(rows=rows):
                client = Mock()
                client.run_procedure.return_value = self.response(rows)
                with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                    with self.assertRaises(RuntimeError):
                        lookup_bom("CON1396379")
                client.run_procedure.assert_called_once()

    def test_api3_production_is_read_from_output_data_with_actual_field_case(self) -> None:
        output = {
            "message": "Darablista megjelenítés OK", "messageType": 2,
            "instruction": "Darablista megjelenítés", "scan_Num": 1416240,
            "scan": "CON1416240", "conId": 11, "olnId": 1219879,
            "olnIdInstance": 1, "prdId": 14635, "cptId": 140, "venId": None,
        }
        scan = {key: output[key] for key in self.scan}
        variants = [
            self.response([{"scan": output["scan"], "olnId": output["olnId"]}], parameters={"data": output}),
            (200, json.dumps({"data": output, "returnValue": 0})),
            self.response([output]),
            self.response([{"prdID": 14545}], parameters={"data": output}),
        ]
        for response in variants:
            with self.subTest(response=response):
                client = Mock()
                client.run_procedure.side_effect = [self.response([scan]), response, self.response([])]
                with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                    result = lookup_scan("CON1416240")
                self.assertEqual(result["production_number"], "14635")
                self.assertEqual(result["scan"]["olnId"], 1219879)
                self.assertEqual([call.args[2] for call in client.run_procedure.call_args_list], [1, 3, 2])

    def test_invalid_output_production_does_not_fall_back_to_a_different_row(self) -> None:
        client = Mock()
        client.run_procedure.side_effect = [
            self.response([self.scan]),
            self.response([{"prdID": 14545}], parameters={"data": {"prdId": None}}),
        ]
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "prdId"):
                lookup_scan("CON1396379")
        self.assertEqual(client.run_procedure.call_count, 2)

    def test_missing_or_invalid_api3_production_stops_before_bom(self) -> None:
        rows_to_reject = [[], [{"prdID": 14545}, {"prdID": 14546}], [{}]]
        rows_to_reject.extend([{"prdID": value}] for value in (None, "", 0, -1, "../14545", 14545.5, True))
        for rows in rows_to_reject:
            with self.subTest(rows=rows):
                client = Mock()
                client.run_procedure.side_effect = [self.response([self.scan]), self.response(rows)]
                with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
                    with self.assertRaisesRegex(RuntimeError, "prdId"):
                        lookup_scan("CON1396379")
                self.assertEqual([call.args[2] for call in client.run_procedure.call_args_list], [1, 3])

    def test_empty_bom_is_a_successful_lookup(self) -> None:
        client = Mock()
        client.run_procedure.side_effect = [self.response([self.scan]), self.response([{"prdID": 14546}]), self.response([])]
        with patch("part_workstation.lookup.ShopfloorApiClient.for_endpoint", return_value=client):
            self.assertEqual(lookup_bom("CON1396379"), [])


if __name__ == "__main__":
    unittest.main()
