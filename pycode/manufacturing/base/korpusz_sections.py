"""Shared Korpusz section builder for all Manufacturing views."""

from __future__ import annotations

from ..workflow import *

def _manufacturing_korpusz_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    """Build the combined Korpusz osszekeszito and alkatresz-kesz sections."""
    xml_sections, xml_count, xml_available = _manufacturing_osszekeszito_xml_sections(bundle, production_number)
    alkatresz_xml_sections, alkatresz_xml_count, alkatresz_xml_available = _manufacturing_alkatresz_kesz_xml_sections(bundle, production_number)
    if xml_available:
        osszekeszito_sections, osszekeszito_count = xml_sections, xml_count
    else:
        osszekeszito_sections, osszekeszito_count = _manufacturing_document_sections(
            bundle,
            production_number,
            ("osszekeszito",),
            include_source_prefix=False,
        )
    if alkatresz_xml_available:
        alkatresz_sections, alkatresz_count = alkatresz_xml_sections, alkatresz_xml_count
    else:
        alkatresz_sections, alkatresz_count = _manufacturing_document_sections(
            bundle,
            production_number,
            ("alkatresz_kesz",),
            include_source_prefix=False,
        )
    return osszekeszito_sections + alkatresz_sections, osszekeszito_count + alkatresz_count

def _manufacturing_osszekeszito_xml_sections(bundle: dict, production_number: str) -> tuple[list[dict], int, bool]:
    """Read Osszekeszito.xml into Korpusz manufacturing sections."""
    folder_text = str(bundle.get("folder", "") or "").strip()
    if not folder_text:
        return [], 0, False
    folder = Path(folder_text)
    xml_path = folder / "Osszekeszito.xml"
    if not xml_path.is_file():
        try:
            xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "osszekeszito.xml"), xml_path)
        except OSError:
            return [], 0, False
    if not xml_path.is_file():
        return [], 0, False

    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(xml_path).getroot()
    except Exception:
        return [], 0, True

    def clean_text(value: object) -> str:
        """Clean XML text and repair known mojibake variants."""
        return (
            str(value or "")
            .strip()
            .replace("Ăµ", "Ĺ‘")
            .replace("Ă•", "Ĺ")
            .replace("Ă»", "Ĺ±")
            .replace("Ă›", "Ĺ°")
        )

    def local_name(tag: object) -> str:
        """Return an XML tag name without namespace."""
        return str(tag or "").rsplit("}", 1)[-1].strip()

    def folded_ascii(value: object) -> str:
        """Return lowercase ASCII-folded text for XML matching."""
        text = unicodedata.normalize("NFKD", clean_text(value))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", text).strip().lower()

    def tag_key(tag: object) -> str:
        """Return a compact normalized XML field key."""
        return re.sub(r"[^a-z0-9]+", "", folded_ascii(local_name(tag)))

    def whole_number(value: object) -> str:
        """Parse a numeric XML value and return it as an integer string."""
        text = clean_text(value).replace(",", ".")
        if not text:
            return ""
        try:
            return str(int(Decimal(text).to_integral_value(rounding=ROUND_HALF_UP)))
        except (InvalidOperation, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if not match:
                return ""
            try:
                return str(int(Decimal(match.group(0)).to_integral_value(rounding=ROUND_HALF_UP)))
            except Exception:
                return ""

    def quantity_value(value: object) -> int:
        """Parse a positive XML quantity, defaulting to one."""
        number_text = whole_number(value)
        if not number_text:
            return 1
        try:
            return max(1, int(number_text))
        except ValueError:
            return 1

    def con_fields(con_element: object) -> dict[str, str]:
        """Collect direct child values from one CON XML element."""
        fields: dict[str, str] = {}
        for child in list(con_element):
            key = tag_key(getattr(child, "tag", ""))
            if key and key not in fields:
                fields[key] = clean_text(getattr(child, "text", ""))
        return fields

    def field_value(fields: dict[str, str], *names: str) -> str:
        """Return the first non-empty value for possible XML field names."""
        for name in names:
            value = fields.get(tag_key(name), "")
            if value:
                return value
        return ""

    def edge_value(value: object) -> str:
        """Normalize empty/K edge values to the UI dash marker."""
        text = clean_text(value)
        if re.sub(r"[^a-z0-9]+", "", folded_ascii(text)).upper() == "K":
            return "-"
        return text or "-"

    def section_label(fields: dict[str, str]) -> str:
        """Build the visible Korpusz section label from XML fields."""
        korp_tip = field_value(fields, "KorpTipPer")
        if not korp_tip:
            return "Összes"
        description = field_value(fields, "icg2Description")
        return " - ".join(part for part in (korp_tip, description) if part) or "Összes"

    def is_all_section_label(label: object) -> bool:
        """Return whether is all section label is true."""
        return folded_ascii(label) == "osszes"

    def pair_info_for_section_label(label: str) -> tuple[str, str] | None:
        """Return pair number and shared label for 1-es/2-es sections."""
        text = clean_text(label)
        if text.startswith("1-es "):
            return ("1", text[5:])
        if text.startswith("2-es "):
            return ("2", text[5:])
        return None

    def pair_sections_in_display_order(sections: list[dict]) -> list[dict]:
        """Keep 1-es/2-es paired sections adjacent in display order."""
        by_label = {clean_text(section.get("label")): section for section in sections}
        used: set[str] = set()
        ordered: list[dict] = []
        for section in sections:
            section_key = str(section.get("key", ""))
            if section_key in used:
                continue
            pair_info = pair_info_for_section_label(str(section.get("label", "")))
            if pair_info and pair_info[0] == "2":
                first_pair = by_label.get(f"1-es {pair_info[1]}")
                if first_pair and str(first_pair.get("key", "")) not in used:
                    continue
            used.add(section_key)
            ordered.append(section)
            if pair_info and pair_info[0] == "1":
                second_pair = by_label.get(f"2-es {pair_info[1]}")
                if second_pair and str(second_pair.get("key", "")) not in used:
                    used.add(str(second_pair.get("key", "")))
                    ordered.append(second_pair)
        for section in sections:
            section_key = str(section.get("key", ""))
            if section_key not in used:
                used.add(section_key)
                ordered.append(section)
        return ordered

    section_rows: dict[str, list[dict]] = {}
    row_index = 0
    for con_element in root.iter():
        if tag_key(getattr(con_element, "tag", "")) != "con":
            continue
        fields = con_fields(con_element)
        label = section_label(fields)
        name = field_value(fields, "Leiras", "Leírás") or "Tétel"
        length = whole_number(field_value(fields, "Hossz"))
        width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
        thickness = whole_number(field_value(fields, "Vastag"))
        size_parts_for_label = [part for part in (length, width, thickness) if part]
        size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
        color = field_value(fields, "Szin", "Szín")
        edge = edge_value(field_value(fields, "Elzartip", "Elzártip", "Élzártip"))
        quantity = quantity_value(field_value(fields, "conQuantity"))
        prd_id = field_value(fields, "prdID", "PrdID", "productionID")
        con_id = field_value(fields, "conID", "ConID", "Barcode")
        child_id = field_value(fields, "childID", "ChildID")
        barcode = field_value(fields, "Barcode") or con_id or f"OSSZXML-{row_index + 1:04d}"
        row_index += 1
        row_id = hashlib.sha1(
            f"osszekeszito-xml|{production_number}|{row_index}|{barcode}|{label}|{name}|{size_label}|{color}|{edge}|{quantity}".encode("utf-8")
        ).hexdigest()[:16]
        section_rows.setdefault(label, []).append(
            {
                "row_id": row_id,
                "state_key": _manufacturing_state_key(production_number, row_id),
                "production_number": _manufacturing_normalize_number(production_number),
                "name": name,
                "source_name": name,
                "detail": "",
                "size": size_label,
                "color": color,
                "edge": edge,
                "quantity": quantity,
                "code": barcode,
                "doc_key": "osszekeszito",
                "section_key": _manufacturing_local_slug(label),
                "section_label": label,
                "page_number": 1,
                **_manufacturing_xml_state_fields(production_number, xml_path.name, barcode, child_id, prd_id, con_id),
            }
        )

    sections = [
        {
            "key": f"osszekeszito::{_manufacturing_local_slug(label)}",
            "label": label,
            "rows": rows,
        }
        for label, rows in section_rows.items()
        if rows
    ]
    sections = pair_sections_in_display_order(
        sorted(
            sections,
            key=lambda section: (
                0 if is_all_section_label(section.get("label")) else 1,
                pair_info_for_section_label(str(section.get("label", ""))) or ("9", str(section.get("label", "")).lower()),
            ),
        )
    )
    return sections, sum(len(section.get("rows", [])) for section in sections), True

def _manufacturing_alkatresz_kesz_xml_sections(bundle: dict, production_number: str) -> tuple[list[dict], int, bool]:
    """Read Alkatresz_kesz.xml into Korpusz component-ready sections."""
    folder_text = str(bundle.get("folder", "") or "").strip()
    if not folder_text:
        return [], 0, False
    folder = Path(folder_text)
    xml_path = folder / "Alkatresz_kesz.xml"
    if not xml_path.is_file():
        try:
            xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "alkatresz_kesz.xml"), xml_path)
        except OSError:
            return [], 0, False
    if not xml_path.is_file():
        return [], 0, False

    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(xml_path).getroot()
    except Exception:
        return [], 0, True

    def clean_text(value: object) -> str:
        """Clean XML text and repair known mojibake variants."""
        return (
            str(value or "")
            .strip()
            .replace("Ăµ", "Ĺ‘")
            .replace("Ă•", "Ĺ")
            .replace("Ă»", "Ĺ±")
            .replace("Ă›", "Ĺ°")
        )

    def local_name(tag: object) -> str:
        """Return an XML tag name without namespace."""
        return str(tag or "").rsplit("}", 1)[-1].strip()

    def folded_ascii(value: object) -> str:
        """Return lowercase ASCII-folded text for XML matching."""
        text = unicodedata.normalize("NFKD", clean_text(value))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", text).strip().lower()

    def tag_key(tag: object) -> str:
        """Return a compact normalized XML field key."""
        return re.sub(r"[^a-z0-9]+", "", folded_ascii(local_name(tag)))

    def whole_number(value: object) -> str:
        """Parse a numeric XML value and return it as an integer string."""
        text = clean_text(value).replace(",", ".")
        if not text:
            return ""
        try:
            return str(int(Decimal(text).to_integral_value(rounding=ROUND_HALF_UP)))
        except (InvalidOperation, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if not match:
                return ""
            try:
                return str(int(Decimal(match.group(0)).to_integral_value(rounding=ROUND_HALF_UP)))
            except Exception:
                return ""

    def quantity_value(value: object) -> int:
        """Parse a positive XML quantity, defaulting to one."""
        number_text = whole_number(value)
        if not number_text:
            return 1
        try:
            return max(1, int(number_text))
        except ValueError:
            return 1

    def con_fields(con_element: object) -> dict[str, str]:
        """Collect direct child values from one CON XML element."""
        fields: dict[str, str] = {}
        for child in list(con_element):
            key = tag_key(getattr(child, "tag", ""))
            if key and key not in fields:
                fields[key] = clean_text(getattr(child, "text", ""))
        return fields

    def field_value(fields: dict[str, str], *names: str) -> str:
        """Return the first non-empty value for possible XML field names."""
        for name in names:
            value = fields.get(tag_key(name), "")
            if value:
                return value
        return ""

    section_rows: dict[str, list[dict]] = {}
    row_index = 0
    for con_element in root.iter():
        if tag_key(getattr(con_element, "tag", "")) != "con":
            continue
        fields = con_fields(con_element)
        name = field_value(fields, "Leiras", "Leírás") or "Tétel"
        length = whole_number(field_value(fields, "Hossz"))
        width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
        thickness = whole_number(field_value(fields, "Vastag"))
        size_parts_for_label = [part for part in (length, width, thickness) if part]
        size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
        color = field_value(fields, "Szin", "Szín")
        edge = field_value(fields, "Elzaras", "Elzárás") or "-"
        item_number = field_value(fields, "itmItemNumber")
        prd_id = field_value(fields, "prdID", "PrdID", "productionID")
        con_id = field_value(fields, "conID", "ConID", "Barcode")
        child_id = field_value(fields, "childID", "ChildID")
        barcode = field_value(fields, "Barcode") or con_id or f"ALKXML-{row_index + 1:04d}"
        quantity = quantity_value(field_value(fields, "conQuantity"))
        row_index += 1
        row_id = hashlib.sha1(
            f"alkatresz-xml|{production_number}|{row_index}|{barcode}|{name}|{size_label}|{color}|{edge}|{item_number}|{quantity}".encode("utf-8")
        ).hexdigest()[:16]
        section_rows.setdefault(name, []).append(
            {
                "row_id": row_id,
                "state_key": _manufacturing_state_key(production_number, row_id),
                "production_number": _manufacturing_normalize_number(production_number),
                "name": name,
                "source_name": name,
                "detail": item_number,
                "size": size_label,
                "color": color,
                "edge": edge,
                "quantity": quantity,
                "code": barcode,
                "doc_key": "alkatresz_kesz",
                "section_key": _manufacturing_local_slug(name),
                "section_label": name,
                "page_number": 1,
                **_manufacturing_xml_state_fields(production_number, xml_path.name, barcode, child_id, prd_id, con_id),
            }
        )

    sections = [
        {
            "key": f"alkatresz_kesz::{_manufacturing_local_slug(label)}",
            "label": label,
            "rows": rows,
        }
        for label, rows in section_rows.items()
        if rows
    ]
    sections.sort(key=lambda section: str(section.get("label", "")).lower())
    return sections, sum(len(section.get("rows", [])) for section in sections), True

