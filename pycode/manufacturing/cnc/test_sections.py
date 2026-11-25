"""Regression tests for distinct CNC lower-cabinet side types."""

from __future__ import annotations

import importlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


BUILDERS = (
    importlib.import_module("manufacturing.cnc.sections"),
    importlib.import_module("manufacturing.admin.cnc.sections"),
)


class CncSideTypeTests(unittest.TestCase):
    def write_xml(self, folder: Path, rows: list[dict]) -> None:
        root = ET.Element("CNC")
        for index, row in enumerate(rows, start=1):
            con = ET.SubElement(root, "CON")
            fields = {
                "KorpTipPer": "2-es alsó",
                "Leiras": row["name"],
                "Hossz": "724",
                "Szelleseg": "550",
                "Vastag": "18",
                "Szin": row["color"],
                "FIOKSIN_FURAS": "T",
                "Oldal_Tip": row["side_type"],
                "Elzaras": row["edge"],
                "conQuantity": str(row["quantity"]),
                "prdID": "14705",
                "conID": f"CON{index}",
                "childID": "0",
            }
            for key, value in fields.items():
                ET.SubElement(con, key).text = value
        ET.ElementTree(root).write(folder / "CNC.xml", encoding="utf-8")

    def build_sections(self, module, bundle: dict):
        with (
            patch.object(module, "load_row_data", return_value={}),
            patch("manufacturing.base.workflow.load_row_data", return_value={}),
        ):
            return module._manufacturing_cnc_sections(bundle, "14705")

    def source_rows(self, atf_pultos: str) -> list[dict]:
        return [
            {
                "row_id": f"source-{index}",
                "name": "Pultos alsó oldal",
                "size": "724 x 550 x 18",
                "color": "Fehér",
                "drawer_drill": "Teleszkóp",
                "side_type": side_type,
                "edge": "2H",
                "quantity": quantity,
            }
            for index, (side_type, quantity) in enumerate(
                ((atf_pultos, 2), ("Pultos normál alsó", 3), ("ATF", 8)), start=1
            )
        ]

    def assert_distinct_types(self, module, bundle: dict, atf_label: str = "ATF Pultos") -> None:
        main, _, views, *_ = self.build_sections(module, bundle)
        lower_main = next(section for section in main if section["key"] == "cnc-main::also")
        lower_view = next(view for view in views if view["key"] == "cnc-also")
        other_section = next(section for section in lower_view["sections"] if section["label"] == "Egyebek")
        rows = lower_main["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            {row["side_type"]: row["quantity"] for row in rows},
            {atf_label: 2, "Pultos normál alsó": 3, "ATF": 8},
        )
        atf_pultos = next(row for row in rows if row["side_type"] == atf_label)
        self.assertEqual(atf_pultos["size"], "724 x 550 x 18")
        self.assertEqual(atf_pultos["edge"], "2H")
        self.assertTrue(any(row["side_type"] == atf_label for row in other_section["rows"]))

    def test_xml_keeps_atf_pultos_distinct_from_normal_pultos_and_atf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for label in ("ATF Pultos", " atf   pultos "):
                self.write_xml(folder, self.source_rows(label))
                for module in BUILDERS:
                    with self.subTest(view=module.__name__, label=label):
                        self.assert_distinct_types(module, {"folder": str(folder), "documents": []}, label.strip())

    def test_xml_preserves_all_formerly_normalized_labels(self) -> None:
        labels = (
            "AR golyós", "AAF fiókos ajtós egyedi", "AF 1 + 2 egyedi",
            "Pultos normál alsó", "AS VT egyedi", "AS MAGIC egyedi",
            "ATF egyedi", "ASZB szemetes egyedi", "ASZHS/ASZB", "ASZB",
            "AKL egyedi", "Jolly egyedi", "Kira egyedi", "AR egyedi",
            "Nyitott egyedi", "Normál alsó", "normál egyedi", "atf   pultos",
        )
        template = self.source_rows("ATF Pultos")[0]
        rows = [dict(template, side_type=label, quantity=index) for index, label in enumerate(labels, start=1)]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.write_xml(folder, rows)
            for module in BUILDERS:
                with self.subTest(view=module.__name__):
                    main, _, _, *_ = self.build_sections(module, {"folder": str(folder), "documents": []})
                    lower = next(section for section in main if section["key"] == "cnc-main::also")
                    self.assertEqual(len(lower["rows"]), len(labels))
                    self.assertEqual(
                        {row["side_type"]: row["quantity"] for row in lower["rows"]},
                        dict(zip(labels, range(1, len(labels) + 1))),
                    )

    def test_separate_grouping_and_cover_panel_rules_still_apply(self) -> None:
        template = self.source_rows("ATF Pultos")[0]
        rows = [
            dict(template, row_id="normal", name="Alsó oldal", size="724 x 505 x 18", side_type="AF 1+2 fiókos"),
            dict(template, row_id="kinga", name="Alsó oldal", size="824 x 505 x 18", side_type="AAF fiókos ajtós"),
            dict(template, row_id="cover", name="Takarólap AS", side_type="Normáls alsó"),
        ]
        bundle = {"documents": [{
            "key": "cnc",
            "sections": [{"key": "lower", "label": "2-es alsó", "rows": rows}],
        }]}
        for module in BUILDERS:
            with self.subTest(view=module.__name__):
                main, _, views, *_ = self.build_sections(module, bundle)
                lower = next(section for section in main if section["key"] == "cnc-main::also")
                cover = next(row for row in lower["rows"] if row["name"] == "Takarólap AS")
                self.assertEqual(cover["side_type"], "")
                view = next(view for view in views if view["key"] == "cnc-also")
                normal = next(section for section in view["sections"] if section["label"] == "Normáls alsó")
                self.assertEqual(normal["rows"][0]["side_type"], "Normáls alsó")
                boxos = next(section for section in view["sections"] if section["label"] == "Boxosok")
                expected = "AAF fiókos ajtós" if ".admin." in module.__name__ else "AF/AAF fiókos"
                self.assertEqual(boxos["rows"][0]["side_type"], expected)

    def test_detail_parsing_keeps_atf_pultos_distinct(self) -> None:
        rows = self.source_rows("ATF Pultos")
        for row in rows:
            row["detail"] = f"Teleszkóp {row.pop('side_type')} 2H"
            row.pop("drawer_drill")
        bundle = {
            "documents": [{
                "key": "cnc",
                "sections": [{"key": "lower", "label": "2-es alsó", "rows": rows}],
            }],
        }
        for module in BUILDERS:
            with self.subTest(view=module.__name__):
                self.assert_distinct_types(module, bundle)


if __name__ == "__main__":
    unittest.main()
