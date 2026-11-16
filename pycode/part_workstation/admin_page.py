"""Production-wide note editor for assembly administrators."""

from __future__ import annotations

import html

from .page import ADMIN_DATA_ROUTE, ADMIN_SAVE_ROUTE, ROUTE


def render_admin_page(user_name: str) -> bytes:
    page = """<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Összeszerelés · Megjegyzések kezelése</title>
  <link rel="stylesheet" href="/styles.css" />
  <style>
    * { box-sizing:border-box; }
    html { min-height:100%; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:Inter,system-ui,sans-serif; }
    body.assembly-admin { display:flow-root; min-height:100vh; min-height:100dvh; color-scheme:dark; }
    button,input,textarea { font:inherit; }
    .notes-admin { width:min(1400px,calc(100% - 32px)); min-width:0; margin:24px auto; display:grid; gap:18px; }
    .notes-header,.notes-controls,.notes-board { min-width:0; padding:22px; border:1px solid var(--border); border-radius:18px; background:var(--panel-strong); }
    .notes-header { display:flex; align-items:center; justify-content:space-between; gap:18px; }
    .notes-header small { color:var(--muted); }
    h1 { margin:5px 0; font-size:clamp(22px,3vw,32px); }
    .notes-header p { margin:8px 0 0; color:var(--muted); }
    .notes-button { display:inline-flex; align-items:center; justify-content:center; min-height:44px; padding:10px 16px; border:1px solid var(--border); border-radius:10px; background:var(--panel-soft); color:var(--text); font-weight:750; text-decoration:none; cursor:pointer; }
    .notes-button.primary { background:var(--accent); color:var(--bg); border-color:var(--accent); }
    button:disabled { opacity:.5; cursor:default; }
    .notes-controls form { display:flex; flex-wrap:wrap; align-items:end; gap:12px; }
    .notes-controls label { display:grid; gap:7px; font-size:13px; font-weight:750; }
    .notes-controls input { width:220px; max-width:100%; min-height:44px; padding:10px 12px; border:1px solid var(--border); border-radius:10px; background:var(--bg); color:var(--text); }
    #notesStatus { margin:14px 0 0; color:var(--muted); line-height:1.45; }
    #notesStatus[data-error="true"] { color:#f87171; }
    .notes-toolbar { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:14px; margin-bottom:16px; }
    .notes-toolbar h2 { margin:0 0 5px; font-size:20px; }
    .notes-toolbar p { margin:0; color:var(--muted); font-size:13px; }
    .notes-actions { display:flex; flex-wrap:wrap; gap:10px; }
    .notes-filters { display:flex; flex-wrap:wrap; align-items:end; gap:12px 20px; margin-bottom:16px; }
    .notes-search { display:grid; gap:7px; min-width:0; max-width:100%; font-size:13px; font-weight:750; }
    .notes-search input { width:280px; max-width:100%; min-height:44px; padding:10px 12px; border:1px solid var(--border); border-radius:10px; background:var(--bg); color:var(--text); }
    .notes-egk { display:flex; align-items:center; gap:9px; min-height:44px; font-size:14px; cursor:pointer; }
    .notes-egk input { width:20px; height:20px; margin:0; accent-color:var(--accent); }
    #filteredCount { align-self:center; color:var(--muted); font-size:13px; }
    .notes-table-wrap { width:100%; min-width:0; overflow:auto; }
    .notes-table { width:100%; border-collapse:collapse; text-align:left; }
    .notes-table th { padding:12px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
    .notes-table th:first-child { width:190px; }
    .notes-table th:nth-child(2) { width:210px; }
    .notes-table td { padding:12px; border-bottom:1px solid var(--line); vertical-align:top; overflow-wrap:anywhere; }
    .notes-table td:first-child { font-weight:750; }
    .notes-table textarea { width:100%; min-width:240px; min-height:70px; padding:10px 12px; resize:vertical; border:1px solid var(--border); border-radius:9px; color:var(--text); background:var(--bg); line-height:1.45; }
    .notes-table textarea.has-note { border-color:#ef4444; box-shadow:0 0 0 2px #ef4444; }
    .notes-table tr.is-edited textarea { border-color:var(--accent); }
    .notes-table textarea:focus-visible,input:focus-visible,.notes-button:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
    #notesEmpty,#notesNoMatches { color:var(--muted); }
    [hidden] { display:none !important; }
    @media(max-width:700px) { .notes-admin { width:calc(100% - 16px); margin:8px auto; gap:10px; } .notes-header,.notes-controls,.notes-board { padding:15px; } .notes-header { align-items:flex-start; flex-direction:column; } .notes-table th:first-child { min-width:140px; } .notes-table th:nth-child(2) { min-width:140px; } }
  </style>
</head>
<body class="assembly-admin">
  <main class="notes-admin">
    <header class="notes-header"><div><small>Összeszerelés · Admin · __USER__</small><h1>Megjegyzések kezelése</h1><p>Nyisd meg a gyártást, majd szerkeszd az elemek megjegyzéseit.</p></div><a class="notes-button" href="__MODULE_ROUTE__">Vissza az összeszereléshez</a></header>
    <section class="notes-controls" aria-label="Gyártás megnyitása">
      <form id="productionForm"><label>Gyártási azonosító (prdID)<input id="productionInput" name="production_id" inputmode="numeric" pattern="[0-9]+" maxlength="20" required autocomplete="off" /></label><button class="notes-button primary" id="loadButton" type="submit">Gyártás megnyitása</button></form>
      <p id="notesStatus" role="status" aria-live="polite">Adj meg egy gyártási azonosítót.</p>
    </section>
    <section class="notes-board" id="notesBoard" aria-label="Gyártási megjegyzések" hidden>
      <div class="notes-toolbar"><div><h2 id="productionTitle"></h2><p><span id="itemCount">0</span> elem · <span id="changedCount">0</span> módosítás</p></div><div class="notes-actions"><button class="notes-button" id="discardButton" type="button" disabled>Változtatások elvetése</button><button class="notes-button primary" id="saveButton" type="button" disabled>Módosítások mentése</button></div></div>
      <div class="notes-filters"><label class="notes-search">CONID keresése<input id="conSearchInput" type="search" placeholder="CON azonosító vagy részlet" maxlength="160" autocomplete="off" aria-controls="notesBody" /></label><label class="notes-egk"><input id="egkOnly" type="checkbox" aria-controls="notesBody" />Csak EGK cikkszám</label><button class="notes-button" id="clearFiltersButton" type="button" hidden>Szűrők törlése</button><span id="filteredCount" role="status" aria-live="polite"></span></div>
      <div class="notes-table-wrap"><table class="notes-table"><thead><tr><th scope="col">CONID</th><th scope="col">Cikkszám</th><th scope="col">Megjegyzés</th></tr></thead><tbody id="notesBody"></tbody></table></div>
      <p id="notesEmpty" hidden>A gyártásban nincs megjeleníthető elem.</p>
      <p id="notesNoMatches" hidden>Nincs a szűrőknek megfelelő elem.</p>
    </section>
  </main>
  <script>
    const productionForm = document.getElementById('productionForm');
    const productionInput = document.getElementById('productionInput');
    const loadButton = document.getElementById('loadButton');
    const saveButton = document.getElementById('saveButton');
    const discardButton = document.getElementById('discardButton');
    const notesBody = document.getElementById('notesBody');
    const notesStatus = document.getElementById('notesStatus');
    const conSearchInput = document.getElementById('conSearchInput');
    const egkOnly = document.getElementById('egkOnly');
    const clearFiltersButton = document.getElementById('clearFiltersButton');
    let production = null;
    let busy = false;
    const changes = new Map();

    function status(message, error = false) {
      notesStatus.textContent = message;
      notesStatus.dataset.error = String(error);
    }
    function updateControls() {
      document.getElementById('changedCount').textContent = changes.size;
      loadButton.disabled = busy;
      productionInput.disabled = busy;
      saveButton.disabled = busy || !changes.size;
      discardButton.disabled = busy || !changes.size;
      conSearchInput.disabled = busy;
      egkOnly.disabled = busy;
      clearFiltersButton.disabled = busy;
      notesBody.querySelectorAll('textarea').forEach(input => { input.disabled = busy; });
      document.getElementById('notesBoard').setAttribute('aria-busy', String(busy));
    }
    function applyFilters() {
      const query = conSearchInput.value.trim().toUpperCase();
      let visible = 0;
      for (const row of notesBody.rows) {
        row.hidden = !row.dataset.conId.toUpperCase().includes(query)
          || (egkOnly.checked && row.dataset.partNumber.trim().toUpperCase() !== 'EGK');
        if (!row.hidden) visible++;
      }
      const total = production?.items.length || 0;
      document.getElementById('filteredCount').textContent = visible + ' / ' + total + ' elem';
      document.getElementById('notesNoMatches').hidden = !total || visible > 0;
      clearFiltersButton.hidden = !conSearchInput.value && !egkOnly.checked;
    }
    conSearchInput.addEventListener('input', applyFilters);
    egkOnly.addEventListener('change', applyFilters);
    clearFiltersButton.addEventListener('click', () => {
      conSearchInput.value = '';
      egkOnly.checked = false;
      applyFilters();
      conSearchInput.focus();
    });
    function renderProduction(data) {
      if (production?.production_id !== data.production_id) {
        conSearchInput.value = '';
        egkOnly.checked = false;
      }
      production = data;
      changes.clear();
      notesBody.replaceChildren();
      document.getElementById('notesBoard').hidden = false;
      document.getElementById('productionTitle').textContent = 'Gyártás: ' + data.production_id;
      document.getElementById('itemCount').textContent = data.items.length;
      document.getElementById('notesEmpty').hidden = data.items.length > 0;
      data.items.forEach(item => {
        const row = document.createElement('tr');
        row.dataset.conId = String(item.con_id || '');
        row.dataset.partNumber = String(item.part_number || '');
        for (const value of [item.con_id, item.part_number]) {
          const cell = document.createElement('td');
          cell.textContent = value || '—';
          row.appendChild(cell);
        }
        const cell = document.createElement('td');
        const input = document.createElement('textarea');
        input.rows = 2;
        input.maxLength = 500;
        input.value = item.notes;
        input.classList.toggle('has-note', Boolean(input.value.trim()));
        input.dataset.rowId = item.row_id;
        input.setAttribute('aria-label', 'Megjegyzés: ' + (item.con_id || item.part_number || 'Elem ' + item.row_id));
        input.addEventListener('input', () => {
          input.classList.toggle('has-note', Boolean(input.value.trim()));
          if (input.value === item.notes) changes.delete(item.row_id);
          else changes.set(item.row_id, input.value);
          row.classList.toggle('is-edited', changes.has(item.row_id));
          updateControls();
        });
        cell.appendChild(input);
        row.appendChild(cell);
        notesBody.appendChild(row);
      });
      applyFilters();
      updateControls();
    }
    async function request(url, options) {
      const response = await fetch(url, options);
      const data = await response.json().catch(() => ({ ok:false, error:'Érvénytelen szerverválasz. Nyisd meg újra az oldalt.' }));
      if (!response.ok || !data.ok) throw new Error(data.error || 'A művelet nem sikerült.');
      return data.production;
    }
    productionForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      if (changes.size && !window.confirm('A nem mentett megjegyzések elvesznek. Megnyitod a gyártást?')) return;
      const number = productionInput.value.trim();
      if (!/^[0-9]{1,20}$/.test(number)) { status('Érvénytelen gyártási azonosító.', true); return; }
      busy = true;
      updateControls();
      status('Gyártás betöltése…');
      try {
        renderProduction(await request('__DATA_ROUTE__?production_id=' + encodeURIComponent(number)));
        status('A gyártás betöltve. A megjegyzés nélküli sorok is szerkeszthetők.');
      } catch (error) { status(error.message, true); }
      finally { busy = false; updateControls(); }
    });
    saveButton.addEventListener('click', async () => {
      if (busy || !production || !changes.size) return;
      const payload = { production_id:production.production_id, revision:production.revision,
        changes:[...changes].map(([row_id, notes]) => ({ row_id, notes })) };
      busy = true;
      updateControls();
      status('Megjegyzések mentése…');
      try {
        renderProduction(await request('__SAVE_ROUTE__', { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify(payload) }));
        status('A megjegyzések mentve a gyártás eredeti fájljába.');
      } catch (error) { status(error.message, true); }
      finally { busy = false; updateControls(); }
    });
    discardButton.addEventListener('click', () => {
      if (busy || !production) return;
      renderProduction(production);
      status('A nem mentett módosításokat elvetetted.');
    });
    window.addEventListener('beforeunload', event => {
      if (!changes.size) return;
      event.preventDefault();
      event.returnValue = '';
    });
  </script>
</body>
</html>"""
    page = page.replace("__MODULE_ROUTE__", ROUTE).replace("__DATA_ROUTE__", ADMIN_DATA_ROUTE).replace("__SAVE_ROUTE__", ADMIN_SAVE_ROUTE)
    return page.replace("__USER__", html.escape(str(user_name or "Admin"))).encode("utf-8")
