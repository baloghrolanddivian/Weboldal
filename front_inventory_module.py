from __future__ import annotations

import csv
import io
import json
import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
except Exception:  # pragma: no cover
    Workbook = None
    load_workbook = None


FRONT_INVENTORY_ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".csv"}
SERIAL_SIZES_DATA_PATH = Path(__file__).resolve().parent / "data" / "front-inventory-serial-sizes.json"


def file_name_allowed(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in FRONT_INVENTORY_ALLOWED_EXTENSIONS


def read_bytes_if_exists(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return path.read_bytes()


def write_runtime_upload(base_path: Path, file_name: str, payload: bytes) -> Path:
    suffix = Path(file_name or "").suffix.lower() or ".bin"
    target_path = base_path.with_suffix(suffix)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(payload)
    return target_path


def load_session_from_path(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def save_session_to_path(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_front_inventory_session(file_name: str, payload: bytes) -> dict:
    stock_rows = _read_stock_rows(file_name, payload)
    serial_sizes = _load_serial_sizes()

    rows: list[dict] = []
    for item in stock_rows:
        size = _extract_front_size(item["description"], item["part_number"])
        is_serial = size in serial_sizes
        rows.append(
            {
                "row_id": item["part_number"],
                "part_number": item["part_number"],
                "description": item["description"],
                "color": item.get("color", ""),
                "stock_qty": item["quantity"],
                "size": size,
                "category": size if is_serial else "egyedi",
                "is_serial": is_serial,
                "input_qty": "",
                "resolved_qty": None,
                "first_check_qty": None,
                "second_check_qty": None,
                "final_check_qty": None,
                "review_level": 0,
                "status": "pending",
            }
        )

    rows.sort(key=_row_sort_key)

    return {
        "session_id": secrets.token_hex(6),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source_name": Path(file_name).name,
        "phase": 0,
        "phase_label": "Számlálás",
        "finalized_at": "",
        "serial_sizes": sorted(serial_sizes, key=_size_sort_key),
        "rows": rows,
    }


def update_row_input(session: dict, row_id: str, raw_value: str) -> tuple[bool, str]:
    row = _find_row(session, row_id)
    if row is None:
        return False, "A kiválasztott frontsort nem találom."
    if str(session.get("phase")) == "finalized":
        return False, "A leltár már le van zárva."
    if row.get("status") != "pending":
        return False, "Ez a sor már lezárt állapotban van."

    clean_value = str(raw_value or "").strip()
    if not clean_value:
        row["input_qty"] = ""
        _touch_session(session)
        return True, ""

    parsed_value = _parse_non_negative_int(clean_value)
    if parsed_value is None:
        return False, "Csak nem negatív egész darabszám adható meg."

    row["input_qty"] = str(parsed_value)
    _touch_session(session)
    return True, ""


def summarize_missing_inputs(session: dict) -> dict:
    if str(session.get("phase")) == "finalized":
        return {"total_missing": 0, "categories": [], "rows": []}

    phase_value = session.get("phase", 0)
    phase = 2 if str(phase_value) == "finalized" else int(phase_value or 0)
    active_rows = _active_rows_for_phase(session, phase)
    missing_rows = [row for row in active_rows if _row_input_value(row) is None]

    category_counts: dict[str, int] = {}
    for row in missing_rows:
        category_key = str(row.get("category") if row.get("is_serial") else "egyedi")
        category_counts[category_key] = category_counts.get(category_key, 0) + 1

    categories = [
        {"key": key, "count": count}
        for key, count in sorted(category_counts.items(), key=lambda item: (_size_sort_key(item[0]) if item[0] != "egyedi" else (9999, 9999, item[0])))
    ]
    rows = [
        {
            "part_number": str(row.get("part_number", "")),
            "description": str(row.get("description", "")),
            "color": str(row.get("color", "")),
            "category": str(row.get("category") if row.get("is_serial") else "egyedi"),
        }
        for row in missing_rows[:40]
    ]
    return {
        "total_missing": len(missing_rows),
        "categories": categories,
        "rows": rows,
    }


def _set_worker_alert(session: dict, title: str, message: str) -> None:
    session["worker_alert"] = {
        "id": datetime.now().isoformat(timespec="seconds"),
        "title": str(title or "").strip(),
        "message": str(message or "").strip(),
    }


def build_inventory_check_workbook(session: dict, mode: str = "check", treat_missing_as_zero: bool = False) -> tuple[bytes | None, str, int]:
    if Workbook is None:
        return None, "", 0

    phase_value = session.get("phase", 0)
    phase = 2 if str(phase_value) == "finalized" else int(phase_value or 0)
    all_rows = sorted(list(session.get("rows", [])), key=_row_sort_key)
    if mode == "finalize":
        report_label = "veglegesites"
    elif phase == 0:
        report_label = "elso-ellenorzes"
    elif phase == 1:
        report_label = "masodik-ellenorzes"
    else:
        report_label = "ellenorzes"

    workbook = Workbook()
    report_rows = [_build_export_row(row, phase=phase, mode=mode, treat_missing_as_zero=treat_missing_as_zero) for row in all_rows]

    if mode == "finalize":
        _fill_finalize_workbook(workbook, report_rows)
    else:
        sheet = workbook.active
        sheet.title = "Ellenorzes"
        if phase == 1:
            headers = ["Alkatresz szam", "Leiras", "Elso szamlalas", "Masodik szamlalas", "Raktari darabszam"]
        else:
            headers = ["Alkatresz szam", "Leiras", "Beirt darabszam", "Raktari darabszam"]
        sheet.append(headers)
        if report_rows:
            for item in report_rows:
                if phase == 1:
                    sheet.append(
                        [
                            item["part_number"],
                            item["description"],
                            _excel_cell_int(item.get("first_check_qty")),
                            _excel_cell_int(item.get("second_check_qty")),
                            item["stock_qty"],
                        ]
                    )
                else:
                    sheet.append(
                        [
                            item["part_number"],
                            item["description"],
                            _excel_cell_int(item.get("current_count_qty")),
                            item["stock_qty"],
                        ]
                    )
        else:
            sheet.append(["", "Nincs elteres ebben az ellenorzesi korben."] + [""] * (len(headers) - 2))

        for width, column in zip((26, 56, 18, 18, 18), ("A", "B", "C", "D", "E")):
            sheet.column_dimensions[column].width = width

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), f"front-leltar-{report_label}.xlsx", len(all_rows)


def run_inventory_check(session: dict, allow_missing: bool = False) -> tuple[bool, str]:
    if str(session.get("phase")) == "finalized":
        return False, "A leltár már le van zárva."

    phase = int(session.get("phase", 0) or 0)
    active_rows = _active_rows_for_phase(session, phase)
    if not active_rows:
        session["phase"] = 2
        session["phase_label"] = "Veglegesites"
        _touch_session(session)
        return True, "Nincs tovabbi ellenorizendo front, a leltar veglegesitheto."

    missing_rows = [row for row in active_rows if _row_input_value(row) is None]
    missing_count = len(missing_rows)
    if missing_count and not allow_missing:
        return False, f"Meg {missing_count} frontnal nincs beirva a darabszam."

    if phase == 0:
        mismatch_count = 0
        for row in active_rows:
            entered_qty = _row_input_value(row)
            if entered_qty is None:
                if allow_missing:
                    entered_qty = 0
                assert entered_qty is not None
            row["first_check_qty"] = entered_qty
            if entered_qty == int(row.get("stock_qty", 0) or 0):
                row["resolved_qty"] = entered_qty
                row["status"] = "resolved"
            else:
                row["review_level"] = 1
                mismatch_count += 1
        _clear_all_pending_inputs(session)
        session["phase"] = 1 if mismatch_count else 2
        session["phase_label"] = "Elso ellenorzes" if mismatch_count else "Veglegesites"
        _touch_session(session)
        if mismatch_count:
            _set_worker_alert(session, "Ellenorzes kesz", f"{mismatch_count} tetelnel elteres talalhato, ujraszamolas szukseges.")
            if missing_count and allow_missing:
                return True, f"{mismatch_count} front eltert a keszlettol, {missing_count} kitoltetlen sor pedig atkerult a kovetkezo korbe."
            return True, f"{mismatch_count} front eltert a keszlettol, ezeket ujra kell szamolni."
        _set_worker_alert(session, "Ellenorzes kesz", "Nem talaltam elterest, a leltar veglegesitheto.")
        if missing_count and allow_missing:
            return True, f"Nincs elteres, de {missing_count} kitoltetlen sor atkerult a kovetkezo korbe."
        return True, "Minden front egyezik a keszlettel, a leltar veglegesitheto."

    high_diff_count = 0
    for row in active_rows:
        entered_qty = _row_input_value(row)
        if entered_qty is None:
            if allow_missing:
                entered_qty = 0
            assert entered_qty is not None
        row["second_check_qty"] = entered_qty
        stock_qty = int(row.get("stock_qty", 0) or 0)
        if abs(entered_qty - stock_qty) > 5:
            row["review_level"] = 2
            high_diff_count += 1
        else:
            row["resolved_qty"] = entered_qty
            row["status"] = "resolved"

    _clear_all_pending_inputs(session)
    session["phase"] = 2
    session["phase_label"] = "Veglegesites"
    _touch_session(session)
    if high_diff_count:
        _set_worker_alert(session, "Ellenorzes kesz", f"{high_diff_count} tetelnel tovabbra is nagy elteres van, ujraszamolas szukseges.")
        if missing_count and allow_missing:
            return True, f"{high_diff_count} frontnal 5 darabnal nagyobb elteres maradt, {missing_count} kitoltetlen sor pedig tovabbra is nyitott."
        return True, f"{high_diff_count} frontnal 5 darabnal nagyobb elteres maradt, ezeket meg egyszer ellenorizni kell."
    _set_worker_alert(session, "Ellenorzes kesz", "Az ujraellenorzes befejezodott, a leltar veglegesitheto.")
    if missing_count and allow_missing:
        return True, f"Az eltero frontok ujraellenorzese kesz, de {missing_count} kitoltetlen sor tovabbra is nyitott."
    return True, "Az eltero frontok ujraellenorzese kesz, a leltar veglegesitheto."


def finalize_inventory(session: dict, allow_missing: bool = False) -> tuple[bool, str]:
    if str(session.get("phase")) == "finalized":
        return False, "A leltar mar le van zarva."

    active_rows = _active_rows_for_phase(session, 2)
    missing_count = sum(1 for row in active_rows if _row_input_value(row) is None)
    if missing_count and not allow_missing:
        return False, f"Meg {missing_count} frontnal nincs vegleges darabszam."

    for row in active_rows:
        entered_qty = _row_input_value(row)
        if entered_qty is None:
            if allow_missing:
                entered_qty = 0
            assert entered_qty is not None
        row["final_check_qty"] = entered_qty
        row["resolved_qty"] = entered_qty
        row["status"] = "resolved"

    _clear_all_pending_inputs(session)
    session["phase"] = "finalized"
    session["phase_label"] = "Lezarva"
    session["finalized_at"] = datetime.now().isoformat(timespec="seconds")
    _touch_session(session)
    return True, "A leltar lezarult."


def _clear_all_pending_inputs(session: dict) -> None:
    for row in session.get("rows", []):
        row["input_qty"] = ""


def _build_export_row(row: dict, phase: int, mode: str, treat_missing_as_zero: bool) -> dict:
    current_input = _row_input_value(row)
    if current_input is None and treat_missing_as_zero and str(row.get("status", "")) != "resolved":
        current_input = 0

    export_row = {
        "part_number": str(row.get("part_number", "")).strip(),
        "description": str(row.get("description", "")).strip(),
        "stock_qty": int(row.get("stock_qty", 0) or 0),
        "first_check_qty": _parse_non_negative_int(row.get("first_check_qty")),
        "second_check_qty": _parse_non_negative_int(row.get("second_check_qty")),
        "final_check_qty": _parse_non_negative_int(row.get("final_check_qty")),
        "resolved_qty": _parse_non_negative_int(row.get("resolved_qty")),
        "current_count_qty": None,
    }

    if mode == "finalize":
        export_row["final_count_qty"] = _final_effective_qty(row)
        return export_row

    if phase == 0:
        export_row["current_count_qty"] = current_input
    elif phase == 1 and int(row.get("review_level", 0) or 0) == 1 and str(row.get("status", "")) != "resolved":
        export_row["second_check_qty"] = current_input
    else:
        export_row["current_count_qty"] = current_input
    return export_row


def _final_effective_qty(row: dict) -> int:
    for key in ("resolved_qty", "final_check_qty", "second_check_qty", "first_check_qty"):
        parsed = _parse_non_negative_int(row.get(key))
        if parsed is not None:
            return parsed
    return 0


def _fill_finalize_workbook(workbook: Workbook, report_rows: list[dict]) -> None:
    summary_sheet = workbook.active
    summary_sheet.title = "Vegleges darabszamok"
    summary_sheet.append(["Alkatresz szam", "Darabszam"])
    for item in report_rows:
        summary_sheet.append([item["part_number"], item["final_count_qty"]])

    compare_sheet = workbook.create_sheet("Rendszer vs szamolt")
    compare_sheet.append(["Alkatresz szam", "Leiras", "Szamolt darabszam", "Raktari darabszam"])
    for item in report_rows:
        compare_sheet.append([item["part_number"], item["description"], item["final_count_qty"], item["stock_qty"]])

    rounds_sheet = workbook.create_sheet("Szamlalasok")
    rounds_sheet.append(["Alkatresz szam", "Leiras", "Elso szamlalas", "Masodik szamlalas", "Vegso szamlalas", "Raktari darabszam"])
    for item in report_rows:
        rounds_sheet.append(
            [
                item["part_number"],
                item["description"],
                _excel_cell_int(item.get("first_check_qty")),
                _excel_cell_int(item.get("second_check_qty")),
                item["final_count_qty"],
                item["stock_qty"],
            ]
        )

    for sheet, widths in (
        (summary_sheet, (28, 16)),
        (compare_sheet, (28, 56, 18, 18)),
        (rounds_sheet, (28, 56, 18, 18, 18, 18)),
    ):
        for width, column in zip(widths, ("A", "B", "C", "D", "E", "F")):
            sheet.column_dimensions[column].width = width


def build_front_inventory_view_model(session: dict, selected_category: str = "") -> dict:
    finalized = str(session.get("phase")) == "finalized"
    source_rows = session.get("rows", [])
    for row in source_rows:
        if not str(row.get("color", "")).strip():
            row["color"] = _extract_color_value(row.get("description", ""), "")
    active_rows = _active_rows_for_phase(session, int(session.get("phase", 0) or 0)) if not finalized else list(source_rows)
    active_rows = list(active_rows)

    serial_rows = [row for row in active_rows if row.get("is_serial")]
    custom_rows = [row for row in active_rows if not row.get("is_serial")]

    categories: list[dict] = []
    categories.append({"key": "all", "label": "Összes", "count": len(serial_rows), "complete": bool(serial_rows) and all(str(row.get("input_qty", "")).strip() for row in serial_rows)})
    categories.append({"key": "egyedi", "label": "Egyedi", "count": len(custom_rows), "complete": bool(custom_rows) and all(str(row.get("input_qty", "")).strip() for row in custom_rows)})

    size_buckets: dict[str, list[dict]] = {}
    for row in serial_rows:
        category_key = str(row.get("category", "")).strip()
        if category_key:
            size_buckets.setdefault(category_key, []).append(row)

    for size_key in sorted(size_buckets, key=_size_sort_key):
        bucket_rows = size_buckets[size_key]
        categories.append({"key": size_key, "label": size_key, "count": len(bucket_rows), "complete": bool(bucket_rows) and all(str(row.get("input_qty", "")).strip() for row in bucket_rows)})

    allowed_keys = {item["key"] for item in categories if item["count"] > 0} | {"all", "egyedi"}
    active_category = selected_category if selected_category in allowed_keys else ("all" if serial_rows else ("egyedi" if custom_rows else "all"))

    if active_category == "all":
        visible_rows = serial_rows
    elif active_category == "egyedi":
        visible_rows = custom_rows
    else:
        visible_rows = [row for row in serial_rows if row.get("category") == active_category]

    finalized_rows = _finalized_rows(session) if finalized else []

    return {
        "selected_category": active_category,
        "categories": categories,
        "visible_rows": visible_rows,
        "active_row_count": len(active_rows),
        "serial_row_count": len(serial_rows),
        "custom_row_count": len(custom_rows),
        "finalized": finalized,
        "finalized_rows": finalized_rows,
    }


def _finalized_rows(session: dict) -> list[dict]:
    rows = []
    for row in session.get("rows", []):
        resolved_qty = row.get("resolved_qty")
        if resolved_qty is None:
            continue
        rows.append(
            {
                "part_number": row.get("part_number", ""),
                "description": row.get("description", ""),
                "color": row.get("color", ""),
                "counted_qty": int(resolved_qty or 0),
                "size": row.get("size", ""),
                "category": row.get("category", ""),
                "is_serial": bool(row.get("is_serial")),
            }
        )
    rows.sort(key=lambda row: (_row_category_sort_key(row), row.get("part_number", "")))
    return rows


def _active_rows_for_phase(session: dict, phase: int) -> list[dict]:
    if str(session.get("phase")) == "finalized":
        return []
    rows = []
    for row in session.get("rows", []):
        if row.get("status") == "resolved":
            continue
        if int(row.get("review_level", 0) or 0) == phase:
            rows.append(row)
    rows.sort(key=_row_sort_key)
    return rows


def _find_row(session: dict, row_id: str) -> dict | None:
    target = str(row_id or "").strip().upper()
    for row in session.get("rows", []):
        if str(row.get("row_id", "")).strip().upper() == target:
            return row
    return None


def _touch_session(session: dict) -> None:
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")


def _read_stock_rows(file_name: str, payload: bytes) -> list[dict]:
    rows = _read_rows(file_name, payload)
    if not rows:
        raise ValueError("A front készletfájl üres.")

    header_map = _build_header_map(rows[0])
    part_index = _find_header_index(header_map, ("alkatr", "szam"))
    desc_index = _find_header_index(header_map, ("alkatr", "leiras"))
    qty_index = _find_header_index(header_map, ("rend", "all", "rakt", "keszl")) or _find_header_index(header_map, ("rend", "all"))
    color_index = _find_header_index(header_map, ("szin", "desc")) or _find_header_index(header_map, ("szin",))

    if None in {part_index, desc_index, qty_index}:
        raise ValueError("A front készletfájlban kell alkatrészszám, leírás és készlet oszlop.")

    items: list[dict] = []
    for row in rows[1:]:
        if max(part_index, desc_index, qty_index) >= len(row):
            continue
        part_number = _normalize_part_number(row[part_index])
        if not part_number:
            continue
        description = str(row[desc_index] or "").strip()
        quantity = _parse_non_negative_int(row[qty_index])
        color_value = row[color_index] if color_index is not None and color_index < len(row) else ""
        if quantity is None or quantity <= 0:
            continue
        if not _looks_like_front(part_number, description):
            continue
        if _is_legacy_matt_front(description, color_value):
            continue
        items.append(
            {
                "part_number": part_number,
                "description": description,
                "color": _extract_color_value(description, color_value),
                "quantity": quantity,
            }
        )

    if not items:
        raise ValueError("A front készletfájlban nem találtam raktáron lévő front sorokat.")
    return items


def _looks_like_front(part_number: str, description: str) -> bool:
    folded_description = _fold_text(description)
    return (
        str(part_number or "").strip().upper().startswith("NFA_")
        or "folias fr" in folded_description
        or "front" in folded_description
    )


def _is_legacy_matt_front(description: object, explicit_color: object) -> bool:
    combined = f"{description or ''} {explicit_color or ''}"
    folded = _fold_text(combined)
    has_sm = "sm." in folded or "sm " in folded or folded.startswith("sm")
    has_gloss = "fenyes" in folded or "magasfeny" in folded
    has_zille = "zille" in folded
    has_matt = " matt " in f" {folded} " or folded.endswith(" matt") or folded.startswith("matt ")
    return has_matt and not has_sm and not has_gloss and not has_zille


def _load_serial_sizes() -> set[str]:
    if SERIAL_SIZES_DATA_PATH.exists():
        try:
            payload = json.loads(SERIAL_SIZES_DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        values = payload.get("sizes", []) if isinstance(payload, dict) else []
        result = {_normalize_front_size(value) for value in values}
        return {value for value in result if value}
    return set()


def _read_rows(file_name: str, payload: bytes) -> list[list[object]]:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        if load_workbook is None:
            raise RuntimeError("Az Excel feldolgozáshoz hiányzik az openpyxl csomag.")
        workbook = load_workbook(io.BytesIO(payload), data_only=True)
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    if suffix == ".csv":
        text = _decode_csv_bytes(payload)
        return [list(row) for row in csv.reader(io.StringIO(text))]
    raise ValueError("Csak XLSX, XLSM vagy CSV fájlokat tudok feldolgozni.")


def _decode_csv_bytes(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _build_header_map(header_row: list[object]) -> dict[int, str]:
    return {index: _normalize_header(value) for index, value in enumerate(header_row)}


def _find_header_index(header_map: dict[int, str], terms: tuple[str, ...]) -> int | None:
    for index, normalized in header_map.items():
        if all(term in normalized for term in terms):
            return index
    return None


def _normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold_text(value))


def _normalize_part_number(value: object) -> str:
    return str(value or "").strip().upper()


def _parse_non_negative_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except Exception:
            return None
        if number < 0:
            return None
        return int(round(number))
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0:
        return None
    return int(round(number))


def _extract_front_size(description: str, part_number: str) -> str:
    for source in (str(description or ""), str(part_number or "")):
        match = re.search(r"(\d{2,4}\s*x\s*\d{2,4})\s*x\s*\d{1,2}\b", source, flags=re.IGNORECASE)
        if match:
            return _normalize_front_size(match.group(1))
        match = re.search(r"(\d{2,4}\s*x\s*\d{2,4})\b", source, flags=re.IGNORECASE)
        if match:
            return _normalize_front_size(match.group(1))
    return ""


def _extract_color_value(description: object, explicit_color: object) -> str:
    clean_color = str(explicit_color or "").strip()
    if clean_color:
        return clean_color

    text = str(description or "").strip()
    if not text:
        return ""

    text = re.sub(r"^Fóliás fr\.?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\b\d{2,4}\s*x\s*\d{2,4}\s*x\s*\d{1,2}\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\b\d{2,4}\s*x\s*\d{2,4}\b", "", text, flags=re.IGNORECASE).strip()
    parts = text.split()
    if len(parts) <= 1:
        return text
    return " ".join(parts[1:]).strip()


def _normalize_front_size(value: object) -> str:
    clean_value = re.sub(r"\s+", "", str(value or "")).lower()
    match = re.match(r"^(\d{2,4})x(\d{2,4})$", clean_value)
    if not match:
        return ""
    return f"{match.group(1)}x{match.group(2)}"


def _size_sort_key(value: str) -> tuple[int, int, str]:
    match = re.match(r"^(\d{2,4})x(\d{2,4})$", str(value or "").strip().lower())
    if not match:
        return (9999, 9999, str(value or ""))
    return (int(match.group(1)), int(match.group(2)), str(value or ""))


def _row_category_sort_key(row: dict) -> tuple[int, tuple[int, int, str] | tuple[int, int, str], str]:
    if row.get("is_serial"):
        return (0, _size_sort_key(str(row.get("category", ""))), str(row.get("part_number", "")))
    return (1, (9999, 9999, "egyedi"), str(row.get("part_number", "")))


def _row_sort_key(row: dict) -> tuple[int, tuple[int, int, str], str]:
    return _row_category_sort_key(row)


def _row_input_value(row: dict) -> int | None:
    return _parse_non_negative_int(row.get("input_qty"))


def _excel_cell_int(value: object) -> int | str:
    parsed = _parse_non_negative_int(value)
    return parsed if parsed is not None else ""


def _fold_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()
