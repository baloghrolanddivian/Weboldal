"""Cutting-shop inventory for boards, worktops, and wall panels."""

from __future__ import annotations

import hashlib
import html
import json
import math
import secrets
import threading
from datetime import date, datetime
from pathlib import Path

from .routes import (
    ADMIN_CUTTING_INVENTORY_ROUTE,
    ADMIN_INVENTORY_GROUP_ROUTE,
    CUTTING_INVENTORY_CLOSE_ROUTE,
    CUTTING_INVENTORY_CATALOG_ROUTE,
    CUTTING_INVENTORY_START_ROUTE,
    CUTTING_INVENTORY_STATE_ROUTE,
    CUTTING_INVENTORY_WORKER_ROUTE,
    PRODUCTION_INVENTORY_GROUP_ROUTE,
)


BOARD_SIZES = (
    ("2800x200", "2800×200", 2800, 200),
    ("2800x600", "2800×600", 2800, 600),
    ("2070x750", "2070×750", 2070, 750),
    ("2070x530", "2070×530", 2070, 530),
)
BOARD_NAMES = (
    "Agyag szürke", "Antracit", "Artizán tölgy", "Bianco", "Beton fehér", "Canyon",
    "Csíkos tölgy", "Etna", "Fehér", "Fehér tölgy", "Fjord zöld", "Ibiza", "Kasmír",
    "Mouse grey", "Néró", "Petra", "Rusztikus sötét tölgy", "San Remo", "Sonoma", "Szürke tölgy",
)
WORKTOP_NAMES = (
    'Arany Craft 38"', "Arany Craft 900mm", 'Artizán tölgy 38"', "Artizán tölgy 900mm",
    'Beige 28"', 'Beton fehér 38"', "Beton fehér 920mm", 'Black 38"', 'Negru Black 38"',
    'California 38"', 'Cappucino 28"', 'Fehér 38"', 'Fehér 38" 2', 'Fehér tölgy 38"',
    "Fehér tölgy 920mm", 'Fekete kvarc 28"', 'Ferrara 38"', 'Gravel 38"',
    'Iguazu márvány 38"', "Iguazu márvány 900mm", 'Krém Navona 38"', "Krém Navona 900mm",
    'Lazac 28"', 'Malibu 38"', 'Merkúr 38"', 'Montana 38"', 'Nevada 38"',
    'Porterhouse dió 38"', "Porterhouse dió 900mm", 'Rusztikus sötét tölgy 38"',
    "Rusztikus sötét tölgy 920mm", 'Sonoma 28"', 'Sonoma 38"', "Sonoma 920mm",
    'Sötét homok 38"', "Sötét homok 900mm", 'Sötét tölgy 38"', "Sötét tölgy 900mm",
    'Szürke tölgy 38"', "Szürke tölgy 920mm", 'Ventura 28"', 'Ventura 38"',
    'Világos homok 38"', "Világos homok 900mm",
)
WALL_PANEL_ITEMS = (
    ("Arany Craft", "m2"),
    ("EGGER Beton fehér", "m"),
    ("EGGER Fehér tölgy", "m"),
    ("EGGER Rusztikus sötét tölgy", "m"),
    ("EGGER Szürke tölgy", "m"),
    ("Iguazu márvány", "m2"),
    ("Krém Navona", "m2"),
    ("Porterhouse dió", "m2"),
    ("Sonoma", "m2"),
    ("Sötét homok", "m2"),
    ("Sötét tölgy", "m2"),
    ("Világos homok", "m2"),
    ("Artizán tölgy", "m2"),
)
WALL_PANEL_WIDTH_M = 0.64

_runtime_dir = Path("runtime/szabaszat-leltar")
_state_lock = threading.RLock()


def configure_cutting_inventory(runtime_dir: Path) -> None:
    global _runtime_dir
    _runtime_dir = Path(runtime_dir)


def load_state() -> dict:
    path = _runtime_dir / "state.json"
    if not path.is_file():
        return {"active": None, "history": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active": None, "history": []}
    if not isinstance(payload, dict):
        return {"active": None, "history": []}
    payload.setdefault("active", None)
    payload.setdefault("history", [])
    return payload


def load_catalog() -> dict:
    path = _runtime_dir / "catalog.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and all(isinstance(payload.get(key), list) for key in ("board_sizes", "boards", "worktops", "wall_panels")):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return _default_catalog()


def apply_catalog_action(form: dict[str, str]) -> None:
    with _state_lock:
        catalog = load_catalog()
        action = str(form.get("action", "")).strip().lower()
        if action == "save_size":
            width = _parse_positive_integer(form.get("width_mm", ""))
            height = _parse_positive_integer(form.get("height_mm", ""))
            if width is None or height is None:
                raise ValueError("A szélességet és magasságot pozitív, egész milliméterben add meg.")
            item_id = str(form.get("item_id", "")).strip()
            sizes = catalog["board_sizes"]
            current = next((item for item in sizes if item.get("id") == item_id), None)
            if current is None:
                if any(int(item.get("width_mm", 0)) == width and int(item.get("height_mm", 0)) == height for item in sizes):
                    raise ValueError("Ez a bútorlapméret már szerepel a listában.")
                sizes.append({"id": f"size_{secrets.token_hex(5)}", "label": f"{width}×{height}", "width_mm": width, "height_mm": height})
            else:
                if any(item is not current and int(item.get("width_mm", 0)) == width and int(item.get("height_mm", 0)) == height for item in sizes):
                    raise ValueError("Ez a bútorlapméret már szerepel a listában.")
                current.update({"label": f"{width}×{height}", "width_mm": width, "height_mm": height})
        elif action == "delete_size":
            item_id = str(form.get("item_id", "")).strip()
            catalog["board_sizes"] = [item for item in catalog["board_sizes"] if item.get("id") != item_id]
        elif action == "save_item":
            category = str(form.get("category", "")).strip()
            if category not in {"boards", "worktops", "wall_panels"}:
                raise ValueError("Ismeretlen törzsadat-kategória.")
            name = str(form.get("name", "")).strip()
            if not name:
                raise ValueError("A megnevezés nem lehet üres.")
            item_id = str(form.get("item_id", "")).strip()
            items = catalog[category]
            if any(str(item.get("name", "")).casefold() == name.casefold() and item.get("id") != item_id for item in items):
                raise ValueError("Ez a megnevezés már szerepel a listában.")
            current = next((item for item in items if item.get("id") == item_id), None)
            values = {"name": name}
            if category == "wall_panels":
                unit = str(form.get("unit", "m")).strip()
                if unit not in {"m", "m2"}:
                    raise ValueError("Ismeretlen falipanel mértékegység.")
                values["unit"] = unit
                width_mm = _parse_positive_integer(form.get("width_mm", ""))
                if unit == "m2" and width_mm is None:
                    raise ValueError("Négyzetméteres elszámolásnál add meg a falipanel szélességét milliméterben.")
                values["width_mm"] = width_mm or WALL_PANEL_WIDTH_M * 1000
            if current is None:
                values["id"] = f"{category}_{secrets.token_hex(5)}"
                items.append(values)
            else:
                current.update(values)
        elif action == "delete_item":
            category = str(form.get("category", "")).strip()
            if category not in {"boards", "worktops", "wall_panels"}:
                raise ValueError("Ismeretlen törzsadat-kategória.")
            item_id = str(form.get("item_id", "")).strip()
            catalog[category] = [item for item in catalog[category] if item.get("id") != item_id]
        else:
            raise ValueError("Ismeretlen törzsadat-művelet.")

        state = load_state()
        if isinstance(state.get("active"), dict):
            _sync_active_session(state["active"], catalog)
            state["active"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _save_state(state)
        _save_catalog(catalog)


def start_inventory(raw_date: str) -> dict:
    try:
        inventory_date = date.fromisoformat(str(raw_date or "").strip())
    except ValueError as exc:
        raise ValueError("Adj meg érvényes leltári dátumot.") from exc
    with _state_lock:
        state = load_state()
        if isinstance(state.get("active"), dict):
            raise ValueError("Már van nyitott szabászati leltár. Előbb zárd le.")
        session = _new_session(inventory_date.isoformat(), load_catalog())
        state["active"] = session
        _save_state(state)
        return session


def close_inventory() -> dict:
    with _state_lock:
        state = load_state()
        session = state.get("active")
        if not isinstance(session, dict):
            raise ValueError("Nincs nyitott szabászati leltár.")
        session["status"] = "closed"
        session["closed_at"] = datetime.now().isoformat(timespec="seconds")
        session["summary"] = session_summary(session)
        state.setdefault("history", []).insert(0, session)
        state["active"] = None
        _save_state(state)
        return session


def apply_active_action(form: dict[str, str]) -> dict:
    with _state_lock:
        state = load_state()
        session = state.get("active")
        if not isinstance(session, dict):
            raise ValueError("Nincs nyitott szabászati leltár.")
        category = str(form.get("category", "")).strip().lower()
        row = _find_row(session, category, form.get("row_id", ""))
        if row is None:
            raise ValueError("A kiválasztott tétel nem található.")
        action = str(form.get("action", "")).strip().lower()
        if action == "set_board_count" and category == "boards":
            size_key = str(form.get("size_key", "")).strip()
            board_sizes = session.get("board_sizes", _legacy_board_sizes())
            if size_key not in {str(item.get("id", "")) for item in board_sizes}:
                raise ValueError("Ismeretlen bútorlapméret.")
            value = str(form.get("value", "")).strip()
            if value:
                parsed = _parse_non_negative_integer(value)
                if parsed is None:
                    raise ValueError("A bútorlap darabszáma csak nem negatív egész szám lehet.")
                row.setdefault("counts", {})[size_key] = str(parsed)
            else:
                row.setdefault("counts", {})[size_key] = ""
        elif action == "add_piece" and category in {"worktops", "wall_panels"}:
            length = _parse_positive_integer(form.get("length_mm", ""))
            if length is None:
                raise ValueError("A méretet pozitív, egész milliméterben add meg.")
            row.setdefault("pieces", []).append({"piece_id": secrets.token_hex(5), "length_mm": length})
        elif action == "delete_piece" and category in {"worktops", "wall_panels"}:
            piece_id = str(form.get("piece_id", "")).strip()
            pieces = [piece for piece in row.get("pieces", []) if isinstance(piece, dict)]
            remaining = [piece for piece in pieces if str(piece.get("piece_id", "")) != piece_id]
            if len(remaining) == len(pieces):
                raise ValueError("A kiválasztott méret nem található.")
            row["pieces"] = remaining
        elif action == "toggle_checked":
            row["checked"] = str(form.get("checked", "")) in {"1", "true", "on"}
        else:
            raise ValueError("Ismeretlen művelet.")
        session["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)
        return {"row": row_payload(category, row, session.get("board_sizes", _legacy_board_sizes())), "summary": session_summary(session)}


def row_payload(category: str, row: dict, board_sizes: list | None = None) -> dict:
    payload = {
        "row_id": str(row.get("row_id", "")),
        "checked": bool(row.get("checked")),
        "total": _format_decimal(_row_total(category, row, board_sizes)),
        "unit": "m²" if category == "boards" or row.get("unit") == "m2" else "m",
    }
    if category == "boards":
        payload["counts"] = row.get("counts", {})
    else:
        payload["pieces"] = row.get("pieces", [])
    return payload


def session_summary(session: dict) -> dict:
    board_sizes = session.get("board_sizes", _legacy_board_sizes())
    categories = {}
    for category in ("boards", "worktops", "wall_panels"):
        rows = [row for row in session.get(category, []) if isinstance(row, dict)]
        categories[category] = {
            "rows": len(rows),
            "checked": sum(1 for row in rows if row.get("checked")),
            "total": _format_decimal(sum(_row_total(category, row, board_sizes) for row in rows)),
            "unit": "m²" if category == "boards" else "vegyes" if category == "wall_panels" else "m",
        }
    all_checked = sum(item["checked"] for item in categories.values())
    all_rows = sum(item["rows"] for item in categories.values())
    categories["all_checked"] = all_checked
    categories["all_rows"] = all_rows
    return categories


def render_admin_page(message: str = "", success: bool = False) -> bytes:
    state = load_state()
    catalog = load_catalog()
    active = state.get("active") if isinstance(state.get("active"), dict) else None
    notice = f'<div class="cut-notice{" is-success" if success else ""}">{html.escape(message)}</div>' if message else ""
    if active:
        summary = session_summary(active)
        active_html = f'''<section class="cut-panel cut-active"><div><span class="cut-tag">Nyitott leltár</span><h2>{_display_date(active.get("inventory_date"))}</h2><p><b>{summary['all_checked']}/{summary['all_rows']}</b> tétel ellenőrizve · utolsó mentés: {html.escape(str(active.get('updated_at', '')))}</p></div><div class="cut-admin-actions"><a href="{CUTTING_INVENTORY_WORKER_ROUTE}">Számolás megnyitása</a><form method="post" action="{CUTTING_INVENTORY_CLOSE_ROUTE}" onsubmit="return confirm('Biztosan lezárod ezt a leltárt?')"><button type="submit">Leltár lezárása</button></form></div></section>'''
        start_html = ""
    else:
        active_html = '<section class="cut-panel cut-empty"><h2>Nincs nyitott leltár</h2><p>Adj meg egy dátumot az új szabászati leltár indításához.</p></section>'
        start_html = f'''<section class="cut-panel cut-start"><div><span class="cut-tag">Új leltár</span><h2>Leltári nap megadása</h2></div><form method="post" action="{CUTTING_INVENTORY_START_ROUTE}"><input type="date" name="inventory_date" value="{date.today().isoformat()}" required /><button type="submit">Leltár megnyitása</button></form></section>'''
    history_rows = "".join(_history_row(item) for item in state.get("history", []) if isinstance(item, dict))
    if not history_rows:
        history_rows = '<tr><td colspan="5">Még nincs lezárt leltár.</td></tr>'
    body = f'''<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Divian-HUB | Szabászat leltár kezelő</title><link rel="stylesheet" href="/styles.css"><style>{_styles()}</style></head><body class="cut-page" data-theme-scope="default"><main class="cut-shell"><header class="cut-top"><div><span class="cut-tag">Admin · Leltár</span><h1>Szabászat leltár</h1></div><a href="{ADMIN_INVENTORY_GROUP_ROUTE}">Vissza a modulokhoz</a></header>{notice}{start_html}{active_html}{_render_catalog_editor(catalog)}<section class="cut-panel cut-history"><h2>Lezárt leltárak</h2><div class="cut-table-wrap"><table><thead><tr><th>Dátum</th><th>Bútorlap</th><th>Munkalap</th><th>Falipanel</th><th>Lezárva</th></tr></thead><tbody>{history_rows}</tbody></table></div></section></main></body></html>'''
    return body.encode("utf-8")


def render_worker_page() -> bytes:
    state = load_state()
    session = state.get("active") if isinstance(state.get("active"), dict) else None
    if session is None:
        content = '<section class="cut-panel cut-empty"><h2>Nincs nyitott szabászati leltár</h2><p>A kezelőfelületen előbb meg kell nyitni egy leltári napot.</p></section>'
    else:
        summary = session_summary(session)
        content = f'''<section class="cut-panel cut-work" data-cut-root data-state-route="{CUTTING_INVENTORY_STATE_ROUTE}">
          <div class="cut-work-head"><div><span class="cut-tag">Nyitott · {_display_date(session.get('inventory_date'))}</span><h2>Anyagok felmérése</h2></div><strong><span data-progress>{summary['all_checked']}/{summary['all_rows']}</span> kész</strong></div>
          <nav class="cut-tabs"><button class="is-active" data-tab="boards">Bútorlap</button><button data-tab="worktops">Munkalap</button><button data-tab="wall_panels">Falipanel</button></nav>
          <label class="cut-search"><span>Keresés</span><input type="search" data-cut-search placeholder="Szín vagy típus…" /></label>
          <section data-section="boards">{_render_board_rows(session.get('boards', []), session.get('board_sizes', _legacy_board_sizes()))}</section>
          <section data-section="worktops" hidden>{_render_piece_rows('worktops', session.get('worktops', []))}</section>
          <section data-section="wall_panels" hidden>{_render_piece_rows('wall_panels', session.get('wall_panels', []))}</section>
        </section>'''
    page = f'''<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Divian-HUB | Szabászat leltár</title><link rel="stylesheet" href="/styles.css"><style>{_styles()}</style></head><body class="cut-page" data-theme-scope="default"><main class="cut-shell"><header class="cut-top"><div><span class="cut-tag">Gyártás · Leltár</span><h1>Szabászat leltár</h1></div><a href="{PRODUCTION_INVENTORY_GROUP_ROUTE}">Vissza a modulokhoz</a></header>{content}</main>{_script()}</body></html>'''
    return page.encode("utf-8")


def _new_session(inventory_date: str, catalog: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    board_sizes = [dict(item) for item in catalog.get("board_sizes", [])]
    return {
        "session_id": secrets.token_hex(6), "inventory_date": inventory_date, "status": "open",
        "created_at": now, "updated_at": now, "closed_at": "",
        "board_sizes": board_sizes,
        "boards": [{"row_id": item["id"], "name": item["name"], "counts": {size["id"]: "" for size in board_sizes}, "checked": False} for item in catalog.get("boards", [])],
        "worktops": [{"row_id": item["id"], "name": item["name"], "pieces": [], "checked": False} for item in catalog.get("worktops", [])],
        "wall_panels": [{"row_id": item["id"], "name": item["name"], "unit": item.get("unit", "m"), "width_mm": item.get("width_mm", WALL_PANEL_WIDTH_M * 1000), "pieces": [], "checked": False} for item in catalog.get("wall_panels", [])],
    }


def _render_board_rows(rows: list, board_sizes: list) -> str:
    headers = "".join(f'<span>{html.escape(str(item.get("label", "")))}</span>' for item in board_sizes)
    cards = "".join(_render_board_row(row, board_sizes) for row in rows if isinstance(row, dict))
    count = len(board_sizes)
    return f'<div class="cut-board-grid" style="--board-size-count:{count}"><div class="cut-board-legend"><span>Szín</span>{headers}<span>Összesen</span><span>Állapot</span></div><div class="cut-rows">{cards}</div></div>'


def _render_board_row(row: dict, board_sizes: list) -> str:
    inputs = "".join(f'<input data-board-count data-size-key="{html.escape(str(item.get("id", "")), quote=True)}" inputmode="numeric" min="0" step="1" value="{html.escape(str(row.get("counts", {}).get(item.get("id"), "")), quote=True)}" placeholder="0" aria-label="{html.escape(str(item.get("label", "")), quote=True)} darabszám" />' for item in board_sizes)
    return f'''<article class="cut-row cut-board-row{' is-checked' if row.get('checked') else ''}" data-cut-row data-category="boards" data-row-id="{row['row_id']}" data-search="{html.escape(str(row.get('name', '')).casefold(), quote=True)}"><strong>{html.escape(str(row.get('name', '')))}</strong>{inputs}<b><span data-row-total>{_format_decimal(_row_total('boards', row, board_sizes))}</span> m²</b>{_check_button(row)}</article>'''


def _render_piece_rows(category: str, rows: list) -> str:
    cards = "".join(_render_piece_row(category, row) for row in rows if isinstance(row, dict))
    return f'<div class="cut-piece-help">Minden darab hosszát külön, egész milliméterben add meg.</div><div class="cut-rows">{cards}</div>'


def _render_piece_row(category: str, row: dict) -> str:
    unit = "m²" if row.get("unit") == "m2" else "m"
    pieces = "".join(_piece_chip(piece) for piece in row.get("pieces", []) if isinstance(piece, dict)) or '<span class="cut-no-pieces" data-no-pieces>Nincs felvett darab</span>'
    return f'''<article class="cut-row cut-piece-row{' is-checked' if row.get('checked') else ''}" data-cut-row data-category="{category}" data-row-id="{row['row_id']}" data-search="{html.escape(str(row.get('name', '')).casefold(), quote=True)}"><div class="cut-piece-name"><strong>{html.escape(str(row.get('name', '')))}</strong><b><span data-row-total>{_format_decimal(_row_total(category, row))}</span> {unit}</b></div><div class="cut-pieces" data-piece-list>{pieces}</div><form data-add-piece><label><input name="length_mm" inputmode="numeric" placeholder="Méret mm-ben" required /><i>mm</i></label><button type="submit">Hozzáadás</button></form>{_check_button(row)}<div class="cut-row-error" data-row-error></div></article>'''


def _piece_chip(piece: dict) -> str:
    return f'<span class="cut-piece" data-piece-id="{html.escape(str(piece.get("piece_id", "")), quote=True)}"><b>{int(piece.get("length_mm", 0))} mm</b><button type="button" data-delete-piece aria-label="Méret törlése">×</button></span>'


def _check_button(row: dict) -> str:
    return f'<button type="button" class="cut-check" data-check-row aria-pressed="{str(bool(row.get("checked"))).lower()}">{"✓ Kész" if row.get("checked") else "Készre"}</button>'


def _history_row(session: dict) -> str:
    summary = session.get("summary") if isinstance(session.get("summary"), dict) else session_summary(session)
    return f'''<tr><td>{_display_date(session.get('inventory_date'))}</td><td>{summary['boards']['total']} m²</td><td>{summary['worktops']['total']} m</td><td>{summary['wall_panels']['checked']}/{summary['wall_panels']['rows']} tétel</td><td>{html.escape(str(session.get('closed_at', '')).replace('T', ' '))}</td></tr>'''


def _row_total(category: str, row: dict, board_sizes: list | None = None) -> float:
    if category == "boards":
        counts = row.get("counts", {})
        sizes = board_sizes if isinstance(board_sizes, list) else _legacy_board_sizes()
        return sum(
            (_parse_non_negative_integer(counts.get(str(item.get("id", "")))) or 0)
            * int(item.get("width_mm", 0)) * int(item.get("height_mm", 0)) / 1_000_000
            for item in sizes if isinstance(item, dict)
        )
    length_m = sum(int(piece.get("length_mm", 0) or 0) for piece in row.get("pieces", []) if isinstance(piece, dict)) / 1000
    panel_width_m = float(row.get("width_mm", WALL_PANEL_WIDTH_M * 1000) or 0) / 1000
    return length_m * panel_width_m if category == "wall_panels" and row.get("unit") == "m2" else length_m


def _find_row(session: dict, category: str, row_id: object) -> dict | None:
    if category not in {"boards", "worktops", "wall_panels"}:
        return None
    clean_id = str(row_id or "").strip()
    return next((row for row in session.get(category, []) if isinstance(row, dict) and row.get("row_id") == clean_id), None)


def _row_id(category: str, name: str) -> str:
    return hashlib.sha1(f"{category}|{name}".encode("utf-8")).hexdigest()[:16]


def _legacy_board_sizes() -> list[dict]:
    return [{"id": key, "label": label, "width_mm": width, "height_mm": height} for key, label, width, height in BOARD_SIZES]


def _default_catalog() -> dict:
    return {
        "board_sizes": _legacy_board_sizes(),
        "boards": [{"id": _row_id("boards", name), "name": name} for name in BOARD_NAMES],
        "worktops": [{"id": _row_id("worktops", name), "name": name} for name in WORKTOP_NAMES],
        "wall_panels": [{"id": _row_id("wall_panels", name), "name": name, "unit": unit, "width_mm": int(WALL_PANEL_WIDTH_M * 1000)} for name, unit in WALL_PANEL_ITEMS],
    }


def _sync_active_session(session: dict, catalog: dict) -> None:
    sizes = [dict(item) for item in catalog.get("board_sizes", []) if isinstance(item, dict)]
    size_ids = [str(item.get("id", "")) for item in sizes]
    session["board_sizes"] = sizes
    for category in ("boards", "worktops", "wall_panels"):
        existing = {str(row.get("row_id", "")): row for row in session.get(category, []) if isinstance(row, dict)}
        synced = []
        for item in catalog.get(category, []):
            item_id = str(item.get("id", ""))
            row = existing.get(item_id)
            if row is None:
                row = {"row_id": item_id, "name": item.get("name", ""), "checked": False}
                if category == "boards":
                    row["counts"] = {}
                else:
                    row["pieces"] = []
            row["name"] = item.get("name", "")
            if category == "boards":
                old_counts = row.get("counts", {})
                row["counts"] = {size_id: old_counts.get(size_id, "") for size_id in size_ids}
            elif category == "wall_panels":
                row["unit"] = item.get("unit", "m")
                row["width_mm"] = item.get("width_mm", WALL_PANEL_WIDTH_M * 1000)
            synced.append(row)
        session[category] = synced


def _save_catalog(catalog: dict) -> None:
    _runtime_dir.mkdir(parents=True, exist_ok=True)
    target = _runtime_dir / "catalog.json"
    temporary = _runtime_dir / "catalog.tmp"
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _parse_non_negative_integer(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text.replace(",", "."))
    except ValueError:
        return None
    return int(parsed) if math.isfinite(parsed) and parsed >= 0 and parsed.is_integer() else None


def _parse_positive_integer(value: object) -> int | None:
    parsed = _parse_non_negative_integer(value)
    return parsed if parsed is not None and parsed > 0 else None


def _format_decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _display_date(value: object) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%Y.%m.%d.")
    except ValueError:
        return html.escape(str(value or "–"))


def _save_state(state: dict) -> None:
    _runtime_dir.mkdir(parents=True, exist_ok=True)
    target = _runtime_dir / "state.json"
    temporary = _runtime_dir / "state.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _render_catalog_editor(catalog: dict) -> str:
    return f'''<section class="cut-panel cut-catalog">
      <div class="cut-catalog-head"><div><span class="cut-tag">Törzsadatok</span><h2>Leltári tételek szerkesztése</h2><p>A módosítások a nyitott leltárban azonnal megjelennek. A lezárt leltárak nem változnak.</p></div></div>
      {_render_size_editor(catalog.get('board_sizes', []))}
      {_render_item_editor('Bútorlapok', 'boards', catalog.get('boards', []))}
      {_render_item_editor('Munkalapok', 'worktops', catalog.get('worktops', []))}
      {_render_item_editor('Falipanelek', 'wall_panels', catalog.get('wall_panels', []), show_unit=True)}
    </section>'''


def _render_size_editor(items: list) -> str:
    rows = "".join(
        f'''<form class="cut-edit-row cut-size-edit" method="post" action="{CUTTING_INVENTORY_CATALOG_ROUTE}">
          <input type="hidden" name="action" value="save_size"><input type="hidden" name="item_id" value="{html.escape(str(item.get('id', '')), quote=True)}">
          <label><span>Szélesség</span><input name="width_mm" inputmode="numeric" value="{int(item.get('width_mm', 0))}" required><i>mm</i></label>
          <label><span>Magasság</span><input name="height_mm" inputmode="numeric" value="{int(item.get('height_mm', 0))}" required><i>mm</i></label>
          <button type="submit">Mentés</button><button class="cut-delete" type="submit" name="action" value="delete_size" onclick="return confirm('Biztosan törlöd ezt a méretoszlopot?')">Törlés</button>
        </form>'''
        for item in items if isinstance(item, dict)
    )
    add = f'''<form class="cut-edit-row cut-size-edit cut-add-row" method="post" action="{CUTTING_INVENTORY_CATALOG_ROUTE}"><input type="hidden" name="action" value="save_size"><label><span>Új szélesség</span><input name="width_mm" inputmode="numeric" placeholder="pl. 2800" required><i>mm</i></label><label><span>Új magasság</span><input name="height_mm" inputmode="numeric" placeholder="pl. 400" required><i>mm</i></label><button type="submit">Méret hozzáadása</button></form>'''
    return f'<details class="cut-editor" open><summary>Bútorlapméretek · oszlopok <b>{len(items)}</b></summary><div class="cut-edit-list">{rows}{add}</div></details>'


def _render_item_editor(title: str, category: str, items: list, show_unit: bool = False) -> str:
    def unit_select(item: dict, new: bool = False) -> str:
        if not show_unit:
            return ""
        unit = str(item.get("unit", "m")) if not new else "m"
        return f'''<label><span>Elszámolás</span><select name="unit"><option value="m"{' selected' if unit == 'm' else ''}>folyóméter</option><option value="m2"{' selected' if unit == 'm2' else ''}>négyzetméter (m²)</option></select></label>'''

    def width_input(item: dict, new: bool = False) -> str:
        if not show_unit:
            return ""
        width = int(item.get("width_mm", WALL_PANEL_WIDTH_M * 1000)) if not new else int(WALL_PANEL_WIDTH_M * 1000)
        return f'''<label><span>Panel szélessége</span><input name="width_mm" inputmode="numeric" value="{width}" required><i>mm</i></label>'''

    rows = "".join(
        f'''<form class="cut-edit-row{' has-unit' if show_unit else ''}" method="post" action="{CUTTING_INVENTORY_CATALOG_ROUTE}">
          <input type="hidden" name="action" value="save_item"><input type="hidden" name="category" value="{category}"><input type="hidden" name="item_id" value="{html.escape(str(item.get('id', '')), quote=True)}">
          <label><span>Megnevezés</span><input name="name" value="{html.escape(str(item.get('name', '')), quote=True)}" required></label>{unit_select(item)}{width_input(item)}
          <button type="submit">Mentés</button><button class="cut-delete" type="submit" name="action" value="delete_item" onclick="return confirm('Biztosan törlöd ezt a tételt?')">Törlés</button>
        </form>'''
        for item in items if isinstance(item, dict)
    )
    add = f'''<form class="cut-edit-row cut-add-row{' has-unit' if show_unit else ''}" method="post" action="{CUTTING_INVENTORY_CATALOG_ROUTE}"><input type="hidden" name="action" value="save_item"><input type="hidden" name="category" value="{category}"><label><span>Új megnevezés</span><input name="name" placeholder="Új tétel neve" required></label>{unit_select(dict(), new=True)}{width_input(dict(), new=True)}<button type="submit">Tétel hozzáadása</button></form>'''
    return f'<details class="cut-editor"><summary>{html.escape(title)} <b>{len(items)}</b></summary><div class="cut-edit-list">{rows}{add}</div></details>'


def _styles() -> str:
    return """
    :root{--green:#0f766e;--ink:#0f172a;--muted:#64748b;--line:#dbe4ea}*{box-sizing:border-box}.cut-page{margin:0;background:#f4f7f8;color:var(--ink);font-family:Manrope,Arial,sans-serif}.cut-shell{width:min(1500px,calc(100% - 24px));margin:12px auto 40px;display:grid;gap:14px}.cut-top,.cut-panel{background:#fff;border:1px solid rgba(15,23,42,.08);border-radius:24px;box-shadow:0 18px 45px rgba(15,23,42,.07)}.cut-top{display:flex;justify-content:space-between;align-items:center;padding:18px 22px}.cut-top h1,.cut-panel h2{margin:5px 0 0;font:800 1.45rem/1.1 "Space Grotesk",sans-serif}.cut-top a{color:var(--ink);text-decoration:none;font-weight:900}.cut-tag{color:var(--green);font-size:.74rem;font-weight:900;text-transform:uppercase;letter-spacing:.07em}.cut-notice{padding:13px 16px;border-radius:16px;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;font-weight:800}.cut-notice.is-success{background:#ecfdf5;color:#047857;border-color:#bbf7d0}.cut-start,.cut-active{display:flex;justify-content:space-between;align-items:end;gap:20px;padding:22px}.cut-start form,.cut-admin-actions{display:flex;gap:9px;align-items:center}.cut-start input,.cut-start button,.cut-admin-actions a,.cut-admin-actions button{min-height:44px;padding:0 15px;border-radius:13px;border:1px solid var(--line);font:800 .9rem Manrope}.cut-start button,.cut-admin-actions button{background:var(--green);border-color:var(--green);color:#fff;cursor:pointer}.cut-admin-actions a{display:inline-flex;align-items:center;color:var(--ink);text-decoration:none}.cut-active p,.cut-empty p{margin:7px 0 0;color:var(--muted)}.cut-empty,.cut-history{padding:24px}.cut-table-wrap{margin-top:14px;overflow:auto}.cut-history table{width:100%;border-collapse:collapse}.cut-history th,.cut-history td{padding:11px 12px;border-bottom:1px solid #eef2f7;text-align:left}.cut-work{padding:16px}.cut-work-head{display:flex;justify-content:space-between;gap:15px;align-items:start}.cut-work-head>strong{padding:9px 12px;border-radius:999px;background:#ccfbf1;color:#115e59}.cut-tabs{display:flex;gap:6px;margin-top:14px;padding:5px;border-radius:14px;background:#f1f5f9;width:max-content}.cut-tabs button{min-height:38px;padding:0 15px;border:0;border-radius:10px;background:transparent;font-weight:900;cursor:pointer}.cut-tabs button.is-active{background:var(--green);color:#fff}.cut-search{display:flex;align-items:center;gap:10px;margin:12px 0;color:var(--muted);font-size:.75rem;font-weight:900;text-transform:uppercase}.cut-search input{width:min(420px,100%);height:40px;padding:0 13px;border:1px solid var(--line);border-radius:999px;font:800 .9rem Manrope;text-transform:none}.cut-board-grid{min-width:calc(390px + var(--board-size-count)*86px)}.cut-board-legend,.cut-board-row{display:grid;grid-template-columns:minmax(160px,1.6fr) repeat(var(--board-size-count),minmax(78px,.7fr)) minmax(90px,.8fr) 96px;gap:7px;align-items:center}.cut-board-legend{padding:0 10px 7px;color:var(--muted);font-size:.7rem;font-weight:900;text-align:center}.cut-board-legend span:first-child{text-align:left}.cut-rows{display:grid;gap:6px}.cut-row{border:1px solid var(--line);border-radius:14px;background:#fff}.cut-board-row{padding:7px 9px}.cut-board-row input{width:100%;height:36px;padding:0 7px;border:1px solid var(--line);border-radius:9px;text-align:center;font-weight:900}.cut-board-row>b{text-align:center;white-space:nowrap}.cut-row.is-checked{background:#f0fdf4;border-color:#86efac}.cut-check{min-width:0;min-height:36px;padding:0 7px;border:1px solid #a7f3d0;border-radius:10px;background:#ecfdf5;color:#047857;font-weight:900;white-space:nowrap;cursor:pointer}.cut-row.is-checked .cut-check{background:#16a34a;color:#fff}.cut-piece-help{margin-bottom:8px;color:var(--muted);font-size:.82rem}.cut-piece-row{position:relative;display:grid;grid-template-columns:minmax(190px,1.25fr) minmax(220px,2fr) minmax(250px,1.4fr) 96px;gap:8px;align-items:center;padding:8px 9px}.cut-piece-name strong,.cut-piece-name b{display:block}.cut-piece-name b{margin-top:3px;color:var(--green)}.cut-pieces{display:flex;gap:5px;overflow-x:auto}.cut-no-pieces{color:#94a3b8;font-size:.78rem}.cut-piece{display:flex;align-items:center;gap:4px;flex:0 0 auto;padding:5px 5px 5px 9px;border-radius:9px;background:#ecfdf5;border:1px solid #bbf7d0;font-size:.78rem}.cut-piece button{width:24px;height:24px;border:0;border-radius:7px;background:#fff;color:#dc2626;cursor:pointer}.cut-piece-row form{display:grid;grid-template-columns:1fr auto;gap:6px}.cut-piece-row form label{display:flex;align-items:center;border:1px solid var(--line);border-radius:10px;overflow:hidden}.cut-piece-row form input{width:100%;min-width:0;height:36px;padding:0 8px;border:0;outline:0;font-weight:900}.cut-piece-row form i{padding-right:8px;color:var(--muted);font-style:normal}.cut-piece-row form>button{border:0;border-radius:10px;background:var(--green);color:#fff;font-weight:900;cursor:pointer}.cut-row-error{position:absolute;right:10px;bottom:-5px;color:#b91c1c;font-size:.72rem}.cut-row[hidden]{display:none!important}.cut-catalog{padding:22px}.cut-catalog-head p{margin:7px 0 15px;color:var(--muted)}.cut-editor{border-top:1px solid #e8eef2}.cut-editor summary{padding:14px 3px;font-weight:900;cursor:pointer}.cut-editor summary b{display:inline-grid;min-width:26px;height:26px;margin-left:5px;place-items:center;border-radius:99px;background:#ccfbf1;color:#115e59;font-size:.75rem}.cut-edit-list{display:grid;gap:6px;padding:0 0 14px}.cut-edit-row{display:grid;grid-template-columns:minmax(220px,1fr) 88px 78px;gap:7px;align-items:end;padding:7px;border:1px solid var(--line);border-radius:13px;background:#f8fafc}.cut-size-edit{grid-template-columns:minmax(190px,1fr) minmax(150px,.55fr) 88px 78px}.cut-edit-row.has-unit{grid-template-columns:minmax(190px,1fr) minmax(140px,.5fr) minmax(150px,.5fr) 88px 78px}.cut-edit-row label{display:grid;gap:3px;position:relative}.cut-edit-row label span{color:var(--muted);font-size:.68rem;font-weight:900;text-transform:uppercase}.cut-edit-row input,.cut-edit-row select,.cut-edit-row button{width:100%;height:38px;border:1px solid var(--line);border-radius:9px;background:#fff;padding:0 10px;font:800 .82rem Manrope}.cut-edit-row label i{position:absolute;right:10px;bottom:10px;color:var(--muted);font-style:normal;font-size:.75rem}.cut-edit-row button{background:var(--green);border-color:var(--green);color:#fff;cursor:pointer}.cut-edit-row .cut-delete{background:#fff;color:#b91c1c;border-color:#fecaca}.cut-add-row{border-style:dashed;background:#f0fdfa}.cut-add-row button{grid-column:auto / span 1}@media(max-width:1000px){.cut-shell{width:calc(100% - 12px);margin:6px auto 24px}.cut-work{padding:10px}.cut-board-legend,.cut-board-row{grid-template-columns:minmax(140px,1.4fr) repeat(var(--board-size-count),minmax(68px,.7fr)) 85px 78px}.cut-piece-row{grid-template-columns:minmax(160px,1.1fr) minmax(160px,1.5fr) minmax(220px,1.4fr) 78px}.cut-piece-row{min-width:760px}.cut-work section{overflow-x:auto}.cut-start,.cut-active{align-items:flex-start}.cut-admin-actions{flex-wrap:wrap}}@media(max-width:700px){.cut-edit-row,.cut-edit-row.has-unit,.cut-size-edit{grid-template-columns:1fr 1fr}.cut-edit-row label:first-of-type{grid-column:1/-1}.cut-size-edit label:first-of-type{grid-column:auto}.cut-edit-row button{grid-column:auto}}@media(max-width:600px){.cut-top{padding:15px}.cut-top h1{font-size:1.2rem}.cut-start,.cut-active{display:grid;padding:17px}.cut-start form{display:grid}.cut-tabs{width:100%}.cut-tabs button{flex:1;padding:0 8px}.cut-search{display:grid}.cut-history,.cut-catalog{padding:15px}}
    """


def _script() -> str:
    return f'''<script>(()=>{{const root=document.querySelector('[data-cut-root]');if(!root)return;const route=root.dataset.stateRoute;const post=(row,data)=>{{data.set('category',row.dataset.category);data.set('row_id',row.dataset.rowId);return fetch(route,{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}},body:data.toString(),credentials:'same-origin',cache:'no-store'}}).then(async r=>{{const p=await r.json().catch(()=>({{error:'A mentés nem sikerült.'}}));if(!r.ok)throw new Error(p.error||'A mentés nem sikerült.');return p;}})}};const update=(row,p)=>{{row.querySelector('[data-row-total]').textContent=p.row.total;row.classList.toggle('is-checked',p.row.checked);const check=row.querySelector('[data-check-row]');check.setAttribute('aria-pressed',String(p.row.checked));check.textContent=p.row.checked?'✓ Kész':'Készre';root.querySelector('[data-progress]').textContent=p.summary.all_checked+'/'+p.summary.all_rows;if(p.row.pieces){{const list=row.querySelector('[data-piece-list]');list.replaceChildren(...p.row.pieces.map(piece=>{{const chip=document.createElement('span');chip.className='cut-piece';chip.dataset.pieceId=piece.piece_id;chip.innerHTML='<b></b><button type="button" data-delete-piece aria-label="Méret törlése">×</button>';chip.querySelector('b').textContent=piece.length_mm+' mm';return chip;}}));if(!p.row.pieces.length){{const empty=document.createElement('span');empty.className='cut-no-pieces';empty.dataset.noPieces='';empty.textContent='Nincs felvett darab';list.append(empty);}}}}}};root.querySelectorAll('[data-cut-row]').forEach(row=>{{const error=row.querySelector('[data-row-error]');row.querySelectorAll('[data-board-count]').forEach(input=>input.addEventListener('change',()=>{{const data=new URLSearchParams();data.set('action','set_board_count');data.set('size_key',input.dataset.sizeKey);data.set('value',input.value);post(row,data).then(p=>update(row,p)).catch(e=>{{if(error)error.textContent=e.message;}});}}));row.querySelector('[data-add-piece]')?.addEventListener('submit',e=>{{e.preventDefault();const form=e.currentTarget;const data=new URLSearchParams(new FormData(form));data.set('action','add_piece');post(row,data).then(p=>{{update(row,p);form.reset();if(error)error.textContent='';}}).catch(err=>{{if(error)error.textContent=err.message;}});}});row.querySelector('[data-piece-list]')?.addEventListener('click',e=>{{const button=e.target.closest('[data-delete-piece]');if(!button)return;const data=new URLSearchParams();data.set('action','delete_piece');data.set('piece_id',button.closest('[data-piece-id]').dataset.pieceId);post(row,data).then(p=>update(row,p)).catch(err=>{{if(error)error.textContent=err.message;}});}});row.querySelector('[data-check-row]').addEventListener('click',e=>{{const data=new URLSearchParams();data.set('action','toggle_checked');data.set('checked',e.currentTarget.getAttribute('aria-pressed')==='true'?'0':'1');post(row,data).then(p=>update(row,p)).catch(err=>{{if(error)error.textContent=err.message;}});}});}});const tabs=root.querySelectorAll('[data-tab]');tabs.forEach(button=>button.addEventListener('click',()=>{{tabs.forEach(item=>item.classList.toggle('is-active',item===button));root.querySelectorAll('[data-section]').forEach(section=>section.hidden=section.dataset.section!==button.dataset.tab);root.querySelector('[data-cut-search]').value='';root.querySelectorAll('[data-cut-row]').forEach(row=>row.hidden=false);}}));root.querySelector('[data-cut-search]').addEventListener('input',e=>{{const q=e.target.value.trim().toLocaleLowerCase('hu-HU');root.querySelectorAll('[data-section]:not([hidden]) [data-cut-row]').forEach(row=>row.hidden=q&&!row.dataset.search.includes(q));}});}})();</script>'''
