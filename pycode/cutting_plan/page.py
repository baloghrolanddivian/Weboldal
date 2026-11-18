"""Data-entry page for preparing cutting plans by material colour."""

from __future__ import annotations

import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROUTE = "/apps/szabasterv"
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "korpusz-alkatresz-meretek.json"
DEFAULT_MANUFACTURING_ROOT = Path(os.getenv("DIVIAN_MANUFACTURING_ROOT", r"J:\inSightData\Output\Gyartasi_papirok"))


def render_page(
    inventory_session_path: Path | None = None,
    board_catalog: dict[str, object] | None = None,
) -> bytes:
    """Render the interactive cutting-plan worksheet."""
    size_catalog = load_size_catalog(inventory_session_path)
    catalog_json = json.dumps(size_catalog, ensure_ascii=False).replace("</", "<\\/")
    colour_catalog = load_colour_catalog(board_catalog)
    colour_json = json.dumps(colour_catalog, ensure_ascii=False).replace("</", "<\\/")
    return (
        PAGE.replace("{{SIZE_CATALOG}}", catalog_json, 1)
        .replace("{{COLOUR_CATALOG}}", colour_json, 1)
        .encode("utf-8")
    )


def load_colour_catalog(board_catalog: dict[str, object] | None = None) -> list[str]:
    """Return the live furniture-board colour names from cutting inventory."""
    if board_catalog is None:
        try:
            from leltar.cutting_inventory import load_catalog

            board_catalog = load_catalog()
        except (ImportError, OSError, ValueError, TypeError):
            board_catalog = {}

    boards = board_catalog.get("boards", []) if isinstance(board_catalog, dict) else []
    colours = {
        str(item.get("name", "")).strip()
        for item in boards
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    return sorted(colours, key=lambda value: value.casefold())


def load_size_catalog(inventory_session_path: Path | None) -> list[dict[str, object]]:
    """Collect dimensions from the durable catalog, inventory, and production XML."""
    found: dict[tuple[int, int, str], dict[str, object]] = {}

    def add_size(width_value: object, height_value: object, colour_value: object = "", source: str = "") -> None:
        try:
            width, height = int(float(str(width_value))), int(float(str(height_value)))
        except (TypeError, ValueError):
            return
        if not (20 <= width <= 4000 and 20 <= height <= 4000):
            return
        colour = str(colour_value or "").strip()
        key = (width, height, colour.casefold())
        found[key] = {
            "width": width,
            "height": height,
            "colour": colour,
            "label": f"{width} × {height} mm",
            "source": source,
        }

    try:
        durable_catalog = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        durable_catalog = []
    for item in durable_catalog if isinstance(durable_catalog, list) else []:
        if isinstance(item, dict):
            add_size(item.get("width"), item.get("height"), item.get("colour", ""), str(item.get("source", "")))

    try:
        payload = json.loads(Path(inventory_session_path).read_text(encoding="utf-8")) if inventory_session_path else {}
    except (OSError, ValueError, TypeError):
        payload = {}
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        colour = str(row.get("icg_code", "") or "").strip()
        source = " ".join(str(row.get(key, "") or "") for key in ("description", "part_number"))
        for match in re.finditer(r"(?<!\d)(\d{2,4})\s*[xX×*]\s*(\d{2,4})(?!\d)", source):
            add_size(match.group(1), match.group(2), colour, "Aktív félkész leltár")

    _add_manufacturing_xml_sizes(found, add_size)
    return sorted(found.values(), key=lambda item: (str(item["colour"]).casefold(), int(item["width"]), int(item["height"])))


def _add_manufacturing_xml_sizes(found: dict, add_size) -> None:
    """Extend the catalog from recent Korpusz XML files when the drive is mounted."""
    root = DEFAULT_MANUFACTURING_ROOT
    if not root.is_dir():
        return
    try:
        folders = sorted(
            (path for path in root.iterdir() if path.is_dir() and path.name.isdigit()),
            key=lambda path: int(path.name),
            reverse=True,
        )[:40]
    except OSError:
        return
    for folder in folders:
        for file_name in ("Osszekeszito.xml", "Alkatresz_kesz.xml"):
            xml_path = folder / file_name
            if not xml_path.is_file():
                continue
            try:
                xml_root = ET.parse(xml_path).getroot()
            except (OSError, ET.ParseError):
                continue
            for element in xml_root.iter():
                if _xml_key(element.tag) != "con":
                    continue
                fields = {_xml_key(child.tag): str(child.text or "").strip() for child in list(element)}
                add_size(
                    fields.get("hossz", ""),
                    fields.get("szelleseg", ""),
                    fields.get("szin", ""),
                    "Gyártási korpusz XML",
                )


def _xml_key(value: object) -> str:
    """Normalize one XML field name for tolerant matching."""
    text = str(value or "").rsplit("}", 1)[-1].strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9]+", "", "".join(char for char in text if not unicodedata.combining(char)))


PAGE = r'''<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Szabásterv készítés</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/styles.css" />
  <style>
    :root{--ink:#14231c;--muted:#66756d;--line:#dce5df;--green:#0d8b55;--green-dark:#096b43;--soft:#eff8f3;--red:#b42318;--orange:#c45a0a}
    *{box-sizing:border-box}.cp-page{min-height:100vh;background:linear-gradient(145deg,#eef7f2 0,#fafcfb 46%,#edf3ef 100%);color:var(--ink);font-family:Manrope,sans-serif}.cp-shell{width:min(1500px,calc(100% - 32px));margin:0 auto;padding:22px 0 52px}.cp-top{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px;padding:18px 22px;border:1px solid rgba(20,35,28,.08);border-radius:22px;background:rgba(255,255,255,.92);box-shadow:0 12px 38px rgba(25,61,42,.08)}.cp-brand{display:flex;align-items:center;gap:13px}.cp-mark{width:42px;height:42px;border-radius:14px;background:linear-gradient(145deg,#12a568,#087648);box-shadow:inset 0 0 0 7px rgba(255,255,255,.18)}.cp-brand strong{display:block;font:700 1.05rem/1 Space Grotesk,sans-serif}.cp-brand small{display:block;margin-top:5px;color:var(--muted);font-weight:700}.cp-back{color:var(--ink);text-decoration:none;font-weight:800}.cp-card{border:1px solid rgba(20,35,28,.09);border-radius:24px;background:#fff;box-shadow:0 16px 42px rgba(25,61,42,.08)}.cp-intro{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:25px;align-items:center;padding:25px 27px}.cp-kicker{margin:0 0 7px;color:var(--green);font-size:.75rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.cp-intro h1{margin:0;font:700 clamp(1.65rem,3vw,2.3rem)/1.08 Space Grotesk,sans-serif}.cp-lead{max-width:750px;margin:10px 0 0;color:var(--muted);line-height:1.55}.cp-print{min-height:46px;border:0;border-radius:13px;background:#182820;color:#fff;padding:0 17px;font-weight:800;cursor:pointer}.cp-create{display:grid;grid-template-columns:minmax(220px,1fr) minmax(220px,1fr) auto;gap:13px;align-items:end;margin-top:18px;padding:20px 22px}.cp-field{display:grid;gap:6px}.cp-field span{color:#48574f;font-size:.74rem;font-weight:800}.cp-field input,.cp-field select{width:100%;min-height:46px;border:1px solid #cfdad3;border-radius:13px;background:#fbfdfc;color:var(--ink);padding:0 13px;font:700 .92rem Manrope,sans-serif;outline:none}.cp-field input:focus,.cp-field select:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(13,139,85,.12)}.cp-add-plan{min-height:46px;border:0;border-radius:13px;background:var(--green);color:#fff;padding:0 20px;font-weight:800;cursor:pointer}.cp-empty{margin-top:18px;padding:50px 25px;text-align:center}.cp-empty strong{display:block;font:700 1.2rem Space Grotesk,sans-serif}.cp-empty p{margin:8px 0 0;color:var(--muted)}.cp-plans{display:grid;gap:18px;margin-top:18px}.cp-plan{overflow:hidden}.cp-plan-head{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 23px;background:linear-gradient(115deg,#153b2a,#0a784a);color:#fff}.cp-plan-title{display:flex;align-items:center;gap:13px}.cp-swatch{width:38px;height:38px;border-radius:12px;background:#4a4d50;border:4px solid rgba(255,255,255,.22)}.cp-plan-title h2{display:inline-flex;align-items:center;gap:10px;margin:0;font:700 1.25rem Space Grotesk,sans-serif}.cp-head-total{display:inline-flex;align-items:center;min-height:29px;padding:0 10px;border-radius:999px;background:rgba(255,255,255,.16);font:800 .72rem Manrope,sans-serif;white-space:nowrap}.cp-head-total strong{margin-right:4px;font-size:.9rem}.cp-plan-title p{margin:5px 0 0;color:rgba(255,255,255,.75);font-size:.78rem;font-weight:700}.cp-remove-plan{border:1px solid rgba(255,255,255,.34);border-radius:11px;background:rgba(255,255,255,.1);color:#fff;padding:9px 12px;font-weight:800;cursor:pointer}.cp-table-wrap{overflow-x:auto}.cp-table{width:100%;min-width:1200px;border-collapse:collapse;table-layout:fixed}.cp-table col.cp-col-index,.cp-table col.cp-col-delete{width:3%}.cp-table col.cp-col-main-size{width:45.8%}.cp-table col.cp-col-main-number{width:10%}.cp-table col.cp-col-offcut-size{width:17.2%}.cp-table col.cp-col-offcut-number,.cp-table col.cp-col-strip{width:5.5%}.cp-table th{padding:11px 9px;background:#f4f8f5;color:#59685f;font-size:.68rem;letter-spacing:.055em;text-align:left;text-transform:uppercase}.cp-table td{padding:10px 7px;border-top:1px solid var(--line);vertical-align:middle}.cp-table td:first-child,.cp-table th:first-child{padding-left:18px}.cp-table td:last-child,.cp-table th:last-child{padding-right:18px}.cp-table input,.cp-table select{width:100%;min-width:0;height:43px;border:1px solid #d1dcd5;border-radius:11px;background:#fff;padding:0 10px;color:var(--ink);font:800 .88rem Manrope,sans-serif;outline:none}.cp-table select{background-image:linear-gradient(45deg,transparent 50%,#567064 50%),linear-gradient(135deg,#567064 50%,transparent 50%);background-position:calc(100% - 16px) 18px,calc(100% - 11px) 18px;background-size:5px 5px,5px 5px;background-repeat:no-repeat;appearance:none;padding-right:32px}.cp-table input:focus,.cp-table select:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(13,139,85,.1)}.cp-table input:disabled,.cp-table select:disabled{background-color:#f1f3f2;color:#98a29c}.cp-size-editor{display:grid;gap:7px}.cp-manual-size{display:grid;grid-template-columns:minmax(75px,1fr) auto minmax(75px,1fr);align-items:center;gap:6px;padding:7px;border-radius:12px;background:#f2f7f4}.cp-manual-size[hidden]{display:none}.cp-manual-size input{min-width:70px;height:38px;text-align:center}.cp-manual-size span{color:#738078;font-weight:900}.cp-row-number{display:grid;place-items:center;width:30px;height:30px;border-radius:10px;background:var(--soft);color:var(--green-dark);font-weight:800}.cp-main-group{background:#e8f6ee!important;color:var(--green-dark)!important;text-align:center!important;font-size:.74rem!important}.cp-offcut-group,.cp-offcut-head{background:#fff1e5!important;color:var(--orange)!important}.cp-offcut-group{text-align:center!important;font-size:.74rem!important}.cp-offcut-start{border-left:3px solid #efb77f!important}.cp-strip-label{display:flex;align-items:center;justify-content:center;gap:7px;color:var(--orange);font-size:.7rem;font-weight:900;white-space:nowrap}.cp-strip-label input{width:20px!important;min-width:20px!important;height:20px!important;padding:0;accent-color:var(--orange)}.cp-remove-row{display:grid;place-items:center;width:38px;height:38px;border:0;border-radius:11px;background:#fff1f0;color:var(--red);font-size:1.12rem;font-weight:800;cursor:pointer}.cp-plan-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 20px;border-top:1px solid var(--line);background:#fbfdfc}.cp-add-row{min-height:42px;border:0;border-radius:12px;background:var(--soft);color:var(--green-dark);padding:0 16px;font-weight:800;cursor:pointer}.cp-summary{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.cp-summary span{padding:8px 11px;border-radius:999px;background:#f0f4f1;color:#425148;font-size:.74rem;font-weight:800}.cp-summary strong{color:var(--green-dark)}.cp-save-state{margin:12px 4px 0;color:var(--muted);font-size:.73rem;font-weight:700;text-align:right}
    .cp-plan-columns{display:grid;grid-template-columns:minmax(0,7fr) minmax(330px,3fr)}.cp-subplan{min-width:0;padding-bottom:16px}.cp-subplan+.cp-subplan{border-left:3px solid #efb77f;background:#fffaf5}.cp-subplan-head{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:58px;padding:12px 18px;background:#e8f6ee;color:var(--green-dark)}.cp-offcut-panel .cp-subplan-head{background:#fff1e5;color:var(--orange)}.cp-subplan-head strong{font:700 1rem Space Grotesk,sans-serif}.cp-subplan-head span{font-size:.7rem;font-weight:800;opacity:.75}.cp-subtable{width:100%;min-width:0;table-layout:auto}.cp-subtable th{white-space:nowrap}.cp-subtable td:first-child,.cp-subtable th:first-child{padding-left:14px}.cp-subtable td:last-child,.cp-subtable th:last-child{padding-right:14px}.cp-main-table .cp-size-cell{width:58%}.cp-offcut-table .cp-size-cell{width:60%}.cp-subplan-empty{padding:25px 16px;color:var(--muted);font-size:.8rem;font-weight:700;text-align:center}.cp-add-row-wrap{padding:12px 16px 0}.cp-offcut-panel .cp-add-row{background:#fff0e2;color:var(--orange)}
    @media(max-width:1000px){.cp-plan-columns{grid-template-columns:1fr}.cp-subplan+.cp-subplan{border-left:0;border-top:3px solid #efb77f}}@media(max-width:760px){.cp-shell{width:calc(100% - 16px);padding-top:8px}.cp-top{padding:14px}.cp-brand small{display:none}.cp-intro{grid-template-columns:1fr;padding:20px}.cp-print{display:none}.cp-create{grid-template-columns:1fr;padding:17px}.cp-plan-head{align-items:flex-start;padding:17px}.cp-plan-title{align-items:flex-start}.cp-plan-foot{align-items:stretch;flex-direction:column}.cp-summary{justify-content:flex-start}.cp-remove-plan{font-size:0}.cp-remove-plan::after{content:"×";font-size:1.2rem}.cp-subtable{min-width:620px}}
    @media print{.cp-page{background:#fff}.cp-top,.cp-create,.cp-empty,.cp-remove-plan,.cp-remove-row,.cp-add-row,.cp-print,.cp-save-state{display:none!important}.cp-shell{width:100%;padding:0}.cp-intro{box-shadow:none;border:0;padding:0 0 18px}.cp-plan{break-inside:avoid;box-shadow:none;margin-bottom:15px}.cp-plans{gap:10px}.cp-table{min-width:0}.cp-table input{border:0;padding:0;min-width:0}.cp-plan-head{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
  </style>
</head>
<body class="cp-page" data-theme-scope="default">
  <main class="cp-shell">
    <header class="cp-top">
      <div class="cp-brand"><span class="cp-mark"></span><div><strong>Divian-HUB</strong><small>Szabászati tervező</small></div></div>
      <a class="cp-back" href="/">← Vissza a modulokhoz</a>
    </header>
    <section class="cp-card cp-create" aria-label="Új színblokk">
      <label class="cp-field"><span>Laptípus</span><select id="material"><option value="Standard bútorlap|2800 × 2070 mm">Standard bútorlap · 2800 × 2070 mm</option><option value="Evogloss lap|2800 × 1220 mm">Evogloss lap · 2800 × 1220 mm</option></select></label>
      <label class="cp-field"><span>Szín</span><select id="colour" aria-label="Bútorlap színe"></select></label>
      <button class="cp-add-plan" id="addPlan" type="button">Szín hozzáadása</button>
    </section>
    <section class="cp-card cp-empty" id="emptyState"><strong>Még nincs felvett szín.</strong><p>Válassz laptípust és színt, majd add hozzá az első tervblokkot.</p></section>
    <div class="cp-plans" id="plans"></div>
    <p class="cp-save-state" id="saveState">A módosítások automatikusan mentődnek ezen a gépen.</p>
  </main>

  <template id="planTemplate">
    <article class="cp-card cp-plan">
      <header class="cp-plan-head"><div class="cp-plan-title"><span class="cp-swatch"></span><div><h2><span data-colour></span><span class="cp-head-total"><strong data-head-board-total>0</strong> tábla</span></h2><p><span data-material></span> · <span data-board-size></span></p></div></div><button class="cp-remove-plan" type="button">Szín törlése</button></header>
      <div class="cp-plan-columns">
        <section class="cp-subplan cp-main-panel"><header class="cp-subplan-head"><div><strong>Korpusz méretek</strong><br /><span>Önállóan hozzáadható</span></div></header><div class="cp-table-wrap"><table class="cp-table cp-subtable cp-main-table"><thead><tr><th>#</th><th>Méret</th><th>Táblák</th><th>Darab</th><th></th></tr></thead><tbody data-main-body></tbody></table><div class="cp-subplan-empty" data-main-empty>Nincs még korpusz méret.</div></div><div class="cp-add-row-wrap"><button class="cp-add-row cp-add-main-row" type="button">+ Korpusz méret hozzáadása</button></div></section>
        <section class="cp-subplan cp-offcut-panel"><header class="cp-subplan-head"><div><strong>Leeső méretek</strong><br /><span>A korpusz soroktól független</span></div></header><div class="cp-table-wrap"><table class="cp-table cp-subtable cp-offcut-table"><thead><tr><th>#</th><th>Méret</th><th>Darab</th><th>+100</th><th></th></tr></thead><tbody data-offcut-body></tbody></table><div class="cp-subplan-empty" data-offcut-empty>Nincs még leeső méret.</div></div><div class="cp-add-row-wrap"><button class="cp-add-row cp-add-offcut-row" type="button">+ Leeső méret hozzáadása</button></div></section>
      </div>
    </article>
  </template>
  <template id="mainRowTemplate">
    <tr><td><span class="cp-row-number"></span></td><td class="cp-size-cell"><div class="cp-size-editor"><select class="cp-size-choice" aria-label="Korpusz méret"></select><div class="cp-manual-size" data-manual hidden><input data-field="width" type="number" min="1" aria-label="Kézi szélesség" /><span>×</span><input data-field="height" type="number" min="1" aria-label="Kézi magasság" /></div></div></td><td><input data-field="boards" type="number" min="0" aria-label="Táblák száma" /></td><td><input data-field="pieces" type="number" min="0" aria-label="Darabszám" /></td><td><button class="cp-remove-row" type="button" aria-label="Korpusz méret törlése">×</button></td></tr>
  </template>
  <template id="offcutRowTemplate">
    <tr><td><span class="cp-row-number"></span></td><td class="cp-size-cell"><div class="cp-size-editor"><select class="cp-size-choice" aria-label="Leeső méret"></select><div class="cp-manual-size" data-manual hidden><input data-field="width" type="number" min="1" aria-label="Kézi leeső szélesség" /><span>×</span><input data-field="height" type="number" min="1" aria-label="Kézi leeső magasság" /></div></div></td><td><input data-field="pieces" type="number" min="0" aria-label="Leeső darabszám" /></td><td><label class="cp-strip-label"><input data-field="strip100" type="checkbox" /> +100</label></td><td><button class="cp-remove-row" type="button" aria-label="Leeső méret törlése">×</button></td></tr>
  </template>
  <script>
  (() => {
    const STORAGE_KEY = "divian-cutting-plan-v2";
    const SIZE_CATALOG = {{SIZE_CATALOG}};
    const COLOUR_CATALOG = {{COLOUR_CATALOG}};
    const plansRoot = document.getElementById("plans"), emptyState = document.getElementById("emptyState");
    const materialInput = document.getElementById("material"), colourInput = document.getElementById("colour");
    COLOUR_CATALOG.forEach(colour => {
      const option=document.createElement("option");option.value=colour;option.textContent=colour;colourInput.appendChild(option);
    });
    if(COLOUR_CATALOG.includes("Antracit"))colourInput.value="Antracit";
    let plans = loadPlans();
    function newId() { return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`; }
    function blankMainRow() { return {id:newId(),sizeMode:"",width:"",height:"",boards:"",pieces:""}; }
    function blankOffcutRow() { return {id:newId(),sizeMode:"",width:"",height:"",pieces:"",strip100:false}; }
    function cleanNumber(value) { return Math.max(0,Math.floor(Number(value)||0)); }
    function normalizePlan(plan) {
      if(Array.isArray(plan.mainRows)&&Array.isArray(plan.offcutRows))return plan;
      const legacy=Array.isArray(plan.rows)?plan.rows:[];
      plan.mainRows=legacy.map(row=>({id:`${row.id||newId()}-main`,sizeMode:row.sizeMode||"",width:row.width||"",height:row.height||"",boards:row.boards||"",pieces:row.pieces||""}));
      plan.offcutRows=legacy.filter(row=>row.offcutWidth||row.offcutHeight||row.offcutPieces||row.strip100).map(row=>({id:`${row.id||newId()}-offcut`,sizeMode:row.offcutSizeMode||"",width:row.offcutWidth||"",height:row.offcutHeight||"",pieces:row.strip100?(row.boards||""):(row.offcutPieces||""),strip100:Boolean(row.strip100)}));
      delete plan.rows;return plan;
    }
    function loadPlans() { try { const value=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");return Array.isArray(value)?value.map(normalizePlan):[]; } catch (_) { return []; } }
    function savePlans() { try { localStorage.setItem(STORAGE_KEY,JSON.stringify(plans));document.getElementById("saveState").textContent="Mentve ezen a gépen."; } catch (_) { document.getElementById("saveState").textContent="A böngésző nem engedte a helyi mentést."; } }
    function addPlan() {
      const colour=colourInput.value.trim(), [material,boardSize]=materialInput.value.split("|");if(!colour){colourInput.focus();return;}
      const existing=plans.find(plan=>plan.colour.toLocaleLowerCase("hu")===colour.toLocaleLowerCase("hu")&&plan.material===material);
      if(existing){document.querySelector(`[data-plan-id="${existing.id}"]`)?.scrollIntoView({behavior:"smooth",block:"center"});return;}
      plans.push({id:newId(),colour,material,boardSize,mainRows:[],offcutRows:[]});savePlans();render();requestAnimationFrame(()=>document.querySelector(`[data-plan-id="${plans.at(-1).id}"] .cp-add-main-row`)?.focus());
    }
    function updateSummary(article,plan) {
      const boardTotal=plan.mainRows.reduce((sum,row)=>sum+cleanNumber(row.boards),0);
      article.querySelector("[data-head-board-total]").textContent=String(boardTotal);
    }
    function bindSizeEditor(tr,row,plan) {
      tr.querySelectorAll('[data-field]:not([type="checkbox"])').forEach(input=>{const field=input.dataset.field;input.value=row[field]??"";input.addEventListener("input",()=>{row[field]=input.value;savePlans();});});
      const normalize=value=>String(value||"").trim().toLocaleLowerCase("hu");
      const colourSizes=SIZE_CATALOG.filter(item=>!normalize(item.colour)||normalize(item.colour)===normalize(plan.colour));
      const availableSizes=colourSizes.length?colourSizes:SIZE_CATALOG,select=tr.querySelector(".cp-size-choice"),manualBox=tr.querySelector("[data-manual]");
      const choose=document.createElement("option");choose.value="";choose.textContent="Válassz méretet…";select.appendChild(choose);
      availableSizes.forEach(item=>{const option=document.createElement("option");option.value=`${item.width}x${item.height}`;option.textContent=item.label+(colourSizes.length?"":item.colour?` · ${item.colour}`:"");select.appendChild(option);});
      const manual=document.createElement("option");manual.value="manual";manual.textContent="Kézi méretmegadás";select.appendChild(manual);
      const catalogValue=availableSizes.some(item=>String(item.width)===String(row.width)&&String(item.height)===String(row.height))?`${row.width}x${row.height}`:"";
      select.value=row.sizeMode==="manual"?"manual":catalogValue||(row.width||row.height?"manual":"");row.sizeMode=select.value;manualBox.hidden=select.value!=="manual";
      select.addEventListener("change",()=>{row.sizeMode=select.value;manualBox.hidden=select.value!=="manual";if(select.value&&select.value!=="manual"){const [width,height]=select.value.split("x");row.width=width;row.height=height;tr.querySelector('[data-field="width"]').value=width;tr.querySelector('[data-field="height"]').value=height;}else if(!select.value){row.width="";row.height="";tr.querySelector('[data-field="width"]').value="";tr.querySelector('[data-field="height"]').value="";}savePlans();});
      return {select,manualBox};
    }
    function render() {
      plansRoot.innerHTML="";emptyState.hidden=plans.length>0;
      plans.forEach(plan=>{
        const article=document.getElementById("planTemplate").content.firstElementChild.cloneNode(true);article.dataset.planId=plan.id;
        article.querySelector("[data-colour]").textContent=plan.colour;article.querySelector("[data-material]").textContent=plan.material;article.querySelector("[data-board-size]").textContent=plan.boardSize;
        const mainBody=article.querySelector("[data-main-body]"),offcutBody=article.querySelector("[data-offcut-body]");article.querySelector("[data-main-empty]").hidden=plan.mainRows.length>0;article.querySelector("[data-offcut-empty]").hidden=plan.offcutRows.length>0;
        plan.mainRows.forEach((row,index)=>{const tr=document.getElementById("mainRowTemplate").content.firstElementChild.cloneNode(true);tr.querySelector(".cp-row-number").textContent=String(index+1);bindSizeEditor(tr,row,plan);tr.querySelectorAll('[data-field="boards"],[data-field="pieces"]').forEach(input=>input.addEventListener("input",()=>updateSummary(article,plan)));tr.querySelector(".cp-remove-row").addEventListener("click",()=>{plan.mainRows=plan.mainRows.filter(item=>item.id!==row.id);savePlans();render();});mainBody.appendChild(tr);});
        plan.offcutRows.forEach((row,index)=>{const tr=document.getElementById("offcutRowTemplate").content.firstElementChild.cloneNode(true);tr.querySelector(".cp-row-number").textContent=String(index+1);const editor=bindSizeEditor(tr,row,plan),strip=tr.querySelector('[data-field="strip100"]'),pieces=tr.querySelector('[data-field="pieces"]');const applyStrip=()=>{strip.checked=Boolean(row.strip100);editor.select.disabled=Boolean(row.strip100);if(row.strip100)editor.manualBox.hidden=true;};strip.addEventListener("change",()=>{row.strip100=strip.checked;if(row.strip100){row.sizeMode="";row.width="";row.height="";editor.select.value="";}applyStrip();updateSummary(article,plan);savePlans();});pieces.addEventListener("input",()=>updateSummary(article,plan));applyStrip();tr.querySelector(".cp-remove-row").addEventListener("click",()=>{plan.offcutRows=plan.offcutRows.filter(item=>item.id!==row.id);savePlans();render();});offcutBody.appendChild(tr);});
        article.querySelector(".cp-add-main-row").addEventListener("click",()=>{plan.mainRows.push(blankMainRow());savePlans();render();requestAnimationFrame(()=>document.querySelector(`[data-plan-id="${plan.id}"] [data-main-body] tr:last-child .cp-size-choice`)?.focus());});
        article.querySelector(".cp-add-offcut-row").addEventListener("click",()=>{plan.offcutRows.push(blankOffcutRow());savePlans();render();requestAnimationFrame(()=>document.querySelector(`[data-plan-id="${plan.id}"] [data-offcut-body] tr:last-child .cp-size-choice`)?.focus());});
        article.querySelector(".cp-remove-plan").addEventListener("click",()=>{if(confirm(`Törlöd ezt a színt: ${plan.colour}?`)){plans=plans.filter(item=>item.id!==plan.id);savePlans();render();}});
        updateSummary(article,plan);plansRoot.appendChild(article);
      });
    }
    document.getElementById("addPlan").addEventListener("click",addPlan);colourInput.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();addPlan();}});render();
  })();
  </script>
</body>
</html>'''
