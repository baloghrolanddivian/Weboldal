"""Verify the supplied connector groups and the exact AR20 exception."""

from pathlib import Path
import unittest

from tools.static_assets import load_static_asset

from .connectors import CONNECTOR_RULES, connector_for_part


class ConnectorTests(unittest.TestCase):
    def test_vertical_prefixes_take_precedence_over_as(self) -> None:
        for prefix in ("AMO", "ASZB", "ASZH", "ASM"):
            for suffix in ("", "60", "90_B", "CUSTOM"):
                with self.subTest(code=prefix + suffix):
                    connector = connector_for_part(prefix + suffix)
                    self.assertEqual(connector["orientation"], "Függőleges")
                    self.assertTrue(connector["image_url"].endswith("/vertical.png"))

    def test_horizontal_codes_match_prefixes_without_requiring_a_size(self) -> None:
        for prefix in ("AML", "AKL", "AAF", "AF", "AS"):
            for suffix in ("", "40", "60_J", "B40", "CUSTOM"):
                with self.subTest(code=prefix + suffix):
                    connector = connector_for_part(prefix + suffix)
                    self.assertEqual(connector["orientation"], "Vízszintes")
                    self.assertTrue(connector["image_url"].endswith("/horizontal.png"))
        self.assertEqual(connector_for_part("  afb60p  ")["orientation"], "Vízszintes")

    def test_ar20_is_exact_and_unlisted_items_have_no_connector(self) -> None:
        self.assertEqual(connector_for_part("AR20")["orientation"], "Vízszintes")
        for code in (None, "", "TEST-PART", "FAF40", "AR", "AR25", "AR200", "AR20_B", "AR20J", "XAF40"):
            with self.subTest(code=code):
                self.assertIsNone(connector_for_part(code))

    def test_both_supplied_images_are_served_as_png_assets(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for rule in CONNECTOR_RULES:
            body, content_type = load_static_asset(root, rule["image_url"])
            self.assertEqual(content_type, "image/png")
            self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"))
