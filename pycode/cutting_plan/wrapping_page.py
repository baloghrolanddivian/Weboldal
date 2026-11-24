"""Pallet selection, persistent wrapping checklists and completion reporting."""

from pathlib import Path

from .page import PAGE
from .ui_style import style_page
from .history_ui import add_history_tabs
from .edge_catalog import with_edge_lookup

ROUTE = "/apps/szabasterv/foliazo"


def render_page():
    logic = Path(__file__).with_name("wrapping.js").read_text(encoding="utf-8")
    page = PAGE.split("</head>", 1)[0].replace("Gépterem", "Fóliázó") + BODY.replace("{{WRAPPING_LOGIC}}", logic)
    return style_page(with_edge_lookup(add_history_tabs(page, "foliazo"))).encode("utf-8")


BODY = r'''
<style>
 .fw-tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}.fw-tabs a{padding:12px 18px;border-radius:12px;background:#fff;color:var(--green-dark);font-weight:800;text-decoration:none}.fw-tabs a[aria-current]{background:var(--green);color:#fff}
 .fw-toolbar{padding:22px;display:flex;gap:14px;align-items:end;flex-wrap:wrap}.fw-toolbar>div{flex:1;min-width:230px}.fw-toolbar h1{margin:0;font:700 1.7rem Space Grotesk,sans-serif}.fw-toolbar p{margin:8px 0 0;color:var(--muted);line-height:1.5}.fw-toolbar input{font-size:1rem;min-width:180px}.fw-toolbar button{min-height:44px}
 .fw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,330px),1fr));gap:18px;margin-top:18px}.fw-card{padding:22px}.fw-card h2{margin:0;font:700 1.3rem Space Grotesk,sans-serif;overflow-wrap:anywhere}.fw-meta{font-size:.8rem;color:var(--muted);line-height:1.5;margin:8px 0}.fw-ready{display:inline-block;background:var(--soft);color:var(--green-dark);padding:7px 10px;border-radius:10px;font-size:.8rem;font-weight:800}.fw-total{font-weight:800;margin:14px 0}.fw-item{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid var(--line);font-size:.85rem;line-height:1.5}.fw-item>span{overflow-wrap:anywhere}.fw-item strong{white-space:nowrap}.fw-status{color:var(--muted);margin:16px 3px;font-size:.85rem}.fw-status[data-error="true"]{color:var(--red)}
 .fw-toolbar{padding:18px}.fw-toolbar>div{flex-basis:100%}.fw-toolbar .cp-field{flex:1}.fw-toolbar input{min-width:0}.fw-card{padding:18px}
 .fw-card button{margin-top:14px;min-height:44px}.fw-checklist{padding:22px;margin-top:18px}.fw-check{display:flex;gap:14px;align-items:center;padding:18px 0;border-bottom:1px solid var(--line);cursor:pointer;min-height:64px}.fw-check input{width:26px;height:26px;accent-color:var(--green);flex-shrink:0}.fw-check span{flex:1;overflow-wrap:anywhere;font-weight:700;line-height:1.5}.fw-check strong{white-space:nowrap}.fw-check:has(input:checked){color:var(--green-dark);background:var(--soft)}.fw-checklist button{min-height:44px;margin:16px 10px 0 0}.fw-card[data-completed="true"]{border-color:#87ba9f}.fw-detail-heading:focus{outline:none}.fw-detail-actions{display:flex;gap:10px;flex-wrap:wrap}.fw-detail-status{margin:14px 0;font-size:.85rem;line-height:1.5}.fw-detail-status[data-error="true"]{color:var(--red)}
 @media(max-width:560px){.fw-checklist{padding:18px}.fw-check{gap:10px;font-size:.85rem}.fw-toolbar>div{min-width:0}}
 .fw-checklist button:disabled{opacity:.45;cursor:not-allowed}
 .fw-check-label{display:flex;align-items:center;gap:14px;flex:1;min-width:0;cursor:pointer}.fw-check-label input[type="checkbox"]{width:26px;height:26px}.fw-original{display:block;margin-top:5px;color:var(--muted);font-size:.8rem;font-weight:400}.fw-good{display:grid;gap:6px;flex:0 0 180px}.fw-good>span{font-size:.74rem;font-weight:800}.fw-good input[type="number"]{width:100%;min-height:44px;height:44px;border:1px solid #cfdad3;border-radius:12px;background:#fff;color:var(--ink);padding:0 12px;font:700 1rem Manrope,sans-serif;text-align:center;accent-color:auto}.fw-rejected{color:var(--orange);font-size:.75rem;font-weight:400}.fw-check{cursor:default}.fw-check:has(input[type="checkbox"]:checked){color:var(--green-dark);background:var(--soft)}
 @media(max-width:560px){.fw-check{align-items:stretch;flex-direction:column}.fw-good{flex:auto;margin-left:36px}.fw-good input[type="number"]{max-width:180px}}
 .fw-check[data-wrapped="true"]{background:var(--soft);color:var(--green-dark)}.fw-check>button{margin:0;flex-shrink:0;min-width:130px}.fw-check-label{cursor:default}.fw-good{flex-basis:160px}
 @media(max-width:560px){.fw-good{margin-left:0;flex-basis:auto}.fw-check>button{align-self:flex-start}}
 .fw-card{padding:0}.fw-card .fw-pallet{display:block;width:100%;margin:0;padding:22px;border:0;border-radius:inherit;background:transparent;color:var(--ink);text-align:left;cursor:pointer;font:inherit}.fw-pallet:hover{background:var(--soft)}.fw-pallet:focus-visible{outline:3px solid var(--green);outline-offset:3px}.fw-pallet time{display:block;margin:10px 0 0}
 .fw-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.fw-grid>.fw-card{min-width:0}.fw-card .fw-pallet{padding:14px;height:100%}.fw-card h2{font-size:1rem;line-height:1.4}.fw-item{gap:8px;font-size:.78rem}.fw-item>span{min-width:0}
 @media(max-width:699px){.fw-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
 @media(max-width:479px){.fw-grid{grid-template-columns:minmax(0,1fr)}}
 .fw-card h2,.fw-pallet time,.fw-item>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fw-card h2{font-size:.88rem}.fw-pallet time{font-size:.72rem}.fw-item>span{flex:1}.fw-item strong{flex-shrink:0}
 .fw-detail-status:empty{display:none}.fw-checklist{margin-top:0}.fw-check:last-child{border-bottom:0}.fw-check-label>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .fw-check-label{gap:10px}.fw-check-label>span{min-width:0}.fw-quantity{flex-shrink:0;display:inline-block;padding:6px 10px;border-radius:9px;background:var(--soft);color:var(--green-dark);font-size:1rem;font-weight:800;line-height:1.3}
 .fw-card h2 time{margin:0;font:inherit;color:inherit}.fw-card .fw-item:first-of-type{margin-top:10px}
 .cp-pallet-dialog{width:min(900px,calc(100% - 24px));max-height:90dvh;padding:48px 22px 22px;border:1px solid var(--line);border-radius:20px;background:#fff;color:var(--ink);box-shadow:0 24px 80px #173b2a40;overflow:auto}.cp-pallet-dialog::backdrop{background:#14271db3;backdrop-filter:blur(3px)}.cp-dialog-close{position:absolute;top:8px;right:10px;width:36px;height:36px;border:0;border-radius:10px;background:var(--soft);color:var(--ink);font-size:1.5rem;cursor:pointer}.cp-dialog-close:disabled{opacity:.45;cursor:wait}.cp-pallet-dialog .fw-checklist{padding:0;border:0;box-shadow:none}.cp-pallet-dialog .fw-check:first-child{padding-top:0}
</style></head><body class="cp-page" data-theme-scope="default"><main class="cp-shell">
 <header class="cp-top"><div class="cp-brand"><span class="cp-mark"></span><div><strong>Divian-HUB</strong><small>Gépterem</small></div></div><a class="cp-back" href="/">← Vissza a modulokhoz</a></header>
 <nav class="fw-tabs" aria-label="Szabászati nézetek"><a href="/apps/szabasterv">Szabászmester</a><a href="/apps/szabasterv/szabasz">Szabász</a><a href="/apps/szabasterv/foliazo" aria-current="page">Fóliázó</a><a href="/apps/szabasterv/elpakolas">Elpakolás</a></nav>
 <section id="wrappingOverview">
 <p id="wrappingEmpty" class="fw-status" hidden>Nincs fóliázásra váró raklap.</p><div id="wrappingCards" class="fw-grid"></div></section>
 <dialog id="wrappingDetail" class="cp-pallet-dialog" aria-label="Fóliázás"><button id="wrappingClose" class="cp-dialog-close" type="button" aria-label="Bezárás">×</button><time id="wrappingCutTime" class="cp-process-time"></time><article class="cp-card fw-checklist"><div id="wrappingLines"></div><p id="wrappingDetailStatus" class="fw-detail-status" role="status" aria-live="polite"></p></article></dialog>
 <p id="wrappingStatus" class="fw-status" role="status" aria-live="polite"></p>
</main><script>{{WRAPPING_LOGIC}}</script></body></html>'''
