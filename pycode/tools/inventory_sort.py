"""Sorting helpers for inventory worker tables."""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation


def normalize_inventory_sort(value: object) -> str:
    """Normalize inventory table sort keys to a supported value."""
    clean_value = str(value or "").strip().lower()
    allowed = {"default", "description", "description_desc", "book_qty", "book_qty_desc", "color", "color_desc", "count", "count_desc"}
    return clean_value if clean_value in allowed else "default"


def inventory_sort_key(row: dict, sort_key: str) -> tuple:
    """Build a sortable tuple for an inventory row."""
    if sort_key == "book_qty":
        return (_inventory_decimal(row.get("book_qty")), clean_sort_text(row.get("description", "")))
    if sort_key == "color":
        return (clean_sort_text(row.get("icg_code", "")), clean_sort_text(row.get("description", "")))
    if sort_key == "count":
        return (_inventory_decimal(row.get("counted_qty", row.get("input_qty", ""))), clean_sort_text(row.get("description", "")))
    return (clean_sort_text(row.get("description", "")), clean_sort_text(row.get("part_number", "")))


def clean_sort_text(value: object) -> str:
    """Normalize text for stable case-insensitive sorting."""
    return unicodedata.normalize("NFKD", str(value or "").strip()).casefold()


def _inventory_decimal(value: object) -> Decimal:
    """Parse an inventory quantity for stable numeric sorting."""
    clean_value = str(value or "").strip().replace(",", ".")
    if not clean_value:
        return Decimal("0")
    try:
        return Decimal(clean_value)
    except InvalidOperation:
        return Decimal("0")

