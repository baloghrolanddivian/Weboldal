"""Verify assembly component reports and their manufacturing replacement queue."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from manufacturing.assembly_damage import complete_damage_report, damaged_bom_indexes, damage_special_view, pending_damage_reports, record_bom_damage
from manufacturing.base.config import configure_manufacturing, runtime_dir
from manufacturing.base.workflow import _manufacturing_view_bundle, manufacturing_module_payload

from .damage import report_bom_damage
from .production_xml import empty_xml_metadata
from .store import register_scan


class AssemblyDamageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous_root = runtime_dir()
        configure_manufacturing(self.root)
        self.addCleanup(configure_manufacturing, previous_root)
        self.row = {"part_number": "COMPONENT-1", "description": "Oldallap", "quantity": 0.055}
        self.lookup_result = {"production_number": "14545", "scan": {"scan": "CON1396379"}, "bom": [self.row]}
        lookup_patch = patch("part_workstation.damage.lookup_scan", return_value=self.lookup_result)
        self.lookup = lookup_patch.start()
        self.addCleanup(lookup_patch.stop)

    def payload(self, **overrides) -> dict:
        return {"barcode": "RAW-SCAN", "production_number": "14545", "bom_index": 0,
                "bom_row": dict(self.row), "request_id": str(uuid.uuid4()), **overrides}

    def report(self, payload=None) -> dict:
        return report_bom_damage(payload or self.payload(), reported_by="Assembly operator")

    def test_report_is_verified_and_persisted_with_component_and_parent_identity(self) -> None:
        report = self.report()
        self.lookup.assert_called_once_with("RAW-SCAN")
        self.assertEqual(report["barcode"], "CON1396379")
        self.assertEqual(report["item"], {"part_number": "COMPONENT-1", "description": "Oldallap", "quantity": "0.055"})
        self.assertEqual(pending_damage_reports(), [report])
        self.assertEqual(json.loads((self.root / "assembly-damaged.json").read_text(encoding="utf-8"))["reports"][report["id"]], report)
        row = damage_special_view()["sections"][0]["rows"][0]
        self.assertEqual(row["part_number"], "COMPONENT-1")
        self.assertEqual(row["code"], "CON1396379")
        self.assertEqual(row["quantity"], "0.055")
        self.assertEqual(row["doc_key"], "osszekeszito")

    def test_stale_or_modified_bom_is_rejected(self) -> None:
        for payload in (self.payload(production_number="999"), self.payload(bom_index=4),
                        self.payload(bom_row={**self.row, "part_number": "OTHER"}), self.payload(bom_row={**self.row, "quantity": 5})):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.report(payload)
        self.assertEqual(pending_damage_reports(), [])
        self.assertFalse((self.root / "assembly-damaged.json").exists())

    def test_duplicate_and_concurrent_reports_create_one_open_request(self) -> None:
        payload = self.payload()
        first = self.report(payload)
        self.assertEqual(self.report(payload)["id"], first["id"])
        with ThreadPoolExecutor(max_workers=4) as executor:
            reports = list(executor.map(lambda _: self.report(), range(8)))
        self.assertTrue(all(report["id"] == first["id"] for report in reports))
        self.assertEqual(len(pending_damage_reports()), 1)

    def test_prepared_report_leaves_pending_queue_and_can_be_reported_again(self) -> None:
        payload = self.payload()
        first = self.report(payload)
        second_operator_payload = self.payload()
        self.assertEqual(self.report(second_operator_payload)["id"], first["id"])
        completed = complete_damage_report(first["id"], completed_by="Preparer")
        self.assertEqual(completed["status"], "prepared")
        self.assertEqual(completed["completed_by"], "Preparer")
        self.assertEqual(damage_special_view()["count"], 0)
        self.assertEqual(self.report(payload)["id"], first["id"])
        self.assertEqual(self.report(payload)["status"], "prepared")
        self.assertEqual(self.report(second_operator_payload)["status"], "prepared")
        self.assertNotEqual(self.report()["id"], first["id"])
        self.assertEqual(len(pending_damage_reports()), 1)

    def test_rescan_marks_only_matching_open_bom_lines(self) -> None:
        first = self.report()
        self.assertEqual(damaged_bom_indexes("14545", "CON1396379", [self.row]), [0])
        self.assertEqual(damaged_bom_indexes("14546", "CON1396379", [self.row]), [])
        self.assertEqual(damaged_bom_indexes("14545", "CON13963790", [self.row]), [])
        self.assertEqual(damaged_bom_indexes("14545", "CON1396379", [{**self.row, "part_number": "OTHER"}]), [])
        with patch("part_workstation.store.lookup_scan", return_value=self.lookup_result), patch("part_workstation.store.lookup_xml_item", return_value=empty_xml_metadata()):
            state = register_scan("RAW-SCAN")
            self.assertEqual(state["production_number"], "14545")
            self.assertEqual(state["damaged_bom_indexes"], [0])
            complete_damage_report(first["id"], completed_by="Preparer")
            self.assertEqual(register_scan("RAW-SCAN")["damaged_bom_indexes"], [])

    def test_completion_is_saved_in_runtime_json_for_only_the_selected_row(self) -> None:
        first = self.report()
        second = record_bom_damage("14545", "CON1396379", 1, self.row, request_id=str(uuid.uuid4()), reported_by="Assembly operator")
        complete_damage_report(first["id"], completed_by="Preparer")
        saved = json.loads((self.root / "assembly-damaged.json").read_text(encoding="utf-8"))["reports"]
        self.assertEqual(saved[first["id"]]["status"], "prepared")
        self.assertEqual(saved[first["id"]]["completed_by"], "Preparer")
        self.assertTrue(saved[first["id"]]["completed_at"])
        self.assertEqual(saved[second["id"]]["status"], "open")
        self.assertNotIn("completed_at", saved[second["id"]])
        self.assertEqual([report["id"] for report in pending_damage_reports()], [second["id"]])

    def test_queue_groups_all_productions_and_is_next_to_red_view(self) -> None:
        self.report()
        record_bom_damage("14546", "CON2000000", 0, self.row, request_id=str(uuid.uuid4()), reported_by="Other operator")
        view = damage_special_view()
        self.assertEqual(view["count"], 2)
        self.assertEqual(len(view["sections"]), 2)
        self.assertTrue(view["excludeFromCompletion"])
        bundle, _ = _manufacturing_view_bundle({"folder": str(self.root / "no-xml"), "documents": []}, "14545", {}, operation_filter="korpusz_osszekeszites")
        views = bundle["documents"][0]["specialViews"]
        keys = [item["key"] for item in views]
        self.assertEqual(keys[keys.index("all-productions-red") + 1], "assembly-damaged")
        self.assertEqual(views[-1]["count"], 2)

    def test_queue_remains_accessible_without_production_xml(self) -> None:
        self.report()
        with patch("manufacturing.base.workflow.available_production_entries", return_value=[]):
            payload = manufacturing_module_payload(operation="korpusz_osszekeszites", include_client_cache=False)
        document = payload["bundle"]["documents"][0]
        self.assertEqual(document["key"], "korpusz_osszekeszites")
        self.assertEqual(document["specialViews"][-1]["key"], "assembly-damaged")
        self.assertEqual(document["specialViews"][-1]["count"], 1)

    def test_invalid_report_and_unknown_completion_do_not_change_queue(self) -> None:
        for payload in (self.payload(bom_index=True), self.payload(barcode=""), self.payload(bom_row={**self.row, "quantity": "NaN"}), self.payload(request_id="invalid")):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.report(payload)
        with self.assertRaises(ValueError):
            complete_damage_report("missing", completed_by="Preparer")
        self.assertEqual(pending_damage_reports(), [])


if __name__ == "__main__":
    unittest.main()
