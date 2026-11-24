"""Daily-plan persistence and browser regression checks."""

import copy
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from . import store
from .page import render_page
from part_workstation.test_page_browser import BROWSER


def sample_plan():
    return [{"id": "colour-1", "colour": "Antracit", "material": "Standard bútorlap", "boardSize": "2800 × 2070 mm",
             "mainRows": [{"id": "row-1", "sizeMode": "manual", "width": "600", "height": "400", "boards": "3", "pieces": "12"}],
             "offcutRows": [{"id": "offcut-1", "sizeMode": "", "width": "", "height": "", "pieces": "3", "strip100": True}]}]


def grouped_plan():
    plans = sample_plan()
    row = plans[0]["mainRows"][0]
    plans[0]["mainRows"] = [{**row, "id": f"row-{index}", "boards": boards}
                            for index, boards in enumerate(("0", "3", "0", "0", "2", "0"))]
    return plans


class DailyPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_create_reopen_edit_and_separate_days(self):
        self.assertEqual(store.load_day(self.root, "2026-11-18")["revision"], 0)
        store.save_day(self.root, "2026-11-18", sample_plan(), 0)
        store.save_day(self.root, "2026-11-19", [], 0)
        record = store.load_day(self.root, "2026-11-18")
        self.assertEqual(record["plans"], sample_plan())
        record["plans"][0]["mainRows"][0]["boards"] = "8"
        store.save_day(self.root, record["day"], record["plans"], record["revision"])
        self.assertEqual(store.load_day(self.root, record["day"])["plans"][0]["mainRows"][0]["boards"], "8")
        self.assertEqual(store.load_day(self.root, "2026-11-19")["plans"], [])
        self.assertEqual([r["day"] for r in store.list_days(self.root)], ["2026-11-19", "2026-11-18"])

    def test_stale_editor_cannot_overwrite(self):
        store.save_day(self.root, "2026-11-18", sample_plan(), 0)
        with self.assertRaises(store.PlanConflict):
            store.save_day(self.root, "2026-11-18", [], 0)
        self.assertEqual(store.load_day(self.root, "2026-11-18")["plans"], sample_plan())

    def test_main_strip_and_optional_offcut_dimensions(self):
        plans = sample_plan()
        plans[0]["mainRows"][0]["strip100"] = True
        plans[0]["offcutRows"][0].pop("strip100")
        store.save_day(self.root, "2026-11-18", plans, 0)
        self.assertEqual(store.load_day(self.root, "2026-11-18")["plans"], plans)
        for invalid in ("true", 1, None):
            plans[0]["mainRows"][0]["strip100"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                store.save_day(self.root, "2026-11-18", plans, 1)

    def test_day_cards_aggregate_boards_by_colour_across_materials(self):
        plans = sample_plan()
        extra = copy.deepcopy(plans[0])
        extra.update(id="colour-2", material="Evogloss lap")
        extra["mainRows"][0]["boards"] = "4"
        extra["offcutRows"][0]["pieces"] = "100"
        plans.append(extra)
        white = copy.deepcopy(extra)
        white.update(id="colour-3", colour="Fehér")
        white["mainRows"][0]["boards"] = "2"
        plans.append(white)
        store.save_day(self.root, "2026-11-18", plans, 0)
        store.save_day(self.root, "2026-11-19", [], 0)
        empty, day = store.list_days(self.root)
        self.assertEqual(empty["total_boards"], 0)
        self.assertEqual(empty["colours"], [])
        self.assertEqual(day["total_boards"], 9)
        self.assertEqual(day["colours"], [{"colour": "Antracit", "boards": 7}, {"colour": "Fehér", "boards": 2}])
        self.assertNotIn("plans", day)

    def test_simultaneous_creation_has_one_winner(self):
        store.list_days(self.root)
        def save(_):
            try:
                store.save_day(self.root, "2026-11-18", sample_plan(), 0)
                return True
            except store.PlanConflict:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(save, range(2))), [False, True])

    def test_invalid_payload_keeps_previous_plan(self):
        store.save_day(self.root, "2026-11-18", sample_plan(), 0)
        for day in ("../other", "2026-02-30", "2026-1-1", None):
            with self.subTest(day=day), self.assertRaises(ValueError):
                store.save_day(self.root, day, [], 0)
        for value in (-1, "2.5", True, {}, "NaN"):
            plan = copy.deepcopy(sample_plan())
            plan[0]["mainRows"][0]["pieces"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                store.save_day(self.root, "2026-11-18", plan, 1)
        self.assertEqual(store.load_day(self.root, "2026-11-18")["plans"], sample_plan())


SETUP = r'''<script>
localStorage.removeItem('divian-cutting-plan-v2');
window.cuttingConfirm=async()=>true;
window.records={};window.failSave=false;window.conflictSave=false;
window.fetch=async(url,options)=>{
  const days=()=>Object.keys(records).sort().reverse().map(day=>{
    const totals={};records[day].plans.forEach(plan=>{totals[plan.colour]=(totals[plan.colour]||0)+plan.mainRows.reduce((sum,row)=>sum+Number(row.boards||0),0);});
    return {day,colours:Object.entries(totals).map(([colour,boards])=>({colour,boards})),total_boards:Object.values(totals).reduce((sum,n)=>sum+n,0)};
  });
  if(options){
    if(failSave)throw new Error('Teszt hálózati hiba');
    if(conflictSave)return {ok:false,json:async()=>({error:'Másik szerkesztő mentette'})};
    const data=JSON.parse(options.body);data.revision++;records[data.day]=data;
    return {ok:true,json:async()=>({ok:true,record:data,days:days()})};
  }
  const day=new URL(url,'http://localhost').searchParams.get('day');
  return {ok:true,json:async()=>({ok:true,record:JSON.parse(JSON.stringify(records[day]||{day,plans:[],revision:0})),days:days()})};
};
</script>'''

CHECKS = r'''<script>
(async()=>{
const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
const tick=()=>new Promise(resolve=>setTimeout(resolve,40));
const check=(condition,message)=>{if(!condition)throw new Error(message);};
const click=id=>document.getElementById(id).click();
const input=(el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));};
try{
  await tick();
  check(!document.getElementById('overview').hidden&&document.getElementById('editor').hidden,'Initial overview not shown');
  check(!document.getElementById('overviewEmpty').hidden,'Empty overview missing');
  document.getElementById('newDayDate').value='2026-11-18';click('newDayButton');await tick();
  check(document.getElementById('overview').hidden&&!document.getElementById('editor').hidden,'New day did not open editor');
  click('addPlan');document.querySelector('.cp-add-main-row').click();
  const normalPanel=document.querySelector('.cp-main-panel').getBoundingClientRect(),offcutPanel=document.querySelector('.cp-offcut-panel').getBoundingClientRect();
  check(normalPanel.right<=offcutPanel.left+1&&Math.abs(normalPanel.top-offcutPanel.top)<1,'Master size columns are not side by side');
  check(!document.querySelector('.cp-size-choice'),'Size selector still shown');
  input(document.querySelector('[data-field="width"]'),'600');input(document.querySelector('[data-field="height"]'),'400');
  input(document.querySelector('[data-field="boards"]'),'3');input(document.querySelector('[data-field="pieces"]'),'12');
  click('saveDay');await tick();
  check(records['2026-11-18'].plans[0].mainRows[0].boards==='3','Creation not persisted');
  check(document.getElementById('saveState').textContent.includes('Napi terv mentve'),'Missing save feedback');
  check(getComputedStyle(document.getElementById('saveDay')).display!=='none','Save button hidden');
  click('backToDays');await tick();
  const card=document.querySelector('[data-day="2026-11-18"]');
  check(card&&card.textContent.includes('Antracit')&&card.textContent.includes('3 tábla'),'Card summary missing');
  check(!document.getElementById('overview').hidden&&document.getElementById('editor').hidden,'Back did not show overview');
  document.getElementById('newDayDate').value='2026-11-19';click('newDayButton');await tick();
  check(document.querySelectorAll('.cp-plan').length===0,'New day inherited previous rows');
  click('saveDay');await tick();
  click('backToDays');await tick();
  check(document.querySelectorAll('.cp-day-card').length===2,'Saved days not listed');
  document.querySelector('[data-day="2026-11-18"]').click();await tick();
  check(document.querySelector('[data-field="boards"]').value==='3','Reopened plan differs');
  input(document.querySelector('[data-field="boards"]'),'8');click('saveDay');await tick();
  check(records['2026-11-18'].revision===2&&records['2026-11-18'].plans[0].mainRows[0].boards==='8','Edit not persisted');
  input(document.querySelector('[data-field="boards"]'),'9');failSave=true;click('saveDay');await tick();
  check(document.getElementById('saveState').dataset.error==='true','Network error hidden');
  check(document.querySelector('[data-field="boards"]').value==='9','Failed save lost edits');
  check(JSON.parse(localStorage.getItem('divian-cutting-day-draft:2026-11-18')).plans[0].mainRows[0].boards==='9','Recovery draft missing');
  failSave=false;conflictSave=true;click('saveDay');await tick();
  check(document.getElementById('saveState').textContent.includes('Másik szerkesztő'),'Conflict hidden');
  check(records['2026-11-18'].plans[0].mainRows[0].boards==='8','Conflict overwrote stored plan');
  conflictSave=false;click('saveDay');await tick();
  check(localStorage.getItem('divian-cutting-day-draft:2026-11-18')===null,'Saved draft not cleared');
  click('backToDays');await tick();
  check(document.querySelector('[data-day="2026-11-18"]').textContent.includes('9 tábla'),'Updated summary missing');
  document.querySelector('[data-day="2026-11-18"]').click();await tick();
  input(document.querySelector('[data-field="boards"]'),'10');
  window.cuttingConfirm=async()=>false;click('backToDays');
  check(!document.getElementById('editor').hidden,'Cancelled back discarded editor');
  window.cuttingConfirm=async()=>true;click('backToDays');await tick();
  document.querySelector('[data-day="2026-11-18"]').click();await tick();
  check(document.querySelector('[data-field="boards"]').value==='10','Back navigation lost local draft');
  result.textContent='PASS';
}catch(error){result.textContent='FAIL: '+error.stack;}
})();
</script>'''


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class DailyPlanBrowserTests(unittest.TestCase):
    def test_daily_workflow_and_failed_saves(self):
        self.check_browser(CHECKS)

    def test_zero_board_rows_group_live_and_after_reopening(self):
        record = {"day": "2026-11-18", "plans": grouped_plan(), "revision": 1}
        setup = SETUP.replace('</script>', f"records['2026-11-18']={json.dumps(record)};</script>")
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
          const tick=()=>new Promise(resolve=>setTimeout(resolve,40));
          const check=(ok,message)=>{if(!ok)throw new Error(message);};
          const rows=()=>document.querySelectorAll('[data-main-body] tr');
          try{
            await tick();document.querySelector('[data-day]').click();await tick();
            check(!rows()[0].dataset.parentRowId,'Leading zero has a parent');
            check(rows()[2].dataset.parentRowId==='row-1'&&rows()[3].dataset.parentRowId==='row-1','Consecutive zeros do not share the last positive parent');
            const parentRect=rows()[1].getBoundingClientRect(),childRect=rows()[2].getBoundingClientRect();
            check(Math.abs(parentRect.left-childRect.left)<1&&Math.abs(parentRect.right-childRect.right)<1&&Math.abs(parentRect.bottom-childRect.top)<1,'Parent and child do not share a continuous box');
            check(rows()[2].querySelector('[data-field="width"]').getBoundingClientRect().left>rows()[1].querySelector('[data-field="width"]').getBoundingClientRect().left+10,'Child dimensions are not indented');
            check(rows()[5].dataset.parentRowId==='row-4','New positive count does not start a new group');
            const field=rows()[4].querySelector('[data-field="boards"]');field.value='0';field.dispatchEvent(new Event('input'));
            check(rows()[4].dataset.parentRowId==='row-1'&&rows()[5].dataset.parentRowId==='row-1','Grouping did not update without rerender');
            check(rows()[5].dataset.groupEnd==='true'&&rows()[3].dataset.groupEnd==='false','Shared frame did not follow regrouping');
            check(document.querySelector('[data-head-board-total]').textContent==='3','Child rows counted as extra boards');
            document.getElementById('saveDay').click();await tick();document.getElementById('backToDays').click();await tick();document.querySelector('[data-day]').click();await tick();
            check(rows()[5].dataset.parentRowId==='row-1'&&rows()[5].querySelector('[data-field="boards"]').value==='0','Saved grouping changed after reopening');
            check(!document.querySelector('[data-offcut-body] tr').dataset.parentRowId,'Offcut grouped with main boards');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(checks, setup)

    def test_next_key_adds_size_in_same_panel_and_focuses_new_width(self):
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
          const tick=()=>new Promise(resolve=>setTimeout(resolve,40));
          const check=(ok,message)=>{if(!ok)throw new Error(message);};
          const key=(input,value,options={})=>input.dispatchEvent(new KeyboardEvent('keydown',{key:value,bubbles:true,cancelable:true,...options}));
          try{
            await tick();document.getElementById('newDayButton').click();await tick();document.getElementById('addPlan').click();
            document.querySelector('.cp-add-main-row').click();
            const fields=[...document.querySelectorAll('[data-main-body] tr:first-child input[type="number"]')];
            const values=['600','400','3','12'];
            fields.forEach((input,index)=>{
              check(input.enterKeyHint==='next'&&input.inputMode==='numeric','Tablet keyboard hints missing');
              input.value=values[index];input.dispatchEvent(new Event('input'));input.focus();
              if(index<fields.length-1){key(input,'Enter');check(document.activeElement===fields[index+1],'Next did not focus next field');}
            });
            key(fields.at(-1),'Enter');
            check(document.querySelectorAll('[data-main-body] tr').length===2,'Next did not add main row');
            check(document.activeElement===document.querySelector('[data-main-body] tr:last-child [data-field="width"]'),'New main width not focused');
            check(document.querySelector('[data-main-body] tr:first-child [data-field="pieces"]').value==='12','Next lost entered quantity');
            document.querySelector('.cp-add-offcut-row').click();
            const pieces=document.querySelector('[data-offcut-body] [data-field="pieces"]');pieces.value='5';pieces.dispatchEvent(new Event('input'));
            key(pieces,'Tab',{shiftKey:true});check(document.querySelectorAll('[data-offcut-body] tr').length===1,'Shift Tab added a row');
            key(pieces,'Enter',{repeat:true});check(document.querySelectorAll('[data-offcut-body] tr').length===1,'Repeated key added a row');
            key(pieces,'Tab');
            check(document.querySelectorAll('[data-offcut-body] tr').length===2&&document.querySelectorAll('[data-main-body] tr').length===2,'Next added row in wrong panel');
            check(document.activeElement===document.querySelector('[data-offcut-body] tr:last-child [data-field="width"]'),'New offcut width not focused');
            document.getElementById('saveDay').click();await tick();
            const plan=Object.values(records)[0].plans[0];
            check(plan.mainRows.length===2&&plan.mainRows[0].pieces==='12'&&plan.offcutRows.length===2&&plan.offcutRows[0].pieces==='5','New rows or entered quantities not saved');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(checks)

    def test_cut_rows_locked_and_draft_cannot_restore_old_edits(self):
        record = {"day": "2026-11-18", "plans": sample_plan(), "revision": 1,
                  "progress": [{"plan_id": "colour-1", "row_group": "mainRows", "row_id": "row-1", "done": True}]}
        draft = copy.deepcopy(record)
        draft["plans"][0]["mainRows"][0]["width"] = "999"
        draft["plans"][0]["offcutRows"][0]["pieces"] = "8"
        seed = (f"records['2026-11-18']={json.dumps(record)};"
                f"localStorage.setItem('divian-cutting-day-draft:2026-11-18',JSON.stringify({json.dumps(draft)}));")
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
          const tick=()=>new Promise(resolve=>setTimeout(resolve,40));
          const check=(ok,message)=>{if(!ok)throw new Error(message);};
          try{
            await tick();document.querySelector('[data-day]').click();await tick();
            const main=document.querySelector('[data-main-body] tr'),offcut=document.querySelector('[data-offcut-body] tr');
            check(main.dataset.locked==='true'&&Array.from(main.querySelectorAll('input,button')).every(node=>node.disabled),'Cut row is editable');
            check(main.querySelector('[data-field="width"]').value==='600','Draft replaced cut dimensions');
            check(!offcut.querySelector('input').disabled&&offcut.querySelector('[data-field="pieces"]').value==='8','Uncut draft changes lost or locked');
            check(document.querySelector('.cp-remove-plan').disabled,'Colour containing cut row can be deleted');
            check(document.getElementById('importLegacy').disabled,'Legacy import could replace cut rows');
            document.querySelector('.cp-add-main-row').click();
            check(document.querySelectorAll('[data-main-body] tr').length===2&&!document.querySelector('[data-main-body] tr:last-child input').disabled,'Adding uncut rows blocked');
            document.getElementById('saveDay').click();await tick();
            check(records['2026-11-18'].plans[0].mainRows[0].width==='600'&&records['2026-11-18'].plans[0].offcutRows[0].pieces==='8','Saving other edits changed locked row');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(checks, SETUP.replace('</script>', seed + '</script>'))

    def test_custom_confirmation_cancel_and_delete(self):
        checks = r'''<script>
        (async()=>{
          const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
          const tick=()=>new Promise(resolve=>setTimeout(resolve,40));
          const check=(ok,message)=>{if(!ok)throw new Error(message);};
          window.confirm=()=>{throw new Error('Native confirm must not be called');};
          try{
            await tick();document.getElementById('newDayButton').click();await tick();
            document.getElementById('addPlan').click();
            document.querySelector('.cp-remove-plan').click();await tick();
            let dialog=document.querySelector('.cp-confirm');
            check(dialog?.open&&dialog.matches(':modal'),'Styled confirmation not modal');
            check(dialog.querySelector('h2').textContent==='Szín törlése','Delete title missing');
            check(dialog.getBoundingClientRect().right<=innerWidth,'Confirmation exceeds viewport');
            check(document.activeElement===dialog.querySelector('[data-confirm="cancel"]'),'Cancel is not focused');
            dialog.querySelector('[data-confirm="cancel"]').click();await tick();
            check(document.querySelector('.cp-plan')&&!document.querySelector('.cp-confirm'),'Cancel deleted the plan or left modal behind');
            document.querySelector('.cp-remove-plan').click();await tick();
            document.querySelector('[data-confirm="accept"]').click();await tick();
            check(!document.querySelector('.cp-plan')&&!document.querySelector('.cp-confirm'),'Confirm did not delete plan');
            const answer=cuttingConfirm('<img src=x onerror=alert(1)>');
            dialog=document.querySelector('.cp-confirm');
            check(!dialog.querySelector('img'),'Confirmation text interpreted as HTML');
            dialog.dispatchEvent(new Event('cancel',{cancelable:true}));check(await answer===false,'Dismissal accepted action');
            result.textContent='PASS';
          }catch(error){result.textContent='FAIL: '+error.stack;}
        })();</script>'''
        self.check_browser(checks, SETUP.replace('window.cuttingConfirm=async()=>true;', ''))

    def check_browser(self, checks, setup=SETUP):
        page = render_page(board_catalog={"boards": [{"name": "Antracit"}]}).decode("utf-8")
        page = page.replace("</head>", setup + "</head>").replace("</body>", checks + "</body>")
        for width in (1360, 600):
            with self.subTest(width=width), tempfile.TemporaryDirectory(prefix="cutting-plan-browser-") as folder:
                path = Path(folder) / "index.html"
                path.write_text(page, encoding="utf-8")
                completed = subprocess.run([BROWSER, "--headless", "--disable-gpu", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking", "--allow-file-access-from-files",
                    f"--user-data-dir={folder}/profile", f"--window-size={width},900",
                    "--virtual-time-budget=5000", "--dump-dom", path.as_uri()],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                match = re.search(r'<pre id="browserTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                self.assertIsNotNone(match, completed.stderr[-2000:])
                self.assertEqual(html.unescape(match.group(1)), "PASS")


if __name__ == "__main__":
    unittest.main()
