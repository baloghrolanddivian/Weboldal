"""Pending wrapping queue, saved checklists and completion workflow."""

from datetime import datetime, timezone
import html
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import pallet_store, store
from .test_days import BROWSER
from .test_pallets import DAY, allocation, seed
from .test_days import sample_plan
from .wrapping_page import render_page


class DispatchTests(unittest.TestCase):
    def test_pending_queue_includes_multiple_days_and_partial_pallets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            other_day = '2026-11-20'
            store.save_day(root, other_day, sample_plan(), 0)
            store.save_progress(root, other_day, 'colour-1', 'mainRows', 'row-1', 12, True, 0, 1)
            with patch.object(pallet_store, 'datetime') as clock:
                clock.now.return_value = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
                older = pallet_store.save_pallet(root, DAY, None, 'Régi raklap', 'ready', [allocation(4), allocation(2,'offcutRows','offcut-1')], 0)
                clock.now.return_value = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
                newer = pallet_store.save_pallet(root, other_day, None, 'Új raklap', 'ready', [allocation(4)], 0)
            partial = {pallet_store.wrapping_key(allocation(4)): True, pallet_store.wrapping_key(allocation(2,'offcutRows','offcut-1')): False}
            pallet_store.save_wrapping(root, older, 0, 1, partial)
            result = pallet_store.list_ready_pallets(root)['pallets']
            self.assertEqual([p['id'] for p in result], [newer, older])
            self.assertEqual([p['sent_date'] for p in result], ['2026-11-20', '2026-11-18'])
            self.assertEqual(result[1]['wrapping_status'], 'in_progress')
            pallet_store.save_wrapping(root, older, 1, 1, dict.fromkeys(partial, True), True)
            self.assertEqual([p['id'] for p in pallet_store.list_ready_pallets(root)['pallets']], [newer])

    def test_successful_quantities_defaults_rejects_and_zero_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);seed(root)
            allocations=[allocation(6),allocation(2,'offcutRows','offcut-1')]
            pallet_id=pallet_store.save_pallet(root,DAY,None,'Raklap','ready',allocations,0)
            keys=[pallet_store.wrapping_key(a) for a in allocations]
            self.assertEqual(pallet_store.list_ready_pallets(root)['pallets'][0]['wrapping_quantities'],dict(zip(keys,[6,2])))
            items=dict.fromkeys(keys,True)
            for value in (-1,7,1.5,True,'5'):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    pallet_store.save_wrapping(root,pallet_id,0,1,items,quantities={keys[0]:value,keys[1]:2})
            quantities=dict(zip(keys,[5,0]))
            pallet_store.save_wrapping(root,pallet_id,0,1,dict.fromkeys(keys,False),quantities=quantities)
            with self.assertRaises(ValueError):pallet_store.save_pallet(root,DAY,pallet_id,'Raklap','draft',allocations,1)
            result=pallet_store.save_wrapping(root,pallet_id,1,1,items,quantities=quantities)
            self.assertEqual(result['successful_pieces'],5);self.assertEqual(result['rejected_pieces'],3)
            saved=pallet_store.save_wrapping(root,pallet_id,2,1,items,True)
            self.assertEqual(pallet_store.list_ready_pallets(root)['pallets'],[])
            self.assertEqual(saved['wrapping_quantities'],quantities)
            self.assertEqual(saved['successful_pieces'],5);self.assertEqual(saved['rejected_pieces'],3)
            self.assertTrue(saved['completed_at'])
            self.assertEqual(pallet_store.load_pallets(root,DAY)['items'][0]['allocated'],6)

    def test_checklist_completion_conflicts_and_locking(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);seed(root)
            allocations=[allocation(6),allocation(2,'offcutRows','offcut-1')]
            pallet_id=pallet_store.save_pallet(root,DAY,None,'Raklap','ready',allocations,0)
            items={pallet_store.wrapping_key(item):False for item in allocations}
            with self.assertRaises(ValueError):pallet_store.save_wrapping(root,pallet_id,0,1,items,True)
            first=next(iter(items));items[first]=True
            result=pallet_store.save_wrapping(root,pallet_id,0,1,items)
            self.assertEqual(result['wrapped_count'],1)
            self.assertEqual(result['wrapping_status'],'in_progress')
            with self.assertRaises(pallet_store.PlanConflict):pallet_store.save_wrapping(root,pallet_id,0,1,items)
            with self.assertRaises(ValueError):pallet_store.save_pallet(root,DAY,pallet_id,'Raklap','draft',allocations,1)
            with self.assertRaises(ValueError):pallet_store.save_wrapping(root,pallet_id,1,1,{**items,'unknown':True})
            items={key:True for key in items}
            pallet_store.save_wrapping(root,pallet_id,1,1,items)
            final=pallet_store.save_wrapping(root,pallet_id,2,1,items,True)
            self.assertTrue(final['completed_at']);self.assertEqual(final['wrapping_status'],'completed')
            self.assertEqual(pallet_store.list_ready_pallets(root)['pallets'],[])
            with pallet_store._connect(root) as conn:
                saved_record=conn.execute('SELECT completed_at FROM pallet_wrapping WHERE pallet_id=?',(pallet_id,)).fetchone()
            self.assertEqual(saved_record['completed_at'],final['completed_at'])
            saved=final
            self.assertEqual(saved['wrapping_items'],items)
            self.assertEqual(saved['wrapped_count'],2)
            with self.assertRaises(ValueError):pallet_store.save_wrapping(root,pallet_id,3,1,items)
            self.assertEqual(pallet_store.load_pallets(root,DAY)['items'][0]['allocated'],6)

    def test_hungarian_dispatch_date_instead_of_planning_date(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            seed(root)
            with patch.object(pallet_store, 'datetime') as clock:
                clock.now.return_value = datetime(2026, 11, 18, 23, 30, tzinfo=timezone.utc)
                pallet_id=pallet_store.save_pallet(root,DAY,None,'Kész raklap','ready',[allocation(8)],0)
            pallet_store.save_pallet(root,DAY,None,'Félkész raklap','draft',[allocation(2)],0)
            result=pallet_store.list_ready_pallets(root)
            self.assertEqual(len(result['pallets']),1)
            self.assertEqual(result['pallets'][0]['sent_time'],'00:30')
            self.assertEqual(result['pallets'][0]['day'],DAY)
            self.assertEqual(result['pallets'][0]['allocations'][0]['quantity'],8)
            self.assertEqual(result['pallets'][0]['allocations'][0]['colour'],'Antracit')
            self.assertEqual(result['pallets'][0]['sent_date'],'2026-11-19')
            with self.assertRaises(pallet_store.PlanConflict):
                pallet_store.save_pallet(root,DAY,None,'Dupla raklap','draft',[allocation(3)],0)
            pallet_store.save_pallet(root,DAY,pallet_id,'Kész raklap','draft',[allocation(8)],1)
            self.assertEqual(pallet_store.list_ready_pallets(root)['pallets'],[])


CHECKS=r'''<script>
(async()=>{
const result=document.createElement('pre');result.id='wrappingTestResult';document.body.append(result);
const check=(ok,message)=>{if(!ok)throw new Error(message);};
const until=async test=>{for(let i=0;i<150;i++){if(test())return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timed out');};
try{
 await until(()=>document.querySelectorAll('.fw-card').length===1);
 const card=document.querySelector('.fw-card');check(card.querySelector('h2').textContent==='Szabva: 2026-11-19 00:30','Date title missing');
 check(/^Szabva: 2026-11-19 \d{2}:\d{2}$/.test(card.querySelector('time').textContent),'Cut date and minute missing');
 check(!card.textContent.includes('Raklap 1'),'Generic pallet name shown');
 check(!document.getElementById('wrappingCards').textContent.includes('Felkesz'),'Draft leaked to wrapping');
 check(!card.querySelector('.fw-pallet-icon'),'Unnecessary pallet icon shown');
 const contents=card.querySelectorAll('.fw-item');
 check(contents.length===1&&contents[0].textContent.includes('Antracit')&&contents[0].textContent.includes('600 × 400 mm')&&contents[0].textContent.includes('6 db'),'Pallet contents missing');
 check(card.querySelector('.fw-card-more').textContent==='+ 1 további tétel','Additional item count missing');
 check(!card.querySelector('input'),'Wrapping queue allows editing quantities');
 check(card.getBoundingClientRect().right<=innerWidth,'Tablet card overflows');
 check(getComputedStyle(document.getElementById('wrappingCards')).gridTemplateColumns.split(' ').length===3,'Queue does not fit three columns');
 check(card.scrollWidth<=card.clientWidth,'Pallet contents overflow card');
 for(const text of card.querySelectorAll('h2,time,.fw-item>span'))check(getComputedStyle(text).whiteSpace==='nowrap','Card text wraps');
 check(card.querySelector('h2').title===card.querySelector('h2').textContent,'Full timestamp is unavailable');
 check(!Array.from(document.querySelectorAll('nav a')).some(a=>a.textContent==='Raklaptervező'),'Old tab still shown');
 check(!document.querySelector('#wrappingOverview input[type="date"]')&&!document.getElementById('wrappingToday'),'Date selection still shown');
 check(!document.getElementById('wrappingRefresh'),'Refresh button still shown');
 document.querySelector('.fw-card button').click();await until(()=>document.getElementById('wrappingDetail').open);check(document.getElementById('wrappingDetail').open,'Pallet did not open');
 check(document.getElementById('wrappingDetail').matches(':modal')&&!document.getElementById('wrappingOverview').hidden,'Wrapping did not open over queue');
 check(document.getElementById('wrappingCutTime').textContent==='Szabva: 2026-11-19 00:30','Popup cut time missing');
 const popup=document.getElementById('wrappingDetail');check(popup.getBoundingClientRect().width<=innerWidth,'Popup overflows');
 document.getElementById('wrappingClose').click();await until(()=>!popup.open);
 document.querySelector('.fw-card button').click();await until(()=>popup.open);
 for(const id of ['wrappingHeading','wrappingPalletMeta','wrappingProgress','wrappingPrint','wrappingReload','wrappingBack','wrappingComplete','wrappingRetry'])check(!document.getElementById(id),'Unnecessary detail control: '+id);
 const numbers=()=>Array.from(document.querySelectorAll('#wrappingLines input[type="number"]'));
 const buttons=()=>Array.from(document.querySelectorAll('#wrappingLines [data-action="wrapped"]'));
 check(buttons().length===2,'Wrapping actions missing');
 check(document.querySelectorAll('#wrappingLines .cp-edge-tag').length===2,'Edge indications missing from wrapping');
 check(document.getElementById('wrappingLines').textContent.includes('Antracit · 600 × 400 mm')&&document.getElementById('wrappingLines').textContent.includes('6 db'),'Colour, size or quantity missing');
 check(numbers()[0].value==='0'&&numbers()[1].value==='0','Scrap quantities not defaulted to zero');
 numbers()[0].value='7';numbers()[0].dispatchEvent(new Event('input'));buttons()[0].click();check(document.getElementById('wrappingDetailStatus').dataset.error==='true','Excess scrap accepted');
 numbers()[0].value='1';numbers()[0].dispatchEvent(new Event('input'));
 numbers()[1].value='2';numbers()[1].dispatchEvent(new Event('input'));
 buttons()[0].click();await until(()=>buttons()[0].disabled&&!numbers()[0].disabled);
 check(document.getElementById('wrappingDetail').open,'Partial pallet closed early');
 const state=(await (await fetch('/apps/szabasterv/foliazasra-var')).json()).pallets[0];
 const firstKey=JSON.stringify([state.allocations[0].plan_id,state.allocations[0].row_group,state.allocations[0].row_id]);
 const secondKey=JSON.stringify([state.allocations[1].plan_id,state.allocations[1].row_group,state.allocations[1].row_id]);
 check(state.wrapping_items[firstKey]&&state.wrapping_quantities[firstKey]===5&&!state.completed_at,'Partial wrapping not persisted');
 check(!state.wrapping_items[secondKey]&&state.wrapping_quantities[secondKey]===2,'Saving one row persisted another row');
 check(numbers()[1].value==='2','Saving one row lost other scrap input');
 window.cuttingConfirm=async()=>false;
 document.getElementById('wrappingClose').click();await new Promise(r=>setTimeout(r,30));
 check(popup.open&&numbers()[1].value==='2','Closing discarded unsaved scrap');
 window.cuttingConfirm=async()=>true;
 document.getElementById('wrappingClose').click();await until(()=>!popup.open);
 document.querySelector('.fw-card button').click();await until(()=>popup.open);
 check(buttons()[0].disabled&&numbers()[0].value==='1'&&numbers()[1].value==='0','Reopening lost persisted wrapping');
 numbers()[1].value='2';numbers()[1].dispatchEvent(new Event('input'));
 const originalFetch=window.fetch;let completion=null;
 window.fetch=async(url,options)=>{if(options)throw new Error('Teszt mentési hiba');return originalFetch(url,options);};
 buttons()[1].click();await until(()=>document.getElementById('wrappingDetailStatus').dataset.error==='true');
 check(numbers()[1].value==='2'&&!buttons()[1].disabled&&document.getElementById('wrappingDetail').open,'Failed save lost scrap or prevented retry');
 window.fetch=async(url,options)=>{
   const response=await originalFetch(url,options);
   if(options)completion=await response.clone().json();
   return response;
 };
 buttons()[1].click();await until(()=>!document.getElementById('wrappingDetail').open);
 check(completion.wrapping.completed_at&&completion.wrapping.successful_pieces===5&&completion.wrapping.rejected_pieces===3,'Final button did not complete pallet with saved scrap');
 await until(()=>!document.querySelector('.fw-card')&&!document.getElementById('wrappingEmpty').hidden);
 check((await (await fetch('/apps/szabasterv/foliazasra-var?date=2026-11-19')).json()).pallets.length===0,'Completed pallet remains in queue');
 result.textContent='PASS';
}catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER,'A local Chromium browser is required')
class WrappingBrowserTests(unittest.TestCase):
    def test_minimal_pending_queue_and_checklist_completion(self):
        import app
        import http.client

        class Handler(app.InvoiceHandler):
            def current_user(self):return app.AuthUser('wrapping-test','Wrapping test',True)
            def log_message(self,*args):pass

        for width in (1360,768):
            with self.subTest(width=width),tempfile.TemporaryDirectory(prefix='wrapping-browser-') as folder:
                runtime=Path(folder)/'runtime';seed(runtime/'szabasterv')
                with patch.object(pallet_store, 'datetime') as clock:
                    clock.now.return_value = datetime(2026,11,18,23,30,tzinfo=timezone.utc)
                    pallet_store.save_pallet(runtime/'szabasterv',DAY,None,'Raklap 1','ready',[allocation(6),allocation(2,'offcutRows','offcut-1')],0)
                pallet_store.save_pallet(runtime/'szabasterv',DAY,None,'Felkesz raklap','draft',[allocation(4)],0)
                body=render_page().decode('utf8').replace('</body>',CHECKS+'</body>').encode('utf8')
                server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True)
                with patch.object(app,'RUNTIME_DIR',runtime),patch.object(app,'render_cutting_wrapping_page',return_value=body):
                    thread.start()
                    try:
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port);conn.request('GET','/apps/szabasterv/raklaptervezo');response=conn.getresponse()
                        self.assertEqual(response.status,303);self.assertEqual(response.getheader('Location'),'/apps/szabasterv/foliazo');response.read();conn.close()
                        completed=subprocess.run([BROWSER,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',f'--user-data-dir={folder}/profile',f'--window-size={width},1000','--virtual-time-budget=12000','--dump-dom',f'http://127.0.0.1:{server.server_port}/apps/szabasterv/foliazo'],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=40)
                        match=re.search(r'<pre id="wrappingTestResult">(.*?)</pre>',completed.stdout,re.DOTALL)
                        self.assertIsNotNone(match,completed.stderr[-2000:]);self.assertEqual(html.unescape(match.group(1)),'PASS')
                    finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
