"""Multipart request parsing for damaged-item reports."""

from __future__ import annotations

import re


def parse_multipart(headers, body: bytes) -> tuple[dict[str, str], dict[str, list[tuple[str, str, bytes]]]]:
    """Return text fields and files from one multipart form request."""
    content_type = headers.get("Content-Type", "")
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
    if "multipart/form-data" not in content_type or not boundary_match:
        return {}, {}
    boundary = boundary_match.group(1).encode("utf-8")
    fields: dict[str, str] = {}
    files: dict[str, list[tuple[str, str, bytes]]] = {}
    for part in body.split(b"--" + boundary):
        raw_headers, separator, payload = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        payload = payload.rsplit(b"\r\n", 1)[0]
        field_match = re.search(br'name="([^"]+)"', raw_headers)
        if not field_match:
            continue
        field_name = field_match.group(1).decode("utf-8", errors="replace")
        file_match = re.search(br'filename="([^"]*)"', raw_headers)
        if file_match:
            file_name = file_match.group(1).decode("utf-8", errors="replace")
            type_match = re.search(br"Content-Type:\s*([^\r\n]+)", raw_headers, flags=re.IGNORECASE)
            file_type = type_match.group(1).decode("ascii", errors="ignore").strip() if type_match else ""
            if file_name and payload:
                files.setdefault(field_name, []).append((file_name, file_type, payload))
            continue
        fields[field_name] = payload.decode("utf-8", errors="replace")
    return fields, files
