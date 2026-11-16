"""Exercise the rendered scanner UI in a locally installed Chromium browser."""

from __future__ import annotations

import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from .page import render_page
from .store import empty_state


def browser_executable() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "msedge"):
        if executable := shutil.which(name):
            return executable
    for folder in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")):
        if folder:
            for relative in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
                executable = Path(folder) / relative
                if executable.is_file():
                    return str(executable)
    return None


BROWSER = browser_executable()

SETUP = """
<script>
window.requests = [];
window.damageRequests = [];
window.randomCalls = 0;
Math.random = () => { window.randomCalls++; return window.sample ?? 0.5; };
window.fetch = async (url, options) => {
  if (url.endsWith('/serult')) {
    window.damageRequests.push(JSON.parse(options.body));
    if (window.failDamage) return { ok:false, json:async () => ({ ok:false, error:'Damage save failed' }) };
    return { ok:true, json:async () => ({ ok:true, report:{ status:'open' } }) };
  }
  const { barcode } = JSON.parse(options.body);
  window.requests.push(barcode);
  if (window.failNext) { window.failNext = false; throw new Error('Lookup failed'); }
  return { ok:true, json:async () => ({ ok:true, state:{
    barcode, production_number:'14545', scanned_at:'2026-11-13T10:00:00Z', lookup_status:'ready',
    item:{ part_number:'TEST-PART', description:'Test cabinet', cabinet:'2A',
      front:'Test front', color:'Fehér', dimensions:'824 × 400 × 600 mm',
      handing:'Jobb', legs:'100 mm', worktop:'Nincs', filler_width:'82', handle_drilling:'64 / 96',
      notes:barcode === 'NORMAL' ? 'Szerelés előtt ellenőrizni' : '' },
    bom:barcode === 'EMPTY' ? [] : [
      { part_number:'PART-1', description:'Zero quantity', quantity:0 },
      { part_number:'PART-2', description:'Fractional quantity', quantity:0.055 }
    ]
  }}) };
};
</script>
"""

CHECKS = """
<script>
(async () => {
  const result = document.createElement('pre');
  result.id = 'browserTestResult';
  document.body.appendChild(result);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const scan = code => {
    for (const key of [...code, 'Enter']) {
      (document.activeElement || document.body).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles:true, cancelable:true }));
    }
  };
  try {
    if (sessionStorage.getItem('browserTestStage') === 'restore') {
      check(bomPanel.open && confirmationRequired, 'Refresh bypassed required confirmation');
      check(currentState.barcode === 'RESTORE', 'Refresh restored the wrong item');
      check(window.randomCalls === 0, 'Refresh rerolled sampling');
      bomConfirm.click();
      check(!bomPanel.open && !resetButton.disabled, 'Confirmation did not unlock after refresh');
      check(!JSON.parse(sessionStorage.getItem(clientStateKey)).bom_confirmation_required, 'Confirmation was not saved');
      renderState(restoreClientState());
      check(!bomPanel.open, 'Confirmed item reopened on restoration');
      result.textContent = 'PASS';
      return;
    }
    check(!bomPanel.open && getComputedStyle(bomPanel).display === 'none', 'BOM must start hidden');
    check(document.getElementById('notesDatum').hidden, 'Empty note must start hidden');
    check(document.getElementById('connectorDatum').hidden, 'Connector must start hidden');
    check(document.getElementById('modelDatum').hidden, 'Missing model must start hidden');
    check(document.querySelector('.info-panel').getBoundingClientRect().width > innerWidth * 0.95, 'Details do not fill the freed space');
    window.sample = 1 / 50;
    scan('NORMAL');
    await tick();
    check(!bomPanel.open && currentState.barcode === 'NORMAL', 'Sampling threshold should be exclusive');
    check(window.randomCalls === 1, 'Normal scan must sample exactly once');
    check(!document.querySelector('[data-item="worktop"]') && !document.querySelector('[data-item="handing"]'), 'Removed fields are still visible');
    check(!document.getElementById('notesDatum').hidden
      && document.querySelector('[data-item="notes"]').textContent === 'Szerelés előtt ellenőrizni', 'Available note is not shown');
    check(document.getElementById('colorDatum').getBoundingClientRect().width > innerWidth * 0.9, 'Cabinet colour does not fill the freed width');
    const identity = document.querySelector('.cabinet-datum');
    check(identity.contains(document.querySelector('[data-item="part_number"]'))
      && identity.contains(document.querySelector('[data-item="description"]')), 'Item identity is not combined');
    check(!document.getElementById('frontDatum') && !document.querySelector('[data-item="front"]'), 'Front box is still visible');
    check(identity.getBoundingClientRect().width > innerWidth * 0.9, 'Combined identity does not fill the available width');
    check(identity.getBoundingClientRect().height > document.querySelector('.primary-info').clientHeight * 0.65, 'Combined identity does not fill the freed height');
    const footer = document.querySelector('.info-footer');
    check(footer.contains(document.getElementById('barcode'))
      && footer.contains(document.querySelector('[data-item="cabinet"]'))
      && footer.contains(document.getElementById('productionId')), 'Scan metadata is not in the footer');
    check(document.getElementById('barcode').textContent === 'NORMAL'
      && document.querySelector('[data-item="cabinet"]').textContent === '2A', 'Footer metadata was not updated');
    check(footer.scrollWidth <= footer.clientWidth + 1, 'Footer metadata overflows');
    const details = document.querySelector('.info-body');
    check(details.scrollWidth <= details.clientWidth + 1, 'Details overflow horizontally');
    check(details.scrollHeight <= details.clientHeight + 1, 'Details require scrolling');
    const secondary = [...document.querySelectorAll('.secondary-info > .datum')].filter(node => !node.hidden);
    check(secondary.every(node => node.offsetTop === secondary[0].offsetTop), 'Secondary details should use the available width');
    const originalItem = currentState;
    const modelItem = { ...originalItem, production_xml:{ ...originalItem.production_xml, features:{ 'Front típus':'Laura' } } };
    renderState(modelItem);
    const modelCard = document.getElementById('modelDatum');
    check(!modelCard.hidden && document.getElementById('frontModel').textContent === 'Laura', 'Front type is not displayed as Modell');
    const colourBox = document.getElementById('colorDatum').getBoundingClientRect();
    const modelBox = modelCard.getBoundingClientRect();
    check(Math.abs(colourBox.top - modelBox.top) < 1 && colourBox.right <= modelBox.left, 'Modell is not beside Korpusz színe');
    for (const [code, orientation, picture] of [
      ['AMO60', 'Függőleges', 'vertical.png'], ['ASZB90_B', 'Függőleges', 'vertical.png'],
      ['ASZH_CUSTOM', 'Függőleges', 'vertical.png'], ['ASM60', 'Függőleges', 'vertical.png'],
      ['AFB60P', 'Vízszintes', 'horizontal.png'], ['AAFE80', 'Vízszintes', 'horizontal.png'],
      ['AS60', 'Vízszintes', 'horizontal.png'], ['AR20', 'Vízszintes', 'horizontal.png'],
      ['AR200', null, null], ['AR20_B', null, null], ['UNLISTED', null, null]
    ]) {
      renderState({ ...modelItem, item:{ ...modelItem.item, part_number:code } });
      const card = document.getElementById('connectorDatum');
      const pictureNode = document.getElementById('connectorImage');
      if (!orientation) {
        check(card.hidden && !pictureNode.getAttribute('src'), 'Unlisted item retained a connector: ' + code);
        check(identity.getBoundingClientRect().width > innerWidth * 0.9, 'Identity did not expand after hiding connector');
        continue;
      }
      check(!card.hidden && document.getElementById('connectorOrientation').textContent === orientation, 'Incorrect connector orientation: ' + code);
      check(pictureNode.getAttribute('src').endsWith('/' + picture), 'Incorrect connector picture: ' + code);
      if (!pictureNode.complete) await new Promise(resolve => {
        pictureNode.addEventListener('load', resolve, { once:true });
        pictureNode.addEventListener('error', resolve, { once:true });
        setTimeout(resolve, 1000);
      });
      check(pictureNode.naturalWidth > 0 && !pictureNode.hidden, 'Connector image did not load: ' + code);
      const box = identity.getBoundingClientRect();
      const connectorBox = card.getBoundingClientRect();
      check(Math.abs(box.top - connectorBox.top) < 1 && box.right <= connectorBox.left, 'Connector is not beside the identity block');
      check(details.scrollWidth <= details.clientWidth + 1 && details.scrollHeight <= details.clientHeight + 1, 'Connector layout requires scrolling');
    }
    renderState({ ...originalItem, production_xml:{ features:{ 'Front típus':'   ' } } });
    check(modelCard.hidden && document.getElementById('frontModel').textContent === '—', 'Empty model retained the previous item model');
    check(document.getElementById('colorDatum').getBoundingClientRect().width > innerWidth * 0.9, 'Colour did not expand after hiding model');
    renderState(originalItem);
    bomToggle.click();
    check(bomPanel.open && !bomPanel.classList.contains('bom-review'), 'Manual drawer failed');
    check(bomPanel.getBoundingClientRect().width < innerWidth * 0.65, 'Manual drawer is too large');
    check(bomToggle.getAttribute('aria-expanded') === 'true', 'Drawer expanded state missing');
    check(bomPartHeader.getBoundingClientRect().width === 96, 'Hidden drawer corrupted the column width');
    check(document.getElementById('bomBody').rows.length === 2, 'BOM rows missing');
    check(document.getElementById('bomBody').rows[1].cells[3].textContent === '0.055', 'Fractional quantity lost');
    check(document.getElementById('bomBody').rows[0].cells[3].textContent === '0', 'Zero quantity lost');
    check(document.querySelectorAll('.bom-damage-button').length === 2, 'BOM rows have no damage actions');
    document.querySelectorAll('.bom-damage-button')[1].click();
    check(damageDialog.open && damageRequests.length === 0 && resetButton.disabled, 'Damage action did not require confirmation');
    damageCancel.click();
    check(!damageDialog.open && damageRequests.length === 0, 'Cancelling damage created a report');
    document.querySelectorAll('.bom-damage-button')[1].click();
    scan('DAMAGE-BLOCKED');
    check(requests.length === 1 && damageDialog.open, 'Scan bypassed damage confirmation');
    window.failDamage = true;
    damageSubmit.click();
    await tick();
    check(damageDialog.open && !damageSubmit.disabled && !document.querySelectorAll('.bom-damage-button')[1].disabled, 'Failed damage save lost retry controls');
    window.failDamage = false;
    damageSubmit.click();
    await tick();
    check(!damageDialog.open && document.querySelectorAll('.bom-damage-button')[1].disabled, 'Confirmed damage was not marked');
    check(damageRequests.length === 2 && damageRequests[0].request_id === damageRequests[1].request_id, 'Damage retry changed its idempotency key');
    check(damageRequests[1].production_number === '14545' && damageRequests[1].bom_index === 1
      && damageRequests[1].bom_row.quantity === 0.055, 'Damage report targeted the wrong BOM item');
    check(JSON.parse(sessionStorage.getItem(clientStateKey)).damaged_bom_indexes.includes(1), 'Damage marker did not survive restoration');
    bomPanel.dispatchEvent(new Event('cancel', { cancelable:true }));
    check(!bomPanel.open && bomToggle.getAttribute('aria-expanded') === 'false', 'Manual drawer cannot be dismissed');
    window.failNext = true;
    scan('ERROR');
    await tick();
    check(!bomPanel.open && currentState.lookup_status === 'error', 'Failed lookup opened review');
    check(window.randomCalls === 1, 'Failed lookup must not sample');
    window.sample = 0.019999;
    scan('REVIEW');
    scan('QUEUED');
    await tick();
    check(bomPanel.open && confirmationRequired && bomPanel.classList.contains('bom-review'), 'Sampled scan did not open large review');
    check(bomPanel.getBoundingClientRect().width > innerWidth * 0.9, 'Review is too small');
    check(currentState.barcode === 'REVIEW' && requests.length === 3, 'Queue replaced the item before confirmation');
    check(document.getElementById('bomItemCode').textContent.includes('REVIEW'), 'Review item identity missing');
    check(resetButton.disabled && bomClose.hidden && !document.getElementById('bomReviewFooter').hidden, 'Review controls are incorrect');
    resetButton.click();
    bomClose.click();
    const cancel = new Event('cancel', { cancelable:true });
    bomPanel.dispatchEvent(cancel);
    bomPanel.dispatchEvent(new MouseEvent('click', { clientX:0, clientY:0, bubbles:true }));
    scan('BLOCKED');
    await tick();
    check(cancel.defaultPrevented && bomPanel.open && requests.length === 3, 'Review can be bypassed');
    window.sample = 0.5;
    bomConfirm.click();
    await tick();
    check(!bomPanel.open && !confirmationRequired && !resetButton.disabled, 'Confirmation did not unlock the screen');
    check(currentState.barcode === 'QUEUED' && requests.length === 4, 'Queued scan did not resume');
    check(document.getElementById('notesDatum').hidden, 'Absent note retained the previous item note');
    check(!requests.includes('BLOCKED'), 'Scan received during review was silently queued');
    bomToggle.click();
    check(!bomPanel.classList.contains('bom-review'), 'Manual drawer retained large review mode');
    bomClose.click();
    window.sample = 0;
    scan('EMPTY');
    await tick();
    check(bomPanel.open && !document.getElementById('emptyBom').hidden, 'Empty BOM review failed');
    bomConfirm.click();
    scan('RESTORE');
    await tick();
    check(JSON.parse(sessionStorage.getItem(clientStateKey)).bom_confirmation_required, 'Required review was not persisted');
    sessionStorage.setItem('browserTestStage', 'restore');
    location.reload();
  } catch (error) {
    result.textContent = 'FAIL: ' + error.stack;
  }
})();
</script>
"""


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class WorkstationBrowserTests(unittest.TestCase):
    def test_drawer_sampling_queue_and_refresh(self) -> None:
        page = render_page(empty_state(), "Browser test", user_id="browser-test").decode("utf-8")
        stylesheet = (Path(__file__).resolve().parents[2] / "styles.css").as_uri()
        page = page.replace('href="/styles.css"', f'href="{stylesheet}"')
        asset_prefix = (Path(__file__).resolve().parents[2] / "assets" / "part-workstation").as_uri() + "/"
        page = page.replace('"/assets/part-workstation/', '"' + asset_prefix)
        page = page.replace("</head>", SETUP + "</head>").replace("</body>", CHECKS + "</body>")
        for width, height in ((1280, 800), (1024, 768), (1024, 600)):
            with self.subTest(viewport=(width, height)), tempfile.TemporaryDirectory(prefix="workstation-browser-") as folder:
                path = Path(folder) / "index.html"
                path.write_text(page, encoding="utf-8")
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
