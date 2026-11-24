"""Per-size and whole-pallet putaway for completed wrapping pallets."""

from pathlib import Path

from .page import PAGE
from .ui_style import style_page
from .history_ui import add_history_tabs
from .wrapping_page import BODY as WRAPPING_BODY

ROUTE = "/apps/szabasterv/elpakolas"


def render_page():
    shell = WRAPPING_BODY.split(' <section id="wrappingOverview">', 1)[0]
    shell = shell.replace('href="/apps/szabasterv/foliazo" aria-current="page"', 'href="/apps/szabasterv/foliazo"')
    shell = shell.replace(f'href="{ROUTE}"', f'href="{ROUTE}" aria-current="page"')
    logic = Path(__file__).with_name("putaway.js").read_text(encoding="utf-8")
    content = r'''
<style>
 .pa-card{padding:0!important}.pa-card h2{margin-bottom:12px}.pa-done{display:flex;gap:10px;align-items:center;min-height:44px;margin-top:10px;cursor:pointer;font-weight:800;color:var(--green-dark)}.pa-done input{width:24px;height:24px;accent-color:var(--green);flex-shrink:0}.pa-error{color:var(--red);font-size:.8rem}.pa-error:empty{display:none}
 .fw-item[data-stored="true"]{opacity:.55}.fw-item[data-stored="true"]>strong::after{content:' ✓';color:var(--green-dark)}#putawayLines .fw-item{align-items:center;gap:14px}#putawayLines .pa-done{margin:0;flex-shrink:0}#putawayLines .fw-item>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 @media(max-width:479px){#putawayLines .fw-item{flex-wrap:wrap}#putawayLines .pa-done{flex-basis:100%}}
</style>
<p id="putawayEmpty" class="fw-status" hidden>Nincs elpakolásra váró raklap.</p>
<div id="putawayCards" class="fw-grid"></div>
<dialog id="putawayDetail" class="cp-pallet-dialog" aria-label="Elpakolás"><button id="putawayClose" class="cp-dialog-close" type="button" aria-label="Bezárás">×</button><div id="putawayLines"></div><label class="pa-done"><input id="putawayCheck" type="checkbox" /><span>Teljes raklap elpakolva</span></label><p id="putawayError" class="pa-error" role="status" aria-live="polite"></p></dialog>
<p id="putawayStatus" class="fw-status" role="status" aria-live="polite"></p>
</main><script>''' + logic + "</script></body></html>"
    page = PAGE.split("</head>", 1)[0].replace("Gépterem", "Elpakolás") + shell + content
    return style_page(add_history_tabs(page, "elpakolas")).encode("utf-8")
