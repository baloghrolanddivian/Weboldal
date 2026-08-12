"""Template-based HR document generation, using only in-memory person data."""

from __future__ import annotations

import calendar
import copy
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ODT_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
ODT_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODT_STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
ET.register_namespace("w", DOCX_NS)
ET.register_namespace("table", ODT_TABLE)
ET.register_namespace("text", ODT_TEXT)


def _source_namespaces(xml_data: bytes) -> list[tuple[str, str]]:
    """Return namespace declarations in source order, including unused ones."""
    namespaces: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for _event, declaration in ET.iterparse(io.BytesIO(xml_data), events=("start-ns",)):
        prefix, uri = declaration
        item = (prefix or "", uri)
        if item not in seen:
            namespaces.append(item)
            seen.add(item)
    return namespaces


def _serialize_xml(root: ET.Element, namespaces: list[tuple[str, str]]) -> bytes:
    """Serialize XML while retaining the template's namespace prefixes.

    ElementTree normally discards declarations used only by values such as
    ``mc:Ignorable``. Word treats those dangling prefix references as damaged
    OOXML, so restore every original declaration on the document root.
    """
    for prefix, uri in namespaces:
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            # ElementTree reserves generated prefixes such as ``ns0``.
            continue
    xml_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    declaration_end = xml_data.find(b"?>")
    root_start = xml_data.find(b"<", declaration_end + 2 if declaration_end >= 0 else 0)
    root_end = xml_data.find(b">", root_start)
    if root_start < 0 or root_end < 0:
        return xml_data
    root_tag = xml_data[root_start:root_end]
    additions = []
    for prefix, uri in namespaces:
        attribute = f"xmlns:{prefix}" if prefix else "xmlns"
        if re.search(rb"\s" + re.escape(attribute.encode("ascii")) + rb"\s*=", root_tag):
            continue
        additions.append(f" {attribute}={quoteattr(uri)}".encode("utf-8"))
    if not additions:
        return xml_data
    return xml_data[:root_end] + b"".join(additions) + xml_data[root_end:]


def _use_poppins(run: ET.Element, size_half_points: int | None = None) -> None:
    """Set the font without disturbing other run formatting."""
    props = run.find(f"{{{DOCX_NS}}}rPr")
    if props is None:
        props = ET.Element(f"{{{DOCX_NS}}}rPr")
        run.insert(0, props)
    fonts = props.find(f"{{{DOCX_NS}}}rFonts")
    if fonts is None:
        fonts = ET.SubElement(props, f"{{{DOCX_NS}}}rFonts")
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(f"{{{DOCX_NS}}}{attribute}", "Poppins")
    if size_half_points is not None:
        size = props.find(f"{{{DOCX_NS}}}sz")
        if size is None:
            size = ET.SubElement(props, f"{{{DOCX_NS}}}sz")
        size.set(f"{{{DOCX_NS}}}val", str(size_half_points))
        size_cs = props.find(f"{{{DOCX_NS}}}szCs")
        if size_cs is None:
            size_cs = ET.SubElement(props, f"{{{DOCX_NS}}}szCs")
        size_cs.set(f"{{{DOCX_NS}}}val", str(size_half_points))


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip().casefold()


def _date(value: str) -> str:
    raw = str(value or "").strip()
    for fmt in ("%Y.%m.%d.", "%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y.%m.%d")
        except ValueError:
            continue
    return raw


def _three_months(value: str) -> str:
    for fmt in ("%Y.%m.%d.", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(value.strip(), fmt).date()
            month = d.month + 3
            year = d.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            anniversary = date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
            return (anniversary - timedelta(days=1)).strftime("%Y.%m.%d.")
        except ValueError:
            continue
    return value


def format_payment(value: str) -> str:
    """Format an integer payment with Hungarian thousands separators."""
    raw = str(value or "").strip()
    digits = re.sub(r"[.\s]", "", raw)
    if not digits.isdigit():
        return raw
    return f"{int(digits):,}".replace(",", ".")


ONES = ("nulla", "egy", "kettő", "három", "négy", "öt", "hat", "hét", "nyolc", "kilenc")
TEENS = ("tíz", "tizenegy", "tizenkettő", "tizenhárom", "tizennégy", "tizenöt", "tizenhat", "tizenhét", "tizennyolc", "tizenkilenc")
TENS = ("", "", "húsz", "harminc", "negyven", "ötven", "hatvan", "hetven", "nyolcvan", "kilencven")


def _hundred(n: int) -> str:
    if n < 10: return ONES[n]
    if n < 20: return TEENS[n - 10]
    if n < 100:
        prefix = "huszon" if n // 10 == 2 and n % 10 else TENS[n // 10]
        return prefix + ("" if n % 10 == 0 else ONES[n % 10])
    hundreds = "száz" if n // 100 == 1 else ("két" if n // 100 == 2 else ONES[n // 100]) + "száz"
    return hundreds + ("" if n % 100 == 0 else _hundred(n % 100))


def number_hu(value: str) -> str:
    raw = str(value or "").replace(" ", "").replace(".", "").replace(",", ".")
    try: amount = float(raw)
    except ValueError: return value
    integer = int(amount)
    if integer == 0: return "nulla"
    if integer < 0:
        return "mínusz " + number_hu(str(abs(integer)))
    groups: list[int] = []
    remaining = integer
    while remaining:
        remaining, group = divmod(remaining, 1000)
        groups.append(group)
    scale_names = ("", "ezer", "millió", "milliárd", "billió")
    if len(groups) > len(scale_names):
        return value
    parts = []
    for scale_index in range(len(groups) - 1, -1, -1):
        group = groups[scale_index]
        if not group:
            continue
        if scale_index == 0:
            parts.append(_hundred(group))
            continue
        prefix = "" if group == 1 else ("két" if group == 2 else _hundred(group))
        parts.append(prefix + scale_names[scale_index])
    separator = "-" if integer >= 2000 else ""
    return separator.join(parts)


def _template_kind(path: Path) -> str:
    return path.stem.casefold().replace("ő", "ö").replace("ű", "ü")


def _find_template(root: Path, needle: str) -> Path | None:
    needle = _norm(needle)
    for path in root.iterdir():
        if path.suffix.lower() not in {".docx", ".odt"}: continue
        if needle in _norm(path.stem): return path
    return None


def _replace_all(root: ET.Element, replacements: dict[str, str], text_tags: str) -> None:
    """Replace placeholders even when Word split them across multiple runs."""
    paragraph_tag = f"{{{ODT_TEXT}}}p" if f"{{{ODT_TEXT}}}p" in text_tags else f"{{{DOCX_NS}}}p"
    for parent in root.iter(paragraph_tag):
        text_nodes = [node for node in parent.iter() if node.tag in text_tags]
        if not text_nodes: continue
        def apply(text: str, selected: dict[str, str] | None = None) -> str:
            changed = text
            source = selected if selected is not None else replacements
            for old, new in sorted(source.items(), key=lambda item: len(str(item[0])), reverse=True):
                # Word often stores visible phrases with multiple spaces between runs.
                if old == "__PAYMENT_PLACEHOLDER__":
                    pattern = r"\s*,-\s*Ft\s*/\s*hó"
                elif old == "__SZABADSAG_VAT__":
                    pattern = r"Adó\s*azonosító\s*jel\s*:\s*\."
                else:
                    pattern = re.escape(str(old)).replace(r"\ ", r"\s+")
                changed = re.sub(pattern, str(new), changed)
            return changed

        # Replace in the original runs first so bold/italic formatting survives.
        # A short token is deferred when its longer compound placeholder is
        # present in the same paragraph.
        paragraph_source = "".join(node.text or "" for node in text_nodes)
        local_replacements = {}
        for key, value in replacements.items():
            if key == "__PAYMENT_PLACEHOLDER__":
                local_replacements[key] = value
                continue
            has_longer_placeholder = any(
                len(str(other_key)) > len(str(key))
                and str(key) in str(other_key)
                and re.search(re.escape(str(other_key)).replace(r"\ ", r"\s+"), paragraph_source)
                for other_key in replacements
            )
            if not has_longer_placeholder:
                local_replacements[key] = value
        for node in text_nodes:
            before = node.text or ""
            node.text = apply(before, local_replacements)
            if node.text != before:
                for candidate in parent.iter(f"{{{DOCX_NS}}}r"):
                    if node in list(candidate):
                        _use_poppins(candidate)

        original = "".join(c.text or "" for c in text_nodes)
        changed = apply(original)
        if changed != original:
            text_nodes[0].text = changed
            for candidate in parent.iter(f"{{{DOCX_NS}}}r"):
                _use_poppins(candidate)
            for node in text_nodes[1:]: node.text = ""


def _set_bold(run: ET.Element) -> None:
    """Make a run bold while retaining its existing character formatting."""
    props = run.find(f"{{{DOCX_NS}}}rPr")
    if props is None:
        props = ET.Element(f"{{{DOCX_NS}}}rPr")
        run.insert(0, props)
    bold = props.find(f"{{{DOCX_NS}}}b")
    if bold is None:
        bold = ET.SubElement(props, f"{{{DOCX_NS}}}b")
    bold.set(f"{{{DOCX_NS}}}val", "1")


def _replace_split_placeholder(
    root: ET.Element,
    old: str,
    new: str,
    text_tags: set[str],
    *,
    force_bold: bool = False,
    paragraph_filter=None,
    last_only: bool = False,
) -> int:
    """Replace a phrase split between Word runs without losing its run style.

    Word often splits a highlighted placeholder (for example ``amely része a
    munkaidőnek``) into several runs.  The generic replacement fallback must
    then collapse it into the paragraph's first run, which can be unbolded.
    This targeted helper keeps the replacement in the run where the
    placeholder starts and clears only the remaining placeholder fragments.
    """
    paragraph_tag = f"{{{ODT_TEXT}}}p" if f"{{{ODT_TEXT}}}p" in text_tags else f"{{{DOCX_NS}}}p"
    replaced = 0
    for paragraph in root.iter(paragraph_tag):
        paragraph_text = "".join(paragraph.itertext())
        if paragraph_filter is not None and not paragraph_filter(paragraph_text):
            continue
        text_nodes = [node for node in paragraph.iter() if node.tag in text_tags]
        if not text_nodes:
            continue
        combined = "".join(node.text or "" for node in text_nodes)
        positions: list[int] = []
        offset = 0
        while True:
            found = combined.find(old, offset)
            if found < 0:
                break
            positions.append(found)
            offset = found + len(old)
        if last_only and positions:
            positions = positions[-1:]
        for start in reversed(positions):
            end = start + len(old)
            cursor = 0
            start_index = end_index = None
            start_offset = end_offset = 0
            for index, node in enumerate(text_nodes):
                node_text = node.text or ""
                node_end = cursor + len(node_text)
                if start_index is None and start < node_end:
                    start_index, start_offset = index, start - cursor
                if end <= node_end:
                    end_index, end_offset = index, end - cursor
                    break
                cursor = node_end
            if start_index is None or end_index is None:
                continue
            start_node = text_nodes[start_index]
            end_node = text_nodes[end_index]
            before = (start_node.text or "")[:start_offset]
            after = (end_node.text or "")[end_offset:]
            if start_node is end_node:
                start_node.text = before + str(new) + after
            else:
                start_node.text = before + str(new)
                for node in text_nodes[start_index + 1:end_index]:
                    node.text = ""
                end_node.text = after
            if force_bold:
                for run in paragraph.iter(f"{{{DOCX_NS}}}r"):
                    if start_node in list(run):
                        _set_bold(run)
                        _use_poppins(run)
                        break
            replaced += 1
    return replaced


def _append_cell(cell: ET.Element, value: str, odt: bool = False) -> None:
    """Append a value beside an existing label without destroying its formatting."""
    if odt:
        paragraph = cell.find(f"{{{ODT_TEXT}}}p")
        if paragraph is None:
            paragraph = ET.SubElement(cell, f"{{{ODT_TEXT}}}p")
        paragraph.text = (paragraph.text or "") + " " + str(value)
        return
    paragraph = cell.find(f".//{{{DOCX_NS}}}p")
    if paragraph is None:
        paragraph = ET.SubElement(cell, f"{{{DOCX_NS}}}p")
    source_run = paragraph.find(f"{{{DOCX_NS}}}r")
    run = ET.SubElement(paragraph, f"{{{DOCX_NS}}}r")
    if source_run is not None:
        source_props = source_run.find(f"{{{DOCX_NS}}}rPr")
        if source_props is not None:
            run.append(copy.deepcopy(source_props))
    _use_poppins(run, size_half_points=20)
    text = ET.SubElement(run, f"{{{DOCX_NS}}}t")
    text.text = " " + str(value)
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _set_cell_width(cell: ET.Element, width_twips: int) -> None:
    props = cell.find(f"{{{DOCX_NS}}}tcPr")
    if props is None:
        props = ET.Element(f"{{{DOCX_NS}}}tcPr")
        cell.insert(0, props)
    width = props.find(f"{{{DOCX_NS}}}tcW")
    if width is None:
        width = ET.SubElement(props, f"{{{DOCX_NS}}}tcW")
    width.set(f"{{{DOCX_NS}}}w", str(width_twips))
    width.set(f"{{{DOCX_NS}}}type", "dxa")


def _set_cell(cell: ET.Element, value: str, odt: bool = False, no_wrap: bool = False, min_width_twips: int | None = None) -> None:
    if odt:
        for child in list(cell):
            if child.tag != f"{{{ODT_TABLE}}}table-cell": cell.remove(child)
        p = ET.SubElement(cell, f"{{{ODT_TEXT}}}p")
        p.text = str(value)
        return
    props = cell.find(f"{{{DOCX_NS}}}tcPr")
    source_run = cell.find(f".//{{{DOCX_NS}}}r")
    source_props = copy.deepcopy(source_run.find(f"{{{DOCX_NS}}}rPr")) if source_run is not None and source_run.find(f"{{{DOCX_NS}}}rPr") is not None else None
    if no_wrap and props is not None and props.find(f"{{{DOCX_NS}}}noWrap") is None:
        ET.SubElement(props, f"{{{DOCX_NS}}}noWrap")
    if min_width_twips is not None and props is not None:
        width = props.find(f"{{{DOCX_NS}}}tcW")
        if width is None:
            width = ET.SubElement(props, f"{{{DOCX_NS}}}tcW")
        width.set(f"{{{DOCX_NS}}}w", str(min_width_twips))
        width.set(f"{{{DOCX_NS}}}type", "dxa")
    for child in list(cell):
        if child is not props: cell.remove(child)
    paragraph = ET.SubElement(cell, f"{{{DOCX_NS}}}p")
    run = ET.SubElement(paragraph, f"{{{DOCX_NS}}}r")
    if source_props is not None:
        run.append(source_props)
    _use_poppins(run, size_half_points=20)
    text = ET.SubElement(run, f"{{{DOCX_NS}}}t")
    text.text = str(value)


def _fill_label_cells(root: ET.Element, values: dict[str, str], odt: bool = False, skip_labels: set[str] | None = None, append_same_cell: bool = False) -> None:
    row_tag = f"{{{ODT_TABLE}}}table-row" if odt else f"{{{DOCX_NS}}}tr"
    cell_tag = f"{{{ODT_TABLE}}}table-cell" if odt else f"{{{DOCX_NS}}}tc"
    label_map = {_norm(k): v for k, v in values.items()}
    skip_labels = skip_labels or set()
    for row in root.iter(row_tag):
        cells = list(row.iter(cell_tag)) if odt else row.findall(cell_tag)
        for index, cell in enumerate(cells):
            label = _norm("".join(cell.itertext()))
            for wanted, replacement in label_map.items():
                if wanted in skip_labels:
                    continue
                # Do not treat signature lines such as ``NÉV:________`` as data fields.
                # They may contain nested tables/boxes whose structure must be preserved.
                label_tail = label[len(wanted):].strip() if label.startswith(wanted) else ""
                is_empty_label = label == wanted or label == wanted + ":"
                if is_empty_label:
                    target = cells[index + 1] if index + 1 < len(cells) and not _norm("".join(cells[index + 1].itertext())) else cell
                    if target is cell:
                        # Keep the label in ODT's single-cell form and append the value.
                        if odt: replacement = f"{''.join(cell.itertext()).strip()} {replacement}"
                    if target is cell and append_same_cell:
                        _append_cell(target, replacement, odt)
                    else:
                        _set_cell(target, replacement, odt)
                    break


def _clean_colours(root: ET.Element, odt: bool = False) -> None:
    if odt:
        for element in root.iter():
            for key in list(element.attrib):
                if "color" in key.casefold() or "background" in key.casefold(): del element.attrib[key]
        return
    colour_tags = {f"{{{DOCX_NS}}}highlight", f"{{{DOCX_NS}}}shd"}
    for parent in root.iter():
        for child in list(parent):
            if child.tag in colour_tags:
                parent.remove(child)
    for element in root.iter():
        for key in list(element.attrib):
            if key.endswith("color") or key.endswith("fill"): del element.attrib[key]


def _split_address(value: str) -> tuple[str, str, str, str]:
    """Split a Hungarian address into postal code, city, street, and number."""
    raw = re.sub(r"\s+", " ", str(value or "").strip())
    match = re.match(r"^(\d{4})\s+([^,]+?)[, ]+(.+?)\s+(\d+[A-Za-z]?)\.?$", raw)
    if not match:
        return "", raw, raw, ""
    return match.group(1), match.group(2).strip(), match.group(3).strip(), match.group(4)


def _fill_szep_card(root: ET.Element, values: dict[str, str]) -> None:
    """Fill the fixed multi-column layout of the SZÉP card application form."""
    rows = root.findall(f".//{{{DOCX_NS}}}tr")
    postal, city, street, number = _split_address(values.get("address", ""))
    mailing_postal, mailing_city, mailing_street, mailing_number = postal, city, street, number
    row_values = {
        0: [(1, values.get("name", ""))],
        1: [(1, values.get("birthname", ""))],
        2: [(1, values.get("momname", ""))],
        3: [(1, values.get("birthplace", "")), (3, values.get("birthday", ""))],
        4: [(1, postal), (4, city)],
        5: [(1, street), (3, number)],
        6: [(1, mailing_postal), (4, mailing_city)],
        7: [(1, mailing_street), (3, mailing_number)],
        8: [(1, values.get("email", ""))],
        9: [(1, values.get("phone", ""))],
        10: [(1, values.get("name", ""))],
    }
    for row_index, assignments in row_values.items():
        if row_index >= len(rows):
            continue
        cells = rows[row_index].findall(f"{{{DOCX_NS}}}tc")
        for cell_index, value in assignments:
            if cell_index < len(cells) and value:
                _set_cell(
                    cells[cell_index], value,
                    no_wrap=(row_index in {5, 7} and cell_index == 3),
                    min_width_twips=(650 if row_index in {5, 7} and cell_index == 3 else None),
                )
        # Postal-code labels are part of the cell layout and do not have a
        # separate empty cell in the source document; keep the label and add the value beside it.
        if row_index in {4, 6} and postal and len(cells) > 1:
            label_cell = cells[1]
            _set_cell(label_cell, f"Irányítószám / Postal code: {postal}")
        if row_index in {5, 7} and len(cells) > 3:
            # The template allocates only 236 twips to the house-number value.
            # Take width from its label cell so multi-digit numbers stay on one line.
            _set_cell_width(cells[2], 1078)
            _set_cell_width(cells[3], 650)


def _edit_template(template: Path, values: dict[str, str], replacements: dict[str, str]) -> bytes:
    with zipfile.ZipFile(template) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    odt = template.suffix.lower() == ".odt"
    xml_name = "content.xml" if odt else "word/document.xml"
    source_xml = entries[xml_name]
    namespaces = _source_namespaces(source_xml)
    root = ET.fromstring(source_xml)
    if odt:
        text_tags = {f"{{{ODT_TEXT}}}p", f"{{{ODT_TEXT}}}span"}
    else:
        text_tags = {f"{{{DOCX_NS}}}t"}
    if "szép" in template.stem.casefold():
        _fill_szep_card(root, values)
    skip_labels = {_norm("NÉV"), _norm("NÉV:")} if template.stem.casefold().startswith("gdpr") else set()
    append_same_cell = any(marker in template.stem.casefold() for marker in ("munkaközi szünet", "munkaszerződés"))
    if "szép" not in template.stem.casefold():
        _fill_label_cells(root, values, odt, skip_labels=skip_labels, append_same_cell=append_same_cell)
    replacements_to_apply = replacements
    if "szép" in template.stem.casefold():
        # The SZÉP form uses the employee's own mobile/e-mail fields; boss
        # contact placeholders belong only to the work-time information form.
        replacements_to_apply = {
            key: value for key, value in replacements.items()
            if key not in {"+3630", ".....@divian.hu"}
        }
    elif "szabadság" in template.stem.casefold():
        replacements_to_apply = {
            key: value for key, value in replacements.items()
            if key != "Adóazonosító jel: ."
        }
    else:
        replacements_to_apply = {
            key: value for key, value in replacements.items() if _norm(key) not in {_norm("NÉV"), _norm("NÉV:")}
        }

    template_name = template.stem.casefold()
    # These placeholders are intentionally bold in the templates, but Word
    # stores several of them in multiple runs.  Replace them before the
    # generic fallback so both choices keep the intended bold appearance.
    if "munkaközi szünet" in template_name:
        for placeholder, value in (
            ("30 perc", replacements.get("30 perc", "")),
            ("harminc perc", replacements.get("harminc perc", "")),
            ("amely része a munkaidőnek", replacements.get("amely része a munkaidőnek", "")),
        ):
            _replace_split_placeholder(root, placeholder, value, text_tags, force_bold=True)
            replacements_to_apply.pop(placeholder, None)

    if "munkaszerződés" in template_name:
        workplace_placeholder = "6724 Szeged, Trafó köz 3."
        workplace_value = replacements.get(workplace_placeholder, "")
        # In the work-location sentence the address is bold; the company
        # address elsewhere in the contract is deliberately not.  Preserve
        # that distinction for either selected workplace.
        _replace_split_placeholder(
            root,
            workplace_placeholder,
            workplace_value,
            text_tags,
            force_bold=True,
            paragraph_filter=lambda text: "munkahelyen" in _norm(text),
        )
        _replace_split_placeholder(root, workplace_placeholder, workplace_value, text_tags)
        replacements_to_apply.pop(workplace_placeholder, None)

    if "munkaruha" in template_name:
        # The first occurrence is the label ``Dátum:``, while only the second
        # standalone placeholder after ``Szeged,`` belongs to the document.
        _replace_split_placeholder(root, "Dátum", replacements.get("Dátum", ""), text_tags, last_only=True)
        replacements_to_apply.pop("Dátum", None)

    _replace_all(root, replacements_to_apply, text_tags)
    _clean_colours(root, odt)
    entries[xml_name] = _serialize_xml(root, namespaces)
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items(): target.writestr(name, data)
    return result.getvalue()


def build_hr_documents(people: list[dict[str, str]], extra: dict[str, str] | list[dict[str, str]], template_dir: Path) -> tuple[bytes, str]:
    """Return a ZIP of one generated copy of every available HR template per person."""
    if isinstance(extra, list) and len(extra) != len(people):
        raise ValueError("A személyek és a személyenkénti kiegészítő adatok száma eltér.")
    output = io.BytesIO()
    generated = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, person in enumerate(people):
            person = dict(person)
            if not str(person.get("stayaddress", "")).strip():
                person["stayaddress"] = str(person.get("address", ""))
            person_extra = dict(extra[index]) if isinstance(extra, list) else (dict(extra) if isinstance(extra, dict) else {})
            boss = person_extra.get("boss", "")
            boss_data = person_extra.get("boss_data", {}) if isinstance(person_extra.get("boss_data"), dict) else {}
            values = {**person, **person_extra, "date": _date(person.get("entry", "")), "bossphone": boss_data.get("phone", ""), "bossemail": boss_data.get("email", "")}
            values["birthplace+birthday"] = f"{person.get('birthplace', '')}, {person.get('birthday', '')}".strip(" ,")
            values["orderfrom+orderfromname"] = person_extra.get("orderfromname", "").strip()
            values["workbreak"] = person_extra.get("workbreak", "")
            values["breaktype"] = "amely része a munkaidőnek" if person_extra.get("breaktype") == "a munkaidő részét képezi" else "nem képezi a munkaidő részét"
            values["probation_end"] = _three_months(person.get("entry", ""))
            values["payment_words"] = number_hu(person.get("payment", ""))
            values["payment_formatted"] = format_payment(person.get("payment", ""))
            written_break = "hatvan perc" if person_extra.get("workbreak", "").strip() == "60 perc" else "harminc perc"
            values.update({
                "Munkavállaló neve": person.get("name", ""), "Munkavállaló neve:": person.get("name", ""),
                "Név:": person.get("name", ""), "**NÉV**": person.get("name", ""),
                "Adóazonosító jel": person.get("vat", ""), "Adóazonosító jel:": person.get("vat", ""),
                "Lakcím": person.get("address", ""), "Lakcím:": person.get("address", ""),
                "Munkakör": person.get("job", ""), "Munkakör:": person.get("job", ""),
                "Állandó lakcím": person.get("address", ""), "Állandó lakcím:": person.get("address", ""),
                "Születési név": person.get("birthname", ""), "Születési név:": person.get("birthname", ""),
                "Születési hely, időpont": values["birthplace+birthday"], "Születési hely, időpont:": values["birthplace+birthday"],
                "Anyja neve": person.get("momname", ""), "Anyja neve:": person.get("momname", ""),
                "Tartózkodási hely": person.get("stayaddress", ""), "Tartózkodási hely:": person.get("stayaddress", ""),
                "TAJ szám": person.get("taj", ""), "TAJ szám:": person.get("taj", ""),
                "Jogviszony kezdete": person.get("entry", ""), "Jogviszony kezdete:": person.get("entry", ""),
                "Munkakör megnevezése": person.get("job", ""),
                "Kitől kaphat még feladatokat, utasítást": values["orderfrom+orderfromname"],
                "Végzettség": person_extra.get("qualification", ""), "Egyéb követelmények": person_extra.get("requirements", ""),
                "E-mail címe* /E-mail address*:": person.get("email", ""),
                "Mobiltelefon száma* / Mobile phone number*:": person.get("phone", ""),
                "Születési helye (település) / Place of birth (city):": person.get("birthplace", ""),
                "Születési ideje (év, hónap, nap) / Date of birth (year, month, day):": person.get("birthday", ""),
                "Állandó lakhelye / Permanent address:": person.get("address", ""),
                "Kártyán szerepeltetni kívánt név / Name to be featured on the card:": person.get("name", ""),
            })
            replacements = {
                "DÁTUM": values["date"], "Dátum": values["date"], "dátum": values["date"],
                "BELÉPÉS DÁTUMA": person.get("entry", ""), "BELÉPÉS DÁTUM": person.get("entry", ""),
                "**BELÉPÉS** **DÁTUM**": person.get("entry", ""), "PRÓBAIDŐ VÉGE DÁTUM": values["probation_end"],
                "**MUNKAKÖR**": person.get("job", ""), "MUNKAKÖR": person.get("job", ""), "SZÁMMAL KIÍRVA": values["payment_words"],
                "6724 Szeged, Trafó köz 3.": person_extra.get("workplace", ""), "+3630": values["bossphone"],
                ".....@divian.hu": values["bossemail"], "30 perc": person_extra.get("workbreak", ""),
                "harminc perc": written_break, "amely része a munkaidőnek": values["breaktype"],
                "__PAYMENT_PLACEHOLDER__": f" {values['payment_formatted']},- Ft / hó",
                "---": person.get("jobdescription", ""),
                "NÉV": person.get("name", ""),
                "Adóazonosító jel: .": f"Adóazonosító jel: {person.get('vat', '')}",
                "__SZABADSAG_VAT__": f"Adóazonosító jel: {person.get('vat', '')}",
            }
            values.update(replacements)
            for template in template_dir.iterdir():
                if template.suffix.lower() not in {".docx", ".odt"}: continue
                data = _edit_template(template, values, replacements)
                safe_name = re.sub(r"[\\/:*?\"<>|]", "_", person.get("name", "ismeretlen"))
                archive.writestr(f"{safe_name}/{template.stem}_{safe_name}{template.suffix}", data)
                generated += 1
    if not generated: raise ValueError("Nem találhatók HR sablonok.")
    return output.getvalue(), "hr-dokumentumok.zip"
