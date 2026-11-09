"""Single-screen landscape tablet UI for scanned production parts."""

from __future__ import annotations

import hashlib
import html
import json

from .cabinet_images import cabinet_image_catalog
from .front_images import front_image_catalog

ROUTE = "/apps/alkatresz-munkalap"
SCAN_ROUTE = f"{ROUTE}/beolvasas"
ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo", "hriroda"})


def render_page(state: dict, user_name: str, *, user_id: str = "") -> bytes:
    """Render the complete no-scroll tablet workstation."""
    safe_user = html.escape(str(user_name or "Felhasználó"))
    initial_state = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    identity_key = hashlib.sha256(str(user_id or user_name).encode("utf-8")).hexdigest()[:24]
    client_state_key = json.dumps(f"part-workstation:v1:{identity_key}")
    cabinet_images = json.dumps(cabinet_image_catalog(), ensure_ascii=True).replace("</", "<\\/")
    front_images = json.dumps(front_image_catalog(), ensure_ascii=True).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#041019" />
  <title>Összeszerelés · Divian-HUB</title>
  <link rel="stylesheet" href="/styles.css" />
  <style>
    body.part-workstation {{ color-scheme:dark; --ink:var(--text); --green:var(--accent); --blue:var(--accent); --amber:var(--accent-warm); --highlight-ink:var(--accent); --accent-ink:var(--bg); }}
    body.part-workstation.hr-theme {{ color-scheme:light; --highlight-ink:var(--text); --accent-ink:var(--text); }}
    * {{ box-sizing:border-box; }}
    html, body {{ width:100%; height:100%; margin:0; overflow:hidden; }}
    body {{ font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    button {{ font:inherit; }}
    .app {{ height:100dvh; min-height:0; display:grid; grid-template-rows:72px minmax(0,1fr); background:radial-gradient(circle at 25% 0%,color-mix(in srgb,var(--accent) 12%,transparent),transparent 32%),var(--bg); }}
    .workstation-topbar {{ min-width:0; display:grid; grid-template-columns:minmax(210px,1fr) minmax(300px,560px) minmax(210px,1fr); align-items:center; gap:16px; padding:10px 18px; border-bottom:1px solid var(--line); background:var(--panel-strong); }}
    .brand {{ display:flex; align-items:center; gap:11px; min-width:0; }}
    .brand-mark {{ width:42px; height:42px; display:grid; place-items:center; border-radius:13px; color:var(--accent-ink); background:var(--green); font-weight:950; letter-spacing:-.06em; box-shadow:0 0 30px color-mix(in srgb,var(--accent) 20%,transparent); }}
    .brand small,.brand strong {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .brand small {{ color:var(--muted); font-size:11px; letter-spacing:.12em; text-transform:uppercase; }}
    .brand strong {{ font-size:17px; }}
    .scanner-state {{ display:flex; align-items:center; justify-content:center; gap:12px; min-width:0; color:var(--muted); font-size:14px; }}
    .scan-pulse {{ width:10px; height:10px; border-radius:50%; background:var(--green); box-shadow:0 0 0 5px color-mix(in srgb,var(--accent) 11%,transparent); }}
    .scanner-state[aria-busy="true"] .scan-pulse {{ background:var(--amber); box-shadow:0 0 0 5px color-mix(in srgb,var(--accent-warm) 11%,transparent); }}
    .reset-button {{ border:0; cursor:pointer; font-weight:850; }}
    button:disabled {{ opacity:.55; cursor:wait; }}
    .user-area {{ min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:10px; }}
    .user-copy {{ min-width:0; text-align:right; }} .user-copy small,.user-copy strong {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .user-copy small {{ color:var(--muted); font-size:11px; }} .user-copy strong {{ font-size:14px; }}
    .reset-button {{ padding:9px 12px; border:1px solid var(--line); border-radius:10px; color:var(--ink); background:var(--panel-soft); }}
    .workspace {{ min-height:0; display:grid; grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr); gap:10px; padding:10px; }}
    .panel {{ min-width:0; min-height:0; overflow:hidden; border:1px solid var(--line); border-radius:18px; background:linear-gradient(145deg,var(--panel-strong),var(--panel)); box-shadow:var(--shadow); }}
    .panel-head {{ height:49px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-bottom:1px solid var(--line); }}
    .panel-title {{ display:flex; align-items:center; gap:9px; font-size:13px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
    .panel-index {{ color:var(--highlight-ink); }}
    .status {{ display:inline-flex; align-items:center; gap:7px; max-width:55%; padding:6px 9px; border:1px solid color-mix(in srgb,var(--accent-warm) 35%,var(--border)); border-radius:999px; color:var(--ink); background:color-mix(in srgb,var(--accent-warm) 12%,var(--panel)); font-size:11px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .status::before {{ content:""; width:6px; height:6px; flex:0 0 auto; border-radius:50%; background:currentColor; }}
    .info-panel {{ display:grid; grid-template-rows:49px minmax(0,1fr) 34px; }}
    .info-body {{ min-height:0; display:flex; flex-direction:column; gap:14px; padding:12px; overflow:auto; }}
    .primary-info {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); grid-template-rows:max-content repeat(2,minmax(66px,1fr)) max-content; gap:9px; }}
    .primary-info > .datum {{ grid-column:span 2; }}
    .primary-info > .datum.wide {{ grid-column:span 4; }}
    .primary-info > .front-datum {{ grid-column:span 3; }}
    .primary-info > #handingDatum {{ grid-column:span 1; }}
    .secondary-info {{ --detail-columns:2; flex:none; display:grid; grid-template-columns:repeat(var(--detail-columns),minmax(0,1fr)); gap:8px; padding-top:12px; border-top:1px solid var(--line); }}
    .secondary-info .dimensions-datum {{ grid-column:1 / -1; }}
    .datum {{ min-width:0; display:flex; flex-direction:column; justify-content:center; padding:11px 13px; border:1px solid var(--border); border-radius:11px; background:var(--panel-soft); }}
    .datum[hidden] {{ display:none; }}
    .datum.wide {{ grid-column:span 2; }} .datum label {{ display:block; margin-bottom:5px; color:var(--muted); font-size:10px; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
    .datum output {{ display:block; color:var(--ink); font-size:clamp(20px,1.9vw,26px); font-weight:800; line-height:1.25; overflow-wrap:anywhere; }}
    .datum output.pending {{ color:var(--muted); font-weight:550; }}
    .datum.top-datum {{ padding:7px 11px; }}
    .top-datum label {{ margin-bottom:3px; }}
    .top-datum output {{ font-size:clamp(16px,1.7vw,22px); line-height:1.15; }}
    .datum.color-datum {{ padding:7px 11px; }}
    .color-datum label {{ margin-bottom:3px; }}
    .color-datum output {{ line-height:1.15; }}
    .datum.with-image {{ display:grid; grid-template-columns:clamp(36px,4vw,52px) minmax(0,1fr); align-items:center; gap:11px; }}
    .datum-content {{ min-width:0; }}
    .image-slot {{ width:100%; aspect-ratio:1; display:grid; place-items:center; border:1px dashed var(--border); border-radius:8px; background:var(--panel-soft); color:var(--muted); font-size:9px; letter-spacing:.06em; text-transform:uppercase; }}
    .datum.cabinet-datum, .datum.front-datum {{ display:flex; flex-direction:row; }}
    .cabinet-datum .datum-content, .front-datum .datum-content {{ flex:1; }}
    .asset-image-slot {{ position:relative; flex:none; min-height:0; width:auto; height:100%; max-height:160px; aspect-ratio:1; overflow:hidden; }}
    .asset-image-slot.has-image {{ border-style:solid; background:#fff; }}
    .asset-image-slot img {{ position:absolute; inset:0; width:100%; height:100%; display:block; object-fit:contain; }}
    .asset-image-slot [hidden] {{ display:none; }}
    .barcode-datum output {{ color:var(--highlight-ink); }}
    .secondary-info .datum {{ padding:8px 11px; border-color:var(--line); background:var(--panel-soft); }}
    .secondary-info .datum label {{ font-size:9px; margin-bottom:3px; letter-spacing:.03em; overflow-wrap:anywhere; }}
    .secondary-info .datum output {{ font-size:15px; font-weight:650; color:var(--ink); }}
    .dimension-order {{ margin-top:3px; color:var(--muted); font-size:10px; }}
    .info-footer {{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:0 14px; border-top:1px solid var(--line); color:var(--muted); font-size:10px; }}
    .bom-panel {{ display:grid; grid-template-rows:49px minmax(0,1fr); }}
    .bom-count {{ min-width:28px; padding:5px 8px; border-radius:9px; color:var(--accent-ink); background:var(--green); font-size:12px; font-weight:950; text-align:center; }}
    .bom-wrap {{ min-height:0; position:relative; overflow:auto; padding:9px 12px; }}
    .bom-table {{ width:100%; border-collapse:separate; border-spacing:0 5px; table-layout:fixed; }}
    .bom-table th {{ padding:0 10px 5px; color:var(--muted); font-size:9px; letter-spacing:.1em; text-align:left; text-transform:uppercase; }}
    .bom-table th:nth-child(1) {{ width:38px; }} .bom-table th:nth-child(2) {{ position:relative; width:96px; }} .bom-table th:nth-child(4) {{ width:90px; text-align:center; }}
    .bom-table td:nth-child(2) {{ border-right:1px solid var(--line); }}
    .bom-column-resizer {{ position:absolute; z-index:2; top:50%; right:-10px; width:20px; height:30px; transform:translateY(-50%); cursor:col-resize; touch-action:none; user-select:none; border-radius:5px; }}
    .bom-column-resizer::after {{ content:""; position:absolute; top:5px; bottom:5px; left:7px; width:6px; border-left:2px solid var(--blue); border-right:2px solid var(--blue); opacity:.65; }}
    .bom-column-resizer:hover,.bom-column-resizer:focus-visible {{ outline:1px solid var(--blue); background:color-mix(in srgb,var(--accent) 12%,transparent); }}
    .resizing-bom,.resizing-bom * {{ cursor:col-resize !important; user-select:none !important; }}
    .bom-table td {{ height:43px; padding:7px 10px; border-top:1px solid var(--line); border-bottom:1px solid var(--line); background:var(--panel-soft); font-size:12px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
    .bom-table td:first-child {{ border-left:1px solid var(--line); border-radius:10px 0 0 10px; color:var(--muted); }} .bom-table td:last-child {{ border-right:1px solid var(--line); border-radius:0 10px 10px 0; }}
    .bom-table td:nth-child(4) {{ text-align:center; font-weight:900; }}
    .empty-bom {{ position:absolute; inset:38px 12px 10px; display:grid; place-items:center; text-align:center; pointer-events:none; }}
    .empty-bom[hidden] {{ display:none; }}
    .empty-icon {{ width:62px; height:62px; display:grid; place-items:center; margin:0 auto 10px; border:1px solid var(--border); border-radius:18px; color:var(--highlight-ink); background:var(--panel-soft); font-size:28px; }}
    .empty-bom strong {{ display:block; margin-bottom:5px; font-size:17px; }} .empty-bom p {{ max-width:360px; margin:0; color:var(--muted); font-size:12px; line-height:1.45; }}
    .toast {{ position:fixed; z-index:20; left:50%; top:82px; transform:translate(-50%,-16px); padding:10px 14px; border:1px solid rgba(248,113,113,.36); border-radius:11px; color:var(--ink); background:color-mix(in srgb,#ef4444 18%,var(--panel-strong)); opacity:0; pointer-events:none; transition:.2s; }} .toast.show {{ opacity:1; transform:translate(-50%,0); }}
    .rotate {{ display:none; }}
    @media (orientation:portrait) {{ .rotate {{ position:fixed; z-index:100; inset:0; display:grid; place-items:center; padding:34px; text-align:center; background:var(--bg); }} .rotate div {{ max-width:420px; }} .rotate b {{ display:block; margin-bottom:10px; font-size:48px; }} .rotate strong {{ display:block; margin-bottom:7px; font-size:23px; }} .rotate p {{ margin:0; color:var(--muted); }} }}
    @media (max-height:680px) and (orientation:landscape) {{ .app {{ grid-template-rows:62px minmax(0,1fr); }} .workstation-topbar {{ padding:7px 14px; }} .brand-mark {{ width:38px;height:38px; }} .workspace {{ gap:7px;padding:7px; }} .panel {{ border-radius:14px; }} .panel-head {{ height:43px; }} .info-panel {{ grid-template-rows:43px minmax(0,1fr) 30px; }} .info-body {{ padding:9px; gap:9px; }} .primary-info {{ gap:7px; grid-template-rows:max-content repeat(2,minmax(55px,1fr)) max-content; }} .datum {{ padding:8px 10px; }} .datum.with-image {{ grid-template-columns:34px minmax(0,1fr); gap:8px; }} .secondary-info {{ grid-template-columns:1.4fr repeat(var(--detail-columns),minmax(0,1fr)); padding-top:8px; gap:6px; }} .secondary-info .wide {{ grid-column:auto; }} .secondary-info .datum {{ padding:6px; }} .dimension-order {{ font-size:9px; }} .bom-panel {{ grid-template-rows:43px minmax(0,1fr); }} .bom-table td {{ height:36px; }} }}
  </style>
</head>
<body class="part-workstation">
  <main class="app">
    <header class="workstation-topbar">
      <div class="brand"><span class="brand-mark">D</span><span><small>Digitális gyártás</small><strong>Összeszerelés</strong></span></div>
      <div class="scanner-state" id="scannerState" role="status" aria-live="polite"><i class="scan-pulse" aria-hidden="true"></i><span id="scannerHint">Csippantsd be a vonalkódot</span></div>
      <div class="user-area"><span class="user-copy"><small>Saját munkamenet</small><strong>{safe_user}</strong></span><button class="reset-button" id="resetButton" type="button">Új elem</button></div>
    </header>
    <section class="workspace" aria-label="Összeszerelés munkaterület">
        <article class="panel info-panel">
          <header class="panel-head"><div class="panel-title"><span class="panel-index">01</span> Beolvasott elem adatai</div><span class="status" id="scanStatus">Scanner készen áll</span></header>
          <div class="info-body">
            <div class="primary-info">
              <div class="datum top-datum barcode-datum"><label>Vonalkód</label><output id="barcode">Még nincs beolvasott kód</output></div>
              <div class="datum top-datum"><label>Korpusz</label><output class="pending" data-item="cabinet">—</output></div>
              <div class="datum with-image cabinet-datum"><div class="image-slot asset-image-slot" id="cabinetImageSlot"><span id="cabinetImagePlaceholder">Kép</span><img id="cabinetImage" alt="" decoding="async" hidden /></div><div class="datum-content"><label>Cikkszám</label><output class="pending" data-item="part_number">—</output></div></div>
              <div class="datum"><label>Megnevezés</label><output class="pending" data-item="description">—</output></div>
              <div class="datum wide with-image front-datum" id="frontDatum"><div class="image-slot asset-image-slot" id="frontImageSlot"><span id="frontImagePlaceholder">Kép</span><img id="frontImage" alt="" decoding="async" hidden /></div><div class="datum-content"><label>Frontszín &amp; Típus</label><output class="pending" data-item="front">—</output></div></div>
              <div class="datum" id="handingDatum" hidden><label>Nyitási irány</label><output data-item="handing">—</output></div>
              <div class="datum wide color-datum" id="colorDatum"><label>Korpusz színe</label><output class="pending" data-item="color">—</output></div>
            </div>
            <div class="secondary-info" id="secondaryInfo">
              <div class="datum wide dimensions-datum"><label>Beépítési méret</label><output class="pending" data-item="dimensions">—</output><span class="dimension-order">Magasság × szélesség × mélység</span></div>
              <div class="datum"><label>Láb</label><output class="pending" data-item="legs">—</output></div>
              <div class="datum"><label>Munkalap</label><output class="pending" data-item="worktop">—</output></div>
              <div class="datum" id="fillerWidthDatum" hidden><label>Hézagtakaró szélessége</label><output data-item="filler_width">—</output></div>
              <div class="datum" id="handleDrillingDatum" hidden><label>Fogantyú furat</label><output data-item="handle_drilling">—</output></div>
            </div>
          </div>
          <footer class="info-footer"><span>Beolvasva: <time id="scannedAt">—</time> · prdID: <output id="productionId">—</output></span><span id="lookupState">Beolvasásra vár</span></footer>
        </article>
      <article class="panel bom-panel">
        <header class="panel-head"><div class="panel-title"><span class="panel-index">02</span> Darabjegyzék</div><span class="bom-count" id="bomCount">0</span></header>
        <div class="bom-wrap">
          <table class="bom-table"><thead><tr><th>#</th><th id="bomPartHeader">Cikkszám<div class="bom-column-resizer" id="bomColumnResizer" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Cikkszám oszlop szélessége" aria-valuemin="64" aria-valuenow="96" title="Húzd az oszlopszélesség állításához. Dupla kattintás: alaphelyzet."></div></th><th>Megnevezés</th><th>Mennyiség</th></tr></thead><tbody id="bomBody"></tbody></table>
          <div class="empty-bom" id="emptyBom"><div><span class="empty-icon">≡</span><strong id="emptyBomTitle">Nincs beolvasott elem</strong><p id="emptyBomText">A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.</p></div></div>
        </div>
      </article>
    </section>
  </main>
  <div class="toast" id="toast" role="alert"></div>
  <div class="rotate"><div><b>↻</b><strong>Fordítsd fekvő helyzetbe a táblagépet</strong><p>Ez a munkafelület fekvő nézetre és egyetlen, görgetésmentes képernyőre készült.</p></div></div>
  <script>
    const initialState = {initial_state};
    document.querySelector('meta[name="theme-color"]').setAttribute('content', getComputedStyle(document.body).getPropertyValue('--bg').trim());
    const clientStateKey = {client_state_key};
    const cabinetImages = new Map(Object.entries({cabinet_images}));
    const frontImages = {front_images};
    const frontImage = document.getElementById('frontImage');
    const cabinetImage = document.getElementById('cabinetImage');
    const scannerState = document.getElementById('scannerState');
    const scannerHint = document.getElementById('scannerHint');
    const resetButton = document.getElementById('resetButton');
    const toast = document.getElementById('toast');
    let toastTimer;
    let busy = false;
    let scanBuffer = '';
    let scanOverflow = false;
    let lastScanKeyAt = 0;
    const pendingScans = [];

    function cabinetImageUrl(item) {{
      const code = String(item?.part_number || '').trim().toUpperCase();
      const side = new Map([['jobb','J'],['bal','B'],['j','J'],['b','B']]).get(String(item?.handing || '').trim().toLowerCase());
      let base = code;
      if (side) {{
        base = code.replace(/_[JB]$/, '');
        if (base === code && /[JB]$/.test(code) && cabinetImages.has(code.slice(0, -1) + (code.endsWith('J') ? 'B' : 'J'))) base = code.slice(0, -1);
        for (const candidate of [base + '_' + side, base + side]) {{
          if (cabinetImages.has(candidate)) return cabinetImages.get(candidate);
        }}
      }}
      return cabinetImages.get(base) || '';
    }}
    function frontImageKey(value) {{
      return String(value || '').trim().toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/\\bfolias\\b/g, '').replace(/[^a-z0-9]/g, '');
    }}
    function frontImageUrl(state) {{
      const features = state.production_xml?.features || {{}};
      const colour = features['Front színe'] || features['Front szín felső'] || features['Keretléc szín'];
      const colours = frontImages[frontImageKey(features['Front típus'])];
      return colours && Object.hasOwn(colours, frontImageKey(colour)) ? colours[frontImageKey(colour)] : '';
    }}
    function showAssetImage(image) {{
      const loaded = Boolean(image.getAttribute('src') && image.complete && image.naturalWidth);
      image.hidden = !loaded;
      image.parentElement.querySelector('span').hidden = loaded;
      image.parentElement.classList.toggle('has-image', loaded);
    }}
    function renderAssetImage(image, url, alt) {{
      image.alt = alt;
      if (image.getAttribute('src') === (url || null)) return;
      image.hidden = true;
      image.parentElement.querySelector('span').hidden = false;
      image.parentElement.classList.remove('has-image');
      if (url) {{ image.src = url; showAssetImage(image); }}
      else image.removeAttribute('src');
    }}
    for (const image of [cabinetImage, frontImage]) {{
      image.addEventListener('load', () => showAssetImage(image));
      image.addEventListener('error', () => {{ image.removeAttribute('src'); showAssetImage(image); }});
    }}

    function restoreClientState() {{
      try {{
        const state = JSON.parse(sessionStorage.getItem(clientStateKey));
        if (state && typeof state.barcode === 'string' && state.barcode
          && ['ready','error'].includes(state.lookup_status)
          && state.item && typeof state.item === 'object' && !Array.isArray(state.item)
          && Array.isArray(state.bom) && state.bom.every(row => row && typeof row === 'object' && !Array.isArray(row))) return state;
      }} catch (error) {{ /* Storage may be unavailable; the current page still works independently. */ }}
      return null;
    }}
    function saveClientState(state) {{
      try {{
        if (state.barcode && ['ready','error'].includes(state.lookup_status)) sessionStorage.setItem(clientStateKey, JSON.stringify(state));
        else sessionStorage.removeItem(clientStateKey);
      }} catch (error) {{ /* A storage failure must not interrupt scanning. */ }}
    }}
    const bomTable = document.querySelector('.bom-table');
    const bomPartHeader = document.getElementById('bomPartHeader');
    const bomColumnResizer = document.getElementById('bomColumnResizer');
    const defaultPartWidth = 96;
    const minPartWidth = 64;
    let columnDrag = null;

    function setPartColumnWidth(width) {{
      const headers = bomTable.tHead.rows[0].cells;
      const maxWidth = Math.max(minPartWidth, Math.floor(bomTable.getBoundingClientRect().width
        - headers[0].getBoundingClientRect().width - headers[3].getBoundingClientRect().width - 160));
      const nextWidth = Math.max(minPartWidth, Math.min(maxWidth, Math.round(width)));
      bomPartHeader.style.width = nextWidth + 'px';
      bomColumnResizer.setAttribute('aria-valuemax', maxWidth);
      bomColumnResizer.setAttribute('aria-valuenow', nextWidth);
      bomColumnResizer.setAttribute('aria-valuetext', nextWidth + ' px');
    }}
    function stopColumnDrag(event) {{
      if (!columnDrag || event.pointerId !== columnDrag.pointerId) return;
      const pointerId = columnDrag.pointerId;
      columnDrag = null;
      document.body.classList.remove('resizing-bom');
      if (bomColumnResizer.hasPointerCapture(pointerId)) bomColumnResizer.releasePointerCapture(pointerId);
    }}
    bomColumnResizer.addEventListener('pointerdown', event => {{
      if (event.button !== 0 || columnDrag) return;
      event.preventDefault();
      columnDrag = {{ pointerId:event.pointerId, x:event.clientX, width:bomPartHeader.getBoundingClientRect().width }};
      bomColumnResizer.focus({{ preventScroll:true }});
      bomColumnResizer.setPointerCapture(event.pointerId);
      document.body.classList.add('resizing-bom');
    }});
    bomColumnResizer.addEventListener('pointermove', event => {{
      if (!columnDrag || event.pointerId !== columnDrag.pointerId) return;
      event.preventDefault();
      setPartColumnWidth(columnDrag.width + event.clientX - columnDrag.x);
    }});
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(name => bomColumnResizer.addEventListener(name, stopColumnDrag));
    bomColumnResizer.addEventListener('dblclick', () => setPartColumnWidth(defaultPartWidth));
    bomColumnResizer.addEventListener('keydown', event => {{
      const step = event.shiftKey ? 24 : 8;
      const width = bomPartHeader.getBoundingClientRect().width;
      const nextWidth = {{ ArrowLeft:width - step, ArrowRight:width + step, Home:minPartWidth, End:Number(bomColumnResizer.getAttribute('aria-valuemax')) }}[event.key];
      if (nextWidth === undefined) return;
      event.preventDefault();
      setPartColumnWidth(nextWidth);
    }});
    setPartColumnWidth(defaultPartWidth);
    if (window.ResizeObserver) new ResizeObserver(() => setPartColumnWidth(bomPartHeader.getBoundingClientRect().width)).observe(bomTable);
    else window.addEventListener('resize', () => setPartColumnWidth(bomPartHeader.getBoundingClientRect().width));

    function setBusy(value) {{
      busy = value;
      resetButton.disabled = value;
      scannerState.setAttribute('aria-busy', String(value));
      scannerHint.textContent = value ? 'Darabjegyzék betöltése…' : 'Csippantsd be a vonalkódot';
    }}

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
      rows.forEach((row, index) => {{
        const tr = document.createElement('tr');
        [index + 1, row.part_number || '—', row.description || '—', row.quantity ?? '—'].forEach(value => {{ const td = document.createElement('td'); td.textContent = value; td.title = String(value); tr.appendChild(td); }});
        body.appendChild(tr);
      }});
      document.getElementById('bomCount').textContent = rows.length;
      document.getElementById('emptyBom').hidden = rows.length > 0;
      document.querySelector('.bom-wrap').scrollTop = 0;
    }}
    function renderState(state) {{
      const hasScan = Boolean(state.barcode);
      const pending = state.lookup_status === 'api_pending';
      const ready = state.lookup_status === 'ready';
      const failed = state.lookup_status === 'error';
      document.getElementById('barcode').textContent = hasScan ? state.barcode : 'Még nincs beolvasott kód';
      document.getElementById('scannedAt').textContent = formatDate(state.scanned_at);
      document.getElementById('productionId').textContent = valueOrPending(state.production_xml && state.production_xml.production_number);
      document.getElementById('scanStatus').textContent = pending ? 'Darabjegyzék betöltése…' : (failed ? 'Sikertelen lekérés' : 'Scanner készen áll');
      document.getElementById('lookupState').textContent = pending ? 'Betöltés…' : (failed ? 'Sikertelen lekérés' : (ready ? 'Darabjegyzék betöltve' : 'Beolvasásra vár'));
      document.getElementById('emptyBomTitle').textContent = pending ? 'Darabjegyzék betöltése…' : (failed ? 'Sikertelen lekérés' : (ready ? 'Nincs darabjegyzék' : 'Nincs beolvasott elem'));
      document.getElementById('emptyBomText').textContent = pending ? 'A beolvasott elem tételeinek lekérése folyamatban van.' : (failed ? state.error_message || 'Olvasd be újra a vonalkódot.' : (ready ? 'A beolvasott elemhez nem érkezett darabjegyzéktétel.' : 'A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.'));
      document.querySelectorAll('[data-item]').forEach(output => {{
        const value = state.item && state.item[output.dataset.item];
        output.textContent = valueOrPending(value, output.dataset.item === 'description' && pending ? 'API-kapcsolatra vár' : '—');
        output.title = valueOrPending(value);
        output.classList.toggle('pending', !value);
      }});
      const hasHanding = Boolean(state.item && state.item.handing);
      document.getElementById('handingDatum').hidden = !hasHanding;
      document.getElementById('frontDatum').classList.toggle('wide', !hasHanding);
      const hasFillerWidth = Boolean(state.item && state.item.filler_width);
      document.getElementById('fillerWidthDatum').hidden = !hasFillerWidth;
      document.getElementById('secondaryInfo').classList.toggle('has-filler', hasFillerWidth);
      const hasHandleDrilling = Boolean(state.item && state.item.handle_drilling);
      document.getElementById('handleDrillingDatum').hidden = !hasHandleDrilling;
      document.getElementById('secondaryInfo').style.setProperty('--detail-columns', 2 + Number(hasFillerWidth) + Number(hasHandleDrilling));
      renderAssetImage(cabinetImage, cabinetImageUrl(state.item), [state.item?.part_number, state.item?.handing].filter(Boolean).join(' · '));
      renderAssetImage(frontImage, frontImageUrl(state), state.item?.front || '');
      renderBom(Array.isArray(state.bom) ? state.bom : []);
      saveClientState(state);
    }}
    async function send(url, payload) {{
      const response = await fetch(url, {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload || {{}}) }});
      const data = await response.json().catch(() => ({{ ok:false, error:'Érvénytelen szerverválasz.' }}));
      if (!response.ok || !data.ok) throw new Error(data.error || 'A művelet nem sikerült.');
      return data.state;
    }}
    async function processScanQueue() {{
      if (busy || !pendingScans.length) return;
      const barcode = pendingScans.shift();
      setBusy(true);
      const scannedAt = new Date().toISOString();
      renderState({{ barcode, scanned_at:scannedAt, lookup_status:'api_pending', bom:[] }});
      try {{ renderState(await send('{SCAN_ROUTE}', {{ barcode }})); }} catch (error) {{ renderState({{ barcode, scanned_at:scannedAt, lookup_status:'error', error_message:error.message, item:{{}}, bom:[] }}); showToast(error.message); }} finally {{ setBusy(false); void processScanQueue(); }}
    }}
    function clearScanBuffer() {{ scanBuffer = ''; scanOverflow = false; lastScanKeyAt = 0; }}
    document.addEventListener('keydown', event => {{
      if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.altKey || event.metaKey || event.repeat
        || event.target.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"])')) {{ clearScanBuffer(); return; }}
      const now = performance.now();
      if (now - lastScanKeyAt > 1500) clearScanBuffer();
      if (event.key === 'Enter' || event.key === 'Tab') {{
        if (!scanBuffer && !scanOverflow) return;
        event.preventDefault();
        const barcode = scanBuffer.trim();
        const overflow = scanOverflow;
        clearScanBuffer();
        if (overflow) {{ showToast('A vonalkód legfeljebb 160 karakter lehet.'); return; }}
        if (barcode) {{ pendingScans.push(barcode); void processScanQueue(); }}
      }} else if (event.key === 'Backspace' && scanBuffer) {{
        event.preventDefault(); scanBuffer = scanBuffer.slice(0, -1); lastScanKeyAt = now;
      }} else if (event.key === 'Escape') clearScanBuffer();
      else if (event.key.length === 1) {{
        if (event.key === ' ' && !scanBuffer && event.target.closest?.('button,[role="separator"]')) return;
        event.preventDefault();
        if (scanBuffer.length < 160) scanBuffer += event.key;
        else scanOverflow = true;
        lastScanKeyAt = now;
      }} else if (event.key !== 'Shift') clearScanBuffer();
    }}, true);
    resetButton.addEventListener('click', () => {{ if (busy) return; clearScanBuffer(); pendingScans.length = 0; renderState(initialState); }});
    document.addEventListener('pointerdown', clearScanBuffer);
    window.addEventListener('blur', clearScanBuffer);
    document.addEventListener('visibilitychange', () => {{ if (document.hidden) clearScanBuffer(); }});
    renderState(restoreClientState() || initialState);
  </script>
</body>
</html>"""
    return page.encode("utf-8")
