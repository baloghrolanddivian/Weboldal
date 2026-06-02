"""Form and query-string parsing helpers for vacation calendar requests."""

from __future__ import annotations

import urllib.parse

def _vacation_parse_int(value: str, default: int | None = None) -> int | None:
    """Parse an integer form value, returning default on invalid input."""
    try:
        return int(value.strip())
    except (TypeError, ValueError, AttributeError):
        return default

def _vacation_parse_form(raw_body: bytes) -> dict[str, list[str]]:
    """Parse an URL-encoded request body into a multi-value form mapping."""
    parsed = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return {key: value for key, value in parsed.items()}

def _vacation_form_value(form_data: dict[str, list[str]], name: str) -> str:
    """Return the last stripped value for a form field."""
    values = form_data.get(name, [])
    return values[-1].strip() if values else ""

def _vacation_form_values(form_data: dict[str, list[str]], name: str) -> list[str]:
    """Return all non-empty stripped values for a repeated form field."""
    return [value.strip() for value in form_data.get(name, []) if value.strip()]

def _vacation_query_params(raw_path: str) -> dict[str, str]:
    """Parse scalar query parameters from a raw request path."""
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}

