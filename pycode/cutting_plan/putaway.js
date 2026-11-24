(() => {
  const root = document.getElementById('putawayCards'), empty = document.getElementById('putawayEmpty');
  const status = document.getElementById('putawayStatus');
  let pending = 0, sequence = 0;
  const el = (tag, text, cls = '') => { const node = document.createElement(tag); node.textContent = text; node.className = cls; return node; };
  const size = item => item.strip100 && item.row_group === 'offcutRows' ? '+100 csík' : `${item.width || '–'} × ${item.height || '–'} mm${item.strip100 ? ' · +100' : ''}`;
  const time = value => new Date(value).toLocaleString('hu-HU', {timeZone: 'Europe/Budapest', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  function processTimes(container, pallet) {
    for (const [label, value] of [['Szabva', pallet.sent_at], ['Élzárva', pallet.completed_at]]) {
      const stamp = el('time', `${label}: ${value ? time(value) : '–'}`, 'cp-process-time');
      if (value) stamp.dateTime = value;
      container.append(stamp);
    }
  }
  async function request(url, options) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Sikertelen mentés. Próbáld újra.');
    return result;
  }
  const detail = document.getElementById('putawayDetail'), lines = document.getElementById('putawayLines');
  const checkbox = document.getElementById('putawayCheck'), error = document.getElementById('putawayError');
  const close = document.getElementById('putawayClose');
  let current = null;
  function contents(container, pallet, tag = 'div', limit = Infinity) {
    for (const item of pallet.allocations.slice(0, limit)) {
      const key = JSON.stringify([item.plan_id, item.row_group, item.row_id]);
      const description = `${item.colour} · ${size(item)}`, quantity = pallet.wrapping_quantities[key];
      const row = el(tag, '', 'fw-item'); row.dataset.key = key; row.dataset.stored = String((pallet.putaway_items || []).includes(key)); row.title = `${description} · ${quantity} db`;
      row.append(el('span', description), el('strong', `${quantity} db`));
      if (container === lines) {
        const label = el('label', '', 'pa-done'), input = document.createElement('input'); input.type = 'checkbox'; input.dataset.key = key;
        input.setAttribute('aria-label', `${description} elpakolva`);
        label.append(input, el('span', 'Elpakolva')); row.append(label);
        input.addEventListener('change', () => { if (input.checked) save([key]); });
      }
      container.append(row);
    }
  }
  function draw(pallets) {
    root.replaceChildren(); empty.hidden = pallets.length > 0;
    for (const pallet of pallets) {
      const card = el('article', '', 'cp-card fw-card pa-card'); card.dataset.palletId = pallet.id;
      const button = el('button', '', 'fw-pallet'); button.type = 'button';
      const header = el('span', '', 'fw-card-head');
      const heading = el('h2', `Szabva: ${pallet.sent_date} ${pallet.sent_time}`); heading.title = heading.textContent; header.append(heading);
      const edged = el('time', `Élzárva: ${time(pallet.completed_at)}`, 'cp-process-time'); edged.dateTime = pallet.completed_at; header.append(edged); button.append(header);
      const preview = el('span', '', 'fw-card-items'); contents(preview, pallet, 'span', 1); button.append(preview);
      if (pallet.allocations.length > 1) button.append(el('span', `+ ${pallet.allocations.length - 1} további tétel`, 'fw-card-more'));
      card.append(button); root.append(card);
      button.addEventListener('click', () => {
        current = {pallet, card}; lines.replaceChildren(); processTimes(lines, pallet); contents(lines, pallet);
        checkbox.checked = false; error.textContent = ''; updateControls(); detail.showModal(); (lines.querySelector('input:not(:disabled)') || checkbox).focus();
      });
    }
  }
  function closeDetail() { if (!pending) { detail.close(); current = null; } }
  close.addEventListener('click', closeDetail);
  detail.addEventListener('cancel', event => { event.preventDefault(); closeDetail(); });
  function updateControls() {
    close.disabled = checkbox.disabled = !!pending;
    if (!current) return;
    const stored = new Set(current.pallet.putaway_items || []);
    for (const input of lines.querySelectorAll('input[data-key]')) {
      input.checked = stored.has(input.dataset.key); input.disabled = !!pending || input.checked;
    }
    for (const row of [...lines.querySelectorAll('.fw-item'), ...current.card.querySelectorAll('.fw-item')]) row.dataset.stored = String(stored.has(row.dataset.key));
  }
  async function save(items) {
    if (pending || !current) return;
    pending++; sequence++; updateControls(); error.textContent = '';
    try {
      const result = await request('/apps/szabasterv/elpakolas', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'Divian-HUB'}, body: JSON.stringify({id: current.pallet.id, items})});
      current.pallet.putaway_items = result.putaway.items;
      if (result.putaway.stored_at) {
        current.card.remove(); empty.hidden = root.childElementCount > 0;
        detail.close(); current = null;
      }
    } catch (failure) { error.textContent = failure.message; }
    finally { pending--; checkbox.checked = false; updateControls(); }
  }
  checkbox.addEventListener('change', () => {
    if (checkbox.checked && current) save(current.pallet.allocations.map(item => JSON.stringify([item.plan_id, item.row_group, item.row_id])));
  });
  async function load() {
    if (pending || detail.open) return;
    const call = ++sequence;
    try {
      const result = await request('/apps/szabasterv/elpakolasra-var');
      if (call !== sequence || pending || detail.open) return;
      draw(result.pallets); status.textContent = '';
    } catch (_) { if (call === sequence) status.textContent = 'A raklapok nem tölthetők be. A lista automatikusan újrapróbálkozik.'; }
  }
  window.addEventListener('beforeunload', event => { if (pending) { event.preventDefault(); event.returnValue = ''; } });
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  load();
})();
