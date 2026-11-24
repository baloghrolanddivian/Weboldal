"""Immutable operation history, migration and the rolling fourteen-day window."""

from datetime import datetime, timedelta, timezone
from contextlib import closing
import html
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import history_store as history, pallet_store as pallets, store
from .history_page import render_page
from .test_days import BROWSER
from .test_pallets import DAY, allocation, seed
from .test_putaway import completed_pallet


class HistoryTests(unittest.TestCase):
    def test_process_timestamps_are_preserved_for_each_putaway_event(self):
        now = datetime.now(timezone.utc)
        cut, edged, first, last = [now-timedelta(minutes=n) for n in (40, 30, 20, 10)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            items = [allocation(6), allocation(2, 'offcutRows', 'offcut-1')]
            keys = [pallets.wrapping_key(item) for item in items]
            with patch.object(pallets, 'datetime') as clock:
                clock.now.return_value = cut
                pallet_id = pallets.save_pallet(root, DAY, None, 'Raklap', 'ready', items, 0)
                clock.now.return_value = edged
                pallets.save_wrapping(root, pallet_id, 0, 1, dict.fromkeys(keys, True), True)
                clock.now.return_value = first
                pallets.save_putaway(root, pallet_id, [keys[0]])
                clock.now.return_value = last
                pallets.save_putaway(root, pallet_id, [keys[1]])
            events = history.list_history(root, 'elpakolas')['events']
            self.assertEqual([e['occurred_at'] for e in events], [last.isoformat(), first.isoformat()])
            for event in events:
                self.assertEqual(event['items'][0]['cut_at'], cut.isoformat())
                self.assertEqual(event['items'][0]['edged_at'], edged.isoformat())
            with store._connect(root) as conn:
                conn.execute('UPDATE pallet_dispatch SET sent_at=? WHERE pallet_id=?', (now.isoformat(), pallet_id))
                conn.execute('UPDATE pallet_wrapping SET completed_at=? WHERE pallet_id=?', (now.isoformat(), pallet_id))
            self.assertEqual(history.list_history(root, 'elpakolas')['events'], events)

    def test_existing_history_without_process_dates_is_enriched(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            pallets.save_putaway(root, pallet_id, [pallets.wrapping_key(allocation(6))])
            with store._connect(root) as conn:
                dates = history.pallet_times(conn, pallet_id)
                event = conn.execute("SELECT event_key,items FROM cutting_history WHERE stage='elpakolas'").fetchone()
                items = json.loads(event['items'])
                for item in items:
                    item.pop('cut_at'); item.pop('edged_at')
                conn.execute('UPDATE cutting_history SET items=? WHERE event_key=?', (json.dumps(items), event['event_key']))
            item = history.list_history(root, 'elpakolas')['events'][0]['items'][0]
            self.assertEqual(item['cut_at'], dates['cut_at'])
            self.assertEqual(item['edged_at'], dates['edged_at'])

    def test_activity_snapshots_partial_progress_and_idempotent_putaway(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            self.assertEqual(len(history.list_history(root, 'szabasz')['events']), 2)
            self.assertTrue(all(event['production_day'] == DAY for event in history.list_history(root, 'szabasz')['events']))
            items = [allocation(6), allocation(2, 'offcutRows', 'offcut-1')]
            pallet_id = pallets.save_pallet(root, DAY, None, 'Raklap', 'ready', items, 0)
            keys = [pallets.wrapping_key(item) for item in items]
            pallets.save_wrapping(root, pallet_id, 0, 1, {keys[0]: True, keys[1]: False}, quantities={keys[0]: 5, keys[1]: 2})
            first = history.list_history(root, 'foliazo')['events']
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]['items'][0]['quantity'], 5)
            self.assertEqual(first[0]['items'][0]['rejected'], 1)
            with self.assertRaises(store.PlanConflict):
                pallets.save_wrapping(root, pallet_id, 0, 1, dict.fromkeys(keys, True))
            self.assertEqual(history.list_history(root, 'foliazo')['events'], first)
            pallets.save_wrapping(root, pallet_id, 1, 1, dict.fromkeys(keys, True))
            pallets.save_wrapping(root, pallet_id, 2, 1, dict.fromkeys(keys, True), True)
            self.assertEqual(len(history.list_history(root, 'foliazo')['events']), 2)
            pallets.save_putaway(root, pallet_id, [keys[0]])
            pallets.save_putaway(root, pallet_id, [keys[0]])
            events = history.list_history(root, 'elpakolas')['events']
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['items'][0]['quantity'], 5)
            pallets.save_putaway(root, pallet_id)
            self.assertEqual(len(history.list_history(root, 'elpakolas')['events']), 2)
            store.save_progress(root, DAY, 'colour-1', 'mainRows', 'row-1', 11, True, 1, 1)
            quantities = [e['items'][0]['quantity'] for e in history.list_history(root, 'szabasz')['events']]
            self.assertIn(12, quantities)
            self.assertIn(11, quantities)
            with store._connect(root) as conn:
                conn.execute("UPDATE days SET plans='[]' WHERE day=?", (DAY,))
            self.assertEqual(history.list_history(root, 'foliazo')['events'][-1], first[0])
            self.assertTrue(all(event['production_day'] == DAY for event in history.list_history(root, 'szabasz')['events']))

    def test_only_requested_stage_and_last_fourteen_days_in_order(self):
        now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder, patch.object(history, 'datetime') as clock:
            clock.now.return_value = now
            root = Path(folder)
            with store._connect(root) as conn:
                for name, age in [('old', timedelta(days=14, microseconds=1)), ('boundary', timedelta(days=14)), ('new', timedelta(minutes=1)), ('future', -timedelta(seconds=1))]:
                    history.record_event(conn, 'foliazo', [name], (now-age).isoformat(), [{'colour': name, 'quantity': 1}])
                history.record_event(conn, 'szabasz', ['other'], now.isoformat(), [{'colour': 'other'}])
            result = history.list_history(root, 'foliazo')
            self.assertEqual([e['items'][0]['colour'] for e in result['events']], ['new', 'boundary'])
            self.assertEqual(result['since'], (now-timedelta(days=14)).isoformat())
            with self.assertRaises(ValueError): history.list_history(root, 'unknown')

    def test_existing_data_is_backfilled_once_with_original_saved_times(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed(root)
            pallet_id = completed_pallet(root)
            key = pallets.wrapping_key(allocation(6))
            pallets.save_putaway(root, pallet_id, [key])
            with closing(sqlite3.connect(root / 'daily-plans.sqlite3')) as conn, conn:
                conn.execute('DROP TABLE cutting_history')
                conn.execute('DROP TABLE cutting_history_meta')
            cut = history.list_history(root, 'szabasz')['events']
            wrapped = history.list_history(root, 'foliazo')['events']
            putaway = history.list_history(root, 'elpakolas')['events']
            self.assertEqual(len(cut), 2)
            self.assertEqual(len(wrapped), 1)
            self.assertEqual(len(putaway), 1)
            with store._connect(root) as conn:
                self.assertEqual(wrapped[0]['occurred_at'], conn.execute('SELECT updated_at FROM pallet_wrapping WHERE pallet_id=?', (pallet_id,)).fetchone()[0])
            self.assertEqual(history.list_history(root, 'elpakolas')['events'], putaway)
            pallets.save_putaway(root, pallet_id)
            self.assertEqual(len(history.list_history(root, 'elpakolas')['events']), 2)


CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='historyTestResult';document.body.append(result);
 const check=(ok,message)=>{if(!ok)throw new Error(message);};
 const until=async test=>{for(let i=0;i<150;i++){if(test())return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timed out');};
 try{
  await until(()=>document.querySelector('.cp-history-event'));
  const stage=document.getElementById('history').dataset.stage;
  check(document.querySelector('.cp-history-tabs [aria-current]').textContent==='Történet','History tab not active');
  check(document.querySelector('.cp-history-tabs a').getAttribute('href')==='/apps/szabasterv/'+stage,'Wrong return tab');
  check(document.getElementById('history').textContent.includes('Elmúlt 14 nap'),'History window missing');
  const cards=Array.from(document.querySelectorAll('.cp-history-event'));
  check(cards.every(c=>c.querySelector('time').dateTime&&c.textContent.includes('Antracit')&&c.textContent.includes('db')),'History details missing');
  check(cards.every(c=>c.textContent.includes('Szabva:')&&(stage==='szabasz'||c.textContent.includes('Élzárva:'))&&(stage!=='elpakolas'||c.textContent.includes('Elpakolva:'))),'Labeled process dates missing');
  if(stage==='szabasz')check(cards.every(c=>c.textContent.includes('Napi gyártás: 2026-11-18')),'Original production day missing from cutting history cards');
  check(cards.every(c=>c.scrollWidth<=c.clientWidth),'History overflows');
  check(getComputedStyle(document.getElementById('historyEvents')).gridTemplateColumns.split(' ').length===3,'History is not a three-column card grid');
  check(cards.every(c=>Math.abs(c.getBoundingClientRect().height-cards[0].getBoundingClientRect().height)<1&&c.querySelectorAll('.fw-item').length===1),'History cards are not uniform single-row previews');
  const expandable=cards.find(c=>c.querySelector('.fw-card-more'))||cards[0];
  const expectedCount=expandable.querySelector('.fw-card-more')?Number(expandable.querySelector('.fw-card-more').textContent.match(/\d+/)[0])+1:1;
  expandable.querySelector('button').click();const popup=document.getElementById('historyDetail');await until(()=>popup.open);
  check(popup.matches(':modal')&&popup.querySelectorAll('.cp-history-row').length===expectedCount,'History modal lost hidden items');
  check(!popup.querySelector('input'),'History permits editing');
  if(stage==='szabasz')check(popup.textContent.includes('Napi gyártás: 2026-11-18'),'Original production day missing from history detail');
  if(stage==='foliazo')check(popup.textContent.includes('Selejt: 1 db'),'Scrap missing from full history');
  document.getElementById('historyClose').click();check(!popup.open,'History modal does not close');
  check(!document.getElementById('history').textContent.includes('TOO_OLD'),'Old events leaked');
  const response=await(await fetch('/apps/szabasterv/tortenet?stage='+stage+'&since=2000-01-01')).json();
  check(response.ok&&response.events.length===cards.length,'Server did not enforce history window');
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, 'A local Chromium browser is required')
class HistoryBrowserTests(unittest.TestCase):
    def test_history_tabs_three_stages_desktop_and_tablet(self):
        import app
        import http.client
        from .worker_page import render_page as render_worker
        from .wrapping_page import render_page as render_wrapping
        from .putaway_page import render_page as render_putaway

        for stage, render in [('szabasz', render_worker), ('foliazo', render_wrapping), ('elpakolas', render_putaway)]:
            self.assertIn(f'href="/apps/szabasterv/{stage}/tortenet"', render().decode('utf8'))

        class Handler(app.InvoiceHandler):
            def current_user(self): return app.AuthUser('history-test', 'History test', True)
            def log_message(self, *args): pass

        with tempfile.TemporaryDirectory(prefix='history-browser-') as folder:
            runtime = Path(folder) / 'runtime'
            root = runtime / 'szabasterv'
            seed(root)
            pallet_id = completed_pallet(root)
            pallets.save_putaway(root, pallet_id, [pallets.wrapping_key(allocation(6))])
            with store._connect(root) as conn:
                for stage in history.STAGES:
                    history.record_event(conn, stage, ['old'], (datetime.now(timezone.utc)-timedelta(days=15)).isoformat(), [{'colour': 'TOO_OLD'}])
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            def page(stage): return render_page(stage).decode('utf8').replace('</body>', CHECKS+'</body>').encode('utf8')
            with patch.object(app, 'RUNTIME_DIR', runtime), patch.object(app, 'render_cutting_history_page', side_effect=page):
                thread.start()
                try:
                    conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    conn.request('GET', '/apps/szabasterv/tortenet?stage=unknown')
                    response = conn.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read(); conn.close()
                    for width in (1360, 768):
                        for stage in history.STAGES:
                            with self.subTest(width=width, stage=stage):
                                completed = subprocess.run([BROWSER, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', f'--user-data-dir={folder}/profile-{width}-{stage}', f'--window-size={width},1000', '--virtual-time-budget=12000', '--dump-dom', f'http://127.0.0.1:{server.server_port}/apps/szabasterv/{stage}/tortenet'], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=40)
                                match = re.search(r'<pre id="historyTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                                self.assertIsNotNone(match, completed.stderr[-2000:])
                                self.assertEqual(html.unescape(match.group(1)), 'PASS')
                finally:
                    server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
