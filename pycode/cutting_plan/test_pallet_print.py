"""Check saved pallet data, physical print sizes and lossless pagination."""

import html
import importlib.util
import re
import subprocess
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from . import pallet_store, store
from .pallet_print import render_page
from .test_days import BROWSER, sample_plan


DAY = "2026-11-18"


def seed(root, count=3, long_text=False):
    plans = sample_plan()
    plan = plans[0]
    plan["colour"] = "Bézs & <fa>" if not long_text else "Világosszürke " * 14
    original = plan["mainRows"][0]
    plan["mainRows"] = [{**original, "id": f"row-{i}", "width": str(600+i), "pieces": str(i+1)} for i in range(count)]
    plan["offcutRows"][0]["strip100"] = False
    store.save_day(root, DAY, plans, 0)
    allocations = []
    for group in ("mainRows", "offcutRows"):
        for row in plan[group]:
            quantity = int(row["pieces"])
            store.save_progress(root, DAY, plan["id"], group, row["id"], quantity, True, 0, 1)
            allocations.append({"plan_id": plan["id"], "row_group": group, "row_id": row["id"], "quantity": quantity})
    name = "Raklap 1" if not long_text else ("Hosszú raklapnév " * 6)[:100]
    return pallet_store.save_pallet(root, DAY, None, name, "ready", allocations, 0)


CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='printTestResult';result.style.display='none';document.body.append(result);
 const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
 for(let i=0;i<100&&!document.documentElement.dataset.printReady;i++)await new Promise(resolve=>setTimeout(resolve,20));
 try{
  check(document.documentElement.dataset.printReady==='true','Preview did not finish');
  const pages=[...document.querySelectorAll('.sheet')],cards=[...document.querySelectorAll('.label')];
  check(document.querySelectorAll('#printPages tbody tr').length===EXPECTED_ROWS,'Rows lost during pagination');
  for(const card of cards){
   const rect=card.getBoundingClientRect(),body=card.querySelector('.label-body'),table=card.querySelector('table');
   check(Math.abs(rect.width-EXPECTED_WIDTH*96/25.4)<1&&Math.abs(rect.height-EXPECTED_HEIGHT*96/25.4)<1,'Physical label size wrong');
   check(card.scrollHeight<=card.clientHeight+1,'Label contents clipped');
   check(table.getBoundingClientRect().height<=body.clientHeight+1,'Table contents clipped');
   check(card.querySelector('tbody tr'),'Blank continuation label');
  }
  check(!document.querySelector('#printPages script'),'Colour text interpreted as HTML');
  let printed=false;window.print=()=>{printed=true;};document.getElementById('printPallet').click();check(printed,'Print button does not open printing');
  result.textContent='PASS:'+pages.length;
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


class PalletPrintTests(unittest.TestCase):
    def test_preview_uses_saved_quantities_and_escaped_text(self):
        with tempfile.TemporaryDirectory() as folder:
            pallet_id = seed(Path(folder))
            page = render_page(folder, DAY, pallet_id).decode("utf-8")
            self.assertIn("Bézs &amp; &lt;fa&gt;", page)
            self.assertIn("2026. 11. 18.", page)
            self.assertIn("Méret nélkül", page)
            self.assertIn("9 db", page)
            for kwargs in ({"paper": "wrong"}, {"label_format": "wrong"}):
                with self.assertRaises(ValueError):
                    render_page(folder, DAY, pallet_id, **kwargs)
            with self.assertRaises(ValueError):
                render_page(folder, DAY, "missing")

    def test_print_route_reads_pallet_without_changing_it(self):
        import app

        class Handler(app.InvoiceHandler):
            def current_user(self):
                return app.AuthUser("print-test", "Print test", True)

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pallet_id = seed(root / 'szabasterv')
            before = pallet_store.load_pallets(root / 'szabasterv', DAY)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            with patch.object(app, 'RUNTIME_DIR', root):
                thread.start()
                try:
                    query = urlencode({'day': DAY, 'pallet_id': pallet_id, 'format': 'label', 'paper': 'a4'})
                    url = f'http://127.0.0.1:{server.server_port}/apps/szabasterv/raklap-nyomtatas?'
                    with urlopen(url+query) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
                        self.assertIn('width:105mm', response.read().decode('utf-8'))
                    with self.assertRaises(HTTPError) as error:
                        urlopen(url+urlencode({'day': DAY, 'pallet_id': 'missing'}))
                    self.assertEqual(error.exception.code, 400)
                    error.exception.close()
                finally:
                    server.shutdown(); server.server_close(); thread.join()
            self.assertEqual(pallet_store.load_pallets(root / 'szabasterv', DAY), before)


@unittest.skipUnless(BROWSER and importlib.util.find_spec("pypdf"), "Chromium and pypdf are required")
class PalletPrintBrowserTests(unittest.TestCase):
    def test_print_pdf_sizes_and_overflow_pagination(self):
        from pypdf import PdfReader

        for label_format, paper, count, long_text in (("a5", "a4", 3, False), ("label", "a4", 3, False),
                ("label", "actual", 3, False), ("a5", "actual", 40, False), ("label", "a4", 30, False), ("label", "a4", 1, True)):
            with self.subTest(format=label_format, paper=paper, count=count, long_text=long_text), tempfile.TemporaryDirectory(prefix="pallet-print-") as folder:
                root = Path(folder)
                pallet_id = seed(root / "runtime", count, long_text)
                page = render_page(root / "runtime", DAY, pallet_id, paper, label_format).decode("utf-8")
                width, height = (148, 210) if label_format == "a5" else (105, 80)
                checks = CHECKS.replace("EXPECTED_ROWS", str(count+1)).replace("EXPECTED_WIDTH", str(width)).replace("EXPECTED_HEIGHT", str(height))
                path, pdf = root / "preview.html", root / "preview.pdf"
                path.write_text(page.replace('</body>', checks+'</body>'), encoding="utf-8")
                completed = subprocess.run([BROWSER, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                    f'--user-data-dir={root}/profile', '--window-size=1100,1200', '--virtual-time-budget=3000', '--no-pdf-header-footer',
                    f'--print-to-pdf={pdf}', '--dump-dom', path.as_uri()], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
                match = re.search(r'<pre id="printTestResult"[^>]*>(.*?)</pre>', completed.stdout, re.DOTALL)
                self.assertIsNotNone(match, completed.stderr[-1500:])
                result = html.unescape(match.group(1))
                self.assertTrue(result.startswith('PASS:'), result)
                reader = PdfReader(pdf)
                self.assertEqual(len(reader.pages), int(result.split(':')[1]))
                expected = (210, 297) if paper == 'a4' else (width, height)
                for printed in reader.pages:
                    self.assertAlmostEqual(float(printed.mediabox.width)*25.4/72, expected[0], delta=.5)
                    self.assertAlmostEqual(float(printed.mediabox.height)*25.4/72, expected[1], delta=.5)
                text = '\n'.join(printed.extract_text() for printed in reader.pages)
                self.assertIn('2026. 11. 18.', text)
                self.assertIn('Méret nélkül', text)
                self.assertNotIn('A4-es teszthez', text)
                if count >= 30:
                    self.assertGreater(len(reader.pages), 1)


if __name__ == '__main__':
    unittest.main()
