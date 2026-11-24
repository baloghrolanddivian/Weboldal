"""Tablet-friendly cutting execution view, separate from plan editing."""

from pathlib import Path

from .page import PAGE
from .ui_style import style_page
from .history_ui import add_history_tabs
from .edge_catalog import with_edge_lookup


ROUTE = "/apps/szabasterv/szabasz"


def render_page():
    head = PAGE.split("</head>", 1)[0].replace("Gépterem", "Szabász nézet")
    logic = Path(__file__).with_name("worker_pallets.js").read_text(encoding="utf-8")
    return style_page(with_edge_lookup(add_history_tabs(head + WORKER.replace("{{PALLET_LOGIC}}", logic), "szabasz"))).encode("utf-8")


WORKER = r'''
<style>
 .cw-tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}.cw-tabs a{padding:12px 18px;border-radius:12px;background:#fff;color:var(--green-dark);font-weight:800;text-decoration:none}.cw-tabs a[aria-current]{background:var(--green);color:#fff}
 .cw-toolbar{display:flex;gap:16px;align-items:center;justify-content:space-between;padding:22px;margin-bottom:18px;flex-wrap:wrap}.cw-toolbar h1{margin:0;font:700 1.5rem Space Grotesk,sans-serif}.cw-toolbar h1:focus{outline:none}.cw-toolbar p{margin:8px 0 0;color:var(--muted);line-height:1.5}.cw-toolbar button{min-height:44px}
 .cw-list{display:grid;gap:18px}.cw-colour{padding:20px}.cw-colour h2{margin:0 0 5px;font:700 1.3rem Space Grotesk,sans-serif}.cw-colour>p{margin:0 0 14px;color:var(--muted);font-size:.85rem}
 .cw-item{padding:12px 0;border-top:1px solid var(--line);display:grid;grid-template-columns:minmax(0,1fr) 90px 90px 140px;align-items:center;gap:10px 14px}.cw-item[data-complete="true"]{background:var(--green);color:#fff}.cw-item[data-complete="true"] .cw-metric-label,.cw-item[data-complete="true"] .cp-field>span{color:#fff}
 .cw-details,.cw-boards,.cw-item .cp-field{min-width:0}.cw-size{display:block;font-weight:800;overflow-wrap:anywhere}.cw-info,.cw-result{display:block;margin-top:4px;font-size:.8rem;color:var(--muted);line-height:1.4}.cw-result[data-state="short"],.cw-result[data-state="stale"]{color:var(--orange)}.cw-result[data-state="full"]{color:var(--green-dark)}
 .cw-done{display:flex;align-items:center;gap:7px;min-height:44px;font-size:.82rem;font-weight:800}.cw-done input{width:24px;height:24px;accent-color:var(--green);margin:0;flex-shrink:0}.cw-item .cp-field input{min-width:0;min-height:44px;padding:0 9px;font-size:1rem;text-align:center}.cw-item button{min-height:44px;padding:0 12px;font-size:.82rem}.cw-status{grid-column:1/-1;margin:0;font-size:.82rem;color:var(--muted)}.cw-status:empty{display:none}.cw-status[data-error="true"]{color:var(--red)}
 .cw-item{gap:8px 10px}.cw-colour{padding:18px}
 .cw-item button:disabled{opacity:.45;cursor:not-allowed}.cw-free{display:block;margin-top:4px;font-size:.78rem;color:var(--green-dark)}
 .cw-pallet{position:fixed;z-index:80;right:18px;bottom:18px;width:350px;max-width:calc(100vw - 20px);max-height:calc(100dvh - 20px);overflow:hidden;border:1px solid #a8c9b8;border-radius:18px;background:#fff;box-shadow:0 16px 65px #123d2938;display:flex;flex-direction:column;color:var(--ink)}
 .cw-pallet-handle{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;background:#153b2a;color:#fff;cursor:grab;touch-action:none;user-select:none}.cw-pallet-handle:active{cursor:grabbing}.cw-pallet-handle small{display:block;margin-top:3px;font-size:.7rem;opacity:.75}.cw-pallet-handle button{min-width:44px;min-height:44px;border:0;border-radius:10px;background:#ffffff20;color:#fff;font-size:1.2rem;cursor:pointer}
 .cw-pallet-body{overflow:auto;padding:14px}.cw-pallet button{min-height:44px}
 .cw-pallet-list{display:grid;margin:0;max-height:min(360px,50dvh);overflow:auto}
 .cw-pallet-line{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid var(--line)}
 .cw-pallet-line strong{font-size:.8rem;line-height:1.5;overflow-wrap:anywhere}.cw-pallet-line>div{display:flex;align-items:center;gap:6px;font-size:.75rem;color:var(--muted)}
 .cw-pallet-line input{width:62px;min-width:0;min-height:44px;border:1px solid #cfdad3;border-radius:10px;background:#f6faf8;color:var(--ink);padding:0 6px;text-align:center;font:800 1rem Manrope,sans-serif;appearance:textfield}
 .cw-pallet-line input::-webkit-inner-spin-button,.cw-pallet-line input::-webkit-outer-spin-button{appearance:none;margin:0}
 .cw-pallet-line input:focus{outline:2px solid var(--green);outline-offset:1px}.cw-pallet-line button{width:36px;border:0;border-radius:10px;background:#fff1f0;color:var(--red);font-size:1.1rem;cursor:pointer}
 .cw-pallet-note{margin:12px 0 20px;font-size:.8rem;color:var(--muted);line-height:1.5}.cw-pallet-total{margin:14px 0;font-size:.8rem;font-weight:800;color:var(--muted)}
 .cw-pallet-status{margin:10px 0 0;font-size:.75rem;line-height:1.4;color:var(--muted)}.cw-pallet-status:empty{display:none}.cw-pallet-status[data-error="true"]{color:var(--red)}.cw-pallet-body>.cp-add-plan{width:100%}
 .cw-sent{margin-top:18px;padding:20px}.cw-sent h2{margin:0 0 12px;font:700 1.2rem Space Grotesk,sans-serif}.cw-sent-list{display:grid;gap:10px}.cw-sent-card{padding:12px;border:1px solid var(--line);border-radius:12px;font-size:.85rem;line-height:1.5}.cw-sent-card summary{cursor:pointer;font-weight:800}.cw-sent-card small{display:block;color:var(--muted);margin-top:5px}.cw-sent-item{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:8px;margin-top:8px}.cw-sent a{display:inline-block;margin-top:12px;color:var(--green-dark);font-weight:800}
 .cw-page-active #workerDetail{padding-bottom:460px}.cw-page-active.cw-pallet-collapsed #workerDetail{padding-bottom:90px}
 @media(max-width:620px){.cw-item{grid-template-columns:85px minmax(0,1fr) minmax(0,1.3fr);gap:8px}.cw-details{grid-column:1/-1}.cw-toolbar{padding:18px}.cw-item button{padding:0 8px;font-size:.76rem}.cw-pallet{width:320px}}
 .cw-item{grid-template-columns:minmax(0,1fr) 66px 90px auto;padding:12px 0;gap:12px}.cw-details{grid-column:auto}.cw-metric-label{display:block;color:var(--muted);font-size:.7rem;font-weight:800;margin-bottom:5px}.cw-size{font:800 1.35rem/1.2 Space Grotesk,sans-serif}.cw-board-count{display:block;font:800 1.7rem/1.2 Space Grotesk,sans-serif}.cw-item .cp-field{gap:5px}.cw-item .cp-field input{font-size:1.5rem;font-weight:800;min-height:48px}.cw-actions{display:flex;gap:7px;align-items:center}.cw-actions button{padding:0 9px;font-size:.75rem}.cw-colour h2{margin-bottom:14px}.cw-sent>summary{cursor:pointer;font-weight:800}.cw-sent[open] .cw-sent-list{margin-top:12px}
 @media(max-width:620px){.cw-item{grid-template-columns:minmax(0,1fr) 60px 90px}.cw-actions{grid-column:1/-1;justify-content:flex-end}.cw-size{font-size:1.3rem}}
 .cw-colour{padding:0;overflow:hidden}.cw-colour-head{display:flex;align-items:center;gap:12px;padding:18px 20px;margin:0;background:linear-gradient(115deg,#153b2a,#0a784a);color:#fff}.cw-plan-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.cw-subplan{min-width:0;padding:0 12px 12px}.cw-subplan>h3{margin:0 -12px;padding:13px 12px;background:#e8f6ee;color:var(--green-dark);font:700 .95rem Space Grotesk,sans-serif}.cw-offcut-panel{border-left:3px solid #efb77f;background:#fffaf5}.cw-offcut-panel>h3{background:#fff1e5;color:var(--orange)}
 .cw-item{grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(48px,1fr) 44px;gap:6px;padding:12px 6px}.cw-item .cw-actions{grid-column:auto;display:grid;grid-template-columns:44px;gap:0;align-items:end;align-self:end}.cw-size{font-size:1.15rem}.cw-board-count{font-size:1.45rem}.cw-item .cp-field input{font-size:1.3rem;padding:0 6px;min-height:44px}.cw-actions button{display:grid;place-items:center;width:44px;min-width:0;min-height:44px;padding:0;font-size:1.4rem;border-radius:10px}.cw-actions svg{width:26px;height:26px}.cw-actions [role="checkbox"][aria-checked="false"]{background:#fff;color:var(--green-dark);border:2px solid #b8cec1}.cw-actions [role="checkbox"][aria-checked="false"] svg{opacity:.25}.cw-actions [role="checkbox"][aria-checked="true"]{background:var(--green);color:#fff;border:2px solid var(--green)}.cw-item[data-complete="true"] .cw-actions button{background:#fff;color:var(--green-dark);border-color:#fff}.cw-offcut-panel .cw-boards{display:none}.cw-offcut-panel .cw-item{grid-template-columns:minmax(0,2fr) minmax(48px,1fr) 44px}.cw-panel-empty{font-size:.8rem;color:var(--muted);margin:18px 0}
 .cw-piece-count{display:flex;align-items:center;justify-content:center;min-height:44px;font:800 1.3rem/1.2 Space Grotesk,sans-serif;color:inherit}
 .cw-item>.cw-details,.cw-item>.cw-boards,.cw-item>.cp-field{display:grid;grid-template-rows:16px minmax(44px,auto);gap:5px;align-self:start}
 .cw-item .cw-metric-label,.cw-item>.cp-field>span{margin:0;font-size:.7rem;font-weight:800;line-height:16px;color:var(--muted)}
 .cw-item .cw-size,.cw-item .cw-board-count{display:flex;align-items:center;min-height:44px;margin:0}
 .cw-item[data-board-parent="true"],.cw-item[data-parent-row-id]{border-left:3px solid var(--green)}
 .cw-item[data-parent-row-id]{border-top-style:dashed;padding-left:12px}
 .cw-item[data-parent-row-id] .cw-size::before{content:'↳';margin-right:5px;flex-shrink:0}
 .cw-item[data-complete="true"][data-parent-row-id]{border-left-color:var(--green-dark)}
 .cw-colour-head h2{margin:0;min-width:0;overflow-wrap:anywhere}
 .cw-strip-tag{display:inline-flex;align-items:center;padding:2px 5px;border:1px solid #c6dbc9;border-radius:5px;background:#edf6e9;color:#3f693b;font:800 .6rem/1.3 Manrope,sans-serif;white-space:nowrap;vertical-align:middle}.cw-item>.cw-details>.cw-metric-label{display:flex;align-items:center;gap:6px}.cw-item[data-complete="true"] .cw-strip-tag{background:#ffffff26;color:#fff;border-color:#ffffff50}.cw-pallet-line .cw-strip-tag,.cw-sent-item .cw-strip-tag{margin-left:6px}.cw-sent-item .cw-strip-tag{display:inline-flex;margin-top:0;color:#3f693b}
 @media(max-width:480px){.cw-plan-columns{min-width:560px}.cw-colour{overflow-x:auto}}
</style></head>
<body class="cp-page" data-theme-scope="default"><main class="cp-shell">
 <header class="cp-top"><div class="cp-brand"><span class="cp-mark"></span><div><strong>Divian-HUB</strong><small>Gépterem</small></div></div><a class="cp-back" href="/">← Vissza a modulokhoz</a></header>
 <nav class="cw-tabs" aria-label="Szabászati nézetek"><a href="/apps/szabasterv">Szabászmester</a><a href="/apps/szabasterv/szabasz" aria-current="page">Szabász</a><a href="/apps/szabasterv/foliazo">Fóliázó</a><a href="/apps/szabasterv/elpakolas">Elpakolás</a></nav>
 <section id="workerOverview"><div id="workerDays" class="cp-day-grid"></div><p id="workerEmpty" hidden>Még nincs mentett napi terv.</p></section>
 <section id="workerDetail" hidden><header class="cp-card cw-toolbar"><div><h1 id="workerHeading" tabindex="-1"></h1></div><button id="workerBack" class="cp-add-row" type="button">← Vissza a napokhoz</button></header><div id="workerRows" class="cw-list"></div><details class="cp-card cw-sent"><summary>Ma fóliázásra küldött raklapok <span id="sentPalletCount"></span></summary><div id="sentPallets" class="cw-sent-list"></div><a href="/apps/szabasterv/foliazo">Fóliázó megnyitása →</a></details></section>
 <p id="workerStatus" class="cw-status" role="status" aria-live="polite"></p>
</main>
<aside class="cw-pallet" id="currentPallet" aria-label="Raklapkészítő" hidden>
 <header class="cw-pallet-handle" id="palletDragHandle" tabindex="0" aria-label="Raklapablak mozgatása; nyílbillentyűkkel is mozgatható"><strong id="miniPalletHeader">Raklapkészítő</strong><button id="collapsePallet" type="button" aria-expanded="true" aria-controls="currentPalletBody" aria-label="Raklapablak összecsukása">−</button></header>
 <div class="cw-pallet-body" id="currentPalletBody"><div id="miniPalletItems" class="cw-pallet-list"></div><p id="miniPalletTotal" class="cw-pallet-total"></p><button id="miniPalletReady" class="cp-add-plan" type="button">Lezárás</button><button id="miniPalletPrint" class="cp-add-row" type="button" style="width:100%;margin-top:8px">Nyomtatási kép</button><button id="miniPalletPrintRetry" class="cp-add-row" type="button" style="width:100%;margin-top:8px" hidden>Nyomtatás újrapróbálása</button><p id="miniPalletStatus" class="cw-pallet-status" role="status" aria-live="polite"></p></div>
</aside>
<script>{{PALLET_LOGIC}}</script><script>
(()=>{
 let record=null,dirty=new Set(),pending=0,allocationUpdaters=[];
 const overview=document.getElementById('workerOverview'),detail=document.getElementById('workerDetail'),root=document.getElementById('workerRows'),status=document.getElementById('workerStatus');
 function message(text,error=false){status.textContent=text;status.dataset.error=String(error);}
 async function request(url,options){const response=await fetch(url,options);let data;try{data=await response.json();}catch(_){throw new Error('A szerver nem érhető el. Próbáld újra.');}if(!response.ok||!data.ok)throw new Error(data.error||'Sikertelen művelet.');return data;}
 function el(tag,text,className=''){const node=document.createElement(tag);node.textContent=text;node.className=className;return node;}
 const palletUI=createWorkerPallets({request,el,getRecord:()=>record,onChange:()=>allocationUpdaters.forEach(fn=>fn()),onPending:delta=>{pending+=delta;}});
 async function mayLeave(){return !pending&&(!dirty.size||await cuttingConfirm('Vannak nem mentett darabszámok. Elhagyod ezt a napot?'));}
 async function loadDays(){
  message('Napok betöltése…');
  try{const data=await request('/apps/szabasterv/napok');const cards=document.getElementById('workerDays');cards.replaceChildren();document.getElementById('workerEmpty').hidden=data.days.length>0;
   data.days.forEach(day=>{const card=el('button','','cp-card cp-day-card');card.type='button';card.dataset.day=day.day;card.append(el('span',day.day.replaceAll('-','. ')+'.','cp-card-date'),el('span',`${day.total_boards} tábla összesen`,'cp-card-total'));const colours=el('span','','cp-card-colours');(day.colours||[]).forEach(item=>colours.append(el('span',`${item.colour} · ${item.boards} tábla`,'cp-card-colour')));card.append(colours,el('span','Vágás rögzítése →','cp-card-open'));card.addEventListener('click',()=>openDay(day.day));cards.append(card);});message('');
  }catch(error){message(error.message,true);}
 }
 async function openDay(day){
  if(!await mayLeave())return;
  message('Napi terv betöltése…');document.getElementById('workerDays').inert=true;
  try{const [data,palletData]=await Promise.all([request(`/apps/szabasterv/napok?day=${encodeURIComponent(day)}`),request(`/apps/szabasterv/raklapok?day=${encodeURIComponent(day)}`)]);record=data.record;dirty.clear();palletUI.setState(palletData.state,true,palletData.sent_today);render();overview.hidden=true;detail.hidden=false;palletUI.show();document.getElementById('workerHeading').textContent=`Vágás · ${day}`;document.getElementById('workerHeading').focus();message('');}catch(error){message(error.message,true);}finally{document.getElementById('workerDays').inert=false;}
 }
 function render(){
  root.replaceChildren();allocationUpdaters=[];let total=0;
  record.plans.forEach(plan=>{
   const groups=cuttingBoardGroups(plan.mainRows,true),boardGroups=new Map(groups.map(item=>[item.row.id,item])),boardParents=new Set(groups.filter(item=>item.parent).map(item=>item.parent.id));
   const block=el('section','','cp-card cw-colour'),heading=el('header','','cw-colour-head');heading.append(el('h2',plan.colour));block.append(heading);root.append(block);
   const columns=el('div','','cw-plan-columns');block.append(columns);
   cuttingColourCollapsible(heading,columns,JSON.stringify(['worker',record.day,plan.id]),plan.colour);
   for(const group of ['mainRows','offcutRows']){
    const panel=el('section','',group==='mainRows'?'cw-subplan cw-main-panel':'cw-subplan cw-offcut-panel');panel.append(el('h3',group==='mainRows'?'Normál méretek':'Leeső méretek'));columns.append(panel);
    if(!plan[group].length)panel.append(el('p','Nincs felvett méret.','cw-panel-empty'));
    for(const row of plan[group]){
    total++;const key=JSON.stringify([plan.id,group,row.id]);let saved=(record.progress||[]).find(item=>item.plan_id===plan.id&&item.row_group===group&&item.row_id===row.id);
    const line=el('div','','cw-item');line.dataset.rowId=row.id;
    const boardParent=group==='mainRows'?boardGroups.get(row.id)?.parent:null;
    if(group==='mainRows'){line.dataset.boardParent=String(boardParents.has(row.id));line.dataset.groupEnd=String(!!boardGroups.get(row.id)?.lastChild);}
    if(boardParent){line.dataset.parentRowId=boardParent.id;line.title=`A(z) ${boardParent.width||'–'} × ${boardParent.height||'–'} mm mérettel közös ${boardParent.boards} táblából.`;}
    const dimensions=row.strip100&&group==='offcutRows'?'100 mm csík':(row.width||row.height?`${row.width||'–'} × ${row.height||'–'} mm`:'Méret nélkül');
    const info=el('div','','cw-details'), sizeLabel=el('span','Méret','cw-metric-label');
    sizeLabel.append(window.cuttingEdgeBadge(row.width,row.height,plan.colour));
    if(row.strip100&&group==='mainRows'){const strip=el('small','100 mm csík','cw-strip-tag');strip.title='Plusz 100 mm-es csík';sizeLabel.append(strip);}
    info.append(sizeLabel,el('strong',dimensions,'cw-size'));
    const boards=el('div','','cw-boards');boards.append(el('span','Tábla','cw-metric-label'),el('strong',group==='mainRows'?String(row.boards||0):'—','cw-board-count'));
    if(boardParent)boards.querySelector('strong').textContent='';
    const label=el('label','','cp-field');label.append(el('span','Darab'));const actual=el('input','');actual.type='number';actual.min='0';actual.max='9999999';actual.step='1';actual.inputMode='numeric';actual.value=saved?String(saved.actual):String(row.pieces||0);actual.setAttribute('aria-label',`${plan.colour} ${dimensions} tényleges darabszám`);actual.title=`Tervezett: ${row.pieces||0} db`;label.append(actual);
    const pieceCount=el('strong','','cw-piece-count');pieceCount.hidden=true;label.append(pieceCount);
    const button=el('button','','cp-add-plan');button.type='button';button.dataset.action='cut';button.setAttribute('role','checkbox');button.setAttribute('aria-checked','false');button.setAttribute('aria-label',`${plan.colour} ${dimensions} levágva`);button.title='Levágtam';
    button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>';
    const addButton=el('button','','cp-add-row');addButton.type='button';addButton.dataset.action='pallet';addButton.setAttribute('aria-label',`${plan.colour} ${dimensions} raklapra rakása`);
    addButton.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 16h18v3H3zM5 19v2m7-2v2m7-2v2M4 16V8h8v8m0-8h8v8M8 8V3h8v5M8 11h0m8 0h0"/></svg>';
    const actions=el('div','','cw-actions');actions.append(button,addButton);const feedback=el('p','','cw-status');feedback.setAttribute('role','status');
    line.append(info);if(group==='mainRows')line.append(boards);line.append(label,actions,feedback);panel.append(line);
    function updateAllocation(){
     const source=palletUI.source(key),cutConfirmed=!!(saved?.matches_plan&&saved.done&&!dirty.has(key)&&Number(actual.value)===saved.actual),allocated=!!source&&source.available===0&&source.allocated>0;
     actual.readOnly=!!source?.allocated||palletUI.busy();
     actual.hidden=!!source?.allocated;pieceCount.hidden=!actual.hidden;pieceCount.textContent=actual.value;
     button.setAttribute('aria-checked',String(cutConfirmed));button.hidden=cutConfirmed;button.disabled=actual.disabled||cutConfirmed||palletUI.busy();
     addButton.hidden=!cutConfirmed||allocated;addButton.disabled=!cutConfirmed||!source||source.available<=0||palletUI.busy();
     addButton.setAttribute('aria-label',`${plan.colour} ${dimensions} · ${allocated?'Raklapra rakva':'Raklapra rakom'}`);
     addButton.title=source?`${allocated?'Raklapra rakva · ':''}Raklapra tehető: ${source.available} db · Raklapokon: ${source.allocated} db`:'Előbb rögzítsd a vágást.';
     line.dataset.complete=String(cutConfirmed&&allocated);
    }
    allocationUpdaters.push(updateAllocation);addButton.addEventListener('click',()=>palletUI.add(key));
    function update(){const planned=Number(row.pieces||0);line.dataset.shortfall=String(saved?Math.max(0,planned-saved.actual):0);line.dataset.cutState=saved?.matches_plan?'saved':'pending';
     if(saved&&!saved.matches_plan){feedback.textContent='A terv módosult. Ellenőrizd a darabszámot, majd rögzítsd újra a vágást.';feedback.dataset.error='true';}
     updateAllocation();
    }
    function changed(){if(actual.readOnly)return;dirty.add(key);feedback.textContent='';feedback.dataset.error='false';update();}
    actual.addEventListener('input',changed);
    button.addEventListener('click',async()=>{
     if(actual.readOnly)return;
     if(actual.value===''||!actual.checkValidity()){feedback.textContent='Adj meg érvényes, nemnegatív egész darabszámot.';feedback.dataset.error='true';actual.focus();return;}
     button.disabled=actual.disabled=true;addButton.disabled=true;pending++;feedback.textContent='';feedback.dataset.error='false';
     try{const data=await request('/apps/szabasterv/teljesites',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'Divian-HUB'},body:JSON.stringify({day:record.day,plan_id:plan.id,row_group:group,row_id:row.id,actual:Number(actual.value),done:true,revision:saved?.revision||0,plan_revision:record.revision})});saved=data.progress;dirty.delete(key);feedback.textContent='';update();try{await palletUI.refresh();}catch(error){palletUI.invalidate();message('Vágás rögzítve. A raklapadatok nem frissültek: '+error.message,true);}}
     catch(error){dirty.add(key);feedback.textContent=error.message;feedback.dataset.error='true';}
     finally{pending--;button.disabled=actual.disabled=false;updateAllocation();}
    });update();
   }}
  });if(!total)root.append(el('p','Ehhez a naphoz még nincs vágási tétel.'));
 }
 document.getElementById('workerBack').addEventListener('click',async()=>{if(!await mayLeave())return;dirty.clear();detail.hidden=true;overview.hidden=false;palletUI.hide();loadDays();});
 window.addEventListener('beforeunload',event=>{if(dirty.size||pending){event.preventDefault();event.returnValue='';}});
 loadDays();
})();</script></body></html>'''
