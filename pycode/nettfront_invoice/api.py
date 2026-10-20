"""Fetch NettFront invoice XML and import it into the receiving workflow."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from .engine import MAX_BATCH_XML_BYTES, build_invoice_from_batch, parse_batch_xml
from .store import DuplicateInvoiceError, create_invoice, load_invoice, normalize_invoice_code


NETTFRONT_INVOICE_API_URL = os.getenv(
    "NETTFRONT_INVOICE_API_URL", "http://2020.nettfront.hu:19000/api/invoices/Info"
)
NETTFRONT_INVOICE_VENDOR_CODE = os.getenv("NETTFRONT_INVOICE_VENDOR_CODE", "DIVIAN-SZ")
NETTFRONT_INVOICE_VENDOR_ID = os.getenv("NETTFRONT_INVOICE_VENDOR_ID", "105")


class NettfrontInvoiceApiError(RuntimeError):
    """The supplier API could not provide the requested invoice."""


def invoice_number_from_code(invoice_code: str) -> str:
    code = normalize_invoice_code(invoice_code)
    match = re.fullmatch(r"(?:NF\d{4}[-/])?([0-9]+)", code)
    if match is None:
        raise ValueError("Adj meg számlaszámot (pl. 34727) vagy teljes számlakódot (pl. NF2026-34727).")
    return match.group(1)


def fetch_invoice_xml(invoice_code: str) -> bytes:
    """Fetch the original XML bytes using NettFront's invoice and vendor parameters."""
    invoice_number = invoice_number_from_code(invoice_code)
    query = urllib.parse.urlencode({
        "invNO": invoice_number,
        "VenCode": NETTFRONT_INVOICE_VENDOR_CODE,
        "venID": NETTFRONT_INVOICE_VENDOR_ID,
    })
    request = urllib.request.Request(
        f"{NETTFRONT_INVOICE_API_URL}?{query}", headers={"Accept": "application/xml, text/xml"}
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            xml_data = response.read(MAX_BATCH_XML_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise NettfrontInvoiceApiError(f"A NettFront API hibát jelzett (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise NettfrontInvoiceApiError("A NettFront API nem érhető el vagy nem válaszolt időben.") from exc
    if not xml_data or len(xml_data) > MAX_BATCH_XML_BYTES:
        raise NettfrontInvoiceApiError("A NettFront API üres vagy túl nagy XML-választ adott.")
    return xml_data


def import_invoice_from_api(invoice_code: str, invoice_date: str, operator: str) -> dict:
    """Validate, fetch, and persist an invoice with its complete ICN index."""
    clean_operator = str(operator or "").strip()
    if not clean_operator:
        raise ValueError("Az azonosítás kötelező a számla megnyitásához.")
    clean_date = str(invoice_date or "").strip()
    try:
        parsed_date = date.fromisoformat(clean_date)
    except ValueError as exc:
        raise ValueError("A számla dátuma kötelező, formátuma ÉÉÉÉ-HH-NN.") from exc
    if parsed_date.year < 2000:
        raise ValueError("A számla dátuma érvénytelen.")
    invoice_number = invoice_number_from_code(invoice_code)
    code = normalize_invoice_code(invoice_code)
    if code.isdigit():
        code = f"NF{parsed_date.year}-{invoice_number}"
    if load_invoice(code) is not None:
        raise DuplicateInvoiceError(f"A(z) {code} számlát már korábban rögzítették; nem tölthető fel újra.")
    xml_data = fetch_invoice_xml(invoice_number)
    try:
        batch_data = parse_batch_xml(xml_data)
    except ValueError as exc:
        raise NettfrontInvoiceApiError(f"A NettFront API válasza nem feldolgozható: {exc}") from exc
    if batch_data["invoice_number"] != invoice_number:
        raise NettfrontInvoiceApiError("A NettFront API válaszában eltérő számlaszám szerepel.")
    parsed = build_invoice_from_batch(batch_data, invoice_code=code, invoice_date=clean_date)
    return create_invoice(parsed, xml_data, clean_operator, f"nettfront-{invoice_number}.xml")
