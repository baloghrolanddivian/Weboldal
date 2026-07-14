"""Template-based HR document generation, using only in-memory person data."""

from __future__ import annotations

import calendar
import copy
import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ODT_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
ODT_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODT_STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
ET.register_namespace("w", DOCX_NS)
ET.register_namespace("table", ODT_TABLE)
ET.register_namespace("text", ODT_TEXT)


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
    return str(value or "").strip()


def _three_months(value: str) -> str:
    for fmt in ("%Y.%m.%d.", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(value.strip(), fmt).date()
            month = d.month + 3
            year = d.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            return date(year, month, min(d.day, calendar.monthrange(year, month)[1])).strftime("%Y.%m.%d.")
        except ValueError:
            continue
    return value


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
    if integer < 1000: return _hundred(integer)
    thousands, rest = divmod(integer, 1000)
    thousand_word = "ezer" if thousands == 1 else (("két" if thousands == 2 else _hundred(thousands)) + "ezer")
    result = thousand_word
    return result if rest == 0 else result + _hundred(rest)


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
    _use_poppins(run, size_half_points=18)
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
    _use_poppins(run, size_half_points=18)
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
    root = ET.fromstring(entries[xml_name])
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
    _replace_all(root, replacements_to_apply, text_tags)
    _clean_colours(root, odt)
    entries[xml_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
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
            person_extra = dict(extra[index]) if isinstance(extra, list) else (dict(extra) if isinstance(extra, dict) else {})
            boss = person_extra.get("boss", "")
            boss_data = person_extra.get("boss_data", {}) if isinstance(person_extra.get("boss_data"), dict) else {}
            values = {**person, **person_extra, "date": _date(person_extra.get("date", "")), "bossphone": boss_data.get("phone", ""), "bossemail": boss_data.get("email", "")}
            values["birthplace+birthday"] = f"{person.get('birthplace', '')}, {person.get('birthday', '')}".strip(" ,")
            values["orderfrom+orderfromname"] = f"{person_extra.get('orderfrom', '')} {person_extra.get('orderfromname', '')}".strip()
            values["workbreak"] = person_extra.get("workbreak", "")
            values["breaktype"] = "amely része a munkaidőnek" if person_extra.get("breaktype") == "a munkaidő részét képezi" else "nem képezi a munkaidő részét"
            values["probation_end"] = _three_months(person.get("entry", ""))
            values["payment_words"] = number_hu(person.get("payment", ""))
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
                "__PAYMENT_PLACEHOLDER__": f" {person.get('payment', '')},- Ft / hó",
                "---": person.get("job", ""),
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
