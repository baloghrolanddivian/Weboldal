"""Single-screen landscape tablet UI for scanned production parts."""

from __future__ import annotations

import hashlib
import html
import json

from .cabinet_images import cabinet_image_catalog
from .connectors import CONNECTOR_RULES
from .front_colours import nettfront_colour_catalog

ROUTE = "/apps/alkatresz-munkalap"
SCAN_ROUTE = f"{ROUTE}/beolvasas"
DAMAGE_ROUTE = f"{ROUTE}/serult"
ADMIN_ROUTE = f"{ROUTE}/admin"
ADMIN_DATA_ROUTE = f"{ADMIN_ROUTE}/adatok"
ADMIN_SAVE_ROUTE = f"{ADMIN_ROUTE}/mentes"
ADMIN_ACCESS_USER_IDS = frozenset({"gyartas-vezerlo"})
ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo", "hriroda"})


def render_page(state: dict, user_name: str, *, user_id: str = "", show_admin: bool = False) -> bytes:
    """Render the complete no-scroll tablet workstation."""
    safe_user = html.escape(str(user_name or "Felhasználó"))
    admin_button = f'<a class="reset-button admin-link" href="{ADMIN_ROUTE}">Admin</a>' if show_admin else ""
    initial_state = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    identity_key = hashlib.sha256(str(user_id or user_name).encode("utf-8")).hexdigest()[:24]
    client_state_key = json.dumps(f"part-workstation:v1:{identity_key}")
    cabinet_images = json.dumps(cabinet_image_catalog(), ensure_ascii=True).replace("</", "<\\/")
    connector_rules = json.dumps(CONNECTOR_RULES, ensure_ascii=True).replace("</", "<\\/")
    nettfront_colours = json.dumps(nettfront_colour_catalog(), ensure_ascii=True).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#041019" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-title" content="Összeszerelés" />
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
    .reset-button {{ flex:none; border:0; cursor:pointer; font-weight:850; white-space:nowrap; }}
    button:disabled {{ opacity:.55; cursor:wait; }}
    .user-area {{ min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:10px; }}
    .user-copy {{ min-width:0; text-align:right; }} .user-copy small,.user-copy strong {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .user-copy small {{ color:var(--muted); font-size:11px; }} .user-copy strong {{ font-size:14px; }}
    .reset-button {{ padding:9px 12px; border:1px solid var(--line); border-radius:10px; color:var(--ink); background:var(--panel-soft); }}
    .fullscreen-button {{ flex:none; width:40px; height:40px; padding:8px; display:grid; place-items:center; }}
    .fullscreen-button svg {{ width:22px; height:22px; }}
    .fullscreen-button[aria-pressed="true"] {{ border-color:var(--accent); }}
    .fullscreen-help {{ max-width:min(480px,calc(100vw - 32px)); border:1px solid var(--border); border-radius:14px; padding:22px; color:var(--ink); background:var(--panel-strong); box-shadow:var(--shadow); }}
    .fullscreen-help::backdrop {{ background:rgba(0,0,0,.6); }}
    .fullscreen-help h2 {{ margin:0 0 12px; font-size:20px; }}
    .fullscreen-help p {{ font-size:15px; line-height:1.5; }}
    .workspace {{ min-height:0; display:grid; grid-template-columns:minmax(0,1fr); gap:10px; padding:10px; }}
    .panel {{ min-width:0; min-height:0; overflow:hidden; border:1px solid var(--line); border-radius:18px; background:linear-gradient(145deg,var(--panel-strong),var(--panel)); box-shadow:var(--shadow); }}
    .panel-head {{ height:49px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 16px; border-bottom:1px solid var(--line); }}
    .panel-title {{ display:flex; align-items:center; gap:9px; font-size:13px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
    .panel-index {{ color:var(--highlight-ink); }}
    .panel-actions {{ display:flex; align-items:center; gap:12px; min-width:0; }}
    .panel-actions .status {{ max-width:none; }}
    .bom-toggle {{ min-height:40px; color:var(--highlight-ink); }}
    .admin-link {{ text-decoration:none; }}
    .status {{ display:inline-flex; align-items:center; gap:7px; max-width:55%; padding:6px 9px; border:1px solid color-mix(in srgb,var(--accent-warm) 35%,var(--border)); border-radius:999px; color:var(--ink); background:color-mix(in srgb,var(--accent-warm) 12%,var(--panel)); font-size:11px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .status::before {{ content:""; width:6px; height:6px; flex:0 0 auto; border-radius:50%; background:currentColor; }}
    .info-panel {{ display:grid; grid-template-rows:49px minmax(0,1fr) minmax(34px,auto); }}
    .info-body {{ min-height:0; display:flex; flex-direction:column; gap:14px; padding:12px; overflow:auto; }}
    .primary-info {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); grid-template-rows:minmax(0,1fr) max-content; gap:9px; }}
    .primary-info > .datum {{ grid-column:span 2; }}
    .primary-info > .datum.wide {{ grid-column:span 4; }}
    .primary-info.has-front > .color-datum {{ grid-column:span 2; }}
    .primary-info.has-connector > .cabinet-datum {{ grid-column:span 3; }}
    .primary-info > .connector-datum {{ grid-column:span 1; display:grid; grid-template-rows:max-content minmax(0,1fr); gap:12px; }}
    .primary-info > .connector-datum[hidden] {{ display:none; }}
    .connector-datum output {{ font-size:clamp(20px,2.1vw,30px); }}
    .connector-image-slot {{ position:relative; min-height:0; width:100%; border:1px solid var(--border); border-radius:8px; overflow:hidden; background:#fff; }}
    .connector-image-slot img {{ position:absolute; inset:0; display:block; width:100%; height:100%; object-fit:contain; }}
    .connector-image-slot span {{ position:absolute; inset:0; display:grid; place-items:center; color:#64748b; font-size:11px; }}
    .connector-image-slot [hidden] {{ display:none; }}
    .has-connector .item-identity {{ font-size:clamp(28px,3.6vw,52px); }}
    .secondary-info {{ --detail-columns:1; flex:none; display:grid; grid-template-columns:1.4fr repeat(var(--detail-columns),minmax(0,1fr)); gap:8px; padding-top:12px; border-top:1px solid var(--line); }}
    .secondary-info .datum.wide {{ grid-column:auto; }}
    .datum {{ min-width:0; display:flex; flex-direction:column; justify-content:center; padding:11px 13px; border:1px solid var(--border); border-radius:11px; background:var(--panel-soft); }}
    .datum[hidden] {{ display:none; }}
    .datum.wide {{ grid-column:span 2; }} .datum label {{ display:block; margin-bottom:5px; color:var(--muted); font-size:10px; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
    .datum output {{ display:block; color:var(--ink); font-size:clamp(24px,2.8vw,40px); font-weight:800; line-height:1.25; overflow-wrap:anywhere; }}
    .datum output.pending {{ color:var(--muted); font-weight:550; }}
    .datum.color-datum {{ padding:7px 11px; }}
    .color-datum label {{ margin-bottom:3px; }}
    .color-datum output {{ line-height:1.15; }}
    .datum.front-datum {{ padding:7px 11px; }}
    .front-datum label {{ margin-bottom:3px; }}
    .front-datum output {{ font-size:clamp(20px,2.1vw,30px); line-height:1.2; }}
    .front-colour-line {{ margin-top:4px; font-size:clamp(14px,1.5vw,21px); font-weight:650; line-height:1.3; overflow-wrap:anywhere; }}
    .front-nettfront {{ color:var(--muted); font-size:.9em; font-weight:550; }}
    .front-datum [hidden] {{ display:none; }}
    .datum.color-datum.colour-white {{ background:#fff; border-color:#d7dde4; }}
    .datum.color-datum.colour-white label, .datum.color-datum.colour-white output {{ color:#000; }}
    .datum.color-datum.colour-anthracite {{ background:#000; border-color:#555; }}
    .datum.color-datum.colour-anthracite label, .datum.color-datum.colour-anthracite output {{ color:#fff; }}
    .datum-content {{ min-width:0; }}
    .image-slot {{ width:100%; aspect-ratio:1; display:grid; place-items:center; border:1px dashed var(--border); border-radius:8px; background:var(--panel-soft); color:var(--muted); font-size:9px; letter-spacing:.06em; text-transform:uppercase; }}
    .datum.cabinet-datum {{ display:flex; flex-direction:row; align-items:center; gap:clamp(16px,2vw,28px); padding:clamp(14px,2vw,28px); }}
    .cabinet-datum .datum-content {{ flex:1; }}
    .item-identity {{ font-size:clamp(32px,4.4vw,64px); font-weight:800; line-height:1.2; overflow-wrap:anywhere; }}
    .item-identity output {{ display:inline; font-size:inherit; line-height:inherit; }}
    .item-separator {{ color:var(--muted); }}
    .asset-image-slot {{ position:relative; flex:none; min-height:0; width:auto; height:100%; max-height:400px; max-width:36%; aspect-ratio:1; overflow:hidden; }}
    .asset-image-slot.has-image {{ border-style:solid; background:#fff; }}
    .asset-image-slot img {{ position:absolute; inset:0; width:100%; height:100%; display:block; object-fit:contain; }}
    .asset-image-slot [hidden] {{ display:none; }}
    .secondary-info .datum {{ padding:8px 11px; border-color:var(--line); background:var(--panel-soft); }}
    .secondary-info .datum label {{ font-size:9px; margin-bottom:3px; letter-spacing:.03em; overflow-wrap:anywhere; }}
    .secondary-info .datum output {{ font-size:clamp(17px,1.8vw,24px); font-weight:650; color:var(--ink); }}
    .secondary-info [data-item="notes"] {{ display:block; min-width:0; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; color:var(--ink); font-size:clamp(17px,1.8vw,24px); font-weight:650; line-height:1.25; }}
    .secondary-info #notesDatum {{ border-color:#ef4444; box-shadow:0 0 0 2px #ef4444; text-align:left; cursor:pointer; }}
    #notesDatum:focus-visible {{ outline:2px solid var(--accent); outline-offset:5px; }}
    .notes-label {{ margin-bottom:3px; color:var(--muted); font-size:9px; font-weight:850; letter-spacing:.03em; text-transform:uppercase; }}
    .notes-hint {{ margin-top:3px; color:var(--muted); font-size:10px; }}
    .notes-dialog {{ width:min(760px,calc(100vw - 32px)); max-height:calc(100dvh - 32px); padding:0; border:1px solid #ef4444; border-radius:18px; color:var(--ink); background:var(--panel-strong); box-shadow:var(--shadow); overflow:hidden; }}
    .notes-dialog[open] {{ display:grid; grid-template-rows:auto auto minmax(0,1fr); }}
    .notes-dialog::backdrop {{ background:rgba(0,0,0,.65); }}
    .notes-dialog-head {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 18px; border-bottom:1px solid var(--line); }}
    .notes-dialog h2 {{ margin:0; font-size:22px; }}
    .notes-dialog-head button {{ min-height:44px; }}
    .notes-context {{ margin:0; padding:12px 18px 0; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
    .notes-full-text {{ min-height:0; max-height:60dvh; margin:0; padding:18px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; font-size:clamp(18px,2vw,24px); line-height:1.5; user-select:text; }}
    .dimension-order {{ margin-top:3px; color:var(--muted); font-size:10px; }}
    .info-footer {{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:6px 14px; border-top:1px solid var(--line); color:var(--muted); font-size:10px; }}
    .footer-metadata {{ flex:1; min-width:0; display:flex; flex-wrap:wrap; gap:4px 14px; }}
    .footer-metadata span {{ min-width:0; overflow-wrap:anywhere; }}
    .footer-metadata output {{ color:var(--ink); }}
    #lookupState {{ flex:none; }}
    .bom-panel {{ position:fixed; inset:82px 10px 10px auto; width:min(540px,calc(100vw - 20px)); max-width:none; height:calc(100dvh - 92px); max-height:none; margin:0; padding:0; color:var(--ink); }}
    .bom-panel[open] {{ display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; animation:bom-slide-in .2s ease-out; }}
    .bom-panel::backdrop {{ background:rgba(0,0,0,.25); }}
    .bom-panel .panel-head {{ height:auto; min-height:54px; }}
    .bom-heading {{ display:flex; align-items:center; gap:12px; min-width:0; }}
    .bom-close {{ min-width:42px; min-height:40px; font-size:20px; }}
    .bom-item {{ padding:12px 16px; border-bottom:1px solid var(--line); }}
    .bom-item strong {{ display:block; font-size:18px; overflow-wrap:anywhere; }}
    .bom-item p {{ margin:5px 0 0; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
    .bom-review-message {{ margin:0 0 12px; color:var(--ink); font-size:16px; line-height:1.4; }}
    .bom-review-footer {{ padding:16px; border-top:1px solid var(--line); }}
    .bom-confirm {{ width:100%; min-height:52px; border-color:var(--green); color:var(--accent-ink); background:var(--green); font-size:17px; }}
    .bom-panel [hidden] {{ display:none; }}
    .bom-panel.bom-review {{ inset:0; width:94vw; height:90dvh; margin:auto; }}
    .bom-review::backdrop {{ background:rgba(0,0,0,.7); }}
    .bom-review .bom-table th {{ font-size:12px; }}
    .bom-review .bom-table td {{ min-height:50px; padding:12px 10px; font-size:clamp(16px,1.8vw,24px); white-space:normal; overflow-wrap:anywhere; }}
    .bom-review .bom-table th:nth-child(4) {{ width:120px; }}
    @keyframes bom-slide-in {{ from {{ opacity:0; transform:translateX(40px); }} to {{ opacity:1; transform:translateX(0); }} }}
    @media (prefers-reduced-motion:reduce) {{ .bom-panel[open] {{ animation:none; }} }}
    .bom-count {{ min-width:28px; padding:5px 8px; border-radius:9px; color:var(--accent-ink); background:var(--green); font-size:12px; font-weight:950; text-align:center; }}
    .bom-wrap {{ min-height:0; position:relative; overflow:auto; padding:9px 12px; }}
    .bom-table {{ width:100%; border-collapse:separate; border-spacing:0 5px; table-layout:fixed; }}
    .bom-table th {{ padding:0 10px 5px; color:var(--muted); font-size:9px; letter-spacing:.1em; text-align:left; text-transform:uppercase; }}
    .bom-table th:nth-child(1) {{ width:38px; }} .bom-table th:nth-child(2) {{ position:relative; width:96px; }} .bom-table th:nth-child(4) {{ width:90px; text-align:center; }}
    .bom-table th:nth-child(5) {{ width:108px; text-align:center; }}
    .bom-damage-button {{ min-height:40px; padding:7px 10px; font-size:12px; color:var(--amber); }}
    .bom-table td:last-child {{ text-align:center; }}
    .bom-table tr.is-damaged td {{ background:color-mix(in srgb,var(--amber) 12%,var(--panel-soft)); }}
    .damage-confirm {{ width:min(520px,calc(100vw - 32px)); max-height:85dvh; padding:24px; border:1px solid var(--border); border-radius:18px; color:var(--ink); background:var(--panel-strong); }}
    .damage-confirm::backdrop {{ background:rgba(0,0,0,.7); }}
    .damage-confirm h2 {{ margin:0 0 12px; font-size:22px; }}
    .damage-confirm p {{ overflow-wrap:anywhere; line-height:1.5; }}
    .damage-confirm-actions {{ display:flex; flex-wrap:wrap; justify-content:flex-end; gap:12px; margin-top:22px; }}
    .damage-confirm-actions button {{ min-height:44px; }}
    #damageSubmit {{ border-color:var(--amber); color:var(--amber); }}
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
    @media (max-height:680px) and (orientation:landscape) {{ .app {{ grid-template-rows:62px minmax(0,1fr); }} .workstation-topbar {{ padding:7px 14px; }} .brand-mark {{ width:38px;height:38px; }} .workspace {{ gap:7px;padding:7px; }} .panel {{ border-radius:14px; }} .panel-head {{ height:43px; }} .info-panel {{ grid-template-rows:43px minmax(0,1fr) minmax(30px,auto); }} .info-body {{ padding:9px; gap:9px; }} .primary-info {{ gap:7px; grid-template-rows:minmax(0,1fr) max-content; }} .datum {{ padding:8px 10px; }} .secondary-info {{ grid-template-columns:1.4fr repeat(var(--detail-columns),minmax(0,1fr)); padding-top:8px; gap:6px; }} .secondary-info .wide {{ grid-column:auto; }} .secondary-info .datum {{ padding:6px; }} .dimension-order {{ font-size:9px; }} .bom-table td {{ height:36px; }} }}
  </style>
</head>
<body class="part-workstation">
  <main class="app">
    <header class="workstation-topbar">
      <div class="brand"><span class="brand-mark">D</span><span><small>Digitális gyártás</small><strong>Összeszerelés</strong></span></div>
      <div class="scanner-state" id="scannerState" role="status" aria-live="polite"><i class="scan-pulse" aria-hidden="true"></i><span id="scannerHint">Csippantsd be a vonalkódot</span></div>
      <div class="user-area"><span class="user-copy"><small>Saját munkamenet</small><strong>{safe_user}</strong></span><button class="reset-button fullscreen-button" id="fullscreenButton" type="button" aria-label="Teljes képernyő" title="Teljes képernyő" aria-pressed="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" /></svg></button><button class="reset-button" id="resetButton" type="button">Új elem</button></div>
    </header>
    <section class="workspace" aria-label="Összeszerelés munkaterület">
        <article class="panel info-panel">
          <header class="panel-head"><div class="panel-title"><span class="panel-index">01</span> Beolvasott elem adatai</div><div class="panel-actions"><span class="status" id="scanStatus">Scanner készen áll</span>{admin_button}<button class="reset-button bom-toggle" id="bomToggle" type="button" aria-haspopup="dialog" aria-controls="bomPanel" aria-expanded="false">Darabjegyzék · <span id="bomToggleCount">0</span></button></div></header>
          <div class="info-body">
            <div class="primary-info">
              <div class="datum wide cabinet-datum"><div class="image-slot asset-image-slot" id="cabinetImageSlot"><span id="cabinetImagePlaceholder">Kép</span><img id="cabinetImage" alt="" decoding="async" hidden /></div><div class="datum-content"><label>Cikkszám | Megnevezés</label><div class="item-identity"><output class="pending" data-item="part_number">—</output><span class="item-separator" aria-hidden="true"> | </span><output class="pending" data-item="description">—</output></div></div></div>
              <div class="datum connector-datum" id="connectorDatum" hidden><div><label>Összekötő</label><output id="connectorOrientation">—</output></div><div class="connector-image-slot"><span>Kép betöltése…</span><img id="connectorImage" alt="" decoding="async" hidden /></div></div>
              <div class="datum wide color-datum" id="colorDatum"><label>Korpusz színe</label><output class="pending" data-item="color">—</output></div>
              <div class="datum front-datum" id="frontDatum" hidden><label>Front</label><output id="frontModel">—</output><div class="front-colour-line" id="frontColourLine" hidden><span id="frontColour"></span> <span class="front-nettfront" id="frontNettfront" hidden></span></div></div>
            </div>
            <div class="secondary-info" id="secondaryInfo">
              <div class="datum wide dimensions-datum"><label>Beépítési méret</label><output class="pending" data-item="dimensions">—</output><span class="dimension-order">Magasság × szélesség × mélység</span></div>
              <div class="datum"><label>Láb</label><output class="pending" data-item="legs">—</output></div>
              <button class="datum" id="notesDatum" type="button" aria-haspopup="dialog" aria-controls="notesDialog" aria-expanded="false" hidden><span class="notes-label">Megjegyzés</span><span data-item="notes">—</span><span class="notes-hint">Koppints a teljes szöveghez</span></button>
              <div class="datum" id="fillerWidthDatum" hidden><label>Hézagtakaró szélessége</label><output data-item="filler_width">—</output></div>
            </div>
          </div>
          <footer class="info-footer"><div class="footer-metadata"><span>Beolvasva: <time id="scannedAt">—</time></span><span>prdID: <output id="productionId">—</output></span><span>Vonalkód: <output id="barcode">—</output></span><span>Korpusz: <output class="pending" data-item="cabinet">—</output></span></div><span id="lookupState">Beolvasásra vár</span></footer>
        </article>
    </section>
  </main>
      <dialog class="panel bom-panel" id="bomPanel" aria-labelledby="bomTitle" aria-describedby="bomItemCode bomItemDescription">
        <header class="panel-head"><div class="bom-heading"><div class="panel-title" id="bomTitle"><span class="panel-index">02</span> Darabjegyzék</div><span class="bom-count" id="bomCount">0</span></div><button class="reset-button bom-close" id="bomClose" type="button" aria-label="Darabjegyzék bezárása" autofocus>×</button></header>
        <div class="bom-item"><strong id="bomItemCode">Nincs beolvasott elem</strong><p id="bomItemDescription"></p></div>
        <div class="bom-wrap">
          <table class="bom-table"><thead><tr><th>#</th><th id="bomPartHeader">Cikkszám<div class="bom-column-resizer" id="bomColumnResizer" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Cikkszám oszlop szélessége" aria-valuemin="64" aria-valuenow="96" title="Húzd az oszlopszélesség állításához. Dupla kattintás: alaphelyzet."></div></th><th>Megnevezés</th><th>Mennyiség</th><th>Állapot</th></tr></thead><tbody id="bomBody"></tbody></table>
          <div class="empty-bom" id="emptyBom"><div><span class="empty-icon">≡</span><strong id="emptyBomTitle">Nincs beolvasott elem</strong><p id="emptyBomText">A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.</p></div></div>
        </div>
        <footer class="bom-review-footer" id="bomReviewFooter" hidden><p class="bom-review-message" id="bomReviewMessage">Ellenőrizd a beolvasott elem darabjegyzékét, majd erősítsd meg. A következő elem csak ezután olvasható be.</p><button class="reset-button bom-confirm" id="bomConfirm" type="button">Ellenőriztem, a darabjegyzék rendben</button></footer>
      </dialog>
  <div class="toast" id="toast" role="alert"></div>
  <dialog class="notes-dialog" id="notesDialog" aria-labelledby="notesDialogTitle" aria-describedby="notesFullText"><header class="notes-dialog-head"><h2 id="notesDialogTitle">Megjegyzés</h2><button class="reset-button" id="notesClose" type="button" aria-label="Megjegyzés bezárása" autofocus>Bezárás</button></header><p class="notes-context" id="notesContext"></p><div class="notes-full-text" id="notesFullText" tabindex="0"></div></dialog>
  <dialog class="damage-confirm" id="damageDialog" aria-labelledby="damageTitle" aria-describedby="damageItem damageExplanation"><h2 id="damageTitle">Sérült alkatrész jelölése</h2><p id="damageItem"></p><p id="damageExplanation">Sérültként jelölöd ezt a darabjegyzéktételt? A tétel az Összekészítő sérült alkatrészei közé kerül.</p><div class="damage-confirm-actions"><button class="reset-button" id="damageCancel" type="button" autofocus>Mégse</button><button class="reset-button" id="damageSubmit" type="button">Sérültként jelölés</button></div></dialog>
  <dialog class="fullscreen-help" id="fullscreenHelp" aria-labelledby="fullscreenHelpTitle"><h2 id="fullscreenHelpTitle">Teljes képernyő</h2><p>A böngésző most nem engedélyezte a teljes képernyőt. Próbáld közvetlenül a modul oldalán megnyomni a teljes képernyő gombot.</p><p>iPad: Safari → Megosztás → Hozzáadás a főképernyőhöz. Ha látható, hagyd bekapcsolva a „Megnyitás webalkalmazásként” lehetőséget, majd a főképernyő ikonjával indítsd el a modult.</p><form method="dialog"><button class="reset-button">Rendben</button></form></dialog>
  <div class="rotate"><div><b>↻</b><strong>Fordítsd fekvő helyzetbe a táblagépet</strong><p>Ez a munkafelület fekvő nézetre és egyetlen, görgetésmentes képernyőre készült.</p></div></div>
  <script>
    const initialState = {initial_state};
    document.querySelector('meta[name="theme-color"]').setAttribute('content', getComputedStyle(document.body).getPropertyValue('--bg').trim());
    const clientStateKey = {client_state_key};
    const cabinetImages = new Map(Object.entries({cabinet_images}));
    const cabinetImage = document.getElementById('cabinetImage');
    const connectorRules = {connector_rules}.map(rule => ({{...rule, match:new RegExp(rule.pattern)}}));
    const connectorImage = document.getElementById('connectorImage');
    const nettfrontColours = {nettfront_colours};
    const scannerState = document.getElementById('scannerState');
    const scannerHint = document.getElementById('scannerHint');
    const resetButton = document.getElementById('resetButton');
    const fullscreenButton = document.getElementById('fullscreenButton');
    const fullscreenHelp = document.getElementById('fullscreenHelp');
    const bomPanel = document.getElementById('bomPanel');
    const bomToggle = document.getElementById('bomToggle');
    const bomClose = document.getElementById('bomClose');
    const bomConfirm = document.getElementById('bomConfirm');
    const notesDatum = document.getElementById('notesDatum');
    const notesDialog = document.getElementById('notesDialog');
    const damageDialog = document.getElementById('damageDialog');
    const damageCancel = document.getElementById('damageCancel');
    const damageSubmit = document.getElementById('damageSubmit');
    const toast = document.getElementById('toast');
    let toastTimer;
    let busy = false;
    let scanBuffer = '';
    let scanOverflow = false;
    let lastScanKeyAt = 0;
    let currentState = initialState;
    let confirmationRequired = false;
    let selectedDamage = null;
    let damageBusy = false;
    const pendingScans = [];

    notesDatum.addEventListener('click', () => {{
      const note = String(currentState.item?.notes || '');
      if (busy || !note.trim()) return;
      clearScanBuffer();
      document.getElementById('notesFullText').textContent = note;
      document.getElementById('notesContext').textContent = [currentState.barcode, currentState.item?.part_number].filter(Boolean).join(' · ');
      notesDialog.showModal();
      document.getElementById('notesFullText').scrollTop = 0;
      notesDatum.setAttribute('aria-expanded', 'true');
      setBusy(busy);
    }});
    function finishClosingNotes() {{
      if (notesDatum.getAttribute('aria-expanded') !== 'true') return;
      notesDatum.setAttribute('aria-expanded', 'false');
      clearScanBuffer();
      setBusy(busy);
      void processScanQueue();
    }}
    function closeNotes() {{
      notesDialog.close();
      finishClosingNotes();
    }}
    document.getElementById('notesClose').addEventListener('click', closeNotes);
    notesDialog.addEventListener('cancel', event => {{ event.preventDefault(); closeNotes(); }});
    notesDialog.addEventListener('close', () => {{ if (!notesDialog.open) finishClosingNotes(); }});
    notesDialog.addEventListener('click', event => {{
      if (event.target !== notesDialog) return;
      const rect = notesDialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeNotes();
    }});

    function damageRequestId() {{
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 15) | 64;
      bytes[8] = (bytes[8] & 63) | 128;
      const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
      return [hex.slice(0,8), hex.slice(8,12), hex.slice(12,16), hex.slice(16,20), hex.slice(20)].join('-');
    }}
    function openDamage(index) {{
      if (busy || damageBusy || currentState.lookup_status !== 'ready') return;
      const row = currentState.bom[index];
      if (!row || (currentState.damaged_bom_indexes || []).includes(index)) return;
      clearScanBuffer();
      selectedDamage = {{ barcode:currentState.barcode, production_number:currentState.production_number || currentState.production_xml?.production_number,
        bom_index:index, bom_row:{{...row}}, request_id:damageRequestId() }};
      document.getElementById('damageItem').textContent = [row.part_number, row.description, String(row.quantity ?? '—') + ' db', currentState.barcode].filter(Boolean).join(' · ');
      damageDialog.showModal();
      damageCancel.focus();
      setBusy(busy);
    }}
    function closeDamage() {{
      if (damageBusy) return;
      damageDialog.close();
      selectedDamage = null;
      clearScanBuffer();
      setBusy(busy);
      void processScanQueue();
    }}
    damageCancel.addEventListener('click', closeDamage);
    damageDialog.addEventListener('cancel', event => {{ event.preventDefault(); closeDamage(); }});
    damageSubmit.addEventListener('click', async () => {{
      if (!selectedDamage || damageBusy || scanBuffer || scanOverflow) return;
      const selected = selectedDamage;
      damageBusy = true;
      damageSubmit.disabled = true;
      damageCancel.disabled = true;
      damageSubmit.textContent = 'Mentés…';
      try {{
        const response = await fetch('{DAMAGE_ROUTE}', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(selected) }});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'A sérült alkatrész mentése nem sikerült.');
        if (data.report.status === 'open') {{
          currentState = {{...currentState, damaged_bom_indexes:[...new Set([...(currentState.damaged_bom_indexes || []), selected.bom_index])]}};
          const wrap = document.querySelector('.bom-wrap');
          const scrollTop = wrap.scrollTop;
          renderBom(currentState.bom);
          wrap.scrollTop = scrollTop;
          saveClientState(currentState);
        }}
        damageBusy = false;
        closeDamage();
      }} catch (error) {{ showToast(error.message); }}
      finally {{
        damageBusy = false;
        damageSubmit.disabled = false;
        damageCancel.disabled = false;
        damageSubmit.textContent = 'Sérültként jelölés';
        setBusy(busy);
      }}
    }});

    function openBom() {{
      clearScanBuffer();
      bomPanel.classList.toggle('bom-review', confirmationRequired);
      bomClose.hidden = confirmationRequired;
      document.getElementById('bomReviewFooter').hidden = !confirmationRequired;
      bomPanel.setAttribute('aria-describedby', 'bomItemCode bomItemDescription' + (confirmationRequired ? ' bomReviewMessage' : ''));
      if (!bomPanel.open) bomPanel.showModal();
      bomToggle.setAttribute('aria-expanded', 'true');
      setPartColumnWidth(bomPartHeader.style.width ? parseFloat(bomPartHeader.style.width) : defaultPartWidth);
      (confirmationRequired ? bomConfirm : bomClose).focus({{ preventScroll:true }});
      if (confirmationRequired) {{
        const resetScroll = () => {{
          bomPanel.scrollTop = 0;
          bomPanel.querySelector('.bom-wrap').scrollTop = 0;
        }};
        resetScroll();
        requestAnimationFrame(() => {{ if (bomPanel.open && confirmationRequired) resetScroll(); }});
      }}
    }}
    function closeBom() {{
      if (confirmationRequired) return;
      if (bomPanel.open) bomPanel.close();
      bomToggle.setAttribute('aria-expanded', 'false');
      clearScanBuffer();
    }}
    bomToggle.addEventListener('click', openBom);
    bomClose.addEventListener('click', closeBom);
    bomPanel.addEventListener('cancel', event => {{
      event.preventDefault();
      closeBom();
    }});
    bomPanel.addEventListener('click', event => {{
      if (event.target !== bomPanel) return;
      const rect = bomPanel.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeBom();
    }});
    bomConfirm.addEventListener('click', () => {{
      if (!confirmationRequired || notesDialog.open || damageDialog.open || damageBusy || scanBuffer || scanOverflow) return;
      confirmationRequired = false;
      currentState = {{ ...currentState, bom_confirmation_required:false }};
      closeBom();
      renderState(currentState);
      void processScanQueue();
    }});

    function fullscreenElement() {{ return document.fullscreenElement || document.webkitFullscreenElement; }}
    function updateFullscreenButton() {{
      const active = Boolean(fullscreenElement());
      fullscreenButton.setAttribute('aria-pressed', String(active));
      fullscreenButton.title = active ? 'Kilépés a teljes képernyőből' : 'Teljes képernyő';
      fullscreenButton.setAttribute('aria-label', fullscreenButton.title);
    }}
    fullscreenButton.addEventListener('click', async () => {{
      try {{
        if (fullscreenElement()) {{
          if (document.exitFullscreen) await document.exitFullscreen();
          else if (document.webkitExitFullscreen) await document.webkitExitFullscreen();
        }} else if (document.documentElement.requestFullscreen) {{
          await document.documentElement.requestFullscreen({{ navigationUI:'hide' }});
        }} else if (document.documentElement.webkitRequestFullscreen) {{
          await document.documentElement.webkitRequestFullscreen();
        }} else fullscreenHelp.showModal();
      }} catch (error) {{ if (!fullscreenHelp.open) fullscreenHelp.showModal(); }}
      updateFullscreenButton();
    }});
    document.addEventListener('fullscreenchange', updateFullscreenButton);
    document.addEventListener('webkitfullscreenchange', updateFullscreenButton);
    updateFullscreenButton();

    function cabinetImageUrl(item) {{
      const code = String(item?.part_number || '').trim().toUpperCase().replace(/_N$/, '');
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
    function frontColourKey(value) {{
      return String(value || '').trim().toLowerCase().normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').replace(/\\bfolias\\b/g, '').replace(/[^a-z0-9]/g, '');
    }}
    function renderFront(state) {{
      const features = state.production_xml?.features || {{}};
      const model = String(features['Front típus'] || '').trim();
      const colour = ['Front színe', 'Front szín felső', 'Keretléc szín']
        .map(key => String(features[key] || '').trim()).find(Boolean) || '';
      const modelKey = frontColourKey(model);
      const names = Object.hasOwn(nettfrontColours, modelKey) ? nettfrontColours[modelKey] : null;
      const colourKey = frontColourKey(colour);
      const counterpart = names && Object.hasOwn(names, colourKey) ? names[colourKey] : '';
      const card = document.getElementById('frontDatum');
      card.hidden = !model && !colour;
      card.title = [model, colour, counterpart ? 'Nettfront: ' + counterpart : ''].filter(Boolean).join(' | ');
      document.getElementById('frontModel').textContent = model || '—';
      document.getElementById('frontModel').hidden = !model;
      document.getElementById('frontColourLine').hidden = !colour;
      document.getElementById('frontColour').textContent = colour;
      document.getElementById('frontNettfront').textContent = counterpart ? '(Nettfront: ' + counterpart + ')' : '';
      document.getElementById('frontNettfront').hidden = !counterpart;
      document.querySelector('.primary-info').classList.toggle('has-front', Boolean(model || colour));
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
    for (const image of [cabinetImage, connectorImage]) {{
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
      if (!bomPanel.open) return;
      const headers = bomTable.tHead.rows[0].cells;
      const maxWidth = Math.max(minPartWidth, Math.floor(bomTable.getBoundingClientRect().width
        - headers[0].getBoundingClientRect().width - headers[3].getBoundingClientRect().width - headers[4].getBoundingClientRect().width - 160));
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
    if (window.ResizeObserver) new ResizeObserver(() => setPartColumnWidth(parseFloat(bomPartHeader.style.width) || defaultPartWidth)).observe(bomTable);
    else window.addEventListener('resize', () => setPartColumnWidth(parseFloat(bomPartHeader.style.width) || defaultPartWidth));

    function setBusy(value) {{
      busy = value;
      resetButton.disabled = value || confirmationRequired || notesDialog.open || damageDialog.open || damageBusy;
      scannerState.setAttribute('aria-busy', String(value));
      scannerHint.textContent = notesDialog.open ? 'Megjegyzés megnyitva' : (confirmationRequired ? 'Erősítsd meg a darabjegyzéket' : (value ? 'Darabjegyzék betöltése…' : 'Csippantsd be a vonalkódot'));
    }}

    function valueOrPending(value, fallback = '—') {{ return value ? String(value) : fallback; }}
    function formatDate(value) {{
      if (!value) return '—';
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('hu-HU', {{ hour:'2-digit', minute:'2-digit', second:'2-digit' }});
    }}
    function showToast(message) {{ (damageDialog.open ? damageDialog : (bomPanel.open ? bomPanel : document.body)).appendChild(toast); toast.textContent = message; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 3200); }}
    function renderBom(rows) {{
      const body = document.getElementById('bomBody');
      body.replaceChildren();
      rows.forEach((row, index) => {{
        const tr = document.createElement('tr');
        [index + 1, row.part_number || '—', row.description || '—', row.quantity ?? '—'].forEach(value => {{ const td = document.createElement('td'); td.textContent = value; td.title = String(value); tr.appendChild(td); }});
        const damaged = (currentState.damaged_bom_indexes || []).includes(index);
        tr.classList.toggle('is-damaged', damaged);
        const action = document.createElement('td');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'reset-button bom-damage-button';
        button.textContent = damaged ? 'Jelezve' : 'Sérült';
        button.disabled = damaged || currentState.lookup_status !== 'ready' || !row.part_number || row.quantity == null;
        button.setAttribute('aria-label', (damaged ? 'Sérültként jelezve: ' : 'Sérültként jelölés: ') + (row.part_number || row.description || 'Tétel'));
        button.addEventListener('click', () => openDamage(index));
        action.appendChild(button);
        tr.appendChild(action);
        body.appendChild(tr);
      }});
      document.getElementById('bomCount').textContent = rows.length;
      document.getElementById('bomToggleCount').textContent = rows.length;
      document.getElementById('emptyBom').hidden = rows.length > 0;
      document.querySelector('.bom-wrap').scrollTop = 0;
    }}
    function renderState(state) {{
      currentState = state;
      confirmationRequired = state.lookup_status === 'ready' && state.bom_confirmation_required === true;
      const hasScan = Boolean(state.barcode);
      const pending = state.lookup_status === 'api_pending';
      const ready = state.lookup_status === 'ready';
      const failed = state.lookup_status === 'error';
      document.getElementById('barcode').textContent = hasScan ? state.barcode : '—';
      document.getElementById('scannedAt').textContent = formatDate(state.scanned_at);
      document.getElementById('productionId').textContent = valueOrPending(state.production_xml && state.production_xml.production_number);
      document.getElementById('scanStatus').textContent = confirmationRequired ? 'Ellenőrzés szükséges' : (pending ? 'Darabjegyzék betöltése…' : (failed ? 'Sikertelen lekérés' : 'Scanner készen áll'));
      document.getElementById('lookupState').textContent = confirmationRequired ? 'Megerősítésre vár' : (pending ? 'Betöltés…' : (failed ? 'Sikertelen lekérés' : (ready ? 'Darabjegyzék betöltve' : 'Beolvasásra vár')));
      document.getElementById('bomItemCode').textContent = hasScan ? [state.barcode, state.item?.part_number].filter(Boolean).join(' · ') : 'Nincs beolvasott elem';
      document.getElementById('bomItemDescription').textContent = state.item?.description || '';
      document.getElementById('emptyBomTitle').textContent = pending ? 'Darabjegyzék betöltése…' : (failed ? 'Sikertelen lekérés' : (ready ? 'Nincs darabjegyzék' : 'Nincs beolvasott elem'));
      document.getElementById('emptyBomText').textContent = pending ? 'A beolvasott elem tételeinek lekérése folyamatban van.' : (failed ? state.error_message || 'Olvasd be újra a vonalkódot.' : (ready ? 'A beolvasott elemhez nem érkezett darabjegyzéktétel.' : 'A scannerrel olvasd be az elem vonalkódját. A hozzá tartozó darabjegyzék itt fog megjelenni.'));
      document.querySelectorAll('[data-item]').forEach(output => {{
        const value = state.item && state.item[output.dataset.item];
        output.textContent = valueOrPending(value, output.dataset.item === 'description' && pending ? 'API-kapcsolatra vár' : '—');
        output.title = valueOrPending(value);
        output.classList.toggle('pending', !value);
      }});
      const colourKey = String(state.item?.color || '').trim().toLowerCase();
      document.getElementById('colorDatum').classList.toggle('colour-white', colourKey === 'fehér');
      document.getElementById('colorDatum').classList.toggle('colour-anthracite', colourKey === 'antracit kr.');
      renderFront(state);
      const hasNotes = Boolean(String(state.item?.notes || '').trim());
      document.getElementById('notesDatum').hidden = !hasNotes;
      const hasFillerWidth = Boolean(state.item && state.item.filler_width);
      document.getElementById('fillerWidthDatum').hidden = !hasFillerWidth;
      document.getElementById('secondaryInfo').classList.toggle('has-filler', hasFillerWidth);
      document.getElementById('secondaryInfo').style.setProperty('--detail-columns', 1 + Number(hasNotes) + Number(hasFillerWidth));
      renderAssetImage(cabinetImage, cabinetImageUrl(state.item), [state.item?.part_number, state.item?.handing].filter(Boolean).join(' · '));
      const partCode = String(state.item?.part_number || '').trim().toUpperCase();
      const connector = connectorRules.find(rule => rule.match.test(partCode));
      document.getElementById('connectorDatum').hidden = !connector;
      document.querySelector('.primary-info').classList.toggle('has-connector', Boolean(connector));
      document.getElementById('connectorOrientation').textContent = connector?.orientation || '—';
      renderAssetImage(connectorImage, connector?.image_url || '', connector ? connector.orientation + ' összekötő' : '');
      renderBom(Array.isArray(state.bom) ? state.bom : []);
      saveClientState(state);
      setBusy(busy);
      if (confirmationRequired) openBom();
    }}
    async function send(url, payload) {{
      const response = await fetch(url, {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload || {{}}) }});
      const data = await response.json().catch(() => ({{ ok:false, error:'Érvénytelen szerverválasz.' }}));
      if (!response.ok || !data.ok) throw new Error(data.error || 'A művelet nem sikerült.');
      return data.state;
    }}
    async function processScanQueue() {{
      if (busy || confirmationRequired || notesDialog.open || damageDialog.open || damageBusy || !pendingScans.length) return;
      const barcode = pendingScans.shift();
      closeBom();
      setBusy(true);
      const scannedAt = new Date().toISOString();
      renderState({{ barcode, scanned_at:scannedAt, lookup_status:'api_pending', bom:[] }});
      try {{
        const state = await send('{SCAN_ROUTE}', {{ barcode }});
        state.bom_confirmation_required = state.lookup_status === 'ready' && Math.random() < 1 / 50;
        renderState(state);
      }} catch (error) {{ renderState({{ barcode, scanned_at:scannedAt, lookup_status:'error', error_message:error.message, item:{{}}, bom:[] }}); showToast(error.message); }} finally {{ setBusy(false); void processScanQueue(); }}
    }}
    function clearScanBuffer() {{ scanBuffer = ''; scanOverflow = false; lastScanKeyAt = 0; }}
    document.addEventListener('keydown', event => {{
      if (fullscreenHelp.open || notesDialog.open) return;
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
        if (barcode) {{
          if (damageDialog.open || damageBusy) {{ showToast('Előbb zárd le a sérült alkatrész jelölését, majd olvasd be újra az elemet.'); return; }}
          if (confirmationRequired) {{ showToast('Előbb erősítsd meg a darabjegyzéket, majd olvasd be újra az elemet.'); return; }}
          pendingScans.push(barcode); void processScanQueue();
        }}
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
    resetButton.addEventListener('click', () => {{ if (busy || confirmationRequired || notesDialog.open || damageDialog.open || damageBusy) return; closeBom(); clearScanBuffer(); pendingScans.length = 0; renderState(initialState); }});
    document.addEventListener('pointerdown', clearScanBuffer);
    window.addEventListener('blur', clearScanBuffer);
    document.addEventListener('visibilitychange', () => {{ if (document.hidden) clearScanBuffer(); }});
    renderState(restoreClientState() || initialState);
  </script>
</body>
</html>"""
    return page.encode("utf-8")
