"""Tests for barcode-scoped label fields and numbered feature slots."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .production_xml import FEATURE_NAMES, XML_FILENAME, lookup_xml_item


# Matches the actual flat CON / FeatureBillTranslationNN / ertekNN export shape.
SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<EtikettKitchen_korp_tip>
  <CON>
    <Barcode>CON1396379</Barcode><olnID>999</olnID>
    <pdCode>OTHER</pdCode><Korp_szin>Másik szín</Korp_szin>
    <FeatureBillTranslation02>J/B</FeatureBillTranslation02><ertek02>Bal</ertek02>
  </CON>
  <CON>
    <Barcode>CON1396379</Barcode><olnID>1207826</olnID>
    <Korpusztipus>2A</Korpusztipus><Korp_tip_nev>2-es alsó</Korp_tip_nev>
    <pdCode>AF40</pdCode><pdvDescription>Alsó 1+2 fiók 40-es</pdvDescription>
    <Korp_szin>Antracit kr.</Korp_szin>
    <FeatureBillTranslation01>Front típus</FeatureBillTranslation01><ertek01>Laura</ertek01>
    <FeatureBillTranslation02>Front színe</FeatureBillTranslation02><ertek02>SM.provance fóliás</ertek02>
    <FeatureBillTranslation04>Munkalap szín</FeatureBillTranslation04><ertek04>Nincs</ertek04>
    <FeatureBillTranslation06>Láb típusa</FeatureBillTranslation06><ertek06>Műa. áll.100-as</ertek06>
    <FeatureBillTranslation07>Beép.mag.cm</FeatureBillTranslation07><OptionDescription07>Méret</OptionDescription07><ertek07>82.4</ertek07>
    <FeatureBillTranslation08>Beép.szél.cm</FeatureBillTranslation08><ertek08>40.000000</ertek08>
    <FeatureBillTranslation09>Beép.mélys.cm</FeatureBillTranslation09><ertek09>60.000000</ertek09>
    <FeatureBillTranslation10>Fogantyú furat</FeatureBillTranslation10><ertek10>Fúrva</ertek10>
    <FeatureBillTranslation12>Keretléc szín</FeatureBillTranslation12><ertek12>Fehér</ertek12>
  </CON>
  <CON>
    <Barcode>CON13963790</Barcode><olnID>1207826</olnID><pdCode>NEIGHBOUR</pdCode>
    <FeatureBillTranslation02>J/B</FeatureBillTranslation02><ertek02>Jobb</ertek02>
  </CON>
</EtikettKitchen_korp_tip>"""


class ProductionXmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "14545"
        self.folder.mkdir()
        self.xml_path = self.folder / XML_FILENAME
        self.xml_path.write_text(SAMPLE_XML, encoding="utf-8")
        folder_patch = patch("part_workstation.production_xml.production_folder", side_effect=lambda number: self.root / number)
        self.production_folder = folder_patch.start()
        self.addCleanup(folder_patch.stop)

    def test_exact_barcode_and_order_line_select_the_correct_record(self) -> None:
        result = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.assertEqual(result["lookup_status"], "ready")
        self.assertEqual(result["production_number"], "14545")
        self.assertEqual(result["fields"], {
            "Barcode": "CON1396379", "Korpusztipus": "2A", "Korp_tip_nev": "2-es alsó",
            "pdCode": "AF40", "pdvDescription": "Alsó 1+2 fiók 40-es", "Korp_Szin": "Antracit kr.",
        })
        self.assertEqual(result["features"], {
            "Láb típusa": "Műa. áll.100-as", "J/B": "", "Nyitási irány": "", "Munkalap szín": "Nincs",
            "Front típus": "Laura", "Beép.mag.cm": "82.4", "Beép.szél.cm": "40.000000",
            "Beép.mélys.cm": "60.000000", "Front színe": "SM.provance fóliás", "Keretléc szín": "Fehér",
            "Hézagtakaró szélessége": "", "Front szín felső": "", "Fogantyú furat": "Fúrva",
        })

    def test_feature_labels_follow_their_numbered_values_in_any_slot(self) -> None:
        xml = """<EtikettKitchen_korp_tip><CON><Barcode>CON1</Barcode>
          <FeatureBillTranslation22>J/B</FeatureBillTranslation22><OptionDescription22>Jobb</OptionDescription22>
          <FeatureBillTranslation05>Nyitási irány</FeatureBillTranslation05><ertek05>Bal</ertek05>
          <FeatureBillTranslation03>Beép.mag.cm</FeatureBillTranslation03><OptionValue03>0</OptionValue03><OptionDescription03>Méret</OptionDescription03>
          <FeatureBillTranslation14>Front típus</FeatureBillTranslation14><OptionValue14>Other</OptionValue14><ertek14>Laura</ertek14>
          <FeatureBillTranslation18>Hézagtakaró szélessége</FeatureBillTranslation18><ertek18>82</ertek18>
          <FeatureBillTranslation19>Front szín felső</FeatureBillTranslation19><ertek19>Artizán tölgy</ertek19>
          <FeatureBillTranslation31>Fogantyú furat</FeatureBillTranslation31><ertek31>64 / 96</ertek31>
        </CON></EtikettKitchen_korp_tip>"""
        self.xml_path.write_text(xml, encoding="utf-8")
        result = lookup_xml_item("CON1", production_number="14545")
        self.assertEqual(result["features"]["J/B"], "Jobb")
        self.assertEqual(result["features"]["Nyitási irány"], "Bal")
        self.assertEqual(result["features"]["Beép.mag.cm"], "0")
        self.assertEqual(result["features"]["Front típus"], "Laura")
        self.assertEqual(result["features"]["Hézagtakaró szélessége"], "82")
        self.assertEqual(result["features"]["Front szín felső"], "Artizán tölgy")
        self.assertEqual(result["features"]["Fogantyú furat"], "64 / 96")
        self.assertEqual(set(result["features"]), set(FEATURE_NAMES))

    def test_missing_barcode_or_wrong_order_line_never_borrows_another_item(self) -> None:
        for barcode, oln_id in (("CON139637", None), ("MISSING", None), ("CON1396379", 123)):
            with self.subTest(barcode=barcode, oln_id=oln_id):
                result = lookup_xml_item(barcode, production_number="14545", oln_id=oln_id)
                self.assertEqual(result["lookup_status"], "not_found")
                self.assertFalse(any(result["fields"].values()))
                self.assertFalse(any(result["features"].values()))

    def test_ambiguous_barcode_never_picks_an_arbitrary_record(self) -> None:
        result = lookup_xml_item("CON1396379", production_number="14545")
        self.assertEqual(result["lookup_status"], "ambiguous")
        self.assertFalse(any(result["fields"].values()))

    def test_repeated_scans_reopen_xml_and_see_source_changes(self) -> None:
        first = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.xml_path.write_text(SAMPLE_XML.replace("<pdCode>AF40</pdCode>", "<pdCode>UPDATED</pdCode>"), encoding="utf-8")
        second = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.assertEqual(first["fields"]["pdCode"], "AF40")
        self.assertEqual(second["fields"]["pdCode"], "UPDATED")
        self.xml_path.unlink()
        self.assertEqual(lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)["lookup_status"], "unavailable")

    def test_unavailable_and_malformed_xml_have_distinct_states(self) -> None:
        self.xml_path.unlink()
        self.assertEqual(lookup_xml_item("CON1396379", production_number="14545")["lookup_status"], "unavailable")
        self.xml_path.write_text("<broken", encoding="utf-8")
        self.assertEqual(lookup_xml_item("CON1396379", production_number="14545")["lookup_status"], "error")

    def test_namespaces_do_not_change_field_matching(self) -> None:
        self.xml_path.write_text(SAMPLE_XML.replace("<EtikettKitchen_korp_tip>", '<EtikettKitchen_korp_tip xmlns="urn:labels">'), encoding="utf-8")
        self.assertEqual(lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)["fields"]["pdCode"], "AF40")

    def test_requested_production_selects_its_own_xml_without_fallback(self) -> None:
        second_folder = self.root / "14546"
        second_folder.mkdir()
        (second_folder / XML_FILENAME).write_text(SAMPLE_XML.replace("<pdCode>AF40</pdCode>", "<pdCode>NEW</pdCode>"), encoding="utf-8")
        first = lookup_xml_item("CON1396379", production_number="14545", oln_id=1207826)
        self.production_folder.assert_called_with("14545")
        second = lookup_xml_item("CON1396379", production_number="14546", oln_id=1207826)
        self.production_folder.assert_called_with("14546")
        self.assertEqual(first["fields"]["pdCode"], "AF40")
        self.assertEqual(second["fields"]["pdCode"], "NEW")
        missing = lookup_xml_item("CON1396379", production_number="14547", oln_id=1207826)
        self.assertEqual(missing["lookup_status"], "unavailable")
        self.assertFalse(any(missing["fields"].values()))

    def test_invalid_production_never_opens_a_folder(self) -> None:
        for number in (None, "", "0", "-1", "../14545", "14545.0", True):
            with self.subTest(number=number):
                self.assertEqual(lookup_xml_item("CON1396379", production_number=number)["lookup_status"], "error")
        self.production_folder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
