"""Browser checks for the damaged-component queue in both manufacturing views."""

import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from manufacturing.admin.page import render_manufacturing_page as render_admin
from manufacturing.page import render_manufacturing_page
from manufacturing.routes import MANUFACTURING_DATA_ROUTE, MANUFACTURING_PARTIAL_QTY_ROUTE, MANUFACTURING_REPORT_READY_ROUTE, MANUFACTURING_ROUTE, MANUFACTURING_STATE_ROUTE

from .test_page_browser import BROWSER


CHECKS = """<script>
(async () => {
  const result = document.createElement('pre');
  result.id = 'browserTestResult';
  document.body.appendChild(result);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  try {
    const tab = document.querySelector('[data-view-key="assembly-damaged"]');
    check(tab && tab.previousElementSibling.getAttribute('data-view-key') === 'all-productions-red', 'Damage tab is not next to the red-items tab');
    tab.click();
    await tick();
    const content = document.getElementById('mfg-content');
    check(content.querySelectorAll('tbody tr').length === 2, 'Opening queue did not refresh incoming reports');
    check(document.querySelector('[data-view-key="assembly-damaged"] small').textContent.trim() === '2', 'Queue count should count reports, not fractional quantities');
    check(content.textContent.includes('COMPONENT-1') && content.textContent.includes('CON1396379')
      && content.textContent.includes('0.055 db') && content.textContent.includes('14545'), 'Component, parent or production details missing');
    check(!content.querySelector('img'), 'Reported description was interpreted as HTML');
    check(document.getElementById('mfg-subsection-tabs').style.display === 'none', 'Queue exposes normal row-state filters');
    check(!content.querySelector('[data-mfg-row]') && document.getElementById('mfg-report-ready').style.display === 'none', 'Replacement queue can accidentally report the parent ready');
    const doneButton = content.querySelector('[data-assembly-damage-complete]');
    check(doneButton.textContent.trim() === '✓' && doneButton.getAttribute('aria-label').includes('COMPONENT-1'), 'Row completion is not an accessible tick');
    doneButton.click();
    await tick();
    check(completionRequests.length === 0 && content.querySelectorAll('tbody tr').length === 2, 'Cancelling confirmation completed a row');
    check(lastConfirmation.includes('COMPONENT-1') && lastConfirmation.includes('CON1396379')
      && lastConfirmation.includes('14545') && lastConfirmation.includes('0.055'), 'Confirmation does not identify the selected row');
    window.confirmDone = true;
    window.failComplete = true;
    content.querySelector('[data-assembly-damage-complete]').click();
    await tick();
    check(content.querySelectorAll('tbody tr').length === 2 && !content.querySelector('[data-assembly-damage-complete]').disabled, 'Failed completion lost the report or retry button');
    window.failComplete = false;
    content.querySelector('[data-assembly-damage-complete]').click();
    await tick();
    check(lastCompleted === 'report-1' && content.querySelectorAll('tbody tr').length === 1, 'Preparation did not remove the correct report');
    content.querySelector('[data-assembly-damage-complete]').click();
    await tick();
    check(!content.querySelector('[data-assembly-damage-complete]') && content.textContent.includes('Nincs összekészítésre váró'), 'Completed queue has no empty state');
    document.querySelector('[data-view-key="korpusz-osszekeszito"]').click();
    check(!content.querySelector('[data-assembly-damage-refresh]'), 'Leaving the queue retained its controls');
    result.textContent = 'PASS';
  } catch (error) { result.textContent = 'FAIL: ' + error.stack; }
})();
</script>"""


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class DamageQueueBrowserTests(unittest.TestCase):
    def test_default_and_admin_replacement_queues(self) -> None:
        first = {"row_id": "report-1", "damage_id": "report-1", "name": "COMPONENT-1", "part_number": "COMPONENT-1",
                 "detail": "<img src=x onerror=alert(1)>", "quantity": "0.055", "code": "CON1396379", "production_number": "14545",
                 "reported_at": "2026-11-13T10:00:00Z", "reported_by": "Assembly"}
        second = {**first, "row_id": "report-2", "damage_id": "report-2", "name": "COMPONENT-2", "part_number": "COMPONENT-2"}
        view = {"key": "assembly-damaged", "label": "Sérült alkatrészek", "count": 1,
                "excludeFromCompletion": True, "sections": [{"key": "assembly-damaged::14545", "label": "Gyártás 14545 · Összekészítő", "rows": [first]}]}
        incoming = {**view, "count": 2, "sections": [{**view["sections"][0], "rows": [first, second]}]}
        document = {"key": "korpusz_osszekeszites", "label": "Korpusz összekészítés", "sections": [], "row_count": 0,
                    "specialViews": [{"key": "korpusz-osszekeszito", "label": "Összekészítő", "sections": [], "count": 0},
                                     {"key": "all-productions-red", "label": "Összes gyártás összes piros eleme", "sections": [], "count": 0}, view]}
        setup = """<script>
window.incoming = __VIEW__;
window.completionRequests = [];
window.confirmDone = false;
window.confirm = message => { window.lastConfirmation = message; return window.confirmDone; };
window.fetch = async (url, options) => {
  if (options?.method === 'POST') {
    window.completionRequests.push(JSON.parse(options.body));
    if (window.failComplete) return { ok:false, json:async () => ({ ok:false, error:'Completion failed' }) };
    window.lastCompleted = JSON.parse(options.body).report_id;
    incoming.sections[0].rows = incoming.sections[0].rows.filter(row => row.damage_id !== lastCompleted);
    incoming.count = incoming.sections[0].rows.length;
    if (!incoming.count) incoming.sections = [];
  }
  return { ok:true, json:async () => ({ ok:true, view:structuredClone(incoming) }) };
};
</script>""".replace("__VIEW__", json.dumps(incoming).replace("</", "<\\/"))
        for renderer in (render_manufacturing_page, render_admin):
            page = renderer(route=MANUFACTURING_ROUTE, data_route=MANUFACTURING_DATA_ROUTE, state_route=MANUFACTURING_STATE_ROUTE,
                            partial_qty_route=MANUFACTURING_PARTIAL_QTY_ROUTE, report_ready_route=MANUFACTURING_REPORT_READY_ROUTE,
                            selected_number="14545", operations=[], selected_operation="korpusz_osszekeszites", recent_productions=[],
                            production_client_cache=[], bundle={"documents": [document]}, selection_state={}, partial_quantity_state={}).decode("utf-8")
            stylesheet = (Path(__file__).resolve().parents[2] / "styles.css").as_uri()
            page = page.replace('href="/styles.css"', f'href="{stylesheet}"')
            page = re.sub(r'<script src="[^"]+"></script>', '', page)
            page = page.replace("</head>", setup + "</head>").replace("</body>", CHECKS + "</body>")
            for width, height in ((1280, 800), (1024, 600)):
                with self.subTest(renderer=renderer.__module__, viewport=(width, height)), tempfile.TemporaryDirectory(prefix="assembly-queue-browser-") as folder:
                    path = Path(folder) / "index.html"
                    path.write_text(page, encoding="utf-8")
                    completed = subprocess.run(
                        [BROWSER, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                         "--allow-file-access-from-files", f"--user-data-dir={folder}/profile", f"--window-size={width},{height}",
                         "--virtual-time-budget=5000", "--dump-dom", path.as_uri()],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
                    )
                    match = re.search(r'<pre id="browserTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                    self.assertIsNotNone(match, completed.stderr[-2000:])
                    self.assertEqual(html.unescape(match.group(1)), "PASS")


if __name__ == "__main__":
    unittest.main()
