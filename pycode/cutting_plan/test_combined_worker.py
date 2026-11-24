"""Exercise cutting and pallet allocation together through the real API."""

import html
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import store
from .pallet_store import load_pallets
from .test_days import BROWSER, sample_plan
from .worker_page import render_page


CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='combinedResult';document.body.append(result);window.cuttingConfirm=async()=>true;
 const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
 const until=async test=>{for(let i=0;i<220;i++){if(test())return;await new Promise(resolve=>setTimeout(resolve,30));}throw new Error('Timed out');};
 const row=id=>document.querySelector(`[data-row-id="${id}"]`);
 const click=id=>document.getElementById(id).click();
 const cut=async id=>{row(id).querySelector('[data-action="cut"]').click();await until(()=>row(id).dataset.cutState==='saved'&&!row(id).querySelector('input').disabled);};
 const add=async id=>{row(id).querySelector('[data-action="pallet"]').click();await until(()=>document.getElementById('miniPalletStatus').textContent==='Mentve.');check(!document.querySelector('dialog[open]'),'Allocation requires another confirmation');};
 try{
  await until(()=>document.querySelector('[data-day]'));document.querySelector('[data-day]').click();await until(()=>row('row-1'));
  check(!document.getElementById('currentPallet').hidden,'Active pallet window missing');
  check(document.getElementById('miniPalletPrint').disabled,'Empty pallet can be printed');
  check(row('row-1').querySelector('[role="checkbox"]').getAttribute('aria-checked')==='false','Cut checkbox initially checked');
  check(row('row-1').querySelector('[data-action="pallet"]').hidden,'Pallet icon shown before cutting');
  check(Array.from(row('row-1').querySelectorAll('.cw-actions button')).filter(node=>!node.hidden).length===1,'More than one action icon shown before cutting');
  check(row('row-1').querySelector('[data-action="pallet"]').disabled,'Uncut main row can be allocated');
  check(row('offcut-1').querySelector('[data-action="pallet"]').disabled,'Uncut offcut can be allocated');
  check(row('row-1').querySelector('input').value==='12','Quantity not prefilled');
  check(row('row-1').querySelector('.cw-size').textContent==='600 × 400 mm'&&row('row-1').querySelector('.cw-strip-tag').textContent==='100 mm csík','Separate strip label or dimensions missing');
  check(row('offcut-1').querySelector('.cw-size').textContent==='Méret nélkül','Optional offcut dimensions not handled');
  const metrics=Array.from(row('row-1').children).slice(0,3).map(node=>node.getBoundingClientRect());
  check(metrics[0].width>=metrics[1].width&&metrics[2].width>=metrics[1].width,'Cutting metric widths are not proportional');
  check(metrics[0].right<=metrics[1].left&&metrics[1].right<=metrics[2].left,'Cutting metrics overlap');
  await cut('row-1');await until(()=>!row('row-1').querySelector('[data-action="pallet"]').disabled);
  check(row('row-1').querySelector('[role="checkbox"]').getAttribute('aria-checked')==='true','Saved cut not checked');
  check(!row('row-1').querySelector('[data-action="pallet"]').hidden&&row('row-1').dataset.complete==='false','Cut alone completed the row');
  const palletRect=row('row-1').querySelector('[data-action="pallet"]').getBoundingClientRect();
  check(palletRect.left>=metrics[2].right,'Pallet icon is not inline after quantity');
  check(row('row-1').querySelector('[data-action="cut"]').hidden&&Array.from(row('row-1').querySelectorAll('.cw-actions button')).filter(node=>!node.hidden).length===1,'Cut icon did not change to a single pallet icon');
  await add('row-1');check(document.getElementById('miniPalletTotal').textContent.includes('12 db'),'Full quantity not saved immediately');
  const originalOpen=window.open;let printUrl='';window.open=url=>{printUrl=url;};click('miniPalletPrint');window.open=originalOpen;
  check(printUrl.includes('/raklap-nyomtatas?')&&new URL(printUrl,location.href).searchParams.get('day')==='2026-11-18','Pallet print preview did not open for selected day');
  const printResponse=await fetch(printUrl),printHtml=await printResponse.text();
  check(printResponse.ok&&printHtml.includes('600 × 400 mm · +100')&&printHtml.includes('12 db'),'Print preview differs from saved pallet');
  check(document.querySelector('.cw-pallet-line').textContent.includes('600 × 400 mm')&&document.querySelector('.cw-pallet-line .cw-strip-tag').textContent==='100 mm csík','Strip label missing from pallet');
  check(row('row-1').dataset.complete==='true'&&getComputedStyle(row('row-1')).backgroundColor==='rgb(13, 139, 85)','Allocated row not fully green');
  check(row('row-1').querySelector('input').readOnly,'Allocated piece count is editable');
  check(row('row-1').querySelector('input').hidden&&!row('row-1').querySelector('.cw-piece-count').hidden&&row('row-1').querySelector('.cw-piece-count').textContent==='12','Allocated quantity is not plain text');
  check(row('row-1').querySelector('[data-action="pallet"]').disabled,'Fully allocated row still available');
  check(row('row-1').querySelector('[data-action="pallet"]').getAttribute('aria-label').includes('Raklapra rakva'),'Allocated row not clearly marked');
  await cut('offcut-1');await add('offcut-1');
  check(document.getElementById('miniPalletTotal').textContent.includes('15 db')&&document.querySelectorAll('.cw-pallet-line').length===2,'Mixed pallet contents incorrect');
  window.cuttingConfirm=async()=>{throw new Error('Pallet removal must not require confirmation');};
  document.querySelector('.cw-pallet-line button').click();await until(()=>document.getElementById('miniPalletTotal').textContent.includes('3 db'));
  check(!row('row-1').querySelector('[data-action="pallet"]').disabled,'Removed quantity not released');
  check(row('row-1').dataset.complete==='false','Removed row stayed green');
  check(!row('row-1').querySelector('input').readOnly,'Removed quantity stayed locked');
  check(!row('row-1').querySelector('input').hidden&&row('row-1').querySelector('.cw-piece-count').hidden,'Removed quantity did not return to an editable field');
  click('miniPalletReady');await until(()=>document.getElementById('miniPalletStatus').textContent.startsWith('Raklap lezárva.'));
  check(document.querySelectorAll('#sentPallets details').length===1&&document.getElementById('sentPallets').textContent.includes('3 db'),'Sent pallet history missing');
  check(!Array.from(document.querySelectorAll('nav a')).some(a=>a.textContent==='Raklaptervező'),'Old pallet tab still shown');
  check(document.querySelector('nav a[href="/apps/szabasterv/foliazo"]'),'Wrapping tab missing');
  await add('row-1');
  check(!document.querySelector('#currentPallet select,#miniPalletId,#miniPalletRefresh,#miniNewPallet'),'Old pallet controls still visible');
  check(document.getElementById('miniPalletHeader').textContent==='Raklapkészítő'&&document.getElementById('miniPalletReady').textContent==='Lezárás','Pallet creator labels incorrect');
  let quantity=document.querySelector('.cw-pallet-line input');
  quantity.value='8';quantity.dispatchEvent(new Event('input'));
  check(document.getElementById('miniPalletReady').disabled,'Unsaved quantity allows closure');
  check(document.getElementById('miniPalletPrint').disabled,'Unsaved pallet quantity can be printed');
  quantity.dispatchEvent(new Event('change'));await until(()=>document.getElementById('miniPalletTotal').textContent.includes('8 db'));
  check(row('row-1').dataset.complete==='false'&&!row('row-1').querySelector('[data-action="pallet"]').hidden,'Partial pallet did not release remainder');
  quantity=document.querySelector('.cw-pallet-line input');quantity.value='13';quantity.dispatchEvent(new Event('input'));quantity.dispatchEvent(new Event('change'));
  check(document.getElementById('miniPalletStatus').dataset.error==='true'&&document.getElementById('miniPalletReady').disabled,'Invalid quantity accepted');
  quantity.value='12';quantity.dispatchEvent(new Event('input'));quantity.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  await until(()=>document.getElementById('miniPalletTotal').textContent.includes('12 db')&&!document.getElementById('miniPalletReady').disabled);
  const actual=row('row-1').querySelector('input');
  check(actual.readOnly,'Editing pallet quantity unlocked the cut quantity');
  document.querySelector('.cw-pallet-line button').click();await until(()=>document.getElementById('miniPalletTotal').textContent.includes('0 db'));
  check(!actual.readOnly,'Removing from selected pallet did not unlock quantity');
  actual.value='11';actual.dispatchEvent(new Event('input'));await cut('row-1');
  check(actual.value==='11'&&!actual.readOnly,'Released quantity cannot be edited');
  actual.value='12';actual.dispatchEvent(new Event('input'));await cut('row-1');
  await until(()=>!row('row-1').querySelector('[data-action="pallet"]').disabled);await add('row-1');
  check(row('row-1').querySelector('[data-action="pallet"]').title.includes('Raklapra tehető: 0 db'),'Released pieces not recalculated');
  click('collapsePallet');check(document.getElementById('currentPalletBody').hidden,'Collapse failed');click('collapsePallet');
  const panel=document.getElementById('currentPallet'),handle=document.getElementById('palletDragHandle');
  const rect=panel.getBoundingClientRect(),capture=handle.setPointerCapture;handle.setPointerCapture=()=>{};
  handle.dispatchEvent(new PointerEvent('pointerdown',{pointerId:7,button:0,clientX:rect.left+15,clientY:rect.top+15,bubbles:true}));
  handle.dispatchEvent(new PointerEvent('pointermove',{pointerId:7,clientX:35,clientY:35,bubbles:true}));
  handle.dispatchEvent(new PointerEvent('pointerup',{pointerId:7,bubbles:true}));handle.setPointerCapture=capture;
  check(Math.abs(panel.getBoundingClientRect().left-20)<2,'Panel cannot be dragged');
  handle.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));check(panel.getBoundingClientRect().left>=39,'Keyboard panel move failed');
  window.scrollTo(0,500);const visible=panel.getBoundingClientRect();check(visible.top>=0&&visible.bottom<=innerHeight&&getComputedStyle(panel).position==='fixed','Panel not always visible');
  click('workerBack');await until(()=>!document.getElementById('workerOverview').hidden);check(panel.hidden,'Pallet panel leaked to day selection');
  document.querySelector('[data-day]').click();await until(()=>!document.getElementById('workerDetail').hidden);
  check(document.getElementById('miniPalletTotal').textContent.includes('12 db'),'Active pallet not restored');
  check(row('row-1').querySelector('input').readOnly&&row('offcut-1').querySelector('input').readOnly,'Reopening day unlocked allocated quantities');
  check(panel.getBoundingClientRect().left>=39,'Panel position not retained');
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class CombinedWorkerTests(unittest.TestCase):
    def test_cut_then_allocate_all_remove_mix_and_finish_in_floating_pallet(self):
        plans = sample_plan()
        plans[0]["mainRows"][0]["strip100"] = True
        plans[0]["offcutRows"][0].pop("strip100")
        self.check_browser(plans, CHECKS, [3, 12], 1)

    def test_limited_sizes_fill_multiple_pallets_and_limit_manual_edits(self):
        plans = sample_plan()
        row = plans[0]["mainRows"][0]
        plans[0]["mainRows"] = [{**row, "width": "724", "height": "505", "pieces": "295"},
                                {**row, "id": "row-2", "width": "720", "height": "330", "pieces": "439"}]
        plans[0]["offcutRows"] = []
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='combinedResult';document.body.append(result);
          const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
          const until=async test=>{for(let i=0;i<220;i++){if(test())return;await new Promise(resolve=>setTimeout(resolve,30));}throw new Error('Timed out');};
          const row=id=>document.querySelector(`[data-row-id="${id}"]`);
          const input=()=>document.querySelector('.cw-pallet-line input');
          try{
            await until(()=>document.querySelector('[data-day]'));document.querySelector('[data-day]').click();await until(()=>row('row-1'));
            check(row('row-1').querySelector('.cp-edge-tag').textContent==='1H','Worker does not show the matched long-edge code');
            for(const [id,limit] of [['row-1',144],['row-2',216]]){
              const line=row(id),add=line.querySelector('[data-action="pallet"]');
              line.querySelector('[data-action="cut"]').click();await until(()=>!add.disabled);
              for(const [index,chunk] of [limit,limit,7].entries()){
                add.click();await until(()=>input()?.value===String(chunk)&&!input().disabled);
                check(Number(input().value)<=limit&&Number(input().max)<=limit,'Pallet exceeded size capacity');
                check(!line.querySelector('.cw-batch-state'),'Unnecessary batch summary is shown');
                if(index===0){
                  check(line.dataset.complete==='false'&&document.getElementById('miniPalletStatus').textContent.includes(String(limit+7)),'Remainder was not preserved');
                  add.click();check(Number(input().value)===limit,'Adding twice exceeded capacity');
                  input().value=String(limit+1);input().dispatchEvent(new Event('input'));input().dispatchEvent(new Event('change'));
                  check(document.getElementById('miniPalletStatus').dataset.error==='true'&&document.getElementById('miniPalletReady').disabled,'Manual edit exceeded capacity');
                  input().value=String(limit);input().dispatchEvent(new Event('input'));input().dispatchEvent(new Event('change'));
                  input().value=String(limit-1);input().dispatchEvent(new Event('input'));input().dispatchEvent(new Event('change'));
                  await until(()=>document.getElementById('miniPalletTotal').textContent.includes(`${limit-1} db`)&&!input().disabled);
                  check(line.dataset.complete==='false','Reduced pallet quantity marked the row complete');
                  input().value=String(limit);input().dispatchEvent(new Event('input'));input().dispatchEvent(new Event('change'));
                  await until(()=>document.getElementById('miniPalletTotal').textContent.includes(`${limit} db`)&&!input().disabled);
                }
                if(index<2||id==='row-1'){
                  document.getElementById('miniPalletReady').click();await until(()=>document.getElementById('miniPalletStatus').textContent.startsWith('Raklap lezárva.'));
                  check(!input(),'Closing did not start a new pallet');
                  check(!line.querySelector('.cw-batch-state'),'Closing restored unnecessary summary');
                }
              }
              check(line.dataset.complete==='true'&&add.hidden,'Split quantity not fully allocated');
            }
            document.getElementById('workerBack').click();await until(()=>!document.getElementById('workerOverview').hidden);
            document.querySelector('[data-day]').click();await until(()=>!document.getElementById('workerDetail').hidden);
            check(row('row-1').dataset.complete==='true'&&row('row-2').dataset.complete==='true'&&!document.querySelector('.cw-batch-state'),'Reopening lost allocation state or restored summaries');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(plans, checks, [7, 7, 144, 144, 216, 216], 5)

    def test_failed_automatic_print_can_retry_without_closing_another_pallet(self):
        plans = sample_plan()
        plans[0]['offcutRows'] = []
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='combinedResult';document.body.append(result);
          const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
          const until=async test=>{for(let i=0;i<220;i++){if(test())return;await new Promise(resolve=>setTimeout(resolve,30));}throw new Error('Timed out');};
          try{
            await until(()=>document.querySelector('[data-day]'));document.querySelector('[data-day]').click();await until(()=>document.querySelector('[data-action="cut"]'));
            document.querySelector('[data-action="cut"]').click();await until(()=>!document.querySelector('[data-action="pallet"]').disabled);
            document.querySelector('[data-action="pallet"]').click();await until(()=>document.getElementById('miniPalletStatus').textContent==='Mentve.');
            document.getElementById('miniPalletReady').click();await until(()=>document.getElementById('miniPalletStatus').dataset.error==='true');
            check(!document.getElementById('miniPalletPrintRetry').hidden&&!document.querySelector('.cw-pallet-line'),'Failed print lost closed pallet or does not allow retry');
            check(document.querySelectorAll('#sentPallets details').length===1,'Pallet did not close before print failure');
            document.getElementById('miniPalletPrintRetry').click();await until(()=>document.getElementById('miniPalletStatus').textContent==='Címke a nyomtatóra küldve.');
            check(document.getElementById('miniPalletPrintRetry').hidden&&document.querySelectorAll('#sentPallets details').length===1,'Retry duplicated a closed pallet');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(plans, checks, [12], 1, print_fail_first=True)

    def check_browser(self, plans, checks, totals, ready_count, print_fail_first=False):
        import app

        class Handler(app.InvoiceHandler):
            def current_user(self):
                return app.AuthUser("combined-test", "Combined test", True)

            def log_message(self, *args):
                pass

        for width in (1360, 768, 560):
            with self.subTest(width=width), tempfile.TemporaryDirectory(prefix="combined-worker-") as folder:
                runtime = Path(folder) / "runtime"
                store.save_day(runtime / "szabasterv", "2026-11-18", plans, 0)
                body = render_page().decode("utf-8").replace("</body>", checks + "</body>").encode("utf-8")
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                success = {"ok": True, "status": "sent", "job_id": 1}
                failures = [{"ok": False, "status": "error", "error": "Printer offline"}, success] if print_fail_first else None
                with patch.object(app, "RUNTIME_DIR", runtime), patch.object(app, "render_cutting_worker_page", return_value=body), patch.object(app, "print_cutting_pallet", side_effect=failures, return_value=success):
                    thread.start()
                    try:
                        completed = subprocess.run([BROWSER, "--headless", "--disable-gpu", "--no-first-run",
                            "--no-default-browser-check", "--disable-background-networking", f"--user-data-dir={folder}/profile",
                            f"--window-size={width},1000", "--virtual-time-budget=20000", "--dump-dom",
                            f"http://127.0.0.1:{server.server_port}/apps/szabasterv/szabasz"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=50)
                        match = re.search(r'<pre id="combinedResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                        self.assertIsNotNone(match, completed.stderr[-2000:])
                        self.assertEqual(html.unescape(match.group(1)), "PASS")
                        state = load_pallets(runtime / "szabasterv", "2026-11-18")
                        self.assertEqual(sorted(p["total_pieces"] for p in state["pallets"]), totals)
                        self.assertEqual(sum(p["status"] == "ready" for p in state["pallets"]), ready_count)
                    finally:
                        server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
