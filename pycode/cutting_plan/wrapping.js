(() => {
  const root = document.getElementById('wrappingCards');
  const detail = document.getElementById('wrappingDetail');
  const lines = document.getElementById('wrappingLines');
  let sequence = 0, data = null, current = null, busy = false, dirty = false;
  const dirtyKeys = new Set();
  const key = item => JSON.stringify([item.plan_id, item.row_group, item.row_id]);
  const el = (tag, text, cls = '') => { const node = document.createElement(tag); node.textContent = text; node.className = cls; return node; };
  const size = item => item.strip100 && item.row_group === 'offcutRows' ? '+100 csík' : (item.width || item.height ? `${item.width || '–'} × ${item.height || '–'} mm` : 'Méret nélkül') + (item.strip100 ? ' · +100' : '');
  function message(text, error = false, selected = false) {
    const node = document.getElementById(selected ? 'wrappingDetailStatus' : 'wrappingStatus');
    node.textContent = text; node.dataset.error = String(error);
  }
  async function request(url, options) {
    const response = await fetch(url, options); let result;
    try { result = await response.json(); } catch (_) { throw new Error('A szerver nem érhető el. Próbáld újra.'); }
    if (!response.ok || !result.ok) throw new Error(result.error || 'Sikertelen művelet.');
    return result;
  }
  async function mayLeave() { return !busy && (!dirty || await cuttingConfirm('Vannak nem mentett jelölések vagy darabszámok. Elveted őket?')); }
  function drawCards() {
    root.replaceChildren();
    data.pallets.filter(p => !p.completed_at).forEach(p => {
      const card = el('article', '', 'cp-card fw-card'); card.dataset.palletId = p.id;
      const button = el('button', '', 'fw-pallet'); button.type = 'button';
      const timestamp = el('time', `Szabva: ${p.sent_date} ${p.sent_time}`); timestamp.dateTime = p.sent_at;
      button.setAttribute('aria-label', `Raklap, ${timestamp.textContent}`);
      const heading = el('h2', ''); heading.append(timestamp); heading.title = heading.textContent;
      const header = el('span', '', 'fw-card-head'); header.append(heading); button.append(header);
      const preview = el('span', '', 'fw-card-items');
      for (const item of p.allocations.slice(0, 1)) {
        const row = el('span', '', 'fw-item');
        row.append(el('span', `${item.colour} · ${size(item)}`), el('strong', `${item.quantity} db`));
        row.title = `${item.colour} · ${size(item)} · ${item.quantity} db`;
        preview.append(row);
      }
      button.append(preview);
      if (p.allocations.length > 1) button.append(el('span', `+ ${p.allocations.length - 1} további tétel`, 'fw-card-more'));
      button.addEventListener('click', () => openPallet(p.id)); card.append(button); root.append(card);
    });
    document.getElementById('wrappingEmpty').hidden = root.childElementCount > 0;
  }
  async function load() {
    if (busy) return;
    const call = ++sequence; message('Raklapok betöltése…');
    try {
      const result = await request('/apps/szabasterv/foliazasra-var');
      if (call !== sequence) return;
      data = result; drawCards(); message('');
    } catch (error) { if (call === sequence) message(error.message, true); }
  }
  async function openPallet(id) {
    if (!await mayLeave()) return;
    current = structuredClone(data.pallets.find(p => p.id === id)); dirty = false;
    drawDetail(); detail.showModal(); message('');
    lines.querySelector('input')?.focus();
  }
  function collect() { return Object.fromEntries(current.allocations.map(item => [key(item),!!current.wrapping_items[key(item)]])); }
  function controls() {
    document.getElementById('wrappingClose').disabled = busy;
    if (!current) return;
    for (const row of lines.querySelectorAll('.fw-check')) {
      const input = row.querySelector('input[type="number"]');
      const done = !!current.wrapping_items[input.dataset.key];
      row.dataset.wrapped = String(done && !dirtyKeys.has(input.dataset.key));
      const button = row.querySelector('[data-action="wrapped"]');
      button.textContent = done && !dirtyKeys.has(input.dataset.key) ? 'Lefóliázva ✓' : 'Lefóliázva';
      button.disabled = busy || !!current.completed_at || (done && !dirtyKeys.has(input.dataset.key));
    }
    for (const input of lines.querySelectorAll('input')) input.disabled = busy || !!current.completed_at;
  }
  function drawDetail() {
    dirtyKeys.clear(); dirty = false;
    const cutTime = document.getElementById('wrappingCutTime'); cutTime.textContent = `Szabva: ${current.sent_date} ${current.sent_time}`; cutTime.dateTime = current.sent_at;
    lines.replaceChildren();
    for (const item of current.allocations) {
      const row = el('div', '', 'fw-check'), label = el('div', '', 'fw-check-label');
      const description = el('span', `${item.colour} · ${size(item)}`); description.title = description.textContent;
      label.append(description, window.cuttingEdgeBadge(item.width,item.height,item.colour), el('strong', `${item.quantity} db`, 'fw-quantity'));
      const numberLabel = el('label', '', 'fw-good'), number = el('input', ''); number.type = 'number'; number.min = '0'; number.max = String(item.quantity); number.step = '1'; number.inputMode = 'numeric'; number.dataset.key = key(item);
      number.value = String(item.quantity - (current.wrapping_quantities?.[key(item)] ?? item.quantity)); number.setAttribute('aria-label', `${item.colour} ${size(item)} selejt darabszám`);
      const button = el('button','Lefóliázva','cp-add-plan'); button.type='button'; button.dataset.action='wrapped';
      button.setAttribute('aria-label',`${item.colour} ${size(item)} lefóliázva`);button.addEventListener('click',()=>save(key(item)));
      numberLabel.append(el('span', 'Selejt / hibás (db)'), number); row.append(label,numberLabel,button); lines.append(row);
      number.addEventListener('input',()=>{dirtyKeys.add(key(item));dirty=true;controls();message('',false,true);});
    }
    controls();
    message('', false, true);
  }
  async function save(rowKey) {
    if (busy || !current || current.completed_at) return;
    const items = collect(), quantities = {...current.wrapping_quantities};
    const item=current.allocations.find(item=>key(item)===rowKey), input=[...lines.querySelectorAll('input')].find(input=>input.dataset.key===rowKey);
    if (!item || !input) return;
    if (input.value==='' || !input.checkValidity()) {message('A selejt 0 és a raklapon lévő mennyiség közötti egész szám legyen.',true,true);input.focus();return;}
    items[rowKey]=true; quantities[rowKey]=item.quantity-Number(input.value);
    const complete = Object.values(items).every(Boolean) && [...dirtyKeys].every(k => k === rowKey);
    busy = true; controls(); message('', false, true);
    let finished = false;
    try {
      const result = await request('/apps/szabasterv/foliazas', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'Divian-HUB'},
        body: JSON.stringify({id: current.id, revision: current.wrapping_revision, pallet_revision: current.revision, items, quantities, complete})});
      Object.assign(current, result.wrapping); Object.assign(data.pallets.find(p => p.id === current.id), result.wrapping);
      dirtyKeys.delete(rowKey); dirty=dirtyKeys.size>0; drawCards();
      if (current.completed_at) {
        dirtyKeys.clear(); dirty=false; current=null; lines.replaceChildren();
        detail.close(); finished=true;
      }
    } catch (error) { dirtyKeys.add(rowKey); dirty=true; message(error.message,true,true); }
    finally { busy = false; controls(); }
    if (finished) load();
  }
  async function closeDetail() {
    if (!await mayLeave()) return;
    dirtyKeys.clear(); dirty=false; current=null; lines.replaceChildren(); detail.close();
  }
  document.getElementById('wrappingClose').addEventListener('click', closeDetail);
  detail.addEventListener('cancel', event => { event.preventDefault(); closeDetail(); });
  window.addEventListener('beforeunload', event => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } });
  setInterval(() => { if (!document.hidden && !detail.open && !busy && !dirty) load(); }, 30000);
  load();
})();
