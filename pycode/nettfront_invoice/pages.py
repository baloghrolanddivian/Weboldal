"""HTML pages for the NettFront invoice receiving skeleton."""

from __future__ import annotations

import html
import json
import urllib.parse

from .routes import (
    NETTFRONT_INVOICE_ADMIN_EXPORT_PREFIX,
    NETTFRONT_INVOICE_ADMIN_REOPEN_PREFIX,
    NETTFRONT_INVOICE_ADMIN_ROUTE,
    NETTFRONT_INVOICE_CHECK_ROUTE,
    NETTFRONT_INVOICE_CLOSE_PREFIX,
    NETTFRONT_INVOICE_IMPORT_ROUTE,
    NETTFRONT_INVOICE_OPEN_ROUTE,
    NETTFRONT_INVOICE_CAMERA_PREFIX,
    NETTFRONT_INVOICE_READ_PREFIX,
    NETTFRONT_INVOICE_ROUTE,
    NETTFRONT_INVOICE_SCAN_PREFIX,
    NETTFRONT_INVOICE_VIEW_PREFIX,
    NETTFRONT_INVOICE_XML_PREFIX,
)


def _e(value: object) -> str:
    return html.escape(str(value or ""))


MODEL_LABELS = {"ANT": "Antónia", "LU": "Laura", "ZI": "Zille"}

FRONT_TYPE_LABELS = {
    "NFAU": "Üveges",
    "NFAB": "Blende",
}

COLOR_LABELS = {
    "FEA": "Matt Fehér",
    "GFA": "Matt Grafit",
    "SZA": "Matt Szürke",
    "PRA": "Matt Provance",
    "KAF": "Matt Kasmír",
    "ANMM": "Mf. Antracit",
    "BGMM": "Mf. Beige",
    "CPMM": "Mf. Capuccino",
    "FFMM": "Mf. Fehér",
    "ARF": "Artizán Tölgy",
    "SOF": "Sonoma Tölgy",
    "WTF": "Wotan Tölgy",
    "BGA": "Matt Beige",
    "CPA": "Matt Capuccino",
    "BGF": "Beige",
    "FER": "Rusztikus Fehér",
    "BGAS": "SM. Beige",
    "FEAS": "SM. Fehér",
    "GFAS": "SM. Grafit",
    "PRAS": "SM Provance",
}


def _code_parts(item: dict) -> tuple[str, str, str]:
    parts = str(item.get("kod", "") or item.get("our_code", "")).split("_")
    prefix = parts[0].upper() if parts else ""
    model = parts[1].upper() if len(parts) > 1 else ""
    color = parts[2].upper() if len(parts) > 2 else ""
    return prefix, model, color


def _display_model(item: dict) -> str:
    prefix, model, _color = _code_parts(item)
    model_label = MODEL_LABELS.get(model, str(item.get("termek", "")))
    type_label = FRONT_TYPE_LABELS.get(prefix, "")
    return " ".join(part for part in (model_label, type_label) if part)


def _display_color(item: dict) -> str:
    _prefix, _model, color = _code_parts(item)
    return COLOR_LABELS.get(color, str(item.get("szin", "")))


def invoice_item_display(item: dict, *, icn: str = "", quantity: object = "") -> dict[str, object]:
    """Return the user-facing fields for one camera-read invoice item."""
    return {
        "icn": str(icn),
        "model": _display_model(item),
        "size": str(item.get("meret", "")),
        "color": _display_color(item),
        "quantity": quantity,
        "our_code": str(item.get("our_code", "")),
        "our_description": str(item.get("our_description", "")),
    }


def _layout(title: str, content: str) -> bytes:
    return f"""<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Divian-HUB | {_e(title)}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet"><link rel="stylesheet" href="/styles.css"></head>
<body class="nettfront-invoice-page"><div class="site-shell"><div class="ambient ambient-one"></div><div class="ambient ambient-two"></div><div class="grid-overlay"></div>
<header class="topbar"><a class="brand" href="/"><span class="brand-mark"></span><span class="brand-text"><strong>Divian-HUB</strong><small>Nettfront számla</small></span></a><nav class="nav"><a href="/">Vissza a modulokhoz</a></nav></header>
<main class="nf-stage"><header class="nf-page-head"><div><span class="nf-eyebrow">NettFront workflow</span><h1>{_e(title)}</h1></div></header>{content}</main></div><script src="/script.js"></script></body></html>""".encode("utf-8")


def render_home(records: list[dict], message: str = "") -> bytes:
    opened = [row for row in records if row.get("status") == "opened"]
    options = "".join(f'<option value="{_e(row.get("invoice_code"))}">{_e(row.get("invoice_code"))} · {_e(row.get("created_at"))}</option>' for row in opened)
    notice = f'<div class="notice">{_e(message)}</div>' if message else ""
    content = f"""{notice}<section class="nf-grid"><article class="nf-card"><h2>Számla lekérése</h2><p class="muted">Az API-kapcsolat előkészítve; a külső végpont még TODO.</p><label>Számlakód<input name="invoice_code" placeholder="NF2026-…" disabled></label><button disabled>Lekérés API-ból</button></article>
<article class="nf-card"><h2>Ideiglenes batch XML-feltöltés</h2><p class="muted">Az API elkészültéig a batch XML közvetlenül hozza létre a számlát és az ICN-kapcsolatokat.</p><form action="{NETTFRONT_INVOICE_IMPORT_ROUTE}" method="post" enctype="multipart/form-data" target="_blank"><label>Azonosító / név<input name="operator" required maxlength="100" autocomplete="name"></label><label>Teljes számlakód<input name="invoice_code" placeholder="NF2026-34056" required maxlength="80"></label><label>Számla dátuma<input type="date" name="invoice_date" required></label><label>NettFront batch XML<input type="file" name="batch_xml" accept=".xml,text/xml,application/xml" required></label><button>Feldolgozás és beolvasó megnyitása</button></form></article></section>
<section class="nf-card"><h2>Nyitott számlák</h2>{'<form action="'+NETTFRONT_INVOICE_OPEN_ROUTE+'" method="post" target="_blank"><label>Számla<select name="invoice_code" required><option value="">Válassz…</option>'+options+'</select></label><label>Azonosító / név<input name="operator" required maxlength="100"></label><button>Beolvasó megnyitása új ablakban</button></form>' if opened else '<p class="muted">Nincs nyitott számla.</p>'}<p><a class="nf-link" href="{NETTFRONT_INVOICE_CHECK_ROUTE}">Csak ellenőrzés / számlák megtekintése →</a></p></section>"""
    return _layout("Nettfront számla", content)


def _item_rows(record: dict) -> str:
    result = []
    for item in record.get("items", []):
        expected = int(item.get("expected_qty", 0) or 0)
        counted = int(item.get("counted_qty", 0) or 0)
        css = "bad" if item.get("missing_in_our_system") else ("warn" if counted != expected else "ok")
        description = _e(item.get("our_description")) or '<span class="muted">API TODO</span>'
        result.append(
            f'<tr><td>{_e(item.get("batch_id"))}</td><td>{_e(_display_model(item))}</td>'
            f'<td>{_e(item.get("meret"))}</td><td>{_e(_display_color(item))}</td>'
            f'<td>{expected}</td><td>{counted}</td><td class="{css}">{counted-expected:+d}</td>'
            f'<td>{_e(item.get("our_code"))}</td><td>{description}</td>'
            f'<td>{len(item.get("available_icns", []))}</td></tr>'
        )
    return "".join(result)


def render_invoice(record: dict, message: str = "", *, read_only: bool = False) -> bytes:
    code = str(record.get("invoice_code", ""))
    missing = len(record.get("missing_codes", []))
    mismatch = sum(1 for item in record.get("items", []) if int(item.get("counted_qty", 0) or 0) != int(item.get("expected_qty", 0) or 0))
    expected_total = sum(int(item.get("expected_qty", 0) or 0) for item in record.get("items", []))
    counted_total = sum(int(item.get("counted_qty", 0) or 0) for item in record.get("items", []))
    missing_quantity = sum(max(0, int(item.get("expected_qty", 0) or 0) - int(item.get("counted_qty", 0) or 0)) for item in record.get("items", []))
    overcounted_quantity = sum(max(0, int(item.get("counted_qty", 0) or 0) - int(item.get("expected_qty", 0) or 0)) for item in record.get("items", []))
    notice = f'<div class="notice">{_e(message)}</div>' if message else ""
    close = ""
    if record.get("status") == "opened" and not read_only:
        warning = '<p class="bad"><strong>Figyelem:</strong> eltérések vagy hiányzó saját kódok vannak.</p>' if mismatch or missing else ""
        close = f'''<section class="nf-card"><h2>Lezárás összefoglaló</h2>
<p>Számlakód: <strong>{_e(code)}</strong> · Rendelt: {len(record.get("items", []))} tétel / {expected_total} db · Beolvasva: {counted_total} db · Hiány: {missing_quantity} db · Túlszámolás: {overcounted_quantity} db · Eltérő tételek: {mismatch} · Sikertelen olvasások: {len(record.get("failed_reads", []))} · Saját rendszerből hiányzik: {missing}</p>
{warning}<form action="{NETTFRONT_INVOICE_CLOSE_PREFIX}/{urllib.parse.quote(code)}" method="post" onsubmit="return confirm('Biztosan lezárod ezt a számlát?')"><label>Lezáró azonosító / név<input name="operator" required maxlength="100"></label><button>Számla lezárása</button></form></section>'''
    mode_notice = '<div class="notice">Csak megtekintési mód: ezen az oldalon nem végezhető módosítás.</div>' if read_only else ""
    batch_xml = record.get("batch_xml", {}) if isinstance(record.get("batch_xml"), dict) else {}
    xml_summary = (
        f'<p class="ok">XML csatolva: {int(batch_xml.get("matched_line_count", 0))}/{int(batch_xml.get("line_count", 0))} sor, {int(batch_xml.get("icn_count", 0))} ICN.</p>'
        if batch_xml else '<p class="muted">Még nincs batch XML csatolva.</p>'
    )
    scanner_link = ""
    if record.get("status") == "opened" and not read_only and batch_xml:
        scanner_link = f'<a class="nf-button" href="{NETTFRONT_INVOICE_READ_PREFIX}/{urllib.parse.quote(code)}" target="_blank" rel="noopener">Automatikus beolvasó megnyitása</a>'
    history_rows = "".join(
        f'<tr><td>{_e(entry.get("time"))}</td><td>{_e(entry.get("user"))}</td><td>{_e(entry.get("icn"))}</td><td>{_e(entry.get("quantity"))}</td><td>{_e(entry.get("result"))}</td><td>{_e(entry.get("message"))}</td></tr>'
        for entry in reversed(record.get("scan_history", [])) if isinstance(entry, dict)
    )
    history_section = f'''<section class="nf-card"><h2>Teljes beolvasási előzmény</h2><div class="nf-scroll"><table><thead><tr><th>Idő</th><th>Felhasználó</th><th>ICN</th><th>Db</th><th>Eredmény</th><th>Üzenet</th></tr></thead><tbody>{history_rows}</tbody></table></div></section>''' if history_rows else ""
    content = f"""{notice}{mode_notice}<section class="nf-card"><span class="nf-pill">{_e(record.get('status'))}</span><h2>{_e(code)}</h2><p>Számla dátuma: {_e(record.get('invoice_date')) or 'nincs adat'} · Létrehozva: {_e(record.get('created_at'))} · Megnyitotta: {_e(record.get('opened_by'))}</p><p class="muted">Mentett fájl: {_e(record.get('saved_file_name'))}</p></section>
<section class="nf-card"><h2>Batch XML és ICN-k</h2>{xml_summary}</section>
<section class="nf-card"><h2>ICN beolvasás</h2><p class="muted">A beolvasás külön ablakban fut. A kamera automatikusan kapja a triggert; külön megerősítés nincs.</p>{scanner_link}</section>
<section class="nf-card"><h2>Számlatételek</h2><div class="nf-scroll"><table><thead><tr><th>Batch</th><th>Modell + fronttípus</th><th>Méret</th><th>Szín</th><th>Várt db</th><th>Olvasott db</th><th>Eltérés</th><th>Saját kód</th><th>Saját leírás</th><th>ICN-ek</th></tr></thead><tbody>{_item_rows(record)}</tbody></table></div></section>{history_section}{close}"""
    return _layout(f"Nettfront számla · {code}", content)


def render_reader(record: dict, initial_operator: str = "") -> bytes:
    """Render the focused, automatically-triggering camera reader window."""
    code = str(record.get("invoice_code", ""))
    endpoint = f"{NETTFRONT_INVOICE_CAMERA_PREFIX}/{urllib.parse.quote(code)}"
    initial_operator_json = json.dumps(str(initial_operator or ""), ensure_ascii=False).replace("<", "\\u003c")
    endpoint_json = json.dumps(endpoint).replace("<", "\\u003c")
    code_json = json.dumps(code, ensure_ascii=False).replace("<", "\\u003c")
    can_read_json = "true" if record.get("status") == "opened" else "false"
    return f'''<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beolvasás · {_e(code)}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&amp;family=Space+Grotesk:wght@500;600;700&amp;display=swap" rel="stylesheet"><link rel="stylesheet" href="/styles.css"></head><body class="nettfront-reader-page"><div class="site-shell"><div class="ambient ambient-one"></div><div class="ambient ambient-two"></div><div class="grid-overlay"></div><main class="reader"><header class="reader-head"><div><small>NETTFRONT SZÁMLA</small><h1>{_e(code)}</h1></div><button type="button" onclick="window.close()">Ablak bezárása</button></header>
<section id="identity-card" class="reader-card hidden"><h2>Beolvasó azonosítása</h2><p class="muted">Ezt csak egyszer kell megadni ebben a böngésző-munkamenetben.</p><form id="identity-form"><label>Név / azonosító<input id="operator-input" maxlength="100" required autocomplete="name"></label><p><button>Beolvasás indítása</button></p></form></section>
<section id="reader-card" class="reader-card hidden"><div class="reader-head"><div><h2>Automatikus kameraolvasás</h2><p class="muted">Felhasználó: <strong id="operator-label"></strong></p></div><label>Darabszám<input id="quantity" type="number" min="1" max="10000" value="1"></label></div><div id="status" class="status working" role="status" aria-live="assertive">Indítás…</div><p class="controls"><button id="pause" type="button">Szünet</button><button id="change-user" type="button">Felhasználó váltása</button></p></section>
<section id="item-card" class="reader-card hidden"><h2>Legutóbbi beolvasott tétel</h2><div class="grid"><div class="value"><small>ICN</small><strong id="item-icn">—</strong></div><div class="value"><small>Modell + fronttípus</small><strong id="item-model">—</strong></div><div class="value"><small>Méret</small><strong id="item-size">—</strong></div><div class="value"><small>Szín</small><strong id="item-color">—</strong></div><div class="value"><small>Darabszám</small><strong id="item-qty">—</strong></div><div class="value"><small>Saját kód</small><strong id="item-code">—</strong></div><div class="value"><small>Saját leírás</small><strong id="item-description">API TODO</strong></div></div></section>
</main></div><script src="/script.js"></script><script>
(() => {{
  const endpoint = {endpoint_json};
  const invoiceCode = {code_json};
  const canRead = {can_read_json};
  const operatorKey = "nettfront_invoice_operator";
  const initialOperator = {initial_operator_json};
  const identityCard = document.getElementById("identity-card");
  const readerCard = document.getElementById("reader-card");
  const status = document.getElementById("status");
  const pauseButton = document.getElementById("pause");
  let operator = initialOperator.trim() || sessionStorage.getItem(operatorKey) || "";
  let running = false;
  let inFlight = false;
  let retryTimer = 0;
  if (initialOperator) history.replaceState(null, "", location.pathname);

  function showIdentity() {{ running = false; clearTimeout(retryTimer); readerCard.classList.add("hidden"); identityCard.classList.remove("hidden"); document.getElementById("operator-input").value = operator; document.getElementById("operator-input").focus(); }}
  function setStatus(message, kind) {{ status.textContent = message; status.className = "status " + kind; }}
  function showItem(payload) {{
    if (!payload) return;
    document.getElementById("item-card").classList.remove("hidden");
    document.getElementById("item-icn").textContent = payload.icn || "—";
    document.getElementById("item-model").textContent = payload.model || "—";
    document.getElementById("item-size").textContent = payload.size || "—";
    document.getElementById("item-color").textContent = payload.color || "—";
    document.getElementById("item-qty").textContent = payload.quantity || "—";
    document.getElementById("item-code").textContent = payload.our_code || "—";
    document.getElementById("item-description").textContent = payload.our_description || "API TODO";
  }}
  function schedule(delay) {{ clearTimeout(retryTimer); if (running) retryTimer = setTimeout(trigger, delay); }}
  async function trigger() {{
    if (!running || inFlight) return;
    inFlight = true;
    setStatus("Kamera trigger elküldve — várakozás az ICN-re…", "working");
    try {{
      const response = await fetch(endpoint, {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{operator,quantity:document.getElementById("quantity").value,invoice_code:invoiceCode}})}});
      const payload = await response.json();
      const scan = payload.scan || {{}};
      setStatus(scan.message || payload.error || "Ismeretlen kamera-válasz.", scan.result === "success" ? "success" : scan.result === "warning" ? "warning" : "failed");
      showItem(payload.item);
      schedule(response.ok ? 700 : 1800);
    }} catch (error) {{
      setStatus("A modul nem érhető el. A beolvasás megállt, újrapróbálkozás folyamatban; ne folytasd kézzel.", "failed");
      schedule(2000);
    }} finally {{ inFlight = false; }}
  }}
  function start() {{
    operator = operator.trim(); if (!operator) return showIdentity();
    sessionStorage.setItem(operatorKey, operator); identityCard.classList.add("hidden"); readerCard.classList.remove("hidden"); document.getElementById("operator-label").textContent = operator; running = true; pauseButton.textContent = "Szünet"; trigger();
  }}
  document.getElementById("identity-form").addEventListener("submit", event => {{ event.preventDefault(); operator = document.getElementById("operator-input").value; start(); }});
  pauseButton.addEventListener("click", () => {{ running = !running; pauseButton.textContent = running ? "Szünet" : "Folytatás"; if (running) trigger(); else setStatus("A beolvasás szünetel.", "warning"); }});
  document.getElementById("change-user").addEventListener("click", () => {{ sessionStorage.removeItem(operatorKey); operator = ""; showIdentity(); }});
  window.addEventListener("beforeunload", () => clearTimeout(retryTimer));
  if (!canRead) {{ readerCard.classList.remove("hidden"); setStatus("Ez a számla le van zárva; a kamera nem indítható.", "failed"); pauseButton.disabled = true; }}
  else if (operator) start(); else showIdentity();
}})();
</script></body></html>'''.encode("utf-8")


def render_check(records: list[dict]) -> bytes:
    rows = "".join(f'<tr><td><a class="nf-link" href="{NETTFRONT_INVOICE_VIEW_PREFIX}/{urllib.parse.quote(str(row.get("invoice_code", "")))}?readonly=1">{_e(row.get("invoice_code"))}</a></td><td>{_e(row.get("created_at"))}</td><td>{_e(row.get("status"))}</td><td>{len(row.get("items", []))}</td></tr>' for row in records)
    return _layout("Nettfront számla ellenőrzés", f'<section class="nf-card"><p class="muted">Megtekintési nézet; módosítás nélkül.</p><div class="nf-scroll"><table><thead><tr><th>Kód</th><th>Létrehozva</th><th>Státusz</th><th>Tételek</th></tr></thead><tbody>{rows or "<tr><td colspan=4>Nincs rögzített számla.</td></tr>"}</tbody></table></div></section>')


def render_admin(records: list[dict], query: dict[str, str]) -> bytes:
    code_filter = str(query.get("code", "")).strip().lower()
    date_filter = str(query.get("date", "")).strip()
    status_filter = str(query.get("status", "")).strip()
    filtered = [row for row in records if (not code_filter or code_filter in str(row.get("invoice_code", "")).lower()) and (not date_filter or str(row.get("created_at", "")).startswith(date_filter)) and (not status_filter or row.get("status") == status_filter)]
    rows = []
    for row in filtered:
        code = str(row.get("invoice_code", "")); quoted = urllib.parse.quote(code)
        reopen = f'<form action="{NETTFRONT_INVOICE_ADMIN_REOPEN_PREFIX}/{quoted}" method="post"><input type="hidden" name="operator" value="admin"><button>Újranyitás</button></form>' if row.get("status") == "closed" else ""
        rows.append(f'<tr><td><a class="nf-link" href="{NETTFRONT_INVOICE_VIEW_PREFIX}/{quoted}">{_e(code)}</a></td><td>{_e(row.get("created_at"))}</td><td>{_e(row.get("status"))}</td><td>{len(row.get("items", []))} / {len(row.get("source_items", []))}</td><td><a class="nf-button" href="{NETTFRONT_INVOICE_ADMIN_EXPORT_PREFIX}/{quoted}">Excel</a>{reopen}</td></tr>')
    content = f"""<section class="nf-card"><form method="get" action="{NETTFRONT_INVOICE_ADMIN_ROUTE}" class="nf-grid"><label>Kód<input name="code" value="{_e(query.get('code'))}"></label><label>Dátum<input type="date" name="date" value="{_e(query.get('date'))}"></label><label>Státusz<select name="status"><option value="">Mind</option><option value="opened" {'selected' if status_filter=='opened' else ''}>Nyitott</option><option value="closed" {'selected' if status_filter=='closed' else ''}>Lezárt</option></select></label><div><button>Szűrés</button></div></form></section><section class="nf-card"><h2>Számlák</h2><p class="muted">Tételszám: összesített / eredeti forrássor. Az Excel mindkettőt és a teljes beolvasási előzményt tartalmazza.</p><div class="nf-scroll"><table><thead><tr><th>Kód</th><th>Dátum</th><th>Státusz</th><th>Tételszám</th><th>Műveletek</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan=5>Nincs találat.</td></tr>'}</tbody></table></div></section>"""
    return _layout("Admin · Nettfront számla", content)
