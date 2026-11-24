"""Evidence-based edge lookup, alias matching and conservative ambiguity handling."""

import html
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from . import edge_catalog
from .test_days import BROWSER


class EdgeCatalogTests(unittest.TestCase):
    def test_imports_exact_integer_sizes_codes_and_namespaced_fields(self):
        from scripts.build_cutting_edge_catalog import collect
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / '12'
            source.mkdir()
            (source / 'Osszekeszito.xml').write_text('''<Root xmlns="urn:test"><CON><Hossz>724.000</Hossz><Szelleseg>505.000</Szelleseg><Szin>Antracit kr.</Szin><ElzarTip>1H</ElzarTip><Leiras>Alsó oldal</Leiras></CON><CON><Hossz>720</Hossz><Szelleseg>290</Szelleseg><Elzaras>1H2R</Elzaras></CON><CON><Hossz>720.5</Hossz><Szelleseg>290</Szelleseg><Elzaras>1H</Elzaras></CON><CON><Hossz>720</Hossz><Szelleseg>290</Szelleseg><Elzaras>-</Elzaras></CON></Root>''', encoding='utf8')
            (source / 'Front_osszekeszito.xml').write_text('<Root><CON><Hossz>718</Hossz><Szelleseg>597</Szelleseg><Elzaras>K</Elzaras></CON></Root>', encoding='utf8')
            result = collect(root)
            self.assertEqual(result['file_count'], 2)
            self.assertEqual([(r['width'],r['height'],r['edge']) for r in result['records']], [(290,720,'1H2R'), (505,724,'1H'), (597,718,'2H2R')])
            self.assertEqual(result['records'][1]['sources'], ['12/Osszekeszito.xml'])
            self.assertEqual(result['records'][2]['source_edges'], ['K'])

    def test_real_catalog_contains_reference_sizes_and_colour_aliases(self):
        catalog = edge_catalog.load_catalog()
        self.assertEqual(catalog['aliases']['antracitkr'], 'antracit')
        self.assertEqual({r['edge'] for r in catalog['sizes']['505x724']}, {'1H'})
        self.assertEqual({r['edge'] for r in catalog['sizes']['290x720']}, {'1H2R'})
        self.assertGreater(len(catalog['sizes']), 300)

    def test_missing_catalog_keeps_the_workstation_available(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(edge_catalog.load_catalog(Path(folder)/'missing.json', override_path=Path(folder)/'missing-overrides.json')['sizes'], {})


CHECKS = r'''<script>
try{
 const check=(ok,msg)=>{if(!ok)throw new Error(msg);};
 const lookup=window.cuttingEdgeLookup;
 check(lookup(724,505,'Antracit').code==='1H','Long edge lookup failed');
 check(lookup('505','724','Antracit kr.').code==='1H','Rotated size or alias failed');
 check(lookup(720,290,'Antracit').code==='1H2R','Three-side edge lookup failed');
 check(lookup(100,163,'Antracit').status==='ambiguous','Ambiguous size guessed');
 check(lookup(100,163,'Artizán tölgy').code==='N','Colour-specific lookup failed');
 check(lookup(3999,3998,'Antracit').status==='unknown','Unknown size guessed');
 check(lookup(724,504,'Antracit').code==='1H'&&lookup(724,504,'Antracit').approximate,'Nearby size was not marked approximate');
 const approximate=lookup(598,720,'Antracit');
 check(approximate.code==='2H2R'&&approximate.approximate&&JSON.stringify(approximate.matchedSizes)==='[[597,718]]','Requested approximate front size did not match');
 check(lookup(720,598,'Antracit').code==='2H2R'&&approximate.title.includes('597 × 718'),'Rotated approximate size or matched dimensions missing');
 check(lookup(597,718,'Antracit').code==='2H2R'&&!lookup(597,718,'Antracit').approximate,'Exact size did not take precedence');
 const confirmed=lookup(359,720,'Antracit');
 check(confirmed.code==='2H2R'&&confirmed.approximate&&JSON.stringify(confirmed.matchedSizes)==='[[357,718]]','Confirmed 359x720 mapping was replaced by a closer unrelated size');
 check(lookup(720,359,'Fehér').code==='2H2R'&&lookup(357,718,'Fehér').code==='2H2R','Confirmed size rotation or edge specification lost');
 check(lookup('',505,'Antracit').status==='missing','Incomplete size matched');
 const badge=window.cuttingEdgeBadge(724,505,'Antracit');document.body.append(badge);
 check(badge.textContent==='1H'&&badge.title.includes('hosszú'),'Badge has no meaning');
 window.cuttingUpdateEdgeBadge(badge,720,290,'Antracit');check(badge.textContent==='1H2R','Badge did not follow dimension edits');
 window.cuttingUpdateEdgeBadge(badge,'',290,'Antracit');check(badge.hidden,'Stale badge remained');
 document.getElementById('edgeTestResult').textContent='PASS';
}catch(error){document.getElementById('edgeTestResult').textContent='FAIL: '+error.stack;}
</script>'''


@unittest.skipUnless(BROWSER, 'A local Chromium browser is required')
class EdgeBrowserTests(unittest.TestCase):
    def test_approximate_ties_and_tolerance_do_not_guess(self):
        fixture = {'aliases': {}, 'sizes': {
            '998x1000': [{'colour': 'test', 'edge': '1H', 'descriptions': []}],
            '1000x1002': [{'colour': 'test', 'edge': '1R', 'descriptions': []}],
        }}
        checks = '''<script>try{const f=window.cuttingEdgeLookup;if(f(1000,1000,'test').status!=='ambiguous')throw Error('Tied codes guessed');if(f(998,1000,'test').code!=='1H'||f(998,1000,'test').approximate)throw Error('Exact match lost');if(f(1004,1006,'test').status!=='unknown')throw Error('Tolerance exceeded');document.getElementById('edgeTestResult').textContent='PASS';}catch(e){document.getElementById('edgeTestResult').textContent='FAIL: '+e.message;}</script>'''
        with patch.object(edge_catalog, 'load_catalog', return_value=fixture):
            self.check_page(checks)

    def test_codes_rotations_colours_ambiguity_and_live_updates(self):
        self.check_page(CHECKS)

    def check_page(self, checks):
        page = edge_catalog.with_edge_lookup('<html><head></head><body><pre id="edgeTestResult"></pre>'+checks+'</body></html>')
        with tempfile.TemporaryDirectory(prefix='edge-browser-') as folder:
            path = Path(folder)/'index.html'
            path.write_text(page, encoding='utf8')
            completed = subprocess.run([BROWSER, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', f'--user-data-dir={folder}/profile', '--dump-dom', path.as_uri()], capture_output=True, text=True, encoding='utf8', errors='replace', timeout=40)
            match = re.search(r'<pre id="edgeTestResult">(.*?)</pre>', completed.stdout, re.DOTALL)
            self.assertIsNotNone(match, completed.stderr[-2000:])
            self.assertEqual(html.unescape(match.group(1)), 'PASS')


if __name__ == '__main__': unittest.main()
