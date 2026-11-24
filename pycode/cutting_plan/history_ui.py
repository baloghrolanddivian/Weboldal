"""Local work/history tabs shared by the three production workstations."""

from .history_store import STAGES


def add_history_tabs(page, stage, history=False):
    route = f"/apps/szabasterv/{stage}"
    tabs = f'''<nav class="cp-history-tabs" aria-label="{STAGES[stage]} nézet"><a href="{route}"{' aria-current="page"' if not history else ''}>Munka</a><a href="{route}/tortenet"{' aria-current="page"' if history else ''}>Történet</a></nav>'''
    return page.replace("</nav>", "</nav>" + tabs, 1)
