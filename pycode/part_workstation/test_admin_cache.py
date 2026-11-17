"""Recent assembly summaries must remain bounded, fresh and safe to edit."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import admin_store
from .admin_store import load_production_notes, load_recent_production_notes, save_production_notes, ProductionConflict
from .production_xml import XML_FILENAME, lookup_xml_item


class RecentProductionCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder_patch = patch("part_workstation.production_xml.production_folder", side_effect=lambda number: self.root / number)
        folder_patch.start()
        self.addCleanup(folder_patch.stop)
        admin_store._NOTE_CACHE.clear()
        self.addCleanup(admin_store._NOTE_CACHE.clear)

    def xml(self, number, order="143810", note=""):
        folder = self.root / str(number)
        folder.mkdir(exist_ok=True)
        path = folder / XML_FILENAME
        path.write_text(f'''<EtikettKitchen_korp_tip><CON><Barcode>CON1</Barcode><olnID>123</olnID>
          <pdCode>EGK</pdCode><ordOrderNo>{order}</ordOrderNo><Megjegyzes>{note}</Megjegyzes>
          </CON></EtikettKitchen_korp_tip>''', encoding="utf-8")
        return path

    def test_latest_twelve_xml_productions_and_start_boundary(self):
        self.xml(14545)
        self.xml(14656)
        for number in range(14657, 14672):
            self.xml(number)
        (self.root / "99999").mkdir()  # A newer folder without this XML is not a production to cache.
        (self.root / "not-a-production").mkdir()
        result = load_recent_production_notes()
        expected = [str(number) for number in range(14671, 14659, -1)]
        self.assertEqual([value["production_id"] for value in result["productions"]], expected)
        self.assertEqual(len(admin_store._NOTE_CACHE), 12)
        self.assertEqual([item["production_id"] for item in result["items"]], expected)
        self.assertTrue(all(item["ordOrderNo"] == "143810" for item in result["items"]))

    def test_fewer_than_twelve_and_no_productions(self):
        self.assertEqual(load_recent_production_notes()["items"], [])
        for number in (14657, 14677, 14681, 14683):
            self.xml(number, order=str(number))
        result = load_recent_production_notes()
        self.assertEqual(len(result["productions"]), 4)
        self.assertEqual(result["productions"][-1]["production_id"], "14657")
        self.assertEqual(result["items"][0]["ordOrderNo"], "14683")

    def test_cache_reuses_unchanged_files_and_reloads_external_changes(self):
        self.xml(14657)
        self.xml(14681)
        with patch.object(admin_store, "_parse", wraps=admin_store._parse) as parse:
            first = load_recent_production_notes()
            self.assertEqual(parse.call_count, 2)
            first["items"][0]["notes"] = "Only the caller changed this"
            self.assertEqual(load_recent_production_notes()["items"][0]["notes"], "")
            self.assertEqual(parse.call_count, 2)
            self.xml(14681, order="9999999", note="An external edit")
            current = load_recent_production_notes()
            self.assertEqual(parse.call_count, 3)
            self.assertEqual(current["items"][0]["notes"], "An external edit")
            self.assertEqual(current["items"][0]["ordOrderNo"], "9999999")
            self.assertNotEqual(first["productions"][0]["revision"], current["productions"][0]["revision"])

    def test_new_production_enters_cache_and_oldest_is_evicted(self):
        for number in range(14657, 14669):
            self.xml(number)
        load_recent_production_notes()
        self.xml(14683)
        result = load_recent_production_notes()
        self.assertEqual(result["productions"][0]["production_id"], "14683")
        self.assertNotIn(self.root / "14657" / XML_FILENAME, admin_store._NOTE_CACHE)
        self.assertEqual(len(admin_store._NOTE_CACHE), 12)

    def test_missing_and_malformed_files_do_not_hide_valid_productions(self):
        self.xml(14657)
        broken = self.xml(14681)
        broken.write_text("<broken", encoding="utf-8")
        result = load_recent_production_notes()
        self.assertEqual(len(result["productions"]), 1)
        self.assertEqual(result["warnings"][0]["production_id"], "14681")
        (self.root / "14657" / XML_FILENAME).unlink()
        self.assertEqual(load_recent_production_notes()["items"], [])
        self.assertFalse(admin_store._NOTE_CACHE)

    def test_manual_old_production_does_not_displace_recent_cache(self):
        self.xml(14657)
        self.xml(14545)
        load_recent_production_notes()
        self.assertEqual(load_production_notes("14545")["production_id"], "14545")
        self.assertEqual({path.parent.name for path in admin_store._NOTE_CACHE}, {"14657"})

    def test_save_invalidates_cache_and_stale_revision_is_still_rejected(self):
        self.xml(14657)
        result = load_recent_production_notes()
        revision = result["productions"][0]["revision"]
        save_production_notes("14657", revision, [{"row_id": "0", "notes": "Saved note"}])
        self.assertEqual(load_recent_production_notes()["items"][0]["notes"], "Saved note")
        with self.assertRaises(ProductionConflict):
            save_production_notes("14657", revision, [{"row_id": "0", "notes": "Stale note"}])

    def test_scanner_does_not_consult_admin_cache(self):
        self.xml(14657, note="Before")
        load_recent_production_notes()
        self.xml(14657, note="After")
        with patch.object(admin_store, "_load_notes", side_effect=AssertionError("Scanner used admin cache")):
            result = lookup_xml_item("CON1", production_number="14657", oln_id=123)
        self.assertEqual(result["fields"]["Megjegyzes"], "After")


if __name__ == "__main__":
    unittest.main()
