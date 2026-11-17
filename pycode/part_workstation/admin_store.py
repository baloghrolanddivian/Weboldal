"""Read and edit item notes in the original production XML."""

from __future__ import annotations

import hashlib
from copy import deepcopy
import os
from pathlib import Path
import re
import tempfile
import threading
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

from . import production_xml

MAX_NOTE_LENGTH = 500
RECENT_PRODUCTION_LIMIT = 12
RECENT_PRODUCTION_FIRST_ID = 14657
_FILE_LOCK = threading.RLock()
_NOTE_CACHE: dict[Path, tuple[tuple[int, int, int], dict]] = {}


class ProductionConflict(ValueError):
    """The production file changed after the editor loaded it."""


def _production_path(production_id: object) -> tuple[str, Path]:
    number = str(production_id or "").strip()
    if not re.fullmatch(r"[0-9]{1,20}", number) or int(number) <= 0:
        raise ValueError("Érvénytelen gyártási azonosító.")
    return number, production_xml.production_folder(number) / production_xml.XML_FILENAME


def _parse(source: bytes) -> minidom.Document:
    try:
        return minidom.parseString(source)
    except ExpatError as exc:
        raise ValueError("A gyártási XML hibás, nem szerkeszthető.") from exc


def _children(node: Node) -> list:
    return [child for child in node.childNodes if child.nodeType == Node.ELEMENT_NODE]


def _name(node: Node) -> str:
    return node.localName or node.nodeName


def _text(node: Node) -> str:
    return "".join(child.data for child in node.childNodes if child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE)).strip()


def _records(document: minidom.Document) -> list:
    return [node for node in _children(document.documentElement) if _name(node) == "CON"]


def _note(fields: dict[str, str]) -> str:
    feature_note = ""
    for name, label in fields.items():
        match = re.fullmatch(r"FeatureBillTranslation(\d+)", name)
        if match and label == "Megjegyzés":
            suffix = match.group(1)
            feature_note = next((fields.get(prefix + suffix, "") for prefix in ("ertek", "OptionValue", "OptionDescription") if fields.get(prefix + suffix, "")), "")
    return feature_note or fields.get("Megjegyzes") or fields.get("Megjegyzés", "")


def _payload(number: str, source: bytes, document: minidom.Document) -> dict:
    items = []
    for index, record in enumerate(_records(document)):
        fields = {_name(child): _text(child) for child in _children(record)}
        items.append({
            "production_id": number,
            "row_id": str(index),
            "con_id": fields.get("Barcode") or fields.get("conID") or fields.get("CONID", ""),
            "part_number": fields.get("pdCode", ""),
            "ordOrderNo": fields.get("ordOrderNo", ""),
            "notes": _note(fields),
        })
    return {"production_id": number, "revision": hashlib.sha256(source).hexdigest(), "items": items}


def load_production_notes(production_id: object) -> dict:
    """List all CON records, including records with no note or a repeated barcode."""
    number, path = _production_path(production_id)
    with _FILE_LOCK:
        return _load_notes(number, path, cache=path in _NOTE_CACHE)


def _signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size


def _load_notes(number: str, path: Path, *, cache: bool) -> dict:
    """Cache only detached admin summaries; scanners never use this cache."""
    signature = _signature(path)
    entry = _NOTE_CACHE.get(path)
    if entry is not None and entry[0] == signature:
        return deepcopy(entry[1])
    _NOTE_CACHE.pop(path, None)
    source = path.read_bytes()
    with _parse(source) as document:
        payload = _payload(number, source, document)
    if cache and _signature(path) == signature:
        _NOTE_CACHE[path] = signature, payload
    return deepcopy(payload)


def load_recent_production_notes() -> dict:
    """Load the latest twelve XML-bearing productions from 14657 onwards."""
    root = production_xml.production_folder(str(RECENT_PRODUCTION_FIRST_ID)).parent
    with _FILE_LOCK:
        folders = sorted(
            (folder for folder in root.iterdir()
             if re.fullmatch(r"[0-9]{1,20}", folder.name)
             and int(folder.name) >= RECENT_PRODUCTION_FIRST_ID and folder.is_dir()),
            key=lambda folder: int(folder.name), reverse=True,
        )
        productions, items, warnings = [], [], []
        selected = set()
        for folder in folders:
            path = folder / production_xml.XML_FILENAME
            try:
                data = _load_notes(folder.name, path, cache=True)
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                warnings.append({"production_id": folder.name, "error": "A gyártási XML nem olvasható."})
                continue
            selected.add(path)
            productions.append({"production_id": data["production_id"], "revision": data["revision"]})
            items.extend(data["items"])
            if len(productions) == RECENT_PRODUCTION_LIMIT:
                break
        for path in set(_NOTE_CACHE) - selected:
            del _NOTE_CACHE[path]
        return {"production_id": "", "revision": "", "recent": True,
                "productions": productions, "items": items, "warnings": warnings}


def _set_text(node: Node, value: str) -> None:
    for child in list(node.childNodes):
        node.removeChild(child)
        child.unlink()
    node.appendChild(node.ownerDocument.createTextNode(value))


def _append_field(record: Node, name: str, value: str) -> None:
    prefix = f"{record.prefix}:" if record.prefix else ""
    field = record.ownerDocument.createElementNS(record.namespaceURI, prefix + name)
    _set_text(field, value)
    record.appendChild(field)


def _set_note(record: Node, value: str) -> None:
    children = _children(record)
    tags = {_name(child): child for child in children}
    found = False
    for child in children:
        if _name(child) in {"Megjegyzes", "Megjegyzés"}:
            _set_text(child, value)
            found = True
        match = re.fullmatch(r"FeatureBillTranslation(\d+)", _name(child))
        if match and _text(child) == "Megjegyzés":
            found = True
            suffix = match.group(1)
            if "ertek" + suffix not in tags:
                _append_field(record, "ertek" + suffix, value)
            # Keep every fallback in sync so clearing a note cannot revive an old value.
            for prefix in ("ertek", "OptionValue", "OptionDescription"):
                if prefix + suffix in tags:
                    _set_text(tags[prefix + suffix], value)
    if not found:
        # Follow the source export's numbered feature/value format, using a free slot.
        used = {int(match.group(1)) for name in tags
                if (match := re.fullmatch(r"(?:FeatureBillTranslation|ertek|OptionValue|OptionDescription)(\d+)", name))}
        slot = 1
        while slot in used:
            slot += 1
        suffix = f"{slot:02d}"
        _append_field(record, "FeatureBillTranslation" + suffix, "Megjegyzés")
        _append_field(record, "ertek" + suffix, value)


def _replace_source(path: Path, original: bytes, updated: bytes) -> None:
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        if path.read_bytes() != original:
            raise ProductionConflict("A gyártási fájl időközben megváltozott. Nyisd meg újra a gyártást a mentés előtt.")
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def save_production_notes(production_id: object, revision: object, changes: object) -> dict:
    """Validate all edits before atomically replacing the same production file."""
    number, path = _production_path(production_id)
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("Hiányzó vagy érvénytelen fájlverzió. Nyisd meg újra a gyártást.")
    if not isinstance(changes, list) or not changes:
        raise ValueError("Nincs mentendő módosítás.")
    edits = {}
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("Hibás megjegyzésmódosítás.")
        row_id, note = change.get("row_id"), change.get("notes")
        if not isinstance(row_id, str) or not re.fullmatch(r"0|[1-9][0-9]*", row_id) or row_id in edits:
            raise ValueError("Érvénytelen vagy ismétlődő tételazonosító.")
        if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
            raise ValueError(f"A megjegyzés legfeljebb {MAX_NOTE_LENGTH} karakter lehet.")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", note):
            raise ValueError("A megjegyzés nem engedélyezett karaktert tartalmaz.")
        edits[row_id] = note.strip()
    with _FILE_LOCK:
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != revision:
            raise ProductionConflict("A gyártási fájl időközben megváltozott. Nyisd meg újra a gyártást a mentés előtt.")
        with _parse(original) as document:
            records = _records(document)
            if any(int(row_id) >= len(records) for row_id in edits):
                raise ValueError("A módosított tétel nem található a gyártásban.")
            for row_id, note in edits.items():
                _set_note(records[int(row_id)], note)
            updated = document.toxml(encoding=document.encoding or "utf-8", standalone=document.standalone)
            _replace_source(path, original, updated)
            payload = _payload(number, updated, document)
            _NOTE_CACHE.pop(path, None)
            return payload
