"""Protect Nettfront names that differ despite sharing the same image."""

import unittest

from .front_colours import nettfront_colour_catalog
from .front_images import MODEL_COLOURS, _key


class NettfrontColourTests(unittest.TestCase):
    def setUp(self):
        self.catalog = nettfront_colour_catalog()

    def name(self, model, colour):
        return self.catalog.get(_key(model), {}).get(_key(colour), "")

    def test_matt_and_sm_finishes_keep_distinct_counterparts(self):
        cases = (
            ("Antónia", "Matt fehér fóliás", "Matt Dusk White"),
            ("Antónia", "SM.fehér fóliás", "Pure White"),
            ("Doroti", "Matt grafit fóliás", "Matt Antracit"),
            ("Doroti", "SM.grafit fóliás", "Mist Grey"),
            ("Laura", "Matt beige fóliás", "Matt Mussel"),
            ("Laura", "SM.beige fóliás", "Palo Santo Beige"),
            ("Laura", "Matt cappuccino", "Matt Stone Grey"),
            ("Laura", "SM.kasmír fóliás", "Dune Beige"),
            ("Laura", "Matt provance fóliás", "Matt Provance"),
            ("Laura", "SM.provance fóliás", "Cedar Green"),
            ("Zille", "Beige fóliás", "Uni beige"),
            ("Zille", "SM.beige fóliás", "Palo Santo Beige"),
            ("ANT", "Mf. beige", "Mf. Krém"),
            ("Doroti", "Mf. capuccino", "Mf. Latte"),
            ("LU", "FEAS", "Pure White"),
            ("ZI", "Wotan tölgy", "Wotan tölgy"),
        )
        for model, colour, expected in cases:
            with self.subTest(model=model, colour=colour):
                self.assertEqual(self.name(model, colour), expected)

    def test_every_bundled_nettfront_colour_alias_has_a_counterpart(self):
        for models, pictures in MODEL_COLOURS.items():
            if models[0] == "Anna":
                continue
            for model in models:
                for aliases in pictures.values():
                    for alias in aliases:
                        with self.subTest(model=model, colour=alias):
                            self.assertTrue(self.name(model, alias))

    def test_existing_nettfront_names_are_not_translated_again(self):
        for model in ("Antónia", "Doroti", "Laura", "Zille"):
            for name in set(self.catalog[_key(model)].values()):
                with self.subTest(model=model, name=name):
                    self.assertEqual(self.name(model, name), name)

    def test_unknown_colour_or_model_does_not_invent_a_nettfront_name(self):
        for model, colour in (("Anna", "Fehér"), ("Klió", "Fehér"), ("Antónia", "unknown"), ("Zille", "Nincs")):
            with self.subTest(model=model, colour=colour):
                self.assertEqual(self.name(model, colour), "")


if __name__ == "__main__":
    unittest.main()
