"""Generating helpers for the invoice translator package."""

from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation

from .page import APP_ROUTE, COMMON_SCRIPT_TAG
from .reading import (
    NO_DATA,
    InvoiceData,
    InvoiceItem,
    _clean_spaces,
    _fix_hungarian_mojibake,
    _format_invoice_date,
    _format_rounded_weight,
    _item_value_or_default,
    _require_party_vat_numbers,
    _value_or_default,
    parse_invoice_data,
    split_pdf_by_invoice,
)


def _to_invoice_data(parsed: InvoiceData | dict[str, str]) -> InvoiceData:
    """Provide to invoice data behavior."""
    if isinstance(parsed, InvoiceData):
        return parsed

    data = InvoiceData()
    data.invoice_profile = parsed.get("invoice_profile", "")
    data.supplier_name = parsed.get("supplier_name", "")
    data.invoice_number = parsed.get("invoice_number", "")
    data.invoice_date = parsed.get("invoice_date", "")
    supplier = parsed.get("supplier", "")
    customer = parsed.get("customer", "")
    data.supplier_lines = [line.strip() for line in supplier.split("|") if line.strip()]
    data.buyer_lines = [line.strip() for line in customer.split("|") if line.strip()]
    data.total_gross = parsed.get("total_amount", "")
    data.vat_19 = parsed.get("vat_amount", "")
    return data


def _html_text(value: str) -> str:
    """Provide html text behavior."""
    return html.escape(_value_or_default(value))


def _html_party(lines: list[str], mark_bank_values: bool = False) -> str:
    """Provide html party behavior."""
    if not lines:
        return html.escape(NO_DATA)
    html_lines: list[str] = []
    for line in lines:
        cleaned = _clean_spaces(line)
        if not cleaned:
            continue
        escaped = html.escape(cleaned)
        if mark_bank_values and re.search(r"\b(IBAN|SWIFT)\b", cleaned, flags=re.IGNORECASE):
            escaped = f'<span class="bank-marker">{escaped}</span>'
        html_lines.append(escaped)
    return "<br>".join(html_lines)


def _html_table_rows(rows: list[tuple[str, str]]) -> str:
    """Provide html table rows behavior."""
    return "".join(f"<tr><th>{html.escape(label)}</th><td>{_html_text(value)}</td></tr>" for label, value in rows)


def _non_empty_rows(rows: list[tuple[str, str]], keep_labels: set[str] | None = None) -> list[tuple[str, str]]:
    """Provide non empty rows behavior."""
    if keep_labels is None:
        keep_labels = set()
    filtered: list[tuple[str, str]] = []
    for label, value in rows:
        if label in keep_labels:
            filtered.append((label, value))
            continue
        if _clean_spaces(value):
            filtered.append((label, value))
    return filtered


def _split_vehicle_plates(raw_value: str) -> tuple[str, str]:
    """Provide split vehicle plates behavior."""
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return "", ""

    direct_parts = [part.strip() for part in re.split(r"\s*/\s*|\s*;\s*|\s+\|\s+", cleaned) if part.strip()]
    if len(direct_parts) >= 2:
        return direct_parts[0], direct_parts[1]

    plate_like = re.findall(r"\b[A-Z]{1,4}\d{1,4}[A-Z]{0,3}\b", cleaned.upper())
    if len(plate_like) >= 2:
        return plate_like[0], plate_like[1]

    tokens = cleaned.split()
    if len(tokens) >= 2:
        return tokens[0], tokens[1]

    return cleaned, ""


def _is_takarotabla_item(description: str) -> bool:
    """Return whether is takarotabla item is true."""
    normalized = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    return normalized.startswith("PAL BRUT")


def _is_kastamonu_credit_profile(invoice_profile: str) -> bool:
    """Return whether is kastamonu credit profile is true."""
    return _clean_spaces(invoice_profile).lower() == "kastamonu_credit"


def _parse_money_value(value: str) -> Decimal | None:
    """Parse a displayed invoice money value without assuming one supplier format."""
    cleaned = _clean_spaces(value).replace(" ", "")
    if not cleaned or not re.fullmatch(r"-?[0-9.,]+", cleaned):
        return None

    if "," in cleaned:
        normalized = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") == 1 and len(cleaned.rsplit(".", 1)[1]) == 2:
        normalized = cleaned
    else:
        normalized = cleaned.replace(".", "")

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _format_money_sum(value: Decimal, sample_value: str) -> str:
    """Format a summed money value using the item row's apparent number style."""
    rounded = value.quantize(Decimal("0.01"))
    sample = _clean_spaces(sample_value)
    if "," in sample:
        return f"{rounded:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{rounded:.2f}"


def _sum_item_net_values(items: list[InvoiceItem]) -> str:
    """Return the sum of displayed item net values."""
    total = Decimal("0")
    sample_value = ""
    has_value = False
    for item in items:
        net_value = _clean_spaces(item.net_value)
        if not net_value:
            continue
        parsed = _parse_money_value(net_value)
        if parsed is None:
            return ""
        total += parsed
        sample_value = sample_value or net_value
        has_value = True
    if not has_value:
        return ""
    return _format_money_sum(total, sample_value)


def _detect_product_type(description: str, article_code: str = "", invoice_profile: str = "") -> str:
    """Provide detect product type behavior."""
    normalized_description = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    normalized_code = _fix_hungarian_mojibake(_clean_spaces(article_code)).upper()
    normalized_profile = _fix_hungarian_mojibake(_clean_spaces(invoice_profile)).lower()
    text = f"{normalized_description} {normalized_code}".upper()
    description_prefix = normalized_description.split(" ", 1)[0] if normalized_description else ""
    code_prefix = normalized_code.split(" ", 1)[0] if normalized_code else ""

    if normalized_profile == "kastamonu_credit":
        return "J\u00f3v\u00e1\u00edr\u00e1s"
    if _is_takarotabla_item(description):
        return "takarótábla"
    if normalized_profile == "gamet" and (normalized_code == "TRANSPORT" or "KOSZT TRANSPORTU" in normalized_description):
        return "szállítás"
    if normalized_profile == "gamet":
        return "fogantyú"
    if normalized_profile == "kronospan":
        if "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
            return "munkalap"
        if "SPLASHBACK" in text:
            return "falipanel"
        if "MF PB" in text or "VP P2" in text or "P2EN" in text:
            return "bútorlap"
    if description_prefix.startswith("SP") or code_prefix.startswith("SP"):
        return "falipanel"
    if (
        description_prefix.startswith("WT")
        or description_prefix.startswith("NT")
        or code_prefix.startswith("WT")
        or code_prefix.startswith("NT")
    ):
        return "munkalap"
    if description_prefix.startswith("NFC") or code_prefix.startswith("NFC"):
        return "bútorlap"
    if "EVOGLOSS" in text or "EVGLS" in text:
        return "evogloss lap"
    if "MUNKALAP" in text or "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
        return "munkalap"
    if (
        "HÁTFAL" in text
        or "HATFAL" in text
        or "HDF THIN" in text
        or "THIN PLUS" in text
        or "BACKWALL" in text
        or "BACK WALL" in text
        or "BACKPANEL" in text
        or "BACK PANEL" in text
    ):
        return "hátfal"
    if "FALIPANEL" in text or ("WALL" in text and "PANEL" in text):
        return "falipanel"
    return "bútorlap"


def _render_invoice_item_row(item: InvoiceItem, invoice_profile: str = "") -> str:
    """Render render invoice item row output."""
    product_type = _detect_product_type(item.description, item.article_code, invoice_profile=invoice_profile)
    if _is_kastamonu_credit_profile(invoice_profile):
        return (
            "<tr>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.row_no))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.article_code))}</td>"
            f"<td class='center'>{html.escape(product_type)}</td>"
            f"<td>{html.escape(_item_value_or_default(item.description))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.pcs_total))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.unit))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.net_value))}</td>"
            "</tr>"
        )
    missing_placeholder = "-" if product_type == "takarótábla" else NO_DATA
    if _fix_hungarian_mojibake(_clean_spaces(invoice_profile)).lower() == "gamet":
        return (
            "<tr>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.row_no, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.article_code, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(product_type)}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.total_qty, missing_placeholder))}</td>"
            f"<td class='center'>{html.escape(_item_value_or_default(item.unit, missing_placeholder))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price, missing_placeholder))}</td>"
            f"<td class='right'>{html.escape(_item_value_or_default(item.net_value, missing_placeholder))}</td>"
            "</tr>"
        )
    return (
        "<tr>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.row_no, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.article_code, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(product_type)}</td>"
        f"<td>{html.escape(_item_value_or_default(item.description, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.package_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.pcs_total, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.total_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.unit, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.net_value, missing_placeholder))}</td>"
        "</tr>"
    )


def _render_invoice_total_row(data: InvoiceData) -> str:
    """Render render invoice total row output."""
    total_value = _item_value_or_default(_sum_item_net_values(data.items))
    if _is_kastamonu_credit_profile(data.invoice_profile):
        colspan = "7"
    elif _fix_hungarian_mojibake(_clean_spaces(data.invoice_profile)).lower() == "gamet":
        colspan = "6"
    else:
        colspan = "9"
    return (
        "<tr class='total-row'>"
        f"<td colspan='{colspan}'><strong>Tételek összege</strong></td>"
        f"<td class='right'><strong>{html.escape(total_value)}</strong></td>"
        "</tr>"
    )


def create_printable_html(parsed: InvoiceData | dict[str, str], source_filename: str = "") -> bytes:
    """Provide create printable html behavior."""
    data = _to_invoice_data(parsed)
    truck_plate, trailer_plate = _split_vehicle_plates(data.truck_number)
    vehicle_plates = ""
    if truck_plate and trailer_plate:
        vehicle_plates = f"{truck_plate} - {trailer_plate}"
    elif truck_plate:
        vehicle_plates = truck_plate
    elif trailer_plate:
        vehicle_plates = trailer_plate

    rounded_net_weight = _format_rounded_weight(data.total_net_weight) if data.total_net_weight else ""
    rounded_gross_weight = _format_rounded_weight(data.total_gross_weight) if data.total_gross_weight else ""
    invoice_date_display = _format_invoice_date(data.invoice_date)
    due_date_display = _format_invoice_date(data.due_date)
    source_label = html.escape(source_filename) if source_filename else "feltöltött PDF"
    compact_mode = len(data.items) >= 10 or (len(data.supplier_lines) + len(data.buyer_lines)) >= 12
    body_class = "compact" if compact_mode else ""
    profile_label = {
        "kastamonu": "Kastamonu sablon",
        "kastamonu_credit": "Kastamonu J\u00f3v\u00e1\u00edr\u00f3",
        "kronospan": "Kronospan sablon",
        "gamet": "Gamet sablon",
        "divian": "DIVI sablon",
        "generic": "Általános sablon",
        "": "Általános sablon",
    }.get(data.invoice_profile, "Általános sablon")
    credit_note_title = '<div class="credit-note-title">Jóváíró</div>' if _is_kastamonu_credit_profile(data.invoice_profile) else ""

    info_field_rows = [
        ("Számlaszám", data.invoice_number),
        ("Számla dátuma", invoice_date_display),
        ("Fizetési határidő", due_date_display),
        ("Fizetési mód", data.payment_method),
    ]
    keep_labels = {"Számlaszám", "Számla dátuma"}
    secondary_field_rows = [
        ("Szállítólevél száma", data.delivery_note_no),
    ]
    if data.invoice_profile != "gamet" and not _is_kastamonu_credit_profile(data.invoice_profile):
        secondary_field_rows.append(("Gépjármű azonosító", vehicle_plates))
    info_fields = _non_empty_rows(info_field_rows, keep_labels=keep_labels)
    info_rows = _html_table_rows(info_fields)

    discount_label = "Engedmény"
    if data.discount_percent:
        discount_label = f"Engedmény ({data.discount_percent}%)"

    summary_fields_raw: list[tuple[str, str]] = [
        ("Pénznem", data.currency),
        ("Összeg", data.total_net),
    ]
    if not _is_kastamonu_credit_profile(data.invoice_profile):
        summary_fields_raw.extend(
            [
                (discount_label, data.discount_amount),
                ("Kedvezményes összeg", data.total_gross),
            ]
        )
    summary_fields = _non_empty_rows(
        summary_fields_raw,
        keep_labels=(
            {"Pénznem", "Összeg"}
            if _is_kastamonu_credit_profile(data.invoice_profile)
            else {"Pénznem", "Összeg", "Kedvezményes összeg"}
        ),
    )
    summary_rows = _html_table_rows(summary_fields)
    secondary_field_rows.extend(
        [
            ("Nettó tömeg (kg)", rounded_net_weight),
            ("Bruttó tömeg (kg)", rounded_gross_weight),
            ("Származási ország", data.origin_country),
        ]
    )
    secondary_fields = _non_empty_rows(secondary_field_rows)
    secondary_rows = _html_table_rows(secondary_fields)
    secondary_html = ""
    if secondary_rows:
        secondary_html = f"""
    <section class="secondary-details">
      <h3>Kiegészítő adatok</h3>
      <table class="kv secondary-kv">
        <tbody>{secondary_rows}</tbody>
      </table>
    </section>
"""

    if data.items:
        item_rows = "".join(
            _render_invoice_item_row(item, data.invoice_profile)
            for item in data.items
        )
        item_rows += _render_invoice_total_row(data)
    else:
        if _is_kastamonu_credit_profile(data.invoice_profile):
            empty_colspan = "8"
        elif data.invoice_profile == "gamet":
            empty_colspan = "7"
        else:
            empty_colspan = "10"
        item_rows = f"<tr><td colspan='{empty_colspan}'>Nem sikerült tételsorokat felismerni.</td></tr>"

    if _is_kastamonu_credit_profile(data.invoice_profile):
        items_header = """
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikksz&aacute;m</th>
          <th class="center">Term&eacute;k t&iacute;pus</th>
          <th>Megnevez&eacute;s</th>
          <th class="center">&Ouml;ssz. db</th>
          <th class="center">ME</th>
          <th class="right">Egys&eacute;g&aacute;r</th>
          <th class="right">Nett&oacute; &eacute;rt&eacute;k</th>
        </tr>
        """
    elif data.invoice_profile == "gamet":
        items_header = """
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikkszám</th>
          <th class="center">Termék típus</th>
          <th class="right">Mennyiség</th>
          <th class="center">ME</th>
          <th class="right">Egységár</th>
          <th class="right">Nettó érték</th>
        </tr>
        """
    else:
        items_header = """
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikkszám</th>
          <th class="center">Termék típus</th>
          <th>Megnevezés</th>
          <th class="center">Rakat</th>
          <th class="center">Össz. db</th>
          <th class="right">Mennyiség</th>
          <th class="center">ME</th>
          <th class="right">Egységár</th>
          <th class="right">Nettó érték</th>
        </tr>
        """

    parties_html = f"""
    <section class="parties">
      <article class="panel">
        <h2>Eladó</h2>
        <p>{_html_party(data.supplier_lines, mark_bank_values=True)}</p>
      </article>
      <article class="panel">
        <h2>Vevő</h2>
        <p>{_html_party(data.buyer_lines)}</p>
      </article>
    </section>
"""

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Nyomtatható számlakivonat</title>
  <style>
    :root {{
      --bg: #f3f6f7;
      --bg-soft: #ffffff;
      --ink: #11202b;
      --ink-deep: #08131b;
      --muted: #58717c;
      --line: #cfdee2;
      --surface: #ffffff;
      --accent: #36d7c3;
      --accent-strong: #149c90;
      --accent-soft: #e3fff8;
      --accent-warm: #c7ff7a;
      --paper: #eff5f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 1rem 1rem 1.25rem;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.32;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .toolbar {{
      max-width: 210mm;
      margin: 0 auto .65rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
      padding: 0 .15rem;
    }}
    .toolbar-group {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
    }}
    .toolbar-note {{
      color: rgba(237, 247, 247, .72);
      font-size: .76rem;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .toolbar button,
    .toolbar a {{
      border: 1px solid rgba(54, 215, 195, .22);
      background: rgba(7, 17, 26, .72);
      color: #edf7f7;
      padding: .55rem .86rem;
      border-radius: 999px;
      cursor: pointer;
      font-size: .84rem;
      font-weight: 700;
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
      backdrop-filter: blur(12px);
    }}
    .toolbar a {{
      color: #edf7f7;
    }}
    .toolbar button {{
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      border-color: transparent;
      color: #041017;
    }}
    .toolbar button:hover,
    .toolbar a:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 22px rgba(0, 0, 0, .2);
      border-color: rgba(54, 215, 195, .4);
    }}
    .sheet {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto .8rem;
      background: var(--surface);
      padding: 8.5mm 8.5mm 8mm;
      border: 1px solid #d6e7e8;
      border-top: 6px solid var(--accent-strong);
      border-radius: 10px;
      box-shadow: 0 12px 28px rgba(10, 24, 32, .13);
      position: relative;
      overflow: hidden;
    }}
    .head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.2rem;
      border-bottom: 1px solid #d9e7e8;
      padding-bottom: .55rem;
      margin-bottom: .75rem;
      position: relative;
      z-index: 1;
    }}
    .head-copy {{
      max-width: 62%;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: .38rem;
      padding: .24rem .5rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      letter-spacing: .12em;
      text-transform: uppercase;
      font-size: .64rem;
      font-weight: 800;
      margin-bottom: .45rem;
    }}
    .head h1 {{
      margin: 0;
      font-size: 1.14rem;
      letter-spacing: .12px;
      color: var(--ink-deep);
    }}
    .credit-note-title {{
      margin: 0 0 .22rem;
      color: var(--ink-deep);
      font-size: 1.36rem;
      font-weight: 900;
      line-height: 1.05;
      text-transform: uppercase;
    }}
    .head-copy p {{
      margin: .3rem 0 0;
      color: var(--muted);
      font-size: .78rem;
    }}
    .meta {{
      min-width: 220px;
      display: grid;
      gap: .34rem;
    }}
    .meta div {{
      padding: .44rem .58rem;
      border: 1px solid #d9e7e8;
      border-radius: 10px;
      background: linear-gradient(180deg, #fcfefe 0%, #f5fbfb 100%);
      font-size: .73rem;
      color: var(--muted);
    }}
    .meta strong {{
      display: block;
      margin-top: .08rem;
      color: var(--ink-deep);
      font-size: .82rem;
    }}
    .parties {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .6rem;
      margin-bottom: .62rem;
      position: relative;
      z-index: 1;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .5rem;
      margin-bottom: .48rem;
      align-items: start;
      position: relative;
      z-index: 1;
    }}
    .meta-card {{
      min-width: 0;
    }}
    .panel {{
      border: 1px solid #d5e5e6;
      border-radius: 12px;
      padding: .46rem .54rem;
      background: linear-gradient(180deg, #fefefe 0%, #f4fbfb 100%);
    }}
    .panel h2 {{
      margin: 0 0 .24rem 0;
      font-size: .74rem;
      color: var(--accent-strong);
      text-transform: uppercase;
      letter-spacing: .14em;
    }}
    .panel p {{
      margin: 0;
      white-space: normal;
      font-size: .8rem;
    }}
    .bank-marker {{
      display: inline-block;
      padding: .08rem .24rem;
      border: 1px solid var(--accent-strong);
      border-radius: 4px;
      background: #f1fffb;
      color: var(--ink-deep);
      font-weight: 800;
    }}
    h3 {{
      margin: .58rem 0 .24rem 0;
      font-size: .76rem;
      text-transform: uppercase;
      letter-spacing: .14em;
      color: var(--accent-strong);
      border-left: 3px solid var(--accent);
      padding-left: .42rem;
      position: relative;
      z-index: 1;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .74rem;
      margin-bottom: .42rem;
      position: relative;
      z-index: 1;
    }}
    th,
    td {{
      border: 1px solid var(--line);
      padding: .18rem .24rem;
      vertical-align: top;
    }}
    th {{
      background: linear-gradient(180deg, #f3fefb 0%, #e9faf6 100%);
      font-weight: 700;
      text-align: left;
    }}
    .kv {{
      table-layout: fixed;
      margin-bottom: 0;
    }}
    .meta-card .kv {{
      font-size: .79rem;
    }}
    .meta-card .kv th,
    .meta-card .kv td {{
      padding: 6px;
      line-height: 1.28;
    }}
    .meta-card .kv th {{
      width: 58%;
      white-space: nowrap;
    }}
    .meta-card .kv td {{
      font-weight: 600;
    }}
    .items td:nth-child(4) {{ line-height: 1.2; }}
    .items tbody tr:nth-child(even) {{
      background: #f8fcfb;
    }}
    .secondary-details {{
      margin-top: .1rem;
      position: relative;
      z-index: 1;
    }}
    .secondary-details h3 {{
      color: var(--muted);
      border-left-color: #9fb5bb;
    }}
    .secondary-kv {{
      max-width: 122mm;
      font-size: .66rem;
      color: var(--muted);
    }}
    .secondary-kv th,
    .secondary-kv td {{
      padding: .13rem .2rem;
      line-height: 1.2;
    }}
    .secondary-kv th {{
      width: 34%;
      background: #f7faf9;
      color: var(--muted);
    }}
    .center {{ text-align: center; }}
    .right {{ text-align: right; }}
    .footnote {{
      margin-top: .38rem;
      border-top: 1px dashed #b7cfd0;
      padding-top: .32rem;
      font-size: .68rem;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }}
    body.compact .sheet {{
      padding: 7.8mm 8mm 7.4mm;
    }}
    body.compact .head h1 {{
      font-size: 1.02rem;
    }}
    body.compact .meta {{
      gap: .3rem;
    }}
    body.compact .meta div {{
      font-size: .7rem;
      padding: .38rem .5rem;
    }}
    body.compact .panel p {{
      font-size: .76rem;
    }}
    body.compact h3 {{
      margin: .42rem 0 .2rem 0;
      font-size: .74rem;
    }}
    body.compact table {{
      font-size: .72rem;
      margin-bottom: .34rem;
    }}
    body.compact th,
    body.compact td {{
      padding: .14rem .18rem;
    }}
    body.compact .meta-card .kv {{
      font-size: .74rem;
    }}
    body.compact .meta-card .kv th,
    body.compact .meta-card .kv td {{
      padding: 5px;
      line-height: 1.22;
    }}
    body.compact .meta-card .kv th {{
      width: 55%;
    }}
    @media (max-width: 860px) {{
      body {{
        padding: .65rem;
      }}
      .toolbar {{
        justify-content: center;
      }}
      .toolbar-note {{
        width: 100%;
        text-align: center;
      }}
      .meta-grid {{
        grid-template-columns: 1fr;
      }}
      .parties {{
        grid-template-columns: 1fr;
      }}
      .head {{
        flex-direction: column;
      }}
      .head-copy {{
        max-width: none;
      }}
      .meta {{
        width: 100%;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @page {{
      size: 210mm 297mm;
      margin: 6mm;
    }}
    @media print {{
      html {{
        width: 100%;
        height: auto;
        min-height: 0;
      }}
      body {{
        width: 100%;
        height: auto;
        min-height: 0;
        padding: 0;
        background: #fff;
        display: block;
        -webkit-print-color-adjust: economy;
        print-color-adjust: economy;
      }}
      .toolbar {{ display: none; }}
      .meta {{ display: none; }}
      .sheet {{
        margin: 0;
        width: auto;
        max-width: none;
        min-height: auto;
        padding: 0;
        border: 0;
        border-radius: 0;
        box-shadow: none;
        transform: none;
        overflow: visible;
      }}
      .eyebrow,
      .credit-note-title,
      .panel,
      .meta div,
      th,
      .items tbody tr:nth-child(even),
      .bank-marker,
      .secondary-kv th {{
        background: transparent;
      }}
      .panel,
      .bank-marker {{
        border-color: #777;
      }}
      .meta-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .parties {{
        grid-template-columns: 1fr 1fr;
      }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body class="{body_class}">
  <div class="toolbar">
    <span class="toolbar-note">Divian-HUB // nyomtatható kivonat</span>
    <div class="toolbar-group">
      <a href="/">Főoldal</a>
      <a href="{APP_ROUTE}">Új számla</a>
      <button onclick="window.print()">Nyomtatás / Mentés PDF-be</button>
    </div>
  </div>
  <main class="sheet">
    <header class="head">
      <div class="head-copy">
        <div class="eyebrow">Divian-HUB kimenet</div>
        {credit_note_title}
        <h1>Külföldi számla magyar fordítása</h1>
        <p>Automatikusan generált, nyomtatható kivonat egységes vállalati megjelenéssel.</p>
      </div>
      <div class="meta">
        <div>Gyártó<strong>{html.escape(data.supplier_name or NO_DATA)}</strong></div>
        <div>Sablon<strong>{profile_label}</strong></div>
        <div>Forrás<strong>{source_label}</strong></div>
      </div>
    </header>

{parties_html}

    <section class="meta-grid">
      <article class="meta-card">
        <h3>Számla adatok</h3>
        <table class="kv">
          <tbody>{info_rows}</tbody>
        </table>
      </article>
      <article class="meta-card">
        <h3>Összesítés</h3>
        <table class="kv">
          <tbody>{summary_rows}</tbody>
        </table>
      </article>
    </section>

    <h3>Tételek</h3>
    <table class="items">
      <thead>
        {items_header}
      </thead>
      <tbody>{item_rows}</tbody>
    </table>
{secondary_html}

    <div class="footnote">
      Ez egy automatikusan generált, nyomtatható fordítási kivonat.
    </div>
  </main>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")

def build_invoice_response(file_name: str, file_data: bytes) -> tuple[int, bytes, str, dict[str, str]]:
    """Build build invoice response data."""
    chunks = split_pdf_by_invoice(file_data)
    chunk = chunks[0]
    parsed = parse_invoice_data(chunk.text)
    _require_party_vat_numbers(parsed)
    source_label = file_name
    if chunk.page_from != chunk.page_to:
        source_label = f"{file_name} (oldalak: {chunk.page_from}-{chunk.page_to})"
    printable_html = create_printable_html(parsed, source_filename=source_label)
    return 200, printable_html, "text/html; charset=utf-8", {"Cache-Control": "no-store"}
