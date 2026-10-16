"""HTML views for damaged-item reporting and administration."""

from __future__ import annotations

import html
from datetime import datetime


WORKER_ROUTE = "/apps/serult-elemek"
CREATE_ROUTE = f"{WORKER_ROUTE}/bejelentes"
IMAGE_PREFIX = f"{WORKER_ROUTE}/kep"
ADMIN_ROUTE = "/apps/admin-serult-elemek"
ADMIN_DELETE_PREFIX = f"{ADMIN_ROUTE}/torles"
WORKER_ACCESS_USER_IDS = frozenset({"manufacturer", "gyartas-vezerlo"})
ADMIN_ACCESS_USER_IDS = frozenset({"gyartas-vezerlo"})


def render_worker_page(reports: list[dict], user_name: str, message: str = "", success: bool = False) -> bytes:
    """Render the worker report flow and report history."""
    notice = _notice(message, success)
    report_cards = _report_cards(reports, admin=False)
    page = _page_shell(
        title="Sérült elem bejelentése",
        eyebrow="Újragyártási igény",
        heading="Sérült elem? Rögzítsd néhány lépésben.",
        lead="Csippantsd be az elemet, dokumentáld a sérülést, majd zárd le a bejelentést. A korábbi bejelentések itt bármikor visszanézhetők.",
        user_name=user_name,
        body=f"""
          {notice}
          <section class="damage-actions">
            <button class="damage-primary" id="openDamageFlow" type="button">
              <span class="damage-primary-icon">+</span>
              <span><strong>Sérült elem felvitele</strong><small>Új bejelentés indítása</small></span>
            </button>
            <div class="damage-quick-note"><span></span>A beküldött bejelentést csak adminisztrátor törölheti.</div>
          </section>

          <section class="damage-flow" id="damageFlow" hidden>
            <div class="damage-flow-head">
              <div><span class="damage-step-kicker">01 · Azonosítás</span><h2>Elem becsippantása</h2></div>
              <button class="damage-icon-button" id="closeDamageFlow" type="button" aria-label="Bezárás">×</button>
            </div>
            <div class="scan-stage" id="scanStage">
              <div class="scan-visual"><i></i><span></span><b></b></div>
              <div>
                <span class="scan-state"><i></i> Várakozás a csippantásra</span>
                <h3>Olvasd be az elem vonalkódját</h3>
                <p>A vonalkódolvasó és az API-kapcsolat egy későbbi ütemben készül el. A gombbal most a teljes felület kipróbálható.</p>
              </div>
              <button class="damage-secondary" id="simulateScan" type="button">Demo becsippantás</button>
            </div>

            <form class="damage-form" id="damageReportForm" action="{CREATE_ROUTE}" method="post" enctype="multipart/form-data">
              <input type="hidden" name="barcode" id="barcode" />
              <input type="hidden" name="part_number" id="partNumber" />
              <input type="hidden" name="description" id="description" />
              <input type="hidden" name="order_number" id="orderNumber" />
              <input type="hidden" name="production_number" id="productionNumber" />
              <div class="identified-card" id="identifiedCard" hidden>
                <div class="identified-check">✓</div>
                <div class="identified-main"><span>Azonosított elem · demo adat</span><strong id="itemDescription">–</strong><small id="itemPartNumber">–</small></div>
                <dl><div><dt>Gyártás</dt><dd id="itemProduction">–</dd></div><div><dt>Rendelés</dt><dd id="itemOrder">–</dd></div></dl>
              </div>
              <fieldset id="reportFields" disabled>
                <div class="damage-form-head"><span class="damage-step-kicker">02 · Dokumentálás</span><h2>Mi történt az elemmel?</h2></div>
                <label class="damage-field">
                  <span>Ki volt a felelős a sérülésért? <b>Kötelező</b></span>
                  <input type="text" name="responsible_person" id="responsiblePerson" required maxlength="120" autocomplete="off" placeholder="A felelős személy neve" />
                </label>
                <label class="damage-field">
                  <span>Ki rögzítette? <b>Kötelező</b></span>
                  <input type="text" name="recorded_by" id="recordedBy" required maxlength="120" autocomplete="off" placeholder="A rögzítő személy neve" />
                </label>
                <label class="damage-field">
                  <span>Megjegyzés <b>Kötelező</b></span>
                  <textarea name="note" id="damageNote" required maxlength="1000" placeholder="Írd le röviden, hol és hogyan sérült meg az elem…"></textarea>
                  <small><span id="noteCount">0</span>/1000 karakter</small>
                </label>
                <label class="photo-upload" id="photoUpload">
                  <input type="file" id="damageCamera" accept="image/*" capture="environment" />
                  <input type="file" name="damage_image" id="damageImage" accept="image/*" multiple required hidden />
                  <span class="photo-icon">⌁</span>
                  <strong>Kép készítése</strong>
                  <small>Koppints ide a hátlapi kamera megnyitásához · legalább 1 kép kötelező</small>
                  <div class="photo-previews" id="photoPreviews" hidden></div>
                  <span class="photo-selection" id="photoSelection" hidden></span>
                </label>
                <div class="damage-submit-row">
                  <span>A lezárás után a bejelentés bekerül az adminisztrációs listába.</span>
                  <button class="damage-primary compact" type="submit" id="closeReport" disabled>Lezárom</button>
                </div>
              </fieldset>
            </form>
          </section>

          <section class="damage-history">
            <div class="damage-section-head"><div><span class="damage-step-kicker">Előzmények</span><h2>Korábbi bejelentések</h2></div><span class="damage-count">{len(reports)} bejelentés</span></div>
            <div class="damage-report-grid">{report_cards}</div>
          </section>
        """,
        script=_worker_script(),
    )
    return page.encode("utf-8")


def render_admin_page(reports: list[dict], user_name: str, message: str = "", success: bool = False) -> bytes:
    """Render the admin overview with deletion controls."""
    today = datetime.now().date().isoformat()
    today_count = sum(1 for item in reports if str(item.get("created_at", "")).startswith(today))
    report_cards = _report_cards(reports, admin=True)
    page = _page_shell(
        title="Sérült elemek · Admin",
        eyebrow="Adminisztráció",
        heading="Sérült elemek és újragyártási igények",
        lead="Az összes csomagolási és raktári bejelentés egy helyen. Itt ellenőrizhető a dokumentáció, és kizárólag innen törölhető téves bejegyzés.",
        user_name=user_name,
        body=f"""
          {_notice(message, success)}
          <section class="damage-admin-stats">
            <article><span>Összes bejelentés</span><strong>{len(reports)}</strong><small>rögzített tétel</small></article>
            <article><span>Ma érkezett</span><strong>{today_count}</strong><small>új bejelentés</small></article>
            <article><span>Integráció</span><strong class="text-status">Előkészítve</strong><small>csippantás + API később</small></article>
          </section>
          <section class="damage-history admin-history">
            <div class="damage-section-head"><div><span class="damage-step-kicker">Bejelentések</span><h2>Újragyártási lista</h2></div><a class="damage-secondary" href="{WORKER_ROUTE}">Dolgozói nézet</a></div>
            <div class="damage-report-grid">{report_cards}</div>
          </section>
        """,
        script="""
          document.querySelectorAll('[data-delete-report]').forEach(function(form){
            form.addEventListener('submit', function(event){
              if(!window.confirm('Biztosan törlöd ezt a bejelentést? Ez a művelet nem vonható vissza.')) event.preventDefault();
            });
          });
        """,
        admin=True,
    )
    return page.encode("utf-8")


def _report_cards(reports: list[dict], admin: bool) -> str:
    if not reports:
        return '<div class="damage-empty"><span>◇</span><h3>Még nincs bejelentés</h3><p>Az új sérült elemek itt fognak megjelenni.</p></div>'
    cards: list[str] = []
    for report in reports:
        report_id = html.escape(str(report.get("id", "")))
        item = report.get("item", {}) if isinstance(report.get("item"), dict) else {}
        description = html.escape(str(item.get("description", "") or "Azonosítatlan elem"))
        part_number = html.escape(str(item.get("part_number", "") or "API-adatra vár"))
        production = html.escape(str(item.get("production_number", "") or "–"))
        order = html.escape(str(item.get("order_number", "") or "–"))
        note = html.escape(str(report.get("note", "")))
        responsible = html.escape(str(report.get("responsible_person", "") or "Nincs megadva"))
        creator = html.escape(str(report.get("created_by", "") or "Ismeretlen"))
        created = _format_datetime(report.get("created_at"))
        images = _report_images(report)
        image_links = "".join(
            f'<a href="{IMAGE_PREFIX}/{report_id}/{index}" target="_blank" rel="noopener"><img src="{IMAGE_PREFIX}/{report_id}/{index}" alt="Sérülés fotója {index + 1}" loading="lazy" /></a>'
            for index, _image in enumerate(images)
        )
        gallery = f'<div class="damage-report-gallery">{image_links}<span>{len(images)} kép</span></div>'
        delete_html = ""
        if admin:
            delete_html = f'<form action="{ADMIN_DELETE_PREFIX}/{report_id}" method="post" data-delete-report><button class="damage-delete" type="submit">Törlés</button></form>'
        cards.append(f"""
          <article class="damage-report-card">
            {gallery}
            <div class="damage-report-content">
              <div class="damage-report-top"><span class="damage-status">Újragyártás szükséges</span><time>{html.escape(created)}</time></div>
              <h3>{description}</h3><p class="damage-part">{part_number}</p>
              <div class="damage-report-meta"><span>Gyártás <b>{production}</b></span><span>Rendelés <b>{order}</b></span><span>Felelős <b>{responsible}</b></span><span>Rögzítette <b>{creator}</b></span></div>
              <blockquote>{note}</blockquote>
              {delete_html}
            </div>
          </article>
        """)
    return "".join(cards)


def _report_images(report: dict) -> list[dict]:
    images = report.get("images")
    if isinstance(images, list):
        return [item for item in images if isinstance(item, dict) and str(item.get("name", "")).strip()]
    return [{}] if str(report.get("image_name", "")).strip() else []


def _notice(message: str, success: bool) -> str:
    if not str(message or "").strip():
        return ""
    kind = "success" if success else "error"
    return f'<div class="damage-notice {kind}">{html.escape(str(message))}</div>'


def _format_datetime(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value or "")
    return parsed.strftime("%Y. %m. %d. · %H:%M")


def _page_shell(*, title: str, eyebrow: str, heading: str, lead: str, user_name: str, body: str, script: str, admin: bool = False) -> str:
    body_class = " damage-admin" if admin else ""
    return f"""<!doctype html>
<html lang="hu"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Divian-HUB | {html.escape(title)}</title><link rel="stylesheet" href="/styles.css"/>
<style>{_styles()}</style></head><body class="damage-page{body_class}">
<div class="damage-shell"><header class="damage-topbar"><a class="damage-brand" href="/"><i></i><span><strong>Divian-HUB</strong><small>Sérült elem kezelés</small></span></a><div class="damage-user"><span>{html.escape(user_name)}</span><a href="/">Modulok</a></div></header>
<main><section class="damage-hero"><div><span class="damage-eyebrow">{html.escape(eyebrow)}</span><h1>{html.escape(heading)}</h1><p>{html.escape(lead)}</p></div><div class="damage-hero-mark" aria-hidden="true"><span>!</span></div></section>{body}</main></div>
<script>{script}</script></body></html>"""


def _worker_script() -> str:
    return """
      const flow=document.getElementById('damageFlow'), openButton=document.getElementById('openDamageFlow');
      const reportFields=document.getElementById('reportFields'), closeReport=document.getElementById('closeReport');
      const note=document.getElementById('damageNote'), camera=document.getElementById('damageCamera'), image=document.getElementById('damageImage'), responsible=document.getElementById('responsiblePerson'), recordedBy=document.getElementById('recordedBy');
      let selectedDamageFiles=[];
      function validate(){ closeReport.disabled=!(responsible.value.trim() && recordedBy.value.trim() && note.value.trim() && selectedDamageFiles.length>=1); }
      openButton.addEventListener('click',()=>{flow.hidden=false;openButton.setAttribute('aria-expanded','true');flow.scrollIntoView({behavior:'smooth',block:'start'});});
      document.getElementById('closeDamageFlow').addEventListener('click',()=>{flow.hidden=true;openButton.setAttribute('aria-expanded','false');});
      document.getElementById('simulateScan').addEventListener('click',function(){
        const data={barcode:'DEMO-240924-001',part_number:'NFA_ANT_KAF_718x447',description:'Antónia fóliás front 718 × 447 mm',order_number:'V-2026-1842',production_number:'261478'};
        Object.keys(data).forEach(key=>{const map={part_number:'partNumber',order_number:'orderNumber',production_number:'productionNumber'};document.getElementById(map[key]||key).value=data[key];});
        document.getElementById('itemDescription').textContent=data.description; document.getElementById('itemPartNumber').textContent=data.part_number;
        document.getElementById('itemProduction').textContent=data.production_number; document.getElementById('itemOrder').textContent=data.order_number;
        document.getElementById('scanStage').classList.add('is-complete'); document.getElementById('identifiedCard').hidden=false; reportFields.disabled=false;
        reportFields.scrollIntoView({behavior:'smooth',block:'start'}); this.textContent='Becsippantva'; this.disabled=true;
      });
      note.addEventListener('input',()=>{document.getElementById('noteCount').textContent=note.value.length;validate();});
      responsible.addEventListener('input',validate);
      recordedBy.addEventListener('input',validate);
      let previewUrls=[];
      function syncImageInput(){const transfer=new DataTransfer();selectedDamageFiles.forEach(file=>transfer.items.add(file));image.files=transfer.files;}
      function renderSelectedImages(){
        const previews=document.getElementById('photoPreviews'), selection=document.getElementById('photoSelection'); previewUrls.forEach(url=>URL.revokeObjectURL(url));previewUrls=[];previews.replaceChildren();
        selectedDamageFiles.forEach((file,index)=>{
          const item=document.createElement('span');item.className='photo-preview-item';
          const preview=document.createElement('img'),previewUrl=URL.createObjectURL(file);previewUrls.push(previewUrl);preview.src=previewUrl;preview.alt='A sérülés előnézete '+(index+1);
          const remove=document.createElement('button');remove.type='button';remove.className='photo-remove';remove.setAttribute('aria-label',(index+1)+'. kép eltávolítása');remove.textContent='×';
          remove.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();selectedDamageFiles.splice(index,1);syncImageInput();renderSelectedImages();});
          item.append(preview,remove);previews.appendChild(item);
        });
        const count=selectedDamageFiles.length; previews.hidden=!count; selection.hidden=!count; selection.textContent=count+' fotó elkészült · újabb fotóhoz koppints ide';
        document.getElementById('photoUpload').classList.toggle('has-image',!!count);validate();
      }
      camera.addEventListener('change',()=>{selectedDamageFiles.push(...Array.from(camera.files||[]));camera.value='';syncImageInput();renderSelectedImages();});
    """


def _styles() -> str:
    return """
      :root{--d-ink:#17201d;--d-muted:#68736f;--d-green:#0f7559;--d-green2:#18a47c;--d-mint:#e7f5ef;--d-line:#dce7e2;--d-card:#fff;--d-bg:#f3f6f4;--d-danger:#b33a35}
      *{box-sizing:border-box}.damage-page{margin:0;background:var(--d-bg);color:var(--d-ink);font-family:Manrope,Arial,sans-serif}.damage-shell{min-height:100vh;background:radial-gradient(circle at 88% 0,rgba(24,164,124,.12),transparent 30%),linear-gradient(180deg,#f9fbfa 0,#f1f5f3 100%)}
      .damage-topbar{height:78px;display:flex;align-items:center;justify-content:space-between;padding:0 clamp(20px,5vw,72px);border-bottom:1px solid var(--d-line);background:rgba(255,255,255,.82);backdrop-filter:blur(16px);position:sticky;top:0;z-index:20}.damage-brand{display:flex;align-items:center;gap:12px;color:inherit;text-decoration:none}.damage-brand>i{width:30px;height:30px;border:8px solid var(--d-green);border-radius:9px;transform:rotate(45deg)}.damage-brand span{display:flex;flex-direction:column}.damage-brand strong{font-size:15px;letter-spacing:.02em}.damage-brand small{font-size:11px;color:var(--d-muted)}.damage-user{display:flex;align-items:center;gap:14px;font-size:12px;color:var(--d-muted)}.damage-user a{padding:9px 14px;border:1px solid var(--d-line);border-radius:10px;color:var(--d-ink);text-decoration:none;background:#fff}
      .damage-page main{width:min(1180px,calc(100% - 36px));margin:0 auto;padding:54px 0 90px}.damage-hero{display:grid;grid-template-columns:minmax(0,780px) 120px;justify-content:space-between;align-items:center;gap:30px;margin-bottom:34px}.damage-eyebrow,.damage-step-kicker{display:block;color:var(--d-green);font-size:11px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin-bottom:9px}.damage-hero h1{font-family:'Space Grotesk',Manrope,sans-serif;font-size:clamp(35px,5vw,62px);line-height:1.03;letter-spacing:-.045em;margin:0 0 18px;max-width:790px}.damage-hero p{color:var(--d-muted);font-size:16px;line-height:1.7;margin:0;max-width:720px}.damage-hero-mark{width:112px;height:112px;border-radius:32px;background:var(--d-green);display:grid;place-items:center;box-shadow:0 24px 60px rgba(15,117,89,.22);transform:rotate(5deg)}.damage-hero-mark span{font:800 58px/1 'Space Grotesk';color:#fff;transform:rotate(-5deg)}
      .damage-notice{padding:14px 18px;border-radius:14px;margin:0 0 22px;font-size:14px;font-weight:700}.damage-notice.success{background:#dff5eb;color:#096044}.damage-notice.error{background:#fde8e6;color:#8c2925}.damage-actions{display:flex;align-items:center;gap:22px;margin-bottom:30px}.damage-primary{border:0;border-radius:18px;background:linear-gradient(135deg,var(--d-green),var(--d-green2));color:#fff;padding:17px 22px;display:inline-flex;align-items:center;gap:14px;box-shadow:0 16px 38px rgba(15,117,89,.24);cursor:pointer;text-align:left}.damage-primary-icon{width:35px;height:35px;border-radius:11px;background:rgba(255,255,255,.16);display:grid;place-items:center;font-size:24px}.damage-primary strong,.damage-primary small{display:block}.damage-primary strong{font-size:15px}.damage-primary small{opacity:.75;margin-top:2px}.damage-primary.compact{padding:14px 22px;justify-content:center;font-weight:800}.damage-primary:disabled{filter:grayscale(.55);opacity:.45;cursor:not-allowed;box-shadow:none}.damage-quick-note{font-size:12px;color:var(--d-muted);display:flex;align-items:center;gap:8px}.damage-quick-note span{width:7px;height:7px;border-radius:50%;background:#f2a93b}
      .damage-flow{background:var(--d-card);border:1px solid var(--d-line);border-radius:26px;padding:clamp(22px,4vw,42px);box-shadow:0 24px 70px rgba(28,52,43,.08);margin-bottom:48px}.damage-flow-head,.damage-section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}.damage-flow h2,.damage-history h2{font:700 clamp(24px,3vw,34px)/1.1 'Space Grotesk',Manrope,Arial,sans-serif;margin:0}.damage-icon-button{border:1px solid var(--d-line);background:#fff;width:40px;height:40px;border-radius:12px;font-size:24px;color:var(--d-muted);cursor:pointer}.scan-stage{margin-top:25px;border:1px dashed #a8bbb3;border-radius:22px;background:#f7faf8;padding:26px;display:grid;grid-template-columns:92px 1fr auto;align-items:center;gap:24px}.scan-visual{width:88px;height:88px;border-radius:22px;background:#17352d;position:relative;overflow:hidden}.scan-visual i,.scan-visual b{position:absolute;left:22px;right:22px;height:4px;background:#d9fff2;border-radius:3px}.scan-visual i{top:27px}.scan-visual b{bottom:27px}.scan-visual span{position:absolute;top:12px;bottom:12px;width:2px;background:#57e4b7;left:50%;box-shadow:0 0 14px #57e4b7;animation:scan 1.7s infinite alternate ease-in-out}.scan-stage.is-complete{border-style:solid;border-color:#9bd6c1;background:#effaf6}.scan-stage h3{font-size:18px;margin:8px 0 5px}.scan-stage p{color:var(--d-muted);font-size:13px;line-height:1.55;margin:0;max-width:620px}.scan-state{font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:#aa7015}.scan-state i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#f1a62e;box-shadow:0 0 0 5px rgba(241,166,46,.13)}.damage-secondary{border:1px solid var(--d-line);background:#fff;color:var(--d-ink);padding:12px 16px;border-radius:12px;font-size:12px;font-weight:800;text-decoration:none;cursor:pointer;white-space:nowrap}
      .damage-form fieldset{border:0;padding:0;margin:0}.damage-form fieldset:disabled{display:none}.identified-card{margin:18px 0 4px;background:#eaf8f2;border:1px solid #bfe6d7;border-radius:18px;padding:18px;display:grid;grid-template-columns:42px 1fr auto;align-items:center;gap:14px}.identified-card[hidden]{display:none}.identified-check{width:38px;height:38px;border-radius:12px;background:var(--d-green);color:#fff;display:grid;place-items:center;font-weight:900}.identified-main span,.identified-main strong,.identified-main small{display:block}.identified-main span{color:var(--d-green);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.identified-main strong{margin:4px 0;font-size:15px}.identified-main small{color:var(--d-muted)}.identified-card dl{display:flex;gap:28px;margin:0}.identified-card dl div{display:flex;flex-direction:column}.identified-card dt{font-size:10px;color:var(--d-muted);text-transform:uppercase}.identified-card dd{margin:4px 0 0;font-weight:800;font-size:13px}.damage-form-head{margin:30px 0 18px}.damage-field>span{display:flex;justify-content:space-between;font-weight:800;font-size:13px;margin-bottom:9px}.damage-field b{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--d-danger);background:#fdecea;padding:4px 7px;border-radius:6px}.damage-field textarea{width:100%;min-height:120px;resize:vertical;border:1px solid var(--d-line);border-radius:15px;padding:15px;font:inherit;outline:none;background:#fbfcfc}.damage-field textarea:focus{border-color:var(--d-green);box-shadow:0 0 0 4px rgba(15,117,89,.1)}.damage-field>small{display:block;text-align:right;color:var(--d-muted);margin-top:6px}.photo-upload{margin-top:18px;min-height:150px;border:1px dashed #a8bbb3;border-radius:18px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;cursor:pointer;background:#fafcfb;position:relative;overflow:hidden}.photo-upload input{position:absolute;opacity:0;inset:0;width:100%;cursor:pointer}.photo-upload strong{font-size:14px}.photo-upload small{color:var(--d-muted)}.photo-icon{font-size:30px;color:var(--d-green)}.photo-upload img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.photo-upload.has-image:after{content:'Kép kiválasztva · kattints a cseréhez';position:absolute;left:12px;bottom:12px;background:rgba(18,31,27,.82);color:#fff;padding:8px 11px;border-radius:9px;font-size:11px;font-weight:700}.damage-submit-row{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-top:20px;padding-top:20px;border-top:1px solid var(--d-line)}.damage-submit-row>span{font-size:12px;color:var(--d-muted)}
      .damage-history{margin-top:46px}.damage-count{font-size:12px;font-weight:800;color:var(--d-green);background:var(--d-mint);padding:9px 12px;border-radius:10px}.damage-report-grid{display:grid;gap:16px;margin-top:20px}.damage-report-card{display:grid;grid-template-columns:210px 1fr;background:#fff;border:1px solid var(--d-line);border-radius:20px;overflow:hidden}.damage-report-photo{position:relative;min-height:210px;background:#dce5e1;overflow:hidden}.damage-report-photo img{width:100%;height:100%;position:absolute;object-fit:cover}.damage-report-photo span{position:absolute;left:12px;bottom:12px;background:rgba(15,25,22,.76);color:#fff;padding:7px 9px;border-radius:8px;font-size:10px}.damage-report-content{padding:22px;position:relative}.damage-report-top{display:flex;justify-content:space-between;gap:14px;align-items:center}.damage-status{font-size:9px;text-transform:uppercase;letter-spacing:.08em;font-weight:900;background:#fff0dc;color:#9a5b0b;padding:7px 9px;border-radius:8px}.damage-report-top time{font-size:11px;color:var(--d-muted)}.damage-report-content h3{margin:14px 0 4px;font-size:18px}.damage-part{font:700 12px 'Space Grotesk';color:var(--d-green);margin:0}.damage-report-meta{display:flex;flex-wrap:wrap;gap:16px;margin:17px 0;font-size:11px;color:var(--d-muted)}.damage-report-meta span{display:flex;flex-direction:column;gap:3px}.damage-report-meta b{color:var(--d-ink)}.damage-report-content blockquote{margin:0;padding:12px 14px;background:#f5f8f6;border-left:3px solid var(--d-green2);border-radius:0 10px 10px 0;color:#4f5c57;font-size:13px;line-height:1.55}.damage-delete{margin-top:14px;border:1px solid #efc4c1;background:#fff6f5;color:var(--d-danger);padding:9px 12px;border-radius:9px;font-weight:800;cursor:pointer}.damage-empty{grid-column:1/-1;text-align:center;padding:58px 20px;background:#fff;border:1px dashed #b9c8c2;border-radius:20px}.damage-empty span{font-size:38px;color:var(--d-green)}.damage-empty h3{margin:10px 0 5px}.damage-empty p{margin:0;color:var(--d-muted);font-size:13px}
      .damage-admin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:36px}.damage-admin-stats article{background:#fff;border:1px solid var(--d-line);border-radius:18px;padding:20px}.damage-admin-stats span,.damage-admin-stats small{display:block;color:var(--d-muted);font-size:11px}.damage-admin-stats strong{display:block;font:700 35px 'Space Grotesk',Manrope,Arial,sans-serif;margin:9px 0 3px}.damage-admin-stats .text-status{font-size:23px;color:var(--d-green);margin-top:16px}
      .damage-field{display:block;margin-top:16px}.damage-field input[type=text]{width:100%;border:1px solid var(--d-line);border-radius:15px;padding:15px;font:inherit;outline:none;background:#fbfcfc}.damage-field input[type=text]:focus{border-color:var(--d-green);box-shadow:0 0 0 4px rgba(15,117,89,.1)}
      .photo-upload{padding:18px}.photo-upload.has-image:after{display:none}.photo-previews{position:relative;z-index:4;display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:8px;width:100%;margin-top:8px}.photo-previews[hidden]{display:none}.photo-preview-item{position:relative;display:block}.photo-previews img{position:relative;inset:auto;display:block;width:100%;height:92px;object-fit:cover;border-radius:10px}.photo-remove{position:absolute;z-index:5;right:6px;top:6px;width:28px;height:28px;border:0;border-radius:9px;background:rgba(128,26,22,.9);color:#fff;font:700 20px/1 Arial,sans-serif;cursor:pointer;box-shadow:0 3px 10px rgba(0,0,0,.2)}.photo-remove:hover{background:#a32621}.photo-selection{background:rgba(18,31,27,.86);color:#fff;padding:8px 11px;border-radius:9px;font-size:11px;font-weight:700;z-index:4}.photo-selection[hidden]{display:none}
      .damage-report-gallery{position:relative;min-height:210px;background:#dce5e1;display:grid;grid-template-columns:repeat(2,1fr);gap:2px;overflow:hidden}.damage-report-gallery a{position:relative;min-height:104px}.damage-report-gallery a:only-of-type{grid-column:1/-1;min-height:210px}.damage-report-gallery img{width:100%;height:100%;position:absolute;object-fit:cover}.damage-report-gallery>span{position:absolute;left:12px;bottom:12px;background:rgba(15,25,22,.76);color:#fff;padding:7px 9px;border-radius:8px;font-size:10px;z-index:2}
      @keyframes scan{from{transform:translateX(-24px)}to{transform:translateX(24px)}}
      @media(max-width:760px){.damage-page main{width:min(calc(100% - 24px),1180px);padding-top:32px}.damage-topbar{height:66px;padding:0 14px}.damage-user span{display:none}.damage-hero{grid-template-columns:1fr}.damage-hero-mark{display:none}.damage-actions{align-items:flex-start;flex-direction:column}.scan-stage{grid-template-columns:64px 1fr}.scan-visual{width:64px;height:64px}.scan-stage .damage-secondary{grid-column:1/-1;width:100%}.identified-card{grid-template-columns:42px 1fr}.identified-card dl{grid-column:1/-1;padding-left:56px}.damage-submit-row{align-items:stretch;flex-direction:column}.damage-report-card{grid-template-columns:1fr}.damage-report-photo{min-height:220px}.damage-admin-stats{grid-template-columns:1fr}.damage-section-head{align-items:flex-end}.damage-flow{padding:20px 16px}}
    """
