"""Compact pallet cards keep the complete modal contents."""

import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from .putaway_page import render_page as putaway_page
from .wrapping_page import render_page as wrapping_page
from .test_days import BROWSER


CHECKS = r'''<script>
(async()=>{
 const result=document.createElement('pre');result.id='cardPreviewResult';document.body.append(result);
 const check=(ok,message)=>{if(!ok)throw new Error(message);};
 const until=async test=>{for(let i=0;i<100;i++){if(test())return;await new Promise(r=>setTimeout(r,20));}throw new Error('Timed out');};
 try{
  await until(()=>document.querySelectorAll('.fw-card').length===4);
  const cards=Array.from(document.querySelectorAll('.fw-card'));
  const heights=cards.map(card=>card.getBoundingClientRect().height);
  check(heights.every(height=>Math.abs(height-heights[0])<1),'Pallet cards have unequal heights');
  const putaway=!!document.getElementById('putawayDetail');
  check(cards.map(card=>card.querySelectorAll('.fw-item').length).join(',')==='1,1,1,1','Preview does not show exactly one item');
  check(!cards[0].querySelector('.fw-card-more'),'Extra count shown unnecessarily');
  check(cards[1].querySelector('.fw-card-more').textContent==='+ 1 további tétel'&&cards[2].querySelector('.fw-card-more').textContent==='+ 4 további tétel'&&cards[3].querySelector('.fw-card-more').textContent==='+ 2 további tétel','Hidden item count incorrect');
  check(cards.every(card=>!card.querySelector('.fw-pallet-icon')),'Pallet icon shown instead of contents');
  check(cards.every(card=>card.scrollHeight<=card.clientHeight+1&&card.scrollWidth<=card.clientWidth+1),'Card preview overflows');
  const button=cards[2].querySelector('button');button.click();
  const popup=document.getElementById(putaway?'putawayDetail':'wrappingDetail');await until(()=>popup.open);
  check(popup.querySelectorAll(putaway?'#putawayLines .fw-item':'#wrappingLines .fw-check').length===5,'Modal lost items hidden from preview');
  check(popup.textContent.includes('797'),'Last hidden item is missing from modal');
  document.getElementById(putaway?'putawayClose':'wrappingClose').click();await until(()=>!popup.open);
  result.textContent='PASS';
 }catch(error){result.textContent='FAIL: '+error.stack;}
})();</script>'''


@unittest.skipUnless(BROWSER, 'A local Chromium browser is required')
class CardPreviewTests(unittest.TestCase):
    def test_uniform_cards_overflow_count_and_complete_modal(self):
        for stage, render in [('wrapping', wrapping_page), ('putaway', putaway_page)]:
            pallets = []
            for index, count in enumerate((1, 2, 5, 3)):
                allocations = [{'plan_id':'p', 'row_group':'mainRows', 'row_id':str(n), 'colour':'Antracit', 'width':str(357+n*10), 'height':'718' if n<4 else '797', 'quantity':12} for n in range(count)]
                pallets.append({'id':str(index)*32, 'day':'2026-11-23', 'sent_date':'2026-11-23', 'sent_time':'08:25', 'sent_at':'2026-11-23T07:25:00+00:00', 'completed_at':'2026-11-23T09:25:00+00:00' if stage=='putaway' else None, 'allocations':allocations, 'wrapping_items':{}, 'wrapping_quantities':{json.dumps([a['plan_id'],a['row_group'],a['row_id']],separators=(',',':')):12 for a in allocations}, 'putaway_items':[]})
            payload = json.dumps({'ok':True,'pallets':pallets}, ensure_ascii=False).replace('</','<\\/')
            page = render().decode('utf8').replace('</head>', '<script>window.fetch=async()=>({ok:true,json:async()=>('+payload+')});</script></head>').replace('</body>', CHECKS+'</body>')
            for width in (1360,768):
                with self.subTest(stage=stage,width=width), tempfile.TemporaryDirectory(prefix='card-preview-test-') as folder:
                    path = Path(folder)/'index.html'
                    path.write_text(page,encoding='utf8')
                    completed = subprocess.run([BROWSER,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',f'--user-data-dir={folder}/profile',f'--window-size={width},1000','--virtual-time-budget=8000','--dump-dom',path.as_uri()],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=40)
                    match = re.search(r'<pre id="cardPreviewResult">(.*?)</pre>',completed.stdout,re.DOTALL)
                    self.assertIsNotNone(match,completed.stderr[-2000:])
                    self.assertEqual(html.unescape(match.group(1)),'PASS')


if __name__=='__main__': unittest.main()
