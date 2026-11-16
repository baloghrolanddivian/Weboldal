"""Connector orientations from the supplied cabinet-family reference photo."""

from __future__ import annotations

import re

ASSET_URL_PREFIX = "/assets/part-workstation/connectors/"

# All groups are prefixes except AR20, which is an exact item code. The
# specific vertical AS groups precede the broader horizontal AS prefix.
CONNECTOR_RULES = (
    {
        "pattern": r"^(?:AMO|ASZB|ASZH|ASM).*$",
        "orientation": "Függőleges",
        "image_url": ASSET_URL_PREFIX + "vertical.png",
    },
    {
        "pattern": r"^(?:(?:AML|AKL|AAF|AF|AS).*|AR20)$",
        "orientation": "Vízszintes",
        "image_url": ASSET_URL_PREFIX + "horizontal.png",
    },
)


def connector_for_part(part_number: object) -> dict | None:
    """Return no connector for cabinets outside the supplied model groups."""
    code = str(part_number or "").strip().upper()
    return next((rule for rule in CONNECTOR_RULES if re.fullmatch(rule["pattern"], code)), None)
