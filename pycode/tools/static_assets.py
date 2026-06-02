"""Static file loading helpers for local assets."""

from __future__ import annotations

import mimetypes
from pathlib import Path


def load_static_asset(base_dir: Path, path: str) -> tuple[bytes, str] | None:
    """Load a static asset below base_dir and return body plus content type."""
    if path in {"", "/"}:
        file_path = base_dir / "index.html"
    else:
        relative = path.lstrip("/")
        if not relative or ".." in Path(relative).parts:
            return None
        file_path = (base_dir / relative).resolve()
        try:
            file_path.relative_to(base_dir)
        except ValueError:
            return None

    if not file_path.is_file():
        return None

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if file_path.suffix.lower() in {".html", ".css", ".js", ".json", ".txt", ".svg"}:
        content_type = f"{content_type}; charset=utf-8"
    return file_path.read_bytes(), content_type

