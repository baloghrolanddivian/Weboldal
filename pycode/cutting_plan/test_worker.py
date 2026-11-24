"""Execution quantities remain separate from plans and tolerate concurrent work."""

import html
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from . import store
from .test_days import BROWSER, grouped_plan, sample_plan
from .worker_page import render_page


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = "2026-11-18"
        store.save_day(self.root, self.day, sample_plan(), 0)

    def save(self, actual=12, done=True, revision=0, plan_revision=1, group="mainRows", row_id="row-1"):
        return store.save_progress(self.root, self.day, "colour-1", group, row_id, actual, done, revision, plan_revision)

    def test_actual_and_corrections_do_not_change_plan(self):
        self.save(actual=8)
        record = store.load_day(self.root, self.day)
        self.assertEqual(record["plans"], sample_plan())
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["progress"][0]["actual"], 8)
        self.assertTrue(record["progress"][0]["done"])
        self.save(actual=10, revision=1)
        self.assertEqual(store.load_day(self.root, self.day)["progress"][0]["actual"], 10)

    def test_parallel_rows_independent_but_same_row_conflicts(self):
        self.save()
        self.save(actual=3, group="offcutRows", row_id="offcut-1")
        self.assertEqual(len(store.load_day(self.root, self.day)["progress"]), 2)
        with self.assertRaises(store.PlanConflict):
            self.save(actual=7)

    def test_master_cannot_change_completed_item_but_can_edit_uncut_items(self):
        self.save()
        plans = sample_plan()
        store.save_day(self.root, self.day, plans, 1)
        self.assertTrue(store.load_day(self.root, self.day)["progress"][0]["matches_plan"])
        plans[0]["mainRows"][0]["pieces"] = "20"
        with self.assertRaisesRegex(ValueError, "levágottnak"):
            store.save_day(self.root, self.day, plans, 2)
        plans = sample_plan()
        plans[0]["offcutRows"][0]["pieces"] = "5"
        store.save_day(self.root, self.day, plans, 2)
        record = store.load_day(self.root, self.day)
        self.assertEqual(record["progress"][0]["actual"], 12)
        self.assertTrue(record["progress"][0]["matches_plan"])
        with self.assertRaises(store.PlanConflict):
            self.save(revision=1, plan_revision=2)
        self.save(actual=20, revision=1, plan_revision=3)
        self.assertTrue(store.load_day(self.root, self.day)["progress"][0]["matches_plan"])

    def test_completed_rows_protected_before_pallet_allocation_even_for_stale_editor(self):
        original = store.load_day(self.root, self.day)
        self.save(actual=0)
        self.save(actual=3, group="offcutRows", row_id="offcut-1")
        for group in ("mainRows", "offcutRows"):
            for field, value in (("width", "999"), ("height", "555"), ("pieces", "21"), ("strip100", True if group == "mainRows" else False)):
                changed = copy.deepcopy(original["plans"])
                changed[0][group][0][field] = value
                with self.subTest(group=group, field=field), self.assertRaises(ValueError):
                    store.save_day(self.root, self.day, changed, original["revision"])
            changed = copy.deepcopy(original["plans"])
            changed[0][group] = []
            with self.subTest(group=group), self.assertRaises(ValueError):
                store.save_day(self.root, self.day, changed, 1)
        changed = copy.deepcopy(original["plans"])
        changed[0]["colour"] = "Másik szín"
        with self.assertRaises(ValueError):
            store.save_day(self.root, self.day, changed, 1)
        with self.assertRaises(ValueError):
            store.save_day(self.root, self.day, [], 1)
        self.assertEqual(store.load_day(self.root, self.day)["plans"], original["plans"])

    def test_unfinished_progress_does_not_lock_master(self):
        self.save(done=False)
        plans = sample_plan()
        plans[0]["mainRows"][0]["pieces"] = "20"
        store.save_day(self.root, self.day, plans, 1)
        self.assertEqual(store.load_day(self.root, self.day)["plans"], plans)

    def test_invalid_and_missing_targets_do_not_write(self):
        for actual in (-1, True, 1.5, "12", 10000000):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                self.save(actual=actual)
        with self.assertRaises(ValueError):
            self.save(row_id="missing")
        self.assertEqual(store.load_day(self.root, self.day)["progress"], [])


SETUP = r'''<script>
window.cuttingConfirm=async()=>true;window.failSave=false;window.conflict=false;
window.sampleRecord=RECORD;
window.fetch=async(url,options)=>{
  if(url.includes('/raklapok')){
    const items=[];
    for(const plan of sampleRecord.plans)for(const group of ['mainRows','offcutRows'])for(const row of plan[group]){
      const p=sampleRecord.progress.find(p=>p.plan_id===plan.id&&p.row_group===group&&p.row_id===row.id);
      if(p&&p.matches_plan&&p.actual>0)items.push({plan_id:plan.id,row_group:group,row_id:row.id,colour:plan.colour,width:row.width,height:row.height,actual:p.actual,allocated:0,available:p.actual});
    }
    return {ok:true,json:async()=>({ok:true,state:{day:sampleRecord.day,items,pallets:[]}})};
  }
  if(options){
    if(failSave)throw new Error('Hálózati hiba');
    if(conflict)return {ok:false,json:async()=>({error:'A terv módosult'})};
    const payload=JSON.parse(options.body);payload.revision++;payload.matches_plan=true;
    sampleRecord.progress=sampleRecord.progress.filter(p=>!(p.row_id===payload.row_id&&p.row_group===payload.row_group));sampleRecord.progress.push(payload);
    return {ok:true,json:async()=>({ok:true,progress:payload})};
  }
  return {ok:true,json:async()=>({ok:true,days:[{day:sampleRecord.day,total_boards:3,colours:[{colour:'Antracit',boards:3}]}],record:JSON.parse(JSON.stringify(sampleRecord))})};
};
</script>'''

CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='workerTestResult';document.body.append(result);
 const check=(value,message)=>{if(!value)throw new Error(message);},tick=()=>new Promise(resolve=>setTimeout(resolve,50));
 const row=()=>document.querySelector('[data-row-id="row-1"]');
 const input=value=>{const field=row().querySelector('input[type="number"]');field.value=value;field.dispatchEvent(new Event('input'));};
 try{
  await tick();check(document.getElementById('workerDetail').hidden,'Detail opened before selecting day');document.querySelector('[data-day]').click();await tick();
  check(!document.getElementById('workerDetail').hidden,'Day did not open');
  check(document.querySelectorAll('.cw-item').length===2,'Main/offcut rows missing');
  check(row().querySelector('.cw-board-count').textContent==='3'&&row().querySelector('.cw-size').textContent==='600 × 400 mm','Main cutting metrics absent');
  check(!document.querySelector('.cw-offcut-panel .cw-boards'),'Offcut incorrectly shows board count');
  check(!row().querySelector('.cw-info,.cw-result,.cw-free'),'Excess row information remains');
  check(row().querySelector('input[type="number"]').value==='12','Planned quantity not prefilled');
  check(document.querySelector('[data-row-id="offcut-1"] input[type="number"]').value==='3','Offcut quantity not prefilled');
  check(row().dataset.cutState==='pending'&&row().dataset.complete!=='true','Prefilled row falsely completed');
  check(!document.querySelector('#workerRows input[type="checkbox"]'),'Old completion checkbox still present');
  check(row().querySelector('[data-action="pallet"]').disabled,'Uncut quantity offered for pallet');
  const cardRect=row().getBoundingClientRect();check(cardRect.right<=innerWidth&&cardRect.left>=0,'Row overflows tablet');
  if(innerWidth>=700)check(cardRect.height<165,'Tablet row is too tall');
  const mainPanel=document.querySelector('.cw-main-panel').getBoundingClientRect(),offcutPanel=document.querySelector('.cw-offcut-panel').getBoundingClientRect();
  check(mainPanel.right<=offcutPanel.left+1&&Math.abs(mainPanel.top-offcutPanel.top)<1,'Normal and offcut sizes are not side by side');
  check(row().closest('.cw-main-panel')&&document.querySelector('[data-row-id="offcut-1"]').closest('.cw-offcut-panel'),'Rows assigned to wrong column');
  row().querySelector('button').click();await tick();check(sampleRecord.progress[0].actual===12&&sampleRecord.progress[0].done,'Completion not saved');
  check(!row().querySelector('[data-action="pallet"]').disabled,'Saved cut not offered for pallet');
  input('8');row().querySelector('button').click();await tick();check(row().dataset.shortfall==='4','Shortfall not tracked');
  check(sampleRecord.plans[0].mainRows[0].pieces==='12','Worker overwrote plan');
  check(row().dataset.complete==='false','Shortfall counted as fulfilled');
  document.getElementById('workerBack').click();await tick();document.querySelector('[data-day]').click();await tick();
  check(row().querySelector('input[type="number"]').value==='8','Actual quantity lost on reopen');
  failSave=true;input('9');row().querySelector('button').click();await tick();check(row().textContent.includes('Hálózati hiba'),'Save failure hidden');
  window.cuttingConfirm=async()=>false;document.getElementById('workerBack').click();check(!document.getElementById('workerDetail').hidden,'Unsaved changes discarded');
  failSave=false;conflict=true;row().querySelector('button').click();await tick();check(row().textContent.includes('A terv módosult'),'Conflict hidden');
  conflict=false;row().querySelector('button').click();await tick();check(sampleRecord.progress[0].actual===9,'Retry did not persist correction');
  window.cuttingConfirm=async()=>true;document.getElementById('workerBack').click();await tick();
  sampleRecord.progress[0].matches_plan=false;document.querySelector('[data-day]').click();await tick();
  check(row().querySelector('[data-action="pallet"]').disabled&&row().textContent.includes('A terv módosult'),'Changed plan did not require review');
  input('0');row().querySelector('button').click();await tick();
  document.getElementById('workerBack').click();await tick();document.querySelector('[data-day]').click();await tick();
  check(row().querySelector('input[type="number"]').value==='0','Saved zero replaced by planned quantity');
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class WorkerBrowserTests(unittest.TestCase):
    def test_quantities_completion_corrections_and_failures(self):
        record = {"day": "2026-11-18", "revision": 1, "plans": sample_plan(), "progress": []}
        self.check_browser(record, CHECKS)

    def test_zero_board_rows_display_under_their_parent(self):
        record = {"day": "2026-11-18", "revision": 1, "plans": grouped_plan(), "progress": []}
        record['plans'][0]['mainRows'][3]['boards'] = ''
        record['plans'][0]['mainRows'][5].pop('boards')
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='workerTestResult';document.body.append(result);
          const tick=()=>new Promise(resolve=>setTimeout(resolve,50));
          const check=(ok,message)=>{if(!ok)throw new Error(message);};
          const row=id=>document.querySelector(`[data-row-id="${id}"]`);
          try{
            await tick();document.querySelector('[data-day]').click();await tick();
            check(!row('row-0').dataset.parentRowId,'Leading zero incorrectly grouped');
            check(row('row-1').dataset.boardParent==='true'&&row('row-2').dataset.parentRowId==='row-1'&&row('row-3').dataset.parentRowId==='row-1','First group lost its children');
            check(row('row-5').dataset.parentRowId==='row-4','Zero not grouped with nearest positive count');
            check(row('row-2').querySelector('.cw-board-count').textContent===''&&row('row-1').querySelector('.cw-board-count').textContent==='3','Group repeats parent board count');
            check(getComputedStyle(row('row-2')).borderLeftWidth==='3px','Child has no visual grouping');
            const parentRect=row('row-1').getBoundingClientRect(),childRect=row('row-2').getBoundingClientRect();
            check(Math.abs(parentRect.left-childRect.left)<1&&Math.abs(parentRect.right-childRect.right)<1&&Math.abs(parentRect.bottom-childRect.top)<1,'Worker group is not a shared box');
            check(row('row-2').querySelector('.cw-details').getBoundingClientRect().left>row('row-1').querySelector('.cw-details').getBoundingClientRect().left+10,'Worker child is not indented');
            check(!row('offcut-1').dataset.parentRowId,'Offcut grouped with main boards');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(record, checks)

    def check_browser(self, record, checks):
        page = render_page().decode("utf-8")
        page = page.replace("</head>", SETUP.replace("RECORD", json.dumps(record)) + "</head>").replace("</body>", checks + "</body>")
        for width in (1360, 768):
            with self.subTest(width=width), tempfile.TemporaryDirectory(prefix="cutting-worker-") as folder:
                path = Path(folder) / "index.html"
                path.write_text(page, encoding="utf-8")
                completed = subprocess.run([BROWSER, "--headless", "--disable-gpu", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking", "--allow-file-access-from-files",
                    f"--user-data-dir={folder}/profile", f"--window-size={width},1000", "--virtual-time-budget=6000",
                    "--dump-dom", path.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                match = re.search(r'<pre id="workerTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                self.assertIsNotNone(match, completed.stderr[-2000:])
                self.assertEqual(html.unescape(match.group(1)), "PASS")


if __name__ == "__main__":
    unittest.main()
