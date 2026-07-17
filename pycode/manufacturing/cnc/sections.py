"""Operation-specific section builders for cnc manufacturing papers."""

from __future__ import annotations

from ..workflow import *

def _manufacturing_cnc_sections(bundle: dict, production_number: str) -> tuple[list[dict], int, list[dict], str, str]:
    """Build CNC/Fiókelő documents, special views, and source labels."""
    raw_sections, _ = _manufacturing_document_sections(bundle, production_number, ("cnc", "fiokelo_furas"))
    using_xml_cnc_source = False
    using_xml_fiokelo_source = False

    def folded(value: object) -> str:
        """Return lowercase accent-folded text for matching."""
        text = str(value or "").strip().lower()
        for source, target in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ö", "o"), ("ő", "o"), ("ú", "u"), ("ü", "u"), ("ű", "u"), ("õ", "o"), ("û", "u")):
            text = text.replace(source, target)
        return text

    def clean_text(value: object) -> str:
        """Clean text and repair known mojibake variants."""
        return (
            str(value or "")
            .strip()
            .replace("õ", "ő")
            .replace("Õ", "Ő")
            .replace("û", "ű")
            .replace("Û", "Ű")
        )

    def cnc_xml_source_sections() -> tuple[list[dict], bool]:
        """Read CNC.xml rows into lower/upper CNC source sections."""
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return [], False
        folder = Path(folder_text)
        xml_path = folder / "CNC.xml"
        if not xml_path.is_file():
            try:
                xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "cnc.xml"), xml_path)
            except OSError:
                return [], False
        if not xml_path.is_file():
            return [], False

        try:
            import xml.etree.ElementTree as ET

            root = ET.parse(xml_path).getroot()
        except Exception:
            return [], True

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
            """Parse an XML quantity, defaulting to one."""
            number_text = whole_number(value)
            if not number_text:
                return 1
            try:
                return int(number_text)
            except ValueError:
                return 1

        def drawer_drill_value(value: object) -> str:
            """Map compact drawer-drilling XML codes to display labels."""
            code = re.sub(r"[^a-z0-9]+", "", folded_ascii(value)).upper()
            if code == "N":
                return "Nincs"
            if code == "T":
                return "Teleszkóp"
            if code == "BH":
                return "Box Hettich"
            return ""

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
            section_label = field_value(fields, "KorpTipPer")
            section_folded = folded_ascii(section_label)
            is_lower_xml_section = "als" in section_folded
            is_upper_xml_section = "fels" in section_folded
            if not is_lower_xml_section and not is_upper_xml_section:
                continue

            length = whole_number(field_value(fields, "Hossz"))
            width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
            thickness = whole_number(field_value(fields, "Vastag"))
            size_parts_for_label = [part for part in (length, width, thickness) if part]
            size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
            mark_size_black = is_upper_xml_section and length == "720" and width == "290"
            name = field_value(fields, "Leiras", "Leírás") or "Tétel"
            color = field_value(fields, "Szin", "Szín")
            edge = field_value(fields, "Elzaras", "Élzárás") or "-"
            side_type = field_value(fields, "Oldal_Tip", "Oldal Tip")
            hardware_type = field_value(fields, "VASALAT_TIP", "Vasalat Tip")
            cnc_tag_value = field_value(fields, "CNC")
            cnc_detail = "" if re.sub(r"[^a-z0-9]+", "", folded_ascii(cnc_tag_value)).upper() == "N" else cnc_tag_value
            drawer_drill = drawer_drill_value(field_value(fields, "FIOKSIN_FURAS", "Fióksín Fúrás"))
            quantity = quantity_value(field_value(fields, "conQuantity"))
            prd_id = field_value(fields, "prdID", "PrdID", "productionID")
            con_id = field_value(fields, "conID", "ConID", "Barcode")
            child_id = field_value(fields, "childID", "ChildID")
            barcode = field_value(fields, "Barcode") or con_id or f"CNCXML-{row_index + 1:04d}"
            detail = clean_text(" ".join(part for part in (drawer_drill if is_lower_xml_section else "", side_type, edge, cnc_detail, hardware_type) if part and part != "-"))
            row_index += 1
            row_id = hashlib.sha1(
                f"cnc-xml|{production_number}|{row_index}|{section_label}|{name}|{size_label}|{color}|{edge}|{side_type}|{drawer_drill}|{quantity}".encode("utf-8")
            ).hexdigest()[:16]
            section_rows.setdefault(section_label, []).append(
                {
                    "row_id": row_id,
                    "state_key": _manufacturing_state_key(production_number, row_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": name,
                    "source_name": name,
                    "size": size_label,
                    "color": color,
                    "drawer_drill": drawer_drill,
                    "side_type": side_type,
                    "hardware_type": hardware_type,
                    "edge": edge,
                    "quantity": quantity,
                    "detail": detail,
                    "code": barcode,
                    "doc_key": "cnc",
                    "section_key": _manufacturing_local_slug(section_label),
                    "section_label": section_label,
                    "page_number": 1,
                    "markSizeBlack": mark_size_black,
                    **_manufacturing_xml_state_fields(production_number, xml_path.name, barcode, child_id, prd_id, con_id),
                }
            )

        sections: list[dict] = []
        for section_label, rows in section_rows.items():
            if not rows:
                continue
            sections.append(
                {
                    "key": f"cnc::{_manufacturing_local_slug(section_label)}",
                    "label": section_label,
                    "rows": rows,
                }
            )
        return sections, True

    def fiokelo_xml_source_sections() -> tuple[list[dict], bool]:
        """Read Fiokelo_furas.xml rows into Fiókelő source sections."""
        folder_text = str(bundle.get("folder", "") or "").strip()
        if not folder_text:
            return [], False
        folder = Path(folder_text)
        xml_path = folder / "Fiokelo_furas.xml"
        if not xml_path.is_file():
            try:
                xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "fiokelo_furas.xml"), xml_path)
            except OSError:
                return [], False
        if not xml_path.is_file():
            return [], False

        try:
            import xml.etree.ElementTree as ET

            root = ET.parse(xml_path).getroot()
        except Exception:
            return [], True

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
            section_label = field_value(fields, "KorpTipPer") or "Fiókelő fúrás"
            name = field_value(fields, "Leiras", "Leírás") or "Fiókelő"
            model = field_value(fields, "Modell") or "Ismeretlen modell"
            length = whole_number(field_value(fields, "Hossz"))
            width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
            thickness = whole_number(field_value(fields, "Vastag"))
            size_parts_for_label = [part for part in (length, width, thickness) if part]
            size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 3 else ""
            color = field_value(fields, "Szin", "Szín")
            drill = field_value(fields, "Fog_furattal", "Fog furattal")
            handle_type = field_value(fields, "Fog_tip", "Fog tip")
            drawer_type = field_value(fields, "Fioktipus", "Fióktípus")
            netfront_color = field_value(fields, "Nettfront_szin", "Nettfront szín")
            if folded(netfront_color) == "nincs":
                netfront_color = ""
            detail_prefix = " ".join(part for part in (model, netfront_color) if part).strip()
            detail_suffix = " ".join(part for part in (drill, drawer_type) if part).strip()
            detail = " - ".join(part for part in (detail_prefix, detail_suffix) if part)
            quantity = quantity_value(field_value(fields, "conQuantity"))
            prd_id = field_value(fields, "prdID", "PrdID", "productionID")
            con_id = field_value(fields, "conID", "ConID", "Barcode")
            child_id = field_value(fields, "childID", "ChildID")
            barcode = field_value(fields, "Barcode") or con_id or f"FIOKXML-{row_index + 1:04d}"
            row_index += 1
            row_id = hashlib.sha1(
                f"fiokelo-xml|{production_number}|{row_index}|{barcode}|{section_label}|{name}|{model}|{size_label}|{color}|{handle_type}|{drill}|{drawer_type}|{netfront_color}|{quantity}".encode("utf-8")
            ).hexdigest()[:16]
            section_rows.setdefault(section_label, []).append(
                {
                    "row_id": row_id,
                    "state_key": _manufacturing_state_key(production_number, row_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": name,
                    "source_name": name,
                    "size": size_label,
                    "color": color,
                    "edge": "-",
                    "quantity": quantity,
                    "detail": detail,
                    "code": barcode,
                    "doc_key": "fiokelo_furas",
                    "section_key": _manufacturing_local_slug(section_label),
                    "section_label": section_label,
                    "page_number": 1,
                    **_manufacturing_xml_state_fields(production_number, xml_path.name, barcode, child_id, prd_id, con_id),
                }
            )

        sections = [
            {
                "key": f"fiokelo_furas::{_manufacturing_local_slug(section_label)}",
                "label": section_label,
                "rows": rows,
            }
            for section_label, rows in section_rows.items()
            if rows
        ]
        return sections, True

    xml_cnc_sections, xml_cnc_available = cnc_xml_source_sections()
    if xml_cnc_available:
        raw_sections = [
            section
            for section in raw_sections
            if not str(section.get("key", "")).startswith("cnc::")
        ] + xml_cnc_sections
        using_xml_cnc_source = True

    xml_fiokelo_sections, xml_fiokelo_available = fiokelo_xml_source_sections()
    if xml_fiokelo_available:
        raw_sections = [
            section
            for section in raw_sections
            if not str(section.get("key", "")).startswith("fiokelo_furas::")
        ] + xml_fiokelo_sections
        using_xml_fiokelo_source = True
    cnc_source_type = "XML" if using_xml_cnc_source or using_xml_fiokelo_source else "Nincs XML"
    cnc_source_label = "Beolvasva: {0}, {1}".format(
        "XML" if using_xml_cnc_source else "Nincs XML",
        "XML" if using_xml_fiokelo_source else "Nincs XML",
    )

    def size_parts(size_label: object) -> tuple[int, ...]:
        """Return numeric size components for sorting/grouping."""
        parts = [int(part.strip()) for part in re.split(r"[xX]", str(size_label or "")) if part.strip().isdigit()]
        return tuple(parts or [9999, 9999, 9999])

    def canonical_side_type(value: object) -> str:
        """Normalize lower-cabinet side type text to canonical labels."""
        text = clean_text(value)
        folded_text = re.sub(r"\s+", " ", folded(text)).strip()
        if not folded_text:
            return ""
        if "ar golyos" in folded_text:
            return "AR golyós tel."
        if "aaf fiokos ajtos" in folded_text:
            return "AAF fiókos ajtós"
        if "af 1+2" in folded_text or "af 1 + 2" in folded_text:
            return "AF 1+2 fiókos"
        if "pultos" in folded_text:
            return "Pultos nor. al."
        if "as vt" in folded_text:
            return "AS VT"
        if "as magic" in folded_text:
            return "AS MAGIC"
        if re.search(r"\batf\b", folded_text):
            return "ATF"
        if "aszb" in folded_text and "szemetes" in folded_text:
            return "ASZB kihúzható szemetes"
        if "aszhs" in folded_text:
            return "ASZHS"
        if "aszb" in folded_text:
            return "ASZB kihúzható szemetes"
        if re.search(r"\bakl\b", folded_text):
            return "AKL"
        if "jolly" in folded_text:
            return "Jolly"
        if re.search(r"\bkira\b", folded_text):
            return "Kira"
        if re.search(r"\bar\b", folded_text):
            return "AR"
        if "nyitott" in folded_text:
            return "Nyitott"
        if "normal" in folded_text:
            return "Normáls alsó"
        return text

    def normalize_side_type(value: object) -> str:
        """Normalize side-type text used by CNC grouping rules."""
        return re.sub(r"\s+", " ", folded(canonical_side_type(value))).strip()

    def cnc_display_name(name: object) -> str:
        """Normalize CNC row names for consistent grouping and display."""
        text = clean_text(name)
        folded_text = folded(text)
        if "hatlap also" in folded_text or "tlap als" in folded_text:
            return "Hátlap alsó"
        vegzaro_folded_match = re.search(r"vegzaro\s+also\s+oldal(?:\s+([bj]))?", folded_text)
        if vegzaro_folded_match:
            suffix = str(vegzaro_folded_match.group(1) or "").upper()
            return clean_text(f"Végzáró alsó oldal {suffix}")
        hatlap_match = re.search(r"h[aá]tlap\s+als[oó]", text, flags=re.IGNORECASE)
        if hatlap_match and hatlap_match.start() > 0:
            return clean_text(text[hatlap_match.start():])
        vegzaro_match = re.search(r"v[eé]gz[aá]r[oó]\s+als[oó]\s+oldal(?:\s+[BJ])?", text, flags=re.IGNORECASE)
        if vegzaro_match and vegzaro_match.start() > 0:
            return clean_text(text[vegzaro_match.start():])
        if folded_text == "also oldal":
            return "Alsó oldal"
        if folded_text == "felso oldal":
            return "Felső oldal"
        if folded_text == "also fenek":
            return "Alsó fenék"
        if "fiokelo" in folded_text:
            return "Fiókelő"
        if "blende" in folded_text:
            return "Blende"
        return text or "Tétel"

    def parse_lower_detail(detail: object) -> tuple[str, str, str, str]:
        """Parse lower cabinet detail text into detail, color, and side hints."""
        text = clean_text(detail)
        if not text:
            return "", "", "", ""
        drawer_drill = ""
        remainder = text
        if text.startswith("Nincs "):
            drawer_drill = "Nincs"
            remainder = clean_text(text[6:].strip())
        if text.startswith("Teleszkóp "):
            drawer_drill = "Teleszkópos"
            remainder = clean_text(text[len("Teleszkóp "):].strip())
        if text.startswith("Teleszkópos "):
            drawer_drill = "Teleszkópos"
            remainder = clean_text(text[len("Teleszkópos "):].strip())
        if text.startswith("AVZ "):
            tokens = [clean_text(token) for token in text.split() if clean_text(token)]
            avz_suffix = tokens[1] if len(tokens) > 1 and tokens[1] in {"B", "J", "N"} else ""
            side_type = clean_text(" ".join(["AVZ", avz_suffix]))
            tail_tokens = tokens[2:] if avz_suffix else tokens[1:]
            edge_pattern = re.compile(r"^\d+H(?:\dR)?$")
            parsed_edge = ""
            hardware_type = ""
            if tail_tokens and edge_pattern.fullmatch(tail_tokens[0]):
                parsed_edge = tail_tokens[0]
                tail_tokens = tail_tokens[1:]
            if tail_tokens:
                hardware_type = clean_text(" ".join(tail_tokens))
            return "", side_type, parsed_edge, hardware_type
        if text.startswith("Box Hettich "):
            drawer_drill = "Box Hettich"
            remainder = clean_text(text[len("Box Hettich "):].strip())
        known_side_types = {
            "Normál alsó",
            "Normáls alsó",
            "AS MAGIC",
            "AKL",
            "AR",
            "Jolly",
            "Kira",
            "Nyitott",
            "ATF",
            "ASZHS/ASZB",
            "ASZHS",
            "ASZB kihúzható szemetes",
            "AS VT",
            "AAF fiókos ajtós",
            "AF 1+2 fiókos",
        }
        if remainder in known_side_types:
            return drawer_drill, canonical_side_type(remainder), "", ""
        tokens = [clean_text(token) for token in remainder.split() if clean_text(token)]
        hardware_type = ""
        parsed_edge = ""
        edge_pattern = re.compile(r"^\d+H(?:\dR)?$")
        # Some rows (especially Box Hettich) contain "SIDE EDGE EXTRA..." format,
        # e.g. "KF60F 1H 176FI N". Keep side type isolated in its own column.
        edge_index = next((idx for idx, token in enumerate(tokens) if edge_pattern.fullmatch(token)), -1)
        if edge_index > 0:
            parsed_edge = tokens[edge_index]
            remainder = clean_text(" ".join(tokens[:edge_index]))
            trailing_tokens = tokens[edge_index + 1 :]
            if trailing_tokens:
                hardware_type = clean_text(" ".join(trailing_tokens))
            return drawer_drill, canonical_side_type(remainder), parsed_edge, hardware_type
        if drawer_drill == "AVZ" and len(tokens) == 1 and tokens[0] in {"N", "KESB", "GTEL", "B", "J"}:
            return drawer_drill, "", "", tokens[0]
        if len(tokens) >= 2 and edge_pattern.fullmatch(tokens[-2]) and tokens[-1] in {"N", "KESB", "GTEL", "B", "TE", "RI", "JO"}:
            parsed_edge = tokens[-2]
            hardware_type = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-2]))
        elif len(tokens) >= 1 and edge_pattern.fullmatch(tokens[-1]):
            parsed_edge = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-1]))
        elif len(tokens) >= 1 and tokens[-1] in {"N", "KESB", "GTEL", "B", "TE", "RI", "JO"} and drawer_drill:
            hardware_type = tokens[-1]
            remainder = clean_text(" ".join(tokens[:-1]))
        return drawer_drill, canonical_side_type(remainder), parsed_edge, hardware_type

    def split_lower_color_and_side_v2(color: object, side_type: object) -> tuple[str, str]:
        """Split lower-row color text from side and hardware hints."""
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        if not color_text:
            return color_text, side_text

        # Keep already parsed side types intact.
        if side_text and side_text not in {"-", ""}:
            return color_text, canonical_side_type(side_text)

        # Some legacy rows append side-type code to color, e.g. "Antracit kr. K60R".
        # Move trailing code-like token into the side-type column.
        match = re.match(r"^(.*\S)\s+(K\d{1,2}[A-Z0-9]{0,6})$", color_text, flags=re.IGNORECASE)
        if match:
            parsed_color = clean_text(match.group(1))
            parsed_side = clean_text(match.group(2)).upper()
            if parsed_color:
                return parsed_color, parsed_side

        return color_text, side_text

    def parse_upper_detail(detail: object) -> tuple[str, str]:
        """Parse upper cabinet detail text into display and side hints."""
        text = clean_text(detail)
        if not text:
            return "", ""
        for marker in ("Felső oldal", "Felső végzáró", "Tető-fenék mart", "EFT fenék excenteres"):
            marker_index = text.find(marker)
            if marker_index > 0:
                text = clean_text(text[:marker_index])
                break
        text = re.sub(r"\b\d+H(?:\dR)?\s+\d+\b", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text).strip()
        if not text:
            return "", ""
        hardware_codes = {"N", "KESB", "GTEL", "TE", "RI", "JO"}
        if text in hardware_codes:
            return "", text
        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in hardware_codes:
            return clean_text(parts[0]), parts[1]
        return text, ""

    def split_upper_color_and_side(color: object, side_type: object) -> tuple[str, str]:
        """Split upper-row color text from side type hints."""
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        patterns = [
            (r"\s+Sarok\s+fels[őo]$", "Sarok felső"),
            (r"\s+Fels[őo]\s+felny[ií]l[oó]s$", "Felnyíló"),
            (r"\s+F_?2A$", "F2A"),
            (r"\s+EF60_?72$", "EF60_72"),
            (r"\s+EF60$", "EF60"),
            (r"\s+FNY$", "FNY"),
            (r"\s+EFT$", "EFT"),
            (r"\s+FVZ$", "FVZ"),
            (r"\s+FMFS$", "FMFS"),
            (r"\s+FMF$", "FMF"),
            (r"\s+FKF\s+Tiplis$", "FKF Tiplis"),
            (r"\s+FKF$", "FKF"),
            (r"\s+FZN$", "FZN"),
            (r"\s+FÜF$", "FÜF"),
            (r"\s+FUF$", "FÜF"),
            (r"\s+Fels[őo]$", "Normál"),
        ]
        detected_side = side_text
        stripped_color = color_text
        changed = True
        while changed and stripped_color:
            changed = False
            for pattern, candidate_side in patterns:
                if re.search(pattern, stripped_color, flags=re.IGNORECASE):
                    stripped_color = re.sub(pattern, "", stripped_color, flags=re.IGNORECASE).strip(" -")
                    if not detected_side:
                        detected_side = candidate_side
                    changed = True
                    break
        return stripped_color or color_text, detected_side

    def parse_upper_detail_v2(detail: object) -> tuple[str, str]:
        """Parse upper cabinet detail text with extended side rules."""
        text = clean_text(detail)
        if not text:
            return "", ""
        folded_text = folded(text)
        marker_positions = []
        for marker in ("felso oldal", "felso vegzaro", "teto-fenek mart", "eft fenek excenteres"):
            marker_index = folded_text.find(marker)
            if marker_index > 0:
                marker_positions.append(marker_index)
        if marker_positions:
            text = clean_text(text[:min(marker_positions)])
        text = re.sub(r"\b\d+H(?:\dR)?\s+\d+\b", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text).strip()
        if not text:
            return "", ""
        hardware_codes = {"N", "KESB", "GTEL", "TE", "RI", "JO"}
        if text in hardware_codes:
            return "", text
        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] in hardware_codes:
            return clean_text(parts[0]), parts[1]
        return text, ""

    def split_upper_color_and_side_v2(color: object, side_type: object) -> tuple[str, str]:
        """Split upper-row color text using extended side type rules."""
        color_text = clean_text(color)
        side_text = clean_text(side_type)
        patterns = [
            (r"\s+Sarok\s+fels[őo]\b.*$", "Sarok felső"),
            (r"\s+Fels[őo]\s+felny[ií]l[oó]s\b.*$", "Felnyíló"),
            (r"\s+F_?2A\b.*$", "F2A"),
            (r"\s+EF60_?72\b.*$", "EF60_72"),
            (r"\s+EF60\b.*$", "EF60"),
            (r"\s+FNY\b.*$", "FNY"),
            (r"\s+EFT\b.*$", "EFT"),
            (r"\s+FVZ\b.*$", "FVZ"),
            (r"\s+FMFS\b.*$", "FMFS"),
            (r"\s+FMF\b.*$", "FMF"),
            (r"\s+FKF\s+Tiplis\b.*$", "FKF Tiplis"),
            (r"\s+FKF\b.*$", "FKF"),
            (r"\s+FZN\b.*$", "FZN"),
            (r"\s+FÜF\b.*$", "FÜF"),
            (r"\s+FUF\b.*$", "FÜF"),
            (r"\s+Fels[őo]\b.*$", "Normál"),
        ]
        detected_side = side_text
        stripped_color = color_text
        changed = True
        while changed and stripped_color:
            changed = False
            for pattern, candidate_side in patterns:
                if re.search(pattern, stripped_color, flags=re.IGNORECASE):
                    stripped_color = re.sub(pattern, "", stripped_color, flags=re.IGNORECASE).strip(" -")
                    if not detected_side or detected_side in {"-", ""}:
                        detected_side = candidate_side
                    changed = True
                    break
        return stripped_color or color_text, detected_side

    def extract_embedded_upper_rows(raw_row: dict, source_group: str) -> list[dict]:
        """Extract extract embedded upper rows data."""
        detail_text = clean_text(raw_row.get("detail"))
        if not detail_text:
            return []
        embedded_rows: list[dict] = []
        segments = re.findall(
            r"(Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18.*?)(?=(?:Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18)|$)",
            detail_text,
            flags=re.IGNORECASE,
        )
        for segment in segments:
            match = re.match(
                r"(Fels[őo] oldal)\s+(1H(?:2R)?)\s+(360 x (?:330|550) x 18)\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű\. ]+?)\s+([A-Z0-9ÁÉÍÓÖŐÚÜŰa-záéíóöőúüű]+)(?:\s+(1H(?:2R)?))?(?:\s+(\d+))?\s+(N|KESB|GTEL)\s*$",
                clean_text(segment),
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            name, edge, size, color, side_type, maybe_edge, maybe_qty, hardware_type = match.groups()
            normalized_color, normalized_side_type = split_upper_color_and_side_v2(color, side_type)
            embedded_rows.append(
                {
                    "sourceGroup": source_group,
                    "name": cnc_display_name(name),
                    "source_name": clean_text(name),
                    "size": clean_text(size),
                    "color": normalized_color,
                    "hardware_type": clean_text(hardware_type),
                    "side_type": clean_text(normalized_side_type or side_type),
                    "edge": clean_text(maybe_edge or edge or "-") or "-",
                    "quantity": int(maybe_qty or 2),
                    "detail": "",
                    "columnLayout": "cnc-upper",
                }
            )
        return embedded_rows

    def clean_upper_detail_for_display(detail: object, side_type: object, hardware_type: object) -> str:
        """Remove grouping-only tokens from upper row detail text."""
        text = clean_text(detail)
        if not text:
            return ""
        side_text = clean_text(side_type)
        hardware_text = clean_text(hardware_type)
        if side_text and hardware_text and side_text != "-" and hardware_text != "-":
            # Remove helper fragments like: "Sarok felső 1H2R 13 N"
            text = re.sub(
                rf"{re.escape(side_text)}\s+\S+\s+\d{{1,3}}\s+{re.escape(hardware_text)}\b",
                "",
                text,
                flags=re.IGNORECASE,
            )
        text = re.sub(
            r"Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18.*?(?=(?:Fels[őo] oldal\s+1H(?:2R)?\s+360 x (?:330|550) x 18)|$)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = clean_text(text)
        candidates = {
            "",
            side_text,
            hardware_text,
            clean_text(f"{side_text} {hardware_text}"),
            clean_text(f"{hardware_text} {side_text}"),
        }
        if text in candidates:
            return ""
        return text

    def upper_quantity_hint_from_detail(detail: object, edge: object, side_type: object, hardware_type: object) -> int:
        """Infer an upper-row quantity hint from detail text."""
        text = clean_text(detail)
        edge_text = clean_text(edge)
        side_text = clean_text(side_type)
        hardware_text = clean_text(hardware_type)
        if not text or not edge_text:
            return 0
        folded_text = folded(text)
        marker_positions = []
        for marker in ("felso oldal", "felso vegzaro", "teto-fenek mart", "eft fenek excenteres"):
            marker_index = folded_text.find(marker)
            if marker_index > 0:
                marker_positions.append(marker_index)
        scan_text = clean_text(text[:min(marker_positions)]) if marker_positions else text
        if not scan_text:
            scan_text = text
        candidates: list[int] = []
        patterns = [
            # "1H2R 13 N"
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(side_text)}\b" if side_text and side_text != "-" else "",
            # "1H2R N 13"
            rf"{re.escape(edge_text)}\s*{re.escape(side_text)}\s*(\d{{1,3}})\b" if side_text and side_text != "-" else "",
            # "1H2R 13 N" where N is hardware type
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(hardware_text)}\b" if hardware_text and hardware_text != "-" else "",
            # "1H2R N 13" where N is hardware type
            rf"{re.escape(edge_text)}\s*{re.escape(hardware_text)}\s*(\d{{1,3}})\b" if hardware_text and hardware_text != "-" else "",
            # merged OCR token: "1H2R13N"
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(side_text)}" if side_text and side_text != "-" else "",
            rf"{re.escape(edge_text)}\s*(\d{{1,3}})\s*{re.escape(hardware_text)}" if hardware_text and hardware_text != "-" else "",
        ]
        for pattern in patterns:
            if not pattern:
                continue
            for match in re.finditer(pattern, scan_text, flags=re.IGNORECASE):
                try:
                    value = int(match.group(1))
                except Exception:
                    continue
                if 1 <= value <= 999:
                    candidates.append(value)
        return max(candidates) if candidates else 0

    def upper_sarok_quantity_hint(detail: object, edge: object) -> int:
        """Infer corner upper quantity hints from size and detail text."""
        text = clean_text(detail)
        edge_text = clean_text(edge)
        if not text or not edge_text:
            return 0
        lowered = folded(text)
        if "sarok fels" not in lowered:
            return 0
        pattern = rf"sarok\s+fels[őo]\s+{re.escape(edge_text)}\s+(\d{{1,3}})\s+(?:N|KESB|GTEL|TE|RI|JO)\b"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return 0
        try:
            value = int(match.group(1))
        except Exception:
            return 0
        return value if 1 <= value <= 999 else 0

    def is_kamra_row(name: str, color: str, side_type: str) -> bool:
        """Return whether is kamra row is true."""
        combined = " ".join([folded(name), folded(color), normalize_side_type(side_type)])
        return "kamra" in combined or "k40" in combined or "k60" in combined or "kmth" in combined or "kmtb" in combined or "ktb60" in combined

    def is_kamra_teto_fenek_row(row: dict) -> bool:
        """Return whether a lower kamra row belongs in the teto-fenek bucket."""
        name_text = " ".join([folded(row.get("source_name")), folded(row.get("name"))])
        return (
            "kamra fenek" in name_text
            or "kamra teto-fenek" in name_text
            or "kamra teto fenek" in name_text
        )

    def is_non_nutos_text(value: object) -> bool:
        """Return whether is non nutos text is true."""
        text = clean_text(value).strip().lower()
        folded_text = folded(text)
        return "nem nútos" in text or "nem nutos" in folded_text

    def is_fiokos_family(row: dict) -> bool:
        """Return whether is fiokos family is true."""
        combined = " ".join(
            [
                folded(row.get("source_name")),
                folded(row.get("name")),
                normalize_side_type(row.get("side_type")),
                folded(row.get("detail")),
            ]
        )
        return "fiokos" in combined or "aaf" in combined or "af 1+2" in combined or "af 1 + 2" in combined


    def build_lower_rows(source_sections: list[dict]) -> list[dict]:
        """Build normalized lower-cabinet CNC rows from source rows."""
        merged: dict[tuple[str, ...], dict] = {}
        for section in source_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                source_name = clean_text(raw_row.get("name"))
                name = cnc_display_name(raw_row.get("name"))
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                raw_edge = clean_text(raw_row.get("edge")) or "-"
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(raw_row.get("detail"))
                direct_drawer_drill = clean_text(raw_row.get("drawer_drill"))
                direct_side_type = clean_text(raw_row.get("side_type"))
                direct_hardware_type = clean_text(raw_row.get("hardware_type"))
                if direct_drawer_drill or direct_side_type or direct_hardware_type:
                    drawer_drill = direct_drawer_drill
                    side_type = canonical_side_type(direct_side_type)
                    hardware_type = direct_hardware_type
                color, side_type = split_lower_color_and_side_v2(color, side_type)

                folded_name = folded(name)
                if "takarolap as" in folded_name:
                    # OCR sometimes emits "alsó 1H 1 Takarólap AS" as name and
                    # "Normál alsó" in detail. This is not a Normál oldalelem.
                    # Normalize it so it stays in AS takarósáv sections.
                    name = "Takarólap AS"
                    drawer_drill = ""
                    side_type = ""
                    hardware_type = ""

                edge = parsed_edge or raw_edge
                if is_kamra_row(name, color, side_type):
                    folded_drill = folded(drawer_drill)
                    if folded_drill.startswith("box hettich"):
                        drawer_drill = "Box Hettich"
                    elif folded_drill.startswith("teleszk"):
                        drawer_drill = "Teleszkóp"
                    elif folded_drill.startswith("nincs"):
                        drawer_drill = "Nincs"
                source_row_id = str(raw_row.get("state_storage_key") or raw_row.get("row_id", "")).strip()
                unique_source_key = f"{source_row_id or 'source-row'}|{len(merged)}"
                merge_key = (name, size, color, drawer_drill, side_type, edge, hardware_type, unique_source_key)
                quantity = int(raw_row.get("quantity", 0) or 0)
                existing = merged.get(merge_key)
                if existing is None:
                    merged_id = hashlib.sha1(
                        f"cnc-lower|{production_number}|{name}|{size}|{color}|{drawer_drill}|{side_type}|{edge}|{hardware_type}|{unique_source_key}".encode("utf-8")
                    ).hexdigest()[:16]
                    row_state_fields = {"state_storage_key": source_row_id, "state_key": source_row_id} if "::" in source_row_id else {}
                    merged[merge_key] = {
                        "row_id": merged_id,
                        "state_key": _manufacturing_state_key(production_number, merged_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": name,
                        "source_name": source_name,
                        "size": size,
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": edge,
                        "quantity": quantity,
                        "detail": clean_text(raw_row.get("detail")),
                        "columnLayout": "cnc-lower",
                        "isMuted": is_non_nutos_text(name) or is_non_nutos_text(source_name),
                        "sourceRowIds": [source_row_id] if source_row_id else [],
                        **row_state_fields,
                    }
                else:
                    existing["quantity"] = int(existing.get("quantity", 0) or 0) + quantity
                    if source_name:
                        existing["source_name"] = f"{existing.get('source_name', '')} · {source_name}".strip(" ·")
                    existing["isMuted"] = bool(existing.get("isMuted")) or is_non_nutos_text(name) or is_non_nutos_text(source_name)
                    source_row_id = str(raw_row.get("state_storage_key") or raw_row.get("row_id", "")).strip()
                    if source_row_id:
                        source_row_ids = list(existing.get("sourceRowIds", []))
                        if source_row_id not in source_row_ids:
                            source_row_ids.append(source_row_id)
                        existing["sourceRowIds"] = source_row_ids
        return list(merged.values())

    def upper_source_group(section_label: object) -> str:
        """Classify an upper row into its source grouping bucket."""
        text = clean_text(section_label)
        folded_text = folded(text)
        if "1-es" in folded_text:
            return "1-es"
        if "2-es" in folded_text:
            return "2-es"
        return text or "egyeb"

    def build_expected_upper_excenter_counts() -> dict[tuple[str, str, str, str, str, str, str], int]:
        """Return expected excenter counts for upper cabinet grouping."""
        return {}

        expected: dict[tuple[str, str, str, str, str, str, str], int] = {}
        current_label = ""
        for lines in pages:
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                token_folded = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", token_folded) or re.fullmatch(r"[12]-es\s+fels.*", token_folded):
                    current_label = token
                    index += 1
                    continue
                if "fels" not in folded(current_label):
                    index += 1
                    continue
                if token_folded not in {"eft fenek", "eft fenek excenteres"}:
                    index += 1
                    continue

                cursor = index + 1
                if cursor < len(lines) and folded(clean_text(lines[cursor])) == "excenteres":
                    cursor += 1
                if cursor + 7 >= len(lines):
                    index += 1
                    continue

                size_tokens = [clean_text(lines[cursor + offset]) for offset in range(5)]
                if not (
                    size_tokens[0].isdigit()
                    and size_tokens[1].lower() == "x"
                    and size_tokens[2].isdigit()
                    and size_tokens[3].lower() == "x"
                    and size_tokens[4].isdigit()
                ):
                    index += 1
                    continue

                size_label = f"{size_tokens[0]} x {size_tokens[2]} x {size_tokens[4]}"
                color = clean_text(lines[cursor + 5])
                edge = clean_text(lines[cursor + 6]) or "-"
                quantity_token = clean_text(lines[cursor + 7])
                if not re.fullmatch(r"-?\d+", quantity_token):
                    index += 1
                    continue

                quantity = int(quantity_token)
                source_group = upper_source_group(current_label)
                key = (
                    source_group,
                    "EFT fenék excenteres",
                    size_label,
                    color,
                    "",
                    "",
                    edge,
                )
                expected[key] = int(expected.get(key, 0) or 0) + quantity
                index = cursor + 8
        return expected

    def build_upper_rows(source_sections: list[dict]) -> list[dict]:
        """Build normalized upper-cabinet CNC rows from source rows."""
        merged: dict[tuple[str, ...], dict] = {}
        def add_upper_row(parsed_row: dict, raw_row: dict | None = None) -> None:
            """Append one normalized upper row to the target collection."""
            source_group = clean_text(parsed_row.get("sourceGroup"))
            name = clean_text(parsed_row.get("name"))
            source_name = clean_text(parsed_row.get("source_name"))
            size = clean_text(parsed_row.get("size"))
            color = clean_text(parsed_row.get("color"))
            hardware_type = clean_text(parsed_row.get("hardware_type"))
            side_type = clean_text(parsed_row.get("side_type"))
            edge = clean_text(parsed_row.get("edge")) or "-"
            quantity = int(parsed_row.get("quantity", 0) or 0)
            mark_size_black = bool(parsed_row.get("markSizeBlack"))
            source_row_id = ""
            if raw_row is not None:
                source_row_id = str(raw_row.get("state_storage_key") or raw_row.get("row_id", "")).strip()
            unique_source_key = f"{source_row_id or 'source-row'}|{len(merged)}"
            merge_key = (source_group, name, size, color, hardware_type, side_type, edge, unique_source_key)
            existing = merged.get(merge_key)
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-upper|{production_number}|{source_group}|{name}|{size}|{color}|{hardware_type}|{side_type}|{edge}|{unique_source_key}".encode("utf-8")
                ).hexdigest()
                row_state_fields = {"state_storage_key": source_row_id, "state_key": source_row_id} if "::" in source_row_id else {}
                merged[merge_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "sourceGroup": source_group,
                    "name": name,
                    "source_name": source_name,
                    "size": size,
                    "color": color,
                    "hardware_type": hardware_type,
                    "side_type": side_type,
                    "edge": edge,
                    "quantity": quantity,
                    "detail": clean_text(parsed_row.get("detail")),
                    "columnLayout": "cnc-upper",
                    "markSizeBlack": mark_size_black,
                    "sourceRowIds": [source_row_id] if source_row_id else [],
                    **row_state_fields,
                }
            else:
                existing["quantity"] = int(existing.get("quantity", 0) or 0) + quantity
                existing["markSizeBlack"] = bool(existing.get("markSizeBlack")) or mark_size_black
                if source_name:
                    existing["source_name"] = f"{existing.get('source_name', '')} · {source_name}".strip(" ·")
                if source_row_id:
                    source_row_ids = list(existing.get("sourceRowIds", []))
                    if source_row_id not in source_row_ids:
                        source_row_ids.append(source_row_id)
                    existing["sourceRowIds"] = source_row_ids

        for section in source_sections:
            source_group = upper_source_group(section.get("label"))
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                source_name = clean_text(raw_row.get("name"))
                name = cnc_display_name(raw_row.get("name"))
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                edge = clean_text(raw_row.get("edge")) or "-"
                side_type, hardware_type = parse_upper_detail_v2(raw_row.get("detail"))
                direct_side_type = clean_text(raw_row.get("side_type"))
                direct_hardware_type = clean_text(raw_row.get("hardware_type"))
                if direct_side_type or direct_hardware_type:
                    side_type = direct_side_type
                    hardware_type = direct_hardware_type
                color, side_type = split_upper_color_and_side_v2(color, side_type)
                raw_quantity = int(raw_row.get("quantity", 0) or 0)
                quantity_hint = upper_quantity_hint_from_detail(raw_row.get("detail"), edge, side_type, hardware_type)
                sarok_quantity_hint = upper_sarok_quantity_hint(raw_row.get("detail"), edge)
                if quantity_hint > raw_quantity:
                    raw_quantity = quantity_hint
                if sarok_quantity_hint > raw_quantity:
                    raw_quantity = sarok_quantity_hint
                add_upper_row(
                    {
                        "sourceGroup": source_group,
                        "name": name,
                        "source_name": source_name,
                        "size": size,
                        "color": color,
                        "hardware_type": hardware_type,
                        "side_type": side_type,
                        "edge": edge,
                        "quantity": raw_quantity,
                        "detail": clean_upper_detail_for_display(raw_row.get("detail"), side_type, hardware_type),
                        "markSizeBlack": bool(raw_row.get("markSizeBlack")),
                    },
                    raw_row,
                )
                for embedded_row in extract_embedded_upper_rows(raw_row, source_group):
                    add_upper_row(embedded_row)

        expected_excenter_counts = build_expected_upper_excenter_counts()
        if expected_excenter_counts:
            actual_excenter_counts: dict[tuple[str, str, str, str, str, str, str], int] = {}
            for row in merged.values():
                row_name_folded = folded(row.get("name"))
                if row_name_folded != "eft fenek excenteres":
                    continue
                key = (
                    clean_text(row.get("sourceGroup")),
                    clean_text(row.get("name")),
                    clean_text(row.get("size")),
                    clean_text(row.get("color")),
                    clean_text(row.get("hardware_type")),
                    clean_text(row.get("side_type")),
                    clean_text(row.get("edge")) or "-",
                )
                actual_excenter_counts[key] = int(actual_excenter_counts.get(key, 0) or 0) + int(row.get("quantity", 0) or 0)

            for key, expected_qty in expected_excenter_counts.items():
                actual_qty = int(actual_excenter_counts.get(key, 0) or 0)
                if expected_qty <= actual_qty:
                    continue
                source_group, name, size, color, hardware_type, side_type, edge = key
                add_upper_row(
                    {
                        "sourceGroup": source_group,
                        "name": name,
                        "source_name": name,
                        "size": size,
                        "color": color,
                        "hardware_type": hardware_type,
                        "side_type": side_type,
                        "edge": edge,
                        "quantity": expected_qty - actual_qty,
                        "detail": "",
                    }
                )
        return list(merged.values())

    def build_front_rows(source_sections: list[dict]) -> list[dict]:
        """Build front-drilling rows from Fiokelo source rows."""
        palette = ("blue", "violet", "amber", "cyan", "slate", "orange", "rose", "lime", "teal")
        explicit_model_tones = {
            "anna": "blue",
            "kinga": "amber",
            "antonia": "violet",
            "laura": "cyan",
            "zille": "slate",
            "kata": "orange",
            "doroti": "rose",
            "kira": "lime",
            "klio": "teal",
        }
        known_models = {"anna", "kinga", "antonia", "laura", "zille", "kata", "doroti", "kira", "klio"}
        invalid_model_tokens = {"", "-", "nincs", "front", "frontos", "furva", "fura", "fio", "fiok"}

        def fiokelo_group_label(section_label: object) -> str:
            """Return the visible Fiokelo group label for a row."""
            text = clean_text(section_label)
            folded_text = folded(text)
            if re.search(r"\b1-es\b", folded_text):
                return "1-es"
            if re.search(r"\b2-es\b", folded_text):
                return "2-es"
            return text or "Egyéb"

        def fiokelo_model_label(detail: object) -> str:
            """Return the normalized Fiokelo model label."""
            text = clean_text(detail)
            if not text:
                return "Ismeretlen modell"
            prefix = clean_text(text.split(" - ", 1)[0])
            prefix = re.sub(r"\bNincs\b", "", prefix, flags=re.IGNORECASE).strip(" -")
            first_token = clean_text(prefix.split()[0] if prefix else "")
            return first_token or prefix or "Ismeretlen modell"

        def parse_fiokelo_detail(detail: object) -> tuple[str, str, str, str]:
            """Parse Fiokelo detail text into model, color, size, and hint parts."""
            text = clean_text(detail)
            if not text:
                return "-", "-", "-", "-"
            parts = [clean_text(part) for part in text.split(" - ") if clean_text(part)]
            prefix = clean_text(parts[0]) if parts else ""
            suffix = clean_text(" - ".join(parts[1:])) if len(parts) > 1 else ""

            # Some legacy extracts split across lines and produce a leading technical token
            # ("Nincs", "Fúrva", "front"), while the real model+color starts in the next chunk.
            leading_token = re.sub(r"[^a-z0-9]+", "", folded(prefix))
            if len(parts) >= 2 and leading_token in {"nincs", "furva", "front", "frontos", "fio", "fiok"}:
                prefix = clean_text(parts[1])
                tail_parts = []
                if parts[0]:
                    tail_parts.append(parts[0])
                if len(parts) > 2:
                    tail_parts.extend(parts[2:])
                suffix = clean_text(" - ".join(tail_parts))

            prefix_tokens = [token for token in prefix.split() if token]
            # Some legacy extracts keep a broken leading token from "Fiókelő"
            # (for example only "ó"), which would shift model/color columns.
            while prefix_tokens:
                lead_normalized = re.sub(r"[^a-z0-9]+", "", folded(prefix_tokens[0]))
                if lead_normalized in {"fiokelo", "fiokelofuras", "fiok", "fio", "io", "front", "frontos", "frontfuras"}:
                    prefix_tokens.pop(0)
                    continue
                if len(prefix_tokens) > 1 and lead_normalized in {"o", "a"}:
                    prefix_tokens.pop(0)
                    continue
                break
            model_index = -1
            for idx, token in enumerate(prefix_tokens):
                normalized = re.sub(r"[^a-z0-9]+", "", folded(token))
                if normalized in known_models:
                    model_index = idx
                    break

            if model_index != -1:
                model_label = clean_text(prefix_tokens[model_index]) or "Ismeretlen modell"
                netfront_color = clean_text(" ".join(prefix_tokens[model_index + 1 :])).strip(" -")
            else:
                model_label = clean_text(prefix_tokens[0]) if prefix_tokens else "Ismeretlen modell"
                netfront_color = clean_text(" ".join(prefix_tokens[1:])).strip(" -")
            if folded(netfront_color) == "nincs":
                netfront_color = ""

            suffix_tokens = [token for token in suffix.split() if token]
            drawer_type = ""
            if suffix_tokens and re.fullmatch(r"[A-Z]{1,4}", suffix_tokens[-1]):
                drawer_type = suffix_tokens.pop()
            drill_text = clean_text(" ".join(suffix_tokens))
            folded_drill_text = folded(drill_text)
            if "furva" in folded_drill_text:
                drill_label = "Fúrva"
            elif "nincs" in folded_drill_text:
                drill_label = "Nincs"
            else:
                drill_label = "-"
            return (
                model_label or "Ismeretlen modell",
                netfront_color or "-",
                drill_label or "-",
                drawer_type or "-",
            )

        def fiokelo_model_tone(model_label: object) -> str:
            """Return model tone or color classification used for grouping."""
            token = folded(model_label)
            if not token:
                return "slate"
            normalized_token = re.sub(r"[^a-z0-9]+", "", token)
            if normalized_token in explicit_model_tones:
                return explicit_model_tones[normalized_token]
            return palette[sum(ord(char) for char in token) % len(palette)]

        def normalized_color_key(value: object) -> str:
            """Return an accent-insensitive color grouping key."""
            return re.sub(r"[^a-z0-9]+", " ", folded(clean_text(value))).strip()

        color_fallback_map = {
            "sm feher folias": "Pure White",
            "sm kasmir folias": "Dune Beige",
            "sm provance folias": "Cedar Green",
            "sm beige folias": "Palo Santo Beige",
            "mf feher": "Mf. Fehér",
            "mf capuccino": "Mf. Latte",
            "mf beige": "Mf. Krém",
            "feher fenyes evogloss": "Magasfényű fehér",
            "matt grafit folias": "Matt antracit",
            "beige folias": "Uni beige",
            "canyon tolgy": "Canyon tölgy",
            "sonoma tolgy": "Sonoma tölgy",
            "kasmir": "Kasmír",
            "antracit kr": "Antracit kr.",
        }

        parsed_rows: list[dict] = []

        def split_model_color_token(value: object) -> tuple[str, str]:
            """Split a model/color token into model and color parts."""
            text = clean_text(value)
            if not text:
                return "", ""
            tokens = [token for token in text.split() if token]
            if not tokens:
                return "", ""
            first_norm = re.sub(r"[^a-z0-9]+", "", folded(tokens[0]))
            if first_norm in known_models:
                model = clean_text(tokens[0])
                color = clean_text(" ".join(tokens[1:]))
                return model, color
            return "", ""

        def is_invalid_model(value: object) -> bool:
            """Return whether is invalid model is true."""
            normalized = re.sub(r"[^a-z0-9]+", "", folded(clean_text(value)))
            return normalized in invalid_model_tokens

        for section in source_sections:
            group_label = fiokelo_group_label(section.get("label"))
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                name = cnc_display_name(raw_row.get("name"))
                if folded(name) == "blende":
                    continue
                size = clean_text(raw_row.get("size"))
                color = clean_text(raw_row.get("color"))
                edge = clean_text(raw_row.get("edge")) or "-"
                detail = clean_text(raw_row.get("detail"))
                model_label, netfront_color, drill_label, drawer_type = parse_fiokelo_detail(detail)

                # Legacy extraction sometimes shifts model into color/netfront fields (e.g. "Kira Fehér").
                # Recover model + color before rendering so model column never shows technical placeholders.
                model_from_color, color_without_model = split_model_color_token(color)
                model_from_netfront, netfront_without_model = split_model_color_token(netfront_color)

                if is_invalid_model(model_label):
                    if model_from_color:
                        model_label = model_from_color
                    elif model_from_netfront:
                        model_label = model_from_netfront

                if model_from_color:
                    model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_label))
                    color_model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_from_color))
                    if is_invalid_model(model_label) or model_norm == color_model_norm:
                        color = color_without_model or color

                if model_from_netfront:
                    model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_label))
                    netfront_model_norm = re.sub(r"[^a-z0-9]+", "", folded(model_from_netfront))
                    if is_invalid_model(model_label) or model_norm == netfront_model_norm:
                        netfront_color = netfront_without_model or netfront_color

                model_tone = fiokelo_model_tone(model_label)
                parsed_rows.append(
                    {
                        "groupLabel": group_label,
                        "name": name,
                        "size": size,
                        "color": color,
                        "edge": edge,
                        "detail": detail,
                        "modelLabel": model_label,
                        "netfrontColor": netfront_color,
                        "drillLabel": drill_label,
                        "drawerType": drawer_type,
                        "modelTone": model_tone,
                        "code": raw_row.get("code", ""),
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                        "doc_key": raw_row.get("doc_key", "fiokelo_furas"),
                        "state_key": raw_row.get("state_key", ""),
                        "state_storage_key": raw_row.get("state_storage_key", ""),
                    }
                )

        explicit_model_color_map: dict[tuple[str, str], str] = {}
        explicit_color_map: dict[str, str] = {}
        for row in parsed_rows:
            netfront_color = clean_text(row.get("netfrontColor"))
            if not netfront_color or netfront_color == "-":
                continue
            model_key = folded(row.get("modelLabel"))
            color_key = normalized_color_key(row.get("color"))
            if model_key and color_key:
                explicit_model_color_map[(model_key, color_key)] = netfront_color
            if color_key:
                explicit_color_map[color_key] = netfront_color

        rendered_rows: list[dict] = []
        for index, row in enumerate(parsed_rows):
            model_label = clean_text(row.get("modelLabel"))
            color = clean_text(row.get("color"))
            color_key = normalized_color_key(color)
            model_key = folded(model_label)
            netfront_color = clean_text(row.get("netfrontColor"))
            folded_color = folded(color)
            is_nettfront_front = ("folias" in folded_color) or bool(re.search(r"\bmf\b", folded_color))

            if is_nettfront_front and (not netfront_color or netfront_color == "-"):
                netfront_color = (
                    explicit_model_color_map.get((model_key, color_key))
                    or explicit_color_map.get(color_key)
                    or color_fallback_map.get(color_key)
                    or color
                    or "-"
                )
            elif not is_nettfront_front:
                netfront_color = "-"

            row_id = hashlib.sha1(
                f"cnc-front|{production_number}|{index}|{row.get('groupLabel','')}|{row.get('name','')}|{model_label}|{color}|{row.get('size','')}|{netfront_color}|{row.get('drillLabel','')}|{row.get('drawerType','')}|{row.get('quantity',0)}".encode("utf-8")
            ).hexdigest()[:16]
            state_storage_key = str(row.get("state_storage_key", "") or "").strip()
            state_key = str(row.get("state_key", "") or state_storage_key).strip()
            rendered_rows.append(
                {
                    "row_id": row_id,
                    "state_key": state_key or _manufacturing_state_key(production_number, row_id),
                    "state_storage_key": state_storage_key or row_id,
                    "sourceRowIds": [state_storage_key] if state_storage_key else [],
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": row.get("name", ""),
                    "size": row.get("size", ""),
                    "color": color,
                    "edge": row.get("edge", ""),
                    "quantity": int(row.get("quantity", 0) or 0),
                    "code": row.get("code", ""),
                    "doc_key": row.get("doc_key", "fiokelo_furas"),
                    "detail": row.get("detail", ""),
                    "fiokeloGroup": row.get("groupLabel", ""),
                    "modelLabel": model_label,
                    "netfrontColor": netfront_color,
                    "drillLabel": row.get("drillLabel", ""),
                    "drawerType": row.get("drawerType", ""),
                    "modelTone": row.get("modelTone", "slate"),
                    "hideSubtitle": True,
                }
            )
        return rendered_rows

    also_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("cnc::") and "als" in folded(section.get("label", ""))
    ]
    felso_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("cnc::") and "fels" in folded(section.get("label", ""))
    ]
    front_source_sections = [
        dict(section)
        for section in raw_sections
        if str(section.get("key", "")).startswith("fiokelo_furas::")
    ]

    lower_rows = build_lower_rows(also_source_sections)
    upper_rows = build_upper_rows(felso_source_sections)
    front_rows = build_front_rows(front_source_sections)

    lower_box_order = {
        "pultos nor. al.": 0,
        "as vt": 1,
        "as magic": 2,
        "atf": 3,
        "aszb kihuzhato szemetes": 4,
        "aszhs": 4,
        "akl": 5,
        "ar": 6,
        "ar golyos tel.": 6,
        "kira": 7,
        "nyitott": 8,
    }
    upper_side_order = {"N": 0, "KESB": 1, "GTEL": 2, "TE": 3, "RI": 4, "JO": 5}

    lower_box_sections: list[dict] = []

    def clone_row(row: dict, **updates: object) -> dict:
        """Return a shallow copy of a row with optional overrides."""
        cloned = dict(row)
        cloned.update(updates)
        return cloned

    def add_lower_section(label: str, rows: list[dict], key_suffix: str, *, hide_side_type: bool = False) -> None:
        """Append a lower-cabinet section when it has rows."""
        if not rows:
            return
        lower_box_sections.append(
            {
                "key": f"cnc-also::{key_suffix}",
                "label": label,
                "rows": rows,
                "columnLayout": "cnc-lower",
                "hideSideTypeColumn": hide_side_type,
            }
        )

    def hide_lower_subtitles(rows: list[dict]) -> None:
        """Mark lower-section rows to hide repeated subtitle text."""
        for row in rows:
            if isinstance(row, dict):
                row["hideSubtitle"] = True

    def set_kinga_anna_subtitles(rows: list[dict]) -> None:
        """Set compact subtitles for Kinga and Anna grouped rows."""
        for row in rows:
            if not isinstance(row, dict):
                continue
            row["detail"] = clean_text(" ".join(
                part
                for part in (clean_text(row.get("drawer_drill")), clean_text(row.get("side_type")))
                if part and part != "-"
            ))
            row.pop("hideSubtitle", None)

    def aggregate_lower_rows(rows: list[dict], group_fields: tuple[str, ...], *, hide_subtitle: bool = False) -> list[dict]:
        """Aggregate lower-cabinet rows by display-relevant fields."""
        unmerged_rows: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["hideSubtitle"] = hide_subtitle
            item["_postOverrideMergeFields"] = list(group_fields)
            item["_postOverrideMergeKind"] = "lower-box"
            unmerged_rows.append(item)
        return unmerged_rows

        grouped: dict[tuple[str, ...], dict] = {}
        for row in rows:
            group_key = tuple(clean_text(row.get(field)) for field in group_fields)
            existing = grouped.get(group_key)
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-lower-box|{production_number}|{'|'.join(group_key)}".encode("utf-8")
                ).hexdigest()[:16]
                source_row_ids = [
                    source_row_id
                    for source_row_id in (
                        str(source_id).strip()
                        for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                    )
                    if source_row_id
                ]
                grouped[group_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": clean_text(row.get("name")),
                    "size": clean_text(row.get("size")),
                    "color": clean_text(row.get("color")),
                    "drawer_drill": clean_text(row.get("drawer_drill")),
                    "side_type": clean_text(row.get("side_type")),
                    "hardware_type": clean_text(row.get("hardware_type")),
                    "edge": clean_text(row.get("edge")) or "-",
                    "quantity": int(row.get("quantity", 0) or 0),
                    "detail": "",
                    "columnLayout": "cnc-lower",
                    "hideSubtitle": hide_subtitle,
                    "isMuted": bool(row.get("isMuted")),
                    "sourceRowIds": source_row_ids,
                    "_colors": {clean_text(row.get("color"))},
                    "_drills": {clean_text(row.get("drawer_drill"))},
                    "_edges": {clean_text(row.get("edge")) or "-"},
                    "_hardware": {clean_text(row.get("hardware_type"))},
                }
                continue
            existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
            existing["isMuted"] = bool(existing.get("isMuted")) or bool(row.get("isMuted"))
            existing["_colors"].add(clean_text(row.get("color")))
            existing["_drills"].add(clean_text(row.get("drawer_drill")))
            existing["_edges"].add(clean_text(row.get("edge")) or "-")
            existing["_hardware"].add(clean_text(row.get("hardware_type")))
            source_row_ids = list(existing.get("sourceRowIds", []))
            for source_row_id in (
                str(source_id).strip()
                for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
            ):
                if source_row_id and source_row_id not in source_row_ids:
                    source_row_ids.append(source_row_id)
            existing["sourceRowIds"] = source_row_ids

        aggregated_rows: list[dict] = []
        for item in grouped.values():
            item["color"] = next(iter(item["_colors"])) if len(item["_colors"]) == 1 else "Vegyes"
            item["drawer_drill"] = next(iter(item["_drills"])) if len(item["_drills"]) == 1 else "Vegyes"
            item["edge"] = next(iter(item["_edges"])) if len(item["_edges"]) == 1 else "Vegyes"
            item["hardware_type"] = next(iter(item["_hardware"])) if len(item["_hardware"]) == 1 else "Vegyes"
            item.pop("_colors", None)
            item.pop("_drills", None)
            item.pop("_edges", None)
            item.pop("_hardware", None)
            aggregated_rows.append(item)
        return aggregated_rows

    def aggregate_kinga_anna_fiokos_rows(rows: list[dict]) -> list[dict]:
        """Aggregate Kinga and Anna drawer rows into display groups."""
        unmerged_rows: list[dict] = []
        mergeable_side_types = {"aaf fiokos ajtos", "af 1+2 fiokos"}
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if normalize_side_type(item.get("side_type")) in mergeable_side_types:
                item["_postOverrideMergeFields"] = [
                    "name", "size", "color", "edge", "drawer_drill", "hardware_type"
                ]
                item["_postOverrideMergeKind"] = "kinga-anna"
            unmerged_rows.append(item)
        return unmerged_rows

        mergeable_side_types = {"aaf fiokos ajtos", "af 1+2 fiokos"}
        grouped: dict[tuple[str, str, str, str, str, str], dict] = {}
        output_rows: list[dict] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            side_type_norm = normalize_side_type(row.get("side_type"))
            if side_type_norm not in mergeable_side_types:
                output_rows.append(row)
                continue

            group_key = (
                clean_text(row.get("name")),
                clean_text(row.get("size")),
                clean_text(row.get("color")),
                clean_text(row.get("edge")) or "-",
                clean_text(row.get("drawer_drill")),
                clean_text(row.get("hardware_type")),
            )
            existing = grouped.get(group_key)
            source_row_ids = [
                source_row_id
                for source_row_id in (
                    str(source_id).strip()
                    for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                )
                if source_row_id
            ]
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-lower-kinga-anna|{production_number}|{'|'.join(group_key)}".encode("utf-8")
                ).hexdigest()[:16]
                merged_row = dict(row)
                merged_row.update(
                    {
                        "row_id": merged_id,
                        "state_key": _manufacturing_state_key(production_number, merged_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "quantity": int(row.get("quantity", 0) or 0),
                        "sourceRowIds": source_row_ids,
                        "_sideTypes": {clean_text(row.get("side_type"))},
                    }
                )
                grouped[group_key] = merged_row
                output_rows.append(merged_row)
                continue

            existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
            existing_side_types = existing.setdefault("_sideTypes", set())
            if isinstance(existing_side_types, set):
                existing_side_types.add(clean_text(row.get("side_type")))
            existing_source_row_ids = list(existing.get("sourceRowIds", []))
            for source_row_id in source_row_ids:
                if source_row_id not in existing_source_row_ids:
                    existing_source_row_ids.append(source_row_id)
            existing["sourceRowIds"] = existing_source_row_ids

        for row in output_rows:
            side_types = row.pop("_sideTypes", None)
            if isinstance(side_types, set):
                row["side_type"] = "AF/AAF fiókos"
        return output_rows

    def is_boxos_side_type(row: dict) -> bool:
        """Return whether is boxos side type is true."""
        return normalize_side_type(row.get("side_type")) in {"aaf fiokos ajtos", "af 1+2 fiokos"}

    def is_as_takarosav_row(row: dict) -> bool:
        """Return whether is as takarosav row is true."""
        name_text = folded(row.get("name"))
        return "as takarosav" in name_text or "takarolap as" in name_text

    def is_takarolap_as_row(row: dict) -> bool:
        """Return whether is takarolap as row is true."""
        return "takarolap as" in folded(row.get("name"))

    def is_normal_also_row(row: dict) -> bool:
        """Return whether is normal also row is true."""
        return (
            folded(row.get("name")) == "also oldal"
            and normalize_side_type(row.get("side_type")) == "normals also"
            and not is_as_takarosav_row(row)
            and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        )

    def is_boxos_target_row(row: dict) -> bool:
        """Return whether is boxos target row is true."""
        size_label = clean_text(row.get("size"))
        source_name_folded = folded(row.get("source_name"))
        return (
            size_label in {"724 x 505 x 18", "725 x 505 x 18"}
            and ("fiokos" in source_name_folded or is_boxos_side_type(row))
            and folded(row.get("name")) == "also oldal"
            and not is_as_takarosav_row(row)
            and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        )

    def is_boxos_box_hettich_row(row: dict) -> bool:
        """Return whether is boxos box hettich row is true."""
        return is_boxos_target_row(row) and folded(row.get("drawer_drill")) == "box hettich"

    def is_boxos_teleszkop_row(row: dict) -> bool:
        """Return whether is boxos teleszkop row is true."""
        return is_boxos_target_row(row) and folded(row.get("drawer_drill")).startswith("teleszk")

    def is_kinga_anna_teleszkop_row(row: dict) -> bool:
        """Return whether a Kinga/Anna row uses telescopic rail drilling."""
        return (
            clean_text(row.get("size")) == "824 x 505 x 18"
            and normalize_side_type(row.get("side_type")) in {"normals also", "aaf fiokos ajtos", "af 1+2 fiokos"}
            and folded(row.get("drawer_drill")).startswith("teleszk")
            and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
            and not is_fvz_row(row)
        )

    def is_box1_mergeable_boxos_teleszkop_row(row: dict) -> bool:
        """Return whether AF/AAF teleszkop rows should merge into the normal lower box."""
        return (
            is_boxos_teleszkop_row(row)
            and clean_text(row.get("size")) == "724 x 505 x 18"
            and normalize_side_type(row.get("side_type")) in {"af 1+2 fiokos", "aaf fiokos ajtos"}
            and str(row.get("row_id", "")) not in box_avz_ids
        )

    def build_raw_normal_also_box_rows() -> list[dict]:
        """Collect raw normal lower-box rows before aggregation."""
        return []

        def is_boundary(token: str) -> bool:
            """Return whether is boundary is true."""
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                clean_token == "Alsó oldal"
                or clean_token.startswith("AS takarósáv")
                or clean_token.startswith("Kamra")
                or clean_token.startswith("Takarólap AS")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                if "als" not in folded(current_label) or token != "Alsó oldal":
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                if size_tokens != ["724", "x", "505", "x", "18"]:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                if normalize_side_type(side_type) != "normals also":
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-normal|{production_number}|{page_number}|{index}|{color}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": "724 x 505 x 18",
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "hideSubtitle": True,
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_kinga_anna_box_rows() -> list[dict]:
        """Collect raw Kinga and Anna box rows before aggregation."""
        return []

        def is_boundary(token: str) -> bool:
            """Return whether is boundary is true."""
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                "also oldal" in folded(clean_token)
                or folded(clean_token).startswith("as takarosav")
                or clean_token.startswith("Kamra")
                or folded(clean_token).startswith("takarolap as")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                if "als" not in folded(current_label) or folded(token) != "also oldal":
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                if size_tokens != ["824", "x", "505", "x", "18"]:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                side_type_normalized = normalize_side_type(side_type)
                if side_type_normalized not in {"normals also", "aaf fiokos ajtos", "af 1+2 fiokos"}:
                    index = cursor
                    continue
                normalized_drill = drawer_drill
                if folded(normalized_drill).startswith("teleszk"):
                    normalized_drill = "Teleszkópos"
                elif folded(normalized_drill).startswith("nincs"):
                    normalized_drill = "Nincs"
                else:
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-824|{production_number}|{page_number}|{index}|{color}|{normalized_drill}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": "824 x 505 x 18",
                        "color": color,
                        "drawer_drill": normalized_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_boxos_box_rows() -> list[dict]:
        """Collect raw Boxos box rows before aggregation."""
        if using_xml_cnc_source:
            return []
        alkatresz_sections, _ = _manufacturing_document_sections(
            bundle,
            production_number,
            ("alkatresz_kesz",),
            include_source_prefix=False,
        )
        raw_rows: list[dict] = []
        for section in alkatresz_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                size_label = clean_text(raw_row.get("size"))
                if size_label not in {"724 x 505 x 18", "725 x 505 x 18"}:
                    continue
                if folded(raw_row.get("name")) != "also oldal":
                    continue
                detail = clean_text(raw_row.get("detail"))
                if not detail:
                    continue
                detail_parts = [clean_text(part) for part in detail.split("_") if clean_text(part)]
                detail_folded = [folded(part) for part in detail_parts]
                if "aaf" in detail_folded:
                    side_type = "AAF fiókos ajtós"
                elif "af" in detail_folded:
                    side_type = "AF 1+2 fiókos"
                else:
                    continue
                drawer_drill = ""
                if "bh" in detail_folded:
                    drawer_drill = "Box Hettich"
                elif "t" in detail_folded:
                    drawer_drill = "Teleszkópos"
                elif "n" in detail_folded:
                    drawer_drill = "Nincs"
                if drawer_drill != "Box Hettich":
                    continue
                row_id = hashlib.sha1(
                    f"cnc-raw-boxos|{production_number}|{detail}|{raw_row.get('color')}|{raw_row.get('quantity')}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": clean_text(raw_row.get("color")),
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": "",
                        "edge": clean_text(raw_row.get("edge")) or "-",
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
        return raw_rows

    def build_raw_boxos_teleszkop_rows() -> list[dict]:
        """Collect raw Boxos telescopic rows before aggregation."""
        alkatresz_sections, _ = _manufacturing_document_sections(
            bundle,
            production_number,
            ("alkatresz_kesz",),
            include_source_prefix=False,
        )
        raw_rows: list[dict] = []
        for section in alkatresz_sections:
            for raw_row in section.get("rows", []):
                if not isinstance(raw_row, dict):
                    continue
                size_label = clean_text(raw_row.get("size"))
                if size_label not in {"724 x 505 x 18", "725 x 505 x 18"}:
                    continue
                if folded(raw_row.get("name")) != "also oldal":
                    continue
                detail = clean_text(raw_row.get("detail"))
                if not detail:
                    continue
                detail_parts = [clean_text(part) for part in detail.split("_") if clean_text(part)]
                detail_folded = [folded(part) for part in detail_parts]
                if "aaf" not in detail_folded and "af" not in detail_folded:
                    continue
                if "t" not in detail_folded:
                    continue
                row_id = hashlib.sha1(
                    f"cnc-raw-boxos-teleszkop|{production_number}|{detail}|{raw_row.get('color')}|{raw_row.get('quantity')}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": clean_text(raw_row.get("color")),
                        "drawer_drill": "Teleszkópos",
                        "side_type": "Normáls alsó",
                        "hardware_type": "",
                        "edge": clean_text(raw_row.get("edge")) or "-",
                        "quantity": int(raw_row.get("quantity", 0) or 0),
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "hideSubtitle": True,
                        "isMuted": False,
                    }
                )
        return raw_rows

    def build_raw_egyebek_box_rows() -> list[dict]:
        """Collect raw miscellaneous box rows before aggregation."""
        return []

        def is_boundary(token: str) -> bool:
            """Return whether is boundary is true."""
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                folded_token in {"also oldal", "alsó oldal"}
                or "also oldal" in folded_token
                or "alsó oldal" in folded_token
                or folded_token.startswith("as takarosav")
                or folded_token.startswith("as takarósáv")
                or clean_token.startswith("Kamra")
                or folded(clean_token).startswith("takarolap as")
                or folded(clean_token).startswith("takarólap as")
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        current_label = ""
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if re.fullmatch(r"[12]-es\s+als.*", folded_token) or re.fullmatch(r"[12]-es\s+fels.*", folded_token):
                    current_label = token
                    index += 1
                    continue
                token_folded = folded(token)
                if "also oldal" not in token_folded and "alsó oldal" not in token_folded:
                    index += 1
                    continue
                if index + 5 >= len(lines):
                    index += 1
                    continue
                size_tokens = [clean_text(lines[index + offset]) for offset in range(1, 6)]
                size_label = " ".join(size_tokens)
                if size_label not in {"724 x 505 x 18", "724 x 520 x 18", "724 x 550 x 18", "824 x 505 x 18"}:
                    index += 1
                    continue

                cursor = index + 6
                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if cursor > index + 6 and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1
                if len(tail_tokens) < 3 or not re.fullmatch(r"-?\d+", tail_tokens[-1]):
                    index = cursor
                    continue

                quantity = int(tail_tokens[-1])
                edge = clean_text(tail_tokens[-2]) or "-"
                payload_tokens = [clean_text(token) for token in tail_tokens[:-2] if clean_text(token)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for position in range(len(payload_tokens)):
                    folded_single = folded(payload_tokens[position])
                    folded_pair = folded(" ".join(payload_tokens[position:position + 2]))
                    if folded_single in {"nincs", "teleszkop", "teleszkopos", "avz", "box hettich"} or folded_pair == "box hettich":
                        detail_start = position
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start]))
                detail = clean_text(" ".join(payload_tokens[detail_start:]))
                drawer_drill, side_type, parsed_edge, hardware_type = parse_lower_detail(detail)
                if folded(drawer_drill) == "avz" or re.search(r"\bavz\b", folded(detail)):
                    index = cursor
                    continue
                side_type_normalized = normalize_side_type(side_type)
                if (
                    size_label in {"724 x 505 x 18", "824 x 505 x 18"}
                    and side_type_normalized == "normals also"
                ) or is_boxos_side_type({"side_type": side_type}) or is_as_takarosav_row({"name": "Alsó oldal"}) or is_kamra_row("Alsó oldal", color, side_type):
                    index = cursor
                    continue
                if side_type_normalized not in {
                    "pultos nor. al.",
                    "as vt",
                    "as magic",
                    "atf",
                    "aszb kihuzhato szemetes",
                    "aszhs",
                    "akl",
                    "ar",
                    "kira",
                    "nyitott",
                } and size_label not in {"724 x 505 x 18", "724 x 520 x 18", "724 x 550 x 18", "824 x 505 x 18"}:
                    index = cursor
                    continue

                row_id = hashlib.sha1(
                    f"cnc-raw-egyebek|{production_number}|{page_number}|{index}|{color}|{drawer_drill}|{side_type}|{quantity}".encode('utf-8')
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Alsó oldal",
                        "source_name": "Alsó oldal",
                        "size": size_label,
                        "color": color,
                        "drawer_drill": drawer_drill,
                        "side_type": side_type,
                        "hardware_type": hardware_type,
                        "edge": parsed_edge or edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def build_raw_takarolap_rows() -> list[dict]:
        """Collect raw cover-panel rows before aggregation."""
        return []

        def is_boundary(token: str) -> bool:
            """Return whether is boundary is true."""
            clean_token = clean_text(token)
            folded_token = folded(clean_token)
            return (
                folded_token.startswith("takarolap as")
                or folded_token.startswith("as takarosav")
                or folded_token == "also oldal"
                or folded_token.startswith("vegzaro")
                or folded_token.startswith("kamra")
                or folded_token == "felso oldal"
                or clean_token.startswith("Oldal ")
                or bool(re.fullmatch(r"[12]-es\s+als.*", folded_token))
                or bool(re.fullmatch(r"[12]-es\s+fels.*", folded_token))
            )

        raw_rows: list[dict] = []
        for page_number, lines in enumerate(pages, start=1):
            index = 0
            while index < len(lines):
                token = clean_text(lines[index])
                folded_token = folded(token)
                if not folded_token.startswith("takarolap as"):
                    index += 1
                    continue

                source_name = token
                cursor = index + 1
                if cursor < len(lines):
                    maybe_suffix = clean_text(lines[cursor])
                    if folded(maybe_suffix) == "165 melle":
                        source_name = clean_text(f"{token} {maybe_suffix}")
                        cursor += 1

                if cursor + 4 >= len(lines):
                    index += 1
                    continue

                size_tokens = [clean_text(lines[cursor + offset]) for offset in range(0, 5)]
                if not (
                    size_tokens[0].isdigit()
                    and size_tokens[1].lower() == "x"
                    and size_tokens[2].isdigit()
                    and size_tokens[3].lower() == "x"
                    and size_tokens[4].isdigit()
                ):
                    index += 1
                    continue
                size_label = " ".join(size_tokens)
                cursor += 5

                tail_tokens: list[str] = []
                while cursor < len(lines):
                    next_token = clean_text(lines[cursor])
                    if tail_tokens and is_boundary(next_token):
                        break
                    tail_tokens.append(next_token)
                    cursor += 1

                if len(tail_tokens) < 2:
                    index = max(index + 1, cursor)
                    continue

                qty_index = -1
                for pos in range(len(tail_tokens) - 1, -1, -1):
                    if re.fullmatch(r"-?\d+", clean_text(tail_tokens[pos])):
                        qty_index = pos
                        break
                if qty_index <= 0:
                    index = cursor
                    continue

                quantity = int(clean_text(tail_tokens[qty_index]))
                edge = clean_text(tail_tokens[qty_index - 1]) or "-"
                payload_tokens = [clean_text(item) for item in tail_tokens[: qty_index - 1] if clean_text(item)]
                if not payload_tokens:
                    index = cursor
                    continue

                detail_start = len(payload_tokens)
                for pos, item in enumerate(payload_tokens):
                    if folded(item).startswith("normal"):
                        detail_start = pos
                        break
                color = clean_text(" ".join(payload_tokens[:detail_start])) if detail_start > 0 else clean_text(" ".join(payload_tokens))
                detail = clean_text(" ".join(payload_tokens[detail_start:])) if detail_start < len(payload_tokens) else ""

                row_id = hashlib.sha1(
                    f"cnc-raw-takarolap|{production_number}|{page_number}|{index}|{size_label}|{color}|{quantity}".encode("utf-8")
                ).hexdigest()[:16]
                raw_rows.append(
                    {
                        "row_id": row_id,
                        "state_key": _manufacturing_state_key(production_number, row_id),
                        "production_number": _manufacturing_normalize_number(production_number),
                        "name": "Takarólap AS",
                        "source_name": source_name,
                        "size": size_label,
                        "color": color,
                        "drawer_drill": "",
                        "side_type": "",
                        "hardware_type": "",
                        "edge": edge,
                        "quantity": quantity,
                        "detail": detail,
                        "columnLayout": "cnc-lower",
                        "isMuted": False,
                    }
                )
                index = cursor
        return raw_rows

    def is_fvz_row(row: dict) -> bool:
        """Return whether is fvz row is true."""
        combined = " ".join(
            [
                folded(row.get("name")),
                folded(row.get("source_name")),
                folded(row.get("color")),
                folded(row.get("side_type")),
                folded(row.get("hardware_type")),
                folded(row.get("detail")),
            ]
        )
        return "fvz" in combined

    def is_avz_lower_row(row: dict) -> bool:
        """Return whether is avz lower row is true."""
        combined = " ".join(
            [
                folded(row.get("side_type")),
                folded(row.get("drawer_drill")),
                folded(row.get("detail")),
            ]
        )
        return bool(re.search(r"\bavz\b", combined))

    box_avz_source_rows = [row for row in lower_rows if is_avz_lower_row(row)]
    box_avz_ids = {str(row.get("row_id", "")) for row in box_avz_source_rows}
    box_avz_rows = aggregate_lower_rows(
        box_avz_source_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )

    box1_source_rows = [
        row for row in lower_rows
        if (
            (
                is_normal_also_row(row)
                and clean_text(row.get("size")) == "724 x 505 x 18"
            )
            or is_box1_mergeable_boxos_teleszkop_row(row)
        )
        and str(row.get("row_id", "")) not in box_avz_ids
    ]
    box1_extra_rows = build_raw_boxos_teleszkop_rows()
    box1_display_rows = (
        build_raw_normal_also_box_rows()
        or [
            clone_row(row, side_type="Normáls alsó")
            if is_box1_mergeable_boxos_teleszkop_row(row)
            else row
            for row in box1_source_rows
        ]
    ) + box1_extra_rows
    box1_rows = aggregate_lower_rows(
        box1_display_rows,
        ("name", "size", "color", "side_type"),
        hide_subtitle=True,
    )
    box1_rows.sort(key=lambda row: (folded(row.get("color")), folded(row.get("name"))))
    box1_ids = {str(row.get("row_id", "")) for row in box1_source_rows}
    if using_xml_cnc_source and box1_extra_rows:
        box1_ids.update(
            str(row.get("row_id", ""))
            for row in lower_rows
            if is_boxos_teleszkop_row(row)
        )
    box2_source_rows = [
        row for row in lower_rows
        if (is_boxos_box_hettich_row(row) or is_kinga_anna_teleszkop_row(row))
        and str(row.get("row_id", "")) not in box_avz_ids
    ]
    kinga_anna_teleszkop_rows = [row for row in box2_source_rows if is_kinga_anna_teleszkop_row(row)]
    boxos_source_rows = [row for row in box2_source_rows if not is_kinga_anna_teleszkop_row(row)]
    raw_boxos_rows = build_raw_boxos_box_rows()
    box2_display_rows = raw_boxos_rows or boxos_source_rows
    box2_rows = aggregate_lower_rows(
        box2_display_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    box2_rows.extend(
        aggregate_kinga_anna_fiokos_rows(kinga_anna_teleszkop_rows)
    )
    box2_ids = {str(row.get("row_id", "")) for row in box2_source_rows}
    box3_rows = [
        row for row in lower_rows
        if row.get("size") == "824 x 505 x 18"
        and normalize_side_type(row.get("side_type")) in {"normals also", "aaf fiokos ajtos", "af 1+2 fiokos"}
        and str(row.get("row_id", "")) not in box_avz_ids
        and str(row.get("row_id", "")) not in box1_ids
        and str(row.get("row_id", "")) not in box2_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and not is_fvz_row(row)
    ]
    box3_ids = {str(row.get("row_id", "")) for row in box3_rows}
    box3_display_rows = build_raw_kinga_anna_box_rows() or box3_rows
    box3_rows = [dict(row) for row in box3_display_rows if isinstance(row, dict)]
    box3_rows = aggregate_kinga_anna_fiokos_rows(box3_rows)
    box_fvz_source_rows = [
        row for row in lower_rows
        if is_fvz_row(row)
        and str(row.get("row_id", "")) not in box_avz_ids
        and str(row.get("row_id", "")) not in box1_ids
        and str(row.get("row_id", "")) not in box2_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and not is_as_takarosav_row(row)
    ]
    box_fvz_ids = {str(row.get("row_id", "")) for row in box_fvz_source_rows}
    box_fvz_rows = aggregate_lower_rows(
        box_fvz_source_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    box4_source_rows = [
        row for row in lower_rows
        if str(row.get("row_id", "")) not in box_avz_ids and str(row.get("row_id", "")) not in box1_ids and str(row.get("row_id", "")) not in box2_ids and str(row.get("row_id", "")) not in box3_ids
        and not is_fvz_row(row)
        and not is_as_takarosav_row(row)
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and normalize_side_type(row.get("side_type")) in lower_box_order
    ]
    box4_ids = {str(row.get("row_id", "")) for row in box4_source_rows}
    box4_display_rows = build_raw_egyebek_box_rows() or box4_source_rows
    box4_rows = aggregate_lower_rows(
        box4_display_rows,
        ("name", "size", "color", "drawer_drill", "side_type", "edge"),
    )
    for row in box4_rows:
        side_norm = normalize_side_type(row.get("side_type"))
        detail_folded = folded(row.get("detail"))
        source_folded = folded(row.get("source_name"))
        if side_norm == "ar golyos tel." or "ar golyos" in detail_folded or "ar golyos" in source_folded:
            row["side_type"] = "AR golyós tel."
        elif side_norm == "ar":
            row["side_type"] = "AR"
    box5_rows = [
        row for row in lower_rows
        if str(row.get("row_id", "")) not in box_avz_ids
        and is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and not is_kamra_teto_fenek_row(row)
    ]
    box5_ids = {str(row.get("row_id", "")) for row in box5_rows}
    box5_teto_fenek_rows = [
        row for row in lower_rows
        if str(row.get("row_id", "")) not in box_avz_ids
        and is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
        and is_kamra_teto_fenek_row(row)
    ]
    box5_teto_fenek_ids = {str(row.get("row_id", "")) for row in box5_teto_fenek_rows}
    box6_source_rows = [
        row for row in lower_rows
        if is_as_takarosav_row(row)
        and str(row.get("row_id", "")) not in box_avz_ids
        and not is_kamra_row(row.get("name", ""), row.get("color", ""), row.get("side_type", ""))
    ]
    box6_ids = {str(row.get("row_id", "")) for row in box6_source_rows}
    box6_rows = list(box6_source_rows)
    box6_takarolap_rows = [row for row in box6_rows if is_takarolap_as_row(row)]
    raw_takarolap_rows = build_raw_takarolap_rows()
    if raw_takarolap_rows:
        box6_takarolap_rows = aggregate_lower_rows(
            raw_takarolap_rows,
            ("name", "size", "color", "drawer_drill", "side_type", "edge"),
        )
    box6_rows = [row for row in box6_rows if not is_takarolap_as_row(row)]
    categorized_lower_ids = {
        row_id
        for row_id in (
            box_avz_ids
            | box1_ids
            | box2_ids
            | box3_ids
            | box_fvz_ids
            | box4_ids
            | box5_ids
            | box5_teto_fenek_ids
            | box6_ids
        )
        if row_id
    }
    uncategorized_lower_rows = [
        row for row in lower_rows
        if using_xml_cnc_source
        and str(row.get("row_id", ""))
        and str(row.get("row_id", "")) not in categorized_lower_ids
    ]
    for row in uncategorized_lower_rows:
        row["hideSubtitle"] = True
    uncategorized_also_oldal_rows = [
        row
        for row in uncategorized_lower_rows
        if folded(row.get("name")) == "also oldal"
    ]
    if uncategorized_also_oldal_rows:
        box4_rows.extend(dict(row) for row in uncategorized_also_oldal_rows)
        moved_also_oldal_ids = {str(row.get("row_id", "")) for row in uncategorized_also_oldal_rows}
        uncategorized_lower_rows = [
            row
            for row in uncategorized_lower_rows
            if str(row.get("row_id", "")) not in moved_also_oldal_ids
        ]

    box2_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            clean_text(row.get("name")),
        )
    )
    # Kinga/Anna: keep original source row order, no merge and no additional sorting.
    box4_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            lower_box_order.get(normalize_side_type(row.get("side_type")), 99),
            1 if "ar goly" in folded(row.get("side_type")) else 0,
            normalize_side_type(row.get("side_type")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
        )
    )
    box_fvz_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box_avz_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box5_rows.sort(
        key=lambda row: (
            0 if clean_text(row.get("size")) != "2017 x 550 x 18" else 1,
            clean_text(row.get("color")),
            0 if "n?tos" in folded(row.get("name")) and "nem n?tos" not in folded(row.get("name")) else 1,
            {"nincs": 0, "teleszkop": 1, "box hettich": 2}.get(folded(row.get("drawer_drill")), 9),
            clean_text(row.get("side_type")),
            clean_text(row.get("hardware_type")),
            clean_text(row.get("name")),
            size_parts(row.get("size")),
        )
    )
    box5_teto_fenek_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
            clean_text(row.get("hardware_type")),
        )
    )
    box6_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )
    box6_takarolap_rows.sort(
        key=lambda row: (
            clean_text(row.get("color")),
            size_parts(row.get("size")),
            clean_text(row.get("name")),
            clean_text(row.get("side_type")),
        )
    )

    set_kinga_anna_subtitles(box3_rows)
    for rows_without_subtitles in (box1_rows, box2_rows, box_fvz_rows, box_avz_rows, box4_rows):
        hide_lower_subtitles(rows_without_subtitles)

    add_lower_section("Normáls alsó · 724 x 505 x 18", box1_rows, "box1")
    add_lower_section("Boxosok", box2_rows, "box2")
    add_lower_section("Kinga/Anna", box3_rows, "box3")
    add_lower_section("FVZ", box_fvz_rows, "box-fvz")
    add_lower_section("Alsó Végzáró", box_avz_rows, "box-avz")
    add_lower_section("Egyebek", box4_rows, "box4")
    add_lower_section("Kamra tet\u0151-fen\u00e9k", box5_teto_fenek_rows, "box5-teto-fenek")
    add_lower_section("Kamrák", box5_rows, "box5")
    add_lower_section("AS takarósávok · Takarólap AS, 165 mellé", box6_takarolap_rows, "box6-takarolap")
    add_lower_section("AS takarósávok", box6_rows, "box6")

    def upper_combined_text(row: dict) -> str:
        """Return combined upper-row text used for classification."""
        return " ".join(
            [
                folded(row.get("name")),
                folded(row.get("color")),
                folded(row.get("hardware_type")),
                folded(row.get("side_type")),
                folded(row.get("detail")),
            ]
        )

    def is_upper_normal_or_fny(row: dict) -> bool:
        """Return whether is upper normal or fny is true."""
        combined = upper_combined_text(row)
        return "normal" in combined or "fny" in combined

    def is_upper_felnyilo_group(row: dict) -> bool:
        """Return whether is upper felnyilo group is true."""
        combined = upper_combined_text(row)
        return (
            "felnyilo" in combined
            or "f_2a" in combined
            or "f2a" in combined
            or "ffm" in combined
            or "ef60" in combined
        )

    def upper_felnyilo_type_sort_value(row: dict) -> str:
        """Return the sort rank for felnyilo upper types."""
        combined = upper_combined_text(row)
        side_type = folded(row.get("side_type"))
        hardware_type = folded(row.get("hardware_type"))
        values = (side_type, hardware_type, combined)
        if any("ef60" in value for value in values):
            return "ef60"
        if any("f2a" in value or "f_2a" in value for value in values):
            return "f2a"
        if any("felnyilo" in value for value in values):
            return "felnyilo"
        if any("ffm" in value for value in values):
            return "ffm"
        return side_type or hardware_type or combined

    def is_upper_zille(row: dict) -> bool:
        """Return whether is upper zille is true."""
        combined = upper_combined_text(row)
        return "zille" in combined or "fuf" in combined or "fzn" in combined

    def is_upper_sarok(row: dict) -> bool:
        """Return whether is upper sarok is true."""
        combined = upper_combined_text(row)
        size = clean_text(row.get("size"))
        return (
            "sarok" in combined
            or (size == "360 x 330 x 18" and ("fmf" in combined or "fmfs" in combined or "fkf" in combined))
            or (size == "360 x 550 x 18" and ("fmf" in combined or "fmfs" in combined or "fkf" in combined))
        )

    def is_upper_595_eft(row: dict) -> bool:
        """Return whether is upper 595 eft is true."""
        return clean_text(row.get("size")).startswith("595 x ") and "eft" in upper_combined_text(row)

    def is_upper_595(row: dict) -> bool:
        """Return whether is upper 595 size is true."""
        return clean_text(row.get("size")).startswith("595 x ")

    def is_upper_any_eft(row: dict) -> bool:
        """Return whether is upper any eft is true."""
        return "eft" in upper_combined_text(row) or folded(row.get("name")) == "eft fenek excenteres"

    def is_upper_680(row: dict) -> bool:
        """Return whether is upper 680 is true."""
        return clean_text(row.get("size")).startswith("680 x ")

    def is_upper_360(row: dict) -> bool:
        """Return whether is upper 360 is true."""
        return clean_text(row.get("size")).startswith("360 x ")

    def is_upper_mart(row: dict) -> bool:
        """Return whether an upper row name/detail contains mart."""
        return "mart" in upper_combined_text(row)

    def aggregate_upper_rows(rows: list[dict]) -> list[dict]:
        """Aggregate upper-cabinet rows by display-relevant fields."""
        unmerged_rows: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["_postOverrideMergeFields"] = [
                "name", "size", "color", "hardware_type", "side_type", "edge"
            ]
            item["_postOverrideMergeKind"] = "upper-box"
            unmerged_rows.append(item)
        return unmerged_rows

        grouped: dict[tuple[str, ...], dict] = {}
        for row in rows:
            group_key = (
                clean_text(row.get("name")),
                clean_text(row.get("size")),
                clean_text(row.get("color")),
                clean_text(row.get("hardware_type")),
                clean_text(row.get("side_type")),
                clean_text(row.get("edge")) or "-",
            )
            existing = grouped.get(group_key)
            if existing is None:
                merged_id = hashlib.sha1(
                    f"cnc-upper-box|{production_number}|{'|'.join(group_key)}".encode("utf-8")
                ).hexdigest()
                source_row_ids = [
                    source_row_id
                    for source_row_id in (
                        str(source_id).strip()
                        for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                    )
                    if source_row_id
                ]
                grouped[group_key] = {
                    "row_id": merged_id,
                    "state_key": _manufacturing_state_key(production_number, merged_id),
                    "production_number": _manufacturing_normalize_number(production_number),
                    "name": clean_text(row.get("name")),
                    "size": clean_text(row.get("size")),
                    "color": clean_text(row.get("color")),
                    "hardware_type": clean_text(row.get("hardware_type")),
                    "side_type": clean_text(row.get("side_type")),
                    "edge": clean_text(row.get("edge")) or "-",
                    "quantity": int(row.get("quantity", 0) or 0),
                    "detail": clean_text(row.get("detail")),
                    "columnLayout": "cnc-upper",
                    "markSizeBlack": bool(row.get("markSizeBlack")),
                    "markSideTypeBlack": "fkf nutos tiplis" in folded(row.get("side_type")),
                    "sourceRowIds": source_row_ids,
                }
            else:
                existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
                existing["markSizeBlack"] = bool(existing.get("markSizeBlack")) or bool(row.get("markSizeBlack"))
                source_row_ids = list(existing.get("sourceRowIds", []))
                for source_row_id in (
                    str(source_id).strip()
                    for source_id in (row.get("sourceRowIds") or [row.get("row_id", "")])
                ):
                    if source_row_id and source_row_id not in source_row_ids:
                        source_row_ids.append(source_row_id)
                existing["sourceRowIds"] = source_row_ids
        return list(grouped.values())

    def sort_upper_rows(rows: list[dict], mode: str) -> list[dict]:
        """Sort upper rows by type, size, color, and source order."""
        if mode == "normal":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    0 if "normal" in upper_combined_text(row) else 1,
                    0 if "fny" in upper_combined_text(row) else 1,
                    size_parts(row.get("size")),
                )
            )
        elif mode == "felnyilo":
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    upper_felnyilo_type_sort_value(row),
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                    clean_text(row.get("side_type")),
                    clean_text(row.get("name")),
                )
            )
        elif mode == "rack1-other":
            rows.sort(
                key=lambda row: (
                    0 if is_upper_595(row) else 1,
                    0 if is_upper_680(row) else 1,
                    0 if is_upper_360(row) else 1,
                    clean_text(row.get("color")),
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        elif mode == "rack2-other":
            rows.sort(
                key=lambda row: (
                    1 if is_upper_fuf_or_fzn(row) else 0,
                    0 if "fuf" in upper_combined_text(row) or "füf" in upper_combined_text(row) else 1,
                    clean_text(row.get("color")),
                    0 if clean_text(row.get("size")).startswith("595 x ") else 1,
                    0 if is_upper_360_special(row) else 1,
                    0 if is_upper_680(row) else 1,
                    0 if is_upper_zille(row) else 1,
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        elif mode == "sarok":
            rows.sort(
                key=lambda row: (
                    0 if is_upper_sarok(row) else 1,
                    0 if clean_text(row.get("size")) == "360 x 290 x 18" else 1,
                    1 if clean_text(row.get("size")) == "360 x 550 x 18" else 0,
                    clean_text(row.get("color")),
                    clean_text(row.get("hardware_type")),
                )
            )
        else:
            rows.sort(
                key=lambda row: (
                    clean_text(row.get("color")),
                    size_parts(row.get("size")),
                    clean_text(row.get("hardware_type")),
                )
            )
        return rows

    upper_sections = []

    def add_upper_section(label: str, rows: list[dict], key_suffix: str, sort_mode: str) -> None:
        """Append an upper-cabinet section when it has rows."""
        if not rows:
            return
        section_rows = sort_upper_rows(aggregate_upper_rows(rows), sort_mode)
        for section_row in section_rows:
            base_row_id = str(section_row.get("row_id", "")).strip()
            if not base_row_id:
                continue
            scoped_row_id = hashlib.sha1(
                f"cnc-upper-section|{production_number}|{key_suffix}|{base_row_id}".encode("utf-8")
            ).hexdigest()
            section_row["row_id"] = scoped_row_id
            section_row["state_key"] = _manufacturing_state_key(production_number, scoped_row_id)
            section_row["hideSubtitle"] = True
        upper_sections.append(
            {
                "key": f"cnc-felso::{key_suffix}",
                "label": label,
                "rows": section_rows,
                "columnLayout": "cnc-upper",
            }
        )

    def upper_source_group(row: dict) -> str:
        """Classify an upper row into its output section group."""
        return clean_text(row.get("sourceGroup"))

    def is_upper_zille_target(row: dict) -> bool:
        """Return whether is upper zille target is true."""
        combined = upper_combined_text(row)
        return "zille" in combined and ("fuf" in combined or "fzn" in combined or "f\u00fcf" in combined)

    def is_upper_fuf_or_fzn(row: dict) -> bool:
        """Return whether is upper fuf or fzn is true."""
        combined = upper_combined_text(row)
        return "fzn" in combined or "fuf" in combined or "f\u00fcf" in combined

    def is_upper_360_special(row: dict) -> bool:
        """Return whether is upper 360 special is true."""
        if not is_upper_360(row):
            return False
        combined = upper_combined_text(row)
        return "fmf" in combined or "fmfs" in combined or "fkf" in combined

    def is_upper_360_fmf(row: dict) -> bool:
        """Return whether is upper 360 fmf is true."""
        if not is_upper_360(row):
            return False
        combined = upper_combined_text(row)
        return "fmf" in combined or "fmfs" in combined

    def is_upper_360_fkf(row: dict) -> bool:
        """Return whether is upper 360 fkf is true."""
        return is_upper_360(row) and "fkf" in upper_combined_text(row)

    def is_upper_sarok_bucket_size(row: dict) -> bool:
        """Return whether is upper sarok bucket size is true."""
        size_text = clean_text(row.get("size"))
        return size_text.startswith("360 x 550") or size_text.startswith("360 x 290")

    def is_upper_360x330(row: dict) -> bool:
        """Return whether is upper 360x330 is true."""
        return clean_text(row.get("size")).startswith("360 x 330")

    def upper_row_id(row: dict) -> str:
        """Build a stable row id for an upper-cabinet row."""
        return str(row.get("row_id", "")).strip()

    non_fvz_upper_rows = [row for row in upper_rows if not is_fvz_row(row)]
    vegzaro_raklap_rows = [row for row in upper_rows if is_fvz_row(row)]
    rack1_source_rows = [row for row in non_fvz_upper_rows if upper_source_group(row) == "2-es"]
    rack2_source_rows = [row for row in non_fvz_upper_rows if upper_source_group(row) == "1-es"]
    fuf_or_fzn_rows = [row for row in non_fvz_upper_rows if is_upper_fuf_or_fzn(row)]
    fuf_or_fzn_ids = {upper_row_id(row) for row in fuf_or_fzn_rows}
    zille_rows = [row for row in non_fvz_upper_rows if is_upper_zille_target(row) and upper_row_id(row) not in fuf_or_fzn_ids]
    rack2_fenek_rows = [
        row for row in rack2_source_rows
        if upper_row_id(row) not in fuf_or_fzn_ids
        and "fenek" in folded(row.get("name"))
    ]
    rack2_fenek_ids = {upper_row_id(row) for row in rack2_fenek_rows}
    rack1_box360_rows = [row for row in rack1_source_rows if is_upper_360x330(row)]
    rack1_box360_ids = {upper_row_id(row) for row in rack1_box360_rows}
    rack2_box360_rows = [
        row for row in rack2_source_rows
        if is_upper_360x330(row) and upper_row_id(row) not in rack2_fenek_ids
    ]
    rack2_box360_ids = {upper_row_id(row) for row in rack2_box360_rows}

    rack1_box1_rows = [
        row
        for row in rack1_source_rows
        if is_upper_normal_or_fny(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
        and not is_upper_mart(row)
        and upper_row_id(row) not in rack1_box360_ids
    ]
    rack1_box1_ids = {upper_row_id(row) for row in rack1_box1_rows}
    rack1_box2_rows = [
        row
        for row in rack1_source_rows
        if is_upper_felnyilo_group(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
        and not is_upper_mart(row)
        and upper_row_id(row) not in rack1_box360_ids
    ]
    rack1_box2_ids = {upper_row_id(row) for row in rack1_box2_rows}
    rack1_box3_rows = [
        row for row in rack1_source_rows
        if upper_row_id(row) not in rack1_box1_ids
        and upper_row_id(row) not in rack1_box2_ids
        and upper_row_id(row) not in fuf_or_fzn_ids
        and not is_upper_sarok(row)
    ]
    for row in rack1_box360_rows:
        if row not in rack1_box3_rows:
            rack1_box3_rows.append(row)
    rack1_box3_ids = {upper_row_id(row) for row in rack1_box3_rows}

    rack2_box1_rows = [
        row
        for row in rack2_source_rows
        if is_upper_normal_or_fny(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
        and upper_row_id(row) not in rack2_fenek_ids
    ]
    rack2_box1_ids = {upper_row_id(row) for row in rack2_box1_rows}
    rack2_box2_rows = [
        row
        for row in rack2_source_rows
        if is_upper_felnyilo_group(row)
        and not is_upper_sarok(row)
        and not is_upper_fuf_or_fzn(row)
        and upper_row_id(row) not in rack2_fenek_ids
    ]
    rack2_box2_ids = {upper_row_id(row) for row in rack2_box2_rows}
    rack2_primary_assigned_ids = {row_id for row_id in (rack2_box1_ids | rack2_box2_ids) if row_id}
    rack2_box3_rows = [
        row for row in rack2_source_rows
        if upper_row_id(row) not in rack2_primary_assigned_ids
        and upper_row_id(row) not in fuf_or_fzn_ids
        and upper_row_id(row) not in rack2_fenek_ids
        and not is_upper_360x330(row)
        and (not is_upper_sarok_bucket_size(row) or is_upper_360_fmf(row))
        and (
            clean_text(row.get("size")).startswith("595 x ")
            or is_upper_360_special(row)
            or is_upper_680(row)
        )
    ]
    all_360_fmf_rows = [
        row for row in non_fvz_upper_rows
        if is_upper_360_fmf(row) and not is_upper_360x330(row)
    ]
    for row in all_360_fmf_rows:
        if upper_row_id(row) not in rack2_fenek_ids and row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    fkf_360_rows = [
        row for row in rack2_source_rows
        if is_upper_360_fkf(row) and not is_upper_sarok_bucket_size(row)
    ]
    for row in fkf_360_rows:
        if upper_row_id(row) not in rack2_fenek_ids and row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    for row in zille_rows:
        if row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    for row in fuf_or_fzn_rows:
        if row not in rack2_box3_rows:
            rack2_box3_rows.append(row)
    rack2_box3_ids = {upper_row_id(row) for row in rack2_box3_rows}
    rack2_box4_rows = [
        row for row in non_fvz_upper_rows
        if upper_row_id(row) not in rack2_fenek_ids
        and (
            ((is_upper_sarok(row) and not is_upper_360_fmf(row)) and not is_upper_360x330(row))
            or ((is_upper_sarok_bucket_size(row) and not is_upper_360_fmf(row)) and not is_upper_360x330(row))
            or (
                upper_row_id(row) not in rack1_box1_ids
                and upper_row_id(row) not in rack1_box2_ids
                and upper_row_id(row) not in rack1_box3_ids
                and upper_row_id(row) not in rack1_box360_ids
                and upper_row_id(row) not in rack2_primary_assigned_ids
                and upper_row_id(row) not in rack2_box360_ids
                and upper_row_id(row) not in rack2_box3_ids
                and row not in zille_rows
                and upper_row_id(row) not in fuf_or_fzn_ids
            )
        )
    ]
    recovered_rack1_360_rows = [
        row for row in rack2_box4_rows
        if upper_source_group(row) == "2-es" and is_upper_360(row) and not is_upper_sarok(row) and not is_upper_360x330(row)
    ]
    for row in recovered_rack1_360_rows:
        if upper_row_id(row) not in rack1_box3_ids:
            rack1_box3_rows.append(row)
            rack1_box3_ids.add(upper_row_id(row))
    rack2_box4_rows = [
        row for row in rack2_box4_rows
        if upper_row_id(row) not in rack1_box3_ids and upper_row_id(row) not in rack2_box3_ids
    ]
    rack1_box3_rows = [row for row in rack1_box3_rows if upper_row_id(row) not in rack2_box3_ids]
    rack1_fenek_rows = [
        row for row in rack1_box3_rows
        if upper_row_id(row) not in fuf_or_fzn_ids
        and ("fenek" in folded(row.get("name")) or is_upper_mart(row))
    ]
    rack1_fenek_ids = {upper_row_id(row) for row in rack1_fenek_rows}
    rack1_box3_rows = [row for row in rack1_box3_rows if upper_row_id(row) not in rack1_fenek_ids]
    rack1_box3_ids = {upper_row_id(row) for row in rack1_box3_rows}
    upper_assigned_ids = {
        str(row.get("row_id", ""))
        for bucket in (
            rack1_box1_rows,
            rack1_box2_rows,
            rack1_box360_rows,
            rack1_fenek_rows,
            rack1_box3_rows,
            rack2_box1_rows,
            rack2_box2_rows,
            rack2_box360_rows,
            rack2_fenek_rows,
            rack2_box3_rows,
            rack2_box4_rows,
            vegzaro_raklap_rows,
        )
        for row in bucket
        if str(row.get("row_id", ""))
    }
    upper_unassigned_rows = [
        row for row in upper_rows
        if str(row.get("row_id", "")) and str(row.get("row_id", "")) not in upper_assigned_ids
    ]

    add_upper_section("2-es konyha · Normál és FNY", rack1_box1_rows, "rack1-box1", "normal")
    add_upper_section("2-es konyha · EF60 / F2A / Felnyíló / FFM", rack1_box2_rows, "rack1-box2", "felnyilo")
    add_upper_section("2-es konyha · Fenekek", rack1_fenek_rows, "rack1-fenek", "rack1-other")
    add_upper_section("2-es konyha · EFT / 360 / 680 / Egyéb", rack1_box3_rows, "rack1-box3", "rack1-other")
    add_upper_section("1-es konyha · Normál és FNY", rack2_box1_rows, "rack2-box1", "normal")
    add_upper_section("1-es konyha · EF60 / F2A / Felnyíló / FFM", rack2_box2_rows, "rack2-box2", "felnyilo")
    add_upper_section("1-es konyha · 360-as elemek", rack2_box360_rows, "rack2-box360", "default")
    add_upper_section("1-es konyha · EFT / 360 / 680 / Zille", rack2_box3_rows, "rack2-box3", "rack2-other")
    add_upper_section("1-es konyha · Sarok", rack2_box4_rows, "rack2-box4", "sarok")
    add_upper_section("1-es konyha · Fenekek", rack2_fenek_rows, "rack2-fenek", "rack2-other")
    add_upper_section("Teszt · Nem besorolt", upper_unassigned_rows, "upper-unassigned", "default")
    add_upper_section("Végzáró raklap", vegzaro_raklap_rows, "vegzaro-raklap", "default")

    upper_sections = []
    add_upper_section("2-es konyha · Normál és FNY", rack1_box1_rows, "rack1-box1", "normal")
    add_upper_section("2-es konyha · EF60 / F2A / Felnyíló / FFM", rack1_box2_rows, "rack1-box2", "felnyilo")
    add_upper_section("2-es konyha · Fenekek", rack1_fenek_rows, "rack1-fenek", "rack1-other")
    add_upper_section("2-es konyha · Minden más 2-es konyha", rack1_box3_rows, "rack1-box3", "rack1-other")
    add_upper_section("1-es konyha · Normál és FNY", rack2_box1_rows, "rack2-box1", "normal")
    add_upper_section("1-es konyha · EF60 / F2A / Felnyíló / FFM", rack2_box2_rows, "rack2-box2", "felnyilo")
    add_upper_section("1-es konyha · 360-as elemek", rack2_box360_rows, "rack2-box360", "default")
    add_upper_section("1-es konyha · 595 / 360 FMF / 680 / Zille", rack2_box3_rows, "rack2-box3", "rack2-other")
    add_upper_section("1-es konyha · Sarok és maradék", rack2_box4_rows, "rack2-box4", "sarok")
    add_upper_section("1-es konyha · Fenekek", rack2_fenek_rows, "rack2-fenek", "rack2-other")
    add_upper_section("Teszt · Nem besorolt", upper_unassigned_rows, "upper-unassigned", "default")
    add_upper_section("Végzáró raklap", vegzaro_raklap_rows, "vegzaro-raklap", "default")

    front_sections = []
    if front_rows:
        grouped_front_rows: dict[str, list[dict]] = {}
        for row in front_rows:
            grouped_front_rows.setdefault(str(row.get("fiokeloGroup", "Egyéb")), []).append(row)
        preferred_order = {"1-es": 0, "2-es": 1}
        for group_label, rows in sorted(grouped_front_rows.items(), key=lambda item: (preferred_order.get(item[0], 9), item[0])):
            rows.sort(
                key=lambda row: (
                    size_parts(row.get("size")),
                    clean_text(row.get("modelLabel")),
                    clean_text(row.get("color")),
                    clean_text(row.get("netfrontColor")),
                    clean_text(row.get("drillLabel")),
                    clean_text(row.get("drawerType")),
                )
            )
            front_sections.append(
                {
                    "key": f"cnc-front::{_manufacturing_local_slug(group_label)}",
                    "label": group_label,
                    "rows": rows,
                    "columnLayout": "cnc-fiokelo",
                }
            )

    main_sections = []
    if lower_rows:
        main_sections.append(
            {
                "key": "cnc-main::also",
                "label": "Alsó",
                "rows": lower_rows,
                "columnLayout": "cnc-lower",
            }
        )
    if upper_rows:
        main_sections.append(
            {
                "key": "cnc-main::felso",
                "label": "Felső",
                "rows": upper_rows,
                "columnLayout": "cnc-upper",
            }
        )
    if front_rows:
        main_sections.append(
            {
                "key": "cnc-main::front",
                "label": "Fiókelő fúrás",
                "rows": front_rows,
                "columnLayout": "cnc-fiokelo",
            }
        )

    row_count = sum(len(section.get("rows", [])) for section in main_sections)
    special_views = [
        {
            "key": "cnc-also",
            "label": "Alsó",
            "count": sum(len(section.get("rows", [])) for section in lower_box_sections),
            "sections": lower_box_sections,
        },
        {
            "key": "cnc-felso",
            "label": "Felső",
            "count": sum(len(section.get("rows", [])) for section in upper_sections),
            "sections": upper_sections,
        },
        {
            "key": "cnc-front",
            "label": "Fiókelő fúrás",
            "count": sum(len(section.get("rows", [])) for section in front_sections),
            "sections": front_sections,
        },
    ]

    # Preserve the XML-derived category and row order above. Only now overlay
    # admin row data, then merge rows by their final displayed values.
    saved_row_data = load_row_data(runtime_dir(), _manufacturing_normalize_number(production_number))
    normalized_saved_row_data = {str(key).casefold(): fields for key, fields in saved_row_data.items()}

    def apply_saved_row_data(row: dict) -> dict:
        item = dict(row)
        row_keys = [
            str(item.get("state_storage_key", "") or "").strip(),
            str(item.get("row_id", "") or "").strip(),
            *(
                [str(value or "").strip() for value in item.get("sourceRowIds", []) if str(value or "").strip()]
                if isinstance(item.get("sourceRowIds"), list)
                else []
            ),
        ]
        for row_key in dict.fromkeys(key for key in row_keys if key):
            candidates = [row_key]
            if row_key.endswith("::0"):
                candidates.append(row_key[:-3])
            elif row_key.count("::") >= 2:
                candidates.append(f"{row_key}::0")
            fields = next(
                (
                    saved_row_data.get(candidate) or normalized_saved_row_data.get(candidate.casefold())
                    for candidate in candidates
                    if saved_row_data.get(candidate) or normalized_saved_row_data.get(candidate.casefold())
                ),
                None,
            )
            if not fields:
                continue
            original_fields = item.setdefault("_rowDataOriginal", {})
            edited_fields = set(item.get("_rowDataEditedFields", []))
            for field, value in fields.items():
                original_value = original_fields.get(field, item.get(field, ""))
                original_fields.setdefault(field, original_value)
                item[field] = value
                if str(value) != str(original_value):
                    edited_fields.add(field)
                else:
                    edited_fields.discard(field)
            item["_rowDataEditedFields"] = sorted(edited_fields)
        return item

    def row_source_ids(row: dict) -> list[str]:
        values = row.get("sourceRowIds", []) if isinstance(row.get("sourceRowIds"), list) else []
        result = [str(value or "").strip() for value in values if str(value or "").strip()]
        fallback = str(row.get("state_storage_key", "") or row.get("row_id", "")).strip()
        if fallback and fallback not in result:
            result.append(fallback)
        return result

    def merge_rows_after_overrides(rows: list[dict], column_layout: str) -> list[dict]:
        display_fields_by_layout = {
            "cnc-lower": ("name", "size", "color", "drawer_drill", "side_type", "hardware_type", "edge"),
            "cnc-upper": ("name", "size", "color", "hardware_type", "side_type", "edge"),
        }
        display_fields = display_fields_by_layout.get(column_layout)
        prepared = [apply_saved_row_data(row) for row in rows if isinstance(row, dict)]
        if not display_fields:
            return prepared
        merged_rows: dict[tuple[str, ...], dict] = {}
        output: list[dict] = []
        for row in prepared:
            configured_fields = row.get("_postOverrideMergeFields")
            merge_fields = (
                tuple(str(field) for field in configured_fields)
                if isinstance(configured_fields, list) and configured_fields
                else display_fields
            )
            merge_kind = str(row.get("_postOverrideMergeKind", "") or "")
            merge_key = (
                merge_kind,
                *tuple(str(row.get(field, "") or "").strip() for field in merge_fields),
            )
            existing = merged_rows.get(merge_key)
            if existing is None:
                row["sourceRowIds"] = row_source_ids(row)
                row["_postOverrideMixedValues"] = {
                    field: [str(row.get(field, "") or "").strip()]
                    for field in display_fields
                    if field not in merge_fields
                }
                merged_rows[merge_key] = row
                output.append(row)
                continue
            existing["quantity"] = int(existing.get("quantity", 0) or 0) + int(row.get("quantity", 0) or 0)
            sources = list(existing.get("sourceRowIds", []))
            for source_id in row_source_ids(row):
                if source_id not in sources:
                    sources.append(source_id)
            existing["sourceRowIds"] = sources
            existing_edited = set(existing.get("_rowDataEditedFields", []))
            existing_edited.update(row.get("_rowDataEditedFields", []))
            existing["_rowDataEditedFields"] = sorted(existing_edited)
            if "detail" in row.get("_rowDataEditedFields", []):
                existing["detail"] = row.get("detail", "")
            existing_original = existing.setdefault("_rowDataOriginal", {})
            for field, value in row.get("_rowDataOriginal", {}).items():
                existing_original.setdefault(field, value)
            mixed_values = existing.setdefault("_postOverrideMixedValues", {})
            for field in display_fields:
                if field in merge_fields:
                    continue
                values = mixed_values.setdefault(field, [])
                value = str(row.get(field, "") or "").strip()
                if value not in values:
                    values.append(value)

        for row in output:
            mixed_values = row.pop("_postOverrideMixedValues", {})
            if isinstance(mixed_values, dict):
                for field, values in mixed_values.items():
                    if isinstance(values, list) and len(values) > 1:
                        row[field] = "Vegyes"
            if row.get("_postOverrideMergeKind") == "kinga-anna":
                row["side_type"] = "AF/AAF fi\u00f3kos"
            row.pop("_postOverrideMergeFields", None)
            row.pop("_postOverrideMergeKind", None)
        return output

    processed_sections: set[int] = set()
    sections_to_process = [*main_sections]
    for special_view in special_views:
        sections_to_process.extend(
            section
            for section in special_view.get("sections", [])
            if isinstance(section, dict)
        )
    for section in sections_to_process:
        section_identity = id(section)
        if section_identity in processed_sections:
            continue
        processed_sections.add(section_identity)
        section["rows"] = merge_rows_after_overrides(
            section.get("rows", []) if isinstance(section.get("rows"), list) else [],
            str(section.get("columnLayout", "")).strip(),
        )

    row_count = sum(len(section.get("rows", [])) for section in main_sections)
    for special_view in special_views:
        special_view["count"] = sum(
            len(section.get("rows", []))
            for section in special_view.get("sections", [])
            if isinstance(section, dict)
        )
    if uncategorized_lower_rows:
        special_views.append(
            {
                "key": "cnc-uncategorized-overview",
                "label": "Kategorizálatlan",
                "count": len(uncategorized_lower_rows),
                "sections": [
                    {
                        "key": "cnc-overview::uncategorized",
                        "label": "Kategorizálatlan",
                        "rows": uncategorized_lower_rows,
                        "columnLayout": "cnc-lower",
                    }
                ],
                "overviewOnly": True,
                "hideTab": True,
            }
        )
    for special_view in special_views:
        for section in special_view.get("sections", []):
            if not isinstance(section, dict) or id(section) in processed_sections:
                continue
            processed_sections.add(id(section))
            section["rows"] = merge_rows_after_overrides(
                section.get("rows", []) if isinstance(section.get("rows"), list) else [],
                str(section.get("columnLayout", "")).strip(),
            )
        special_view["count"] = sum(
            len(section.get("rows", []))
            for section in special_view.get("sections", [])
            if isinstance(section, dict)
        )
    return main_sections, row_count, special_views, cnc_source_type, cnc_source_label
