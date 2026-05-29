"""Operation-specific section builders for pantolas manufacturing papers."""

from __future__ import annotations

from ..workflow import *

def _manufacturing_pantolo_xml_sections(bundle: dict, production_number: str) -> tuple[list[dict], int, bool]:
    folder_text = str(bundle.get("folder", "") or "").strip()
    if not folder_text:
        return [], 0, False
    folder = Path(folder_text)
    xml_path = folder / "Pantolo.xml"
    if not xml_path.is_file():
        try:
            xml_path = next((path for path in folder.iterdir() if path.is_file() and path.name.lower() == "pantolo.xml"), xml_path)
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
        return (
            str(value or "")
            .strip()
            .replace("Ăµ", "Ĺ‘")
            .replace("Ă•", "Ĺ")
            .replace("Ă»", "Ĺ±")
            .replace("Ă›", "Ĺ°")
        )

    def local_name(tag: object) -> str:
        return str(tag or "").rsplit("}", 1)[-1].strip()

    def folded_ascii(value: object) -> str:
        text = unicodedata.normalize("NFKD", clean_text(value))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", text).strip().lower()

    def tag_key(tag: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", folded_ascii(local_name(tag)))

    def whole_number(value: object) -> str:
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
        number_text = whole_number(value)
        if not number_text:
            return 1
        try:
            return max(1, int(number_text))
        except ValueError:
            return 1

    def con_fields(con_element: object) -> dict[str, str]:
        fields: dict[str, str] = {}
        for child in list(con_element):
            key = tag_key(getattr(child, "tag", ""))
            if key and key not in fields:
                fields[key] = clean_text(getattr(child, "text", ""))
        return fields

    def field_value(fields: dict[str, str], *names: str) -> str:
        for name in names:
            value = fields.get(tag_key(name), "")
            if value:
                return value
        return ""

    rows: list[dict] = []
    row_index = 0
    for con_element in root.iter():
        if tag_key(getattr(con_element, "tag", "")) != "con":
            continue
        fields = con_fields(con_element)
        front_type = field_value(fields, "KorpTipPer") or "-"
        color = field_value(fields, "Szin", "Szín")
        model = field_value(fields, "Modell") or "-"
        length = whole_number(field_value(fields, "Hossz"))
        width = whole_number(field_value(fields, "Szelleseg", "Szélesség"))
        size_parts_for_label = [part for part in (length, width) if part]
        size_label = " x ".join(size_parts_for_label) if len(size_parts_for_label) == 2 else ""
        pant_type = field_value(fields, "PantTip") or "Nincs"
        handle_drill = field_value(fields, "FOG_FURAT", "Fog Furat") or "-"
        handle_type = field_value(fields, "FOG_TIP", "Fog Tip") or "-"
        opening = field_value(fields, "Nyitas", "Nyitás") or "-"
        door_type = field_value(fields, "AJTO_TIP", "Ajto Tip", "Ajtó Tip") or "-"
        quantity = quantity_value(field_value(fields, "conQuality", "conQuantity"))
        barcode = field_value(fields, "Barcode") or f"PANTXML-{row_index + 1:04d}"
        detail_tail = " ".join(part for part in (handle_drill, handle_type, opening, door_type) if part and part != "-").strip()
        detail = f"Front típus: {front_type} · {pant_type}"
        if detail_tail:
            detail = f"{detail} · {detail_tail}"
        row_index += 1
        row_id = hashlib.sha1(
            f"pantolo-xml|{production_number}|{row_index}|{barcode}|{front_type}|{color}|{model}|{size_label}|{pant_type}|{handle_drill}|{handle_type}|{opening}|{door_type}|{quantity}".encode("utf-8")
        ).hexdigest()[:16]
        rows.append(
            {
                "row_id": row_id,
                "state_key": _manufacturing_state_key(production_number, row_id),
                "production_number": _manufacturing_normalize_number(production_number),
                "name": model,
                "source_name": model,
                "detail": detail,
                "size": size_label,
                "color": color,
                "edge": "-",
                "quantity": quantity,
                "code": barcode,
                "doc_key": "pantolo",
                "section_key": "pantolo",
                "section_label": "Pántoló",
                "page_number": 1,
                **_manufacturing_xml_state_fields(production_number, "pantolo", barcode),
            }
        )

    if not rows:
        return [], 0, True
    return [
        {
            "key": "pantolo::xml",
            "label": "Pántoló",
            "rows": rows,
        }
    ], len(rows), True

def _manufacturing_pantolo_sections(bundle: dict, production_number: str) -> tuple[list[dict], int]:
    raw_sections, _, xml_pantolo_available = _manufacturing_pantolo_xml_sections(bundle, production_number)
    if not xml_pantolo_available:
        raw_sections, _ = _manufacturing_document_sections(
            bundle,
            production_number,
            ("pantolo",),
            include_source_prefix=False,
        )

    def clean_text(value: object) -> str:
        return str(value or "").strip()

    def folded(value: object) -> str:
        text = clean_text(value).lower()
        for source, target in (
            ("á", "a"),
            ("é", "e"),
            ("í", "i"),
            ("ó", "o"),
            ("ö", "o"),
            ("ő", "o"),
            ("ú", "u"),
            ("ü", "u"),
            ("ű", "u"),
            ("Ăˇ", "a"),
            ("Ă©", "e"),
            ("Ă­", "i"),
            ("Ăł", "o"),
            ("Ă¶", "o"),
            ("Ĺ‘", "o"),
            ("Ăş", "u"),
            ("ĂĽ", "u"),
            ("Ĺ±", "u"),
            ("Ăµ", "o"),
            ("Ă»", "u"),
            ("õ", "o"),
            ("û", "u"),
        ):
            text = text.replace(source, target)
        return text

    opening_tokens = {
        "bal": "Bal",
        "balos": "Balos",
        "jobb": "Jobb",
        "jobbos": "Jobbos",
        "nincs": "Nincs",
        "felnyilo": "Felnyíló",
        "felnyíló": "Felnyíló",
    }

    def normalize_token(token: object) -> str:
        return folded(str(token or "").strip().strip(".,;:|/_-()[]{}"))

    def is_nincs_token(token: object) -> bool:
        return normalize_token(token) == "nincs"

    def normalize_nincs_text(value: object) -> str:
        text = clean_text(value)
        if not text:
            return ""
        tokens = [clean_text(part) for part in text.split() if clean_text(part)]
        if not tokens:
            return ""
        if all(is_nincs_token(part) for part in tokens):
            return "Nincs"
        if len(tokens) >= 2 and is_nincs_token(tokens[0]) and is_nincs_token(tokens[1]):
            tail = " ".join(tokens[2:]).strip()
            return f"Nincs {tail}".strip()
        return text

    def strip_leading_nincs(value: object) -> str:
        text = normalize_nincs_text(value)
        while text and normalize_token(text.split(" ", 1)[0]) == "nincs" and " " in text:
            text = clean_text(text.split(" ", 1)[1])
        return text or "Nincs"

    def normalize_pant_label(value: object) -> str:
        label = clean_text(value)
        if not label:
            return "Nincs"
        folded_label = folded(label)
        folded_compact = re.sub(r"\s+", " ", folded_label).strip()
        # OCR variánsok: "ráüt.165°-os klipp", "raut 165 klipp", stb.
        if "165" in folded_compact and "klipp" in folded_compact:
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact in {"raut", "raut.", "ráüt", "ráüt."}:
            return "Ráüt."
        if folded_compact.startswith("raut.tip") or folded_compact.startswith("ráüt.tip"):
            return "Ráüt.tip."
        if folded_compact.startswith("csill. raut. 165") or folded_compact.startswith("csill. ráüt. 165"):
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact.startswith("csill.raut.165") or folded_compact.startswith("csill.ráüt.165"):
            return "Csill. ráüt. 165°-os klipp"
        if folded_compact.startswith("csill.raut") or folded_compact.startswith("csill.ráüt"):
            return "Csill.ráüt."
        if folded_compact.startswith("raut.csill. 3d-s") or folded_compact.startswith("ráüt.csill. 3d-s"):
            return "Ráüt.csill. 3D-s"
        return label

    def canonical_pantolo_color(value: object) -> tuple[str, bool]:
        raw = re.sub(r"\s+", " ", clean_text(value)).strip()
        if not raw:
            return "-", False
        tokens = [clean_text(part) for part in raw.split() if clean_text(part)]
        if not tokens:
            return "-", False
        had_hutos = False
        filtered: list[str] = []
        for token in tokens:
            if normalize_token(token) == "hutos":
                had_hutos = True
                continue
            filtered.append(token)
        final_text = re.sub(r"\s+", " ", " ".join(filtered)).strip() or raw
        return final_text, had_hutos

    def strip_model_prefix_from_color(color_value: object, model_value: object) -> str:
        color_text = clean_text(color_value)
        model_text = clean_text(model_value)
        if not color_text or not model_text:
            return color_text
        color_fold = folded(color_text)
        model_fold = folded(model_text)
        color_parts = [normalize_token(part) for part in color_fold.split() if normalize_token(part)]
        if not color_parts:
            return color_text
        if color_parts[0] == normalize_token(model_fold):
            original_parts = [clean_text(part) for part in color_text.split() if clean_text(part)]
            if len(original_parts) >= 2:
                stripped = " ".join(original_parts[1:]).strip()
                if stripped:
                    return stripped
        if color_fold.startswith(model_fold + " "):
            stripped = color_text[len(model_text):].strip()
            if stripped:
                return stripped
        return color_text

    def is_generic_pantolo_color(value: object) -> bool:
        color = folded(clean_text(value))
        if not color or color == "-":
            return True
        generic_tokens = {
            "folias",
            "fóliás",
            "matt",
            "sm",
            "mf",
        }
        parts = [normalize_token(part) for part in color.split() if normalize_token(part)]
        if not parts:
            return True
        if len(parts) == 1 and parts[0] in generic_tokens:
            return True
        return False

    def normalize_handle_type(drill_value: object, handle_value: object) -> str:
        handle = normalize_nincs_text(handle_value)
        if not handle:
            return "-"
        drill_norm = normalize_token(drill_value)
        parts = [clean_text(part) for part in handle.split() if clean_text(part)]
        if not parts:
            return "-"
        # OCR/parse csúszás esetén: "Fúrva Szabina fekete" ne maradjon a fogantyú típus elején,
        # ha a furat oszlop már "Nincs".
        if drill_norm == "nincs":
            while parts and normalize_token(parts[0]) in {"furva", "nincs"}:
                parts = parts[1:]
        return " ".join(parts).strip() or "Nincs"

    def parse_front_type(detail_text: object) -> tuple[str, list[str]]:
        detail = clean_text(detail_text)
        parts = [clean_text(part) for part in re.split(r"\s*(?:Â·|·)\s*", detail) if clean_text(part)]
        front_type = ""
        if parts and folded(parts[0]).startswith("front tipus:"):
            front_type = clean_text(parts[0].split(":", 1)[1] if ":" in parts[0] else parts[0].replace("Front tipus", ""))
            parts = parts[1:]
        return front_type or "-", parts

    drill_tokens = {"furva", "fúrva", "nincs"}

    def parse_tail_fields(parts: list[str]) -> tuple[str, str, str, str]:
        if not parts:
            return "-", "-", "-", "-"
        tail_tokens: list[str] = []
        for piece in parts:
            tail_tokens.extend([token for token in clean_text(piece).split() if token])
        tokens = tail_tokens
        if not tokens:
            return "-", "-", "-", "-"
        lowered = [normalize_token(token) for token in tokens]

        drill_index = -1
        for probe in range(min(len(tokens), 4)):
            if lowered[probe] in drill_tokens:
                drill_index = probe
                break
        if drill_index == -1:
            for probe, token in enumerate(lowered):
                if token in drill_tokens:
                    drill_index = probe
                    break

        drill = "-"
        remaining: list[str]
        if drill_index == -1:
            remaining = tokens
        else:
            drill_norm = lowered[drill_index]
            drill = "Fúrva" if drill_norm == "furva" else "Nincs"
            remaining = tokens[drill_index + 1 :]

        # OCR/parse zaj: "Nincs Nincs Balos FSL" jellegű soroknál az első
        # "Nincs" nem nyitásirány, csak töltelék token a furat után.
        # Ilyenkor a nyitásirány valójában a következő token (Balos/Jobb/Bal...).
        if drill == "Nincs":
            while (
                len(remaining) >= 2
                and normalize_token(remaining[0]) == "nincs"
                and normalize_token(remaining[1]) in opening_tokens
                and normalize_token(remaining[1]) != "nincs"
            ):
                remaining = remaining[1:]

        if not remaining:
            return drill, "-", "-", "-"

        opening_index = -1
        opening_label = "-"
        for index, token in enumerate(remaining):
            normalized = normalize_token(token)
            if normalized in opening_tokens:
                opening_index = index
                opening_label = opening_tokens[normalized]
                break

        if opening_index == -1:
            handle_type = normalize_handle_type(drill, " ".join(remaining)) or "-"
            if normalize_token(handle_type) == "nincs":
                return drill, "Nincs", "Nincs", "Nincs"
            return drill, handle_type, "-", "-"

        handle_type = normalize_handle_type(drill, " ".join(remaining[:opening_index])) or "-"
        door_type = normalize_nincs_text(" ".join(remaining[opening_index + 1 :])) or "-"
        if door_type and normalize_token(door_type.split(" ", 1)[0]) == "nincs" and " " in door_type:
            door_type = clean_text(door_type.split(" ", 1)[1]) or "Nincs"
        if normalize_token(door_type) == "nincs":
            door_type = "Nincs"
        if handle_type == "Nincs Nincs":
            handle_type = "Nincs"
        return drill, handle_type, opening_label, door_type

    grouped_sections: dict[str, dict] = {}
    grouped_order: list[str] = []
    row_count = 0
    last_valid_color_by_front_model: dict[tuple[str, str], str] = {}
    last_valid_color_by_front: dict[str, str] = {}
    unresolved_rows_by_front_model: dict[tuple[str, str], list[dict]] = {}

    for section in raw_sections:
        for raw_row in section.get("rows", []):
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            model_label = clean_text(row.get("name")) or "-"
            color, _had_hutos_in_color = canonical_pantolo_color(row.get("color"))
            color = strip_model_prefix_from_color(color, model_label)
            size_label = clean_text(row.get("size")) or "-"
            quantity_value = int(row.get("quantity") or 0)
            front_type, tail_parts = parse_front_type(row.get("detail"))
            front_type = clean_text(front_type) or "-"
            model_label = clean_text(row.get("name")) or "-"
            color_key = (front_type, model_label)
            if is_generic_pantolo_color(color):
                fallback_color = last_valid_color_by_front_model.get(color_key)
                if not fallback_color:
                    fallback_color = last_valid_color_by_front.get(front_type)
                if fallback_color:
                    color = fallback_color
                else:
                    color = "-"
            else:
                last_valid_color_by_front_model[color_key] = color
                last_valid_color_by_front[front_type] = color
            first_tail = clean_text(tail_parts[0]) if tail_parts else ""
            first_tail_token = clean_text(first_tail.split(" ", 1)[0]) if first_tail else ""
            first_tail_norm = normalize_token(first_tail_token)
            if first_tail_norm in drill_tokens:
                if first_tail_norm == "nincs":
                    # "Nincs · Fúrva ..." mintánál az első "Nincs" a pánt oszlophoz tartozik,
                    # a furatot a következő rész adja.
                    next_token_norm = ""
                    if len(tail_parts) > 1:
                        next_token = clean_text(tail_parts[1]).split(" ", 1)[0]
                        next_token_norm = normalize_token(next_token)
                    if next_token_norm in drill_tokens:
                        pant_type = "Nincs"
                        row["_pantolo_explicit_nincs"] = True
                        row["_pantolo_missing_pant"] = False
                        tail_payload = tail_parts[1:]
                    else:
                        pant_type = "Nincs"
                        row["_pantolo_explicit_nincs"] = True
                        row["_pantolo_missing_pant"] = False
                        tail_payload = tail_parts
                else:
                    # Ha "Fúrva"-val indul a sor, tipikusan hiányzik a pánttoken (parser törés),
                    # ezt inferenciával pótoljuk később.
                    pant_type = "-"
                    row["_pantolo_explicit_nincs"] = False
                    row["_pantolo_missing_pant"] = True
                    tail_payload = tail_parts
            else:
                pant_type = first_tail or "Nincs"
                row["_pantolo_explicit_nincs"] = False
                row["_pantolo_missing_pant"] = False
                tail_payload = tail_parts[1:] if len(tail_parts) > 1 else []
            drill_label, handle_type, opening_dir, door_type = parse_tail_fields(tail_payload)
            group_label = f"Front típus: {front_type} | {color} | {model_label}"
            group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            if group_key not in grouped_sections:
                grouped_sections[group_key] = {
                    "key": f"pantolo::{group_key}",
                    "label": group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                grouped_order.append(group_key)
            row["name"] = color
            row["color"] = color
            row["detail"] = ""
            row["frontType"] = front_type
            row["modelLabel"] = model_label
            row["color23"] = "-"
            row["pantType"] = normalize_pant_label(pant_type or "Nincs")
            row["handleDrill"] = drill_label or "-"
            row["handleType"] = handle_type or "-"
            row["openingDir"] = opening_dir or "-"
            row["doorType"] = door_type or "-"
            row["meValue"] = quantity_value
            row["columnLayout"] = "pantolo"
            row["hideSubtitle"] = True
            grouped_sections[group_key]["rows"].append(row)
            if color == "-":
                unresolved_rows_by_front_model.setdefault(color_key, []).append(row)
            else:
                for pending_row in unresolved_rows_by_front_model.pop(color_key, []):
                    pending_row["name"] = color
            row_count += quantity_value

    # Rebuild groups after color backfill so rows that were initially "-" can
    # move into their correct color box once the real color appears later.
    rebuilt_sections: dict[str, dict] = {}
    rebuilt_order: list[str] = []
    for group_key in grouped_order:
        section_rows = grouped_sections.get(group_key, {}).get("rows", [])
        for row in section_rows:
            if not isinstance(row, dict):
                continue
            front_type = clean_text(row.get("frontType")) or "-"
            color = clean_text(row.get("name")) or "-"
            model_label = clean_text(row.get("modelLabel")) or "-"
            rebuilt_group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            rebuilt_group_label = f"Front típus: {front_type} | {color} | {model_label}"
            if rebuilt_group_key not in rebuilt_sections:
                rebuilt_sections[rebuilt_group_key] = {
                    "key": f"pantolo::{rebuilt_group_key}",
                    "label": rebuilt_group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                rebuilt_order.append(rebuilt_group_key)
            rebuilt_sections[rebuilt_group_key]["rows"].append(row)

    sections = [rebuilt_sections[key] for key in rebuilt_order]
    all_pantolo_rows = [row for section in sections for row in section.get("rows", []) if isinstance(row, dict)]

    def apply_hutos_suffix(base_color: str, has_hutos: bool) -> str:
        color_text = clean_text(base_color) or "-"
        if color_text == "-" or not has_hutos:
            return color_text
        if "hutos" in folded(color_text):
            return color_text
        return f"{color_text} Hűtős"

    def is_bad_pantolo_section_color(row: dict) -> bool:
        color_text = clean_text(row.get("name"))
        if is_generic_pantolo_color(color_text):
            return True
        stripped = strip_model_prefix_from_color(color_text, row.get("modelLabel"))
        return clean_text(stripped) != color_text

    def resolve_nearest_section_color(index: int) -> str:
        current = all_pantolo_rows[index]
        front_type = clean_text(current.get("frontType")) or "-"
        model_label = clean_text(current.get("modelLabel")) or "-"
        previous_match: tuple[int, str] | None = None
        next_match: tuple[int, str] | None = None
        for probe in range(index - 1, -1, -1):
            candidate = all_pantolo_rows[probe]
            if clean_text(candidate.get("frontType")) != front_type:
                continue
            if clean_text(candidate.get("modelLabel")) != model_label:
                continue
            candidate_color = clean_text(candidate.get("name"))
            candidate_color = strip_model_prefix_from_color(candidate_color, candidate.get("modelLabel"))
            if is_generic_pantolo_color(candidate_color):
                continue
            previous_match = (index - probe, candidate_color)
            break
        for probe in range(index + 1, len(all_pantolo_rows)):
            candidate = all_pantolo_rows[probe]
            if clean_text(candidate.get("frontType")) != front_type:
                continue
            if clean_text(candidate.get("modelLabel")) != model_label:
                continue
            candidate_color = clean_text(candidate.get("name"))
            candidate_color = strip_model_prefix_from_color(candidate_color, candidate.get("modelLabel"))
            if is_generic_pantolo_color(candidate_color):
                continue
            next_match = (probe - index, candidate_color)
            break
        if previous_match and next_match:
            if clean_text(previous_match[1]) == clean_text(next_match[1]):
                return previous_match[1]
            return previous_match[1] if previous_match[0] <= next_match[0] else next_match[1]
        if previous_match:
            return previous_match[1]
        if next_match:
            return next_match[1]
        return "-"

    needs_color_regroup = False
    for index, row in enumerate(all_pantolo_rows):
        if not is_bad_pantolo_section_color(row):
            continue
        resolved_color = resolve_nearest_section_color(index)
        original_color, had_hutos = canonical_pantolo_color(row.get("color"))
        resolved_color = strip_model_prefix_from_color(resolved_color, row.get("modelLabel"))
        resolved_color = apply_hutos_suffix(resolved_color, had_hutos)
        if clean_text(resolved_color) and clean_text(resolved_color) != clean_text(row.get("name")):
            row["name"] = resolved_color
            row["color"] = resolved_color
            needs_color_regroup = True

    if needs_color_regroup:
        regrouped_sections: dict[str, dict] = {}
        regrouped_order: list[str] = []
        for row in all_pantolo_rows:
            front_type = clean_text(row.get("frontType")) or "-"
            color = clean_text(row.get("name")) or "-"
            model_label = clean_text(row.get("modelLabel")) or "-"
            regrouped_group_key = _manufacturing_local_slug(f"pantolo::{front_type}::{color}::{model_label}")
            regrouped_group_label = f"Front típus: {front_type} | {color} | {model_label}"
            if regrouped_group_key not in regrouped_sections:
                regrouped_sections[regrouped_group_key] = {
                    "key": f"pantolo::{regrouped_group_key}",
                    "label": regrouped_group_label,
                    "rows": [],
                    "columnLayout": "pantolo",
                }
                regrouped_order.append(regrouped_group_key)
            regrouped_sections[regrouped_group_key]["rows"].append(row)
        sections = [regrouped_sections[key] for key in regrouped_order]
        all_pantolo_rows = [row for section in sections for row in section.get("rows", []) if isinstance(row, dict)]

    for row in all_pantolo_rows:
        row["color"] = clean_text(row.get("name")) or "-"

    def canonical_pantolo_door(value: object) -> str:
        text = folded(clean_text(value))
        compact = re.sub(r"[^a-z0-9]+", "", text)
        if "sar" in text and "fel" in text:
            return "sarok_felso"
        if "sar" in text and "als" in text:
            return "sarok_also"
        if "felso" in compact and "uv" in compact:
            return "felso_uv"
        return compact or "-"

    def infer_pant_from_global_context(target_row: dict) -> str | None:
        if bool(target_row.get("_pantolo_explicit_nincs")):
            return None
        current_pant = folded(clean_text(target_row.get("pantType")))
        if current_pant not in {"", "-"}:
            return None
        if folded(clean_text(target_row.get("handleDrill"))) != "furva":
            return None

        target_size = clean_text(target_row.get("size"))
        target_opening = folded(clean_text(target_row.get("openingDir")))
        target_door = canonical_pantolo_door(target_row.get("doorType"))
        if not target_size or not target_opening or target_opening in {"-", "nincs"}:
            return None

        candidate_pants: set[str] = set()
        for row in all_pantolo_rows:
            if row is target_row:
                continue
            pant = clean_text(row.get("pantType"))
            if not pant or folded(pant) in {"-", "nincs"}:
                continue
            if clean_text(row.get("size")) != target_size:
                continue
            if folded(clean_text(row.get("openingDir"))) != target_opening:
                continue
            if canonical_pantolo_door(row.get("doorType")) != target_door:
                continue
            candidate_pants.add(pant)
        if len(candidate_pants) == 1:
            return next(iter(candidate_pants))
        return None

    def infer_pant_from_door_dominance(target_row: dict) -> str | None:
        """Fallback hiányzó pántnál: ajtó-típus alapú domináns pánt."""
        if bool(target_row.get("_pantolo_explicit_nincs")):
            return None
        if folded(clean_text(target_row.get("handleDrill"))) != "furva":
            return None

        target_door = canonical_pantolo_door(target_row.get("doorType"))
        target_opening = folded(clean_text(target_row.get("openingDir")))
        if target_door in {"", "-"}:
            return None

        def collect_counts(match_opening: bool) -> dict[str, int]:
            counts: dict[str, int] = {}
            for candidate in all_pantolo_rows:
                if candidate is target_row:
                    continue
                if bool(candidate.get("_pantolo_missing_pant")):
                    continue
                candidate_pant = clean_text(candidate.get("pantType"))
                if not candidate_pant or folded(candidate_pant) in {"", "-", "nincs"}:
                    continue
                if folded(clean_text(candidate.get("handleDrill"))) != "furva":
                    continue
                if canonical_pantolo_door(candidate.get("doorType")) != target_door:
                    continue
                if match_opening and folded(clean_text(candidate.get("openingDir"))) != target_opening:
                    continue
                counts[candidate_pant] = counts.get(candidate_pant, 0) + 1
            return counts

        def pick_if_dominant(counts: dict[str, int], min_advantage: int) -> str | None:
            if not counts:
                return None
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if len(ordered) == 1:
                return ordered[0][0]
            if ordered[0][1] >= ordered[1][1] + min_advantage:
                return ordered[0][0]
            return None

        by_door_opening = collect_counts(match_opening=True)
        inferred = pick_if_dominant(by_door_opening, min_advantage=2)
        if inferred:
            return inferred

        by_door = collect_counts(match_opening=False)
        return pick_if_dominant(by_door, min_advantage=3)

    for section in sections:
        rows = [row for row in section.get("rows", []) if isinstance(row, dict)]
        pant_counts: dict[str, int] = {}
        pant_rows_non_nincs: list[dict] = []
        for row in rows:
            pant_value = clean_text(row.get("pantType"))
            if not pant_value or pant_value == "-":
                continue
            pant_counts[pant_value] = pant_counts.get(pant_value, 0) + 1
            if folded(pant_value) != "nincs":
                pant_rows_non_nincs.append(row)
        if not pant_counts:
            for row in rows:
                row["pantType"] = "Nincs" if bool(row.get("_pantolo_explicit_nincs")) else "-"
            continue

        def infer_pant_type(target_row: dict) -> str | None:
            if not pant_rows_non_nincs:
                return None
            scored: list[tuple[tuple[int, int, int, int, int], str]] = []
            for candidate_row in pant_rows_non_nincs:
                candidate_pant = clean_text(candidate_row.get("pantType"))
                if not candidate_pant:
                    continue
                # Prioritás: fogantyú típus + fogantyú furat > nyitás irány > ajtó típus > méret.
                # Ez stabilabb azokra az első sorokra, ahol a pánt mező hiányos a PDF-ből.
                feature_score = (
                    int(clean_text(candidate_row.get("handleType")) == clean_text(target_row.get("handleType"))),
                    int(clean_text(candidate_row.get("handleDrill")) == clean_text(target_row.get("handleDrill"))),
                    int(clean_text(candidate_row.get("openingDir")) == clean_text(target_row.get("openingDir"))),
                    int(clean_text(candidate_row.get("doorType")) == clean_text(target_row.get("doorType"))),
                    int(clean_text(candidate_row.get("size")) == clean_text(target_row.get("size"))),
                )
                scored.append((feature_score, candidate_pant))
            if not scored:
                return None
            scored.sort(reverse=True)
            best_score = scored[0][0]
            if best_score <= (0, 0, 0, 0, 0):
                unique_pants = sorted({pant for _feature_score, pant in scored})
                return unique_pants[0] if len(unique_pants) == 1 else None
            best_pants = sorted({pant for feature_score, pant in scored if feature_score == best_score})
            if len(best_pants) != 1:
                return None
            inferred = best_pants[0]
            target_opening = folded(clean_text(target_row.get("openingDir")))
            # Ne keverjük: Felnyíló soroknál a hiányzó pánttípus tipikusan "Ráüt.",
            # nem "Ráüt.tip.".
            if target_opening == "felnyilo" and folded(inferred).startswith("raut.tip"):
                return "Ráüt."
            return inferred

        def dominant_section_pant() -> str | None:
            counts: dict[str, int] = {}
            for row in pant_rows_non_nincs:
                pant = clean_text(row.get("pantType"))
                if not pant:
                    continue
                counts[pant] = counts.get(pant, 0) + 1
            if not counts:
                return None
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            if len(ordered) == 1:
                return ordered[0][0]
            # Csak markáns többségnél használjuk fallbackként.
            if ordered[0][1] >= ordered[1][1] + 2:
                return ordered[0][0]
            return None

        dominant_pant = dominant_section_pant()

        def can_use_dominant_for_missing(target_row: dict) -> bool:
            opening = folded(clean_text(target_row.get("openingDir")))
            door_key = canonical_pantolo_door(target_row.get("doorType"))
            if opening in {"felnyilo", "nincs", "-"}:
                return False
            # Ezeknél gyakori az eltérő pánt (vagy explicit Nincs), ezért itt nem domináns-tippelünk.
            if door_key in {"sarok_felso", "sarok_also", "fsl", "felso_uv", "-"}:
                return False
            return True

        def infer_pant_type_strict_first_row(target_row: dict, row_index: int) -> str | None:
            # Csak az első sorra: 3-lépcsős kontroll, hogy ne maradjon hibás "Nincs".
            if row_index != 0:
                return None
            if not pant_rows_non_nincs:
                return None
            current_pant = clean_text(target_row.get("pantType"))
            current_drill = clean_text(target_row.get("handleDrill"))
            if folded(current_pant) not in {"nincs", "-"}:
                return None
            if folded(current_drill) != "furva":
                return None

            def row_pant(candidate: dict) -> str:
                return clean_text(candidate.get("pantType"))

            def non_nincs(candidate: dict) -> bool:
                pant = row_pant(candidate)
                return bool(pant and folded(pant) not in {"nincs", "-"})

            candidates = [candidate for candidate in rows if isinstance(candidate, dict) and candidate is not target_row and non_nincs(candidate)]
            if not candidates:
                return None

            # 1) Erős egyezés: fogantyú típus + furat + nyitás + ajtó típus
            strict = [
                candidate
                for candidate in candidates
                if clean_text(candidate.get("handleType")) == clean_text(target_row.get("handleType"))
                and clean_text(candidate.get("handleDrill")) == clean_text(target_row.get("handleDrill"))
                and clean_text(candidate.get("openingDir")) == clean_text(target_row.get("openingDir"))
                and clean_text(candidate.get("doorType")) == clean_text(target_row.get("doorType"))
            ]
            strict_pants = sorted({row_pant(candidate) for candidate in strict if row_pant(candidate)})
            if len(strict_pants) == 1:
                return strict_pants[0]

            # 2) Közepes egyezés: fogantyú típus + furat
            medium = [
                candidate
                for candidate in candidates
                if clean_text(candidate.get("handleType")) == clean_text(target_row.get("handleType"))
                and clean_text(candidate.get("handleDrill")) == clean_text(target_row.get("handleDrill"))
            ]
            medium_pants = sorted({row_pant(candidate) for candidate in medium if row_pant(candidate)})
            if len(medium_pants) == 1:
                return medium_pants[0]

            # 3) Közeli sorok többségi pántja (2-3 következő sorból)
            nearby = []
            for index, candidate in enumerate(rows):
                if not isinstance(candidate, dict) or candidate is target_row or not non_nincs(candidate):
                    continue
                if index in {1, 2, 3}:
                    nearby.append(candidate)
            if nearby:
                counts: dict[str, int] = {}
                for candidate in nearby:
                    pant = row_pant(candidate)
                    if not pant:
                        continue
                    counts[pant] = counts.get(pant, 0) + 1
                if counts:
                    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                    top_pant, top_count = ordered[0]
                    if top_count >= 2 or len(ordered) == 1:
                        return top_pant

            return None

        def infer_missing_pant_from_section_pairs(target_row: dict) -> str | None:
            """Hiányzó pántot csak ugyanazon box biztos párjából örököljünk."""
            target_size = clean_text(target_row.get("size"))
            target_door = canonical_pantolo_door(target_row.get("doorType"))
            target_handle = clean_text(target_row.get("handleType"))
            target_drill = folded(clean_text(target_row.get("handleDrill")))
            target_opening = folded(clean_text(target_row.get("openingDir")))
            if not target_size or target_door in {"", "-"} or target_drill != "furva":
                return None

            candidate_pants: set[str] = set()
            for candidate in rows:
                if candidate is target_row or not isinstance(candidate, dict):
                    continue
                candidate_pant = clean_text(candidate.get("pantType"))
                if not candidate_pant or folded(candidate_pant) in {"", "-", "nincs"}:
                    continue
                if clean_text(candidate.get("size")) != target_size:
                    continue
                if canonical_pantolo_door(candidate.get("doorType")) != target_door:
                    continue
                if clean_text(candidate.get("handleType")) != target_handle:
                    continue
                if folded(clean_text(candidate.get("handleDrill"))) != target_drill:
                    continue
                candidate_opening = folded(clean_text(candidate.get("openingDir")))
                # előny: ellentétes nyitású pár sor
                if target_opening in {"bal", "jobb"} and candidate_opening in {"bal", "jobb"}:
                    if candidate_opening == target_opening:
                        continue
                candidate_pants.add(candidate_pant)
            if len(candidate_pants) == 1:
                return next(iter(candidate_pants))
            return None

        def infer_missing_pant_business_rule(target_row: dict) -> str | None:
            """Gyártási szabály: Sarok alsó + Fém rúd esetén pánt = Pillér."""
            door_key = canonical_pantolo_door(target_row.get("doorType"))
            handle_type = folded(clean_text(target_row.get("handleType")))
            drill = folded(clean_text(target_row.get("handleDrill")))
            if door_key == "sarok_also" and "fem rud" in handle_type and drill == "furva":
                return "Pillér"
            return None

        # Csak egyértelmű esetben pótolunk, hogy a "Ráüt." és "Ráüt.tip." ne keveredjen.
        for row_index, row in enumerate(rows):
            pant_value = clean_text(row.get("pantType"))
            if not pant_value or pant_value == "-":
                row["pantType"] = "Nincs" if bool(row.get("_pantolo_explicit_nincs")) else "-"

        # Nincs második/harmadik pánt-korrekciós passz: nincs találgatás.

        for row in rows:
            if "_pantolo_explicit_nincs" in row:
                row.pop("_pantolo_explicit_nincs", None)
            if "_pantolo_missing_pant" in row:
                row.pop("_pantolo_missing_pant", None)

    return sections, row_count

