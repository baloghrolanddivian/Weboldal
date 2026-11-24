(() => {
  const stage = document.getElementById('history').dataset.stage;
  const root = document.getElementById('historyEvents'), status = document.getElementById('historyStatus');
  const el = (tag, text, cls = '') => { const node = document.createElement(tag); node.textContent = text; node.className = cls; return node; };
  const time = value => new Date(value).toLocaleString('hu-HU', {timeZone: 'Europe/Budapest', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
  const size = item => item.strip100 && item.row_group === 'offcutRows' ? '+100 csík' : `${item.width || '–'} × ${item.height || '–'} mm${item.strip100 ? ' · +100' : ''}`;
  const detail = document.getElementById('historyDetail');
  const stages = event => stage === 'szabasz' ? [['Szabva', event.occurred_at], ['Napi gyártás', event.production_day]] : stage === 'foliazo' ? [['Szabva', event.items[0]?.cut_at], ['Élzárva', event.occurred_at]] : [['Szabva', event.items[0]?.cut_at], ['Élzárva', event.items[0]?.edged_at], ['Elpakolva', event.occurred_at]];
  function stamp(label, value) {
    const node = el('time', `${label}: ${value ? (label === 'Napi gyártás' ? value : time(value)) : '–'}`, 'cp-process-time');
    if (value) node.dateTime = value;
    return node;
  }
  function itemRow(item, preview = false) {
    const row = el(preview ? 'span' : 'div', '', preview ? 'fw-item' : 'cp-history-row');
    const description = el('span', `${item.colour} · ${size(item)}`); description.title = description.textContent;
    row.append(description, el('strong', `${item.quantity} db`));
    row.title = `${description.textContent} · ${item.quantity} db${item.rejected ? ` · Selejt: ${item.rejected} db` : ''}`;
    if (!preview && stage === 'foliazo' && item.rejected) row.append(el('small', `Selejt: ${item.rejected} db`));
    return row;
  }
  function openEvent(event) {
    const times = document.getElementById('historyTimes'), lines = document.getElementById('historyLines');
    times.replaceChildren(); lines.replaceChildren();
    for (const [label,value] of stages(event)) times.append(stamp(label,value));
    for (const item of event.items) lines.append(itemRow(item));
    detail.showModal();
  }
  document.getElementById('historyClose').addEventListener('click', () => detail.close());
  async function load() {
    if (detail.open) return;
    try {
      const response = await fetch(`/apps/szabasterv/tortenet?stage=${encodeURIComponent(stage)}`), result = await response.json();
      if (!response.ok || !result.ok) throw new Error();
      if (detail.open) return;
      root.replaceChildren();
      for (const event of result.events) {
        const card = el('article', '', 'cp-card fw-card cp-history-event history-card'); card.dataset.eventId = event.id;
        const button = el('button', '', 'fw-pallet'); button.type = 'button';
        const header = el('span', '', 'fw-card-head');
        stages(event).forEach(([label,value],index) => {
          const timestamp = stamp(label,value); timestamp.title = timestamp.textContent;
          if (!index) { const heading = el('h2', ''); heading.append(timestamp); header.append(heading); }
          else header.append(timestamp);
        });
        button.append(header);
        const preview = el('span', '', 'fw-card-items');
        if (event.items.length) preview.append(itemRow(event.items[0], true));
        button.append(preview);
        if (event.items.length > 1) button.append(el('span', `+ ${event.items.length - 1} további tétel`, 'fw-card-more'));
        button.addEventListener('click', () => openEvent(event)); card.append(button); root.append(card);
      }
      status.textContent = result.events.length ? '' : 'Az elmúlt 14 napban nincs rögzített művelet.';
    } catch (_) { status.textContent = 'A történet nem tölthető be. Az oldal automatikusan újrapróbálkozik.'; }
  }
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  load();
})();
