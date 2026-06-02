"""Datetime formatting helpers for UI labels."""

from __future__ import annotations

from datetime import datetime


def format_hungarian_timestamp(value: str) -> str:
    """Format an ISO timestamp as yyyy.mm.dd. hh:mm, preserving unknown values."""
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    try:
        parsed = datetime.fromisoformat(clean_value)
    except ValueError:
        return clean_value
    return parsed.strftime("%Y.%m.%d. %H:%M")

