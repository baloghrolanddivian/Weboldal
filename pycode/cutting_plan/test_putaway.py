"""Completed pallets can be put away once, including safe checkbox retries."""

import html
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from . import pallet_store as pallets
from .putaway_page import render_page
from .test_days import BROWSER
from .test_pallets import DAY, allocation, seed


def completed_pallet(root):
    items = [allocation(6), allocation(2, 'offcutRows', 'offcut-1')]
    pallet_id = pallets.save_pallet(root, DAY, None, 'Raklap 1', 'ready', items, 0)
    keys = [pallets.wrapping_key(item) for item in items]
    pallets.save_wrapping(root, pallet_id, 0, 1, dict.fromkeys(keys, True), True, dict(zip(keys, [5, 0])))
    return pallet_id


class PutawayTests(unittest.TestCase):
    def test_partial_putaway_is_saved_and_only_finishes_after_last_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            keys = [pallets.wrapping_key(allocation(6)), pallets.wrapping_key(allocation(2, 'offcutRows', 'offcut-1'))]
            for invalid in ([], 'all', [True], ['unknown'], [keys[0], 'unknown']):
                with self.subTest(items=invalid), self.assertRaises(ValueError):
                    pallets.save_putaway(root, pallet_id, invalid)
            first = pallets.save_putaway(root, pallet_id, [keys[0]])
            self.assertIsNone(first['stored_at'])
            self.assertEqual(first['items'], [keys[0]])
            queue = pallets.list_putaway_pallets(root)['pallets']
            self.assertEqual(queue[0]['id'], pallet_id)
            self.assertEqual(queue[0]['putaway_items'], [keys[0]])
            self.assertEqual(pallets.save_putaway(root, pallet_id, [keys[0]]), first)
            final = pallets.save_putaway(root, pallet_id, [keys[1]])
            self.assertTrue(final['stored_at'])
            self.assertEqual(set(final['items']), set(keys))
            self.assertEqual(pallets.list_putaway_pallets(root)['pallets'], [])

    def test_simultaneous_size_checks_merge_without_losing_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            keys = [pallets.wrapping_key(allocation(6)), pallets.wrapping_key(allocation(2, 'offcutRows', 'offcut-1'))]
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda key: pallets.save_putaway(root, pallet_id, [key]), keys))
            self.assertTrue(any(result['stored_at'] for result in results))
            self.assertEqual(pallets.list_putaway_pallets(root)['pallets'], [])
            self.assertEqual(set(pallets.save_putaway(root, pallet_id)['items']), set(keys))

    def test_whole_pallet_check_after_partial_and_legacy_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            key = pallets.wrapping_key(allocation(6))
            pallets.save_putaway(root, pallet_id, [key])
            saved = pallets.save_putaway(root, pallet_id)
            self.assertTrue(saved['stored_at'])
            with pallets._connect(root) as conn:
                conn.execute('DELETE FROM pallet_putaway_items WHERE pallet_id=?', (pallet_id,))
            self.assertEqual(pallets.list_putaway_pallets(root)['pallets'], [])
            self.assertEqual(pallets.save_putaway(root, pallet_id, [key]), saved)

    def test_completed_queue_quantities_and_persistent_idempotent_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            queue = pallets.list_putaway_pallets(root)['pallets']
            self.assertEqual([p['id'] for p in queue], [pallet_id])
            self.assertEqual(queue[0]['successful_pieces'], 5)
            self.assertEqual(sorted(queue[0]['wrapping_quantities'].values()), [0, 5])
            self.assertEqual(pallets.list_ready_pallets(root)['pallets'], [])
            saved = pallets.save_putaway(root, pallet_id)
            self.assertTrue(saved['stored_at'])
            self.assertEqual(pallets.save_putaway(root, pallet_id), saved)
            self.assertEqual(pallets.list_putaway_pallets(root)['pallets'], [])
            with pallets._connect(root) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM pallet_putaway').fetchone()[0], 1)
                self.assertIsNotNone(conn.execute('SELECT completed_at FROM pallet_wrapping WHERE pallet_id=?', (pallet_id,)).fetchone()[0])

    def test_unfinished_and_unknown_pallets_cannot_be_put_away(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            items = [allocation(4), allocation(2, 'offcutRows', 'offcut-1')]
            pallet_id = pallets.save_pallet(root, DAY, None, 'Raklap', 'ready', items, 0)
            for value in (None, True, '', 'unknown', pallet_id):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    pallets.save_putaway(root, value)
            pallets.save_wrapping(root, pallet_id, 0, 1, {pallets.wrapping_key(items[0]): True, pallets.wrapping_key(items[1]): False})
            self.assertEqual(pallets.list_putaway_pallets(root)['pallets'], [])
            with self.assertRaises(ValueError):
                pallets.save_putaway(root, pallet_id)


CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='putawayTestResult';document.body.append(result);
 const check=(ok,message)=>{if(!ok)throw new Error(message);};
 const until=async test=>{for(let i=0;i<150;i++){if(test())return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timed out');};
 try{
  await until(()=>document.querySelectorAll('.pa-card').length===1);
  const card=document.querySelector('.pa-card'), popup=document.getElementById('putawayDetail'), checkbox=document.getElementById('putawayCheck');
  check(document.querySelector('nav [aria-current]').textContent==='Elpakolás','Wrong active tab');
  check(!card.textContent.includes('Raklap 1')&&card.querySelector('h2').textContent.match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/),'Date title missing');
  check(card.textContent.includes('Szabva:')&&card.textContent.includes('Élzárva:')&&card.querySelector('time').dateTime,'Process timestamps missing from queue');
  const rows=card.querySelectorAll('.fw-item');
  check(rows.length===1&&rows[0].textContent.includes('600 × 400 mm')&&rows[0].textContent.includes('5 db')&&card.querySelector('.fw-card-more').textContent==='+ 1 további tétel','Putaway quantities include scrap');
  check(!card.querySelector('input')&&card.querySelector('button'),'Queue should open a popup');
  card.querySelector('button').click();await until(()=>popup.open);
  check(popup.matches(':modal')&&checkbox.type==='checkbox'&&!checkbox.checked&&popup.querySelectorAll('input').length===3,'Per-size and whole-pallet checkboxes missing');
  check(popup.textContent.includes('Szabva:')&&popup.textContent.includes('Élzárva:'),'Process timestamps missing from popup');
  check(popup.getBoundingClientRect().width<=innerWidth,'Putaway popup overflows');
  document.getElementById('putawayClose').click();check(!popup.open&&document.contains(card),'Closing putaway saved it');
  card.querySelector('button').click();await until(()=>popup.open);
  check(card.scrollWidth<=card.clientWidth,'Card overflows');
  const originalFetch=window.fetch;
  window.fetch=async(url,options)=>{if(options)throw new Error('Teszt hiba');return originalFetch(url,options);};
  const sizeChecks=()=>Array.from(document.querySelectorAll('#putawayLines input'));
  sizeChecks()[0].click();await until(()=>popup.querySelector('.pa-error').textContent);
  check(popup.open&&!sizeChecks()[0].checked&&!sizeChecks()[0].disabled&&document.contains(card),'Failure lost card or blocked retry');
  window.fetch=originalFetch;sizeChecks()[0].click();await until(()=>sizeChecks()[0].checked&&sizeChecks()[0].disabled&&!checkbox.disabled);
  check(popup.open&&document.contains(card)&&!sizeChecks()[1].checked,'Partial putaway closed or saved other size');
  const saved=(await(await fetch('/apps/szabasterv/elpakolasra-var')).json()).pallets;
  check(saved.length===1&&saved[0].putaway_items.length===1,'Partial putaway not persisted');
  check(card.querySelectorAll('[data-stored="true"]').length===1,'Stored size missing from card');
  document.getElementById('putawayClose').click();card.querySelector('button').click();await until(()=>popup.open);
  check(sizeChecks()[0].checked&&sizeChecks()[0].disabled&&!sizeChecks()[1].checked,'Reopening lost size progress');
  if(innerWidth<1000)checkbox.click();else sizeChecks()[1].click();
  await until(()=>!document.contains(card)&&!popup.open);
  check(!document.getElementById('putawayEmpty').hidden,'Empty queue missing');
  check((await(await fetch('/apps/szabasterv/elpakolasra-var')).json()).pallets.length===0,'Checkbox not persisted');
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, 'A local Chromium browser is required')
class PutawayBrowserTests(unittest.TestCase):
    def test_checkbox_saves_and_retries_on_desktop_and_tablet(self):
        import app
        import http.client

        class Handler(app.InvoiceHandler):
            def current_user(self): return app.AuthUser('putaway-test', 'Putaway test', True)
            def log_message(self, *args): pass

        for width in (1360, 768):
            with self.subTest(width=width), tempfile.TemporaryDirectory(prefix='putaway-browser-') as folder:
                runtime = Path(folder) / 'runtime'
                root = runtime / 'szabasterv'
                seed(root)
                pallet_id = completed_pallet(root)
                pending_id = pallets.save_pallet(root, DAY, None, 'Folyamatban', 'ready', [allocation(4)], 0)
                body = render_page().decode('utf8').replace('</body>', CHECKS + '</body>').encode('utf8')
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                with patch.object(app, 'RUNTIME_DIR', runtime), patch.object(app, 'render_cutting_putaway_page', return_value=body):
                    thread.start()
                    try:
                        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                        conn.request('POST', '/apps/szabasterv/elpakolas', json.dumps({'id': pending_id}), {'Content-Type': 'application/json', 'X-Requested-With': 'Divian-HUB'})
                        response = conn.getresponse()
                        self.assertEqual(response.status, 400)
                        response.read(); conn.close()
                        completed = subprocess.run([BROWSER, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', f'--user-data-dir={folder}/profile', f'--window-size={width},1000', '--virtual-time-budget=12000', '--dump-dom', f'http://127.0.0.1:{server.server_port}/apps/szabasterv/elpakolas'], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=40)
                        match = re.search(r'<pre id="putawayTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                        self.assertIsNotNone(match, completed.stderr[-2000:])
                        self.assertEqual(html.unescape(match.group(1)), 'PASS')
                        self.assertTrue(pallets.save_putaway(root, pallet_id)['stored_at'])
                    finally:
                        server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
