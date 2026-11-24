"""Check the warehouse catalog and manual cutting-plan dimensions."""

import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from .page import DEFAULT_CATALOG_PATH, load_size_catalog, render_page
from .test_days import BROWSER, SETUP


class WarehouseCatalogTests(unittest.TestCase):
    def test_complete_colour_size_catalog(self):
        source = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(source), 1088)
        self.assertEqual(sum(len(row["source_rows"]) for row in source), 1096)
        self.assertEqual(len({row["colour_code"] for row in source}), 20)
        catalog = load_size_catalog()
        self.assertEqual(len(catalog), len(source))
        self.assertTrue(all(row["colour"] for row in catalog))
        self.assertTrue(all(row["families"] for row in catalog))
        for row in catalog:
            self.assertIn(" · ", row["label"])
        bottom = next(row for row in catalog if row["colour"] == "Antracit" and (row["width"], row["height"]) == (163, 505))
        self.assertEqual(bottom["label"], "163 × 505 mm · Fenék")
        self.assertTrue(any("Hátfal" in row["label"] for row in catalog))
        for code, colour, count in (("ANK", "Antracit", 176), ("FEL", "Fehér", 203), ("KTL", "Canyon", 56), ("ANK/FEL", "Antracit kr./Fehér", 35)):
            with self.subTest(code=code):
                self.assertEqual(sum(row["colour_code"] == code for row in source), count)
                self.assertEqual(sum(row["colour"] == colour for row in catalog), count)


CHECKS = r'''<script>
(async()=>{
  const result=document.createElement('pre');result.id='browserTestResult';document.body.append(result);
  const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
  const check=(ok,message)=>{if(!ok)throw new Error(message);};
  try{
    await tick();
    document.getElementById('newDayButton').click();await tick();
    const colour=document.getElementById('colour');
    const colours=Array.from(colour.options,option=>option.value);
    check(colours.includes('Fehér fényes evogloss')&&colours.includes('Világos Szürke'),'Excel-only colours missing');
    for(const name of colours){
      colour.value=name;document.getElementById('addPlan').click();
      const article=Array.from(document.querySelectorAll('.cp-plan')).find(el=>el.querySelector('[data-colour]').textContent===name);
      article.querySelector('.cp-add-main-row').click();
      // Adding a row re-renders all cards.
      const current=Array.from(document.querySelectorAll('.cp-plan')).find(el=>el.querySelector('[data-colour]').textContent===name);
      current.querySelector('.cp-add-offcut-row').click();
      const card=Array.from(document.querySelectorAll('.cp-plan')).find(el=>el.querySelector('[data-colour]').textContent===name);
      check(!card.querySelector('.cp-size-choice'),'Size dropdown still present');
      const main=card.querySelector('[data-main-body] tr'),offcut=card.querySelector('[data-offcut-body] tr');
      if(name==='Antracit'){
        const initialHeight=main.getBoundingClientRect().height;
        for(const [width,height,expected] of [['724','505','1H'],['290','720','1H2R'],['598','720','≈ 2H2R'],['100','163','Ellenőrizd'],['3999','3998','Nincs adat']]){
          for(const [field,value] of [['width',width],['height',height]]){const input=main.querySelector(`[data-field="${field}"]`);input.value=value;input.dispatchEvent(new Event('input'));}
          check(main.querySelector('.cp-edge-tag').textContent===expected,'Edge badge did not match manually entered size');
          const top=main.querySelector('[data-field="width"]').getBoundingClientRect().top;
          check(['height','boards','pieces'].every(field=>Math.abs(main.querySelector(`[data-field="${field}"]`).getBoundingClientRect().top-top)<1),'Edge badge shifted input alignment');
          check(Math.abs(main.getBoundingClientRect().height-initialHeight)<1,'Edge badge changed row height');
          check(main.querySelector('.cp-edge-tag').getBoundingClientRect().bottom<=top,'Edge badge overlaps size input');
        }
      }
      for(const field of ['width','height']){
        const input=main.querySelector(`[data-field="${field}"]`);input.value=field==='width'?'777':'333';input.dispatchEvent(new Event('input'));
        check(!offcut.querySelector(`[data-field="${field}"]`).required,'Offcut dimension is required');
      }
      check(!offcut.querySelector('[data-field="strip100"]'),'Offcut still has +100 control');
      main.querySelector('[data-field="strip100"]').click();
      check(main.querySelector('[data-field="width"]').value==='777','+100 cleared the main dimension');
      const pieces=offcut.querySelector('[data-field="pieces"]');pieces.value='5';pieces.dispatchEvent(new Event('input'));
    }
    document.getElementById('saveDay').click();await tick();
    check(document.getElementById('saveState').dataset.error!=='true','Manual plan failed to save');
    document.getElementById('backToDays').click();await tick();
    document.querySelector('[data-day]').click();await tick();
    check(document.querySelectorAll('.cp-plan').length===colours.length,'Plans lost after reopen');
    for(const card of document.querySelectorAll('.cp-plan')){
      const main=card.querySelector('[data-main-body] tr'),offcut=card.querySelector('[data-offcut-body] tr');
      check(main.querySelector('[data-field="width"]').value==='777'&&main.querySelector('[data-field="height"]').value==='333','Manual dimensions lost after reopen');
      check(main.querySelector('[data-field="strip100"]').checked,'Main +100 lost after reopen');
      check(offcut.querySelector('[data-field="width"]').value===''&&offcut.querySelector('[data-field="height"]').value===''&&offcut.querySelector('[data-field="pieces"]').value==='5','Optional offcut dimensions did not survive save');
    }
    result.textContent='PASS';
  }catch(error){result.textContent='FAIL: '+error.stack;}
})();
</script>'''


@unittest.skipUnless(BROWSER, "A local Chromium browser is required")
class WarehouseSizeBrowserTests(unittest.TestCase):
    def test_all_colours_preserve_manual_sizes_main_strip_and_optional_offcut(self):
        page = render_page().decode("utf-8")
        page = page.replace("</head>", SETUP + "</head>")
        page = page.replace("</body>", CHECKS + "</body>")
        for width in (1360,768):
            with tempfile.TemporaryDirectory(prefix="warehouse-sizes-browser-") as folder:
                path = Path(folder) / "index.html"
                path.write_text(page, encoding="utf-8")
                completed = subprocess.run([BROWSER, "--headless", "--disable-gpu", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking", "--allow-file-access-from-files",
                    f"--user-data-dir={folder}/profile", f"--window-size={width},900", "--virtual-time-budget=8000",
                    "--dump-dom", path.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                match = re.search(r'<pre id="browserTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
                self.assertIsNotNone(match, completed.stderr[-2000:])
                self.assertEqual(html.unescape(match.group(1)), "PASS")


    if __name__ == "__main__":
        unittest.main()
