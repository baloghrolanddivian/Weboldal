"""Long-press gestures must open history without changing manufacturing state."""

import html
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from cutting_plan.test_days import BROWSER
from .page import render_manufacturing_page
from .admin.page import render_manufacturing_page as render_admin_page


SETUP = r'''<script>
window.historyCalls=0; window.stateCalls=0; window.failHistory=false; window.emptyHistory=false;
window.fetch=async(url, options)=>{
 if(String(url).includes('/alkatresz-elozmeny?')){
  window.historyCalls++;
  if(window.failHistory)throw new Error('Teszt betöltési hiba');
  return {ok:true,json:async()=>({ok:true,history:{cut_at:window.emptyHistory?null:'2026-11-24T07:25:00+00:00',cut_quantity:12,cut_planned_quantity:3,awaiting_edge_quantity:window.noWaiting?0:7,awaiting_putaway_quantity:window.noWaiting?0:5}})};
 }
 if(options?.method==='POST')window.stateCalls++;
 return {ok:true,json:async()=>({ok:true})};
};
window.addEventListener('error',e=>{window.pageError=String(e.error||e.message)});
</script>'''

CHECKS = r'''<script>
(async()=>{
const result=document.createElement('pre');result.id='partHistoryResult';document.body.append(result);
const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const until=async f=>{for(let i=0;i<100;i++){if(f())return;await wait(20);}throw new Error('Timed out: '+(window.pageError||document.getElementById('mfg-content').textContent));};
try{
 await until(()=>document.querySelector('[data-mfg-row],[data-history-row-id]'));
 const row=document.querySelector('[data-mfg-row],[data-history-row-id]'), popup=document.getElementById('manufacturingPartHistory');
 const pointer=(type,x=10,y=10)=>row.dispatchEvent(new PointerEvent(type,{bubbles:true,isPrimary:true,pointerId:1,button:0,clientX:x,clientY:y}));
 pointer('pointerdown');pointer('pointerup');await wait(650);
 check(!popup.open&&!window.historyCalls,'Short press opened history');
 pointer('pointerdown');pointer('pointermove',40,10);await wait(650);pointer('pointerup');
 check(!popup.open,'Scrolling gesture opened history');
 pointer('pointerdown');pointer('pointercancel');await wait(650);
 check(!popup.open,'Cancelled gesture opened history');
 pointer('pointerdown');await until(()=>popup.open&&popup.querySelectorAll('time').length===1);pointer('pointerup');
 row.click();await wait(50);
 check(window.stateCalls===0,'Long press changed row state');
 check(popup.matches(':modal'),'History is not modal');
 check(popup.textContent.includes('08:25'),'Hungarian local timestamp missing');
 const counts=Array.from(popup.querySelectorAll('dd')).slice(1).map(node=>node.textContent);
 check(counts.join('|')==='Igen · 3 db|Igen · 7 db|Igen · 5 db','Current queue quantities missing');
 check(popup.querySelectorAll('[data-awaiting="true"]').length===2,'Waiting stages are not green');
 const waitingBackground=getComputedStyle(popup.querySelector('[data-awaiting="true"]')).backgroundColor;
 check(popup.querySelectorAll('dd')[0].textContent.includes('12 db'),'Cut quantity missing');
 check(popup.getBoundingClientRect().width<=innerWidth,'Popup overflows');
 popup.querySelector('button').click();await until(()=>!popup.open);
 window.emptyHistory=true;window.noWaiting=true;
 row.dispatchEvent(new KeyboardEvent('keydown',{key:'F10',shiftKey:true,bubbles:true}));
 await until(()=>popup.open&&popup.textContent.includes('Nincs rögzített szabási előzmény'));
 check(popup.querySelectorAll('dd').length===4&&popup.textContent.includes('Igen · 3 db'),'Uncut planned work hidden without cut history');
 check(popup.querySelectorAll('[data-awaiting="false"]').length===2&&!popup.querySelector('[data-awaiting="true"]'),'Empty queues are highlighted');
 check(getComputedStyle(popup.querySelector('[data-awaiting="false"]')).backgroundColor!==waitingBackground,'Waiting and empty stages have the same colour');
 popup.querySelector('button').click();window.emptyHistory=false;window.failHistory=true;
 row.dispatchEvent(new KeyboardEvent('keydown',{key:'ContextMenu',bubbles:true}));
 await until(()=>popup.textContent.includes('Teszt betöltési hiba'));
 check(window.stateCalls===0,'History caused state writes');
 popup.querySelector('button').click();window.failHistory=false;
 const expand=document.querySelector('[data-pantolo-expand]');
 if(expand){
  expand.click();
  await until(()=>document.querySelector('.is-pantolo-unit'));
  document.querySelector('.is-pantolo-unit').dispatchEvent(new KeyboardEvent('keydown',{key:'ContextMenu',bubbles:true}));
  await until(()=>popup.open&&popup.querySelectorAll('time').length===1);
  check(window.stateCalls===0,'Child history changed state');
 }
 result.textContent='PASS';
}catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, 'A local Chromium browser is required')
class PartHistoryBrowserTests(unittest.TestCase):
    def test_worker_and_admin_operations(self):
        for renderer in (render_manufacturing_page, render_admin_page):
            for operation in ('korpusz_osszekeszites', 'cnc_furas', 'front_osszekeszites'):
                with self.subTest(renderer=renderer.__module__, operation=operation), tempfile.TemporaryDirectory(prefix='part-history-') as folder:
                    row = {'row_id':'part-1', 'state_key':'part-1', 'name':'Oldal', 'size':'600 x 400 x 18', 'color':'Antracit', 'quantity':12, 'code':'123', 'production_number':'1234'}
                    document = {'key':operation,'label':operation,'row_count':1,'sections':[{'key':'parts','label':'Alkatrészek','rows':[row]}]}
                    if operation == 'cnc_furas':
                        document['specialViews'] = [{'key':'cnc-parts','label':'Alkatrészek','sections':document['sections']}]
                    if operation == 'front_osszekeszites':
                        row['columnLayout'] = 'front-standard'
                        document['sections'][0]['columnLayout'] = 'front-standard'
                    body = renderer(route='/manufacturing',data_route='/data',state_route='/state',partial_qty_route='/partial',report_ready_route='/ready',selected_number='1234',operations=[{'key':operation,'label':operation}],selected_operation=operation,recent_productions=[],production_client_cache=[],bundle={'documents':[document]},selection_state={},partial_quantity_state={}).decode('utf-8')
                    body = body.replace('</head>', SETUP+'</head>').replace('</body>', CHECKS+'</body>')
                    path=Path(folder)/'index.html';path.write_text(body,encoding='utf-8')
                    completed=subprocess.run([BROWSER,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',f'--user-data-dir={folder}/profile','--window-size=768,1000','--virtual-time-budget=10000','--dump-dom',path.as_uri()],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
                    match=re.search(r'<pre id="partHistoryResult">(.*?)</pre>',completed.stdout,re.DOTALL)
                    self.assertIsNotNone(match,completed.stderr[-1500:])
                    self.assertEqual(html.unescape(match.group(1)), 'PASS')
