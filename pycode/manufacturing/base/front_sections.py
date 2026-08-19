"""Shared Front section builder for all Manufacturing views."""

from __future__ import annotations

from ..workflow import *

def _manufacturing_front_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    """Build grouped Front osszekeszito sections for the manufacturing UI."""
    raw_sections, row_count = _manufacturing_document_sections(bundle, production_number, ("front_osszekeszito",))

    def folded(value: object) -> str:
        """Return lowercase accent-folded text for matching."""
        text = str(value or "").strip().lower()
        for source, target in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ö", "o"), ("ő", "o"), ("ú", "u"), ("ü", "u"), ("ű", "u"), ("õ", "o"), ("û", "u")):
            text = text.replace(source, target)
        return text

    def cabinet_level(value: object) -> str:
        """Classify a KorpTipPer value as lower or upper cabinet."""
        normalized = folded(value)
        if "also" in normalized:
            return "also"
        if "felso" in normalized:
            return "felso"
        return ""

    def cabinet_level_label(value: object) -> str:
        """Return the visible Hungarian label for a cabinet level key."""
        return {"also": "Alsó", "felso": "Felső"}.get(str(value or ""), "")

    def clean_text(value: object) -> str:
        """Clean text and repair known mojibake/OCR splits."""
        text = (
            str(value or "")
            .strip()
            .replace("õ", "ő")
            .replace("Õ", "Ő")
            .replace("û", "ű")
            .replace("Û", "Ű")
        )
        fixes = {
            "fehé r": "fehér",
            "fehé r fóliás": "fehér fóliás",
            "kas mír": "kasmír",
            "kas mír fóliás": "kasmír fóliás",
            "prov ance": "provance",
            "prov ance fóliás": "provance fóliás",
            "beig e": "beige",
            "beig e fóliás": "beige fóliás",
            "Sonom a": "Sonoma",
            "sonom a": "sonoma",
            "capucci no": "cappuccino",
            "SM.fehé r": "SM.fehér",
            "SM.kas mír": "SM.kasmír",
            "SM.pro vance": "SM.provance",
            "SM.beig e": "SM.beige",
            "Mf. fehé r": "Mf. fehér",
            "Mf. capucci no": "Mf. cappuccino",
        }
        for source, target in fixes.items():
            text = text.replace(source, target)
        return text

    def size_sort_key(size_label: str) -> tuple[int, ...]:
        """Return numeric size parts for stable front-size sorting."""
        parts = [
            int(part.strip())
            for part in re.split(r"[xX]", str(size_label or ""))
            if part.strip().isdigit()
        ]
        return tuple(parts or [9999, 9999, 9999])

    def front_group_size_label(row: dict, size_label: str, type_label: str) -> str:
        """Normalize AS cover front paired 81/165 dimensions for grouping."""
        source = " ".join(
            [
                str(row.get("section_label", "")).strip().lower(),
                str(row.get("name", "")).strip().lower(),
                str(type_label or "").strip().lower(),
            ]
        )
        if "as takar" not in source and not bool(row.get("frontPair8165Group")):
            return str(size_label or "").strip()

        parts = [part.strip() for part in re.split(r"[xX]", str(size_label or "")) if part.strip()]
        if len(parts) < 3:
            return str(size_label or "").strip()

        pair_values = {"81", "165"}
        if parts[0] in pair_values and parts[1] not in pair_values:
            parts[0] = "81/165"
        elif parts[1] in pair_values and parts[0] not in pair_values:
            parts[1] = "81/165"

        return " x ".join(parts)

    def front_material_label(row: dict) -> str:
        """Return the visible front material family label."""
        explicit_material = clean_text(row.get("frontMaterial"))
        if explicit_material:
            return explicit_material
        source = clean_text(f"{row.get('color', '')} {row.get('name', '')} {row.get('detail', '')}").lower()
        if "mf." in source or "sm." in source or "matt" in source:
            return "Fóliás"
        return "Bútorlapos"

    def display_row_name(row: dict) -> str:
        """Return a row name with duplicate trailing color text removed."""
        name = clean_text(row.get("name"))
        color = clean_text(row.get("color"))
        if not name:
            return "Front"
        if not color:
            return name
        name_parts = [part for part in name.split() if part]
        color_parts = [part for part in color.split() if part]
        if len(name_parts) > len(color_parts):
            if [folded(part) for part in name_parts[-len(color_parts):]] == [folded(part) for part in color_parts]:
                trimmed = " ".join(name_parts[:-len(color_parts)]).strip()
                if trimmed:
                    return trimmed
        return name

    def front_type_label(row: dict) -> str:
        """Derive the front category/type from the source section label."""
        section_label = clean_text(row.get("section_label"))
        parts = [clean_text(part) for part in section_label.split(" - ") if clean_text(part)]
        if parts and folded(parts[0]).startswith("front "):
            parts = parts[1:]
        if parts and re.fullmatch(r"[12]-es", folded(parts[0])):
            parts = parts[1:]
        color = clean_text(row.get("color"))
        if parts and color and folded(parts[-1]) == folded(color):
            parts = parts[:-1]
        return " - ".join(parts) if parts else display_row_name(row)

    def front_box_type_label(type_label: str) -> str:
        """Normalize front type text for box/group display."""
        clean_type = clean_text(type_label)
        if "alsó kihúzható" in folded(clean_type):
            return "Fiókelő"
        for suffix in (" - Oldalra", " - Nincs"):
            if clean_type.endswith(suffix):
                return clean_type[: -len(suffix)].strip()
        return clean_type

    def front_model_label(row: dict) -> str:
        """Extract the model prefix from the row detail text."""
        detail_text = clean_text(row.get("detail"))
        if "·" in detail_text:
            return clean_text(detail_text.split("·", 1)[0])
        if "-" in detail_text:
            return clean_text(detail_text.split("-", 1)[0])
        return ""

    def is_glass_row(row: dict, type_label: str) -> bool:
        """Return whether is glass row is true."""
        combined = " ".join(
            [
                clean_text(row.get("name")),
                clean_text(row.get("detail")),
                clean_text(row.get("section_label")),
                clean_text(type_label),
            ]
        )
        return "uveges" in folded(combined) or "uveg" in folded(combined)

    def normalized_front_column_text(value: object) -> str:
        """Normalize front text for pullout/glass/trait matching."""
        text = folded(clean_text(value))
        text = re.sub(r"\bkihuzhat\s+o\b", "kihuzhato", text)
        return re.sub(r"\s+", " ", text).strip()

    def is_pullout_front_row(row: dict) -> bool:
        """Return whether is pullout front row is true."""
        detail_text = clean_text(row.get("detail"))
        if "·" in detail_text:
            detail_text = clean_text(detail_text.split("·", 1)[1])
        return bool(re.search(r"\balso\s+kihuzhato\b", normalized_front_column_text(detail_text)))

    def front_trait_label(row: dict, type_label: str) -> str:
        """Return special front traits such as Blende or curved marker."""
        combined = " ".join(
            [
                clean_text(row.get("name")),
                clean_text(row.get("detail")),
                clean_text(row.get("section_label")),
                clean_text(type_label),
            ]
        )
        if "blende" in folded(combined):
            return "Blende"

        size_text = clean_text(row.get("size"))
        code_text = clean_text(row.get("code"))
        compact_size = re.sub(r"[^0-9X]", "", size_text.upper().replace("x", "X"))
        compact_code = re.sub(r"\s+", "", code_text).upper()
        if compact_size and re.search(re.escape(compact_size) + r"[JB]", compact_code):
            return "Íves"
        return "-"

    def is_curved_front_row(row: dict) -> bool:
        """Return whether is curved front row is true."""
        if folded(row.get("doorType")) == "fzn":
            return True
        size_text = clean_text(row.get("size"))
        code_text = clean_text(row.get("code"))
        compact_size = re.sub(r"[^0-9X]", "", size_text.upper().replace("x", "X"))
        compact_code = re.sub(r"\s+", "", code_text).upper()
        if compact_size == "655X397X18":
            return True
        if compact_size == "718X297X18":
            combined = " ".join(
                [
                    clean_text(row.get("name")),
                    clean_text(row.get("detail")),
                    clean_text(row.get("section_label")),
                    clean_text(row.get("code")),
                ]
            ).upper()
            return "FZN" in combined
        return bool(compact_size and re.search(re.escape(compact_size) + r"[JB]", compact_code))

    def front_xml_source_sections() -> tuple[list[dict], int, bool]:
        """Read Front_osszekeszito.xml into section rows when available."""
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return [], row_count, False
        folder = Path(folder_text)
        xml_path = folder / "Front_osszekeszito.xml"
        if not xml_path.is_file():
            try:
                xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "front_osszekeszito.xml"), xml_path)
            except OSError:
                return [], row_count, False
        if not xml_path.is_file():
            return [], row_count, False

        try:
            import xml.etree.ElementTree as ET

            root = ET.parse(xml_path).getroot()
        except Exception:
            return [], 0, True

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

        def category_label(fields: dict[str, str], name: str, model: str, color: str) -> str:
            """Derive the visible front category label from XML fields."""
            front_group = re.sub(r"[^a-z0-9]+", "", folded_ascii(field_value(fields, "FRONT_CSOP"))).upper()
            opening = field_value(fields, "Nyitas", "Nyitás")
            opening_is_empty = re.sub(r"[^a-z0-9]+", "", folded_ascii(opening)) in {"", "nincs"}
            if front_group == "AJ":
                return "Ajtó" if opening_is_empty else f"Ajtó - {opening}"
            if front_group == "FE":
                return "Fiókelő"
            if front_group == "FN":
                return "Fúrás nélkül"
            if front_group == "HT":
                label_parts = [name or "Front"]
                label_folded = folded_ascii(label_parts[0])
                for value in (model, color):
                    value_text = clean_text(value)
                    if value_text and folded_ascii(value_text) not in label_folded:
                        label_parts.append(value_text)
                        label_folded = folded_ascii(" ".join(label_parts))
                return " ".join(label_parts)
            return name or "Front"

        def material_label(color: object) -> str:
            """Infer material family from the XML color text."""
            normalized = folded_ascii(color)
            if re.search(r"\bmf\b", normalized) or "folias" in normalized:
                return "Fóliás"
            return "Bútorlapos"

        def is_pullout_door_type(value: object) -> bool:
            """Return whether is pullout door type is true."""
            return folded_ascii(value) == "also kihuzhato"

        rows: list[dict] = []
        row_index = 0
        for con_element in root.iter():
            if tag_key(getattr(con_element, "tag", "")) != "con":
                continue
            fields = con_fields(con_element)
            name = field_value(fields, "Leiras", "Leírás") or "Front"
            model = field_value(fields, "Modell")
            color = field_value(fields, "Szin", "Szín")
            length = whole_number(field_value(fields, "Hossz", "Hoszz"))
            width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
            thickness = whole_number(field_value(fields, "Vastag"))
            size_parts_for_label = [part for part in (length, width, thickness) if part]
            size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
            quantity = quantity_value(field_value(fields, "conQuantity"))
            prd_id = field_value(fields, "prdID", "PrdID", "productionID")
            con_id = field_value(fields, "conID", "ConID", "Barcode")
            child_id = field_value(fields, "childID", "ChildID")
            barcode = field_value(fields, "Barcode") or con_id or f"FRONTXML-{row_index + 1:04d}"
            type_label = category_label(fields, name, model, color)
            door_type = field_value(fields, "AJTO_TIP", "Ajto Tip", "Ajtó Tip")
            korp_tip_per = field_value(fields, "KorpTipPer")
            level = cabinet_level(korp_tip_per)
            row_index += 1
            row_id = hashlib.sha1(
                f"front-xml|{production_number}|{row_index}|{barcode}|{name}|{model}|{color}|{size_label}|{type_label}|{quantity}".encode("utf-8")
            ).hexdigest()[:16]
            section_key = _manufacturing_local_slug(type_label)
            rows.append(
                {
                    "row_id": row_id,
                    "state_key": _manufacturing_state_key(production_number, row_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": name,
                    "source_name": name,
                    "detail": model,
                    "size": size_label,
                    "color": color,
                    "edge": "-",
                    "quantity": quantity,
                    "code": barcode,
                    "doc_key": "front_osszekeszito",
                    "section_key": section_key,
                    "section_label": type_label,
                    "page_number": 1,
                    "frontMaterial": material_label(color),
                    "frontPair8165Group": True,
                    "frontModel": model,
                    "doorType": door_type,
                    "frontPullOut": is_pullout_door_type(door_type),
                    "korpTipPer": korp_tip_per,
                    "cabinetLevel": level,
                    **_manufacturing_xml_state_fields(production_number, xml_path.name, barcode, child_id, prd_id, con_id),
                }
            )

        if not rows:
            return [], 0, True
        return [
            {
                "key": "front_osszekeszito::xml",
                "label": "Front összekészítés",
                "rows": rows,
            }
        ], len(rows), True

    xml_front_sections, xml_front_row_count, xml_front_available = front_xml_source_sections()
    if xml_front_available:
        raw_sections = xml_front_sections
        row_count = xml_front_row_count

    grouped_sections: dict[str, dict] = {}
    for section in raw_sections:
        for raw_row in section.get("rows", []):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            size = clean_text(row.get("size")) or "Méret nélkül"
            material = front_material_label(row)
            type_label = front_type_label(row)
            box_type_label = front_box_type_label(type_label)
            level = clean_text(row.get("cabinetLevel")) or cabinet_level(row.get("korpTipPer"))
            level_label = cabinet_level_label(level)
            group_size = front_group_size_label(row, size, box_type_label) or size
            section_key = f"{level or 'other'}::{group_size}::{material}::{box_type_label}"
            section_slug = _manufacturing_local_slug(section_key)
            visible_label = f"{group_size} · {material} · {box_type_label}"
            if level_label:
                visible_label = f"{visible_label} · {level_label}"
            if section_slug not in grouped_sections:
                grouped_sections[section_slug] = {
                    "key": f"front_osszekeszito::{section_slug}",
                    "label": visible_label,
                    "rows": [],
                    "frontMaterial": material,
                    "cabinetLevel": level,
                }
            grouped_sections[section_slug]["label"] = visible_label
            row["name"] = clean_text(raw_row.get("name")) or display_row_name(row)
            row["detail"] = type_label
            row["modelLabel"] = clean_text(raw_row.get("frontModel")) or front_model_label(raw_row)
            row["frontTrait"] = front_trait_label(raw_row, type_label)
            row["isCurved"] = is_curved_front_row(raw_row)
            row["hideSubtitle"] = True
            row["isGlass"] = is_glass_row(row, type_label)
            row["isPullOut"] = bool(raw_row.get("frontPullOut")) if "frontPullOut" in raw_row else is_pullout_front_row(raw_row)
            row["columnLayout"] = "front-standard"
            grouped_sections[section_slug]["rows"].append(row)

    material_order = {"Fóliás": 0, "Bútorlapos": 1}
    sorted_sections = list(grouped_sections.values())
    for section in sorted_sections:
        rows = [row for row in section.get("rows", []) if isinstance(row, dict)]
        rows.sort(
            key=lambda row: (
                str(row.get("color", "")).lower(),
                str(row.get("frontTrait", "")).lower(),
                str(row.get("modelLabel", "")).lower(),
                str(row.get("name", "")).lower(),
                size_sort_key(str(row.get("size", "")).strip()),
                str(row.get("detail", "")).lower(),
                str(row.get("code", "")).lower(),
            )
        )
        section["rows"] = rows

    sorted_sections.sort(
        key=lambda section: (
            {"also": 0, "felso": 1}.get(str(section.get("cabinetLevel", "")), 2),
            size_sort_key(str(section.get("label", "")).split("·", 1)[0].strip()),
            material_order.get(str(section.get("label", "")).split("·", 2)[1].strip(), 9)
            if "·" in str(section.get("label", ""))
            else 9,
            str(section.get("label", "")).split("·", 2)[2].strip().lower()
            if str(section.get("label", "")).count("·") >= 2
            else "",
            str(section.get("label", "")),
        )
    )
    return sorted_sections, row_count

