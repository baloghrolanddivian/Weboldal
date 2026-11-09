"""Nettfront names from the existing translations and naming workbook.

Matt and SM finishes can share a picture, but have different Nettfront names.
Keep that distinction when expanding the picture aliases into display names.
"""

from .front_images import MODEL_COLOURS, _key


# Base names for the bundled pictures, including unchanged wood/decor names.
NAMES_BY_PICTURE = {
    "ANTMT_ARF": "Artizán tölgy", "ANTMT_FEHR": "Matt Dusk White",
    "ANTMT_GRAFIT": "Matt Antracit", "ANTMT_KAF": "Dune Beige",
    "ANTMT_PRA": "Cedar Green", "ANTMT_SURK": "Matt Platinum Grey",
    "ANT_ANTH_MF": "Mf. Antracit", "ANT_BEI_MF": "Mf. Krém",
    "ANT_CAP_MF": "Mf. Latte", "ANT_WHT_MF": "Mf. Fehér",
    "Doroti_ANMM": "Mf. Antracit", "Doroti_ARF": "Artizán tölgy",
    "Doroti_ART": "Artizán tölgy", "Doroti_BFL": "Beton fehér",
    "Doroti_BGMM": "Mf. Krém", "Doroti_CPMM": "Mf. Latte",
    "Doroti_FEA": "Matt Dusk White", "Doroti_FET": "Fehér tölgy",
    "Doroti_FFMM": "Mf. Fehér", "Doroti_FZL": "Fjord zöld",
    "Doroti_GFA": "Matt Antracit", "Doroti_KAF": "Dune Beige",
    "Doroti_PRA": "Cedar Green", "Doroti_RST": "Rusztikus sötét tölgy",
    "Doroti_SOL": "Sonoma tölgy", "Doroti_SZA": "Matt Platinum Grey",
    "Doroti_SZU": "Szürke tölgy",
    "ZILLE_ANT_OAK": "Antracit tölgy", "ZILLE_BEI": "Uni beige",
    "ZILLE_RUS_WH": "Rusztikus fehér", "ZILLE_SON_OAK": "Sonoma tölgy",
    "ZILLE_WOT_OAK": "Wotan tölgy",
    "LAURA_CAP": "Matt Stone Grey", "LAURA_GEI": "Matt Mussel",
    "LAURA_GRAP": "Matt Antracit", "LAURA_GRAY": "Matt Platinum Grey",
    "LAURA_PRO": "Matt Provance", "LAURA_WHT": "Matt Dusk White",
}


def nettfront_colour_catalog() -> dict[str, dict[str, str]]:
    """Return account-independent names keyed by the actual front model/colour."""
    catalog = {}
    for models, pictures in MODEL_COLOURS.items():
        if models[0] == "Anna":
            continue
        names = {}
        for picture, aliases in pictures.items():
            counterpart = NAMES_BY_PICTURE[picture]
            for alias in (picture, *aliases):
                names[_key(alias)] = counterpart
        # These finishes are deliberately not inferred from a shared image URL.
        groups = {
            "Pure White": ("FEAS", "SM. Fehér", "Pure White"),
            "Mist Grey": ("GFAS", "SM. Grafit", "Mist Grey"),
            "Dune Beige": ("KAF", "KAFS", "Kasmír", "Kasmír matt", "Matt Kasmír", "SM. Kasmír", "Dune Beige"),
            "Cedar Green": ("PRAS", "SM. Provance", "SM. Provence", "Cedar Green", "Cedar Green SM"),
            "Palo Santo Beige": ("BGAS", "SM. Beige", "Palo Santo Beige"),
            "Matt Mussel": ("BGA", "Matt Beige", "Matt Mussel", "Matt Mussell"),
            "Matt Stone Grey": ("CPA", "Matt Capuccino", "Matt Cappuccino", "Matt Stone Grey"),
        }
        for counterpart, aliases in groups.items():
            for alias in aliases:
                names[_key(alias)] = counterpart
        for counterpart in set(names.values()):
            names[_key(counterpart)] = counterpart
        for model in models:
            catalog[_key(model)] = names
    return catalog
