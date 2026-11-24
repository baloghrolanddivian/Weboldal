(() => {
  const operations = new Set(['korpusz_osszekeszites', 'cnc_furas', 'front_osszekeszites']);
  const rowSelector = '[data-mfg-row],[data-history-row-id]';
  const make = (tag, text, cls = '') => {
    const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;
  };
  const style = make('style', `
    .mfg-part-history{width:min(480px,calc(100% - 32px));max-height:85dvh;overflow:auto;box-sizing:border-box;padding:24px;border:1px solid var(--border,#dce5df);border-radius:18px;background:var(--panel-strong,#fff);color:var(--text,#1b2e24);box-shadow:0 24px 80px #0004;font:inherit}
    .mfg-part-history::backdrop{background:#14271daa;backdrop-filter:blur(3px)}
    .mfg-part-history h2{font-size:1.2rem;margin:0 40px 14px 0}
    .mfg-part-history-close{position:absolute;right:12px;top:10px;min-width:40px;min-height:40px;border:0;border-radius:10px;background:var(--panel,#eef4f0);color:inherit;font:inherit;font-size:1.5rem;cursor:pointer}
    .mfg-part-history p{line-height:1.5;overflow-wrap:anywhere}
    .mfg-part-history dl{margin:20px 0}.mfg-part-history dl>div{margin:8px 0;padding:12px 14px;border:1px solid #dce1e4;border-radius:10px;background:#f1f3f4;color:#58636b}
    .mfg-part-history dl>div[data-awaiting="true"]{border-color:#9bcbaa;background:#e4f4e9;color:#20663b}
    .mfg-part-history dt{font-weight:800}.mfg-part-history dd{margin:5px 0 0;font-variant-numeric:tabular-nums}
    .mfg-part-history-note{font-size:.8rem;color:var(--muted,#65776d)}
    [data-mfg-row],[data-history-row-id]{-webkit-touch-callout:none;user-select:none}
  `);
  document.head.append(style);
  const popup = make('dialog', '', 'mfg-part-history'); popup.id = 'manufacturingPartHistory';
  popup.setAttribute('aria-labelledby', 'manufacturingPartHistoryTitle');
  const close = make('button', '×', 'mfg-part-history-close'); close.type = 'button'; close.setAttribute('aria-label', 'Bezárás');
  const title = make('h2', 'Alkatrész előzményei'); title.id = 'manufacturingPartHistoryTitle';
  const description = make('p', ''), status = make('p', ''), stages = make('dl', '');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const note = make('p', 'Azonos méret és szín alapján, minden nap folyamatban lévő munkáival.', 'mfg-part-history-note');
  popup.append(close, title, description, status, stages, note); document.body.append(popup);
  close.addEventListener('click', () => popup.close());
  let requestId = 0, timer = null, press = null, suppressed = null;
  popup.addEventListener('close', () => { requestId++; });
  const formatTime = value => new Date(value).toLocaleString('hu-HU', {
    timeZone: 'Europe/Budapest', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  });
  async function openHistory(button) {
    const row = findRowById(button.dataset.pantoloParentRowId || button.dataset.rowId || button.dataset.historyRowId);
    if (!row) return;
    const call = ++requestId;
    description.textContent = [row.name, row.color, row.size].filter(Boolean).join(' · ');
    status.textContent = 'Előzmények betöltése…'; stages.replaceChildren(); note.hidden = false;
    if (!popup.open) popup.showModal();
    close.focus();
    try {
      const params = new URLSearchParams({colour: row.color || '', size: row.size || ''});
      const response = await fetch(`/apps/gyartasi-papirok/alkatresz-elozmeny?${params}`, {cache: 'no-store'});
      const result = await response.json();
      if (call !== requestId || !popup.open) return;
      if (!response.ok || !result.ok) throw new Error(result.error || 'Az előzmények nem tölthetők be.');
      const history = result.history;
      status.textContent = '';
      const cut = make('div', ''), cutDetail = make('dd', '');
      cut.append(make('dt', 'Utoljára vágva'), cutDetail);
      if (history.cut_at) {
        const stamp = make('time', formatTime(history.cut_at)); stamp.dateTime = history.cut_at;
        cutDetail.append(stamp, make('span', ` · ${history.cut_quantity} db`));
      } else cutDetail.textContent = 'Nincs rögzített szabási előzmény';
      stages.append(cut);
      for (const [label, field, empty] of [
        ['Szabászatra kiírva', 'cut_planned_quantity', 'Nincs kiírva szabászatra'],
        ['Élzárásra vár', 'awaiting_edge_quantity', 'Nincs élzárásra váró mennyiség'],
        ['Elpakolásra vár', 'awaiting_putaway_quantity', 'Nincs elpakolásra váró mennyiség']
      ]) {
        const entry = make('div', ''), count = history[field] || 0;
        if (field === 'awaiting_edge_quantity' || field === 'awaiting_putaway_quantity') entry.dataset.awaiting = String(count > 0);
        entry.append(make('dt', label), make('dd', count > 0 ? `Igen · ${count} db` : `${empty} · 0 db`));
        stages.append(entry);
      }
    } catch (error) {
      if (call === requestId && popup.open) status.textContent = error.message || 'Az előzmények nem tölthetők be.';
    }
  }
  function targetRow(event) {
    if (!operations.has(String(currentDocument()?.key || ''))) return null;
    if (event.target.closest('input,textarea,select,a,[data-pantolo-expand],[data-sort-key]')) return null;
    return event.target.closest(rowSelector);
  }
  function cancelPress() { clearTimeout(timer); timer = null; press = null; }
  contentNode.addEventListener('pointerdown', event => {
    cancelPress();
    const row = targetRow(event);
    if (!row || !event.isPrimary || event.button !== 0 || popup.open) return;
    suppressed = null;
    press = {row, x: event.clientX, y: event.clientY, id: event.pointerId};
    const operation = currentDocument()?.key;
    timer = setTimeout(() => {
      if (!row.isConnected || currentDocument()?.key !== operation) { cancelPress(); return; }
      suppressed = {row, until: Date.now() + 2000};
      cancelPress(); void openHistory(row);
    }, 600);
  });
  window.addEventListener('pointermove', event => {
    if (press && event.pointerId === press.id && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 12) cancelPress();
  }, {passive: true});
  window.addEventListener('pointerup', cancelPress);
  window.addEventListener('pointercancel', cancelPress);
  window.addEventListener('blur', cancelPress);
  document.addEventListener('scroll', cancelPress, {capture: true, passive: true});
  document.addEventListener('visibilitychange', cancelPress);
  contentNode.addEventListener('click', event => {
    if (suppressed && (popup.open || Date.now() < suppressed.until) && event.target.closest(rowSelector) === suppressed.row) {
      event.preventDefault(); event.stopImmediatePropagation(); suppressed = null;
    }
  }, true);
  contentNode.addEventListener('contextmenu', event => {
    if (targetRow(event)) event.preventDefault();
  });
  contentNode.addEventListener('keydown', event => {
    const row = targetRow(event);
    if (row && (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10'))) {
      event.preventDefault(); cancelPress(); void openHistory(row);
    }
  });
})();
