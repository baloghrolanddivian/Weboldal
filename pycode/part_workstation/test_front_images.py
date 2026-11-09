"""Front image matching must keep model and finish distinctions intact."""

import unittest
from urllib.parse import unquote

from .front_images import ASSET_DIRECTORY, ASSET_URL_PREFIX, _key, front_image_catalog


class FrontImageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = front_image_catalog()

    def image(self, model, colour):
        return self.catalog.get(_key(model), {}).get(_key(colour), "")

    def test_production_xml_spellings_and_program_codes(self):
        cases = (
            ("Anna", "Canyon tölgy", "AN_CAN.jpg"),
            ("AN", "Antracit kr.", "AN_ANT.jpg"),
            ("Anna", "Petra tölgy", "AN_PTE.jpg"),
            ("Anna", "Sonoma tölgy", "AN_SONF.jpg"),
            ("Antónia", "SM.kasmír fóliás", "ANTMT_KAF.jpg"),
            ("ANT", "PRAS", "ANTMT_PRA.jpg"),
            ("Antónia", "Mf. beige", "ANT_BEI_MF.jpg"),
            ("Antónia", "Mf. capuccino", "ANT_CAP_MF.jpg"),
            ("Doroti", "Artizán tölgy fóliás", "Doroti_ARF.jpg"),
            ("Doroti", "Fjord zöld", "Doroti_FZL.jpg"),
            ("Doroti", "SM.fehér fóliás", "Doroti_FEA.jpg"),
            ("Doroti", "Mf. fehér", "Doroti_FFMM.jpg"),
            ("ZILLE", "SM.beige fóliás", "ZILLE_BEI.jpg"),
            ("ZI", "WTF", "ZILLE_WOT_OAK.jpg"),
            ("Laura", "SM.provance fóliás", "LAURA_PRO.jpg"),
            ("Laura", "SM.kasmír fóliás", "LAURA_CAP.jpg"),
            ("Laura", "Kasmír", "LAURA_CAP.jpg"),
            ("LU", "KAFS", "LAURA_CAP.jpg"),
            ("Laura", "Capuccino", "LAURA_CAP.jpg"),
            ("Laura", "Beige", "LAURA_GEI.jpg"),
            ("Laura", "SM.beige fóliás", "LAURA_GEI.jpg"),
            ("LU", "FEAS", "LAURA_WHT.jpg"),
        )
        for model, colour, filename in cases:
            with self.subTest(model=model, colour=colour):
                self.assertEqual(self.image(model, colour), ASSET_URL_PREFIX + filename)

    def test_normalizes_accents_case_spacing_and_foil_suffix(self):
        self.assertEqual(self.image(" ANTÓNIA ", " sm. KASMÍR   FÓLIÁS "), self.image("Antonia", "KAFS"))
        self.assertNotEqual(self.image("Antónia", "Matt fehér"), self.image("Antónia", "Mf. fehér"))
        self.assertNotEqual(self.image("Antónia", "Matt fehér"), self.image("Doroti", "Matt fehér"))

    def test_unknown_model_colour_and_finish_have_no_fallback(self):
        for model, colour in (("Klió", "Fehér"), ("Kata", "Mf. Fehér"), ("Anna", "Nincs"), ("Anna", "Mf. Fehér"), ("Antónia", "Fehér"), ("Doroti", "unknown")):
            with self.subTest(model=model, colour=colour):
                self.assertEqual(self.image(model, colour), "")

    def test_all_bundled_images_are_exposed_with_valid_static_urls(self):
        urls = {url for colours in self.catalog.values() for url in colours.values()}
        self.assertEqual(len(urls), 52)
        for url in urls:
            self.assertTrue(url.startswith(ASSET_URL_PREFIX))
            path = ASSET_DIRECTORY / unquote(url.removeprefix(ASSET_URL_PREFIX))
            self.assertTrue(path.is_file(), url)
            self.assertEqual(path.read_bytes()[:2], b"\xff\xd8")
            self.assertEqual(path.suffix, ".jpg")


if __name__ == "__main__":
    unittest.main()
