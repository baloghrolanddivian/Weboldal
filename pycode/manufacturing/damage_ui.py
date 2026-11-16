"""Shared replacement-queue presentation for both manufacturing renderers."""

import json

from .routes import MANUFACTURING_DAMAGE_COMPLETE_ROUTE, MANUFACTURING_DAMAGE_ROUTE

DAMAGE_VIEW_STYLE = """
    .mfg-damage-toolbar { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px; }
    .mfg-damage-toolbar p { margin:0; color:var(--muted); }
    .mfg-damage-action { min-height:42px; padding:9px 14px; border:1px solid var(--border); border-radius:10px; background:var(--panel-strong); color:var(--text); font:inherit; font-weight:750; cursor:pointer; }
    .mfg-damage-action:disabled { opacity:.5; cursor:wait; }
    .mfg-damage-tick { width:44px; height:44px; padding:0; color:var(--accent); font-size:24px; }
    .mfg-damage-action:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
    .mfg-damage-group { min-width:0; margin:0 0 16px; padding:16px; border:1px solid var(--border); border-radius:14px; background:var(--panel-strong); }
    .mfg-damage-group h3 { margin:0 0 12px; font-size:17px; }
    .mfg-damage-table-wrap { width:100%; overflow:auto; }
    .mfg-damage-table { width:100%; border-collapse:collapse; text-align:left; font-size:14px; }
    .mfg-damage-table th,.mfg-damage-table td { padding:12px; border-bottom:1px solid var(--border); vertical-align:top; }
    .mfg-damage-table th { color:var(--muted); font-size:12px; }
    .mfg-damage-table td { overflow-wrap:anywhere; }
    .mfg-damage-table td:first-child { font-weight:800; }
    .mfg-damage-table td:nth-child(3) { white-space:nowrap; }
    .mfg-damage-table small { display:block; margin-top:5px; color:var(--muted); }
"""


def damage_view_script() -> str:
    script = r"""
      const applyAssemblyDamageView = (view) => {
        for (const item of documents) {
          if (String(item?.key || '') !== 'korpusz_osszekeszites') continue;
          const existing = specialViewForKey(item, 'assembly-damaged');
          if (existing) Object.assign(existing, view);
          else (item.specialViews ||= []).push(view);
        }
      };
      const damageResponse = async (response) => {
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'A sérült alkatrészek listája nem érhető el.');
        applyAssemblyDamageView(result.view);
      };
      let damageRefreshBusy = false;
      const refreshAssemblyDamageView = async () => {
        if (damageRefreshBusy) return;
        damageRefreshBusy = true;
        try {
          await damageResponse(await fetch(__DAMAGE_DATA_ROUTE__, { cache:'no-store' }));
          renderAll();
        } catch (error) { setStatus(error.message, 'is-error'); }
        finally { damageRefreshBusy = false; }
      };
      const renderAssemblyDamageView = (groups) => {
        contentNode.classList.remove('is-split');
        contentNode.classList.add('is-single-column-overview');
        contentNode.innerHTML = `
          <div class="mfg-damage-toolbar"><p>Az összes gyártás sérült darabjegyzéktételei. A sor melletti pipával jelölheted késznek az adott tétel pótlását.</p><button class="mfg-damage-action" type="button" data-assembly-damage-refresh>Frissítés</button></div>
          ${groups.length ? groups.map(group => `
            <section class="mfg-damage-group"><h3>${escapeHtml(group.label)}</h3><div class="mfg-damage-table-wrap"><table class="mfg-damage-table"><thead><tr><th>Cikkszám</th><th>Megnevezés</th><th>Mennyiség</th><th>CON</th><th>Bejelentés</th><th>Kész</th></tr></thead><tbody>
              ${(group.rows || []).map(row => `<tr><td>${escapeHtml(row.part_number || row.name)}</td><td>${escapeHtml(row.detail || '')}</td><td>${escapeHtml(String(row.quantity))} db</td><td>${escapeHtml(row.code)}</td><td>${escapeHtml(new Date(row.reported_at).toLocaleString('hu-HU'))}<small>${escapeHtml(row.reported_by || '')}</small></td><td><button class="mfg-damage-action mfg-damage-tick" type="button" data-assembly-damage-complete="${escapeHtml(row.damage_id)}" aria-label="${escapeHtml('Sor késznek jelölése: ' + (row.part_number || row.name) + ' · ' + row.code)}" title="Sor késznek jelölése"><span aria-hidden="true">✓</span></button></td></tr>`).join('')}
            </tbody></table></div></section>`).join('') : '<div class="mfg-empty"><strong>Nincs összekészítésre váró sérült alkatrész.</strong></div>'}`;
      };
      sectionTabsNode.addEventListener('click', event => {
        if (event.target.closest('[data-view-key="assembly-damaged"]')) void refreshAssemblyDamageView();
      });
      contentNode.addEventListener('click', async event => {
        if (event.target.closest('[data-assembly-damage-refresh]')) { void refreshAssemblyDamageView(); return; }
        const button = event.target.closest('[data-assembly-damage-complete]');
        if (!button || button.disabled) return;
        event.preventDefault();
        event.stopPropagation();
        const reportId = button.getAttribute('data-assembly-damage-complete');
        const row = (specialViewForKey(currentDocument(), 'assembly-damaged')?.sections || [])
          .flatMap(group => group.rows || []).find(item => item.damage_id === reportId);
        if (!row) return;
        const message = ['Késznek jelölöd ezt a sort?', 'Gyártás: ' + row.production_number,
          'CON: ' + row.code, 'Cikkszám: ' + (row.part_number || row.name),
          'Mennyiség: ' + row.quantity + ' db'].join('\n');
        if (!window.confirm(message)) return;
        button.disabled = true;
        try {
          await damageResponse(await fetch(__DAMAGE_COMPLETE_ROUTE__, { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ report_id:reportId }) }));
          setStatus('A sor késznek jelölése mentve.', 'is-success');
          renderAll();
        } catch (error) { button.disabled = false; setStatus(error.message, 'is-error'); }
      });
"""
    return script.replace("__DAMAGE_DATA_ROUTE__", json.dumps(MANUFACTURING_DAMAGE_ROUTE)).replace("__DAMAGE_COMPLETE_ROUTE__", json.dumps(MANUFACTURING_DAMAGE_COMPLETE_ROUTE))
