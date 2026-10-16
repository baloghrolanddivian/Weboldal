"""Single-screen landscape tablet UI for scanned production parts."""

from __future__ import annotations

import html
import json


ROUTE = "/apps/alkatresz-munkalap"
SCAN_ROUTE = f"{ROUTE}/beolvasas"
RESET_ROUTE = f"{ROUTE}/alaphelyzet"
ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo", "hriroda"})


def render_page(state: dict, user_name: str) -> bytes:
    """Render the complete no-scroll tablet workstation."""
    safe_user = html.escape(str(user_name or "Felhasználó"))
    initial_state = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#07111f" />
  <title>Alkatrész munkalap · Divian-HUB</title>
  <style>
    :root {{ color-scheme: dark; --ink:#f8fafc; --muted:#94a3b8; --line:rgba(148,163,184,.2); --panel:#0d1929; --panel2:#111f31; --green:#37e6a1; --blue:#5eb6ff; --amber:#ffca5c; }}
    * {{ box-sizing:border-box; }}
    html, body {{ width:100%; height:100%; margin:0; overflow:hidden; }}
    body {{ font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; background:#07111f; color:var(--ink); }}
    button, input {{ font:inherit; }}
    .app {{ height:100dvh; min-height:0; display:grid; grid-template-rows:72px minmax(0,1fr); background:radial-gradient(circle at 25% 0%,rgba(37,99,235,.14),transparent 32%),#07111f; }}
    .topbar {{ min-width:0; display:grid; grid-template-columns:minmax(210px,1fr) minmax(300px,560px) minmax(210px,1fr); align-items:center; gap:16px; padding:10px 18px; border-bottom:1px solid var(--line); background:rgba(7,17,31,.92); }}
    .brand {{ display:flex; align-items:center; gap:11px; min-width:0; }}
    .brand-mark {{ width:42px; height:42px; display:grid; place-items:center; border-radius:13px; color:#062419; background:var(--green); font-weight:950; letter-spacing:-.06em; box-shadow:0 0 30px rgba(55,230,161,.2); }}
    .brand small,.brand strong {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .brand small {{ color:var(--muted); font-size:11px; letter-spacing:.12em; text-transform:uppercase; }}
    .brand strong {{ font-size:17px; }}
    .scan-form {{ height:48px; display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px; padding:5px 6px 5px 14px; border:1px solid rgba(94,182,255,.42); border-radius:15px; background:#0b1727; box-shadow:0 0 0 3px rgba(94,182,255,.05); }}
    .scan-form:focus-within {{ border-color:var(--green); box-shadow:0 0 0 3px rgba(55,230,161,.1); }}
    .scan-pulse {{ width:10px; height:10px; border-radius:50%; background:var(--green); box-shadow:0 0 0 5px rgba(55,230,161,.11); }}
    .scan-input {{ min-width:0; border:0; outline:0; color:var(--ink); background:transparent; font-size:17px; font-weight:750; letter-spacing:.035em; }}
    .scan-input::placeholder {{ color:#7890aa; font-weight:550; letter-spacing:0; }}
    .scan-submit,.reset-button {{ border:0; cursor:pointer; font-weight:850; }}
    .scan-submit {{ align-self:stretch; padding:0 17px; border-radius:11px; color:#062419; background:var(--green); }}
    .user-area {{ min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:10px; }}
    .user-copy {{ min-width:0; text-align:right; }} .user-copy small,.user-copy strong {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .user-copy small {{ color:var(--muted); font-size:11px; }} .user-copy strong {{ font-size:14px; }}
    .reset-button {{ padding:9px 12px; border:1px solid var(--line); border-radius:10px; color:#cbd5e1; background:#101d2d; }}
    .workspace {{ min-height:0; display:grid; grid-template-columns:1fr 1fr; gap:10px; padding:10px; }}
    .left-column {{ min-width:0; min-height:0; display:grid; grid-template-rows:1fr 1fr; gap:10px; }}
    .panel {{ min-width:0; min-height:0; overflow:hidden; border:1px solid var(--line); border-radius:18px; background:linear-gradient(145deg,rgba(17,31,49,.98),rgba(10,22,37,.98)); box-shadow:0 18px 45px rgba(0,0,0,.17); }}
    .panel-head {{ height:49px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-bottom:1px solid var(--line); }}
    .panel-title {{ display:flex; align-items:center; gap:9px; font-size:13px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
    .panel-index {{ color:var(--green); }}
    .status {{ display:inline-flex; align-items:center; gap:7px; max-width:55%; padding:6px 9px; border:1px solid rgba(255,202,92,.25); border-radius:999px; color:var(--amber); background:rgba(255,202,92,.07); font-size:11px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .status::before {{ content:""; width:6px; height:6px; flex:0 0 auto; border-radius:50%; background:currentColor; }}
    .model-stage {{ position:relative; height:calc(100% - 49px); display:grid; place-items:center; padding:8px 24px 10px; background:linear-gradient(rgba(94,182,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(94,182,255,.035) 1px,transparent 1px); background-size:26px 26px; }}
    .model-stage::after {{ content:""; position:absolute; left:12%; right:12%; bottom:12%; height:16%; border-radius:50%; background:rgba(0,0,0,.35); filter:blur(18px); }}
    .part-svg {{ position:relative; z-index:1; width:min(90%,520px); height:100%; max-height:265px; filter:drop-shadow(0 20px 18px rgba(0,0,0,.28)); }}
    .part-face {{ fill:#203a50; stroke:#76c8ff; stroke-width:2; }} .part-side {{ fill:#142b3d; stroke:#4e95c6; stroke-width:2; }} .part-top {{ fill:#2b526c; stroke:#8ed5ff; stroke-width:2; }}
    .dimension {{ stroke:#58e1ad; stroke-width:1.4; stroke-dasharray:5 5; }} .dimension-text {{ fill:#78efbd; font-size:13px; font-weight:800; }}
    .model-watermark {{ position:absolute; z-index:2; right:14px; bottom:10px; color:#64748b; font-size:10px; letter-spacing:.08em; text-transform:uppercase; }}
    .info-body {{ height:calc(100% - 49px); display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); grid-auto-rows:1fr; gap:7px; padding:9px; }}
    .datum {{ min-width:0; padding:9px 11px; border:1px solid rgba(148,163,184,.14); border-radius:11px; background:rgba(5,14,25,.32); }}
    .datum.wide {{ grid-column:span 2; }} .datum label {{ display:block; margin-bottom:4px; color:var(--muted); font-size:9px; font-weight:850; letter-spacing:.1em; text-transform:uppercase; }}
    .datum output {{ display:block; overflow:hidden; color:#eaf2fa; font-size:13px; font-weight:750; white-space:nowrap; text-overflow:ellipsis; }} .datum output.pending {{ color:#7f94aa; font-weight:550; }}
    .bom-panel {{ display:grid; grid-template-rows:49px minmax(0,1fr) 50px; }}
    .bom-count {{ min-width:28px; padding:5px 8px; border-radius:9px; color:#062419; background:var(--green); font-size:12px; font-weight:950; text-align:center; }}
    .bom-wrap {{ min-height:0; position:relative; overflow:hidden; padding:9px 12px; }}
    .bom-table {{ width:100%; border-collapse:separate; border-spacing:0 5px; table-layout:fixed; }}
    .bom-table th {{ padding:0 10px 5px; color:#7890aa; font-size:9px; letter-spacing:.1em; text-align:left; text-transform:uppercase; }}
    .bom-table th:nth-child(1) {{ width:46px; }} .bom-table th:nth-child(3) {{ width:90px; text-align:center; }} .bom-table th:nth-child(4) {{ width:78px; }}
    .bom-table td {{ height:43px; padding:7px 10px; border-top:1px solid rgba(148,163,184,.12); border-bottom:1px solid rgba(148,163,184,.12); background:rgba(5,14,25,.34); font-size:12px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
    .bom-table td:first-child {{ border-left:1px solid rgba(148,163,184,.12); border-radius:10px 0 0 10px; color:var(--muted); }} .bom-table td:last-child {{ border-right:1px solid rgba(148,163,184,.12); border-radius:0 10px 10px 0; }}
    .bom-table td:nth-child(3) {{ text-align:center; font-weight:900; }}
    .empty-bom {{ position:absolute; inset:38px 12px 10px; display:grid; place-items:center; text-align:center; pointer-events:none; }}
    .empty-icon {{ width:62px; height:62px; display:grid; place-items:center; margin:0 auto 10px; border:1px solid rgba(94,182,255,.25); border-radius:18px; color:var(--blue); background:rgba(94,182,255,.06); font-size:28px; }}
    .empty-bom strong {{ display:block; margin-bottom:5px; font-size:17px; }} .empty-bom p {{ max-width:360px; margin:0; color:var(--muted); font-size:12px; line-height:1.45; }}
    .bom-footer {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; }}
    .api-state {{ color:var(--amber); font-weight:800; }}
    .toast {{ position:fixed; z-index:20; left:50%; top:82px; transform:translate(-50%,-16px); padding:10px 14px; border:1px solid rgba(248,113,113,.36); border-radius:11px; color:#fecaca; background:#33131b; opacity:0; pointer-events:none; transition:.2s; }} .toast.show {{ opacity:1; transform:translate(-50%,0); }}
    .rotate {{ display:none; }}
    @media (orientation:portrait) {{ .rotate {{ position:fixed; z-index:100; inset:0; display:grid; place-items:center; padding:34px; text-align:center; background:#07111f; }} .rotate div {{ max-width:420px; }} .rotate b {{ display:block; margin-bottom:10px; font-size:48px; }} .rotate strong {{ display:block; margin-bottom:7px; font-size:23px; }} .rotate p {{ margin:0; color:var(--muted); }} }}
    @media (max-height:680px) and (orientation:landscape) {{ .app {{ grid-template-rows:62px minmax(0,1fr); }} .topbar {{ padding:7px 14px; }} .brand-mark {{ width:38px;height:38px; }} .workspace {{ gap:7px;padding:7px; }} .left-column {{ gap:7px; }} .panel {{ border-radius:14px; }} .panel-head {{ height:43px; }} .model-stage,.info-body {{ height:calc(100% - 43px); }} .bom-panel {{ grid-template-rows:43px minmax(0,1fr) 43px; }} .bom-table td {{ height:36px; }} }}
  </style>
</head>
<body data-theme-scope="default">
  <main class="app">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">D</span><span><small>Digitális gyártás</small><strong>Alkatrész munkalap</strong></span></div>
      <form class="scan-form" id="scanForm" autocomplete="off"><i class="scan-pulse"></i><input class="scan-input" id="scanInput" maxlength="160" aria-label="Vonalkód" placeholder="Csippantsd be a vonalkódot…" autofocus /><button class="scan-submit" type="submit">Beolvasás</button></form>
      <div class="user-area"><span class="user-copy"><small>Saját munkamenet</small><strong>{safe_user}</strong></span><button class="reset-button" id="resetButton" type="button">Új elem</button></div>
    </header>
    <section class="workspace" aria-label="Alkatrész munkaterület">
      <div class="left-column">
        <article class="panel">
          <header class="panel-head"><div class="panel-title"><span class="panel-index">01</span> 3D elemnézet</div><span class="status" id="modelStatus">Beolvasásra vár</span></header>
          <div class="model-stage">
            <svg class="part-svg" viewBox="0 0 560 270" role="img" aria-label="Az elem sematikus 3D előnézete">
              <line class="dimension" x1="94" y1="241" x2="447" y2="241"/><line class="dimension" x1="94" y1="234" x2="94" y2="248"/><line class="dimension" x1="447" y1="234" x2="447" y2="248"/><text class="dimension-text" x="248" y="261" id="modelWidth">— mm</text>
              <polygon class="part-side" points="430,52 469,73 469,205 430,218"/><polygon class="part-top" points="119,62 158,42 469,73 430,89"/><polygon class="part-face" points="119,62 430,89 430,218 119,191"/>
              <circle cx="151" cy="91" r="6" fill="#07111f" stroke="#76c8ff"/><circle cx="151" cy="166" r="6" fill="#07111f" stroke="#76c8ff"/><circle cx="397" cy="112" r="6" fill="#07111f" stroke="#76c8ff"/><circle cx="397" cy="187" r="6" fill="#07111f" stroke="#76c8ff"/>
              <path d="M182 103l171 15v54l-171-15z" fill="rgba(94,182,255,.08)" stroke="rgba(118,200,255,.45)" stroke-dasharray="5 5"/>
            </svg>
            <span class="model-watermark" id="modelWatermark">Sematikus előnézet · API-modellre előkészítve</span>
          </div>
        </article>
        <article class="panel">
          <header class="panel-head"><div class="panel-title"><span class="panel-index">02</span> Beolvasott elem adatai</div><span class="status" id="scanStatus">Scanner készen áll</span></header>
          <div class="info-body">
            <div class="datum wide"><label>Vonalkód</label><output id="barcode">Még nincs beolvasott kód</output></div>
            <div class="datum"><label>Beolvasás ideje</label><output id="scannedAt">—</output></div>
            <div class="datum"><label>Cikkszám</label><output class="pending" data-item="part_number">—</output></div>
            <div class="datum wide"><label>Megnevezés</label><output class="pending" data-item="description">API-kapcsolatra vár</output></div>
            <div class="datum"><label>Méret</label><output class="pending" data-item="dimensions">—</output></div>
            <div class="datum"><label>Anyag</label><output class="pending" data-item="material">—</output></div>
            <div class="datum"><label>Szín / dekor</label><output class="pending" data-item="color">—</output></div>
            <div class="datum"><label>Gyártási szám</label><output class="pending" data-item="production_number">—</output></div>
            <div class="datum"><label>Rendelésszám</label><output class="pending" data-item="order_number">—</output></div>
            <div class="datum"><label>Adatállapot</label><output class="pending" id="lookupState">Beolvasásra vár</output></div>
          </div>
        </article>
      </div>
      <article class="panel bom-panel">
        <header class="panel-head"><div class="panel-title"><span class="panel-index">03</span> Darabjegyzék</div><span class="bom-count" id="bomCount">0</span></header>
        <div class="bom-wrap">
          <table class="bom-table"><thead><tr><th>#</th><th>Megnevezés / cikkszám</th><th>Mennyiség</th><th>Egység</th></tr></thead><tbody id="bomBody"></tbody></table>
          <div class="empty-bom" id="emptyBom"><div><span class="empty-icon">≡</span><strong id="emptyBomTitle">Nincs beolvasott elem</strong><p id="emptyBomText">A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.</p></div></div>
        </div>
        <footer class="bom-footer"><span>A lista az elem API-válaszából töltődik majd.</span><span class="api-state" id="apiState">API: nincs bekötve</span></footer>
      </article>
    </section>
  </main>
  <div class="toast" id="toast" role="alert"></div>
  <div class="rotate"><div><b>↻</b><strong>Fordítsd fekvő helyzetbe a táblagépet</strong><p>Ez a munkafelület fekvő nézetre és egyetlen, görgetésmentes képernyőre készült.</p></div></div>
  <script>
    const initialState = {initial_state};
    const scanForm = document.getElementById('scanForm');
    const scanInput = document.getElementById('scanInput');
    const resetButton = document.getElementById('resetButton');
    const toast = document.getElementById('toast');
    let toastTimer;

    function valueOrPending(value, fallback = '—') {{ return value ? String(value) : fallback; }}
    function formatDate(value) {{
      if (!value) return '—';
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('hu-HU', {{ hour:'2-digit', minute:'2-digit', second:'2-digit' }});
    }}
    function showToast(message) {{ toast.textContent = message; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 3200); }}
    function renderBom(rows) {{
      const body = document.getElementById('bomBody');
      body.replaceChildren();
      rows.slice(0, 9).forEach((row, index) => {{
        const tr = document.createElement('tr');
        [index + 1, row.description || row.part_number || '—', row.quantity || '—', row.unit || 'db'].forEach(value => {{ const td = document.createElement('td'); td.textContent = value; tr.appendChild(td); }});
        body.appendChild(tr);
      }});
      document.getElementById('bomCount').textContent = rows.length;
      document.getElementById('emptyBom').hidden = rows.length > 0;
    }}
    function renderState(state) {{
      const hasScan = Boolean(state.barcode);
      const pending = state.lookup_status === 'api_pending';
      document.getElementById('barcode').textContent = hasScan ? state.barcode : 'Még nincs beolvasott kód';
      document.getElementById('scannedAt').textContent = formatDate(state.scanned_at);
      document.getElementById('modelStatus').textContent = pending ? 'API-modellre vár' : (hasScan ? 'Modell betöltve' : 'Beolvasásra vár');
      document.getElementById('scanStatus').textContent = pending ? 'Kód beolvasva' : 'Scanner készen áll';
      document.getElementById('apiState').textContent = pending ? 'API: kapcsolatra vár' : (state.lookup_status === 'ready' ? 'API: adatok betöltve' : 'API: nincs bekötve');
      document.getElementById('lookupState').textContent = pending ? 'API-kapcsolatra vár' : (state.lookup_status === 'ready' ? 'Adatok betöltve' : 'Beolvasásra vár');
      document.getElementById('emptyBomTitle').textContent = pending ? 'A kód sikeresen beolvasva' : 'Nincs beolvasott elem';
      document.getElementById('emptyBomText').textContent = pending ? 'A darabjegyzék a későbbi API-kapcsolat válaszából automatikusan ide töltődik.' : 'A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.';
      document.querySelectorAll('[data-item]').forEach(output => {{
        const value = state.item && state.item[output.dataset.item];
        output.textContent = valueOrPending(value, output.dataset.item === 'description' && pending ? 'API-kapcsolatra vár' : '—');
        output.classList.toggle('pending', !value);
      }});
      document.getElementById('modelWidth').textContent = state.item && state.item.dimensions ? state.item.dimensions : '— mm';
      renderBom(Array.isArray(state.bom) ? state.bom : []);
    }}
    async function send(url, payload) {{
      const response = await fetch(url, {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload || {{}}) }});
      const data = await response.json().catch(() => ({{ ok:false, error:'Érvénytelen szerverválasz.' }}));
      if (!response.ok || !data.ok) throw new Error(data.error || 'A művelet nem sikerült.');
      return data.state;
    }}
    scanForm.addEventListener('submit', async event => {{
      event.preventDefault();
      const barcode = scanInput.value.trim();
      if (!barcode) {{ showToast('Csippants be vagy írj be egy vonalkódot.'); scanInput.focus(); return; }}
      try {{ renderState(await send('{SCAN_ROUTE}', {{ barcode }})); scanInput.value = ''; }} catch (error) {{ showToast(error.message); }}
      scanInput.focus();
    }});
    resetButton.addEventListener('click', async () => {{ try {{ renderState(await send('{RESET_ROUTE}', {{}})); scanInput.value = ''; }} catch (error) {{ showToast(error.message); }} scanInput.focus(); }});
    document.addEventListener('pointerdown', event => {{ if (!event.target.closest('button,input')) setTimeout(() => scanInput.focus(), 0); }});
    window.addEventListener('pageshow', () => scanInput.focus());
    renderState(initialState);
  </script>
</body>
</html>"""
    return page.encode("utf-8")
