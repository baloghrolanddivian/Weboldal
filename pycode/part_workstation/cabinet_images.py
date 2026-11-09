"""Catalog of cabinet drawings bundled with the application as static assets."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


ASSET_DIRECTORY = Path(__file__).resolve().parents[2] / "assets" / "part-workstation" / "cabinets"
ASSET_URL_PREFIX = "/assets/part-workstation/cabinets/"


def cabinet_image_catalog() -> dict[str, str]:
    """Expose asset URLs by model code without loading the image contents."""
    return {
        path.stem.upper(): ASSET_URL_PREFIX + quote(path.name)
        for path in sorted(ASSET_DIRECTORY.glob("*"))
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
