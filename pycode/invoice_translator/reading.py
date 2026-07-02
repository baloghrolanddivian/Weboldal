"""Reading helpers for the invoice translator package."""

from __future__ import annotations

import io
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency handling
    PdfReader = None


NO_DATA = "Nincs adat"
SAVED_SELLER_VAT_NUMBERS = {
    "kronospan": "SK2020070866",
}


def extract_invoice_upload(files: dict[str, tuple[str, bytes]]) -> tuple[str | None, bytes | None]:
    """Return the uploaded invoice filename and bytes from parsed form files."""
    invoice_file = files.get("invoice_file")
    if invoice_file is None:
        return None, None
    return invoice_file


ITEM_PATTERN_FULL = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)
ITEM_PATTERN_SIMPLE = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)


@dataclass
class InvoiceItem:
    """One parsed invoice line item in the normalized printable schema."""
    row_no: str = ""
    article_code: str = ""
    description: str = ""
    pallet_qty: str = ""
    package_qty: str = ""
    pcs_total: str = ""
    total_qty: str = ""
    unit: str = ""
    unit_price: str = ""
    net_value: str = ""


@dataclass
class InvoiceData:
    """Normalized invoice fields extracted from supplier-specific PDF text."""
    invoice_profile: str = ""
    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    payment_method: str = ""
    payment_term: str = ""
    delivery_term: str = ""
    transport_mode: str = ""
    order_confirmation_no: str = ""
    client_ref_no: str = ""
    delivery_note_no: str = ""
    truck_number: str = ""
    currency: str = ""
    supplier_lines: list[str] = field(default_factory=list)
    buyer_lines: list[str] = field(default_factory=list)
    items: list[InvoiceItem] = field(default_factory=list)
    total_net: str = ""
    vat_0: str = ""
    vat_19: str = ""
    discount_amount: str = ""
    discount_percent: str = ""
    total_gross: str = ""
    total_pcs: str = ""
    total_m2: str = ""
    total_m3: str = ""
    total_net_weight: str = ""
    total_gross_weight: str = ""
    origin_country: str = ""


@dataclass
class InvoiceChunk:
    """A contiguous PDF page range that appears to contain one invoice."""
    invoice_hint: str
    text: str
    page_from: int
    page_to: int


class MissingInvoiceDataError(ValueError):
    """Raised when required invoice fields are missing after parsing."""
    pass


def _clean_spaces(value: str) -> str:
    """Collapse repeated whitespace and trim surrounding spaces."""
    return re.sub(r"\s+", " ", value).strip()


def _value_or_default(value: str) -> str:
    """Return cleaned text or the shared no-data placeholder."""
    return _clean_spaces(value) if value else NO_DATA


def _parse_invoice_date(value: str) -> datetime | None:
    """Parse invoice dates from known supplier text formats."""
    clean_value = _clean_spaces(value)
    if not clean_value:
        return None

    for pattern in (
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(clean_value, pattern)
        except ValueError:
            continue
    return None


def _format_invoice_date(value: str) -> str:
    """Format format invoice date values for display or export."""
    parsed = _parse_invoice_date(value)
    if parsed is None:
        return _clean_spaces(value)
    return parsed.strftime("%Y.%m.%d")


def _item_value_or_default(value: str, placeholder: str = NO_DATA) -> str:
    """Return cleaned item text or the item-specific placeholder."""
    cleaned = _clean_spaces(value)
    return cleaned if cleaned else placeholder


def _is_number_token(value: str) -> bool:
    """Return whether is number token is true."""
    return bool(re.fullmatch(r"[0-9][0-9.,]*", value))


def _is_integer_token(value: str) -> bool:
    """Return whether is integer token is true."""
    return bool(re.fullmatch(r"\d+", value))


def _parse_eu_number(value: str) -> float | None:
    """Parse a European-formatted numeric string into a Decimal."""
    cleaned = value.strip().replace(" ", "")
    if not cleaned:
        return None
    if not re.fullmatch(r"-?[0-9.,]+", cleaned):
        return None
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _format_eu_number(value: float, decimals: int = 2) -> str:
    """Format format eu number values for display or export."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_rounded_weight(raw_value: str) -> str:
    """Format format rounded weight values for display or export."""
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return ""
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        rounded = Decimal(normalized).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return raw_value
    return f"{int(rounded):,}".replace(",", ".")


def _normalize_kronospan_weight(raw_value: str) -> str:
    """Normalize Kronospan weight values to kilograms when possible."""
    value = _parse_eu_number(raw_value)
    if value is None:
        return raw_value
    # Kronospan totalsorban a gross/net weight tipikusan tonnában jelenik meg,
    # a felületen viszont kg-ban mutatjuk.
    if value < 1000:
        value *= 1000
    return _format_eu_number(value, 0)


def _fix_hungarian_mojibake(value: str) -> str:
    """Repair the limited mojibake variants seen in Hungarian invoice text."""
    return value.translate(str.maketrans({"õ": "ő", "û": "ű", "Õ": "Ő", "Û": "Ű"}))


def _find_index(lines: list[str], pattern: str, start: int = 0) -> int:
    """Return the first line index matching a regex, or -1."""
    for idx in range(start, len(lines)):
        if re.search(pattern, lines[idx], re.IGNORECASE):
            return idx
    return -1


def _extract_block(lines: list[str], start_pattern: str, end_patterns: list[str]) -> list[str]:
    """Extract extract block data."""
    start_idx = _find_index(lines, start_pattern)
    if start_idx == -1:
        return []

    end_idx = len(lines)
    for end_pattern in end_patterns:
        match_idx = _find_index(lines, end_pattern, start_idx + 1)
        if match_idx != -1:
            end_idx = min(end_idx, match_idx)

    block = lines[start_idx + 1 : end_idx]
    return [line for line in block if line]


def _match_first(text: str, patterns: list[str], flags: int = re.IGNORECASE | re.MULTILINE) -> str:
    """Return the first captured value from a list of regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean_spaces(match.group(1))
    return ""


def _saved_seller_vat_number(profile: str, supplier_name: str = "") -> str:
    """Return a known seller VAT number for profiles that omit it."""
    normalized_profile = _clean_spaces(profile).lower()
    if normalized_profile in SAVED_SELLER_VAT_NUMBERS:
        return SAVED_SELLER_VAT_NUMBERS[normalized_profile]

    normalized_supplier = _clean_spaces(supplier_name).lower()
    for key, vat_number in SAVED_SELLER_VAT_NUMBERS.items():
        if key in normalized_supplier:
            return vat_number
    return ""


def _party_has_vat_number(lines: list[str]) -> bool:
    """Return whether a supplier/buyer address block contains a VAT label."""
    joined = "\n".join(_clean_spaces(line) for line in lines if _clean_spaces(line))
    return bool(
        re.search(
            r"\b(?:VAT\s*(?:ID\s*)?(?:NO\.?|NUMBER)|TAX\s*NO\.?|AD[ÓO]SZ[ÁA]M)\b",
            joined,
            re.IGNORECASE,
        )
    )


def _extract_party_vat_number(lines: list[str]) -> str:
    """Extract extract party vat number data."""
    vat_label_pattern = r"\b(?:VAT\s*(?:ID\s*)?(?:NO\.?|NUMBER)|TAX\s*NO\.?|AD[ÓO]SZ[ÁA]M)\b"
    for idx, line in enumerate(lines):
        cleaned = _clean_spaces(line)
        if not cleaned:
            continue

        label_match = re.search(vat_label_pattern, cleaned, re.IGNORECASE)
        if not label_match:
            continue

        value = cleaned[label_match.end() :].strip(" :.-#")
        if value:
            return value

        for candidate in lines[idx + 1 : idx + 3]:
            candidate_value = _clean_spaces(candidate).strip(" :.-#")
            if candidate_value:
                return candidate_value

    return ""


def _require_party_vat_numbers(data: InvoiceData) -> None:
    """Validate that both supplier and buyer blocks contain VAT numbers."""
    missing: list[str] = []
    if not _party_has_vat_number(data.supplier_lines):
        missing.append("eladó VAT Number")
    if not _party_has_vat_number(data.buyer_lines):
        missing.append("vevő VAT Number")
    if missing:
        raise MissingInvoiceDataError(f"Adat nem található: {', '.join(missing)}")


def _pdf_unescape(value: str) -> str:
    """Decode simple PDF string escapes from fallback text extraction."""
    value = value.replace(r"\n", " ").replace(r"\r", " ").replace(r"\t", " ")
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return value


def _looks_like_human_text(text: str) -> bool:
    """Return whether a value looks like looks like human text."""
    if len(text.strip()) < 40:
        return False
    indicator_hits = sum(token in text for token in (" endobj", " stream", " xref", "/Type", "FlateDecode"))
    if indicator_hits >= 3 and text.count("\n") < 8:
        return False
    alpha_ratio = sum(ch.isalpha() for ch in text) / max(len(text), 1)
    return alpha_ratio > 0.15


def _fallback_extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract rough text from PDF streams when pypdf is unavailable or empty."""
    raw_text = pdf_bytes.decode("latin1", errors="ignore")
    chunks: list[str] = []

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        stream_data = match.group(1)
        candidates = [stream_data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                candidates.append(zlib.decompress(stream_data, wbits))
            except Exception:
                pass

        for candidate in candidates:
            decoded = candidate.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", decoded, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", decoded, re.DOTALL):
                chunks.extend(_pdf_unescape(part) for part in re.findall(r"\((.*?)\)", arr, re.DOTALL))
        for cand in candidates:
            text = cand.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", text, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
                parts = re.findall(r"\((.*?)\)", arr, re.DOTALL)
                chunks.extend(_pdf_unescape(p) for p in parts)

    extracted = " ".join(chunks).strip()
    if extracted:
        return re.sub(r"\s+", " ", extracted)

    rough = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.,:/ ]{4,}", raw_text)
    return " ".join(rough[:800])


def _extract_text_pages_from_pdf(pdf_bytes: bytes) -> list[str]:
    """Extract extract text pages from pdf data."""
    if PdfReader is None:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception:
        return []


# Image OCR extractor kept here for later targeted use. Do not wire this into the
# invoice module as a general fallback; Kronospan seller VAT is stored explicitly.
#
# def _pdf_filter_names(raw_filter) -> set[str]:
#     if raw_filter is None:
#         return set()
#     if isinstance(raw_filter, (list, tuple)):
#         return {str(item) for item in raw_filter}
#     return {str(raw_filter)}
#
#
# def _ocr_image_file(image_path: Path) -> str:
#     if os.name != "nt":
#         return ""
#
#     ocr_script = BASE_DIR / "tools" / "windows_ocr.ps1"
#     if not ocr_script.exists():
#         return ""
#
#     try:
#         completed = subprocess.run(
#             [
#                 "powershell",
#                 "-ExecutionPolicy",
#                 "Bypass",
#                 "-File",
#                 str(ocr_script),
#                 "-Path",
#                 str(image_path.resolve()),
#             ],
#             capture_output=True,
#             encoding="utf-8",
#             errors="replace",
#             text=True,
#             timeout=20,
#             check=False,
#         )
#     except Exception:
#         return ""
#
#     if completed.returncode != 0:
#         return ""
#     return _clean_spaces(completed.stdout)
#
#
# def _extract_pdf_dct_image_ocr_pages(pdf_bytes: bytes) -> list[str]:
#     if PdfReader is None or os.name != "nt":
#         return []
#
#     try:
#         reader = PdfReader(io.BytesIO(pdf_bytes))
#     except Exception:
#         return []
#
#     RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
#     image_text_by_hash: dict[str, str] = {}
#     page_ocr_texts: list[str] = []
#
#     for page in reader.pages:
#         page_parts: list[str] = []
#         try:
#             resources = page.get("/Resources") or {}
#             xobjects = resources.get("/XObject") or {}
#             if hasattr(xobjects, "get_object"):
#                 xobjects = xobjects.get_object()
#         except Exception:
#             page_ocr_texts.append("")
#             continue
#
#         for image_object in xobjects.values():
#             try:
#                 obj = image_object.get_object() if hasattr(image_object, "get_object") else image_object
#                 if str(obj.get("/Subtype")) != "/Image":
#                     continue
#                 if "/DCTDecode" not in _pdf_filter_names(obj.get("/Filter")):
#                     continue
#                 image_data = obj.get_data()
#             except Exception:
#                 continue
#
#             digest = hashlib.sha256(image_data).hexdigest()
#             if digest not in image_text_by_hash:
#                 temp_path = RUNTIME_DIR / f"pdf-ocr-{digest[:16]}-{uuid.uuid4().hex[:8]}.jpg"
#                 try:
#                     temp_path.write_bytes(image_data)
#                     image_text_by_hash[digest] = _ocr_image_file(temp_path)
#                 except Exception:
#                     image_text_by_hash[digest] = ""
#                 finally:
#                     try:
#                         temp_path.unlink(missing_ok=True)
#                     except Exception:
#                         pass
#
#             if image_text_by_hash[digest]:
#                 page_parts.append(image_text_by_hash[digest])
#
#         page_ocr_texts.append("\n".join(page_parts))
#
#     return page_ocr_texts


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract extract text from pdf data."""
    page_text = _extract_text_pages_from_pdf(pdf_bytes)
    if page_text:
        joined = "\n".join(chunk for chunk in page_text if chunk).strip()
        if _looks_like_human_text(joined):
            return joined

    return _fallback_extract_text_from_pdf(pdf_bytes)


def _extract_invoice_number_hint(text: str) -> str:
    """Extract extract invoice number hint data."""
    lines = [_clean_spaces(line) for line in text.splitlines() if _clean_spaces(line)]
    normalized = "\n".join(lines)

    for pattern in (
        r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
        r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"SZÁMLA\s*SZÁMA[\s\S]{0,120}?(\d{5,})",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    idx = _find_index(lines, r"^Invoice number$")
    if idx != -1:
        for candidate in lines[idx + 1 : idx + 12]:
            if re.fullmatch(r"\d{4,}", candidate):
                return candidate

    return ""


def split_pdf_by_invoice(pdf_bytes: bytes) -> list[InvoiceChunk]:
    """Split a multi-page PDF into invoice chunks using invoice-number hints."""
    page_texts = _extract_text_pages_from_pdf(pdf_bytes)
    if not page_texts:
        text = extract_text_from_pdf(pdf_bytes)
        return [InvoiceChunk(invoice_hint=_extract_invoice_number_hint(text), text=text, page_from=1, page_to=1)]

    groups: list[InvoiceChunk] = []
    current_hint = ""
    current_pages: list[tuple[int, str]] = []

    for page_index, raw_text in enumerate(page_texts, start=1):
        page_text = raw_text.strip()
        hint = _extract_invoice_number_hint(page_text) if page_text else ""

        if not current_pages:
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        should_split = bool(hint and current_hint and hint != current_hint)
        if should_split:
            from_page = current_pages[0][0]
            to_page = current_pages[-1][0]
            joined_text = "\n".join(text for _, text in current_pages if text).strip()
            groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        if hint and not current_hint:
            current_hint = hint
        current_pages.append((page_index, page_text))

    if current_pages:
        from_page = current_pages[0][0]
        to_page = current_pages[-1][0]
        joined_text = "\n".join(text for _, text in current_pages if text).strip()
        groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))

    # Ha nem sikerült jól szétbontani (pl. mind üres), maradjon egy blokk.
    valid_groups = [group for group in groups if group.text]
    return valid_groups or [InvoiceChunk(invoice_hint="", text=extract_text_from_pdf(pdf_bytes), page_from=1, page_to=len(page_texts))]


def _parse_items(lines: list[str]) -> list[InvoiceItem]:
    """Parse generic invoice item rows from extracted text lines."""
    items: list[InvoiceItem] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 7 or not _is_integer_token(tokens[0]):
            continue

        # A sor végétől bontunk, mert a leírás maga is tartalmazhat számokat.
        if (
            len(tokens) >= 10
            and _is_number_token(tokens[-1])
            and _is_number_token(tokens[-2])
            and _is_number_token(tokens[-4])
            and re.fullmatch(r"[A-Za-z0-9]{1,8}", tokens[-3])
        ):
            if len(tokens) >= 14 and all(_is_integer_token(tokens[idx]) for idx in (-5, -6, -7)):
                description = " ".join(tokens[2:-7]).strip()
                if not description:
                    continue
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        pallet_qty=tokens[-7],
                        package_qty=tokens[-6],
                        pcs_total=tokens[-5],
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

            description = " ".join(tokens[2:-5]).strip()
            if description:
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

        full_match = ITEM_PATTERN_FULL.match(line)
        if full_match:
            row_no, code, desc, pallet, package_qty, pcs, qty, unit, unit_price, net_value = full_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    pallet_qty=pallet,
                    package_qty=package_qty,
                    pcs_total=pcs,
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )
            continue

        simple_match = ITEM_PATTERN_SIMPLE.match(line)
        if simple_match:
            row_no, code, desc, qty, unit, unit_price, net_value = simple_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )

    return items


def _detect_invoice_profile(lines: list[str], text: str) -> str:
    """Identify the supplier-specific parser profile from invoice text markers."""
    upper_text = text.upper()
    if "KASTAMONU" in upper_text:
        if "CREDIT NOTE" in upper_text:
            return "kastamonu_credit"
        return "kastamonu"

    if "GAMET SP. Z O.O." in upper_text or "GAMET SP. Z O.O." in upper_text.replace("Ł", "L"):
        return "gamet"

    krono_hits = 0
    for marker in ("KRONOSPAN", "DESPATCH ADDRESS", "SPLIT_PDF_MARK", "PAYMENT DUE", "DELIVERY NOTE NO."):
        if marker in upper_text:
            krono_hits += 1
    if krono_hits >= 2:
        return "kronospan"

    if ("DIVIAN-MEGA KFT" in upper_text or "/DIVI" in upper_text) and (
        "SZÁMLA SZÁMA" in upper_text or "ÁRUÉRTÉK" in upper_text or "TRAILER:" in upper_text
    ):
        return "divian"

    return "generic"


def _is_signed_number_token(value: str) -> bool:
    """Return whether is signed number token is true."""
    return bool(re.fullmatch(r"-?[0-9][0-9.,]*", value))


def _extract_decimal_from_token(token: str) -> str:
    """Extract extract decimal from token data."""
    match = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", token)
    if match:
        return match.group(0)
    match = re.search(r"-?\d+,\d{2}", token)
    if match:
        return match.group(0)
    return ""


def _infer_unit_from_line(line: str) -> str:
    """Infer a known unit token from a free-form item line."""
    upper = line.upper()
    if "LFM" in upper:
        return "lfm"
    if "M2" in upper:
        return "m2"
    if "PCS" in upper:
        return "pcs"
    return ""


def _parse_kronospan_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    """Parse Kronospan invoice item rows from extracted text lines."""
    items: list[InvoiceItem] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if not any(token in upper_line for token in ("P2EN", "WORKTOP", "SPLASHBACK", "MF PB", "VP P2")):
            i += 1
            continue

        kronospan_marker = ""
        if "SPLASHBACK" in upper_line:
            kronospan_marker = "SPLASHBACK"
        elif "WORKTOP" in upper_line or "WORK TOP" in upper_line or "KITCHEN TOP" in upper_line:
            kronospan_marker = "WORKTOP"
        elif "MF PB" in upper_line:
            kronospan_marker = "MF PB"
        elif "VP P2" in upper_line:
            kronospan_marker = "VP P2"
        elif "P2EN" in upper_line:
            kronospan_marker = "P2EN"

        item = InvoiceItem(row_no=str(len(items) + 1))
        position_code = start_match.group(1)
        payload = start_match.group(2)
        item.unit = _infer_unit_from_line(line)

        payload_tokens = payload.split()
        comma_tokens = [token for token in payload_tokens if "," in token]
        if comma_tokens:
            item.net_value = _extract_decimal_from_token(comma_tokens[0])
        if len(comma_tokens) > 1:
            item.unit_price = _extract_decimal_from_token(comma_tokens[1])

        code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{3,})\b", payload)
        if code_match:
            item.article_code = code_match.group(1)
        else:
            item.article_code = position_code

        description_lines: list[str] = []
        quantity_line = ""
        code_line = ""
        packs_line = ""
        pcs_line = ""

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.match(r"^T\s*o\s*t\s*a\s*l:", next_line, re.IGNORECASE):
                break
            if re.fullmatch(r"\d+\s+\d+/", next_line):
                break
            if "SPLIT_PDF_MARK" in next_line.upper():
                j += 1
                continue
            if "C A R R Y" in next_line.upper() or "CARRY" in next_line.upper():
                break
            if next_line.upper().startswith("COUNTRY OF ORIGIN") or next_line.upper().startswith("CUSTOM TARIFF"):
                j += 1
                continue

            if "/" in next_line and "HTTP" not in next_line.upper():
                description_lines.append(next_line)
            elif re.fullmatch(r"-?[0-9][0-9.,]*", next_line):
                if not quantity_line:
                    quantity_line = next_line
            elif re.fullmatch(r"\d+\s+\d+", next_line):
                pcs_line = next_line
            elif re.search(r"PACK\(S\)", next_line, re.IGNORECASE):
                packs_line = next_line
            elif re.fullmatch(r"(?=.*[A-Z])[0-9A-Z ]{6,}", next_line):
                code_line = next_line

            j += 1

        if quantity_line:
            item.total_qty = quantity_line

        if code_line:
            refined_code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{2,}|\d{4})\b", code_line)
            if refined_code_match:
                item.article_code = refined_code_match.group(1)

        if description_lines:
            description_parts = description_lines + ([code_line] if code_line else [])
            description_text = " | ".join(description_parts)
            if kronospan_marker and kronospan_marker not in description_text.upper():
                description_text = f"{kronospan_marker} | {description_text}"
            item.description = description_text
        else:
            item.description = payload

        if packs_line:
            packs_match = re.search(r"(\d+)\s*Pack\(s\)", packs_line, re.IGNORECASE)
            if packs_match:
                item.package_qty = packs_match.group(1)

        if pcs_line:
            parts = pcs_line.split()
            if len(parts) == 2:
                if not item.package_qty:
                    item.package_qty = parts[0]
                item.pcs_total = parts[1]

        if not item.net_value and total_net_fallback and len(items) == 0:
            item.net_value = total_net_fallback

        if item.total_qty and item.net_value and not item.unit_price:
            quantity_value = _parse_eu_number(item.total_qty)
            net_value_num = _parse_eu_number(item.net_value)
            if quantity_value and net_value_num and quantity_value > 0:
                item.unit_price = _format_eu_number(net_value_num / quantity_value, 2)

        items.append(item)
        i = j

    return items


def _parse_kastamonu_or_generic_invoice_data(lines: list[str]) -> InvoiceData:
    """Parse Kastamonu or generic invoice header and item data."""
    normalized_text = "\n".join(lines)
    profile = "kastamonu" if "KASTAMONU" in normalized_text.upper() else "generic"
    data = InvoiceData(invoice_profile=profile)

    data.supplier_lines = _extract_block(lines, r"^(SELLER|SUPPLIER)\b", [r"^INVOICE\b", r"^DATE\b"])
    data.buyer_lines = _extract_block(
        lines,
        r"^(BUYER|CUSTOMER|BILL TO)\b",
        [r"^CONSIGNEE\b", r"^DELIVERY TERM\b", r"^NR\.?$", r"^ARTICLE\b"],
    )

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
            r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
            r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"\bDATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"INVOICE\s*DATE\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(normalized_text, [r"DUE\s*DATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.payment_method = _match_first(normalized_text, [r"PAYMENT\s*METHOD\s*:\s*(.+)"])
    data.payment_term = _match_first(normalized_text, [r"PAYMENT\s*TERM\s*:\s*(.+)"])
    data.delivery_term = _match_first(normalized_text, [r"DELIVERY\s*TERM\s*:\s*(.+)"])
    data.transport_mode = _match_first(normalized_text, [r"MEAN\s*OF\s*TRANSPORT\s*:\s*(.+)"])
    data.order_confirmation_no = _match_first(normalized_text, [r"ORDER\s*CONFIRMATION\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.client_ref_no = _match_first(normalized_text, [r"CLIENT'?S\s*REF\s*NO\s*:\s*(.+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"TRUCK\s*NUMBER\s*:\s*([A-Z0-9/\- ]+)"])
    data.currency = _match_first(
        normalized_text,
        [
            r"TOTAL\s*\(([A-Z]{3})\)",
            r"VALUE\s*\(([A-Z]{3})\)",
            r"PRICE/UM\s*\(([A-Z]{3})\)",
            r"CURRENCY\s*:\s*([A-Z]{3})",
        ],
    )

    data.total_net = _match_first(
        normalized_text,
        [
            r"^TOTAL\s+\d+\s+\d+\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"^TOTAL\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"NET\s*(?:VALUE|AMOUNT)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_gross = _match_first(
        normalized_text,
        [
            r"^TOTAL\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"GROSS\s*(?:VALUE|AMOUNT|TOTAL)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_m2 = _match_first(normalized_text, [r"TOTAL\s*M2\s*:\s*([0-9][0-9.,]*)"])
    data.total_m3 = _match_first(normalized_text, [r"TOTAL\s*M3\s*:\s*([0-9][0-9.,]*)"])
    data.total_net_weight = _match_first(normalized_text, [r"TOTAL\s*NET\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.total_gross_weight = _match_first(normalized_text, [r"TOTAL\s*GROSS\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.origin_country = _match_first(
        normalized_text,
        [r"ORIGIN\s*OF\s*THE\s*GOODS\s*:\s*(.+)", r"COUNTRY\s*OF\s*ORIGIN\s*:\s*(.+)"],
    )

    for idx, line in enumerate(lines):
        vat_match = re.search(r"VAT\(([\d.,]+)%\)\s*([0-9][0-9.,]*)?$", line, re.IGNORECASE)
        if not vat_match:
            continue

        rate = vat_match.group(1).replace(",", ".").strip()
        amount = vat_match.group(2) or ""
        if not amount and idx + 1 < len(lines) and re.fullmatch(r"[0-9][0-9.,]*", lines[idx + 1]):
            amount = lines[idx + 1]
        if not amount:
            amount = "0,00"

        if rate == "0":
            data.vat_0 = amount
        elif rate == "19":
            data.vat_19 = amount

    if not data.vat_0:
        data.vat_0 = _match_first(normalized_text, [r"VAT\(?0%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])
    if not data.vat_19:
        data.vat_19 = _match_first(normalized_text, [r"VAT\(?19%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])

    data.items = _parse_items(lines)
    if data.supplier_lines:
        data.supplier_name = data.supplier_lines[0]
    return data


def _parse_kastamonu_credit_note_items(lines: list[str]) -> list[InvoiceItem]:
    """Parse Kastamonu credit note item rows from extracted text lines."""
    items: list[InvoiceItem] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 7 or not _is_integer_token(tokens[0]):
            continue
        if not re.fullmatch(r"[A-Z0-9\-/]+", tokens[1], re.IGNORECASE):
            continue
        if not (
            _is_signed_number_token(tokens[-1])
            and _is_signed_number_token(tokens[-2])
            and re.fullmatch(r"[A-Za-z0-9]{1,8}", tokens[-3])
        ):
            continue

        pcs_total = ""
        description_end = -3
        if len(tokens) >= 8 and _is_integer_token(tokens[-4]):
            pcs_total = tokens[-4]
            description_end = -5 if len(tokens) >= 9 and _is_signed_number_token(tokens[-5]) else -4

        description = " ".join(tokens[2:description_end]).strip()
        if not description:
            continue

        items.append(
            InvoiceItem(
                row_no=tokens[0],
                article_code=tokens[1],
                description=_clean_spaces(description),
                pcs_total=pcs_total,
                unit=tokens[-3],
                unit_price=tokens[-2],
                net_value=tokens[-1],
            )
        )

    return items


def _parse_kastamonu_credit_note_data(lines: list[str], text: str) -> InvoiceData:
    """Parse Kastamonu credit note header and item data."""
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="kastamonu_credit")

    data.supplier_lines = _extract_block(lines, r"^(SELLER|SUPPLIER)\b", [r"^CREDIT\s+NOTE\b", r"^DATE\b"])
    data.buyer_lines = _extract_block(
        lines,
        r"^(BUYER|CUSTOMER|BILL TO)\b",
        [r"^CONSIGNEE\b", r"^ORDER\s+CONFIRMATION\b", r"^NR\.?$", r"^ARTICLE\b"],
    )

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
            r"CREDIT\s+NOTE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
            r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"\bDATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"CREDIT\s+NOTE\s*DATE\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.order_confirmation_no = _match_first(normalized_text, [r"ORDER\s*CONFIRMATION\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.client_ref_no = _match_first(normalized_text, [r"INVOICE\s*REF\s*:\s*(.+)"])
    data.currency = _match_first(
        normalized_text,
        [
            r"TOTAL\s*\(([A-Z]{3})\)",
            r"VALUE\s*\(([A-Z]{3})\)",
            r"PRICE/UM\s*\(([A-Z]{3})\)",
        ],
    )
    data.total_net = _match_first(
        normalized_text,
        [
            r"^TOTAL\s+VALUE\s*\([A-Z]{3}\)\s*(-?[0-9][0-9.,]*)\s*$",
            r"NET\s*(?:VALUE|AMOUNT)\s*[:\-]?\s*(-?[0-9][0-9.,]*)",
        ],
    )
    data.total_gross = _match_first(
        normalized_text,
        [
            r"^TOTAL\s*\([A-Z]{3}\)\s*(-?[0-9][0-9.,]*)\s*$",
            r"GROSS\s*(?:VALUE|AMOUNT|TOTAL)\s*[:\-]?\s*(-?[0-9][0-9.,]*)",
        ],
    )
    if not data.total_gross:
        data.total_gross = data.total_net

    if re.search(r"\b(?:VAT|TVA)\(?0%?\)?", normalized_text, re.IGNORECASE):
        data.vat_0 = "0,00"

    data.items = _parse_kastamonu_credit_note_items(lines)
    if data.supplier_lines:
        data.supplier_name = data.supplier_lines[0]
    return data


def _parse_gamet_items(lines: list[str]) -> list[InvoiceItem]:
    """Parse Gamet invoice item rows from extracted text lines."""
    items: list[InvoiceItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d+)\s+([A-Z0-9-]+)\s*$", line)
        if not start_match:
            i += 1
            continue

        row_no = start_match.group(1)
        article_code = start_match.group(2)
        description = ""
        total_qty = ""
        unit = ""
        unit_price = ""
        net_value = ""

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^\d+\s+[A-Z0-9-]+\s*$", next_line):
                break
            if next_line.startswith("Total according to VAT rates") or next_line == "Total":
                break
            if next_line.startswith("GTIN No:"):
                j += 1
                continue
            if next_line.startswith("Delivery Note(s):"):
                j += 1
                continue

            qty_match = re.match(
                r"^([0-9]+(?:\.[0-9]+)?)\s+(\S+)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Z]{3})\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+%)\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)$",
                next_line,
            )
            if qty_match:
                total_qty = qty_match.group(1)
                unit = qty_match.group(2)
                unit_price = qty_match.group(3)
                net_value = qty_match.group(5)
                j += 1
                continue

            if not description:
                description = next_line
            else:
                description = f"{description} | {next_line}"
            j += 1

        items.append(
            InvoiceItem(
                row_no=row_no,
                article_code=article_code,
                description=description,
                total_qty=total_qty,
                unit=unit,
                unit_price=unit_price,
                net_value=net_value,
            )
        )
        i = j

    return items


def _parse_gamet_invoice_data(lines: list[str], text: str) -> InvoiceData:
    """Parse Gamet invoice header and item data."""
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="gamet", supplier_name="GAMET Sp. z o.o.")

    data.invoice_number = _match_first(normalized_text, [r"Invoice No\s*\n\s*([A-Z0-9/\-]+)"])
    data.invoice_date = _match_first(normalized_text, [r"Invoice date\s*\n\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.due_date = _match_first(normalized_text, [r"Due date:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.payment_method = _match_first(normalized_text, [r"Payment:\s*\n\s*(.+)"])
    data.payment_term = data.payment_method
    data.delivery_term = _match_first(normalized_text, [r"Delivery Terms:\s*(.+)"])
    data.transport_mode = _match_first(normalized_text, [r"Ship Via:\s*(.+)"])
    data.currency = _match_first(normalized_text, [r"Total\s*\n\s*([A-Z]{3})\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+"])
    data.total_net = _match_first(normalized_text, [r"Total\s*\n\s*[A-Z]{3}\s+([0-9.]+)\s+[0-9.]+\s+[0-9.]+"])
    data.total_gross = _match_first(normalized_text, [r"Total\s*\n\s*[A-Z]{3}\s+[0-9.]+\s+[0-9.]+\s+([0-9.]+)"])
    data.vat_0 = _match_first(normalized_text, [r"0%\s+[A-Z]{3}\s+[0-9.]+\s+([0-9.]+)\s+[0-9.]+"])
    data.total_gross_weight = _match_first(normalized_text, [r"Gross weight including transport packaging:\s*([0-9]+)\s*kgs"])
    data.order_confirmation_no = _match_first(normalized_text, [r"Order Number:\s*([A-Z0-9/\-]+)"])

    seller_block = _extract_block(lines, r"^Seller:", [r"^Buyer:"])
    buyer_block = _extract_block(lines, r"^Buyer:", [r"^Terms of", r"^Payment:"])
    data.supplier_lines = ["GAMET Sp. z o.o."] + [line for line in seller_block if not line.startswith("Address:")]
    data.buyer_lines = ["DIVIAN MEGA Kft."] + [line for line in buyer_block if not line.startswith("Address:")]

    if seller_block:
        data.supplier_lines = [lines[_find_index(lines, r"^Seller:")]] + seller_block
    if buyer_block:
        data.buyer_lines = [lines[_find_index(lines, r"^Buyer:")]] + buyer_block

    data.items = _parse_gamet_items(lines)
    return data


def _parse_kronospan_invoice_data(lines: list[str], text: str) -> InvoiceData:
    """Parse Kronospan invoice header and item data."""
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="kronospan", supplier_name="KRONOSPAN, s.r.o.")

    data.invoice_number = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)"])
    if not data.invoice_number:
        idx = _find_index(lines, r"^Invoice number$")
        if idx != -1:
            for candidate in lines[idx + 1 : idx + 12]:
                if re.fullmatch(r"\d{4,}", candidate):
                    data.invoice_number = candidate
                    break

    data.invoice_date = _match_first(
        normalized_text,
        [
            r"DATE\s*OF\s*INVOICE\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"\bDate\b[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(
        normalized_text,
        [r"PAYMENT\s*DUE\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"],
    )

    payment_idx = _find_index(lines, r"^Payment Terms")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        data.payment_term = lines[payment_idx + 1]

    data.delivery_term = _match_first(
        normalized_text,
        [r"((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)", r"TERMS\s*OF\s*DEL\.?\s*[:\-]?\s*(.+)"],
    )
    data.payment_method = "Banki átutalás"
    data.truck_number = _match_first(normalized_text, [r"TRAILER\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*([A-Z0-9/\-]+)"])

    order_idx = _find_index(lines, r"^Order Number$")
    if order_idx != -1:
        strict_match = ""
        for candidate in lines[order_idx + 1 : order_idx + 10]:
            if re.fullmatch(r"\d{5,}", candidate):
                strict_match = candidate
                break
        if strict_match:
            data.order_confirmation_no = strict_match
        else:
            for candidate in lines[order_idx + 1 : order_idx + 10]:
                if re.fullmatch(r"[A-Z0-9/\-]{4,}", candidate) and not re.fullmatch(
                    r"\d{1,2}\.\d{1,2}\.\d{2,4}",
                    candidate,
                ):
                    data.order_confirmation_no = candidate
                    break

    ref_idx = _find_index(lines, r"^Your Reference$")
    if ref_idx != -1:
        for candidate in lines[ref_idx + 1 : ref_idx + 8]:
            if "/" in candidate and "ORDER DATE" not in candidate.upper():
                data.client_ref_no = candidate
                break

    vat_no = _match_first(normalized_text, [r"VAT\s*-\s*NO\.?\s*([A-Z0-9]+?)(?:DELIVERY|\s|$)"])
    seller_vat_id = _match_first(
        normalized_text,
        [r"VAT\s*ID\s*NO[\W_:.]*([A-Z]{2}\s*\d[\d\s]{5,})"],
    ).replace(" ", "")
    if not seller_vat_id:
        seller_vat_id = _saved_seller_vat_number(data.invoice_profile, data.supplier_name)
    tax_idx = _find_index(lines, r"^Tax No\.")
    if tax_idx != -1:
        data.buyer_lines = [line for line in lines[max(0, tax_idx - 4) : tax_idx] if line]
    else:
        despatch_idx = _find_index(lines, r"^Despatch Address")
        if despatch_idx != -1 and despatch_idx + 1 < len(lines):
            data.buyer_lines = [lines[despatch_idx + 1]]
    if vat_no:
        data.buyer_lines.append(f"VAT NUMBER: {vat_no}")
    data.buyer_lines = list(dict.fromkeys(data.buyer_lines))

    data.supplier_lines = [data.supplier_name]
    if seller_vat_id:
        data.supplier_lines.append(f"VAT ID No.: {seller_vat_id}")
    for label in ("BANK:", "IBAN:", "SWIFT:"):
        idx = _find_index(lines, f"^{re.escape(label)}")
        if idx != -1:
            data.supplier_lines.append(lines[idx])

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[-0-9.,]+\s*VALUE\s*OF\s*GOODS",
            r"\b(EUR)\s*[-0-9.,]+\s*TOTAL\s*AMOUNT",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*VALUE\s*OF\s*GOODS"])
    data.total_gross = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*TOTAL\s*AMOUNT"])

    discount_match = re.search(r"EUR\s*([-0-9.,]+)\s*([0-9]+,[0-9]{2})?\s*DISCOUNT\s*%", normalized_text, re.IGNORECASE)
    if discount_match:
        discount_blob = (discount_match.group(1) or "").strip()
        percent = (discount_match.group(2) or "").strip()
        split_match = re.fullmatch(r"(-?[0-9.]+,[0-9]{2})([0-9]+,[0-9]{2})", discount_blob)
        if split_match and not percent:
            data.discount_amount = split_match.group(1)
            data.discount_percent = split_match.group(2)
        else:
            data.discount_amount = discount_blob
            data.discount_percent = percent

    totals_idx = _find_index(lines, r"^T\s*o\s*t\s*a\s*l:")
    if totals_idx != -1:
        totals_line = lines[totals_idx]
        m_pcs = re.search(r"pcs\.\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m2 = re.search(r"m2\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m3 = re.search(r"m3\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_gross_weight = re.search(r"gross\s*to\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if m_pcs:
            data.total_pcs = m_pcs.group(1)
        if m_m2:
            data.total_m2 = m_m2.group(1)
        if m_m3:
            data.total_m3 = m_m3.group(1)
        if m_gross_weight:
            data.total_gross_weight = _normalize_kronospan_weight(m_gross_weight.group(1))

    if not data.total_m2:
        data.total_m2 = _match_first(normalized_text, [r"\bm2\s*:\s*([0-9][0-9.,]*)"])
    if not data.total_m3:
        data.total_m3 = _match_first(normalized_text, [r"\bm3\s*:\s*([0-9][0-9.,]*)"])
    data.origin_country = _match_first(normalized_text, [r"COUNTRY\s*OF\s*ORIGIN\s*:\s*([A-Z]{2,})"])

    if "VAT EXEMPT" in normalized_text.upper():
        data.vat_0 = "0,00"
        data.vat_19 = "0,00"

    data.items = _parse_kronospan_items(lines, total_net_fallback=data.total_net)
    if data.total_pcs and data.items:
        has_any_pcs = any(item.pcs_total for item in data.items)
        if not has_any_pcs and len(data.items) == 1:
            data.items[0].pcs_total = data.total_pcs

    return data


def _parse_divian_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    """Parse Divian invoice item rows from extracted text lines."""
    items: list[InvoiceItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if "Á T V I T E L" in upper_line or "ÁT VITEL" in upper_line:
            i += 1
            continue
        if "STCK" not in upper_line and "M2" not in upper_line:
            i += 1
            continue

        item = InvoiceItem(row_no=str(len(items) + 1))
        payload = start_match.group(2)
        item.article_code = start_match.group(1)

        quantity_match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", line)
        if quantity_match:
            item.total_qty = quantity_match.group(0)
        if "M2" in upper_line:
            item.unit = "m2"
        elif "STCK" in upper_line:
            item.unit = "stck"

        description_parts: list[str] = []
        base_description = re.sub(r"\d{1,3}(?:\.\d{3})*,\d{2}.*$", "", payload).strip()
        if base_description:
            description_parts.append(base_description)

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            upper_next = next_line.upper()

            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.search(r"nettó\s*to:", next_line, re.IGNORECASE):
                break
            if "Á T V I T E L" in upper_next or "ÁT VITEL" in upper_next:
                break
            if upper_next.startswith("MINDEN TÉTEL") or upper_next.startswith("A KITERJESZTETT GYÁRTÓI"):
                break

            if upper_next.startswith("EAN:") or upper_next.startswith("RÉSZSZ.:"):
                j += 1
                continue
            if upper_next.startswith("SZÁRMAZÁSI ORSZÁG") or upper_next.startswith("VÁMTARIFASZÁM"):
                j += 1
                continue

            if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", next_line):
                if not item.net_value:
                    item.net_value = next_line
                j += 1
                continue

            article_match = re.match(r"^(\d{4})\s+([A-Z0-9]{2,})$", next_line, re.IGNORECASE)
            if article_match:
                item.article_code = article_match.group(1)
                j += 1
                continue

            pcs_match = re.fullmatch(r"(\d+)\s+([0-9.]+)", next_line)
            if pcs_match:
                item.package_qty = pcs_match.group(1)
                item.pcs_total = pcs_match.group(2)
                j += 1
                continue

            package_match = re.search(
                r"(\d+)\s*csomag\(ok\)\s*a\s*([0-9.]+)\s*darab",
                next_line,
                re.IGNORECASE,
            )
            if package_match:
                item.package_qty = package_match.group(1)
                if not item.pcs_total:
                    try:
                        packages = int(package_match.group(1))
                        per_package = int(package_match.group(2).replace(".", ""))
                        item.pcs_total = str(packages * per_package)
                    except ValueError:
                        pass
                j += 1
                continue

            if "/" in next_line or re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{3,}", next_line):
                description_parts.append(next_line)

            j += 1

        unique_descriptions: list[str] = []
        for part in description_parts:
            cleaned_part = _fix_hungarian_mojibake(_clean_spaces(part))
            if cleaned_part and cleaned_part not in unique_descriptions:
                unique_descriptions.append(cleaned_part)

        if unique_descriptions:
            item.description = " | ".join(unique_descriptions[:3])
        else:
            item.description = _fix_hungarian_mojibake(_clean_spaces(payload))

        if not item.net_value and total_net_fallback and not items:
            item.net_value = total_net_fallback

        items.append(item)
        i = j

    return items


def _parse_divian_invoice_data(lines: list[str], text: str) -> InvoiceData:
    """Parse Divian invoice header and item data."""
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="divian")

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"Számla\s*száma[\s\S]{0,120}?(\d{5,})",
            r"\b(\d{5,}/DIVI\d+)\b",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"számla\s*dátuma\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"Kiállítás\s*dátuma[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.order_confirmation_no = _match_first(
        normalized_text,
        [
            r"\b(WO\d{4,})\b",
            r"Rendelésszám[\s\S]{0,80}?([A-Z0-9/\-]{4,})",
        ],
    )
    data.delivery_note_no = _match_first(normalized_text, [r"Út\s*száma\s*([A-Z0-9/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"Trailer\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_term = _match_first(
        normalized_text,
        [r"\b((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)\b"],
    )

    payment_idx = _find_index(lines, r"^Fizetési feltétel:?$")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        payment_value = _fix_hungarian_mojibake(lines[payment_idx + 1])
        data.payment_term = payment_value
        data.payment_method = payment_value

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[0-9][0-9.,]*\s*Áruérték",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Áruérték"])
    data.total_gross = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Végső\s*összeg"])

    vat_match = re.search(
        r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*([0-9]{1,2},[0-9]{2})\s*ÁFA",
        normalized_text,
        re.IGNORECASE,
    )
    if vat_match:
        vat_amount = vat_match.group(1)
        vat_rate = vat_match.group(2).replace(",", ".")
        if vat_rate.startswith("0"):
            data.vat_0 = vat_amount
        else:
            data.vat_19 = vat_amount

    totals_line = ""
    for line in lines:
        if re.search(r"nettó\s*to:", line, re.IGNORECASE) and re.search(r"bruttó\s*to:", line, re.IGNORECASE):
            totals_line = line
            break

    if totals_line:
        net_weight_match = re.search(r"nettó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        gross_weight_match = re.search(r"bruttó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        pcs_match = re.search(r"Stck:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m2_match = re.search(r"m2:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m3_match = re.search(r"m3:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if net_weight_match:
            data.total_net_weight = net_weight_match.group(1)
        if gross_weight_match:
            data.total_gross_weight = gross_weight_match.group(1)
        if pcs_match:
            data.total_pcs = pcs_match.group(1)
        if m2_match:
            data.total_m2 = m2_match.group(1)
        if m3_match:
            data.total_m3 = m3_match.group(1)

    data.origin_country = _match_first(normalized_text, [r"Származási ország\s*:\s*([A-Z]{2,})"])

    company_blocks: list[list[str]] = []
    seller_candidates: list[tuple[int, list[str]]] = []
    for idx, line in enumerate(lines):
        if "DIVIAN-MEGA KFT" not in line.upper():
            continue

        buyer_block = [line]
        for candidate in lines[idx + 1 : idx + 6]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("RENDELÉSI ADATOK") or upper_candidate.startswith("ADÓSZÁM"):
                break
            if upper_candidate.startswith("CÉGJEGYZÉKSZÁM") or upper_candidate.startswith("EUR "):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            buyer_block.append(candidate)
            if len(buyer_block) >= 3:
                break
        if len(buyer_block) >= 2:
            fixed_buyer_block = [_fix_hungarian_mojibake(entry) for entry in buyer_block]
            company_blocks.append(list(dict.fromkeys(fixed_buyer_block)))

        seller_block = [line]
        seller_score = 0
        for candidate in lines[idx + 1 : idx + 9]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("EUR ") or upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            if upper_candidate.startswith("MNB ÁRFOLYAM") or upper_candidate.startswith("Ö S S Z E S E N"):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("SZÁMLA") or upper_candidate.startswith("OLDAL"):
                break
            seller_block.append(candidate)
            if upper_candidate.startswith("ADÓSZÁM"):
                seller_score += 3
            elif upper_candidate.startswith("CÉGJEGYZÉKSZÁM"):
                seller_score += 2
            elif re.search(r"\b\d{4}\s+[A-ZÁÉÍÓÖŐÚÜŰ]", upper_candidate):
                seller_score += 1

        fixed_seller_block = [_fix_hungarian_mojibake(entry) for entry in seller_block if _clean_spaces(entry)]
        if len(fixed_seller_block) >= 2:
            deduped_seller_block = list(dict.fromkeys(fixed_seller_block[:5]))
            seller_candidates.append((seller_score + len(deduped_seller_block), deduped_seller_block))

    if company_blocks:
        preferred_block = next((b for b in company_blocks if re.search(r"\b\d{4}\b", " ".join(b))), company_blocks[0])
        data.buyer_lines = preferred_block

    if seller_candidates:
        seller_candidates.sort(key=lambda x: x[0], reverse=True)
        data.supplier_lines = seller_candidates[0][1]
        data.supplier_name = data.supplier_lines[0]
    elif company_blocks:
        data.supplier_lines = company_blocks[0]
        data.supplier_name = data.supplier_lines[0]

    data.items = _parse_divian_items(lines, total_net_fallback=data.total_net)
    return data


def parse_invoice_data(text: str) -> InvoiceData:
    """Parse an uploaded invoice into the normalized invoice model."""
    lines = [_clean_spaces(raw) for raw in text.splitlines() if _clean_spaces(raw)]
    profile = _detect_invoice_profile(lines, text)
    if profile == "kastamonu_credit":
        return _parse_kastamonu_credit_note_data(lines, text)
    if profile == "kronospan":
        return _parse_kronospan_invoice_data(lines, text)
    if profile == "gamet":
        return _parse_gamet_invoice_data(lines, text)
    if profile == "divian":
        return _parse_divian_invoice_data(lines, text)
    return _parse_kastamonu_or_generic_invoice_data(lines)


def parse_fields(text: str) -> dict[str, str]:
    """Parse form fields and uploaded PDF text into invoice data."""
    data = parse_invoice_data(text)
    return {
        "invoice_number": data.invoice_number,
        "invoice_date": data.invoice_date,
        "supplier": " | ".join(data.supplier_lines),
        "customer": " | ".join(data.buyer_lines),
        "total_amount": data.total_gross or data.total_net,
        "vat_amount": data.vat_19 or data.vat_0,
    }
