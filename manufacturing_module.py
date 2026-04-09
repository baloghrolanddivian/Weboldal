from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency handling
    PdfReader = None


MANUFACTURING_ROOT = Path(os.getenv("DIVIAN_MANUFACTURING_ROOT", r"J:\inSightData\Output\Gyartasi_papirok"))
MANUFACTURING_ENTRIES_CACHE_LOCK = threading.Lock()
MANUFACTURING_ENTRIES_CACHE: dict[tuple[int, bool], dict[str, object]] = {}
MANUFACTURING_DATE_LABEL_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_ENTRIES_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class ManufacturingRow:
    row_id: str
    name: str
    detail: str
    size: str
    color: str
    edge: str
    quantity: int
    code: str
    doc_key: str
    section_key: str
    section_label: str
    page_number: int


@dataclass(frozen=True)
class ManufacturingSection:
    key: str
    label: str
    rows: tuple[ManufacturingRow, ...]


@dataclass(frozen=True)
class ManufacturingDocument:
    key: str
    label: str
    file_name: str
    sections: tuple[ManufacturingSection, ...]
    row_count: int


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slugify(value: str) -> str:
    cleaned = _clean_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "szakasz"


def _row_hash(*parts: str) -> str:
    payload = "||".join(_clean_text(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _pair_info_for_section_label(label: str) -> tuple[str, str] | None:
    text = _clean_text(label)
    if text.startswith("1-es "):
        return ("1", text[5:])
    if text.startswith("2-es "):
        return ("2", text[5:])
    return None


def _pair_sections_in_display_order(sections: list[ManufacturingSection]) -> list[ManufacturingSection]:
    if not sections:
        return []
    by_label = {_clean_text(section.label): section for section in sections}
    used: set[str] = set()
    ordered: list[ManufacturingSection] = []

    for section in sections:
        if section.key in used:
            continue
        pair_info = _pair_info_for_section_label(section.label)
        if pair_info and pair_info[0] == "2":
            first_pair = by_label.get(f"1-es {pair_info[1]}")
            if first_pair and first_pair.key not in used:
                continue
        used.add(section.key)
        ordered.append(section)
        if pair_info and pair_info[0] == "1":
            second_pair = by_label.get(f"2-es {pair_info[1]}")
            if second_pair and second_pair.key not in used:
                used.add(second_pair.key)
                ordered.append(second_pair)

    for section in sections:
        if section.key in used:
            continue
        used.add(section.key)
        ordered.append(section)

    return ordered


def _pdf_lines(path: Path) -> list[list[str]]:
    if PdfReader is None:
        raise RuntimeError("A gyártási PDF-ek olvasásához a pypdf csomag szükséges.")

    reader = PdfReader(str(path))
    pages: list[list[str]] = []
    for page in reader.pages:
        raw_text = page.extract_text() or ""
        lines = [_clean_text(line) for line in raw_text.splitlines()]
        lines = [line for line in lines if line]
        pages.append(lines)
    return pages


def _pdf_first_page_lines(path: Path) -> list[str]:
    if PdfReader is None:
        raise RuntimeError("A gyártási PDF-ek olvasásához a pypdf csomag szükséges.")
    reader = PdfReader(str(path))
    if not reader.pages:
        return []
    raw_text = reader.pages[0].extract_text() or ""
    lines = [_clean_text(line) for line in raw_text.splitlines()]
    return [line for line in lines if line]


def _find_osszekeszito_path(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if "sszek" in name and "front" not in name and "hettich" not in name:
            return path
    return None


def _find_alkatresz_kesz_path(folder: Path) -> Path | None:
    candidate = folder / "Alkatresz_kesz.pdf"
    if candidate.exists():
        return candidate
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.name.lower() == "alkatresz_kesz.pdf":
            return path
    return None


def _find_front_osszekeszito_path(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if "front" in name and "sszek" in name and "hettich" not in name:
            return path
    return None


def _find_cnc_path(folder: Path) -> Path | None:
    candidate = folder / "CNC.pdf"
    if candidate.exists():
        return candidate
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.name.lower() == "cnc.pdf":
            return path
    return None


def _find_fiokelo_furas_path(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if "fiokelo" in name and "furas" in name:
            return path
    return None


def has_required_manufacturing_pdfs(folder: Path) -> bool:
    return _find_osszekeszito_path(folder) is not None and _find_alkatresz_kesz_path(folder) is not None


def _entries_cache_signature() -> tuple[tuple[str, int], ...]:
    if not MANUFACTURING_ROOT.exists():
        return tuple()
    entries: list[tuple[str, int]] = []
    for item in MANUFACTURING_ROOT.iterdir():
        if not item.is_dir() or not item.name.isdigit():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append((item.name, stat.st_mtime_ns))
    entries.sort(key=lambda pair: int(pair[0]), reverse=True)
    return tuple(entries[:200])


def _production_pdf_signature(folder: Path) -> tuple[tuple[str, int, int], ...]:
    signatures: list[tuple[str, int, int]] = []
    for path in (_find_osszekeszito_path(folder), _find_alkatresz_kesz_path(folder), _find_front_osszekeszito_path(folder)):
        if path is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        signatures.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(signatures)


def _production_date_label_cached(folder: Path) -> str:
    signature = _production_pdf_signature(folder)
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_DATE_LABEL_CACHE.get(str(folder))
        if cached and cached.get("signature") == signature:
            return str(cached.get("value", ""))
    value = _production_date_label(folder)
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        MANUFACTURING_DATE_LABEL_CACHE[str(folder)] = {"signature": signature, "value": value}
    return value


def available_production_entries(limit: int = 60, ready_only: bool = False) -> list[dict[str, str]]:
    cache_key = (int(limit), bool(ready_only))
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_ENTRIES_CACHE.get(cache_key)
        if cached and (time.time() - float(cached.get("created_at", 0.0) or 0.0)) < MANUFACTURING_ENTRIES_CACHE_TTL_SECONDS:
            return [dict(item) for item in cached.get("entries", []) if isinstance(item, dict)]
    signature = _entries_cache_signature()
    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        cached = MANUFACTURING_ENTRIES_CACHE.get(cache_key)
        if cached and cached.get("signature") == signature:
            return [dict(item) for item in cached.get("entries", []) if isinstance(item, dict)]

    if not MANUFACTURING_ROOT.exists():
        return []

    candidates = [path for path in MANUFACTURING_ROOT.iterdir() if path.is_dir() and path.name.isdigit()]
    candidates.sort(key=lambda path: int(path.name), reverse=True)

    entries: list[dict[str, str]] = []
    for folder in candidates:
        if ready_only and not has_required_manufacturing_pdfs(folder):
            continue
        entries.append(
            {
                "number": folder.name,
                "date_label": _production_date_label_cached(folder),
            }
        )
        if len(entries) >= limit:
            break

    with MANUFACTURING_ENTRIES_CACHE_LOCK:
        MANUFACTURING_ENTRIES_CACHE[cache_key] = {
            "signature": signature,
            "created_at": time.time(),
            "entries": [dict(item) for item in entries],
        }
    return entries


def _extract_production_date_label(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if "Termelési rendelés dátuma" not in line:
            continue
        window = [line]
        if index + 1 < len(lines):
            window.append(lines[index + 1])
        joined = " ".join(window)
        match = re.search(r"\b(\d{4}\.\d{2}\.\d{2})\b", joined)
        if match:
            return f"{match.group(1)}."
    for line in lines[:12]:
        match = re.search(r"\b(\d{4}\.\d{2}\.\d{2})\b", line)
        if match:
            return f"{match.group(1)}."
    return ""


def _production_date_label(folder: Path) -> str:
    for candidate in (_find_osszekeszito_path(folder), _find_alkatresz_kesz_path(folder)):
        if candidate is None:
            continue
        try:
            lines = _pdf_first_page_lines(candidate)
        except Exception:
            continue
        date_label = _extract_production_date_label(lines)
        if date_label:
            return date_label
    return ""
def available_production_numbers(limit: int = 60, ready_only: bool = False) -> list[str]:
    return [str(item.get("number", "")) for item in available_production_entries(limit=limit, ready_only=ready_only) if str(item.get("number", "")).isdigit()]


def latest_production_number() -> str:
    numbers = available_production_numbers(limit=1, ready_only=True)
    return numbers[0] if numbers else ""


def production_folder(production_number: str) -> Path:
    return MANUFACTURING_ROOT / production_number.strip()


def _footer_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if re.fullmatch(r"Oldal \d+/\d+", _clean_text(line)):
            return index
    return len(lines)


def _looks_like_dimension_start(tokens: list[str], index: int) -> bool:
    if index + 4 >= len(tokens):
        return False
    return (
        re.fullmatch(r"\d{1,4}", tokens[index]) is not None
        and tokens[index + 1].lower() == "x"
        and re.fullmatch(r"\d{1,4}", tokens[index + 2]) is not None
        and tokens[index + 3].lower() == "x"
        and re.fullmatch(r"\d{1,4}", tokens[index + 4]) is not None
    )


def _consume_dimension(tokens: list[str], index: int) -> tuple[str, int]:
    if not _looks_like_dimension_start(tokens, index):
        return "", index
    return f"{tokens[index]} x {tokens[index + 2]} x {tokens[index + 4]}", index + 5


def _looks_like_edge(token: str) -> bool:
    return re.fullmatch(r"(?:N|\d+[HR](?:\d+[HR])*|[A-Z]{2,4})", token) is not None


def _is_final_code(token: str) -> bool:
    return re.fullmatch(r"CON\d{6,}", token) is not None


def _looks_like_code_fragment(token: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9_/-]+", token):
        return False
    return "_" in token or any(character.isalpha() for character in token)


def _parse_osszekeszito_rows(tokens: list[str], section_label: str, page_number: int) -> list[ManufacturingRow]:
    rows: list[ManufacturingRow] = []
    section_key = _slugify(section_label)
    index = 0
    row_index = 0

    while index < len(tokens):
        while index < len(tokens) and tokens[index] in {"-", ","}:
            index += 1
        if index >= len(tokens):
            break

        name_parts: list[str] = []
        while index < len(tokens) and tokens[index] != ",":
            name_parts.append(tokens[index])
            index += 1
        if index >= len(tokens):
            break
        name = _clean_text(" ".join(name_parts))
        index += 1

        detail_parts: list[str] = []
        while index < len(tokens) and not _looks_like_dimension_start(tokens, index):
            detail_parts.append(tokens[index])
            index += 1
        size, index = _consume_dimension(tokens, index)
        if not size:
            break

        color_parts: list[str] = []
        edge = "-"
        while index < len(tokens):
            token = tokens[index]
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            if _looks_like_edge(token) and re.fullmatch(r"\d+", next_token):
                edge = token
                index += 1
                break
            if re.fullmatch(r"\d+", token):
                break
            color_parts.append(token)
            index += 1

        if index >= len(tokens) or re.fullmatch(r"\d+", tokens[index]) is None:
            break
        quantity = int(tokens[index])
        index += 1

        code = ""
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if _is_final_code(token):
                code = token
                break

        row_index += 1
        row = ManufacturingRow(
            row_id=_row_hash("osszekeszito", section_label, code, name, size, str(row_index)),
            name=name,
            detail=_clean_text(" ".join(detail_parts)),
            size=size,
            color=_clean_text(" ".join(color_parts)),
            edge=edge,
            quantity=quantity,
            code=code,
            doc_key="osszekeszito",
            section_key=section_key,
            section_label=section_label,
            page_number=page_number,
        )
        rows.append(row)

    return rows


def parse_osszekeszito(path: Path) -> ManufacturingDocument:
    pages = _pdf_lines(path)
    sections: list[ManufacturingSection] = []
    current_label = "Összes"
    current_rows: list[ManufacturingRow] = []
    current_key = _slugify(current_label)

    for page_number, lines in enumerate(pages, start=1):
        footer_index = _footer_index(lines)
        content_lines = lines[:footer_index]
        if not content_lines:
            continue

        if content_lines[0] == "Alkatrész kivételezés":
            try:
                header_end = content_lines.index("Menny.")
            except ValueError:
                header_end = 17
            tokens = content_lines[header_end + 1 :]
            if len(tokens) >= 3 and tokens[1] == "-":
                next_label = f"{tokens[0]} - {tokens[2]}"
                if current_rows:
                    sections.append(
                        ManufacturingSection(
                            key=current_key,
                            label=current_label,
                            rows=tuple(current_rows),
                        )
                    )
                current_label = next_label
                current_key = _slugify(current_label)
                current_rows = []
                tokens = tokens[3:]
            rows = _parse_osszekeszito_rows(tokens, current_label, page_number)
        else:
            rows = _parse_osszekeszito_rows(content_lines, current_label, page_number)

        current_rows.extend(rows)

    if current_rows:
        sections.append(ManufacturingSection(key=current_key, label=current_label, rows=tuple(current_rows)))
    sections = _pair_sections_in_display_order([section for section in sections if section.rows])

    return ManufacturingDocument(
        key="osszekeszito",
        label="Összekészítő",
        file_name=path.name,
        sections=tuple(sections),
        row_count=sum(len(section.rows) for section in sections),
    )


def _parse_alkatresz_rows(tokens: list[str], page_number: int) -> list[ManufacturingRow]:
    rows: list[ManufacturingRow] = []
    row_index = 0

    start_index = 0
    while start_index < len(tokens) and not _looks_like_code_fragment(tokens[start_index]):
        start_index += 1
    working_tokens = tokens[start_index:]

    segments: list[list[str]] = []
    current_segment: list[str] = []
    for token in working_tokens:
        current_segment.append(token)
        if _is_final_code(token):
            segments.append(current_segment)
            current_segment = []

    for segment in segments:
        if len(segment) < 8:
            continue
        intake_code = segment[-1]
        quantity_index = -1
        edge_index = -1
        for index in range(len(segment) - 2, -1, -1):
            token = segment[index]
            if quantity_index == -1 and re.fullmatch(r"\d+", token):
                quantity_index = index
                continue
            if quantity_index != -1 and edge_index == -1 and _looks_like_edge(token):
                edge_index = index
                break
        if quantity_index == -1 or edge_index == -1:
            continue

        dimension_index = -1
        for index in range(0, edge_index):
            if _looks_like_dimension_start(segment, index):
                dimension_index = index
                break
        if dimension_index == -1:
            continue

        code_parts: list[str] = []
        name_start_index = 0
        while name_start_index < dimension_index and _looks_like_code_fragment(segment[name_start_index]):
            code_parts.append(segment[name_start_index])
            name_start_index += 1
        if not code_parts:
            continue
        raw_code = "".join(code_parts)

        name_parts = segment[name_start_index:dimension_index]
        size, _ = _consume_dimension(segment, dimension_index)
        if not size:
            continue

        color_parts = segment[dimension_index + 5 : edge_index]
        section_label = _clean_text(" ".join(name_parts))
        if not section_label:
            continue

        row_index += 1
        rows.append(
            ManufacturingRow(
                row_id=_row_hash("alkatresz", section_label, raw_code, size, str(row_index)),
                name=section_label,
                detail=raw_code,
                size=size,
                color=_clean_text(" ".join(color_parts)),
                edge=segment[edge_index],
                quantity=int(segment[quantity_index]),
                code=intake_code or raw_code,
                doc_key="alkatresz_kesz",
                section_key=_slugify(section_label),
                section_label=section_label,
                page_number=page_number,
            )
        )

    return rows


def parse_alkatresz_kesz(path: Path) -> ManufacturingDocument:
    pages = _pdf_lines(path)
    section_map: dict[str, list[ManufacturingRow]] = {}

    for page_number, lines in enumerate(pages, start=1):
        footer_index = _footer_index(lines)
        content_lines = lines[:footer_index]
        if not content_lines:
            continue

        if content_lines[0] == "Alkatrész bevételezés":
            try:
                header_end = content_lines.index("ME")
            except ValueError:
                header_end = 17
            tokens = content_lines[header_end + 1 :]
        else:
            tokens = content_lines

        for row in _parse_alkatresz_rows(tokens, page_number):
            section_map.setdefault(row.section_label, []).append(row)

    sections = [
        ManufacturingSection(
            key=_slugify(section_label),
            label=section_label,
            rows=tuple(rows),
        )
        for section_label, rows in sorted(section_map.items(), key=lambda item: item[0].lower())
    ]
    return ManufacturingDocument(
        key="alkatresz_kesz",
        label="Alkatrész kész",
        file_name=path.name,
        sections=tuple(section for section in sections if section.rows),
        row_count=sum(len(section.rows) for section in sections),
    )


def _looks_like_front_color(value: str) -> bool:
    folded = _clean_text(value).lower()
    return any(
        marker in folded
        for marker in (
            "mf.",
            "sm.",
            "fóliás",
            "folias",
            "fényes",
            "fenyes",
            "matt",
            "antracit",
            "beige",
            "fehér",
            "feher",
            "szürke",
            "szurke",
            "tölgy",
            "tolgy",
            "kasmír",
            "kasmir",
            "provance",
            "remo",
            "agyag",
        )
    )


def _parse_front_section_meta(side: str, meta_lines: list[str]) -> tuple[str, str, str]:
    cleaned_meta = [_clean_text(line) for line in meta_lines if _clean_text(line) and _clean_text(line) not in {"-", ":"}]
    descriptor = ""
    color = ""
    if len(cleaned_meta) >= 2:
        descriptor = " - ".join(cleaned_meta[:-1])
        color = cleaned_meta[-1]
    elif len(cleaned_meta) == 1:
        if _looks_like_front_color(cleaned_meta[0]):
            color = cleaned_meta[0]
        else:
            descriptor = cleaned_meta[0]

    label_parts = [side]
    if descriptor:
        label_parts.append(descriptor)
    if color:
        label_parts.append(color)
    return descriptor, color, " - ".join(part for part in label_parts if part)


def _front_row_segments(lines: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        token = _clean_text(line)
        if not token:
            continue
        current.append(token)
        if _is_final_code(token):
            segments.append(current)
            current = []
    return segments


def _parse_front_rows(
    row_lines: list[str],
    *,
    section_label: str,
    section_descriptor: str,
    section_color: str,
    page_number: int,
) -> list[ManufacturingRow]:
    rows: list[ManufacturingRow] = []
    section_key = _slugify(section_label)
    row_index = 0

    for segment in _front_row_segments(row_lines):
        cleaned_segment = [
            token
            for token in segment
            if _clean_text(token) and (_is_final_code(token) or "CON" not in token.upper())
        ]
        if len(cleaned_segment) < 8:
            continue
        code = next((token for token in reversed(cleaned_segment) if _is_final_code(token)), "")
        if not code:
            continue
        code_index = cleaned_segment.index(code)
        payload = cleaned_segment[:code_index]
        quantity_index = -1
        for index in range(len(payload) - 1, -1, -1):
            if re.fullmatch(r"-?\d+", payload[index]):
                quantity_index = index
                break
        if quantity_index == -1:
            continue
        quantity = int(payload[quantity_index])
        payload = payload[:quantity_index]

        dimension_index = -1
        for index in range(len(payload)):
            if _looks_like_dimension_start(payload, index):
                dimension_index = index
                break
        if dimension_index == -1:
            continue

        size, size_end = _consume_dimension(payload, dimension_index)
        if not size:
            continue

        pre_tokens = [_clean_text(token) for token in payload[:dimension_index] if _clean_text(token) and token != "-"]
        post_tokens = [_clean_text(token) for token in payload[size_end:] if _clean_text(token)]

        edge = "-"
        detail_tokens = list(post_tokens)
        if detail_tokens and (detail_tokens[0] == "-" or _looks_like_edge(detail_tokens[0])):
            edge = detail_tokens[0]
            detail_tokens = detail_tokens[1:]
        detail_tokens = [token for token in detail_tokens if token != "-"]

        model = ""
        name_tokens = list(pre_tokens)
        if name_tokens:
            model = name_tokens[-1]
            name_tokens = name_tokens[:-1]

        name = _clean_text(" ".join(name_tokens))
        if not name:
            name = section_descriptor or "Front"

        detail_parts = [part for part in (model, _clean_text(" ".join(detail_tokens))) if part]
        detail = " · ".join(detail_parts)

        row_index += 1
        rows.append(
            ManufacturingRow(
                row_id=_row_hash("front_osszekeszito", section_label, code, name, size, str(row_index)),
                name=name,
                detail=detail,
                size=size,
                color=section_color,
                edge=edge,
                quantity=quantity,
                code=code,
                doc_key="front_osszekeszito",
                section_key=section_key,
                section_label=section_label,
                page_number=page_number,
            )
        )

    return rows


def parse_front_osszekeszito(path: Path) -> ManufacturingDocument:
    pages = _pdf_lines(path)
    section_map: dict[str, list[ManufacturingRow]] = {}

    for page_number, lines in enumerate(pages, start=1):
        footer_index = _footer_index(lines)
        content_lines = lines[:footer_index]
        if not content_lines:
            continue

        index = 0
        while index < len(content_lines):
            if content_lines[index] not in {"Front tÃ­pus:", "Front típus:"}:
                index += 1
                continue

            side = _clean_text(content_lines[index + 1] if index + 1 < len(content_lines) else "") or "Front"
            index += 2
            meta_lines: list[str] = []
            while index < len(content_lines) and content_lines[index] != "Leiras":
                meta_lines.append(content_lines[index])
                index += 1
            if index >= len(content_lines):
                break
            while index < len(content_lines) and content_lines[index] != "ME":
                index += 1
            if index < len(content_lines) and content_lines[index] == "ME":
                index += 1

            row_lines: list[str] = []
            while index < len(content_lines) and content_lines[index] not in {"Front tÃ­pus:", "Front típus:"}:
                row_lines.append(content_lines[index])
                index += 1

            descriptor, color, section_label = _parse_front_section_meta(side, meta_lines)
            rows = _parse_front_rows(
                row_lines,
                section_label=section_label,
                section_descriptor=descriptor,
                section_color=color,
                page_number=page_number,
            )
            if not rows:
                continue

            if not descriptor:
                inferred_descriptor = rows[0].name
                label_parts = [side, inferred_descriptor]
                if color:
                    label_parts.append(color)
                section_label = " - ".join(part for part in label_parts if part)
                rows = [
                    ManufacturingRow(
                        row_id=row.row_id,
                        name=row.name,
                        detail=row.detail,
                        size=row.size,
                        color=row.color,
                        edge=row.edge,
                        quantity=row.quantity,
                        code=row.code,
                        doc_key=row.doc_key,
                        section_key=_slugify(section_label),
                        section_label=section_label,
                        page_number=row.page_number,
                    )
                    for row in rows
                ]

            section_map.setdefault(section_label, []).extend(rows)

    sections = [
        ManufacturingSection(
            key=_slugify(section_label),
            label=section_label,
            rows=tuple(rows),
        )
        for section_label, rows in section_map.items()
        if rows
    ]
    sections = _pair_sections_in_display_order(
        sorted(
            sections,
            key=lambda section: (_pair_info_for_section_label(section.label) or ("9", section.label.lower())),
        )
    )
    return ManufacturingDocument(
        key="front_osszekeszito",
        label="Front összekészítő",
        file_name=path.name,
        sections=tuple(sections),
        row_count=sum(len(section.rows) for section in sections),
    )


def _fold_hu(value: str) -> str:
    text = _clean_text(value).lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
        "õ": "o",
        "û": "u",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _looks_like_cnc_section_header(line: str) -> bool:
    folded = _fold_hu(line)
    return bool(re.fullmatch(r"[12]-es\s+als.*", folded) or re.fullmatch(r"[12]-es\s+fels.*", folded))


def _looks_like_fiokelo_header(line: str) -> bool:
    return _fold_hu(line) == "front tipus:"


def _looks_like_fiokelo_row_start(tokens: list[str], index: int) -> bool:
    token = _fold_hu(_clean_text(tokens[index] if index < len(tokens) else ""))
    if not token:
        return False
    if token in {"fiokelo", "fiokelo:", "fiokelo. "}:
        return True
    if token in {"kihuzhat", "kihuzhato", "kihuzhato front"}:
        return True
    return False


def _looks_like_potential_row_start(tokens: list[str], index: int, max_name_tokens: int) -> bool:
    token = _clean_text(tokens[index] if index < len(tokens) else "")
    if not token or token in {":", "-"} or token.lower() == "x":
        return False
    if token.startswith("Oldal ") or _looks_like_cnc_section_header(token) or _looks_like_fiokelo_header(token):
        return False
    if re.fullmatch(r"-?\d+", token):
        return False
    if any(character.isdigit() for character in token):
        return False
    folded = _fold_hu(token)
    if folded in {"te", "ri", "jo", "n"}:
        return False
    if re.fullmatch(r"[A-Z]{1,4}", token):
        return False
    for offset in range(1, max_name_tokens + 1):
        if _looks_like_dimension_start(tokens, index + offset):
            return True
    return False


def _next_segment_start(tokens: list[str], start_index: int, max_name_tokens: int) -> int:
    for index in range(start_index, len(tokens)):
        token = _clean_text(tokens[index])
        if token.startswith("Oldal ") or _looks_like_cnc_section_header(token) or _looks_like_fiokelo_header(token):
            return index
        if _looks_like_potential_row_start(tokens, index, max_name_tokens):
            return index
    return len(tokens)


def _split_cnc_color_and_detail(tokens: list[str]) -> tuple[str, str]:
    if not tokens:
        return "", ""
    marker_tokens = {
        "nincs",
        "teleszkop",
        "box hettich",
        "normal",
        "also",
        "as vt",
        "as magic",
        "aaf fiokos",
        "af 1+2",
        "atf",
        "ar",
        "akl",
        "aszb",
        "eft 68",
        "ffm",
        "sarok felso",
        "avz b",
        "kmtb60",
        "kmth75",
        "kmth60",
        "kmth60w",
        "kmtb602f",
        "kesb",
        "gtel",
        "n",
    }
    color_tokens: list[str] = []
    detail_tokens: list[str] = []
    marker_seen = False
    for token in tokens:
        folded = _fold_hu(token)
        if not marker_seen and folded not in marker_tokens:
            color_tokens.append(token)
            continue
        marker_seen = True
        detail_tokens.append(token)
    if not color_tokens and tokens:
        color_tokens = [tokens[0]]
        detail_tokens = tokens[1:]
    return _clean_text(" ".join(color_tokens)), _clean_text(" ".join(detail_tokens))


def _parse_cnc_row_segment(segment: list[str], section_label: str, page_number: int, row_index: int) -> ManufacturingRow | None:
    dimension_index = -1
    for index in range(len(segment)):
        if _looks_like_dimension_start(segment, index):
            dimension_index = index
            break
    if dimension_index <= 0:
        return None

    name = _clean_text(" ".join(segment[:dimension_index]))
    size, tail_start = _consume_dimension(segment, dimension_index)
    if not size or not name:
        return None

    tail_tokens = [_clean_text(token) for token in segment[tail_start:] if _clean_text(token)]
    if not tail_tokens:
        return None

    quantity_index = -1
    for index in range(len(tail_tokens) - 1, -1, -1):
        if re.fullmatch(r"-?\d+", tail_tokens[index]):
            quantity_index = index
            break
    if quantity_index == -1:
        return None

    quantity = int(tail_tokens[quantity_index])
    before_quantity = tail_tokens[:quantity_index]
    after_quantity = tail_tokens[quantity_index + 1 :]
    edge = "-"
    if before_quantity and (before_quantity[-1] == "-" or _looks_like_edge(before_quantity[-1])):
        edge = before_quantity[-1]
        before_quantity = before_quantity[:-1]

    color, detail = _split_cnc_color_and_detail(before_quantity)
    if after_quantity:
        detail = _clean_text(" ".join([detail, *after_quantity]))

    code = f"CNC-{_row_hash(section_label, name, size, color, detail, str(row_index))[:10].upper()}"
    return ManufacturingRow(
        row_id=_row_hash("cnc", section_label, name, size, code, str(row_index)),
        name=name,
        detail=detail,
        size=size,
        color=color,
        edge=edge,
        quantity=quantity,
        code=code,
        doc_key="cnc",
        section_key=_slugify(section_label),
        section_label=section_label,
        page_number=page_number,
    )


def parse_cnc(path: Path) -> ManufacturingDocument:
    pages = _pdf_lines(path)
    section_map: dict[str, list[ManufacturingRow]] = {}
    current_label = ""
    row_index = 0

    for page_number, lines in enumerate(pages, start=1):
        footer_index = _footer_index(lines)
        content_lines = lines[:footer_index]
        if not content_lines:
            continue

        index = 0
        while index < len(content_lines):
            token = _clean_text(content_lines[index])
            if _looks_like_cnc_section_header(token):
                current_label = token
                index += 1
                continue
            if not current_label:
                index += 1
                continue
            if not _looks_like_potential_row_start(content_lines, index, 4):
                index += 1
                continue

            dimension_index = -1
            for offset in range(1, 5):
                if _looks_like_dimension_start(content_lines, index + offset):
                    dimension_index = index + offset
                    break
            if dimension_index == -1:
                index += 1
                continue

            row_end = _next_segment_start(content_lines, dimension_index + 5, 4)
            segment = content_lines[index:row_end]
            row_index += 1
            row = _parse_cnc_row_segment(segment, current_label, page_number, row_index)
            if row is not None:
                section_map.setdefault(current_label, []).append(row)
            index = row_end

    sections = [
        ManufacturingSection(
            key=_slugify(section_label),
            label=section_label,
            rows=tuple(rows),
        )
        for section_label, rows in section_map.items()
        if rows
    ]
    sections = _pair_sections_in_display_order(
        sorted(sections, key=lambda section: (_pair_info_for_section_label(section.label) or ("9", section.label.lower())))
    )
    return ManufacturingDocument(
        key="cnc",
        label="CNC",
        file_name=path.name,
        sections=tuple(sections),
        row_count=sum(len(section.rows) for section in sections),
    )


def _fiokelo_model_index(tokens: list[str]) -> int:
    known_models = {"anna", "antonia", "laura", "kinga", "zille", "doroti", "petra", "ibiza", "etna"}
    for index, token in enumerate(tokens):
        if _fold_hu(token) in known_models:
            return index
    return -1


def _parse_fiokelo_row_segment(segment: list[str], section_label: str, page_number: int, row_index: int) -> ManufacturingRow | None:
    dimension_index = -1
    for index in range(len(segment)):
        if _looks_like_dimension_start(segment, index):
            dimension_index = index
            break
    if dimension_index <= 0:
        return None

    pre_tokens = [_clean_text(token) for token in segment[:dimension_index] if _clean_text(token)]
    size, tail_start = _consume_dimension(segment, dimension_index)
    if not size or not pre_tokens:
        return None

    model_index = _fiokelo_model_index(pre_tokens)
    if model_index != -1:
        name = _clean_text(" ".join(pre_tokens[:model_index])) or section_label
        model = _clean_text(pre_tokens[model_index])
        color = _clean_text(" ".join(pre_tokens[model_index + 1 :]))
    else:
        name = _clean_text(pre_tokens[0]) or section_label
        model = _clean_text(pre_tokens[1]) if len(pre_tokens) > 1 else ""
        color = _clean_text(" ".join(pre_tokens[2:])) if len(pre_tokens) > 2 else ""

    tail_tokens = [_clean_text(token) for token in segment[tail_start:] if _clean_text(token)]
    if not tail_tokens:
        return None

    quantity_index = -1
    for index in range(len(tail_tokens) - 1, -1, -1):
        if re.fullmatch(r"-?\d+", tail_tokens[index]):
            quantity_index = index
            break
    if quantity_index == -1:
        return None

    quantity = int(tail_tokens[quantity_index])
    detail = _clean_text(" ".join([part for part in [model, *tail_tokens[:quantity_index]] if part]))
    code = f"FIOK-{_row_hash(section_label, name, size, color, detail, str(row_index))[:10].upper()}"
    return ManufacturingRow(
        row_id=_row_hash("fiokelo_furas", section_label, name, size, code, str(row_index)),
        name=name,
        detail=detail,
        size=size,
        color=color,
        edge="-",
        quantity=quantity,
        code=code,
        doc_key="fiokelo_furas",
        section_key=_slugify(section_label),
        section_label=section_label,
        page_number=page_number,
    )


def parse_fiokelo_furas(path: Path) -> ManufacturingDocument:
    pages = _pdf_lines(path)
    section_map: dict[str, list[ManufacturingRow]] = {}
    current_label = ""
    row_index = 0

    for page_number, lines in enumerate(pages, start=1):
        footer_index = _footer_index(lines)
        content_lines = lines[:footer_index]
        if not content_lines:
            continue

        index = 0
        while index < len(content_lines):
            token = _clean_text(content_lines[index])
            if _looks_like_fiokelo_header(token):
                side = _clean_text(content_lines[index + 1] if index + 1 < len(content_lines) else "")
                descriptor = _clean_text(content_lines[index + 2] if index + 2 < len(content_lines) else "")
                current_label = " - ".join(part for part in (side, descriptor) if part) or "Front összekészítés"
                index += 2
                continue
            if not current_label:
                index += 1
                continue
            if not _looks_like_fiokelo_row_start(content_lines, index):
                index += 1
                continue

            dimension_index = -1
            for offset in range(1, 7):
                if _looks_like_dimension_start(content_lines, index + offset):
                    dimension_index = index + offset
                    break
            if dimension_index == -1:
                index += 1
                continue

            row_end = len(content_lines)
            for next_index in range(dimension_index + 5, len(content_lines)):
                token = _clean_text(content_lines[next_index])
                if token.startswith("Oldal ") or _looks_like_fiokelo_header(token):
                    row_end = next_index
                    break
                if _looks_like_fiokelo_row_start(content_lines, next_index):
                    row_end = next_index
                    break
            segment = content_lines[index:row_end]
            row_index += 1
            row = _parse_fiokelo_row_segment(segment, current_label, page_number, row_index)
            if row is not None:
                section_map.setdefault(current_label, []).append(row)
            index = row_end

    sections = [
        ManufacturingSection(
            key=_slugify(section_label),
            label=section_label,
            rows=tuple(rows),
        )
        for section_label, rows in section_map.items()
        if rows
    ]
    sections = _pair_sections_in_display_order(
        sorted(sections, key=lambda section: (_pair_info_for_section_label(section.label) or ("9", section.label.lower())))
    )
    return ManufacturingDocument(
        key="fiokelo_furas",
        label="Fiókelő fúrás",
        file_name=path.name,
        sections=tuple(sections),
        row_count=sum(len(section.rows) for section in sections),
    )


def load_production_bundle(production_number: str) -> dict:
    folder = production_folder(production_number)
    if not folder.exists():
        raise FileNotFoundError(f"A gyártási mappa nem található: {folder}")

    osszek_path = _find_osszekeszito_path(folder)
    alkatresz_path = _find_alkatresz_kesz_path(folder)
    if osszek_path is None or alkatresz_path is None:
        raise FileNotFoundError("Az Összekészítő vagy az Alkatresz_kesz PDF hiányzik a gyártási mappából.")

    osszek_doc = parse_osszekeszito(osszek_path)
    alkatresz_doc = parse_alkatresz_kesz(alkatresz_path)
    documents = [asdict(osszek_doc), asdict(alkatresz_doc)]
    front_path = _find_front_osszekeszito_path(folder)
    if front_path is not None:
        try:
            front_doc = parse_front_osszekeszito(front_path)
        except Exception:
            front_doc = None
        if front_doc is not None:
            documents.append(asdict(front_doc))

    cnc_path = _find_cnc_path(folder)
    if cnc_path is not None:
        try:
            cnc_doc = parse_cnc(cnc_path)
        except Exception:
            cnc_doc = None
        if cnc_doc is not None:
            documents.append(asdict(cnc_doc))

    fiokelo_furas_path = _find_fiokelo_furas_path(folder)
    if fiokelo_furas_path is not None:
        try:
            fiokelo_doc = parse_fiokelo_furas(fiokelo_furas_path)
        except Exception:
            fiokelo_doc = None
        if fiokelo_doc is not None:
            documents.append(asdict(fiokelo_doc))

    return {
        "production_number": production_number,
        "folder": str(folder),
        "documents": documents,
    }


def selection_state_path(runtime_root: Path, production_number: str) -> Path:
    target_dir = runtime_root / production_number
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "state.json"


def load_selection_state(runtime_root: Path, production_number: str) -> dict[str, str]:
    path = selection_state_path(runtime_root, production_number)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(value) in {"green", "red"}}


def save_selection_state(runtime_root: Path, production_number: str, row_id: str, state: str) -> dict[str, str]:
    current = load_selection_state(runtime_root, production_number)
    normalized_state = str(state or "").strip().lower()
    if normalized_state in {"", "none", "clear"}:
        current.pop(row_id, None)
    elif normalized_state in {"green", "red"}:
        current[row_id] = normalized_state
    path = selection_state_path(runtime_root, production_number)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
