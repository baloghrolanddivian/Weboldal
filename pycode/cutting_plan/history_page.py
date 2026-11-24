"""Read-only recent activity for cutting, wrapping and putaway."""

from pathlib import Path

from .history_store import STAGES
from .history_ui import add_history_tabs
from .page import PAGE
from .ui_style import style_page
from .wrapping_page import BODY

ROUTES = {f"/apps/szabasterv/{stage}/tortenet": stage for stage in STAGES}


def render_page(stage):
    title = STAGES[stage]
    shell = BODY.split(' <section id="wrappingOverview">', 1)[0]
    shell = shell.replace(' aria-current="page"', '')
    shell = shell.replace(f'href="/apps/szabasterv/{stage}"', f'href="/apps/szabasterv/{stage}" aria-current="page"')
    logic = Path(__file__).with_name("history.js").read_text(encoding="utf-8")
    content = f'''<section id="history" data-stage="{stage}"><p class="fw-status">Elmúlt 14 nap</p><p id="historyStatus" class="fw-status" role="status" aria-live="polite"></p><div id="historyEvents" class="fw-grid cp-history-events"></div></section><dialog id="historyDetail" class="cp-pallet-dialog" aria-label="Történet részletei"><button id="historyClose" class="cp-dialog-close" type="button" aria-label="Bezárás">×</button><div id="historyTimes"></div><div id="historyLines"></div></dialog></main><script>{logic}</script></body></html>'''
    page = PAGE.split("</head>", 1)[0].replace("Gépterem", f"{title} · Történet") + shell + content
    return style_page(add_history_tabs(page, stage, history=True)).encode("utf-8")
