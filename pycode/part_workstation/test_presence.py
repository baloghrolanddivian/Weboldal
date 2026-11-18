"""Concurrent scanner presence and durable production history."""

from concurrent.futures import ThreadPoolExecutor
import ast
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from .admin_store import load_production_notes, mark_item_scanned, save_production_notes, ProductionConflict
from .presence import ScanPresence, register_live_scan, update_presence
from .production_xml import XML_FILENAME, lookup_xml_item
from .test_production_xml import SAMPLE_XML


class ScanPresenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / XML_FILENAME
        self.path.write_text(SAMPLE_XML, encoding="utf-8")
        folder = patch("part_workstation.production_xml.production_folder", return_value=self.path.parent)
        folder.start()
        self.addCleanup(folder.stop)
        self.now = 0
        self.registry = ScanPresence(clock=lambda: self.now)
        self.a = dict(production_id="14545", con_id="CON1396379", oln_id="1207826")
        self.b = dict(production_id="14545", con_id="CON13963790", oln_id="1207826")

    def open(self, session_id, identity, sequence=1):
        session = self.registry.begin(session_id, sequence, "manufacturer", "Worker")
        self.registry.activate(session_id, session, identity)
        return session

    def test_multiple_tabs_and_same_item_remain_independent(self):
        self.open("session-000000001", self.a)
        self.open("session-000000002", self.a)
        self.assertEqual(len(self.registry.snapshot()["active"]), 2)
        self.open("session-000000001", self.b, 2)
        self.assertEqual({item["con_id"] for item in self.registry.snapshot()["active"]}, {self.a["con_id"], self.b["con_id"]})
        self.registry.begin("session-000000002", 2, "manufacturer", "Worker")
        state = self.registry.snapshot()
        self.assertEqual([item["con_id"] for item in state["active"]], [self.b["con_id"]])
        self.assertEqual(len(state["scanned"]), 2)
        self.assertEqual([item["scanned"] for item in load_production_notes("14545")["items"]], [False, True, True])

    def test_late_lookup_cannot_reopen_released_or_newer_session(self):
        pending = self.registry.begin("session-000000001", 1, "manufacturer", "Worker")
        self.open("session-000000001", self.b, 2)
        self.registry.activate("session-000000001", pending, self.a)
        self.assertEqual(self.registry.snapshot()["active"][0]["con_id"], self.b["con_id"])
        with self.assertRaises(ValueError):
            self.registry.begin("session-000000001", 1, "manufacturer", "Worker")
        self.registry.begin("session-000000001", 3, "manufacturer", "Worker")
        self.registry.activate("session-000000001", pending, self.a)
        self.assertFalse(self.registry.snapshot()["active"])

    def test_expiry_heartbeat_and_session_owner(self):
        self.open("session-000000001", self.a)
        self.now = 80
        self.assertFalse(self.registry.heartbeat("session-000000001", 0, "manufacturer"))
        self.assertFalse(self.registry.heartbeat("session-000000001", 1, "other"))
        self.assertTrue(self.registry.heartbeat("session-000000001", 1, "manufacturer"))
        self.now = 160
        self.assertTrue(self.registry.snapshot()["active"])
        self.now = 171
        self.assertFalse(self.registry.snapshot()["active"])
        self.assertTrue(load_production_notes("14545")["items"][1]["scanned"])

    def test_scan_wakes_admin_stream_immediately(self):
        revision = self.registry.snapshot()["revision"]
        with ThreadPoolExecutor() as pool:
            update = pool.submit(self.registry.wait, revision, 3)
            self.open("session-000000001", self.a)
            self.assertEqual(update.result(timeout=2)["active"][0]["con_id"], self.a["con_id"])

    def test_real_http_stream_pushes_scan_and_release(self):
        # Run the actual application stream method without unrelated app startup.
        source = Path(__file__).resolve().parents[2] / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "InvoiceHandler")
        stream = next(node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name == "respond_part_workstation_scans")
        namespace = {"part_workstation_presence": self.registry, "json": json}
        exec(compile(ast.Module(body=[stream], type_ignores=[]), str(source), "exec"), namespace)

        class Handler(BaseHTTPRequestHandler):
            do_GET = namespace["respond_part_workstation_scans"]

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        self.addCleanup(connection.close)
        connection.request("GET", "/events")
        response = connection.getresponse()
        self.addCleanup(response.close)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream; charset=utf-8")

        def event():
            line = response.readline().decode()
            self.assertTrue(line.startswith("data: "))
            self.assertEqual(response.readline(), b"\n")
            return json.loads(line[6:])

        self.assertFalse(event()["active"])
        self.open("session-000000001", self.a)
        self.assertEqual(event()["active"][0]["con_id"], self.a["con_id"])
        self.registry.begin("session-000000001", 2, "manufacturer", "Worker")
        released = event()
        self.assertFalse(released["active"])
        self.assertEqual(released["scanned"][0]["con_id"], self.a["con_id"])

    def test_scan_history_does_not_conflict_with_notes_and_is_idempotent(self):
        editor = load_production_notes("14545")
        mark_item_scanned(**self.a)
        scanned_source = self.path.read_bytes()
        mark_item_scanned(**self.a)
        self.assertEqual(scanned_source, self.path.read_bytes())
        saved = save_production_notes("14545", editor["revision"], [{"row_id":"1", "notes":"Updated while scanning"}])
        self.assertTrue(saved["items"][1]["scanned"])
        self.assertEqual(saved["items"][1]["notes"], "Updated while scanning")
        with self.assertRaises(ProductionConflict):
            save_production_notes("14545", editor["revision"], [{"row_id":"1", "notes":"Old editor"}])

    def test_concurrent_scans_preserve_both_source_records(self):
        with ThreadPoolExecutor() as pool:
            list(pool.map(lambda identity: mark_item_scanned(**identity), [self.a, self.b] * 4))
        self.assertEqual(len(ET.parse(self.path).findall(".//Scanned")), 2)
        with self.assertRaises(ValueError):
            mark_item_scanned("14545", "CON1396379", "wrong")

    def test_namespaced_history_and_original_comments_survive(self):
        self.path.write_text(SAMPLE_XML.replace('<EtikettKitchen_korp_tip>', '<EtikettKitchen_korp_tip xmlns="urn:test"><!--keep-->'), encoding="utf-8")
        mark_item_scanned(**self.a)
        self.assertIn(b"<!--keep-->", self.path.read_bytes())
        self.assertEqual(ET.parse(self.path).find(".//{urn:test}Scanned").text, "true")

    def test_live_scan_and_restore_share_exact_identity(self):
        metadata = lookup_xml_item(self.a["con_id"], production_number="14545", oln_id=self.a["oln_id"])
        with patch("part_workstation.presence.presence", self.registry), patch("part_workstation.presence.register_scan", return_value={"production_xml":metadata}):
            state = register_live_scan(self.a["con_id"], session_id="session-000000001", sequence=1, user_id="manufacturer", user_name="Worker")
            self.assertEqual(state["scan_identity"]["oln_id"], self.a["oln_id"])
            update_presence(dict(action="clear", session_id="session-000000001", sequence=2), user_id="manufacturer", user_name="Worker")
            self.assertFalse(self.registry.snapshot()["active"])
            update_presence(dict(action="open", identity=state["scan_identity"], session_id="session-000000002", sequence=1), user_id="manufacturer", user_name="Worker")
            self.assertEqual(len(self.registry.snapshot()["active"]), 1)
