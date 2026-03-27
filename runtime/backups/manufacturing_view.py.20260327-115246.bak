from __future__ import annotations

import html
import json
import urllib.parse


def _json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_manufacturing_page(
    *,
    route: str,
    state_route: str,
    selected_number: str,
    recent_productions: list[dict[str, str]],
    bundle: dict,
    selection_state: dict[str, str],
    message: str = "",
    success: bool = False,
) -> bytes:
    documents = bundle.get("documents", [])
    total_rows = sum(int(document.get("row_count", 0) or 0) for document in documents if isinstance(document, dict))
    green_count = sum(1 for value in selection_state.values() if value == "green")
    red_count = sum(1 for value in selection_state.values() if value == "red")

    notice_markup = ""
    if message:
        notice_class = "mfg-notice is-success" if success else "mfg-notice is-error"
        notice_markup = f'<div class="{notice_class}">{html.escape(message)}</div>'

    recent_chips_html = "".join(
        (
            f'<a class="mfg-chip-link{" is-active" if str(entry.get("number", "")) == selected_number else ""}" '
            f'href="{route}?production={urllib.parse.quote(str(entry.get("number", "")))}">'
            f'<span class="mfg-chip-date">{html.escape(str(entry.get("date_label", "") or "Dátum nélkül"))}</span>'
            f'<span class="mfg-chip-number">{html.escape(str(entry.get("number", "")))}</span>'
            f"</a>"
        )
        for entry in recent_productions[:10]
    )
    payload_json = _json_script_payload(
        {
            "productionNumber": selected_number,
            "folder": bundle.get("folder", ""),
            "documents": documents,
            "selectionState": selection_state,
            "stateRoute": state_route,
        }
    )

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Gyártási papírok</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <style>
    :root {{
      color-scheme: light;
      --mfg-bg: #f3f5f7;
      --mfg-panel: #ffffff;
      --mfg-panel-soft: #f8fafc;
      --mfg-line: #d7dde4;
      --mfg-line-strong: #c5ced8;
      --mfg-text: #121417;
      --mfg-muted: #5f6975;
      --mfg-shadow: 0 18px 40px rgba(17, 24, 39, 0.08);
      --mfg-radius-xl: 28px;
      --mfg-radius-lg: 20px;
      --mfg-radius-md: 16px;
      --mfg-green-bg: #e7f8ee;
      --mfg-green-line: #6fc893;
      --mfg-green-text: #0d6b37;
      --mfg-red-bg: #ffecec;
      --mfg-red-line: #ef7b7b;
      --mfg-red-text: #b33131;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      background: var(--mfg-bg);
      color: var(--mfg-text);
      font-family: "Manrope", sans-serif;
    }}
    body {{
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}
    a {{ color: inherit; text-decoration: none; }}
    button, input {{ font: inherit; }}
    .mfg-page {{
      min-height: 100vh;
      padding: 8px 8px 16px;
      display: grid;
      gap: 0;
      align-content: start;
    }}
    .mfg-toolbar,
    .mfg-board,
    .mfg-notice {{
      width: min(1280px, 100%);
      margin: 0 auto;
    }}
    .mfg-toolbar {{
      padding: 8px 10px;
      height: 52px;
      min-height: 52px;
      max-height: 52px;
      border-radius: 18px 18px 0 0;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid rgba(18, 20, 23, 0.08);
      border-bottom: 0;
      box-shadow: 0 10px 22px rgba(17, 24, 39, 0.05);
      display: flex;
      align-items: center;
      overflow: hidden;
    }}
    .mfg-topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid rgba(18, 20, 23, 0.08);
      box-shadow: 0 12px 32px rgba(17, 24, 39, 0.06);
    }}
    .mfg-brand {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
    }}
    .mfg-brand-mark {{
      width: 18px;
      height: 18px;
      border-radius: 6px;
      background: linear-gradient(135deg, #111827, #657182);
    }}
    .mfg-nav {{
      display: flex;
      gap: 16px;
      color: var(--mfg-muted);
      font-size: 0.94rem;
    }}
    .mfg-notice {{
      padding: 14px 18px;
      border-radius: var(--mfg-radius-md);
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .mfg-notice.is-error {{
      background: #fff0f0;
      border: 1px solid #f1b7b7;
      color: #a73939;
    }}
    .mfg-notice.is-success {{
      background: #ecfaf1;
      border: 1px solid #bde2c9;
      color: #1e7a42;
    }}
    .mfg-card,
    .mfg-board {{
      background: var(--mfg-panel);
      border: 1px solid rgba(18, 20, 23, 0.08);
      border-radius: var(--mfg-radius-xl);
      box-shadow: var(--mfg-shadow);
    }}
    .mfg-card {{
      padding: 12px 14px;
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.9fr);
      gap: 12px;
      align-items: center;
    }}
    .mfg-head {{
      display: grid;
      gap: 8px;
    }}
    .mfg-kicker {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      background: #f4f6f8;
      color: var(--mfg-muted);
      font-size: 0.7rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .mfg-head h1 {{
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(1.22rem, 1.8vw, 1.7rem);
      line-height: 1;
    }}
    .mfg-head p,
    .mfg-board-subtitle,
    .mfg-status,
    .mfg-empty-copy,
    .mfg-section-count,
    .mfg-row-subtitle,
    .mfg-tab span,
    .mfg-doc-meta,
    .mfg-stat span,
    .mfg-table-head span {{
      color: var(--mfg-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-head p {{
      margin: 0;
      max-width: 88ch;
      font-size: 0.84rem;
      line-height: 1.35;
    }}
    .mfg-status.is-error {{
      color: var(--mfg-red-text);
    }}
    .mfg-status.is-success {{
      color: var(--mfg-green-text);
    }}
    .mfg-picker {{
      display: flex;
      gap: 6px;
      align-items: center;
      min-height: 38px;
    }}
    .mfg-picker input {{
      flex: 0 1 180px;
      min-height: 38px;
      padding: 0 12px;
      border-radius: 14px;
      border: 1px solid var(--mfg-line);
      background: #fff;
      color: var(--mfg-text);
      font-size: 0.88rem;
      font-weight: 700;
    }}
    .mfg-picker input:focus {{
      outline: none;
      border-color: #111827;
      box-shadow: 0 0 0 4px rgba(17, 24, 39, 0.08);
    }}
    .mfg-button {{
      min-height: 38px;
      padding: 0 13px;
      border-radius: 14px;
      border: 1px solid #111827;
      background: #111827;
      color: #fff;
      font-weight: 800;
      cursor: pointer;
      transition: transform 180ms ease, box-shadow 180ms ease;
    }}
    .mfg-button:hover {{
      transform: translateY(-1px);
      box-shadow: 0 14px 28px rgba(17, 24, 39, 0.16);
    }}
    .mfg-chip-row {{
      display: flex;
      gap: 6px;
      min-height: 28px;
      max-height: 28px;
      overflow-x: auto;
      overflow-y: hidden;
      align-items: center;
      flex-wrap: nowrap;
    }}
    .mfg-chip-link {{
      min-height: 36px;
      padding: 5px 10px 4px;
      display: inline-grid;
      align-content: center;
      gap: 1px;
      border-radius: 999px;
      background: #f5f7f9;
      border: 1px solid transparent;
      color: var(--mfg-muted);
      white-space: nowrap;
      flex: 0 0 auto;
    }}
    .mfg-chip-link.is-active {{
      border-color: #111827;
      color: #111827;
      background: #eef2f6;
    }}
    .mfg-chip-date {{
      font-size: 0.67rem;
      line-height: 1;
      font-weight: 800;
    }}
    .mfg-chip-number {{
      font-size: 0.62rem;
      line-height: 1;
      font-weight: 700;
      color: var(--mfg-muted);
    }}
    .mfg-chip-link.is-active .mfg-chip-number {{
      color: #4b5563;
    }}
    .mfg-stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }}
    .mfg-stat {{
      padding: 10px 12px;
      border-radius: 14px;
      background: var(--mfg-panel-soft);
      border: 1px solid rgba(18, 20, 23, 0.06);
      display: grid;
      gap: 2px;
    }}
    .mfg-stat strong {{
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(0.96rem, 1.2vw, 1.2rem);
    }}
    .mfg-stat span {{
      font-size: 0.78rem;
    }}
    .mfg-board {{
      padding: 8px;
      grid-template-rows: 50px 36px 28px auto;
      display: grid;
      gap: 8px;
      align-content: start;
      border-top-left-radius: 0;
      border-top-right-radius: 0;
    }}
    .mfg-status-row {{
      min-height: 28px;
      max-height: 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      overflow: hidden;
    }}
    .mfg-status {{
      font-size: 0.76rem;
      padding: 0 4px;
      min-height: 20px;
      max-height: 20px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1 1 auto;
    }}
    .mfg-layout-toggle {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px;
      border-radius: 999px;
      border: 1px solid rgba(17, 24, 39, 0.08);
      background: #f7f9fb;
    }}
    .mfg-layout-button {{
      width: 30px;
      min-width: 30px;
      height: 22px;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--mfg-muted);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 160ms ease, color 160ms ease;
      font-size: 0.82rem;
      font-weight: 800;
      line-height: 1;
    }}
    .mfg-layout-button.is-active {{
      background: #111827;
      color: #fff;
    }}
    .mfg-tab-row,
    .mfg-section-tab-row {{
      display: flex;
      gap: 6px;
      overflow-x: auto;
      overflow-y: hidden;
      padding-bottom: 2px;
      scrollbar-width: thin;
      align-items: stretch;
      flex-wrap: nowrap;
    }}
    .mfg-tab-row {{
      min-height: 50px;
      max-height: 50px;
    }}
    .mfg-section-tab-row {{
      min-height: 36px;
      max-height: 36px;
    }}
    .mfg-tab,
    .mfg-section-tab {{
      flex: 0 0 auto;
      border: 1px solid var(--mfg-line);
      background: #fff;
      color: var(--mfg-text);
      border-radius: 18px;
      cursor: pointer;
      transition: background 180ms ease, border-color 180ms ease, transform 180ms ease, color 180ms ease;
    }}
    .mfg-tab {{
      width: 160px;
      min-width: 160px;
      max-width: 160px;
      min-height: 48px;
      max-height: 48px;
      padding: 7px 10px;
      text-align: left;
      display: grid;
      gap: 2px;
      align-content: center;
      overflow: hidden;
    }}
    .mfg-tab strong,
    .mfg-section-tab strong {{
      font-size: 0.9rem;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-tab span {{
      font-size: 0.74rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-section-tab {{
      min-height: 34px;
      max-height: 34px;
      padding: 0 10px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      overflow: hidden;
    }}
    .mfg-section-tab small {{
      color: var(--mfg-muted);
      font-size: 0.72rem;
      flex: 0 0 auto;
    }}
    .mfg-tab.is-active {{
      border-color: #111827;
      background: #111827;
      color: #fff;
    }}
    .mfg-tab.is-active span {{
      color: rgba(255, 255, 255, 0.76);
    }}
    .mfg-section-tab.is-active {{
      border-color: #111827;
      box-shadow: inset 0 0 0 1px #111827;
    }}
    .mfg-section-tab.is-secondary {{
      border-color: #64748b;
      box-shadow: inset 0 0 0 1px #64748b;
    }}
    .mfg-section-tab.is-complete {{
      border-color: var(--mfg-green-line);
      background: var(--mfg-green-bg);
      color: var(--mfg-green-text);
    }}
    .mfg-section-tab.is-complete small {{
      color: var(--mfg-green-text);
      opacity: 0.82;
    }}
    .mfg-section-tab.is-alert {{
      border-color: var(--mfg-red-line);
      background: var(--mfg-red-bg);
      color: var(--mfg-red-text);
    }}
    .mfg-section-tab.is-alert small {{
      color: var(--mfg-red-text);
      opacity: 0.82;
    }}
    .mfg-content {{
      min-height: 220px;
      display: grid;
      gap: 8px;
    }}
    .mfg-content.is-overview {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: start;
    }}
    .mfg-content.is-split {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: start;
    }}
    .mfg-section-card {{
      border-radius: 14px;
      border: 1px solid rgba(17, 24, 39, 0.08);
      background: #ffffff;
      padding: 0;
      display: grid;
      gap: 0;
      overflow: hidden;
    }}
    .mfg-table-head {{
      display: grid;
      grid-template-columns: 1.02fr 0.7fr 0.7fr 0.4fr 0.5fr 1.98fr;
      gap: 5px;
      min-height: 34px;
      max-height: 34px;
      padding: 0 10px;
      align-items: center;
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      border-top: 1px solid rgba(17, 24, 39, 0.06);
      border-bottom: 1px solid rgba(17, 24, 39, 0.06);
      background: #f7f9fb;
      overflow: hidden;
    }}
    .mfg-sort-head {{
      min-width: 0;
      min-height: 24px;
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font: inherit;
      font-weight: inherit;
      letter-spacing: inherit;
      text-transform: inherit;
      cursor: pointer;
      overflow: hidden;
    }}
    .mfg-sort-head-label {{
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-sort-head-arrow {{
      flex: 0 0 auto;
      font-size: 0.7rem;
      color: #111827;
      opacity: 0.95;
    }}
    .mfg-table-head [data-sort-key="color"] {{
      padding-left: 14px;
    }}
    .mfg-sort-head.is-active {{
      color: #111827;
    }}
    .mfg-section-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 8px 10px;
      background: #f5f7fa;
      border-bottom: 1px solid rgba(17, 24, 39, 0.06);
    }}
    .mfg-section-title {{
      font-size: 0.82rem;
      font-weight: 800;
    }}
    .mfg-row-list {{
      display: grid;
      gap: 0;
    }}
    .mfg-content.is-split .mfg-section-card {{
      align-self: start;
      max-height: calc(100vh - 228px);
      max-height: calc(100dvh - 228px);
      grid-template-rows: auto auto auto;
    }}
    .mfg-content.is-split .mfg-row-list {{
      max-height: calc(100vh - 314px);
      max-height: calc(100dvh - 314px);
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior: contain;
      scrollbar-width: thin;
      box-sizing: border-box;
      padding-bottom: 16px;
    }}
    .mfg-row {{
      width: 100%;
      padding: 7px 10px;
      border-radius: 0;
      border: 0;
      border-top: 1px solid rgba(17, 24, 39, 0.06);
      background: #fff;
      color: var(--mfg-text);
      text-align: left;
      display: grid;
      grid-template-columns: 1.02fr 0.7fr 0.7fr 0.4fr 0.5fr 1.98fr;
      gap: 5px;
      align-items: center;
      cursor: pointer;
      transition: background 220ms ease, border-color 220ms ease;
      touch-action: pan-y manipulation;
      user-select: none;
      -webkit-user-select: none;
      -webkit-touch-callout: none;
    }}
    .mfg-row.is-green {{
      background: var(--mfg-green-bg);
      box-shadow: inset 3px 0 0 var(--mfg-green-line);
    }}
    .mfg-row.is-red {{
      background: var(--mfg-red-bg);
      box-shadow: inset 3px 0 0 var(--mfg-red-line);
    }}
    .mfg-row.is-green .mfg-row-meta span,
    .mfg-row.is-green .mfg-row-code {{
      color: var(--mfg-green-text);
    }}
    .mfg-row.is-red .mfg-row-meta span,
    .mfg-row.is-red .mfg-row-code {{
      color: var(--mfg-red-text);
    }}
    .mfg-row-main {{
      display: grid;
      gap: 1px;
      min-width: 0;
      align-content: center;
    }}
    .mfg-row-title {{
      font-size: 0.78rem;
      font-weight: 800;
      line-height: 1.1;
    }}
    .mfg-row-subtitle {{
      font-size: 0.7rem;
      line-height: 1.12;
      min-height: 0;
    }}
    .mfg-row-meta {{
      display: grid;
      align-content: center;
      min-width: 0;
    }}
    .mfg-row-meta span,
    .mfg-row-code {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 2px;
      border-radius: 0;
      background: transparent;
      font-size: 0.84rem;
      font-weight: 800;
      color: var(--mfg-text);
    }}
    .mfg-row-meta span {{
      white-space: normal;
      overflow: visible;
      text-overflow: clip;
      line-height: 1.14;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .mfg-row-meta span.is-size {{
      white-space: nowrap;
      overflow: visible;
      text-overflow: clip;
      word-break: normal;
      overflow-wrap: normal;
      line-height: 1;
      font-size: 0.8rem;
      align-self: center;
      transform: translateY(2px);
    }}
    .mfg-row-meta span.is-color {{
      white-space: normal;
      line-height: 1.14;
      padding-left: 14px;
    }}
    .mfg-row-code {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-row-side {{
      display: grid;
      gap: 6px;
      align-content: center;
    }}
    .mfg-row-qty {{
      min-width: 0;
      min-height: 28px;
      padding: 0 8px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #111827;
      color: #fff;
      font-weight: 800;
      font-size: 0.84rem;
      justify-self: start;
    }}
    .mfg-row.is-green .mfg-row-qty {{
      background: var(--mfg-green-text);
    }}
    .mfg-row.is-red .mfg-row-qty {{
      background: var(--mfg-red-text);
    }}
    .mfg-row-barcode-wrap {{
      display: grid;
      gap: 2px;
      align-content: center;
      min-width: 0;
      overflow: hidden;
      justify-self: stretch;
      width: 100%;
      max-width: 100%;
    }}
    .mfg-row-barcode {{
      min-height: 38px;
      padding: 4px 10px;
      border-radius: 8px;
      background: #fff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      display: grid;
      place-items: center;
      overflow: hidden;
      width: 100%;
      max-width: 100%;
    }}
    .mfg-row-barcode svg {{
      width: 100%;
      height: 30px;
      display: block;
    }}
    .mfg-row-code {{
      justify-content: center;
      text-align: center;
      font-size: 0.64rem;
      min-height: 16px;
    }}
    .mfg-empty {{
      min-height: 240px;
      border: 1px dashed var(--mfg-line);
      border-radius: 24px;
      background: #fbfcfd;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 28px;
    }}
    .mfg-empty strong {{
      display: block;
      margin-bottom: 8px;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.08rem;
    }}
    @media (max-width: 1080px) {{
      .mfg-content.is-overview {{
        grid-template-columns: minmax(0, 1fr);
      }}
      .mfg-table-head,
      .mfg-row {{
        grid-template-columns: 0.96fr 0.66fr 0.66fr 0.38fr 0.46fr 1.88fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="mfg-page">
    {notice_markup}

    <section class="mfg-toolbar">
      <div class="mfg-chip-row">{recent_chips_html}</div>
    </section>

    <section class="mfg-board">

      <div class="mfg-tab-row" id="mfg-doc-tabs"></div>
      <div class="mfg-section-tab-row" id="mfg-section-tabs"></div>
      <div class="mfg-status-row">
        <div class="mfg-status" id="mfg-status">Érintés: zöld, majd piros, majd üres.</div>
        <div class="mfg-layout-toggle" id="mfg-layout-toggle" aria-label="Nézet mód">
          <button class="mfg-layout-button is-active" type="button" data-layout-mode="single" title="Egy kategória">▣</button>
          <button class="mfg-layout-button" type="button" data-layout-mode="double" title="Két kategória">▥</button>
        </div>
      </div>
      <div class="mfg-content" id="mfg-content"></div>
    </section>

    <script type="application/json" id="manufacturing-data">{payload_json}</script>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script>
  </div>

  <script>
    (() => {{
      const dataNode = document.getElementById("manufacturing-data");
      const docTabsNode = document.getElementById("mfg-doc-tabs");
      const sectionTabsNode = document.getElementById("mfg-section-tabs");
      const contentNode = document.getElementById("mfg-content");
      const statusNode = document.getElementById("mfg-status");
      const layoutToggleNode = document.getElementById("mfg-layout-toggle");
      if (!dataNode || !docTabsNode || !sectionTabsNode || !contentNode || !statusNode || !layoutToggleNode) return;

      let payload = {{}};
      try {{
        payload = JSON.parse(dataNode.textContent || "{{}}");
      }} catch (_error) {{
        payload = {{}};
      }}

      const documents = Array.isArray(payload.documents) ? payload.documents : [];
      const selectionState = Object.assign({{}}, payload.selectionState || {{}});
      const stateRoute = String(payload.stateRoute || "");
      const productionNumber = String(payload.productionNumber || "");
      let currentDocKey = documents[0]?.key || "";
      let currentViewKey = "all";
      let secondaryViewKey = "";
      let layoutMode = "single";
      let currentSortKey = "pdf";
      let currentSortDirection = "asc";

      const escapeHtml = (value) =>
        String(value ?? "").replace(/[&<>"']/g, (character) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[character] || character);
      const flattenRows = (document) => (document?.sections || []).flatMap((section) => Array.isArray(section.rows) ? section.rows : []);
      const currentDocument = () => documents.find((document) => document.key === currentDocKey) || documents[0] || null;
      const countStateInDocument = (document, wanted) => flattenRows(document).filter((row) => selectionState[row.row_id] === wanted).length;
      const countPlainInDocument = (document) => flattenRows(document).filter((row) => !selectionState[row.row_id]).length;
      const specialViewKeys = new Set(["all", "plain", "green", "red"]);
      const isSpecialViewKey = (key) => specialViewKeys.has(String(key || ""));
      const barcodePatternFor = (value) => {{
        const source = String(value || "").trim() || "EMPTY";
        let bits = "1010";
        for (const character of source) {{
          const binary = character.charCodeAt(0).toString(2).padStart(8, "0");
          bits += binary + "0";
        }}
        bits += "10101";
        return bits;
      }};
      const barcodeFallbackSvgMarkup = (value) => {{
        const bits = barcodePatternFor(value);
        const width = bits.length * 2;
        let x = 0;
        let bars = "";
        for (const bit of bits) {{
          if (bit === "1") {{
            bars += `<rect x="${{x}}" y="0" width="2" height="28" fill="#111827"></rect>`;
          }}
          x += 2;
        }}
        return {{
          viewBox: `0 0 ${{width}} 28`,
          bars,
        }};
      }};
      const renderBarcodes = () => {{
        const barcodeNodes = Array.from(contentNode.querySelectorAll(".mfg-row-barcode-svg[data-barcode-value]"));
        for (const node of barcodeNodes) {{
          const value = node.getAttribute("data-barcode-value") || "";
          if (!value) continue;
          if (typeof window.JsBarcode === "function") {{
            try {{
              window.JsBarcode(node, value, {{
                format: "CODE128",
                lineColor: "#111827",
                width: 0.98,
                height: 34,
                margin: 2,
                displayValue: false,
                background: "transparent",
              }});
              node.removeAttribute("width");
              node.removeAttribute("height");
              node.setAttribute("preserveAspectRatio", "none");
              node.style.width = "100%";
              node.style.height = "30px";
              node.style.display = "block";
              continue;
            }} catch (_error) {{
            }}
          }}
          const fallback = barcodeFallbackSvgMarkup(value);
          node.setAttribute("viewBox", fallback.viewBox);
          node.setAttribute("preserveAspectRatio", "none");
          node.setAttribute("aria-hidden", "true");
          node.setAttribute("focusable", "false");
          node.innerHTML = fallback.bars;
        }}
      }};
      const setStatus = (message, tone = "") => {{
        statusNode.textContent = message;
        statusNode.classList.remove("is-error", "is-success");
        if (tone) statusNode.classList.add(tone);
      }};
      const nextRowState = (currentState) => {{
        if (currentState === "green") return "red";
        if (currentState === "red") return "clear";
        return "green";
      }};
      const normalizeSortText = (value) => String(value || "").trim().toLocaleLowerCase("hu-HU");
      const parseSizeParts = (value) =>
        String(value || "")
          .split(/x/i)
          .map((part) => Number.parseFloat(part.replace(",", ".").trim()))
          .filter((part) => Number.isFinite(part));
      const compareArrays = (left, right) => {{
        const maxLength = Math.max(left.length, right.length);
        for (let index = 0; index < maxLength; index += 1) {{
          const leftValue = Number.isFinite(left[index]) ? left[index] : -Infinity;
          const rightValue = Number.isFinite(right[index]) ? right[index] : -Infinity;
          if (leftValue !== rightValue) return leftValue - rightValue;
        }}
        return 0;
      }};
      const rowSortValue = (row, sortKey) => {{
        if (sortKey === "name") return normalizeSortText(row.name);
        if (sortKey === "size") return parseSizeParts(row.size);
        if (sortKey === "color") return normalizeSortText(row.color);
        if (sortKey === "edge") return normalizeSortText(row.edge);
        if (sortKey === "quantity") return Number(row.quantity || 0);
        if (sortKey === "code") return normalizeSortText(row.code || row.detail || row.row_id);
        return 0;
      }};
      const compareRowsBySort = (leftRow, rightRow) => {{
        if (currentSortKey === "pdf") return 0;
        const leftValue = rowSortValue(leftRow, currentSortKey);
        const rightValue = rowSortValue(rightRow, currentSortKey);
        let result = 0;
        if (Array.isArray(leftValue) && Array.isArray(rightValue)) {{
          result = compareArrays(leftValue, rightValue);
        }} else if (typeof leftValue === "number" && typeof rightValue === "number") {{
          result = leftValue - rightValue;
        }} else {{
          result = String(leftValue).localeCompare(String(rightValue), "hu-HU", {{ numeric: true, sensitivity: "base" }});
        }}
        if (result === 0) {{
          const leftFallback = normalizeSortText(leftRow.code || leftRow.row_id);
          const rightFallback = normalizeSortText(rightRow.code || rightRow.row_id);
          result = leftFallback.localeCompare(rightFallback, "hu-HU", {{ numeric: true, sensitivity: "base" }});
        }}
        return currentSortDirection === "desc" ? -result : result;
      }};
      const sortedRowsForView = (rows) => {{
        const items = Array.isArray(rows) ? [...rows] : [];
        if (currentSortKey === "pdf") return items;
        items.sort(compareRowsBySort);
        return items;
      }};
      const sortArrowFor = (sortKey) => {{
        if (currentSortKey !== sortKey) return "";
        return currentSortDirection === "desc" ? "↓" : "↑";
      }};
      const sortButtonMarkup = (sortKey, label) => {{
        const activeClass = currentSortKey === sortKey ? " is-active" : "";
        const arrow = sortArrowFor(sortKey);
        return `
          <button class="mfg-sort-head${{activeClass}}" type="button" data-sort-key="${{escapeHtml(sortKey)}}" title="${{escapeHtml(label)}}">
            <span class="mfg-sort-head-label">${{escapeHtml(label)}}</span>
            <span class="mfg-sort-head-arrow">${{escapeHtml(arrow)}}</span>
          </button>
        `;
      }};

      const sectionTabStateClass = (section) => {{
        const rows = Array.isArray(section?.rows) ? section.rows : [];
        if (!rows.length) return "";
        if (rows.some((row) => !selectionState[row.row_id])) return "";
        if (rows.every((row) => selectionState[row.row_id] === "green")) return " is-complete";
        if (rows.some((row) => selectionState[row.row_id] === "red")) return " is-alert";
        return "";
      }};
      const pairInfoForLabel = (label) => {{
        const text = String(label || "").trim();
        if (text.startsWith("1-es ")) return {{ side: "1", base: text.slice(5) }};
        if (text.startsWith("2-es ")) return {{ side: "2", base: text.slice(5) }};
        return null;
      }};
      const normalizedSectionLabel = (label) => String(label || "").trim();
      const pairedSectionKey = (document, sourceKey) => {{
        const sections = Array.isArray(document?.sections) ? document.sections : [];
        const currentSection = sections.find((section) => section.key === sourceKey);
        if (!currentSection) return "";
        const pairInfo = pairInfoForLabel(currentSection.label);
        if (!pairInfo) return "";
        const targetLabel = pairInfo.side === "1" ? `2-es ${{pairInfo.base}}` : `1-es ${{pairInfo.base}}`;
        const pairSection = sections.find((section) => normalizedSectionLabel(section.label) === targetLabel);
        return pairSection?.key || "";
      }};
      const orderedSectionsForTabs = (sections) => {{
        const items = Array.isArray(sections) ? sections : [];
        const labelMap = new Map(items.map((section) => [normalizedSectionLabel(section.label), section]));
        const used = new Set();
        const ordered = [];
        for (const section of items) {{
          if (!section || used.has(section.key)) continue;
          const pairInfo = pairInfoForLabel(section.label);
          if (pairInfo?.side === "2") {{
            const firstPair = labelMap.get(`1-es ${{pairInfo.base}}`);
            if (firstPair && !used.has(firstPair.key)) continue;
          }}
          used.add(section.key);
          ordered.push(section);
          if (pairInfo?.side === "1") {{
            const secondPair = labelMap.get(`2-es ${{pairInfo.base}}`);
            if (secondPair && !used.has(secondPair.key)) {{
              used.add(secondPair.key);
              ordered.push(secondPair);
            }}
          }}
        }}
        for (const section of items) {{
          if (!section || used.has(section.key)) continue;
          used.add(section.key);
          ordered.push(section);
        }}
        return ordered;
      }};

      const buildGroupsForView = (document) => {{
        if (!document) return [];
        const sections = orderedSectionsForTabs(Array.isArray(document.sections) ? document.sections : []);
        if (layoutMode === "double" && !isSpecialViewKey(currentViewKey)) {{
          const selectedKeys = [currentViewKey, secondaryViewKey].filter((key, index, items) => key && items.indexOf(key) === index);
          return selectedKeys
            .map((key) => sections.find((section) => section.key === key))
            .filter((section) => section && Array.isArray(section.rows) && section.rows.length);
        }}
        if (currentViewKey === "all") {{
          return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
        }}
        if (currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain") {{
          return sections
            .map((section) => ({{
              key: section.key,
              label: section.label,
              rows: (Array.isArray(section.rows) ? section.rows : []).filter((row) =>
                currentViewKey === "plain" ? !selectionState[row.row_id] : selectionState[row.row_id] === currentViewKey
              ),
            }}))
            .filter((section) => section.rows.length);
        }}
        const selectedSection = sections.find((section) => section.key === currentViewKey);
        return selectedSection ? [selectedSection] : [];
      }};

      const renderDocTabs = () => {{
        docTabsNode.innerHTML = documents.map((document) => `
          <button class="mfg-tab${{document.key === currentDocKey ? " is-active" : ""}}" type="button" data-doc-key="${{escapeHtml(document.key)}}">
            <strong>${{escapeHtml(document.label || document.key)}}</strong>
            <span>${{flattenRows(document).length}} sor</span>
          </button>
        `).join("");
      }};

      const renderSectionTabs = (document) => {{
        if (!document) {{
          sectionTabsNode.innerHTML = "";
          return;
        }}
        const sections = Array.isArray(document.sections) ? document.sections : [];
        const specialTabs = [
          {{ key: "all", label: "Összes", count: flattenRows(document).length }},
          {{ key: "plain", label: "Simák", count: countPlainInDocument(document) }},
          {{ key: "green", label: "Zöldek", count: countStateInDocument(document, "green") }},
          {{ key: "red", label: "Pirosak", count: countStateInDocument(document, "red") }},
        ];
        const sectionTabs = sections.map((section) => ({{
          key: section.key,
          label: section.label,
          count: Array.isArray(section.rows) ? section.rows.length : 0,
          stateClass: sectionTabStateClass(section),
          selectedClass: section.key === currentViewKey ? " is-active" : (layoutMode === "double" && section.key === secondaryViewKey ? " is-secondary" : ""),
        }}));
        sectionTabsNode.innerHTML = [...specialTabs, ...sectionTabs].map((item) => `
          <button class="mfg-section-tab${{item.selectedClass || (item.key === currentViewKey ? " is-active" : "")}}${{item.stateClass || ""}}" type="button" data-view-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
            <strong>${{escapeHtml(item.label)}}</strong>
            <small>${{item.count}}</small>
          </button>
        `).join("");
      }};

      const renderRows = (groups) => {{
        const isOverviewMode = currentViewKey === "all" || currentViewKey === "plain" || currentViewKey === "green" || currentViewKey === "red";
        const isSplitMode = layoutMode === "double" && !isSpecialViewKey(currentViewKey) && groups.length > 1;
        contentNode.classList.toggle("is-overview", isOverviewMode);
        contentNode.classList.toggle("is-split", isSplitMode);
        if (!groups.length) {{
          const emptyLabel = currentViewKey === "green"
            ? "Még nincs zöldre jelölt sor."
            : currentViewKey === "red"
              ? "Még nincs pirosra jelölt sor."
              : currentViewKey === "plain"
                ? "Minden sor kapott már kijelölést."
                : "Ehhez a nézethez nincs megjeleníthető sor.";
          contentNode.innerHTML = `
            <div class="mfg-empty">
              <div class="mfg-empty-copy">
                <strong>Nincs megjeleníthető sor.</strong>
                <div>${{escapeHtml(emptyLabel)}}</div>
              </div>
            </div>
          `;
          return;
        }}

        contentNode.innerHTML = groups.map((group) => {{
          const showSectionHeader = isOverviewMode || isSplitMode;
          const headMarkup = showSectionHeader
            ? `
              <div class="mfg-section-head">
                <div class="mfg-section-title">${{escapeHtml(group.label)}}</div>
                <div class="mfg-section-count">${{group.rows.length}} sor</div>
              </div>
            `
            : "";
          const tableHeadMarkup = `
            <div class="mfg-table-head">
              ${{sortButtonMarkup("name", "Megnevezés")}}
              ${{sortButtonMarkup("size", "Méret")}}
              ${{sortButtonMarkup("color", "Szín")}}
              ${{sortButtonMarkup("edge", "Él")}}
              ${{sortButtonMarkup("quantity", "Menny.")}}
              ${{sortButtonMarkup("code", "Vonalkód")}}
            </div>
          `;
          const rowMarkup = sortedRowsForView(group.rows).map((row) => {{
            const rowState = selectionState[row.row_id] || "";
            const detailText = row.detail || "";
            const subtitleMarkup = detailText ? `<div class="mfg-row-subtitle">${{escapeHtml(detailText)}}</div>` : "";
            return `
              <button class="mfg-row${{rowState ? ` is-${{rowState}}` : ""}}" type="button" data-mfg-row data-row-id="${{escapeHtml(row.row_id)}}">
                <div class="mfg-row-main">
                  <div class="mfg-row-title">${{escapeHtml(row.name || "Névtelen sor")}}</div>
                  ${{subtitleMarkup}}
                </div>
                <div class="mfg-row-meta">
                  <span class="is-size">${{escapeHtml(row.size || "Méret nélkül")}}</span>
                </div>
                <div class="mfg-row-meta">
                  <span class="is-color">${{escapeHtml(row.color || "Szín nélkül")}}</span>
                </div>
                <div class="mfg-row-meta">
                  <span>${{escapeHtml(row.edge || "Él nélkül")}}</span>
                </div>
                <div class="mfg-row-side">
                  <div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div>
                </div>
                <div class="mfg-row-barcode-wrap">
                  <div class="mfg-row-barcode">
                    <svg class="mfg-row-barcode-svg" data-barcode-value="${{escapeHtml(row.code || row.detail || row.row_id)}}"></svg>
                  </div>
                  <div class="mfg-row-code">${{escapeHtml(row.code || row.detail || "Kód nélkül")}}</div>
                </div>
              </button>
            `;
          }}).join("");
          return `<section class="mfg-section-card" data-section-key="${{escapeHtml(group.key || "")}}">${{headMarkup}}${{tableHeadMarkup}}<div class="mfg-row-list" data-section-key="${{escapeHtml(group.key || "")}}">${{rowMarkup}}</div></section>`;
        }}).join("");
      }};

      const captureScrollState = () => {{
        const listScroll = {{}};
        Array.from(contentNode.querySelectorAll(".mfg-row-list[data-section-key]")).forEach((node) => {{
          const key = node.getAttribute("data-section-key") || "";
          if (key) listScroll[key] = node.scrollTop;
        }});
        return {{
          pageY: window.scrollY || window.pageYOffset || 0,
          listScroll,
        }};
      }};

      const restoreScrollState = (snapshot) => {{
        if (!snapshot) return;
        const listScroll = snapshot.listScroll || {{}};
        Array.from(contentNode.querySelectorAll(".mfg-row-list[data-section-key]")).forEach((node) => {{
          const key = node.getAttribute("data-section-key") || "";
          if (key && Object.prototype.hasOwnProperty.call(listScroll, key)) {{
            node.scrollTop = Number(listScroll[key] || 0);
          }}
        }});
        window.scrollTo(0, Number(snapshot.pageY || 0));
      }};

      const renderAll = (snapshot = null) => {{
        const scrollState = snapshot || captureScrollState();
        const document = currentDocument();
        renderDocTabs();
        renderSectionTabs(document);
        Array.from(layoutToggleNode.querySelectorAll("[data-layout-mode]")).forEach((button) => {{
          const mode = button.getAttribute("data-layout-mode") || "single";
          button.classList.toggle("is-active", mode === layoutMode);
        }});
        renderRows(buildGroupsForView(document));
        renderBarcodes();
        requestAnimationFrame(() => restoreScrollState(scrollState));
      }};

      const persistRowState = async (rowId, nextState, previousState) => {{
        try {{
          const response = await fetch(stateRoute, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              production_number: productionNumber,
              row_id: rowId,
              state: nextState || "clear",
            }}),
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "A mentés nem sikerült.");
          }}
          setStatus("Mentve.", "is-success");
        }} catch (error) {{
          if (previousState) selectionState[rowId] = previousState;
          else delete selectionState[rowId];
          renderAll();
          setStatus(error instanceof Error ? error.message : "A mentés nem sikerült.", "is-error");
        }}
      }};

      const applyRowState = (rowId, targetState) => {{
        const scrollState = captureScrollState();
        const previousState = selectionState[rowId] || "";
        if (targetState === "clear") delete selectionState[rowId];
        else selectionState[rowId] = targetState;
        renderAll(scrollState);
        setStatus("Mentés...");
        void persistRowState(rowId, targetState, previousState);
      }};

      docTabsNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-doc-key]");
        if (!(button instanceof HTMLElement)) return;
        const nextDocKey = button.getAttribute("data-doc-key") || "";
        if (!nextDocKey || nextDocKey === currentDocKey) return;
        currentDocKey = nextDocKey;
        currentViewKey = "all";
        secondaryViewKey = "";
        renderAll();
      }});

      sectionTabsNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-view-key]");
        if (!(button instanceof HTMLElement)) return;
        const nextViewKey = button.getAttribute("data-view-key") || "all";
        if (isSpecialViewKey(nextViewKey)) {{
          if (nextViewKey === currentViewKey && !secondaryViewKey) return;
          currentViewKey = nextViewKey;
          secondaryViewKey = "";
          renderAll();
          return;
        }}
        if (layoutMode === "double") {{
          const activeDocument = currentDocument();
          if (isSpecialViewKey(currentViewKey)) {{
            currentViewKey = nextViewKey;
            secondaryViewKey = pairedSectionKey(activeDocument, nextViewKey);
          }} else if (nextViewKey === currentViewKey || nextViewKey === secondaryViewKey) {{
            return;
          }} else {{
            currentViewKey = nextViewKey;
            secondaryViewKey = pairedSectionKey(activeDocument, nextViewKey);
          }}
        }} else {{
          if (nextViewKey === currentViewKey) return;
          currentViewKey = nextViewKey;
          secondaryViewKey = "";
        }}
        renderAll();
      }});

      layoutToggleNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-layout-mode]");
        if (!(button instanceof HTMLElement)) return;
        const nextMode = button.getAttribute("data-layout-mode") || "single";
        if (nextMode === layoutMode) return;
        layoutMode = nextMode === "double" ? "double" : "single";
        if (layoutMode === "single") {{
          secondaryViewKey = "";
        }} else if (isSpecialViewKey(currentViewKey)) {{
          currentViewKey = "all";
          secondaryViewKey = "";
        }} else {{
          secondaryViewKey = pairedSectionKey(currentDocument(), currentViewKey);
        }}
        renderAll();
      }});

      contentNode.addEventListener("click", (event) => {{
        const sortButton = event.target.closest("[data-sort-key]");
        if (sortButton instanceof HTMLElement) {{
          event.preventDefault();
          event.stopPropagation();
          const nextSortKey = sortButton.getAttribute("data-sort-key") || "pdf";
          if (currentSortKey !== nextSortKey) {{
            currentSortKey = nextSortKey;
            currentSortDirection = "asc";
          }} else if (currentSortDirection === "asc") {{
            currentSortDirection = "desc";
          }} else {{
            currentSortKey = "pdf";
            currentSortDirection = "asc";
          }}
          renderAll();
          return;
        }}
        const row = event.target.closest("[data-mfg-row]");
        if (!(row instanceof HTMLElement)) return;
        const rowId = row.getAttribute("data-row-id") || "";
        if (!rowId) return;
        const currentState = selectionState[rowId] || "";
        applyRowState(rowId, nextRowState(currentState));
      }});

      renderAll();
    }})();
  </script>
  <script src="/script.js"></script>
</body>
</html>"""
    return page.encode("utf-8")
