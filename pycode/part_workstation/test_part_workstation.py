"""Tests for the scanned-part workstation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from .page import render_page
from .store import configure_part_workstation, load_user_state, register_scan, reset_user_state


class PartWorkstationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        configure_part_workstation(Path(self.temp_dir.name))

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

    def test_page_contains_three_regions_and_escaped_user(self) -> None:
        body = render_page(load_user_state("worker-a"), "Teszt <Felhasználó>").decode("utf-8")
        self.assertIn("3D elemnézet", body)
        self.assertIn("Beolvasott elem adatai", body)
        self.assertIn("Darabjegyzék", body)
        self.assertIn("Teszt &lt;Felhasználó&gt;", body)


if __name__ == "__main__":
    unittest.main()
