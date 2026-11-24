/* Persistent active pallet, quantity allocation and a draggable tablet panel. */
function createWorkerPallets({request, el, getRecord, onChange, onPending}) {
  const panel = document.getElementById('currentPallet');
  const body = document.getElementById('currentPalletBody');
  const list = document.getElementById('miniPalletItems');
  const key = item => JSON.stringify([item.plan_id, item.row_group, item.row_id]);
  let state = null, current = null, working = false, editing = false, dragging = null, failedPrint = null;
  const read = name => { try { return JSON.parse(localStorage.getItem(name)); } catch (_) { return null; } };
  const write = (name, value) => { try { localStorage.setItem(name, JSON.stringify(value)); } catch (_) {} };
  function notice(text, error = false) {
    const node = document.getElementById('miniPalletStatus');
    node.textContent = text; node.dataset.error = String(error);
  }
  function fresh() {
    const names = new Set((state?.pallets || []).map(p => p.name));
    let number = 1; while (names.has(`Raklap ${number}`)) number++;
    const id = globalThis.crypto?.randomUUID ? crypto.randomUUID().replaceAll('-', '') : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
    return {id, name: `Raklap ${number}`, status: 'draft', revision: 0, allocations: []};
  }
  function source(itemKey) { return state?.items.find(item => key(item) === itemKey); }
  const sizeKey = item => [Number(item?.width), Number(item?.height)].sort((a,b) => a-b).join('x');
  function palletRoom(item) {
    if (!item?.pallet_limit) return Infinity;
    const used = current.allocations.reduce((sum, allocation) => sum + (sizeKey(source(key(allocation))) === sizeKey(item) ? allocation.quantity : 0), 0);
    return Math.max(0, item.pallet_limit - used);
  }
  function setEditing(value) {
    if (editing === value) return;
    editing = value; onPending(value ? 1 : -1);
    document.getElementById('miniPalletReady').disabled = working || editing || !current?.allocations.length;
    document.getElementById('miniPalletPrint').disabled = working || editing || !current?.allocations.length;
    document.getElementById('miniPalletPrintRetry').disabled = working || editing;
    onChange();
  }
  function setWorking(value) {
    working = value; onPending(value ? 1 : -1);
    for (const node of panel.querySelectorAll('button,input')) {
      if (node.id !== 'collapsePallet') node.disabled = value;
    }
    document.getElementById('miniPalletReady').disabled = value || editing || !current?.allocations.length;
    document.getElementById('miniPalletPrint').disabled = value || editing || !current?.allocations.length;
    document.getElementById('miniPalletPrintRetry').disabled = value || editing;
    onChange();
  }
  function renderSent(data) {
    const root = document.getElementById('sentPallets'), pallets = data?.pallets || [];
    root.replaceChildren(); document.getElementById('sentPalletCount').textContent = `(${pallets.length})`;
    for (const pallet of pallets) {
      const card = el('details', '', 'cw-sent-card'); card.dataset.palletId = pallet.id;
      card.append(el('summary', `${pallet.name} · ${pallet.total_pieces} db · ${pallet.sent_time}`));
      card.append(el('small', `RK-${pallet.id.slice(0,8).toUpperCase()} · Vágási terv: ${pallet.day}`));
      for (const item of pallet.allocations) {
        const row = el('div', '', 'cw-sent-item'); const size = item.strip100 && item.row_group === 'offcutRows' ? '100 mm csík' : (item.width || item.height ? `${item.width || '–'} × ${item.height || '–'} mm` : 'Méret nélkül');
        const description=el('span', `${item.colour} · ${size}`);if(item.strip100&&item.row_group!=='offcutRows')description.append(el('small','100 mm csík','cw-strip-tag'));
        description.append(window.cuttingEdgeBadge(item.width,item.height,item.colour));
        row.append(description, el('strong', `${item.quantity} db`)); card.append(row);
      }
      const print = el('a', 'Nyomtatási kép');print.href=printUrl(pallet.day,pallet.id);print.target='_blank';print.rel='noopener';card.append(print);
      if(pallet.print_status==='error'){
        const retry=el('button','Nyomtatás újrapróbálása','cp-add-row');retry.type='button';retry.addEventListener('click',()=>retryPrint({day:pallet.day,id:pallet.id}));card.append(retry);
      }
      root.append(card);
    }
    if (!pallets.length) root.append(el('p', 'Ma még nem küldtél raklapot fóliázásra.', 'cw-pallet-note'));
  }
  function setState(next, reset = false, sentToday) {
    setEditing(false);
    const previous = current;
    state = next;
    const remembered = reset ? read(`cutting-active-pallet:${state.day}`) : previous?.id;
    current = state.pallets.find(p => p.id === remembered && p.status === 'draft');
    if (!current && !reset && previous?.revision === 0) current = previous;
    if (!current) current = state.pallets.find(p => p.status === 'draft') || fresh();
    current = structuredClone(current);
    const failed=sentToday?.pallets.find(pallet=>pallet.print_status==='error');
    failedPrint=failed?{day:failed.day,id:failed.id}:null;
    document.getElementById('miniPalletPrintRetry').hidden=!failedPrint;
    render(); renderSent(sentToday); onChange();
  }
  function render() {
    write(`cutting-active-pallet:${state.day}`, current.id);
    list.replaceChildren();
    for (const allocation of current.allocations) {
      const item = source(key(allocation));
      const line = el('div', '', 'cw-pallet-line');
      const size = item?.strip100 && item.row_group === 'offcutRows' ? '100 mm csík' : (item?.width || item?.height ? `${item.width || '–'} × ${item.height || '–'} mm` : 'Méret nélkül');
      const description=el('strong', `${item?.colour || 'Tétel'} · ${size}`);if(item?.strip100&&item.row_group!=='offcutRows')description.append(el('small','100 mm csík','cw-strip-tag'));
      description.append(window.cuttingEdgeBadge(item?.width,item?.height,item?.colour));
      line.append(description);
      const footer = el('div', '');
      const quantity = el('input', ''); quantity.type = 'number'; quantity.min = '0'; quantity.max = String(Math.min(allocation.quantity + (item?.available || 0), allocation.quantity + palletRoom(item))); quantity.step = '1'; quantity.inputMode = 'numeric'; quantity.enterKeyHint = 'done'; quantity.value = String(allocation.quantity);
      quantity.setAttribute('aria-label', `${item?.colour || 'Tétel'} ${size} darabszáma a raklapon`);
      quantity.addEventListener('input', () => { quantity.setCustomValidity(''); setEditing(quantity.value === '' || Number(quantity.value) !== allocation.quantity); });
      const saveQuantity = () => {
        if (working) return;
        if (quantity.value === '' || !quantity.checkValidity()) { setEditing(true); notice(`Adj meg 0 és ${quantity.max} közötti egész darabszámot.`, true); quantity.reportValidity(); return; }
        const count = Number(quantity.value);
        if (count === allocation.quantity) { setEditing(false); return; }
        const allocations = current.allocations.flatMap(entry => key(entry) !== key(allocation) ? [entry] : count ? [{...entry, quantity: count}] : []);
        persist(allocations, 'draft');
      };
      quantity.addEventListener('change', saveQuantity);
      quantity.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); saveQuantity(); } });
      footer.append(quantity, el('span', 'db'));
      const remove = el('button', '×'); remove.type = 'button';
      remove.setAttribute('aria-label', `${size} levétele a raklapról`);
      remove.addEventListener('click', () => {
        if (!working) {
          persist(current.allocations.filter(item => key(item) !== key(allocation)), 'draft');
        }
      });
      footer.append(remove); line.append(footer); list.append(line);
    }
    if (!current.allocations.length) list.append(el('p', 'Még nincs méret a raklapon.', 'cw-pallet-note'));
    const total = current.allocations.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('miniPalletTotal').textContent = `${total} db · ${current.allocations.length} méret`;
    document.getElementById('miniPalletTotal').hidden = !current.allocations.length;
    document.getElementById('miniPalletReady').disabled = working || editing || !current.allocations.length;
    document.getElementById('miniPalletPrint').disabled = working || editing || !current.allocations.length;
    clampPosition();
  }
  async function refresh() {
    const day = getRecord().day;
    const data = await request(`/apps/szabasterv/raklapok?day=${encodeURIComponent(day)}`);
    if (getRecord()?.day === day) setState(data.state, false, data.sent_today);
  }
  async function persist(allocations, status) {
    if (working || !current) return false;
    setWorking(true); notice(status === 'ready' ? 'Raklap lezárása és nyomtatása…' : 'Raklap mentése…');
    try {
      const data = await request('/apps/szabasterv/raklapok', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'Divian-HUB'},
        body: JSON.stringify({action: 'save', day: state.day, id: current.id, name: current.name, status, allocations, revision: current.revision, print: status === 'ready'})
      });
      if (status === 'ready') current = null;
      setState(data.state, false, data.sent_today);
      if(status === 'ready' && data.print && !data.print.ok){
        failedPrint={day:state.day,id:data.id};document.getElementById('miniPalletPrintRetry').hidden=false;
        notice('Raklap lezárva. A nyomtatás nem sikerült: '+(data.print.error||'A feladat állapota nem ismert.'),true);
      }else notice(status === 'ready' ? 'Raklap lezárva. Címke a nyomtatóra küldve.' : 'Mentve.');
      return true;
    } catch (error) {
      notice(error.message, true);
      return false;
    } finally { setWorking(false); }
  }
  function expand() {
    body.hidden = false;
    write('cutting-pallet-collapsed', false);
    document.body.classList.remove('cw-pallet-collapsed');
    const button = document.getElementById('collapsePallet');
    button.textContent = '−'; button.setAttribute('aria-expanded', 'true');
    button.setAttribute('aria-label', 'Raklapablak összecsukása');
    clampPosition();
  }
  async function add(itemKey) {
    if (working || editing) return;
    const item = source(itemKey);
    if (!item || item.available <= 0) { notice('Ebből a tételből nincs szabad, levágott darab.', true); return; }
    expand();
    const count = Math.min(item.available, palletRoom(item));
    if (count <= 0) { notice(`Ebből a méretből legfeljebb ${item.pallet_limit} db fér egy raklapra. Kattints a Lezárás gombra, és a maradékot tedd a következő raklapra.`); return false; }
    const allocations = structuredClone(current.allocations);
    const existing = allocations.find(allocation => key(allocation) === itemKey);
    if (existing) existing.quantity += count;
    else allocations.push({plan_id: item.plan_id, row_group: item.row_group, row_id: item.row_id, quantity: count});
    const saved = await persist(allocations, 'draft');
    if (saved && count < item.available) notice(`${count} db raklapra került. Még ${item.available-count} db vár raklapra; a Lezárás után folytathatod a következő raklapon.`);
    return saved;
  }
  document.getElementById('miniPalletReady').addEventListener('click', () => {
    if (!editing && current?.allocations.length) persist(current.allocations, 'ready');
  });
  async function retryPrint(target=failedPrint){
    if(working||editing||!target)return;
    setWorking(true);notice('Címke nyomtatása…');
    try{
      const data=await request('/apps/szabasterv/raklapok',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'Divian-HUB'},body:JSON.stringify({action:'print',...target})});
      if(!data.print?.ok)throw new Error(data.print?.error||'A nyomtatás nem sikerült.');
      setState(data.state,false,data.sent_today);notice('Címke a nyomtatóra küldve.');
    }catch(error){notice(error.message,true);}finally{setWorking(false);}
  }
  document.getElementById('miniPalletPrintRetry').addEventListener('click',()=>retryPrint());
  function printUrl(day,id){return '/apps/szabasterv/raklap-nyomtatas?'+new URLSearchParams({day,pallet_id:id});}
  document.getElementById('miniPalletPrint').addEventListener('click',()=>{
    if(!working&&!editing&&current?.allocations.length)window.open(printUrl(state.day,current.id),'_blank','noopener');
  });
  document.getElementById('collapsePallet').addEventListener('click', () => {
    if (body.hidden) expand();
    else {
      body.hidden = true;
      write('cutting-pallet-collapsed', true);
      document.body.classList.add('cw-pallet-collapsed');
      const button = document.getElementById('collapsePallet');
      button.textContent = '+'; button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-label', 'Raklapablak kinyitása');
    }
  });
  function move(x, y) {
    const rect = panel.getBoundingClientRect();
    const left = Math.max(10, Math.min(x, innerWidth - rect.width - 10));
    const top = Math.max(10, Math.min(y, innerHeight - rect.height - 10));
    Object.assign(panel.style, {left: `${left}px`, top: `${top}px`, right: 'auto', bottom: 'auto'});
    write('cutting-pallet-position', {x: left, y: top});
  }
  function clampPosition() {
    if (panel.hidden) return;
    const rect = panel.getBoundingClientRect(); move(rect.left, rect.top);
  }
  const handle = document.getElementById('palletDragHandle');
  handle.addEventListener('pointerdown', event => {
    if (event.target.closest('button') || event.button !== 0) return;
    const rect = panel.getBoundingClientRect();
    dragging = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    handle.setPointerCapture(event.pointerId); event.preventDefault();
  });
  handle.addEventListener('pointermove', event => { if (dragging) move(event.clientX - dragging.x, event.clientY - dragging.y); });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(name, () => { dragging = null; });
  handle.addEventListener('keydown', event => {
    if (event.target !== handle) return;
    const offsets = {ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20]};
    if (offsets[event.key]) {
      event.preventDefault(); const rect = panel.getBoundingClientRect(); const [x, y] = offsets[event.key]; move(rect.left + x, rect.top + y);
    }
  });
  window.addEventListener('resize', clampPosition);
  return {
    setState, source, refresh, busy: () => working || editing,
    invalidate: () => { state.items = []; onChange(); notice('A raklapadatok frissítése szükséges.', true); },
    show: () => {
      const pos = read('cutting-pallet-position');
      panel.hidden = false; document.body.classList.add('cw-page-active');
      const collapsed = read('cutting-pallet-collapsed');
      if (collapsed !== false) {
        body.hidden = true; document.body.classList.add('cw-pallet-collapsed');
        const button = document.getElementById('collapsePallet');
        button.textContent = '+'; button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-label', 'Raklapablak kinyitása');
      } else expand();
      if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) move(pos.x, pos.y);
      else {
        const shell = document.querySelector('.cp-shell').getBoundingClientRect(), rect = panel.getBoundingClientRect();
        move(shell.right - rect.width - 10, innerHeight - rect.height - 18);
      }
    },
    hide: () => { panel.hidden = true; document.body.classList.remove('cw-page-active'); }, add
  };
}
