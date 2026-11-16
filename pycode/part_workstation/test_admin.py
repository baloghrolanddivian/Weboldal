"""Protect source XML edits, item identity, and administrator access."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from .admin_page import render_admin_page
from .admin_store import ProductionConflict, load_production_notes, save_production_notes
from .page import ADMIN_ACCESS_USER_IDS, ADMIN_DATA_ROUTE, ADMIN_ROUTE, ADMIN_SAVE_ROUTE, ACCESS_USER_IDS, ROUTE, render_page
from .page import DAMAGE_ROUTE
from manufacturing.routes import MANUFACTURING_DAMAGE_ROUTE, MANUFACTURING_DAMAGE_COMPLETE_ROUTE
from .production_xml import XML_FILENAME, lookup_xml_item
from .store import empty_state
from .test_production_xml import SAMPLE_XML
from tools.http import normalize_path


class ProductionNotesTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder = self.root / "14545"
        folder.mkdir()
        self.path = folder / XML_FILENAME
        self.path.write_text(SAMPLE_XML, encoding="utf-8")
        folder_patch = patch("part_workstation.production_xml.production_folder", side_effect=lambda number: self.root / number)
        folder_patch.start()
        self.addCleanup(folder_patch.stop)

    def save(self, changes: list) -> dict:
        state = load_production_notes("14545")
        return save_production_notes("14545", state["revision"], changes)

    def test_lists_all_items_including_blank_notes_and_duplicate_con_ids(self) -> None:
        state = load_production_notes("14545")
        self.assertEqual(len(state["items"]), 3)
        self.assertEqual([item["con_id"] for item in state["items"]], ["CON1396379", "CON1396379", "CON13963790"])
        self.assertEqual([item["row_id"] for item in state["items"]], ["0", "1", "2"])
        self.assertEqual(state["items"][1]["part_number"], "AF40")
        self.assertTrue(all(item["notes"] == "" for item in state["items"]))

    def test_creates_missing_note_fields_in_original_file_and_scanner_reads_them(self) -> None:
        before = ET.fromstring(self.path.read_bytes())
        state = self.save([{"row_id": "1", "notes": "Egyedi <szerelés> & ellenőrzés\nMásodik sor"}])
        after = ET.fromstring(self.path.read_bytes())
        self.assertEqual(ET.tostring(before[0]), ET.tostring(after[0]))
        self.assertEqual(ET.tostring(before[2]), ET.tostring(after[2]))
        self.assertEqual(after[1].findtext("ertek01"), "Laura")
        self.assertEqual(after[1].findtext("FeatureBillTranslation03"), "Megjegyzés")
        self.assertEqual(state["items"][1]["notes"], "Egyedi <szerelés> & ellenőrzés\nMásodik sor")
        scanner = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.assertEqual(scanner["features"]["Megjegyzés"], state["items"][1]["notes"])
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_updates_and_clears_all_existing_note_representations(self) -> None:
        note_fields = """<Megjegyzes>Direct note</Megjegyzes><Megjegyzés>Accented note</Megjegyzés>
          <FeatureBillTranslation33>Megjegyzés</FeatureBillTranslation33><OptionValue33>Option note</OptionValue33>
          <OptionDescription33>Fallback note</OptionDescription33>"""
        self.path.write_text(SAMPLE_XML.replace("<pdCode>AF40</pdCode>", "<pdCode>AF40</pdCode>" + note_fields), encoding="utf-8")
        self.assertEqual(load_production_notes("14545")["items"][1]["notes"], "Option note")
        self.save([{"row_id": "1", "notes": "Updated"}])
        record = ET.parse(self.path).getroot()[1]
        for tag in ("Megjegyzes", "Megjegyzés", "ertek33", "OptionValue33", "OptionDescription33"):
            self.assertEqual(record.findtext(tag), "Updated")
        state = self.save([{"row_id": "1", "notes": ""}])
        self.assertEqual(state["items"][1]["notes"], "")
        scanner = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.assertEqual(scanner["features"]["Megjegyzés"], "")
        self.assertEqual(scanner["fields"]["Megjegyzes"], "")

    def test_namespace_comments_and_non_note_fields_survive(self) -> None:
        source = SAMPLE_XML.replace("<EtikettKitchen_korp_tip>", '<EtikettKitchen_korp_tip xmlns="urn:production"><!--preserve comment--><?label keep?>')
        self.path.write_bytes(source.replace('encoding="utf-8"', 'encoding="utf-16"').encode("utf-16"))
        self.save([{"row_id": "1", "notes": "Árvíztűrő tükörfúrógép"}])
        saved = self.path.read_bytes().decode("utf-16")
        self.assertIn("<!--preserve comment-->", saved)
        self.assertIn("<?label keep?>", saved)
        self.assertIn('encoding="utf-16"', saved)
        root = ET.fromstring(self.path.read_bytes())
        self.assertEqual(root[1].findtext("{urn:production}pdCode"), "AF40")
        self.assertEqual(root[1].findtext("{urn:production}ertek03"), "Árvíztűrő tükörfúrógép")
        self.assertEqual(lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)["features"]["Megjegyzés"], "Árvíztűrő tükörfúrógép")

    def test_stale_editor_cannot_overwrite_another_save(self) -> None:
        state = load_production_notes("14545")
        self.save([{"row_id": "0", "notes": "First editor"}])
        source = self.path.read_bytes()
        with self.assertRaises(ProductionConflict):
            save_production_notes("14545", state["revision"], [{"row_id": "1", "notes": "Stale editor"}])
        self.assertEqual(self.path.read_bytes(), source)

    def test_invalid_batch_never_changes_source(self) -> None:
        state = load_production_notes("14545")
        source = self.path.read_bytes()
        for changes in (None, [], [{}], [{"row_id": "0", "notes": "x"}, {"row_id": "9", "notes": "y"}],
                        [{"row_id": "0", "notes": "x"}, {"row_id": "0", "notes": "y"}],
                        [{"row_id": "0", "notes": "x" * 501}], [{"row_id": "0", "notes": "bad\x00value"}]):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                save_production_notes("14545", state["revision"], changes)
            self.assertEqual(self.path.read_bytes(), source)

    def test_failed_replace_preserves_source_and_removes_temporary_file(self) -> None:
        source = self.path.read_bytes()
        with patch("part_workstation.admin_store.os.replace", side_effect=PermissionError("Read-only share")):
            with self.assertRaises(PermissionError):
                self.save([{"row_id": "1", "notes": "Cannot save"}])
        self.assertEqual(self.path.read_bytes(), source)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_production_ids_and_malformed_xml_are_not_written(self) -> None:
        for number in ("", "0", "-1", "../14545", "14545/../14546", True, "1" * 21):
            with self.subTest(number=number), self.assertRaises(ValueError):
                load_production_notes(number)
        with self.assertRaises(FileNotFoundError):
            load_production_notes("999")
        self.path.write_bytes(b"<broken")
        with self.assertRaises(ValueError):
            load_production_notes("14545")


class AdminAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Exercise the real router functions without importing the application's
        # startup side effects (login database and unrelated module configuration).
        source = Path(__file__).resolve().parents[2] / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        routes = next(node.value for node in tree.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "AUTH_ROUTE_RULES")
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"_route_matches", "_can_access_path", "_normalize_path"}]
        handlers = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "InvoiceHandler")
        handler = ast.ClassDef(name="InvoiceHandler", bases=[], keywords=[], body=[node for node in handlers.body if isinstance(node, ast.FunctionDef) and node.name in {"do_GET", "do_POST", "reject_unauthorized_module"}], decorator_list=[])
        namespace = {"AuthUser": object, "PART_WORKSTATION_ROUTE": ROUTE, "PART_WORKSTATION_ACCESS_USER_IDS": ACCESS_USER_IDS,
                     "PART_WORKSTATION_ADMIN_ROUTE": ADMIN_ROUTE, "PART_WORKSTATION_ADMIN_ACCESS_USER_IDS": ADMIN_ACCESS_USER_IDS,
                     "PART_WORKSTATION_ADMIN_DATA_ROUTE": ADMIN_DATA_ROUTE, "PART_WORKSTATION_ADMIN_SAVE_ROUTE": ADMIN_SAVE_ROUTE,
                     "PART_WORKSTATION_DAMAGE_ROUTE": DAMAGE_ROUTE,
                     "MANUFACTURING_DAMAGE_ROUTE": MANUFACTURING_DAMAGE_ROUTE, "STANDARD_ACCESS_USER_IDS": frozenset({"manufacturer", "gyartas-vezerlo"}),
                     "_normalize_path": normalize_path, "_ThemedResponseWriter": lambda writer, user: writer,
                     "DEV_RELOAD_ROUTE": "/__dev__/events", "LOGIN_ROUTE": "/login"}
        pairs = [pair for pair in routes.elts if isinstance(pair.elts[0], ast.Name) and (pair.elts[0].id.startswith("PART_WORKSTATION") or pair.elts[0].id == "MANUFACTURING_DAMAGE_ROUTE")]
        namespace["AUTH_ROUTE_RULES"] = eval(compile(ast.fix_missing_locations(ast.Expression(ast.Tuple(elts=pairs, ctx=ast.Load()))), str(source), "eval"), namespace)
        exec(compile(ast.fix_missing_locations(ast.Module(body=functions + [handler], type_ignores=[])), str(source), "exec"), namespace)
        cls.router = namespace

    def test_only_controller_and_admin_can_access_admin_routes(self) -> None:
        for user_id, is_admin, allowed in (("manufacturer", False, False), ("hriroda", False, False), ("gyartas-vezerlo", False, True), ("admin", True, True)):
            user = SimpleNamespace(user_id=user_id, is_admin=is_admin)
            for path in (ADMIN_ROUTE, ADMIN_DATA_ROUTE, ADMIN_SAVE_ROUTE):
                with self.subTest(user=user_id, path=path):
                    self.assertEqual(self.router["_can_access_path"](user, path), allowed)

    def test_button_is_shown_only_when_authorized(self) -> None:
        self.assertNotIn(f'href="{ADMIN_ROUTE}"', render_page(empty_state(), "Worker").decode())
        self.assertIn(f'href="{ADMIN_ROUTE}"', render_page(empty_state(), "Controller", show_admin=True).decode())
        page = render_admin_page("Admin <test>").decode()
        self.assertIn("Admin &lt;test&gt;", page)
        self.assertLess(page.index('>CONID</th>'), page.index('>Cikkszám</th>'))
        self.assertLess(page.index('>Cikkszám</th>'), page.index('>Megjegyzés</th>'))

    def test_damage_reporting_and_preparation_have_separate_access(self) -> None:
        for user_id, is_admin, report_allowed, prepare_allowed in (("manufacturer", False, True, True), ("hriroda", False, True, False), ("gyartas-vezerlo", False, True, True), ("admin", True, True, True)):
            user = SimpleNamespace(user_id=user_id, is_admin=is_admin)
            with self.subTest(user=user_id):
                self.assertEqual(self.router["_can_access_path"](user, DAMAGE_ROUTE), report_allowed)
                self.assertEqual(self.router["_can_access_path"](user, MANUFACTURING_DAMAGE_ROUTE), prepare_allowed)
                self.assertEqual(self.router["_can_access_path"](user, MANUFACTURING_DAMAGE_COMPLETE_ROUTE), prepare_allowed)

    def test_direct_admin_requests_are_rejected_before_reading_or_writing(self) -> None:
        for user_id in ("manufacturer", "hriroda"):
            for method, path in (("do_GET", ADMIN_ROUTE), ("do_GET", ADMIN_DATA_ROUTE + "?production_id=14545"), ("do_POST", ADMIN_SAVE_ROUTE)):
                with self.subTest(user=user_id, method=method, path=path):
                    handler = self.router["InvoiceHandler"]()
                    handler.path = path
                    handler.wfile = io.BytesIO()
                    handler.rfile = Mock()
                    handler.current_user = lambda: SimpleNamespace(user_id=user_id, is_admin=False)
                    handler.redirect_to_home = Mock()
                    getattr(handler, method)()
                    handler.redirect_to_home.assert_called_once()
                    handler.rfile.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
