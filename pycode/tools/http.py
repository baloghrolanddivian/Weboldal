"""HTTP request parsing helpers for the built-in web server."""

from __future__ import annotations

import re
import urllib.parse


def normalize_path(raw_path: str) -> str:
    """Return the decoded request path without query string."""
    return urllib.parse.unquote(urllib.parse.urlsplit(raw_path).path)


def extract_uploaded_file_parts(headers, body: bytes) -> list[tuple[str, str, bytes]]:
    """Extract all multipart file parts as field name, file name, and bytes."""
    content_type = headers.get("Content-Type", "")
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
    if "multipart/form-data" not in content_type or not boundary_match:
        return []

    boundary = boundary_match.group(1).encode()
    parts: list[tuple[str, str, bytes]] = []
    for part in body.split(b"--" + boundary):
        header, _, payload = part.partition(b"\r\n\r\n")
        if not payload:
            continue

        payload = payload.rsplit(b"\r\n", 1)[0]
        field_match = re.search(br'name="([^"]+)"', header)
        if not field_match:
            continue

        field_name = field_match.group(1).decode("utf-8", errors="ignore")
        name_match = re.search(br'filename="([^"]*)"', header)
        file_name = name_match.group(1).decode("utf-8", errors="ignore") if name_match else ""
        if file_name and payload:
            parts.append((field_name, file_name, payload))

    return parts


def extract_uploaded_files(headers, body: bytes) -> dict[str, tuple[str, bytes]]:
    """Extract the first uploaded file for each multipart field."""
    files: dict[str, tuple[str, bytes]] = {}
    for field_name, file_name, payload in extract_uploaded_file_parts(headers, body):
        if field_name not in files:
            files[field_name] = (file_name, payload)
    return files


def parse_urlencoded_body(body: bytes) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body into scalar values."""
    try:
        payload = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        payload = urllib.parse.parse_qs(body.decode("latin1"), keep_blank_values=True)
    return {key: values[-1] for key, values in payload.items() if values}

