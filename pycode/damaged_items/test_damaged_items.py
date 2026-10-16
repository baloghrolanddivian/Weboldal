"""Tests for the damaged-item report module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from damaged_items.http import parse_multipart
from damaged_items import (
    configure_damaged_items,
    create_report,
    delete_report,
    list_reports,
    render_admin_page,
    render_worker_page,
    report_image,
)


class DamagedItemsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        configure_damaged_items(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_report_requires_note_responsible_person_and_image(self) -> None:
        with self.assertRaisesRegex(ValueError, "megjegyzés"):
            create_report(created_by="Teszt", note="", responsible_person="Teszt Elek", images=[("hiba.jpg", "image/jpeg", b"img")])
        with self.assertRaisesRegex(ValueError, "felelős"):
            create_report(created_by="Teszt", note="Eltört", responsible_person="", images=[("hiba.jpg", "image/jpeg", b"img")])
        with self.assertRaisesRegex(ValueError, "rögzítő"):
            create_report(created_by="", note="Eltört", responsible_person="Teszt Elek", images=[("hiba.jpg", "image/jpeg", b"img")])
        with self.assertRaisesRegex(ValueError, "kép"):
            create_report(created_by="Teszt", note="Eltört", responsible_person="Teszt Elek", images=[])

    def test_report_image_and_delete_lifecycle(self) -> None:
        report = create_report(
            created_by="Raktár",
            note="A sarok a csomagolás közben megsérült.",
            responsible_person="Minta Márton",
            images=[
                ("serules.jpg", "image/jpeg", b"fake-jpeg"),
                ("reszlet.png", "image/png", b"fake-png"),
            ],
            barcode="TEST-001",
            part_number="NFA_TEST",
            description="Teszt front",
            order_number="V-100",
            production_number="260001",
        )
        self.assertEqual(len(list_reports()), 1)
        self.assertEqual(report_image(report["id"]), (b"fake-jpeg", "image/jpeg"))
        self.assertEqual(report_image(report["id"], 1), (b"fake-png", "image/png"))
        self.assertIsNone(report_image(report["id"], 2))
        self.assertTrue(delete_report(report["id"]))
        self.assertEqual(list_reports(), [])
        self.assertIsNone(report_image(report["id"]))

    def test_worker_has_no_delete_control_and_admin_does(self) -> None:
        report = create_report(
            created_by="Raktár",
            note="Karcos lett.",
            responsible_person="Teszt Elek",
            images=[("serules.png", "image/png", b"fake-png")],
            description="Teszt elem",
        )
        worker = render_worker_page([report], "Raktár").decode("utf-8")
        admin = render_admin_page([report], "Admin").decode("utf-8")
        self.assertIn("Sérült elem felvitele", worker)
        self.assertIn("Várakozás a csippantásra", worker)
        self.assertIn('name="note"', worker)
        self.assertIn('name="responsible_person"', worker)
        self.assertIn('name="recorded_by"', worker)
        self.assertIn('name="damage_image"', worker)
        self.assertIn('id="damageCamera" accept="image/*" capture="environment"', worker)
        self.assertIn('id="damageImage" accept="image/*" multiple required hidden', worker)
        self.assertIn("photo-remove", worker)
        self.assertIn("new DataTransfer()", worker)
        self.assertIn("Felelős", worker)
        self.assertNotIn("data-delete-report", worker)
        self.assertIn("data-delete-report", admin)
        self.assertIn("/apps/admin-serult-elemek/torles/", admin)

    def test_multipart_parser_keeps_repeated_image_fields(self) -> None:
        body = (
            b'--test-boundary\r\nContent-Disposition: form-data; name="damage_image"; filename="a.jpg"\r\n'
            b'Content-Type: image/jpeg\r\n\r\none\r\n'
            b'--test-boundary\r\nContent-Disposition: form-data; name="damage_image"; filename="b.png"\r\n'
            b'Content-Type: image/png\r\n\r\ntwo\r\n--test-boundary--\r\n'
        )
        _fields, files = parse_multipart(
            {"Content-Type": "multipart/form-data; boundary=test-boundary"}, body
        )
        self.assertEqual([item[0] for item in files["damage_image"]], ["a.jpg", "b.png"])


if __name__ == "__main__":
    unittest.main()
