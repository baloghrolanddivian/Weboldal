"""Browser coverage for production note loading, edits, and save failures."""

from __future__ import annotations

import html
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from .admin_page import render_admin_page
from .test_page_browser import BROWSER


SETUP = """<script>
window.calls = [];
window.confirm = () => false;
window.fixture = { production_id:'14545', revision:'original', items:[
  { row_id:'0', con_id:'CON1', part_number:'ITEM-A', notes:'' },
  { row_id:'1', con_id:'CON1', part_number:'EGK', notes:'Existing note' },
  { row_id:'2', con_id:'CON2', part_number:'EGK-OTHER', notes:'<img src=x onerror=alert(1)>' }
] };
window.fetch = async (url, options) => {
  window.calls.push({ url, options });
  if (url.includes('production_id=999')) return { ok:false, json:async () => ({ ok:false, error:'Production not found' }) };
  if (options?.method === 'POST') {
    if (window.failSave) return { ok:false, json:async () => ({ ok:false, error:'File changed' }) };
    const payload = JSON.parse(options.body);
    window.lastPayload = payload;
    for (const change of payload.changes) window.fixture.items.find(item => item.row_id === change.row_id).notes = change.notes;
    window.fixture.revision = 'updated';
  }
  return { ok:true, json:async () => ({ ok:true, production:structuredClone(window.fixture) }) };
};
</script>"""

CHECKS = """<script>
(async () => {
  const result = document.createElement('pre');
  result.id = 'browserTestResult';
  document.body.appendChild(result);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const submit = () => productionForm.dispatchEvent(new Event('submit', { bubbles:true, cancelable:true }));
  const edit = (index, value) => {
    const input = notesBody.rows[index].querySelector('textarea');
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles:true }));
  };
  const search = value => {
    conSearchInput.value = value;
    conSearchInput.dispatchEvent(new Event('input', { bubbles:true }));
  };
  const visibleRows = () => [...notesBody.rows].filter(row => !row.hidden);
  try {
    check(document.body.getBoundingClientRect().top === 0, 'Admin body has a collapsed top margin');
    check(document.body.getBoundingClientRect().height >= innerHeight, 'Admin background stops before the viewport bottom');
    const expectedAccent = document.body.classList.contains('admin-theme') ? '#ff7138' : '#9dfff1';
    check(getComputedStyle(document.body).getPropertyValue('--accent').trim() === expectedAccent, 'Signed-in user theme was lost');
    check(document.getElementById('notesBoard').hidden && saveButton.disabled, 'Editor should start empty');
    productionInput.value = '14545';
    submit();
    await tick();
    check(notesBody.rows.length === 3, 'Not all production items are shown');
    check(notesBody.rows[0].querySelector('textarea').value === '', 'Missing note is not editable');
    check(notesBody.rows[1].cells[0].textContent === 'CON1' && notesBody.rows[1].cells[1].textContent === 'EGK', 'Columns or duplicate CON identity incorrect');
    check(!notesBody.querySelector('img'), 'Note text was interpreted as HTML');
    check(document.documentElement.scrollWidth <= innerWidth + 1, 'Admin layout overflows the screen');
    edit(0, 'New note');
    edit(1, '');
    check(document.getElementById('changedCount').textContent === '2' && !saveButton.disabled, 'Changed rows are not tracked');
    const callsBeforeFilters = calls.length;
    search(' con1 ');
    check(visibleRows().length === 2, 'CONID search must ignore case and whitespace and retain duplicate CON rows');
    check(document.getElementById('filteredCount').textContent === '2 / 3 elem', 'Filtered row count is incorrect');
    egkOnly.checked = true;
    egkOnly.dispatchEvent(new Event('change', { bubbles:true }));
    check(visibleRows().length === 1 && visibleRows()[0].cells[1].textContent === 'EGK', 'EGK filter did not combine with CONID search');
    search('2');
    check(visibleRows().length === 0 && !document.getElementById('notesNoMatches').hidden, 'Combined filters should show no-match state and exclude EGK prefixes');
    check(changes.size === 2 && !saveButton.disabled && calls.length === callsBeforeFilters, 'Filtering lost edits or sent an unnecessary server request');
    window.failSave = true;
    saveButton.click();
    await tick();
    check(notesStatus.textContent === 'File changed' && notesStatus.dataset.error === 'true', 'Save failure not shown');
    check(changes.size === 2 && notesBody.rows[0].querySelector('textarea').value === 'New note', 'Failed save lost edits');
    window.failSave = false;
    // Changing the production selector must not change the production being saved.
    productionInput.value = '999';
    saveButton.click();
    await tick();
    check(lastPayload.production_id === '14545' && lastPayload.revision === 'original', 'Save targeted the wrong file or revision');
    check(lastPayload.changes.length === 2 && lastPayload.changes[0].row_id === '0' && lastPayload.changes[1].row_id === '1', 'Save did not send exactly the edited records');
    check(notesBody.rows[0].querySelector('textarea').value === 'New note' && notesBody.rows[1].querySelector('textarea').value === '', 'Saved values not rendered');
    check(production.revision === 'updated' && changes.size === 0 && saveButton.disabled, 'Save did not update file revision');
    check(egkOnly.checked && conSearchInput.value === '2' && visibleRows().length === 0, 'Saving unexpectedly cleared active filters');
    clearFiltersButton.click();
    check(visibleRows().length === 3 && document.getElementById('notesNoMatches').hidden && clearFiltersButton.hidden, 'Clearing filters did not restore all rows');
    search('2');
    check(visibleRows().length === 1 && visibleRows()[0].cells[0].textContent === 'CON2', 'Partial numeric CONID search failed');
    clearFiltersButton.click();
    edit(0, 'Temporary edit');
    edit(0, 'New note');
    check(saveButton.disabled && changes.size === 0, 'Reverted edit is still dirty');
    edit(0, 'Keep unsaved');
    const callCount = calls.length;
    submit();
    await tick();
    check(calls.length === callCount && changes.size === 1, 'Opening another production discarded edits without confirmation');
    discardButton.click();
    check(changes.size === 0 && notesBody.rows[0].querySelector('textarea').value === 'New note', 'Discard did not restore saved state');
    submit();
    await tick();
    check(notesStatus.textContent === 'Production not found' && production.production_id === '14545', 'Failed load lost current production');
    renderProduction({ ...production, items:Array.from({ length:40 }, (_, index) => ({ row_id:String(index), con_id:'CON' + index, part_number:'ITEM-' + index, notes:'Test note' })) });
    check(document.body.scrollHeight > innerHeight, 'Long production cannot scroll');
    check(document.documentElement.scrollWidth <= innerWidth + 1, 'Long production overflows the screen horizontally');
    result.textContent = 'PASS';
  } catch (error) { result.textContent = 'FAIL: ' + error.stack; }
})();
</script>"""


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class AdminBrowserTests(unittest.TestCase):
    def test_load_edit_save_discard_and_errors(self) -> None:
        page = render_admin_page("Admin").decode("utf-8")
        stylesheet = (Path(__file__).resolve().parents[2] / "styles.css").as_uri()
        page = page.replace('href="/styles.css"', f'href="{stylesheet}"')
        page = page.replace("</head>", SETUP + "</head>").replace("</body>", CHECKS + "</body>")
        for theme, width, height in (("admin-theme", 1920, 960), ("admin-theme", 1024, 600), ("admin-theme", 640, 800),
                                     ("production-controller-theme", 1920, 960), ("production-controller-theme", 1024, 600), ("production-controller-theme", 640, 800)):
            with self.subTest(theme=theme, viewport=(width, height)), tempfile.TemporaryDirectory(prefix="assembly-admin-browser-") as folder:
                path = Path(folder) / "index.html"
                path.write_text(page.replace('class="assembly-admin"', f'class="assembly-admin {theme}"'), encoding="utf-8")
                completed = subprocess.run(
                    [BROWSER, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                     "--disable-background-networking", "--allow-file-access-from-files",
                     f"--user-data-dir={folder}/profile", f"--window-size={width},{height}",
                     "--virtual-time-budget=5000", "--dump-dom", path.as_uri()],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
                )
                match = re.search(r'<pre id="browserTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                self.assertIsNotNone(match, completed.stderr[-2000:])
                self.assertEqual(html.unescape(match.group(1)), "PASS")


if __name__ == "__main__":
    unittest.main()
