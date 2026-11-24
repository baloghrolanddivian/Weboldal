"""Data-entry page for preparing cutting plans by material colour."""

from __future__ import annotations

import json
from pathlib import Path
from .ui_style import style_page
from .edge_catalog import with_edge_lookup

ROUTE = "/apps/szabasterv"
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "korpusz-alkatresz-meretek.json"
FAMILY_LABELS = {"Fiok": "Fiók", "Hatfal": "Hátfal", "Osszekoto": "Összekötő", "Egyeb_alk": "Egyéb alkatrész"}


def render_page(
    inventory_session_path: Path | None = None,
    board_catalog: dict[str, object] | None = None,
) -> bytes:
    """Render the interactive cutting-plan worksheet."""
    size_catalog = load_size_catalog(inventory_session_path)
    colour_catalog = load_colour_catalog(board_catalog)
    colour_catalog = sorted(set(colour_catalog) | {str(item["colour"]) for item in size_catalog}, key=str.casefold)
    colour_json = json.dumps(colour_catalog, ensure_ascii=False).replace("</", "<\\/")
    return style_page(with_edge_lookup(PAGE.replace("{{COLOUR_CATALOG}}", colour_json, 1))).encode("utf-8")


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


def load_size_catalog(inventory_session_path: Path | None = None) -> list[dict[str, object]]:
    """Read the imported warehouse sizes, excluding unassigned generic sizes.

    The optional session argument is retained for existing callers. Live inventory
    and production files do not expand the warehouse-size choices.
    """
    found: dict[tuple[int, int, str], dict[str, object]] = {}

    def add_size(width_value: object, height_value: object, colour_value: object = "", source: str = "", families_value: object = None) -> None:
        try:
            width, height = int(float(str(width_value))), int(float(str(height_value)))
        except (TypeError, ValueError):
            return
        if not (20 <= width <= 4000 and 20 <= height <= 4000):
            return
        colour = str(colour_value or "").strip()
        if not colour:
            return
        key = (width, height, colour.casefold())
        families = sorted({str(family).strip() for family in families_value if isinstance(family, str) and family.strip()}, key=str.casefold) if isinstance(families_value, list) else []
        family_label = " / ".join(FAMILY_LABELS.get(family, family) for family in families)
        found[key] = {
            "width": width,
            "height": height,
            "colour": colour,
            "label": f"{width} × {height} mm" + (f" · {family_label}" if family_label else ""),
            "families": families,
            "source": source,
        }

    try:
        durable_catalog = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        durable_catalog = []
    for item in durable_catalog if isinstance(durable_catalog, list) else []:
        if isinstance(item, dict):
            add_size(item.get("width"), item.get("height"), item.get("colour", ""), str(item.get("source", "")), item.get("families"))

    return sorted(found.values(), key=lambda item: (str(item["colour"]).casefold(), int(item["width"]), int(item["height"])))


PAGE = r'''<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Gépterem</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/styles.css" />
  <style>
    :root{--ink:#14231c;--muted:#66756d;--line:#dce5df;--green:#0d8b55;--green-dark:#096b43;--soft:#eff8f3;--red:#b42318;--orange:#c45a0a}
    *{box-sizing:border-box}.cp-page{min-height:100vh;background:linear-gradient(145deg,#eef7f2 0,#fafcfb 46%,#edf3ef 100%);color:var(--ink);font-family:Manrope,sans-serif}.cp-shell{width:min(1500px,calc(100% - 32px));margin:0 auto;padding:22px 0 52px}.cp-top{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px;padding:18px 22px;border:1px solid rgba(20,35,28,.08);border-radius:22px;background:rgba(255,255,255,.92);box-shadow:0 12px 38px rgba(25,61,42,.08)}.cp-brand{display:flex;align-items:center;gap:13px}.cp-mark{width:42px;height:42px;border-radius:14px;background:linear-gradient(145deg,#12a568,#087648);box-shadow:inset 0 0 0 7px rgba(255,255,255,.18)}.cp-brand strong{display:block;font:700 1.05rem/1 Space Grotesk,sans-serif}.cp-brand small{display:block;margin-top:5px;color:var(--muted);font-weight:700}.cp-back{color:var(--ink);text-decoration:none;font-weight:800}.cp-card{border:1px solid rgba(20,35,28,.09);border-radius:24px;background:#fff;box-shadow:0 16px 42px rgba(25,61,42,.08)}.cp-intro{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:25px;align-items:center;padding:25px 27px}.cp-kicker{margin:0 0 7px;color:var(--green);font-size:.75rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.cp-intro h1{margin:0;font:700 clamp(1.65rem,3vw,2.3rem)/1.08 Space Grotesk,sans-serif}.cp-lead{max-width:750px;margin:10px 0 0;color:var(--muted);line-height:1.55}.cp-print{min-height:46px;border:0;border-radius:13px;background:#182820;color:#fff;padding:0 17px;font-weight:800;cursor:pointer}.cp-create{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:13px;align-items:end;margin-top:18px;padding:20px 22px}.cp-field{display:grid;gap:6px}.cp-field span{color:#48574f;font-size:.74rem;font-weight:800}.cp-field input,.cp-field select{width:100%;min-height:46px;border:1px solid #cfdad3;border-radius:13px;background:#fbfdfc;color:var(--ink);padding:0 13px;font:700 .92rem Manrope,sans-serif;outline:none}.cp-field input:focus,.cp-field select:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(13,139,85,.12)}.cp-add-plan{min-height:46px;border:0;border-radius:13px;background:var(--green);color:#fff;padding:0 20px;font-weight:800;cursor:pointer}.cp-empty{margin-top:18px;padding:50px 25px;text-align:center}.cp-empty strong{display:block;font:700 1.2rem Space Grotesk,sans-serif}.cp-empty p{margin:8px 0 0;color:var(--muted)}.cp-plans{display:grid;gap:18px;margin-top:18px}.cp-plan{overflow:hidden}.cp-plan-head{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 23px;background:linear-gradient(115deg,#153b2a,#0a784a);color:#fff}.cp-plan-title{display:flex;align-items:center;gap:13px}.cp-swatch{width:38px;height:38px;border-radius:12px;background:#4a4d50;border:4px solid rgba(255,255,255,.22)}.cp-plan-title h2{display:inline-flex;align-items:center;gap:10px;margin:0;font:700 1.25rem Space Grotesk,sans-serif}.cp-head-total{display:inline-flex;align-items:center;min-height:29px;padding:0 10px;border-radius:999px;background:rgba(255,255,255,.16);font:800 .72rem Manrope,sans-serif;white-space:nowrap}.cp-head-total strong{margin-right:4px;font-size:.9rem}.cp-plan-title p{margin:5px 0 0;color:rgba(255,255,255,.75);font-size:.78rem;font-weight:700}.cp-remove-plan{border:1px solid rgba(255,255,255,.34);border-radius:11px;background:rgba(255,255,255,.1);color:#fff;padding:9px 12px;font-weight:800;cursor:pointer}.cp-table-wrap{overflow-x:auto}.cp-table{width:100%;min-width:1200px;border-collapse:collapse;table-layout:fixed}.cp-table col.cp-col-index,.cp-table col.cp-col-delete{width:3%}.cp-table col.cp-col-main-size{width:45.8%}.cp-table col.cp-col-main-number{width:10%}.cp-table col.cp-col-offcut-size{width:17.2%}.cp-table col.cp-col-offcut-number,.cp-table col.cp-col-strip{width:5.5%}.cp-table th{padding:11px 9px;background:#f4f8f5;color:#59685f;font-size:.68rem;letter-spacing:.055em;text-align:left;text-transform:uppercase}.cp-table td{padding:10px 7px;border-top:1px solid var(--line);vertical-align:middle}.cp-table td:first-child,.cp-table th:first-child{padding-left:18px}.cp-table td:last-child,.cp-table th:last-child{padding-right:18px}.cp-table input,.cp-table select{width:100%;min-width:0;height:43px;border:1px solid #d1dcd5;border-radius:11px;background:#fff;padding:0 10px;color:var(--ink);font:800 .88rem Manrope,sans-serif;outline:none}.cp-table select{background-image:linear-gradient(45deg,transparent 50%,#567064 50%),linear-gradient(135deg,#567064 50%,transparent 50%);background-position:calc(100% - 16px) 18px,calc(100% - 11px) 18px;background-size:5px 5px,5px 5px;background-repeat:no-repeat;appearance:none;padding-right:32px}.cp-table input:focus,.cp-table select:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(13,139,85,.1)}.cp-table input:disabled,.cp-table select:disabled{background-color:#f1f3f2;color:#98a29c}.cp-size-editor{display:grid;gap:7px}.cp-manual-size{display:grid;grid-template-columns:minmax(75px,1fr) auto minmax(75px,1fr);align-items:center;gap:6px;padding:7px;border-radius:12px;background:#f2f7f4}.cp-manual-size[hidden]{display:none}.cp-manual-size input{min-width:70px;height:38px;text-align:center}.cp-manual-size span{color:#738078;font-weight:900}.cp-row-number{display:grid;place-items:center;width:30px;height:30px;border-radius:10px;background:var(--soft);color:var(--green-dark);font-weight:800}.cp-main-group{background:#e8f6ee!important;color:var(--green-dark)!important;text-align:center!important;font-size:.74rem!important}.cp-offcut-group,.cp-offcut-head{background:#fff1e5!important;color:var(--orange)!important}.cp-offcut-group{text-align:center!important;font-size:.74rem!important}.cp-offcut-start{border-left:3px solid #efb77f!important}.cp-strip-label{display:flex;align-items:center;justify-content:center;gap:7px;color:var(--orange);font-size:.7rem;font-weight:900;white-space:nowrap}.cp-strip-label input{width:20px!important;min-width:20px!important;height:20px!important;padding:0;accent-color:var(--orange)}.cp-remove-row{display:grid;place-items:center;width:38px;height:38px;border:0;border-radius:11px;background:#fff1f0;color:var(--red);font-size:1.12rem;font-weight:800;cursor:pointer}.cp-plan-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 20px;border-top:1px solid var(--line);background:#fbfdfc}.cp-add-row{min-height:42px;border:0;border-radius:12px;background:var(--soft);color:var(--green-dark);padding:0 16px;font-weight:800;cursor:pointer}.cp-summary{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.cp-summary span{padding:8px 11px;border-radius:999px;background:#f0f4f1;color:#425148;font-size:.74rem;font-weight:800}.cp-summary strong{color:var(--green-dark)}.cp-save-state{margin:12px 4px 0;color:var(--muted);font-size:.73rem;font-weight:700;text-align:right}
    .cp-plan-columns{display:grid;grid-template-columns:minmax(0,7fr) minmax(330px,3fr)}.cp-subplan{min-width:0;padding-bottom:16px}.cp-subplan+.cp-subplan{border-left:3px solid #efb77f;background:#fffaf5}.cp-subplan-head{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:58px;padding:12px 18px;background:#e8f6ee;color:var(--green-dark)}.cp-offcut-panel .cp-subplan-head{background:#fff1e5;color:var(--orange)}.cp-subplan-head strong{font:700 1rem Space Grotesk,sans-serif}.cp-subplan-head span{font-size:.7rem;font-weight:800;opacity:.75}.cp-subtable{width:100%;min-width:0;table-layout:auto}.cp-subtable th{white-space:nowrap}.cp-subtable td:first-child,.cp-subtable th:first-child{padding-left:14px}.cp-subtable td:last-child,.cp-subtable th:last-child{padding-right:14px}.cp-main-table .cp-size-cell{width:58%}.cp-offcut-table .cp-size-cell{width:60%}.cp-subplan-empty{padding:25px 16px;color:var(--muted);font-size:.8rem;font-weight:700;text-align:center}.cp-add-row-wrap{padding:12px 16px 0}.cp-offcut-panel .cp-add-row{background:#fff0e2;color:var(--orange)}
    @media(max-width:1000px){.cp-plan-columns{grid-template-columns:1fr}.cp-subplan+.cp-subplan{border-left:0;border-top:3px solid #efb77f}}@media(max-width:760px){.cp-shell{width:calc(100% - 16px);padding-top:8px}.cp-top{padding:14px}.cp-brand small{display:none}.cp-intro{grid-template-columns:1fr;padding:20px}.cp-print{display:none}.cp-create{grid-template-columns:1fr;padding:17px}.cp-plan-head{align-items:flex-start;padding:17px}.cp-plan-title{align-items:flex-start}.cp-plan-foot{align-items:stretch;flex-direction:column}.cp-summary{justify-content:flex-start}.cp-remove-plan{font-size:0}.cp-remove-plan::after{content:"×";font-size:1.2rem}.cp-subtable{min-width:620px}}
    @media print{.cp-page{background:#fff}.cp-top,.cp-create,.cp-empty,.cp-remove-plan,.cp-remove-row,.cp-add-row,.cp-print,.cp-save-state{display:none!important}.cp-shell{width:100%;padding:0}.cp-intro{box-shadow:none;border:0;padding:0 0 18px}.cp-plan{break-inside:avoid;box-shadow:none;margin-bottom:15px}.cp-plans{gap:10px}.cp-table{min-width:0}.cp-table input{border:0;padding:0;min-width:0}.cp-plan-head{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
    .cp-editor-actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:12px;margin-top:18px}
    .cp-editor-actions button:disabled{opacity:.5;cursor:wait}
    .cp-save-state[data-error="true"]{color:var(--red)}
    @media print{.cp-editor-actions{display:none!important}}
  </style>
  <style>
    [hidden]{display:none!important}
    .cp-overview-head{padding:24px;display:flex;align-items:center;justify-content:space-between;gap:24px}
    .cp-overview-head h1{margin:0;font:700 clamp(1.5rem,3vw,2rem) Space Grotesk,sans-serif}
    .cp-overview-head p{margin:8px 0 0;color:var(--muted);line-height:1.5}
    .cp-new-day{display:flex;align-items:end;gap:12px;flex-shrink:0}.cp-new-day input{font-size:1rem;min-width:180px}
    .cp-day-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,290px),1fr));gap:18px;margin-top:18px}
    .cp-day-card{display:flex;flex-direction:column;align-items:stretch;padding:22px;text-align:left;font-family:inherit;color:var(--ink);cursor:pointer;transition:border-color .15s,box-shadow .15s;min-width:0}
    .cp-day-card:hover{border-color:var(--green);box-shadow:0 14px 38px rgba(13,139,85,.14)}
    .cp-day-card:focus-visible{outline:3px solid var(--green);outline-offset:3px}
    .cp-card-date{display:block;font:700 1.3rem Space Grotesk,sans-serif}.cp-card-weekday{display:block;margin-top:4px;color:var(--muted);font-size:.8rem;text-transform:capitalize}
    .cp-card-total{display:block;margin:18px 0 12px;color:var(--green-dark);font-weight:800}.cp-card-total strong{font-size:1.7rem}
    .cp-card-colours{display:grid;gap:8px;padding-top:12px;border-top:1px solid var(--line)}
    .cp-card-colour{display:flex;align-items:baseline;justify-content:space-between;gap:12px;font-size:.85rem}.cp-card-colour>span{overflow-wrap:anywhere}.cp-card-colour strong{white-space:nowrap}
    .cp-card-open{display:block;margin-top:auto;padding-top:18px;color:var(--green-dark);font-size:.8rem;font-weight:800}
    .cp-editor-back{margin-bottom:14px}.cp-overview-status{margin:18px 0;color:var(--muted)}
    .cp-view-tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}.cp-view-tabs a{padding:12px 18px;border-radius:12px;background:#fff;color:var(--green-dark);font-weight:800;text-decoration:none}.cp-view-tabs a[aria-current]{background:var(--green);color:#fff}
    @media(max-width:1000px){.cp-overview-head{align-items:stretch;flex-direction:column;gap:18px}.cp-new-day .cp-field{flex:1}.cp-new-day button{min-height:44px;padding:9px 16px}.cp-day-grid{gap:14px}}
    @media(max-width:560px){.cp-overview-head{padding:18px}.cp-new-day{flex-wrap:wrap}.cp-new-day .cp-field{flex-basis:100%}.cp-day-card{padding:20px}}
    @media print{#overview,.cp-editor-back,.cp-view-tabs{display:none!important}}
  </style>
  <style>
    /* Keep the cutting module in its tablet layout on every screen. */
    @media screen{
      .cp-shell{max-width:768px}
      .cp-plan-columns{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
      .cp-subplan+.cp-subplan{border-left:3px solid #efb77f;border-top:0}
      .cp-subtable{display:block;min-width:0;table-layout:auto}
      .cp-subtable thead{display:none}
      .cp-subtable tbody{display:grid}
      .cp-subtable tr{display:grid;grid-template-columns:minmax(0,2.4fr) minmax(0,.8fr) minmax(0,.8fr) 32px 32px;align-items:end;gap:5px;padding:12px 8px;border-top:1px solid var(--line)}
      .cp-offcut-table tr{grid-template-columns:minmax(0,2.4fr) minmax(0,.8fr) 32px}
      .cp-subtable tr>td,.cp-subtable tr>td:last-child{padding:0;border:0;min-width:0}
      .cp-subtable tr>td:first-child{display:none}
      .cp-subtable tr>.cp-size-cell{grid-column:auto;width:auto}
      .cp-main-table td:nth-child(3)::before,.cp-main-table td:nth-child(4)::before,.cp-offcut-table td:nth-child(3)::before,.cp-size-cell::before,.cp-strip-cell::before{display:block;margin-bottom:5px;font-size:.65rem;font-weight:800;line-height:16px;color:var(--muted)}
      .cp-size-cell::before{content:'Méret (mm)'}
      .cp-strip-cell::before{content:'+100';text-align:center}
      .cp-main-table td:nth-child(3)::before{content:'Tábla'}
      .cp-main-table td:nth-child(4)::before,.cp-offcut-table td:nth-child(3)::before{content:'Darab'}
      .cp-subtable tr>td:last-child{align-self:end}
      .cp-subtable input{min-height:44px;padding:0 3px;font-size:.8rem;text-align:center;appearance:textfield;-moz-appearance:textfield}
      .cp-subtable input::-webkit-inner-spin-button,.cp-subtable input::-webkit-outer-spin-button{appearance:none;margin:0}
      .cp-subtable .cp-remove-row{width:32px;height:44px}
      .cp-strip-cell .cp-strip-label{height:44px}
      .cp-strip-cell input[type="checkbox"]{min-height:20px}
      .cp-subplan-head{padding:12px;min-height:50px}
      .cp-subplan-head strong{font-size:.95rem}
      .cp-add-row-wrap{padding:10px 12px 0}
      .cp-add-row-wrap .cp-add-row{font-size:.75rem;padding:8px 10px;min-height:44px}
      .cp-manual-size{grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:3px;padding:0;background:transparent}
      .cp-manual-size input{min-width:0}
      .cp-overview-head{align-items:stretch;flex-direction:column;gap:18px}
      .cp-overview-head h1{font-size:1.5rem}
      .cp-new-day .cp-field{flex:1}
      .cp-new-day button{min-height:44px;padding:9px 16px}
      .cp-day-grid{gap:14px}
    }
  </style>
  <style>
    .cp-main-table tr[data-board-parent="true"],.cp-main-table tr[data-parent-row-id]{border-left:3px solid var(--green)}
    .cp-main-table tr[data-parent-row-id]{border-top-style:dashed;background:var(--soft)}
    .cp-main-table tr[data-parent-row-id] .cp-size-cell::before{content:'↳ Méret (mm)';color:var(--green-dark)}
    @media screen and (max-width:480px){.cp-plan-columns{min-width:560px}.cp-plan{overflow-x:auto}}
  </style>
  <style>
    .cp-plan-title{flex:1;min-width:0}.cp-collapse-toggle{display:grid;place-items:center;flex:0 0 38px;width:38px;min-height:44px;padding:0;border:1px solid #ffffff50;border-radius:11px;background:#ffffff18;color:#fff;cursor:pointer}
    .cp-collapse-toggle svg{width:21px;height:21px;transition:transform .15s}.cp-collapse-toggle[aria-expanded="false"] svg{transform:rotate(-90deg)}.cp-collapse-toggle:focus-visible{outline:3px solid #fff;outline-offset:3px}
    .cp-plan-head,.cw-colour-head{cursor:pointer}
    @media print{.cp-collapse-toggle{display:none!important}.cp-plan-columns[hidden],.cw-plan-columns[hidden]{display:grid!important}}
    .cp-confirm{width:min(440px,calc(100vw - 32px));padding:26px;border:1px solid var(--line);border-radius:22px;background:#fff;color:var(--ink);font-family:Manrope,sans-serif;box-shadow:0 24px 80px #14231c35}
    .cp-confirm::backdrop{background:#14231c80;backdrop-filter:blur(4px)}
    .cp-confirm h2{margin:0;font:700 1.3rem Space Grotesk,sans-serif}.cp-confirm p{margin:14px 0 24px;color:var(--muted);font-size:.9rem;line-height:1.6;overflow-wrap:anywhere}
    .cp-confirm-actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}.cp-confirm-actions button{min-height:44px}.cp-confirm-danger{background:var(--red)}
  </style>
  <script>
    window.cuttingColourCollapsible=(()=>{
      const states=new Map();let sequence=0;
      return (header,content,key,colour)=>{
        const storageKey='cutting-colour-collapsed:'+key;
        let collapsed=states.get(storageKey);
        if(collapsed===undefined){try{collapsed=sessionStorage.getItem(storageKey)==='true';}catch(_){collapsed=false;}}
        const button=document.createElement('button');button.type='button';button.className='cp-collapse-toggle';
        button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
        content.id='cuttingColourBody'+(++sequence);button.setAttribute('aria-controls',content.id);
        function set(value){
          collapsed=value;content.hidden=value;button.setAttribute('aria-expanded',String(!value));
          button.setAttribute('aria-label',`${colour} ${value?'kinyitása':'összecsukása'}`);
          states.set(storageKey,value);try{sessionStorage.setItem(storageKey,String(value));}catch(_){}
        }
        const swatch=header.querySelector('.cp-swatch');if(swatch)swatch.replaceWith(button);else header.prepend(button);
        button.addEventListener('click',()=>set(!collapsed));
        header.addEventListener('click',event=>{if(!event.target.closest('button,a,input,select,label'))button.click();});
        set(!!collapsed);return ()=>set(false);
      };
    })();
    window.cuttingBoardGroups=(rows,emptyAsZero=false)=>{
      let parent=null;
      const groups=rows.map(row=>{
        const boards=String(row.boards??'').trim();
        if(Number(boards)>0)parent=row;
        return {row,parent:(boards!==''||emptyAsZero)&&Number(boards)===0?parent:null};
      });
      return groups.map((item,index)=>({...item,lastChild:!!item.parent&&groups[index+1]?.parent?.id!==item.parent.id}));
    };
    window.cuttingConfirm=(message,{title='Megerősítés',accept='Folytatás',danger=false}={})=>{
      if(document.querySelector('.cp-confirm[open]'))return Promise.resolve(false);
      return new Promise(resolve=>{
        const dialog=document.createElement('dialog');dialog.className='cp-confirm';
        dialog.setAttribute('aria-labelledby','cpConfirmTitle');dialog.setAttribute('aria-describedby','cpConfirmMessage');
        dialog.innerHTML='<h2 id="cpConfirmTitle"></h2><p id="cpConfirmMessage"></p><div class="cp-confirm-actions"><button type="button" class="cp-add-row" data-confirm="cancel" autofocus>Mégse</button><button type="button" class="cp-add-plan" data-confirm="accept"></button></div>';
        dialog.querySelector('h2').textContent=title;dialog.querySelector('p').textContent=message;
        let settled=false;
        const finish=accepted=>{if(settled)return;settled=true;dialog.close();dialog.remove();resolve(accepted);};
        const confirmButton=dialog.querySelector('[data-confirm="accept"]');confirmButton.textContent=accept;confirmButton.classList.toggle('cp-confirm-danger',danger);
        confirmButton.addEventListener('click',()=>finish(true));
        dialog.querySelector('[data-confirm="cancel"]').addEventListener('click',()=>finish(false));
        dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false);});
        dialog.addEventListener('close',()=>finish(false),{once:true});
        document.body.append(dialog);dialog.showModal();
      });
    };
  </script>
</head>
<body class="cp-page" data-theme-scope="default">
  <main class="cp-shell">
    <header class="cp-top">
      <div class="cp-brand"><span class="cp-mark"></span><div><strong>Divian-HUB</strong><small>Gépterem</small></div></div>
      <a class="cp-back" href="/">← Vissza a modulokhoz</a>
    </header>
    <nav class="cp-view-tabs" aria-label="Szabászati nézetek"><a href="/apps/szabasterv" aria-current="page">Szabászmester</a><a href="/apps/szabasterv/szabasz">Szabász</a><a href="/apps/szabasterv/foliazo">Fóliázó</a><a href="/apps/szabasterv/elpakolas">Elpakolás</a></nav>
    <section id="overview" aria-labelledby="overviewHeading">
      <header class="cp-card cp-overview-head">
        <div><h1 id="overviewHeading" tabindex="-1">Tervezett vágási napok</h1><p>Válassz egy napot a részletekhez és a szerkesztéshez, vagy készíts új napi tervet.</p></div>
        <form class="cp-new-day" id="newDayForm"><label class="cp-field"><span>Új vágási nap dátuma</span><input id="newDayDate" type="date" required /></label><button class="cp-add-plan" id="newDayButton" type="submit">Új nap</button></form>
      </header>
      <p class="cp-overview-status" id="overviewEmpty" hidden>Még nincs mentett vágási nap. Válassz dátumot, és kattints az Új nap gombra.</p>
      <div class="cp-day-grid" id="dayCards" aria-label="Mentett vágási napok"></div>
    </section>
    <div id="editor" tabindex="-1" aria-label="Napi vágási terv" hidden>
    <button class="cp-add-row cp-editor-back" id="backToDays" type="button">← Vissza a napokhoz</button>
    <section class="cp-card cp-create" aria-label="Új színblokk">
      <label class="cp-field"><span>Szín</span><select id="colour" aria-label="Bútorlap színe"></select></label>
      <button class="cp-add-plan" id="addPlan" type="button">Szín hozzáadása</button>
    </section>
    <section class="cp-card cp-empty" id="emptyState"><strong>Még nincs felvett szín.</strong><p>Válassz színt, majd add hozzá az első tervblokkot.</p></section>
    <div class="cp-plans" id="plans"></div>
    <footer class="cp-editor-actions">
      <button class="cp-add-row" id="importLegacy" type="button" hidden>Korábbi helyi terv átvétele</button>
      <button class="cp-add-plan" id="saveDay" type="button">Napi terv mentése</button>
    </footer>
    </div>
    <p class="cp-save-state" id="saveState" role="status" aria-live="polite">Napi tervek betöltése…</p>
  </main>

  <template id="planTemplate">
    <article class="cp-card cp-plan">
      <header class="cp-plan-head"><div class="cp-plan-title"><span class="cp-swatch"></span><div><h2><span data-colour></span><span class="cp-head-total"><strong data-head-board-total>0</strong> tábla</span></h2><p><span data-material></span> · <span data-board-size></span></p></div></div><button class="cp-remove-plan" type="button">Szín törlése</button></header>
      <div class="cp-plan-columns">
        <section class="cp-subplan cp-main-panel"><header class="cp-subplan-head"><div><strong>Normál méretek</strong></div></header><div class="cp-table-wrap"><table class="cp-table cp-subtable cp-main-table"><thead><tr><th>#</th><th>Méret</th><th>Táblák</th><th>Darab</th><th>+100</th><th></th></tr></thead><tbody data-main-body></tbody></table><div class="cp-subplan-empty" data-main-empty>Nincs még korpusz méret.</div></div><div class="cp-add-row-wrap"><button class="cp-add-row cp-add-main-row" type="button">+ Méret hozzáadása</button></div></section>
        <section class="cp-subplan cp-offcut-panel"><header class="cp-subplan-head"><div><strong>Leeső méretek</strong></div><span>Nem kötelező</span></header><div class="cp-table-wrap"><table class="cp-table cp-subtable cp-offcut-table"><thead><tr><th>#</th><th>Méret</th><th>Darab</th><th></th></tr></thead><tbody data-offcut-body></tbody></table><div class="cp-subplan-empty" data-offcut-empty>Nincs még leeső méret.</div></div><div class="cp-add-row-wrap"><button class="cp-add-row cp-add-offcut-row" type="button">+ Leeső méret hozzáadása</button></div></section>
      </div>
    </article>
  </template>
  <template id="mainRowTemplate">
    <tr><td><span class="cp-row-number"></span></td><td class="cp-size-cell"><div class="cp-size-editor"><div class="cp-manual-size" data-manual><input data-field="width" type="number" min="1" aria-label="Kézi szélesség" /><span>×</span><input data-field="height" type="number" min="1" aria-label="Kézi magasság" /></div></div></td><td><input data-field="boards" type="number" min="0" aria-label="Táblák száma" /></td><td><input data-field="pieces" type="number" min="0" aria-label="Darabszám" /></td><td class="cp-strip-cell"><label class="cp-strip-label"><input data-field="strip100" type="checkbox" aria-label="+100" /></label></td><td><button class="cp-remove-row" type="button" aria-label="Korpusz méret törlése">×</button></td></tr>
  </template>
  <template id="offcutRowTemplate">
    <tr><td><span class="cp-row-number"></span></td><td class="cp-size-cell"><div class="cp-size-editor"><div class="cp-manual-size" data-manual><input data-field="width" type="number" min="1" aria-label="Kézi leeső szélesség (nem kötelező)" /><span>×</span><input data-field="height" type="number" min="1" aria-label="Kézi leeső magasság (nem kötelező)" /></div></div></td><td><input data-field="pieces" type="number" min="0" aria-label="Leeső darabszám" /></td><td><button class="cp-remove-row" type="button" aria-label="Leeső méret törlése">×</button></td></tr>
  </template>
  <script>
  (() => {
    const STORAGE_KEY = "divian-cutting-plan-v2";
    const COLOUR_CATALOG = {{COLOUR_CATALOG}};
    const plansRoot = document.getElementById("plans"), emptyState = document.getElementById("emptyState");
    const colourInput = document.getElementById("colour");
    COLOUR_CATALOG.forEach(colour => {
      const option=document.createElement("option");option.value=colour;option.textContent=colour;colourInput.appendChild(option);
    });
    if(COLOUR_CATALOG.includes("Antracit"))colourInput.value="Antracit";
    let lockedRows = new Set();
    let plans = [], activeDay = "", revision = 0, dirty = false, busy = false, editVersion = 0;
    const saveButton=document.getElementById("saveDay");
    const legacyPlans=loadPlans();
    const importButton=document.getElementById("importLegacy");
    importButton.hidden=!legacyPlans.length;
    const now=new Date();
    const overview=document.getElementById("overview"), editor=document.getElementById("editor"), newDayDate=document.getElementById("newDayDate");
    newDayDate.value=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
    function status(message,error=false){const el=document.getElementById("saveState");el.textContent=message;el.dataset.error=String(error);}
    function setBusy(value){busy=value;saveButton.disabled=value||!activeDay;plansRoot.inert=value;document.querySelector(".cp-create").inert=value;importButton.disabled=value||lockedRows.size>0;document.getElementById("backToDays").disabled=value;document.getElementById("newDayButton").disabled=value;newDayDate.disabled=value;document.getElementById("dayCards").inert=value;}
    function showDays(days){
      const cards=document.getElementById("dayCards");cards.replaceChildren();document.getElementById("overviewEmpty").hidden=days.length>0;
      days.forEach(item=>{
        const card=document.createElement("button");card.type="button";card.className="cp-card cp-day-card";card.dataset.day=item.day;
        const add=(className,text,parent=card)=>{const el=document.createElement("span");el.className=className;el.textContent=text;parent.appendChild(el);return el;};
        const date=add("cp-card-date",item.day.replaceAll("-",". ")+".");
        const weekday=new Date(item.day+"T12:00:00").toLocaleDateString("hu-HU",{weekday:"long"});add("cp-card-weekday",weekday);
        const total=add("cp-card-total","");const number=document.createElement("strong");number.textContent=String(item.total_boards||0);total.append(number,document.createTextNode(" tábla összesen"));
        const colours=add("cp-card-colours","");
        (item.colours||[]).forEach(entry=>{const line=add("cp-card-colour","",colours);add("",entry.colour,line);const count=document.createElement("strong");count.textContent=`${entry.boards} tábla`;line.appendChild(count);});
        if(!(item.colours||[]).length)add("cp-card-colour","Még nincs felvett szín.",colours);
        add("cp-card-open","Terv megnyitása →");card.setAttribute("aria-label",`${date.textContent} · ${item.total_boards||0} tábla · Terv megnyitása`);
        card.addEventListener("click",()=>openDay(item.day));cards.appendChild(card);
      });
    }
    async function loadOverview(){setBusy(true);status("Napi tervek betöltése…");try{const data=await request("/apps/szabasterv/napok");showDays(data.days);status("");}catch(error){status(error.message,true);}finally{setBusy(false);}}
    async function backToOverview(){
      if(busy)return;
      if(dirty&&!await cuttingConfirm("Vannak nem mentett módosítások. Visszalépsz a napokhoz? A helyi piszkozat megmarad."))return;
      if(dirty)rememberDraft();dirty=false;activeDay="";editor.hidden=true;overview.hidden=false;document.getElementById("overviewHeading").focus();loadOverview();
    }
    async function request(url,options){const response=await fetch(url,options);if(!response.ok){let message="A napi terv nem érhető el. Próbáld újra.";try{message=(await response.json()).error||message;}catch(_){}throw new Error(message);}const data=await response.json();if(!data.ok)throw new Error(data.error||"Sikertelen művelet.");return data;}
    function draftKey(day){return `divian-cutting-day-draft:${day}`;}
    function rememberDraft(){if(!activeDay)return;try{localStorage.setItem(draftKey(activeDay),JSON.stringify({revision,plans}));}catch(_){status("Nem mentett módosítások. A helyi biztonsági mentés nem sikerült; mentsd a napi tervet!",true);}}
    async function openDay(day){
      if(busy)return;
      if(!day){status("Válassz napot.",true);return;}
      if(dirty&&!await cuttingConfirm("Vannak nem mentett módosítások. Megnyitod a másik napot? A helyi piszkozat megmarad."))return;
      setBusy(true);
      try{
        const data=await request(`/apps/szabasterv/napok?day=${encodeURIComponent(day)}`);
        const record=data.record;lockedRows=new Set((record.progress||[]).filter(item=>item.done).map(item=>JSON.stringify([item.plan_id,item.row_group,item.row_id])));activeDay=record.day;revision=record.revision;plans=record.plans.map(normalizePlan);dirty=false;editVersion++;
        let restored=false;
        try{const draft=JSON.parse(localStorage.getItem(draftKey(activeDay))||"null");if(draft&&Array.isArray(draft.plans)&&JSON.stringify(draft.plans)!==JSON.stringify(plans)&&await cuttingConfirm("Ehhez a naphoz helyi, nem mentett piszkozat található. Visszaállítod?")){plans=draft.plans.map(normalizePlan);revision=draft.revision;dirty=true;restored=true;}}catch(_){}
        restoreLockedRows(record.plans);
        showDays(data.days);render();editor.setAttribute("aria-label",`Napi vágási terv · ${activeDay}`);
        overview.hidden=true;editor.hidden=false;editor.focus();
        status(restored?"Helyi piszkozat visszaállítva. A szerverre mentéshez kattints a Napi terv mentése gombra.":revision?"Mentett napi terv megnyitva. Szerkesztés után mentsd a változásokat.":"Új nap. A létrehozáshoz mentsd el a napi tervet.");
      }catch(error){status(error.message,true);}finally{setBusy(false);}
    }
    async function persistDay(){
      if(busy||!activeDay)return;
      const savingVersion=editVersion, snapshot=JSON.parse(JSON.stringify(plans));setBusy(true);status("Mentés folyamatban…");
      try{const data=await request("/apps/szabasterv/napok",{method:"POST",headers:{"Content-Type":"application/json","X-Requested-With":"Divian-HUB"},body:JSON.stringify({day:activeDay,plans:snapshot,revision})});revision=data.record.revision;dirty=editVersion!==savingVersion;showDays(data.days);if(dirty){rememberDraft();status("A korábbi állapot mentve. Az újabb módosítások még mentésre várnak.");}else{try{localStorage.removeItem(draftKey(activeDay));}catch(_){}status(`Napi terv mentve · ${activeDay}`);}}
      catch(error){status(error.message,true);}finally{setBusy(false);}
    }
    function newId() { return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`; }
    function blankMainRow() { return {id:newId(),sizeMode:"manual",width:"",height:"",boards:"",pieces:"",strip100:false}; }
    function blankOffcutRow() { return {id:newId(),sizeMode:"manual",width:"",height:"",pieces:""}; }
    function cleanNumber(value) { return Math.max(0,Math.floor(Number(value)||0)); }
    function normalizePlan(plan) {
      if(Array.isArray(plan.mainRows)&&Array.isArray(plan.offcutRows))return plan;
      const legacy=Array.isArray(plan.rows)?plan.rows:[];
      plan.mainRows=legacy.map(row=>({id:`${row.id||newId()}-main`,sizeMode:row.sizeMode||"",width:row.width||"",height:row.height||"",boards:row.boards||"",pieces:row.pieces||""}));
      plan.offcutRows=legacy.filter(row=>row.offcutWidth||row.offcutHeight||row.offcutPieces||row.strip100).map(row=>({id:`${row.id||newId()}-offcut`,sizeMode:row.offcutSizeMode||"",width:row.offcutWidth||"",height:row.offcutHeight||"",pieces:row.strip100?(row.boards||""):(row.offcutPieces||""),strip100:Boolean(row.strip100)}));
      delete plan.rows;return plan;
    }
    function loadPlans() { try { const value=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");return Array.isArray(value)?value.map(normalizePlan):[]; } catch (_) { return []; } }
    function savePlans() { dirty=true;editVersion++;status("Nem mentett módosítások · A szerverre mentéshez kattints a Napi terv mentése gombra.");rememberDraft(); }
    function addPlan() {
      if(!activeDay){status("Előbb nyiss meg egy napot.",true);return;}
      const colour=colourInput.value.trim();if(!colour){colourInput.focus();return;}
      const evogloss=colour.toLocaleLowerCase("hu").includes("evogloss"),material=evogloss?"Evogloss lap":"Standard bútorlap",boardSize=evogloss?"2800 × 1220 mm":"2800 × 2070 mm";
      const existing=plans.find(plan=>plan.colour.toLocaleLowerCase("hu")===colour.toLocaleLowerCase("hu"));
      if(existing){const article=document.querySelector(`[data-plan-id="${existing.id}"]`);article?.expandColour?.();article?.scrollIntoView({behavior:"smooth",block:"center"});return;}
      plans.push({id:newId(),colour,material,boardSize,mainRows:[],offcutRows:[]});savePlans();render();requestAnimationFrame(()=>document.querySelector(`[data-plan-id="${plans.at(-1).id}"] .cp-add-main-row`)?.focus());
    }
    function updateSummary(article,plan) {
      const boardTotal=plan.mainRows.reduce((sum,row)=>sum+cleanNumber(row.boards),0);
      article.querySelector("[data-head-board-total]").textContent=String(boardTotal);
      const groups=cuttingBoardGroups(plan.mainRows),parents=new Set(groups.filter(item=>item.parent).map(item=>item.parent.id));
      const rows=article.querySelector('[data-main-body]').children;
      groups.forEach(({row,parent,lastChild},index)=>{
        const tr=rows[index];tr.dataset.boardParent=String(parents.has(row.id));
        tr.dataset.groupEnd=String(lastChild);
        if(parent){tr.dataset.parentRowId=parent.id;tr.querySelector('[data-field="boards"]').title=`A(z) ${parent.width||'–'} × ${parent.height||'–'} mm mérettel közös ${parent.boards} táblából.`;}
        else{delete tr.dataset.parentRowId;tr.querySelector('[data-field="boards"]').removeAttribute('title');}
      });
    }
    function bindSizeEditor(tr,row,plan) {
      tr.querySelectorAll('[data-field]:not([type="checkbox"])').forEach(input=>{const field=input.dataset.field;input.value=row[field]??"";input.addEventListener("input",()=>{row[field]=input.value;savePlans();});});
      const edge=window.cuttingEdgeBadge(row.width,row.height,plan.colour),sizeHeading=document.createElement('div');sizeHeading.className='cp-size-heading';
      const sizeTitle=document.createElement('span');sizeTitle.textContent='Méret (mm)';sizeHeading.append(sizeTitle,edge);tr.querySelector('.cp-size-cell').prepend(sizeHeading);
      tr.querySelectorAll('[data-field="width"],[data-field="height"]').forEach(input=>input.addEventListener('input',()=>window.cuttingUpdateEdgeBadge(edge,row.width,row.height,plan.colour)));
      const fields=[...tr.querySelectorAll('input[type="number"]')];
      fields.forEach((input,index)=>{
        input.inputMode='numeric';input.enterKeyHint='next';
        input.addEventListener('keydown',event=>{
          if(event.isComposing||event.shiftKey||!['Enter','Tab'].includes(event.key))return;
          event.preventDefault();
          if(event.repeat||input.disabled||busy)return;
          if(!input.checkValidity()){input.reportValidity();return;}
          if(index<fields.length-1){fields[index+1].focus();return;}
          addSizeRow(plan,plan.mainRows.includes(row)?'mainRows':'offcutRows');
        });
      });
      const strip=tr.querySelector('[data-field="strip100"]');
      if(strip){strip.checked=Boolean(row.strip100);strip.addEventListener("change",()=>{row.strip100=strip.checked;savePlans();});}
    }

    function addSizeRow(plan,group){
      if(busy)return;
      plan[group].push(group==='mainRows'?blankMainRow():blankOffcutRow());savePlans();render();
      const body=group==='mainRows'?'data-main-body':'data-offcut-body';
      const input=document.querySelector(`[data-plan-id="${plan.id}"] [${body}] tr:last-child [data-field="width"]`);
      input?.focus();input?.scrollIntoView({block:'nearest',inline:'nearest'});
    }

    function restoreLockedRows(savedPlans){
      savedPlans.forEach(savedPlan=>{
        if(![...lockedRows].some(key=>JSON.parse(key)[0]===savedPlan.id))return;
        let plan=plans.find(item=>item.id===savedPlan.id);
        if(!plan){plan={...savedPlan,mainRows:[],offcutRows:[]};plans.push(plan);}
        for(const field of ['colour','material','boardSize'])plan[field]=savedPlan[field];
        for(const group of ['mainRows','offcutRows']){
          savedPlan[group].forEach(row=>{
            if(!lockedRows.has(JSON.stringify([plan.id,group,row.id])))return;
            const index=plan[group].findIndex(item=>item.id===row.id),copy=structuredClone(row);
            if(index<0)plan[group].push(copy);else plan[group][index]=copy;
          });
        }
      });
    }
    function lockRow(tr,planId,group,rowId){
      if(!lockedRows.has(JSON.stringify([planId,group,rowId])))return;
      tr.dataset.locked='true';tr.title='Levágva · A szabászmester már nem módosíthatja.';
      tr.querySelectorAll('input,select,button').forEach(control=>control.disabled=true);
      tr.querySelector('.cp-remove-row').textContent='🔒';
    }
    function render() {
      plansRoot.innerHTML="";emptyState.hidden=plans.length>0;
      plans.forEach(plan=>{
        const article=document.getElementById("planTemplate").content.firstElementChild.cloneNode(true);article.dataset.planId=plan.id;
        article.expandColour=cuttingColourCollapsible(article.querySelector('.cp-plan-head'),article.querySelector('.cp-plan-columns'),JSON.stringify(['master',activeDay,plan.id]),plan.colour);
        article.querySelector("[data-colour]").textContent=plan.colour;article.querySelector("[data-material]").textContent=plan.material;article.querySelector("[data-board-size]").textContent=plan.boardSize;
        const mainBody=article.querySelector("[data-main-body]"),offcutBody=article.querySelector("[data-offcut-body]");article.querySelector("[data-main-empty]").hidden=plan.mainRows.length>0;article.querySelector("[data-offcut-empty]").hidden=plan.offcutRows.length>0;
        plan.mainRows.forEach((row,index)=>{const tr=document.getElementById("mainRowTemplate").content.firstElementChild.cloneNode(true);tr.querySelector(".cp-row-number").textContent=String(index+1);bindSizeEditor(tr,row,plan);tr.querySelectorAll('[data-field="boards"],[data-field="pieces"]').forEach(input=>input.addEventListener("input",()=>updateSummary(article,plan)));tr.querySelector(".cp-remove-row").addEventListener("click",()=>{plan.mainRows=plan.mainRows.filter(item=>item.id!==row.id);savePlans();render();});lockRow(tr,plan.id,"mainRows",row.id);mainBody.appendChild(tr);});
        plan.offcutRows.forEach((row,index)=>{const tr=document.getElementById("offcutRowTemplate").content.firstElementChild.cloneNode(true);tr.querySelector(".cp-row-number").textContent=String(index+1);bindSizeEditor(tr,row,plan);tr.querySelector(".cp-remove-row").addEventListener("click",()=>{plan.offcutRows=plan.offcutRows.filter(item=>item.id!==row.id);savePlans();render();});lockRow(tr,plan.id,"offcutRows",row.id);offcutBody.appendChild(tr);});
        article.querySelector(".cp-add-main-row").addEventListener("click",()=>addSizeRow(plan,'mainRows'));
        article.querySelector(".cp-add-offcut-row").addEventListener("click",()=>addSizeRow(plan,'offcutRows'));
        article.querySelector(".cp-remove-plan").addEventListener("click",async()=>{if(await cuttingConfirm(`Törlöd ezt a színt: ${plan.colour}?`,{title:'Szín törlése',accept:'Törlés',danger:true})){plans=plans.filter(item=>item.id!==plan.id);savePlans();render();}});
        article.querySelector(".cp-remove-plan").disabled=[...lockedRows].some(key=>JSON.parse(key)[0]===plan.id);
        updateSummary(article,plan);plansRoot.appendChild(article);
      });
    }
    document.getElementById("newDayForm").addEventListener("submit",event=>{event.preventDefault();openDay(newDayDate.value);});
    document.getElementById("backToDays").addEventListener("click",backToOverview);
    saveButton.addEventListener("click",persistDay);
    importButton.addEventListener("click",async()=>{if(!activeDay||busy||lockedRows.size)return;if(plans.length&&!await cuttingConfirm("A napi tervet lecseréled a korábbi helyi tervre?"))return;plans=JSON.parse(JSON.stringify(legacyPlans));savePlans();render();});
    window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
    document.getElementById("addPlan").addEventListener("click",addPlan);colourInput.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();addPlan();}});render();loadOverview();
  })();
  </script>
</body>
</html>'''
