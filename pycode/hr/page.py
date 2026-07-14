"""HTML pages for the HR document generator."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

APP_ROUTE = "/apps/hr-dokumentumok"
CONFIRM_ROUTE = f"{APP_ROUTE}/confirm"
COMMON = '<link rel="stylesheet" href="/styles.css" /><script src="/script.js"></script><style>.hr-field option,.hr-table option{background:#09131c;color:#f3fbff}.hr-field select,.hr-table select{color-scheme:dark}.hr-table{min-width:3900px}.hr-table th{white-space:nowrap;min-width:180px}.hr-table td{min-width:180px}.hr-table input,.hr-table select{min-width:170px;min-height:42px;font-size:.92rem;line-height:1.35}.hr-table input[type=checkbox]{width:20px;min-width:20px;min-height:20px}.hr-table td:first-child{min-width:110px}.hr-table td:nth-child(2){min-width:220px}</style>'
HR_UI = '''<style>
.hr-panel { overflow: visible; }
.hr-actions .button { min-width: 230px; cursor: pointer; }
.hr-back-button { min-width: 0 !important; min-height: 38px !important; padding: 0 16px !important; font-size: .82rem; }
.hr-actions .primary-button { background: linear-gradient(135deg, var(--accent-warm), var(--accent)); color: #041017; font-weight: 800; box-shadow: 0 12px 28px rgba(67, 222, 207, .18); }
.hr-upload { display: grid; gap: 10px; max-width: 520px; }
.hr-upload input[type=file] { width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--panel-soft); color: var(--text); }
.hr-upload input[type=file]::file-selector-button { margin-right: 12px; padding: 9px 14px; border: 1px solid var(--border); border-radius: 999px; background: linear-gradient(135deg, var(--accent-warm), var(--accent)); color: #041017; font-weight: 800; cursor: pointer; }
.hr-table-scroll { width: 100%; overflow-x: auto; overflow-y: visible; border: 1px solid var(--border); border-radius: 14px; scrollbar-color: var(--accent) var(--panel-soft); }
.hr-table th:first-child, .hr-table td:first-child { width: 68px !important; min-width: 68px !important; max-width: 68px !important; padding-left: 12px; padding-right: 8px; }
.hr-table input[type=checkbox] { appearance: none; -webkit-appearance: none; display: grid; place-content: center; width: 20px !important; min-width: 20px !important; max-width: 20px; height: 20px; min-height: 20px !important; max-height: 20px; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: 5px; background: rgba(255,255,255,.06); cursor: pointer; }
.hr-table input[type=checkbox]::before { content: ''; width: 10px; height: 10px; transform: scale(0); clip-path: polygon(14% 44%, 0 59%, 39% 100%, 100% 16%, 84% 0, 37% 62%); background: #041017; transition: transform 120ms ease; }
.hr-table input[type=checkbox]:checked { border-color: var(--accent-warm); background: linear-gradient(135deg, var(--accent-warm), var(--accent)); }
.hr-table input[type=checkbox]:checked::before { transform: scale(1); }
.hr-table input[type=checkbox]:focus-visible { outline: 2px solid var(--accent-warm); outline-offset: 3px; }
.hr-table-scroll::-webkit-scrollbar, .hr-table-scrollbar::-webkit-scrollbar { height: 12px; }
.hr-table-scroll::-webkit-scrollbar-track, .hr-table-scrollbar::-webkit-scrollbar-track { background: var(--panel-soft); border-radius: 999px; }
.hr-table-scroll::-webkit-scrollbar-thumb, .hr-table-scrollbar::-webkit-scrollbar-thumb { background: linear-gradient(90deg, var(--accent), var(--accent-warm)); border: 2px solid var(--panel); border-radius: 999px; }
.hr-table-scrollbar { position: fixed; z-index: 30; left: 18px; right: 18px; bottom: 14px; display: none; height: 14px; padding: 0 2px; overflow-x: auto; overflow-y: hidden; border: 1px solid var(--border); border-radius: 999px; background: var(--panel); box-shadow: var(--shadow); scrollbar-color: var(--accent) var(--panel-soft); }
.hr-table-scrollbar > div { height: 1px; }
@media (max-width: 600px) { .hr-table-scrollbar { left: 10px; right: 10px; bottom: 10px; } .hr-actions .button { width: 100%; } }
.hr-hero, .hr-upload-card { position: relative; overflow: hidden; background: linear-gradient(180deg, var(--panel), var(--panel-strong)); border: 1px solid var(--border); border-radius: var(--radius-xl); box-shadow: var(--shadow); }
.hr-hero::before, .hr-upload-card::before { content: ''; position: absolute; inset: 0; background: linear-gradient(120deg, rgba(255,114,186,.14), transparent 34%), linear-gradient(180deg, transparent, rgba(255,193,224,.08)); pointer-events: none; }
.hr-hero { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 28px; align-items: center; padding: 38px 40px; min-height: 350px; }
.hr-hero-copy, .hr-hero-visual, .hr-upload-card > * { position: relative; z-index: 1; }
.hr-hero h1 { max-width: 700px; margin: 14px 0 16px; font-size: clamp(3.2rem, 7vw, 6rem); line-height: .98; letter-spacing: -.06em; }
.hr-hero h1 span { display: block; color: var(--accent); }
.hr-lead { max-width: 620px; color: var(--muted); font-size: 1.05rem; line-height: 1.65; }
.hr-hero-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 24px; }
.hr-hero-visual { display: grid; place-items: center; min-height: 230px; }
.hr-doc-stack { position: relative; width: 190px; height: 190px; transform: rotate(-5deg); }
.hr-doc { position: absolute; width: 122px; height: 164px; padding: 18px 14px; border: 1px solid var(--border); border-radius: 20px; background: linear-gradient(160deg, rgba(255,193,224,.22), rgba(62,16,47,.9)); box-shadow: var(--shadow); }
.hr-doc::before { content: ''; display: block; height: 10px; margin-bottom: 20px; border-radius: 999px; background: linear-gradient(90deg, var(--accent), var(--accent-warm)); }
.hr-doc::after { content: ''; display: block; height: 1px; margin: 15px 0; background: var(--line); box-shadow: 0 18px var(--line), 0 36px var(--line), 0 54px var(--line); }
.hr-doc:first-child { left: 0; top: 18px; transform: rotate(-8deg); }
.hr-doc:last-child { right: 0; top: 0; transform: rotate(8deg); }
.hr-doc-label { position: absolute; right: -12px; bottom: 0; padding: 8px 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--panel); color: var(--accent); font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.hr-upload-card { margin-top: 18px; padding: 26px 28px 30px; }
.hr-upload-card h2 { margin: 0 0 4px; font-size: 1.1rem; }
.hr-upload-card .hr-note { margin: 0 0 18px; }
.hr-upload-card form { display: grid; gap: 20px; width: min(100%, 760px); }
.hr-upload-card .hr-field { display: grid; gap: 8px; }
.hr-upload-card .hr-field label { font-size: .82rem; font-weight: 700; color: var(--text); }
.hr-upload-card .hr-upload input[type=file] { display: block; min-height: 64px; padding: 12px; }
.hr-upload-card .hr-actions { display: flex; align-items: center; gap: 12px; margin-top: 0; }
.hr-upload-card .hr-actions .button { min-height: 48px; }
@media(max-width: 760px) { .hr-hero { grid-template-columns: 1fr; padding: 28px; } .hr-hero-visual { min-height: 190px; } .hr-hero h1 { font-size: clamp(2.8rem, 13vw, 4.4rem); } }
</style><script>
document.addEventListener('DOMContentLoaded', function () {
  var scroller = document.querySelector('.hr-table-scroll');
  var proxy = document.querySelector('.hr-table-scrollbar');
  if (!scroller || !proxy) return;
  var spacer = proxy.firstElementChild;
  var syncing = false;
  function update() { spacer.style.width = scroller.scrollWidth + 'px'; var rect = scroller.getBoundingClientRect(); proxy.style.display = rect.top < window.innerHeight && rect.bottom > window.innerHeight ? 'block' : 'none'; }
  scroller.addEventListener('scroll', function () { if (!syncing) { syncing = true; proxy.scrollLeft = scroller.scrollLeft; syncing = false; } });
  proxy.addEventListener('scroll', function () { if (!syncing) { syncing = true; scroller.scrollLeft = proxy.scrollLeft; syncing = false; } });
  window.addEventListener('scroll', update, { passive: true }); window.addEventListener('resize', update); update();
  var form = document.querySelector('.hr-table-scroll').closest('form');
  form.querySelectorAll('tbody tr').forEach(function (row) {
    var checkbox = row.querySelector('input[type=checkbox]');
    var fields = row.querySelectorAll('input:not([type=checkbox]), select');
    function syncRequired() { fields.forEach(function (field) { field.required = checkbox.checked; }); }
    checkbox.addEventListener('change', syncRequired); syncRequired();
  });
});
</script>'''
HR_COLUMNS = (
    ("name", "Név"), ("vat", "Adóazonosító jel"), ("address", "Lakcím"), ("job", "Munkakör"),
    ("birthname", "Születési név"), ("birthplace", "Születési hely"), ("birthday", "Születési idő"),
    ("momname", "Anyja neve"), ("taj", "TAJ szám"), ("entry", "Belépés"), ("payment", "Havi bér"),
    ("stayaddress", "Tartózkodási hely"), ("email", "E-mail"), ("phone", "Telefon"),
)
EXTRA_COLUMNS = (
    ("workplace", "Munkahely"), ("boss", "Felettes"), ("workbreak", "Szünet"),
    ("breaktype", "Szünet a munkaidő része"), ("orderfrom", "Utasítástól"),
    ("orderfromname", "Utasítást adó személy"), ("qualification", "Végzettség"),
    ("requirements", "Egyéb követelmények"), ("date", "Dátum"),
)


def _layout(body: str, title: str = "HR dokumentumok") -> bytes:
    return f'''<!doctype html><html lang="hu"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" /><title>Divian-HUB | {html.escape(title)}</title>{COMMON}{HR_UI}
<style>.hr-shell{{width:min(1400px,calc(100vw - 48px));margin:0 auto;padding:34px 0 70px}}.hr-panel{{padding:28px;background:linear-gradient(180deg,var(--panel),var(--panel-strong));border:1px solid var(--border);border-radius:var(--radius-xl);box-shadow:var(--shadow);overflow:auto}}.hr-grid{{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:14px}}.hr-field{{display:grid;gap:6px}}.hr-field label{{font-size:.78rem;color:var(--muted)}}.hr-field input,.hr-field select{{width:100%;padding:11px 12px;border:1px solid var(--border);border-radius:12px;background:rgba(255,255,255,.06);color:var(--text)}}.hr-table{{width:100%;border-collapse:collapse;min-width:1000px;margin:18px 0 26px}}.hr-table th,.hr-table td{{padding:8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}.hr-table th{{color:var(--muted);font-size:.75rem}}.hr-table input,.hr-table select{{width:100%;min-width:110px;padding:8px;border:1px solid var(--border);border-radius:8px;background:rgba(255,255,255,.05);color:var(--text)}}.hr-actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}}.hr-note{{color:var(--muted);line-height:1.6}}.alert{{margin:0 0 18px;padding:12px 14px;border:1px solid var(--danger-line);border-radius:12px;background:var(--danger-bg)}}@media(max-width:900px){{.hr-grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:600px){{.hr-grid{{grid-template-columns:1fr}}.hr-shell{{width:min(100% - 24px,1400px)}}}}</style></head><body><div class="site"><header class="topbar"><a class="brand" href="/" aria-label="Divian-HUB kezdőoldal"><span class="brand-mark"></span><span class="brand-text"><strong>Divian-HUB</strong><small>Céges modulplatform</small></span></a><nav class="nav"><a href="/">Főoldal</a><a href="/#modules">Modulok</a></nav><a class="ghost-link" href="/">Vissza</a></header><main class="module-shell hr-shell">{body}</main></div></body></html>'''.encode("utf-8")


def render_form(message: str = "") -> bytes:
    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    body = f'''<section class="hr-hero"><div class="hr-hero-copy"><p class="eyebrow">HR / belépési csomag</p><h1>Belépési dokumentumok <span>készen, egy csomagban</span></h1><p class="hr-lead">Töltsd fel a munkavállalói adatokat tartalmazó Excelt, ellenőrizd és egészítsd ki személyenként az adatokat, majd generáld le a szükséges dokumentumcsomagot.</p><div class="hr-hero-actions"><a class="button primary-button" href="#hr-upload">Feltöltés</a><a class="button button-secondary" href="/#modules">Modulok</a></div></div><div class="hr-hero-visual" aria-hidden="true"><div class="hr-doc-stack"><div class="hr-doc"></div><div class="hr-doc"></div><span class="hr-doc-label">HR csomag</span></div></div></section><section class="hr-upload-card" id="hr-upload"><h2>Feltöltés</h2><p class="hr-note">Excel kiválasztása, majd ellenőrzés.</p>{notice}<form action="{APP_ROUTE}" method="post" enctype="multipart/form-data"><div class="hr-field hr-upload"><label for="people_file">Excel fájl</label><input id="people_file" name="people_file" type="file" accept=".xlsx,.xlsm" required></div><div class="hr-actions"><button class="button primary-button" type="submit">Beolvasás és ellenőrzés</button></div></form></section>'''
    return _layout(body, "HR dokumentumok").replace(b'<a class="ghost-link" href="/">Vissza</a>', b'', 1)

    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    body = f'''<section class="hr-panel"><p class="eyebrow">HR / belépési csomag</p><h1>Belépő dokumentumok</h1>
<p class="hr-note">Töltsd fel az Excelt. A személyes adatok csak a feldolgozás idejére, memóriában kerülnek beolvasásra.</p>{notice}
<form action="{APP_ROUTE}" method="post" enctype="multipart/form-data"><div class="hr-field"><label for="people_file">Excel fájl</label><input id="people_file" name="people_file" type="file" accept=".xlsx,.xlsm" required></div><div class="hr-actions"><button class="button primary-button" type="submit">Beolvasás és ellenőrzés</button></div></form></section>'''
    body = body.replace('<div class="hr-field"><label for="people_file">', '<div class="hr-field hr-upload"><label for="people_file">', 1)
    return _layout(body)


def render_review(people: list[dict[str, str]], bosses: dict[str, dict[str, str]], message: str = "") -> bytes:
    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    headers = '<th>Kiválasztás</th>' + ''.join(f'<th>{html.escape(label)}</th>' for _, label in (*HR_COLUMNS, *EXTRA_COLUMNS))
    rows = []
    for i, person in enumerate(people):
        cells = f'<td><input type="checkbox" name="p_{i}_selected" value="1" checked aria-label="{html.escape(person.get("name", "sor"), quote=True)} kiválasztása"></td>' + ''.join(f'<td><input name="p_{i}_{key}" value="{html.escape(person.get(key, ""), quote=True)}"></td>' for key, _ in HR_COLUMNS)
        extra_cells = f'''<td><select name="p_{i}_workplace"><option>6724 Szeged, Trafó köz 3.</option><option>6724 Szeged, Bakay Nándor utca 52.</option></select></td>
<td><select name="p_{i}_boss">{''.join(f'<option value="{html.escape(name, quote=True)}">{html.escape(name)}</option>' for name in bosses)}</select></td>
<td><select name="p_{i}_workbreak"><option>30 perc</option><option>60 perc</option></select></td>
<td><select name="p_{i}_breaktype"><option>a munkaidő részét képezi</option><option>nem képezi a munkaidő részét</option></select></td>
<td><select name="p_{i}_orderfrom"><option>a vezető</option><option>a részlegvezető</option></select></td>
<td><input name="p_{i}_orderfromname"></td><td><input name="p_{i}_qualification"></td><td><input name="p_{i}_requirements"></td>
<td><input type="date" name="p_{i}_date" value="{date.today().isoformat()}" required></td>'''
        rows.append(f'<tr>{cells}{extra_cells}</tr>')
    body = f'''<section class="hr-panel"><p class="eyebrow">Ellenőrzés szükséges</p><h1>Adatok áttekintése</h1>{notice}
<p class="hr-note">Módosíthatod az Excelből beolvasott adatokat. A további HR-adatok is személyenként állíthatók be.</p>
<form action="{CONFIRM_ROUTE}" method="post"><input type="hidden" name="row_count" value="{len(people)}">
<table class="hr-table"><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table><div class="hr-actions"><button class="button primary-button" type="submit">Megerősítés és dokumentumok generálása</button></div></form></section>'''
    body = body.replace('<table class="hr-table">', '<div class="hr-table-scroll"><table class="hr-table">', 1)
    body = body.replace('</table><div class="hr-actions">', '</table></div><div class="hr-table-scrollbar" aria-label="Adattabla vizszintes gorgetese"><div></div></div><div class="hr-actions">', 1)
    return _layout(body, "HR adatok ellenőrzése").replace(b'<a class="ghost-link" href="/">Vissza</a>', f'<a class="button button-secondary hr-back-button" href="{APP_ROUTE}">Vissza</a>'.encode("utf-8"), 1)
