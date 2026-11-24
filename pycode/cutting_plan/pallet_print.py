"""Physical-size pallet labels and an A4 test-print preview."""

from datetime import date
from html import escape

from .pallet_store import load_pallets


ROUTE = "/apps/szabasterv/raklap-nyomtatas"
FORMATS = {"a5": (148, 210, "A5 · 148 × 210 mm"), "label": (105, 80, "Címke · 105 × 80 mm")}


def render_page(root, day, pallet_id, paper="a4", label_format="a5"):
    if label_format not in FORMATS or paper not in ("a4", "actual"):
        raise ValueError("Válassz A5-ös vagy 105 × 80 mm-es címkét és érvényes papírméretet.")
    state = load_pallets(root, day)
    pallet = next((item for item in state["pallets"] if item["id"] == pallet_id), None)
    if pallet is None or not pallet["allocations"]:
        raise ValueError("Csak mentett, legalább egy méretet tartalmazó raklap nyomtatható.")
    sources = {(item["plan_id"], item["row_group"], item["row_id"]): item for item in state["items"]}
    rows = []
    for allocation in pallet["allocations"]:
        item = sources.get((allocation["plan_id"], allocation["row_group"], allocation["row_id"]))
        if item is None:
            raise ValueError("A raklap egyik tételének adatai hiányoznak. Nyisd meg újra a raklapot.")
        if item.get("strip100") and item["row_group"] == "offcutRows":
            dimensions = "+100 csík"
        elif item.get("width") or item.get("height"):
            dimensions = f'{item.get("width") or "–"} × {item.get("height") or "–"} mm'
            if item.get("strip100"):
                dimensions += " · +100"
        else:
            dimensions = "Méret nélkül"
        rows.append(f'<tr><td>{escape(item["colour"])}</td><td>{escape(dimensions)}</td><td>{allocation["quantity"]}</td></tr>')
    width, height, _ = FORMATS[label_format]
    sheet_width, sheet_height = (210, 297) if paper == "a4" else (width, height)
    options = "".join(f'<option value="{key}"{" selected" if key == label_format else ""}>{value[2]}</option>' for key, value in FORMATS.items())
    paper_options = '<option value="a4"{}>A4-es tesztlap</option><option value="actual"{}>Saját méretű papír</option>'.format(" selected" if paper == "a4" else "", " selected" if paper == "actual" else "")
    cut_day = date.fromisoformat(day).strftime("%Y. %m. %d.")
    replacements = {
        "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height), "{{SHEET_WIDTH}}": str(sheet_width), "{{SHEET_HEIGHT}}": str(sheet_height),
        "{{MARGIN}}": "10" if paper == "a4" else "0", "{{PAGE_SIZE}}": "A4 portrait" if paper == "a4" else f"{width}mm {height}mm",
        "{{FORMAT}}": label_format, "{{OPTIONS}}": options, "{{PAPER_OPTIONS}}": paper_options,
        "{{DAY}}": escape(day), "{{PALLET_ID}}": escape(pallet_id, quote=True), "{{DATE}}": cut_day,
        "{{NAME}}": escape(pallet["name"]), "{{TOTAL}}": str(pallet["total_pieces"]), "{{ROWS}}": "".join(rows),
    }
    page = PAGE
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page.encode("utf-8")


PAGE = r'''<!doctype html>
<html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raklap nyomtatási kép · {{NAME}}</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf2ef;color:#17251e;font-family:Arial,sans-serif}
.toolbar{max-width:1000px;margin:24px auto 0;padding:22px 24px;background:#fff;border:1px solid #dae4dd;border-radius:18px}
.toolbar h1{margin:0 0 8px;font-size:23px}.toolbar p{margin:6px 0 18px;font-size:14px;line-height:1.5;color:#586b60}
.controls{display:flex;flex-wrap:wrap;align-items:end;gap:12px}.controls label{display:grid;gap:6px;font-size:12px;font-weight:bold}.controls select,.controls button{min-height:44px;border:1px solid #ccd9d0;border-radius:10px;background:#fff;padding:0 12px;font:inherit;color:inherit}.controls button{cursor:pointer;font-weight:bold}.controls .print{background:#0d8b55;color:white;border:0;padding:0 22px}.controls button:disabled{opacity:.45;cursor:wait}
.preview{overflow:auto;padding:24px 16px 40px}.sheet{width:{{SHEET_WIDTH}}mm;height:{{SHEET_HEIGHT}}mm;padding:{{MARGIN}}mm;margin:0 auto 24px;background:white;box-shadow:0 5px 30px #153b2a20;break-after:page;page-break-after:always}.sheet:last-child{break-after:auto;page-break-after:auto}
.label{width:{{WIDTH}}mm;height:{{HEIGHT}}mm;padding:6mm;display:flex;flex-direction:column;border:.2mm dashed #8c968e;color:#111;background:#fff;overflow:hidden}
.label[data-format="label"]{padding:4mm}
.label-head{display:flex;align-items:start;justify-content:space-between;gap:4mm;padding-bottom:3mm;border-bottom:.5mm solid #111;flex-shrink:0}
.label-head>div:first-child{min-width:0}.label-head h2{margin:0;font-size:20pt;line-height:1.1;overflow-wrap:anywhere}.label-head .date{text-align:right;font-size:11pt;line-height:1.4;white-space:nowrap}.label-head small{display:block;font-size:8pt;color:#444;margin-bottom:1mm}
.label-body{flex:1;min-height:0;padding-top:2mm;overflow:hidden}table{width:100%;border-collapse:collapse;table-layout:fixed}col.colour{width:43%}col.size{width:39%}col.quantity{width:18%}th,td{text-align:left;overflow-wrap:anywhere;vertical-align:top}th{font-size:9pt;padding:1.5mm 1mm 2mm;border-bottom:.3mm solid #111}td{font-size:12pt;line-height:1.35;padding:2.5mm 1mm;border-bottom:.2mm solid #aaa}th:last-child,td:last-child{text-align:right;font-weight:bold}td:nth-child(2){font-weight:bold}
.label-foot{display:flex;justify-content:space-between;align-items:end;gap:3mm;border-top:.5mm solid #111;padding-top:3mm;flex-shrink:0;font-size:9pt}.label-foot strong{display:block;font-size:18pt}.page-number{white-space:nowrap;font-size:8pt;color:#444}
.label[data-format="label"] .label-head{padding-bottom:2mm}.label[data-format="label"] .label-head h2{font-size:13pt}.label[data-format="label"] .date{font-size:9pt}.label[data-format="label"] .label-head small{font-size:7pt}.label[data-format="label"] th{font-size:7.5pt;padding:1mm}.label[data-format="label"] td{font-size:9pt;line-height:1.25;padding:1.4mm 1mm}.label[data-format="label"] .label-foot{padding-top:2mm;font-size:7.5pt}.label[data-format="label"] .label-foot strong{font-size:13pt}.label[data-format="label"] .page-number{font-size:7pt}
.label.compact td{font-size:8pt!important;line-height:1.15!important;padding:.8mm 1mm!important}
@page{size:{{PAGE_SIZE}};margin:0}
@media print{html,body{margin:0;background:white}.toolbar{display:none}.preview{padding:0;overflow:visible}.sheet{margin:0;box-shadow:none}.label{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
@media(max-width:700px){.toolbar{margin:12px 12px 0;padding:18px}.toolbar h1{font-size:20px}}
</style></head><body>
<header class="toolbar"><h1>Raklap nyomtatási kép</h1><p>A szín, a méret és a darabszám a mentett raklap adataiból készül. Ha több tétel van, a folytatás külön címkére kerül.</p>
<form class="controls" method="get"><input type="hidden" name="day" value="{{DAY}}"><input type="hidden" name="pallet_id" value="{{PALLET_ID}}">
<label>Címke mérete<select name="format" id="labelFormat">{{OPTIONS}}</select></label><label>Papír<select name="paper" id="paperFormat">{{PAPER_OPTIONS}}</select></label><button type="submit">Előnézet frissítése</button><button class="print" id="printPallet" type="button" disabled>Nyomtatás</button></form>
<p style="margin:16px 0 0" id="printHint">A4-es teszthez: Kyocera ECOSYS P2040dn, álló A4, 100% / tényleges méret; fejléc és lábléc kikapcsolva. A szaggatott vonal a címke vágási határa.</p></header>
<main class="preview" id="printPages" aria-label="Nyomtatási kép"></main>
<template id="labelTemplate"><section class="sheet"><article class="label" data-format="{{FORMAT}}"><header class="label-head"><div><small>DIVIAN-HUB · RAKLAP</small><h2>{{NAME}}</h2></div><div class="date"><small>Vágás napja</small>{{DATE}}</div></header><div class="label-body"><table><colgroup><col class="colour"><col class="size"><col class="quantity"></colgroup><thead><tr><th>Szín</th><th>Méret</th><th>Darab</th></tr></thead><tbody></tbody></table></div><footer class="label-foot"><div>Raklap összesen<strong>{{TOTAL}} db</strong></div><span class="page-number"></span></footer></article></section></template>
<template id="rowsTemplate"><table><tbody>{{ROWS}}</tbody></table></template>
<script>
(async()=>{
 await document.fonts.ready;
 const pages=document.getElementById('printPages'),template=document.getElementById('labelTemplate');
 let sheet,card,body,table,tbody;
 function newPage(){sheet=template.content.firstElementChild.cloneNode(true);pages.append(sheet);card=sheet.querySelector('.label');body=sheet.querySelector('.label-body');table=sheet.querySelector('table');tbody=sheet.querySelector('tbody');}
 newPage();
 for(const original of document.getElementById('rowsTemplate').content.querySelectorAll('tr')){
  const row=original.cloneNode(true);tbody.append(row);
  if(table.getBoundingClientRect().height>body.clientHeight+.5&&tbody.children.length>1){row.remove();newPage();tbody.append(row);}
  if(table.getBoundingClientRect().height>body.clientHeight+.5)card.classList.add('compact');
 }
 const all=[...pages.querySelectorAll('.sheet')];
 all.forEach((page,index)=>page.querySelector('.page-number').textContent=`${index+1} / ${all.length}`);
 document.getElementById('printPallet').disabled=false;
 document.getElementById('printPallet').addEventListener('click',()=>window.print());
 document.documentElement.dataset.printReady='true';
})();
</script></body></html>'''
