"""Model-specific front colour pictures shipped as application assets.

Colour names/codes follow the NettFront translations and invoice labels, including
the manufacturing SM./fóliás spellings. The client uses Anna for unknown models;
known models still require a matching colour/finish from their own catalogue.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import quote


ASSET_DIRECTORY = Path(__file__).resolve().parents[2] / "assets" / "part-workstation" / "front-colours"
ASSET_URL_PREFIX = "/assets/part-workstation/front-colours/"

# Each filename has its own aliases so similarly named matt/gloss colours remain
# distinct. The old/SM colour spellings mirror NettFront's colour code aliases.
MODEL_COLOURS = {
    ("Anna", "AN"): {
        "AN_AGS": ("AGS", "Agyag szürke"),
        "AN_ANT": ("ANT", "Antracit", "Antracit kr."),
        "AN_BIA": ("BIA", "Bianco"),
        "AN_CAN": ("CAN", "Canyon", "Canyon tölgy"),
        "AN_CST": ("CST", "Csíkos tölgy"),
        "AN_ETNA": ("ETNA",),
        "AN_FEH": ("FEH", "Fehér"),
        "AN_IBZ": ("IBZ", "Ibiza"),
        "AN_KAS": ("KAS", "Kasmír"),
        "AN_NERO": ("NERO", "Néró"),
        "AN_PTE": ("PTE", "Petra", "Petra tölgy"),
        "AN_SONF": ("SONF", "Sonoma", "Sonoma tölgy"),
        "AN_SR": ("SR", "San Remo"),
        "AN_VS": ("VS",),
    },
    ("Antónia", "ANT"): {
        "ANTMT_ARF": ("ARF", "Artizán tölgy"),
        "ANTMT_FEHR": ("FEHR", "FEA", "FEAS", "Matt Fehér", "SM. Fehér", "Pure White", "Matt Dusk White"),
        "ANTMT_GRAFIT": ("GRAFIT", "GFA", "GFAS", "Matt Grafit", "Matt antracit", "SM. Grafit", "Mist Grey"),
        "ANTMT_KAF": ("KAF", "KAFS", "Matt Kasmír", "SM. Kasmír", "Dune Beige"),
        "ANTMT_PRA": ("PRA", "PRAS", "Matt Provance", "Matt Provence", "SM. Provance", "SM. Provence", "Cedar Green", "Cedar Green SM"),
        "ANTMT_SURK": ("SURK", "SZA", "Matt Szürke", "Matt Platinum Grey"),
        "ANT_ANTH_MF": ("ANTH_MF", "ANMM", "Mf. Antracit", "Magasfényű antracit"),
        "ANT_BEI_MF": ("BEI_MF", "BGMM", "Mf. Beige", "Mf. Krém", "Magasfényű beige", "Magasfényű krém"),
        "ANT_CAP_MF": ("CAP_MF", "CPMM", "Mf. Capuccino", "Mf. Cappuccino", "Mf. Latte", "Magasfényű latte", "Magasfényű capuccino"),
        "ANT_WHT_MF": ("WHT_MF", "FFMM", "Mf. Fehér", "Magasfényű fehér"),
    },
    ("Doroti",): {
        "Doroti_ANMM": ("ANMM", "Mf. Antracit", "Magasfényű antracit"),
        "Doroti_ARF": ("ARF", "Artizán tölgy"),
        "Doroti_ART": ("ART",),
        "Doroti_BFL": ("BFL", "Beton fehér"),
        "Doroti_BGMM": ("BGMM", "Mf. Beige", "Mf. Krém", "Magasfényű beige", "Magasfényű krém"),
        "Doroti_CPMM": ("CPMM", "Mf. Capuccino", "Mf. Cappuccino", "Mf. Latte", "Magasfényű latte", "Magasfényű capuccino"),
        "Doroti_FEA": ("FEA", "FEAS", "Matt Fehér", "SM. Fehér", "Pure White", "Matt Dusk White"),
        "Doroti_FET": ("FET", "Fehér tölgy"),
        "Doroti_FFMM": ("FFMM", "Mf. Fehér", "Magasfényű fehér"),
        "Doroti_FZL": ("FZL", "Fjord zöld"),
        "Doroti_GFA": ("GFA", "GFAS", "Matt Grafit", "Matt antracit", "SM. Grafit", "Mist Grey"),
        "Doroti_KAF": ("KAF", "KAFS", "Matt Kasmír", "SM. Kasmír", "Dune Beige"),
        "Doroti_PRA": ("PRA", "PRAS", "Matt Provance", "Matt Provence", "SM. Provance", "SM. Provence", "Cedar Green", "Cedar Green SM"),
        "Doroti_RST": ("RST", "Rusztikus sötét tölgy"),
        "Doroti_SOL": ("SOL", "SOF", "Sonoma", "Sonoma tölgy"),
        "Doroti_SZA": ("SZA", "Matt Szürke", "Matt Platinum Grey"),
        "Doroti_SZU": ("SZU", "Szürke tölgy"),
    },
    ("Zille", "ZI"): {
        "ZILLE_ANT_OAK": ("ANT_OAK", "Antracit tölgy"),
        "ZILLE_BEI": ("BEI", "BGF", "BGA", "BGAS", "Beige", "Matt Beige", "SM. Beige", "Uni beige", "Palo Santo Beige"),
        "ZILLE_RUS_WH": ("RUS_WH", "FER", "Rusztikus fehér"),
        "ZILLE_SON_OAK": ("SON_OAK", "SOF", "Sonoma", "Sonoma tölgy"),
        "ZILLE_WOT_OAK": ("WOT_OAK", "WTF", "Wotan tölgy"),
    },
    ("Laura", "LU"): {
        "LAURA_CAP": ("CAP", "CPA", "KAF", "KAFS", "Capuccino", "Cappuccino", "Matt Capuccino", "Matt Cappuccino", "Matt Stone Grey", "Kasmír", "Matt Kasmír", "SM. Kasmír", "Dune Beige"),
        "LAURA_GEI": ("GEI", "BGA", "BGAS", "Beige", "Matt Beige", "SM. Beige", "Palo Santo Beige"),
        "LAURA_GRAP": ("GRAP", "GFA", "GFAS", "Matt Grafit", "Matt antracit", "SM. Grafit", "Mist Grey"),
        "LAURA_GRAY": ("GRAY", "SZA", "Matt Szürke", "Matt Platinum Grey"),
        "LAURA_PRO": ("PRO", "PRA", "PRAS", "Matt Provance", "Matt Provence", "SM. Provance", "SM. Provence", "Cedar Green", "Cedar Green SM"),
        "LAURA_WHT": ("WHT", "FEA", "FEAS", "Matt Fehér", "SM. Fehér", "Pure White", "Matt Dusk White"),
    },
}


def _key(value: str) -> str:
    folded = "".join(char for char in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(char))
    # XML appends fóliás to the same colour names used elsewhere in the program.
    folded = re.sub(r"\bfolias\b", "", folded)
    return re.sub(r"[^a-z0-9]", "", folded)


def front_image_catalog() -> dict[str, dict[str, str]]:
    """Expose exact normalized type/colour pairs and their static image URLs."""
    files = {path.stem: path for path in sorted(ASSET_DIRECTORY.glob("*")) if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    catalog = {}
    for models, colours in MODEL_COLOURS.items():
        aliases = {}
        for stem, names in colours.items():
            if stem not in files:
                continue
            url = ASSET_URL_PREFIX + quote(files[stem].name)
            for name in (stem, *names):
                aliases[_key(name)] = url
        for model in models:
            catalog[_key(model)] = aliases
    return catalog
