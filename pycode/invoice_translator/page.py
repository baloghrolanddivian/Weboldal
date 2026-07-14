"""Page helpers for the invoice translator package."""

from __future__ import annotations

import html


APP_ROUTE = "/apps/szamla-magyarito"
GENERATE_ROUTE = f"{APP_ROUTE}/generate"
COMMON_SCRIPT_TAG = '<script src="/script.js"></script>'
INVOICE_THEME_LINK = '<link rel="stylesheet" href="/styles.css" />'
INVOICE_HR_THEME_STYLE = '''<style>
body.hr-theme { --bg: #fff8f4; --bg-soft: #ffe9f1; --panel: rgba(255,255,255,.9); --panel-strong: rgba(255,244,248,.98); --border: rgba(235,151,188,.5); --line: rgba(222,139,177,.28); --text: #4c1834; --muted: #8d5c74; --accent: #f38ab8; --accent-strong: #e85d9d; --accent-warm: #ffc6dc; --shadow: 0 24px 58px rgba(157,74,113,.16); background: linear-gradient(180deg,#fffaf6 0%,#fff0f5 46%,#ffe4ed 100%) !important; }
body.hr-theme .site { background: transparent; }
body.hr-theme .site::before { background-image: linear-gradient(rgba(230,147,183,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(230,147,183,.12) 1px,transparent 1px); }
body.hr-theme .topbar { background: rgba(255,252,250,.82); }
body.hr-theme .hero-card, body.hr-theme .upload-card { background: linear-gradient(180deg,var(--panel),var(--panel-strong)); }
body.hr-theme .hero-card::before, body.hr-theme .upload-card::before { background: linear-gradient(120deg,rgba(255,180,213,.28),transparent 34%),linear-gradient(180deg,transparent,rgba(255,225,237,.2)); }
body.hr-theme .upload-surface, body.hr-theme .support-pill { background: rgba(255,230,240,.6); }
body.hr-theme .upload-rail { background: linear-gradient(90deg,rgba(243,138,184,.72),rgba(255,198,220,.7)); }
body.hr-theme .visual-arrow, body.hr-theme .upload-badge { background: var(--accent-warm); }
</style>'''
INVOICE_ADMIN_THEME_STYLE = '''<style>
body.admin-theme {
  --bg: #120b08; --bg-soft: #21130e; --panel: rgba(29,19,15,.9); --panel-strong: rgba(37,22,16,.97);
  --border: rgba(255,123,48,.3); --line: rgba(255,123,48,.18); --text: #fff1e8; --muted: #c8a99b;
  --accent: #ff7138; --accent-strong: #d93616; --accent-warm: #ffb347;
  background: linear-gradient(180deg,#120b08 0%,#1b100c 44%,#28150e 100%) !important;
}
body.admin-theme .site { background: transparent; }
body.admin-theme .site::before {
  background-image: linear-gradient(rgba(255,113,56,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(255,113,56,.08) 1px,transparent 1px);
}
body.admin-theme .topbar { background: rgba(24,14,10,.86); }
body.admin-theme .hero-card, body.admin-theme .upload-card { background: linear-gradient(180deg,var(--panel),var(--panel-strong)); }
body.admin-theme .hero-card::before, body.admin-theme .upload-card::before {
  background: linear-gradient(120deg,rgba(255,113,56,.2),transparent 34%),linear-gradient(180deg,transparent,rgba(255,179,71,.08));
}
body.admin-theme .brand-mark { box-shadow: 0 0 0 8px rgba(255,113,56,.1), 0 0 28px rgba(255,113,56,.24); }
body.admin-theme .button, body.admin-theme .primary-button, body.admin-theme .nav-cta {
  box-shadow: 0 12px 26px rgba(217,54,22,.25);
}
body.admin-theme .visual-doc::before { background: linear-gradient(90deg,rgba(255,113,56,.72),rgba(255,179,71,.58)); }
body.admin-theme .visual-doc { border-color: rgba(255,123,48,.34); }
body.admin-theme .visual-arrow { border-color: rgba(255,123,48,.28); background: linear-gradient(90deg,rgba(255,113,56,.18),rgba(255,179,71,.16)); }
body.admin-theme .upload-surface, body.admin-theme .support-pill { background: rgba(255,113,56,.08); }
body.admin-theme .upload-badge { box-shadow: 0 16px 34px rgba(217,54,22,.24); }
body.admin-theme .upload-rail { background: transparent; }
body.admin-theme .upload-rail span { background: rgba(48,20,10,.42); }
body.admin-theme .upload-rail i { background: linear-gradient(90deg,var(--accent),var(--accent-warm)); }
</style>'''


def render_form(message: str = "") -> bytes:
    """Render the invoice translator upload form."""
    msg_html = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {INVOICE_THEME_LINK}
  <title>Divian-HUB | Számla magyarító</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <style>
    :root {{
      --bg: #040b12;
      --bg-soft: #09131c;
      --panel: rgba(8, 18, 28, 0.84);
      --panel-strong: rgba(10, 22, 33, 0.94);
      --border: rgba(84, 191, 214, 0.18);
      --line: rgba(84, 191, 214, 0.12);
      --text: #f3fbff;
      --muted: #8ea8b8;
      --accent: #43decf;
      --accent-strong: #1197a2;
      --accent-warm: #ff8b64;
      --danger-bg: rgba(88, 27, 28, 0.78);
      --danger-line: rgba(255, 139, 100, 0.34);
      --shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-width: 320px;
      font-family: "Manrope", sans-serif;
      background:
        radial-gradient(circle at 14% 16%, rgba(67, 222, 207, 0.2), transparent 24%),
        radial-gradient(circle at 82% 10%, rgba(255, 139, 100, 0.15), transparent 18%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
      color: var(--text);
      overflow-x: hidden;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    button,
    input {{
      font: inherit;
    }}
    .site {{
      position: relative;
      min-height: 100vh;
      padding: 20px 24px 36px;
    }}
    .site::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(84, 191, 214, 0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(84, 191, 214, 0.04) 1px, transparent 1px);
      background-size: 72px 72px;
      mask-image: radial-gradient(circle at center, black 35%, transparent 85%);
      pointer-events: none;
      z-index: -1;
    }}
    .topbar,
    .content {{
      width: min(1080px, calc(100vw - 48px));
      margin-inline: auto;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 16px 20px;
      background: rgba(7, 16, 24, 0.76);
      border: 1px solid var(--border);
      backdrop-filter: blur(18px);
      border-radius: 999px;
      box-shadow: var(--shadow);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-mark {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 35% 35%, #ffffff, transparent 28%),
        radial-gradient(circle, var(--accent-warm), var(--accent-strong));
      box-shadow:
        0 0 0 8px rgba(67, 222, 207, 0.08),
        0 0 28px rgba(67, 222, 207, 0.22);
    }}
    .brand-text {{
      display: grid;
      gap: 3px;
    }}
    .brand-text strong,
    h1,
    h2,
    .surface-title strong {{
      font-family: "Space Grotesk", sans-serif;
    }}
    .brand-text strong {{
      font-size: 0.98rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .brand-text small {{
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .nav {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      justify-content: center;
      gap: 18px;
      color: var(--muted);
      font-weight: 600;
    }}
    .nav a {{
      transition: color 180ms ease;
    }}
    .nav a:hover,
    .nav a:focus-visible {{
      color: var(--text);
    }}
    .ghost-link,
    .nav-cta,
    .button,
    .primary-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 20px;
      border-radius: 999px;
      font-weight: 700;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        background 180ms ease,
        color 180ms ease;
    }}
    .ghost-link {{
      border: 1px solid var(--border);
      color: var(--text);
      background: rgba(255, 255, 255, 0.06);
    }}
    .button,
    .primary-button {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      cursor: pointer;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .nav-cta {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      font-weight: 800;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .ghost-link:hover,
    .nav-cta:hover,
    .button:hover,
    .primary-button:hover,
    .nav-cta:focus-visible {{
      transform: translateY(-2px);
    }}
    .content {{
      display: grid;
      gap: 18px;
      padding-top: 28px;
      align-items: start;
    }}
    .hero-card,
    .upload-card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }}
    .hero-card::before,
    .upload-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, transparent, rgba(255, 139, 100, 0.06));
      pointer-events: none;
    }}
    .hero-card {{
      padding: 26px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) 240px;
      gap: 20px;
      align-items: center;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 13px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.06);
      color: var(--accent);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.72rem;
    }}
    .eyebrow::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-warm);
      box-shadow: 0 0 16px rgba(255, 142, 110, 0.45);
    }}
    h1 {{
      margin: 18px 0 14px;
      font-size: clamp(2.6rem, 5vw, 4.5rem);
      line-height: 0.94;
      letter-spacing: -0.05em;
      max-width: 9ch;
    }}
    h1 span {{
      display: block;
      color: transparent;
      background: linear-gradient(135deg, var(--accent-strong) 0%, var(--accent) 48%, var(--accent-warm) 100%);
      -webkit-background-clip: text;
      background-clip: text;
    }}
    .lead,
    .surface-title p,
    .file-state small,
    .inline-note,
    .alert {{
      color: var(--muted);
    }}
    .lead {{
      max-width: 40ch;
      font-size: 1.02rem;
      line-height: 1.7;
      margin: 0;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-visual {{
      position: relative;
      width: 250px;
      height: 200px;
      margin-left: auto;
    }}
    .visual-doc,
    .visual-arrow,
    .visual-lang {{
      position: absolute;
    }}
    .visual-doc {{
      width: 122px;
      height: 156px;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.04));
      box-shadow: 0 18px 30px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(14px);
    }}
    .visual-doc::before {{
      content: "";
      position: absolute;
      left: 14px;
      right: 14px;
      top: 18px;
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.6), rgba(255, 139, 100, 0.45));
    }}
    .visual-doc::after {{
      content: "";
      position: absolute;
      left: 14px;
      right: 20px;
      top: 42px;
      height: 72px;
      border-radius: 18px;
      background:
        linear-gradient(rgba(255, 255, 255, 0.14) 0 0) 0 0 / 100% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.1) 0 0) 0 18px / 86% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 36px / 92% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 54px / 70% 1px no-repeat;
    }}
    .doc-source {{
      left: 2px;
      top: 26px;
      transform: rotate(-6deg);
    }}
    .doc-target {{
      right: 0;
      top: 18px;
      transform: rotate(6deg);
      border-color: rgba(67, 222, 207, 0.26);
    }}
    .visual-arrow {{
      left: 99px;
      top: 84px;
      width: 52px;
      height: 20px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(90deg, rgba(255, 139, 100, 0.12), rgba(67, 222, 207, 0.12));
      display: grid;
      place-items: center;
      color: var(--accent);
      font-size: 1rem;
      font-weight: 700;
      backdrop-filter: blur(8px);
    }}
    .visual-lang {{
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.06);
      font-size: 0.7rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--text);
    }}
    .lang-source {{
      left: 0;
      top: 0;
    }}
    .lang-target {{
      right: 0;
      bottom: 0;
      color: var(--accent);
    }}
    .upload-card {{
      padding: 22px;
    }}
    .alert {{
      padding: 14px 16px;
      border-radius: var(--radius-md);
      border: 1px solid var(--danger-line);
      background: var(--danger-bg);
      line-height: 1.55;
      margin-bottom: 14px;
    }}
    .surface-title {{
      margin-bottom: 14px;
    }}
    .surface-title strong {{
      display: block;
      font-size: 1.05rem;
      margin-bottom: 4px;
    }}
    .surface-title p {{
      margin: 0;
    }}
    .upload-shell {{
      display: grid;
      gap: 14px;
    }}
    .upload-shell.is-dragover {{
      box-shadow: 0 0 0 1px rgba(69, 224, 207, 0.22) inset;
    }}
    .file-input {{
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }}
    .upload-surface {{
      display: grid;
      gap: 16px;
      min-height: 188px;
      padding: 22px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top left, rgba(67, 222, 207, 0.08), transparent 32%),
        rgba(255, 255, 255, 0.04);
      cursor: pointer;
    }}
    .upload-top {{
      display: grid;
      grid-template-columns: 70px 1fr;
      gap: 16px;
      align-items: center;
    }}
    .upload-badge {{
      width: 70px;
      height: 70px;
      border-radius: 22px;
      display: grid;
      place-items: center;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.05rem;
      color: #041017;
      background: linear-gradient(135deg, var(--accent), var(--accent-warm));
      box-shadow: 0 16px 34px rgba(67, 222, 207, 0.18);
    }}
    .upload-copy strong {{
      display: block;
      font-size: 1.16rem;
      margin-bottom: 4px;
    }}
    .upload-copy p {{
      margin: 0;
      line-height: 1.65;
      color: var(--muted);
    }}
    .upload-rail {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .upload-rail span {{
      color: var(--text);
    }}
    .upload-rail i {{
      width: 22px;
      height: 1px;
      background: linear-gradient(90deg, var(--accent), var(--accent-warm));
      display: block;
    }}
    .file-state {{
      padding-top: 2px;
    }}
    .file-state strong {{
      display: block;
      font-size: 0.96rem;
      margin-bottom: 4px;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .inline-note {{
      font-size: 0.88rem;
    }}
    .support-footer {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.8rem;
    }}
    .support-footer strong {{
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .support-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    @media (max-width: 1100px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
      .hero-visual {{
        margin-inline: auto;
      }}
    }}
    @media (max-width: 760px) {{
      .site {{
        padding: 14px 14px 28px;
      }}
      .topbar {{
        border-radius: 28px;
        justify-content: center;
        text-align: center;
        flex-wrap: wrap;
      }}
      .nav {{
        width: 100%;
      }}
      .content,
      .topbar {{
        width: min(100vw - 28px, 1080px);
      }}
      .hero-card,
      .upload-card {{
        padding: 22px;
      }}
      h1 {{
        max-width: none;
      }}
      .hero-visual {{
        width: 180px;
        height: 180px;
      }}
      .visual-core {{
        inset: 60px;
      }}
      .surface-title {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .upload-top {{
        grid-template-columns: 1fr;
      }}
      .action-row {{
        align-items: stretch;
      }}
    }}
  </style>
  {INVOICE_HR_THEME_STYLE}
  {INVOICE_ADMIN_THEME_STYLE}
</head>
<body>
  <div class="site">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Divian-HUB főoldal">
        <span class="brand-mark"></span>
        <span class="brand-text">
          <strong>Divian-HUB</strong>
          <small>Számla magyarító</small>
        </span>
      </a>

      <nav class="nav">
        <a href="/">Főoldal</a>
        <a href="/#modules">Modulok</a>
      </nav>

      <a class="nav-cta" href="/#modules">Modulok</a>
    </header>

    <main class="content">
      <section class="hero-card">
        <div class="hero-grid">
          <div class="hero-copy">
            <div class="eyebrow">Számla magyarító</div>
            <h1>PDF számla <span>kész fordítás</span></h1>
            <p class="lead">
              Tölts fel egy PDF számlát, és a rendszer elkészíti a fordított, nyomtatható változatot.
            </p>
            <div class="hero-actions">
              <a class="button" href="#feltoltes">Feltöltés</a>
              <a class="ghost-link" href="/">Modulok</a>
            </div>
          </div>

          <div class="hero-visual" aria-hidden="true">
            <div class="visual-lang lang-source">Forrás</div>
            <div class="visual-doc doc-source"></div>
            <div class="visual-arrow">→</div>
            <div class="visual-doc doc-target"></div>
            <div class="visual-lang lang-target">Magyar</div>
          </div>
        </div>
      </section>

      <section class="upload-card" id="feltoltes">
        <div class="surface-title">
          <strong>Feltöltés</strong>
          <p>Fájl kiválasztása, majd indítás.</p>
        </div>

        {msg_html}

        <form method="post" action="{GENERATE_ROUTE}" enctype="multipart/form-data" target="_blank" id="invoice-form">
          <div class="upload-shell" id="upload-shell">
            <input
              class="file-input"
              id="invoice_file"
              type="file"
              name="invoice_file"
              accept="application/pdf"
              required
            />

            <label class="upload-surface" for="invoice_file">
              <div class="upload-top">
                <div class="upload-badge">PDF</div>
                <div class="upload-copy">
                  <strong>Számla kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                </div>
              </div>

              <div class="upload-rail" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>Magyar nézet</span>
              </div>

              <div class="file-state">
                <strong id="file-name">Még nincs kiválasztott fájl</strong>
                <small id="file-meta">Támogatott formátum: .pdf</small>
              </div>
            </label>

            <div class="action-row">
              <button class="primary-button" type="submit" id="submit-button">Fordítás indítása</button>
              <span class="inline-note">Az eredmény külön lapon jelenik meg.</span>
            </div>
          </div>
        </form>

        <div class="support-footer">
          <strong>Működik jelenleg:</strong>
          <span class="support-pill">Kronospan</span>
          <span class="support-pill">Kastamonu</span>
        </div>
      </section>
    </main>
  </div>

  <script>
    const fileInput = document.getElementById("invoice_file");
    const fileName = document.getElementById("file-name");
    const fileMeta = document.getElementById("file-meta");
    const uploadShell = document.getElementById("upload-shell");
    const form = document.getElementById("invoice-form");
    const submitButton = document.getElementById("submit-button");

    const updateFileState = () => {{
      const file = fileInput.files && fileInput.files[0];
      if (!file) {{
        fileName.textContent = "Még nincs kiválasztott fájl";
        fileMeta.textContent = "Támogatott formátum: .pdf";
        return;
      }}

      fileName.textContent = file.name;
      fileMeta.textContent = `${{(file.size / 1024 / 1024).toFixed(2)}} MB`;
    }};

    ["dragenter", "dragover"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.add("is-dragover");
      }});
    }});

    ["dragleave", "drop"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.remove("is-dragover");
      }});
    }});

    fileInput.addEventListener("change", updateFileState);

    form.addEventListener("submit", () => {{
      submitButton.textContent = "Feldolgozás indul...";
      submitButton.disabled = true;
      window.setTimeout(() => {{
        submitButton.textContent = "Fordítás indítása";
        submitButton.disabled = false;
      }}, 2000);
    }});
  </script>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")
