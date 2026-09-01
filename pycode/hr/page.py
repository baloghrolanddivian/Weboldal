"""HTML pages for the HR document generator."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from .generating import format_payment

APP_ROUTE = "/apps/hr-dokumentumok"
CONFIRM_ROUTE = f"{APP_ROUTE}/confirm"
COMMON = '<link rel="stylesheet" href="/styles.css" /><script src="/script.js"></script><style>.hr-field option,.hr-table option{background:#09131c;color:#f3fbff}.hr-field select,.hr-table select{color-scheme:dark}.hr-table{min-width:3900px}.hr-table th{white-space:nowrap;min-width:180px}.hr-table td{min-width:180px}.hr-table input,.hr-table select{min-width:170px;min-height:42px;font-size:.92rem;line-height:1.35}.hr-table input[type=checkbox]{width:20px;min-width:20px;min-height:20px}.hr-table td:first-child{min-width:110px}.hr-table td:nth-child(2){min-width:220px}</style>'
HR_UI = '''<style>
.hr-panel { overflow: visible; }
.hr-field option, .hr-table option { background: #fff8f4; color: #4c1834; }
.hr-field select, .hr-table select { color-scheme: light; }
.hr-actions .button { min-width: 230px; cursor: pointer; }
.hr-back-button { min-width: 0 !important; min-height: 38px !important; padding: 0 16px !important; font-size: .82rem; }
.hr-actions .primary-button { background: linear-gradient(135deg, var(--accent-warm), var(--accent)); color: #041017; font-weight: 800; box-shadow: 0 12px 28px rgba(67, 222, 207, .18); }
.hr-upload { display: grid; gap: 10px; max-width: 520px; }
.hr-upload input[type=file] { width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--panel-soft); color: var(--text); }
.hr-upload input[type=file]::file-selector-button { margin-right: 12px; padding: 9px 14px; border: 1px solid var(--border); border-radius: 999px; background: linear-gradient(135deg, var(--accent-warm), var(--accent)); color: #041017; font-weight: 800; cursor: pointer; }
.hr-table-scroll { width: 100%; max-height: 370px; overflow: auto; overscroll-behavior: contain; border: 1px solid var(--border); border-radius: 14px; scrollbar-color: var(--accent) var(--panel-soft); }
.hr-table-scroll .hr-table { margin: 0; }
.hr-table-scroll .hr-table th { position: sticky; top: 0; z-index: 5; background: var(--panel-strong); box-shadow: 0 1px 0 var(--line); }
.hr-table th:first-child, .hr-table td:first-child { width: 52px !important; min-width: 52px !important; max-width: 52px !important; padding-left: 12px; padding-right: 8px; }
.hr-table input[type=checkbox] { appearance: none; -webkit-appearance: none; display: grid; place-content: center; width: 20px !important; min-width: 20px !important; max-width: 20px; height: 20px; min-height: 20px !important; max-height: 20px; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: 5px; background: rgba(255,255,255,.06); cursor: pointer; }
.hr-table input[type=checkbox]::before { content: ''; width: 10px; height: 10px; transform: scale(0); clip-path: polygon(14% 44%, 0 59%, 39% 100%, 100% 16%, 84% 0, 37% 62%); background: #041017; transition: transform 120ms ease; }
.hr-table input[type=checkbox]:checked { border-color: var(--accent-warm); background: linear-gradient(135deg, var(--accent-warm), var(--accent)); }
.hr-table input[type=checkbox]:checked::before { transform: scale(1); }
.hr-table input[type=checkbox]:focus-visible { outline: 2px solid var(--accent-warm); outline-offset: 3px; }
.hr-table tbody tr.hr-row-selected td { background: rgba(255, 192, 225, 0.24); }
.hr-table tbody tr.hr-row-selected td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.hr-table tbody tr:has(input[type=checkbox]:checked) td { background: rgba(255, 192, 225, 0.24); }
.hr-table tbody tr:has(input[type=checkbox]:checked) td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.hr-multiselect { position: relative; min-width: 210px; }
.hr-multiselect-toggle { width: 100%; min-height: 42px; padding: 8px 34px 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: rgba(255,255,255,.05); color: var(--text); text-align: left; cursor: pointer; }
.hr-multiselect-toggle::after { content: '⌄'; position: absolute; right: 11px; top: 8px; color: var(--accent); font-size: 1.2rem; }
.hr-multiselect-menu, .hr-single-select-menu { position: fixed; z-index: 100; display: none; width: max-content; min-width: 270px; max-width: 340px; max-height: 260px; padding: 8px; overflow-y: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--panel-strong); box-shadow: var(--shadow); }
.hr-multiselect-menu.is-floating, .hr-single-select-menu.is-floating { display: grid; gap: 2px; }
.hr-multiselect-option { display: flex; align-items: center; gap: 9px; padding: 8px 9px; border-radius: 8px; color: var(--text); cursor: pointer; white-space: nowrap; }
.hr-multiselect-option:hover { background: var(--panel-soft); }
.hr-multiselect-option input[type=checkbox] { flex: 0 0 auto; }
.hr-single-select { position: relative; min-width: 190px; }
.hr-single-select-toggle { width: 100%; min-height: 42px; padding: 8px 34px 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: rgba(255,255,255,.05); color: var(--text); text-align: left; cursor: pointer; }
.hr-single-select-toggle::after { content: '⌄'; position: absolute; right: 11px; top: 8px; color: var(--accent); font-size: 1.2rem; }
.hr-single-select-option { display: block; width: 100%; padding: 8px 9px; border: 0; border-radius: 8px; background: transparent; color: var(--text); text-align: left; cursor: pointer; white-space: nowrap; }
.hr-single-select-option:hover { background: var(--panel-soft); }
.hr-table-scroll::-webkit-scrollbar { width: 12px; height: 12px; }
.hr-table-scroll::-webkit-scrollbar-track { background: var(--panel-soft); border-radius: 999px; }
.hr-table-scroll::-webkit-scrollbar-thumb { background: linear-gradient(90deg, var(--accent), var(--accent-warm)); border: 2px solid var(--panel); border-radius: 999px; }
@media (max-width: 600px) { .hr-actions .button { width: 100%; } }
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
.hr-doc { position: absolute; width: 122px; height: 164px; padding: 18px 14px; border: 1px solid var(--border); border-radius: 20px; background: linear-gradient(160deg, rgba(255,255,255,.94), rgba(255,210,228,.78)); box-shadow: var(--shadow); }
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
  if (!scroller) return;
  var form = document.querySelector('.hr-table-scroll').closest('form');
  form.querySelectorAll('tbody tr').forEach(function (row) {
    var checkbox = row.querySelector('input[type=checkbox]');
    var fields = row.querySelectorAll('input:not([type=checkbox]), select');
    function syncRequired() { fields.forEach(function (field) { field.required = checkbox.checked && !field.name.endsWith('_stayaddress'); }); row.classList.toggle('hr-row-selected', checkbox.checked); }
    checkbox.addEventListener('change', syncRequired); syncRequired();
  });
  form.querySelectorAll('input[name$="_payment"]').forEach(function (field) {
    function formatPayment() {
      var digits = field.value.replace(/\\D/g, '');
      field.value = digits.replace(/\\B(?=(\\d{3})+(?!\\d))/g, '.');
    }
    field.addEventListener('input', formatPayment);
    formatPayment();
  });
  function closeMenus() { document.querySelectorAll('.hr-multiselect-menu.is-floating, .hr-single-select-menu.is-floating').forEach(function (menu) { menu.classList.remove('is-floating'); }); }
  function openMenu(toggle, menu) { closeMenus(); var rect = toggle.getBoundingClientRect(); menu.style.left = rect.left + 'px'; menu.style.top = (rect.bottom + 6) + 'px'; menu.style.minWidth = rect.width + 'px'; menu.classList.add('is-floating'); }
  form.querySelectorAll('[data-instruction-people]').forEach(function (picker) {
    var target = form.querySelector('input[name="' + picker.dataset.instructionTarget + '"]');
    var toggle = picker.querySelector('.hr-multiselect-toggle');
    var menu = picker.querySelector('.hr-multiselect-menu');
    var choices = picker.querySelectorAll('input[type=checkbox]');
    function syncPeople() {
      var selected = Array.from(choices).filter(function (choice) { return choice.checked; }).map(function (choice) { return choice.value; });
      target.value = selected.join(', ');
      toggle.textContent = selected.length ? selected.join(', ') : 'Válassz személyeket';
    }
    toggle.addEventListener('click', function (event) { event.stopPropagation(); if (menu.classList.contains('is-floating')) closeMenus(); else openMenu(toggle, menu); });
    menu.addEventListener('click', function (event) { event.stopPropagation(); });
    choices.forEach(function (choice) { choice.addEventListener('change', syncPeople); });
    syncPeople();
  });
  form.querySelectorAll('[data-single-select]').forEach(function (picker) {
    var target = form.querySelector('input[name="' + picker.dataset.singleTarget + '"]');
    var toggle = picker.querySelector('.hr-single-select-toggle');
    var menu = picker.querySelector('.hr-single-select-menu');
    toggle.addEventListener('click', function (event) { event.stopPropagation(); if (menu.classList.contains('is-floating')) closeMenus(); else openMenu(toggle, menu); });
    menu.querySelectorAll('.hr-single-select-option').forEach(function (option) { option.addEventListener('click', function () { target.value = option.value; toggle.textContent = option.value; closeMenus(); }); });
  });
  document.addEventListener('click', function () { closeMenus(); });
  form.addEventListener('submit', function (event) {
    var missingPicker = Array.from(form.querySelectorAll('tbody tr')).find(function (row) { return row.querySelector('input[type=checkbox]').checked && !row.querySelector('[data-instruction-people] input[type=hidden]').value; });
    if (missingPicker) { event.preventDefault(); var toggle = missingPicker.querySelector('.hr-multiselect-toggle'); openMenu(toggle, missingPicker.querySelector('.hr-multiselect-menu')); toggle.focus(); alert('Válassz legalább egy személyt a „Kitől kaphat utasítást?” mezőben.'); }
  });
});
</script>'''
HR_COLUMNS = (
    ("name", "Név"), ("birthname", "Születési név"), ("birthplace", "Születési hely"),
    ("birthday", "Születési idő"), ("momname", "Anyja neve"), ("vat", "Adóazonosító jel"),
    ("taj", "TAJ szám"), ("address", "Állandó lakcím"), ("stayaddress", "Tartózkodási hely"),
    ("email", "E-mail cím"), ("phone", "Telefonszám"), ("job", "Munkakör"),
    ("jobdescription", "Munkaköri leírás"), ("entry", "Belépés dátuma"), ("payment", "Munkabér"),
)
EXTRA_COLUMNS = (
    ("workplace", "Munkavégzés helye"), ("orderfromname", "Kitől kaphat utasítást?"),
    ("boss", "Közvetlen felettes"), ("workbreak", "Munkaközi szünet"),
    ("breaktype", "A szünet beleszámít a munkaidőbe?"),
    ("qualification", "Legmagasabb végzettség"), ("requirements", "Egyéb követelmények"),
)
PERSON_OPTIONS = (
    "Varga Zoltán", "Jambrik József", "Fekete János", "Szabó Szabolcs", "Bozsó Gábor",
    "Papp-Gyenes Veronika", "Őri Balázs", "Szabó-Varga Dorina Lili", "Kovács Bertalan",
    "Szabó Márk", "Bodó Tibor", "Stevanov György", "Matuz János",
)


def _layout(body: str, title: str = "HR dokumentumok") -> bytes:
    return f'''<!doctype html><html lang="hu"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" /><title>Divian-HUB | {html.escape(title)}</title>{COMMON}{HR_UI}
<style>.hr-shell{{width:min(1400px,calc(100vw - 48px));margin:0 auto;padding:34px 0 70px}}.hr-panel{{padding:28px;background:linear-gradient(180deg,var(--panel),var(--panel-strong));border:1px solid var(--border);border-radius:var(--radius-xl);box-shadow:var(--shadow);overflow:auto}}.hr-grid{{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:14px}}.hr-field{{display:grid;gap:6px}}.hr-field label{{font-size:.78rem;color:var(--muted)}}.hr-field input,.hr-field select{{width:100%;padding:11px 12px;border:1px solid var(--border);border-radius:12px;background:rgba(255,255,255,.06);color:var(--text)}}.hr-table{{width:100%;border-collapse:collapse;min-width:1000px;margin:18px 0 26px}}.hr-table th,.hr-table td{{padding:8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}.hr-table th{{color:var(--muted);font-size:.75rem}}.hr-table input,.hr-table select{{width:100%;min-width:110px;padding:8px;border:1px solid var(--border);border-radius:8px;background:rgba(255,255,255,.05);color:var(--text)}}.hr-actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}}.hr-note{{color:var(--muted);line-height:1.6}}.alert{{margin:0 0 18px;padding:12px 14px;border:1px solid var(--danger-line);border-radius:12px;background:var(--danger-bg)}}@media(max-width:900px){{.hr-grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:600px){{.hr-grid{{grid-template-columns:1fr}}.hr-shell{{width:min(100% - 24px,1400px)}}}}</style></head><body><div class="site"><header class="topbar"><a class="brand" href="/" aria-label="Divian-HUB kezdőoldal"><span class="brand-mark"></span><span class="brand-text"><strong>Divian-HUB</strong><small>Céges modulplatform</small></span></a><nav class="nav"><a href="/">Főoldal</a><a href="/#modules">Modulok</a></nav><a class="ghost-link" href="/">Vissza</a></header><main class="module-shell hr-shell">{body}</main></div></body></html>'''.encode("utf-8")


def render_form(message: str = "") -> bytes:
    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    body = f'''<section class="hr-hero"><div class="hr-hero-copy"><p class="eyebrow">HR / belépési csomag</p><h1>Belépési dokumentumok <span>készen, egy csomagban</span></h1><p class="hr-lead">Töltsd fel a munkavállalói adatokat tartalmazó Excelt, ellenőrizd és egészítsd ki személyenként az adatokat, majd generáld le a szükséges dokumentumcsomagot.</p><div class="hr-hero-actions"><a class="button primary-button" href="#hr-upload">Feltöltés</a><a class="button button-secondary" href="/#modules">Modulok</a></div></div><div class="hr-hero-visual" aria-hidden="true"><div class="hr-doc-stack"><div class="hr-doc"></div><div class="hr-doc"></div><span class="hr-doc-label">HR csomag</span></div></div></section><section class="hr-upload-card" id="hr-upload"><h2>Feltöltés</h2><p class="hr-note">Excel kiválasztása, majd ellenőrzés.</p>{notice}<form action="{APP_ROUTE}" method="post" enctype="multipart/form-data"><div class="hr-field hr-upload"><label for="people_file">Excel fájl</label><input id="people_file" name="people_file" type="file" accept=".xls,.xlsx,.xlsm" required></div><div class="hr-actions"><button class="button primary-button" type="submit">Beolvasás és ellenőrzés</button></div></form></section>'''
    return _layout(body, "HR dokumentumok").replace(b'<a class="ghost-link" href="/">Vissza</a>', b'', 1)

    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    body = f'''<section class="hr-panel"><p class="eyebrow">HR / belépési csomag</p><h1>Belépő dokumentumok</h1>
<p class="hr-note">Töltsd fel az Excelt. A személyes adatok csak a feldolgozás idejére, memóriában kerülnek beolvasásra.</p>{notice}
<form action="{APP_ROUTE}" method="post" enctype="multipart/form-data"><div class="hr-field"><label for="people_file">Excel fájl</label><input id="people_file" name="people_file" type="file" accept=".xls,.xlsx,.xlsm" required></div><div class="hr-actions"><button class="button primary-button" type="submit">Beolvasás és ellenőrzés</button></div></form></section>'''
    body = body.replace('<div class="hr-field"><label for="people_file">', '<div class="hr-field hr-upload"><label for="people_file">', 1)
    return _layout(body)


def _single_picker(index: int, key: str, options: tuple[str, ...] | list[str]) -> str:
    """Render a themed single-value dropdown backed by a hidden form field."""
    choices = tuple(options)
    selected = choices[0] if choices else ""
    menu = ''.join(
        f'<button class="hr-single-select-option" type="button" value="{html.escape(value, quote=True)}">{html.escape(value)}</button>'
        for value in choices
    )
    return (
        f'<div class="hr-single-select" data-single-select data-single-target="p_{index}_{key}">'
        f'<button class="hr-single-select-toggle" type="button">{html.escape(selected)}</button>'
        f'<div class="hr-single-select-menu">{menu}</div>'
        f'<input type="hidden" name="p_{index}_{key}" value="{html.escape(selected, quote=True)}"></div>'
    )


def render_review(people: list[dict[str, str]], bosses: dict[str, dict[str, str]], message: str = "") -> bytes:
    notice = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    headers = '<th aria-label="Kiválasztás"></th>' + ''.join(f'<th>{html.escape(label)}</th>' for _, label in (*HR_COLUMNS, *EXTRA_COLUMNS))
    rows = []
    for i, person in enumerate(people):
        cells = ''.join(
            f'<td><input name="p_{i}_{key}" value="{html.escape(format_payment(person.get(key, "")) if key == "payment" else (person.get(key, "") or (person.get("address", "") if key == "stayaddress" else "")), quote=True)}"></td>'
            for key, _ in HR_COLUMNS
        )
        workplace_picker = _single_picker(i, "workplace", ("6724 Szeged, Trafó köz 3.", "6724 Szeged, Bakay Nándor utca 52."))
        boss_picker = _single_picker(i, "boss", list(bosses))
        break_picker = _single_picker(i, "workbreak", ("30 perc", "60 perc"))
        breaktype_picker = _single_picker(i, "breaktype", ("a munkaidő részét képezi", "nem képezi a munkaidő részét"))
        extra_cells = f'''<td>{workplace_picker}</td>
<td><div class="hr-multiselect" data-instruction-people data-instruction-target="p_{i}_orderfromname"><button class="hr-multiselect-toggle" type="button" aria-label="Kitől kaphat utasítást?"></button><div class="hr-multiselect-menu">{''.join(f'<label class="hr-multiselect-option"><input type="checkbox" value="{html.escape(name, quote=True)}">{html.escape(name)}</label>' for name in PERSON_OPTIONS)}</div><input type="hidden" name="p_{i}_orderfromname"></div></td>
<td>{boss_picker}</td>
<td>{break_picker}</td>
<td>{breaktype_picker}</td>
<td><input name="p_{i}_qualification"></td><td><input name="p_{i}_requirements"></td>'''
        select_cell = f'<td><input type="checkbox" name="p_{i}_selected" value="1" aria-label="{html.escape(person.get("name", "sor"), quote=True)} kiválasztása"></td>'
        rows.append(f'<tr>{select_cell}{cells}{extra_cells}</tr>')
    body = f'''<section class="hr-panel"><p class="eyebrow">Ellenőrzés szükséges</p><h1>Adatok áttekintése</h1>{notice}
<p class="hr-note">Módosíthatod az Excelből beolvasott adatokat. A további HR-adatok is személyenként állíthatók be.</p>
<form action="{CONFIRM_ROUTE}" method="post"><input type="hidden" name="row_count" value="{len(people)}">
<table class="hr-table"><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table><div class="hr-actions"><button class="button primary-button" type="submit">Megerősítés és dokumentumok generálása</button></div></form></section>'''
    body = body.replace('<table class="hr-table">', '<div class="hr-table-scroll"><table class="hr-table">', 1)
    body = body.replace('</table><div class="hr-actions">', '</table></div><div class="hr-actions">', 1)
    return _layout(body, "HR adatok ellenőrzése").replace(b'<a class="ghost-link" href="/">Vissza</a>', f'<a class="button button-secondary hr-back-button" href="{APP_ROUTE}">Vissza</a>'.encode("utf-8"), 1)
