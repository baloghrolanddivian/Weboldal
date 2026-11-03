"""Persistent storage for damaged-item remake reports."""

from __future__ import annotations

import json
import mimetypes
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path


_runtime_dir = Path("runtime") / "serult-elemek"
_lock = threading.RLock()
_allowed_image_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_allowed_image_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def configure_damaged_items(runtime_dir: Path) -> None:
    """Configure the runtime folder used by the module."""
    global _runtime_dir
    _runtime_dir = Path(runtime_dir)


def list_reports() -> list[dict]:
    """Return reports newest first."""
    with _lock:
        reports = _read_reports()
    return sorted(reports, key=lambda item: str(item.get("created_at", "")), reverse=True)


def create_report(
    *,
    created_by: str,
    note: str,
    responsible_person: str,
    images: list[tuple[str, str, bytes]],
    barcode: str = "",
    part_number: str = "",
    description: str = "",
    order_number: str = "",
    production_number: str = "",
) -> dict:
    """Validate and persist one damaged-item report."""
    clean_note = _clean_text(note)
    clean_responsible_person = _clean_text(responsible_person)
    clean_created_by = _clean_text(created_by)
    if not clean_note:
        raise ValueError("A megjegyzés megadása kötelező.")
    if not clean_responsible_person:
        raise ValueError("A sérülésért felelős személy megadása kötelező.")
    if not clean_created_by:
        raise ValueError("A rögzítő személy megadása kötelező.")
    if not images:
        raise ValueError("Legalább egy, a sérülésről készült kép feltöltése kötelező.")

    report_id = secrets.token_hex(8)
    stored_images: list[dict[str, str]] = []
    validated_images: list[tuple[str, bytes]] = []
    for index, (image_name, image_content_type, image_body) in enumerate(images):
        if not image_body:
            raise ValueError("Minden kiválasztott képnek tartalmaznia kell adatot.")
        if len(image_body) > MAX_IMAGE_BYTES:
            raise ValueError("Egy feltöltött kép legfeljebb 12 MB lehet.")
        original_suffix = Path(image_name or "").suffix.lower()
        clean_content_type = str(image_content_type or "").split(";", 1)[0].strip().lower()
        if clean_content_type not in _allowed_image_types and original_suffix not in _allowed_image_suffixes:
            raise ValueError("Csak JPG, PNG, WEBP vagy HEIC kép tölthető fel.")
        suffix = original_suffix if original_suffix in _allowed_image_suffixes else _suffix_for_type(clean_content_type)
        stored_image_name = f"{report_id}-{index + 1}{suffix}"
        content_type = clean_content_type or mimetypes.guess_type(stored_image_name)[0] or "application/octet-stream"
        stored_images.append({"name": stored_image_name, "content_type": content_type, "original_name": _clean_text(image_name)})
        validated_images.append((stored_image_name, image_body))

    report = {
        "id": report_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "created_by": clean_created_by,
        "status": "remake_required",
        "note": clean_note,
        "responsible_person": clean_responsible_person,
        "images": stored_images,
        "item": {
            "barcode": _clean_text(barcode),
            "part_number": _clean_text(part_number),
            "description": _clean_text(description),
            "order_number": _clean_text(order_number),
            "production_number": _clean_text(production_number),
        },
    }

    with _lock:
        _runtime_dir.mkdir(parents=True, exist_ok=True)
        image_dir = _runtime_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        for stored_image_name, image_body in validated_images:
            (image_dir / stored_image_name).write_bytes(image_body)
        reports = _read_reports()
        reports.append(report)
        _write_reports(reports)
    return report


def delete_report(report_id: str) -> bool:
    """Delete one report and its stored image."""
    clean_id = _clean_identifier(report_id)
    if not clean_id:
        return False
    with _lock:
        reports = _read_reports()
        target = next((item for item in reports if str(item.get("id", "")) == clean_id), None)
        if target is None:
            return False
        _write_reports([item for item in reports if str(item.get("id", "")) != clean_id])
        for image in _report_images(target):
            image_name = Path(str(image.get("name", ""))).name
            image_path = _runtime_dir / "images" / image_name
            if image_name and image_path.is_file():
                image_path.unlink()
    return True


def report_image(report_id: str, image_index: int = 0) -> tuple[bytes, str] | None:
    """Return an image body and content type for one report."""
    clean_id = _clean_identifier(report_id)
    if not clean_id:
        return None
    with _lock:
        report = next((item for item in _read_reports() if str(item.get("id", "")) == clean_id), None)
        if report is None:
            return None
        images = _report_images(report)
        if image_index < 0 or image_index >= len(images):
            return None
        image = images[image_index]
        image_name = Path(str(image.get("name", ""))).name
        image_path = _runtime_dir / "images" / image_name
        if not image_name or not image_path.is_file():
            return None
        content_type = str(image.get("content_type", "")).strip() or "application/octet-stream"
        return image_path.read_bytes(), content_type


def _report_images(report: dict) -> list[dict[str, str]]:
    """Return normalized image metadata, including legacy single-image reports."""
    images = report.get("images")
    if isinstance(images, list):
        return [item for item in images if isinstance(item, dict) and str(item.get("name", "")).strip()]
    legacy_name = str(report.get("image_name", "")).strip()
    if not legacy_name:
        return []
    return [{"name": legacy_name, "content_type": str(report.get("image_content_type", ""))}]


def _reports_path() -> Path:
    return _runtime_dir / "reports.json"


def _read_reports() -> list[dict]:
    path = _reports_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _write_reports(reports: list[dict]) -> None:
    _runtime_dir.mkdir(parents=True, exist_ok=True)
    path = _reports_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_identifier(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-f0-9]{16}", text) else ""


def _suffix_for_type(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }.get(content_type, ".jpg")
