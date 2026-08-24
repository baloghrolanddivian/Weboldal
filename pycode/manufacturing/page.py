"""HTML page rendering for the manufacturing papers workflow."""

from __future__ import annotations

import html
import json
import urllib.parse
from datetime import date


def _json_script_payload(payload: object) -> str:
    """Serialize JSON safely for embedding inside a script tag."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_manufacturing_page(
    *,
    route: str,
    data_route: str,
    state_route: str,
    partial_qty_route: str,
    report_ready_route: str,
    topfloor_box_route: str = "",
    topfloor_transfer_route: str = "",
    admin_revision_route: str = "",
    admin_change_revision: str = "",
    topfloor_storage_box_types: list[dict[str, object]] | None = None,
    selected_number: str,
    direct_lookup: bool = False,
    operations: list[dict[str, str]],
    selected_operation: str,
    recent_productions: list[dict[str, str]],
    production_client_cache: list[dict[str, object]] | None,
    bundle: dict,
    selection_state: dict[str, str],
    partial_quantity_state: dict[str, str],
    message: str = "",
    success: bool = False,
) -> bytes:
    """Render the manufacturing papers single-page application shell."""
    documents = bundle.get("documents", [])
    selected_operation_key = str(selected_operation or "").strip()
    active_document = next(
        (
            document
            for document in documents
            if isinstance(document, dict) and str(document.get("key", "")).strip() == selected_operation_key
        ),
        None,
    )
    all_documents = [document for document in documents if isinstance(document, dict)]
    visible_documents = [active_document] if isinstance(active_document, dict) else all_documents
    total_rows = int(active_document.get("row_count", 0) or 0) if isinstance(active_document, dict) else 0
    green_count = sum(1 for value in selection_state.values() if value == "green")
    red_count = sum(1 for value in selection_state.values() if value == "red")
    active_source_label = str(active_document.get("sourceLabel", "")).strip() if isinstance(active_document, dict) else ""
    active_source_markup = (
        f'<span class="mfg-operation-source">{html.escape(active_source_label)}</span>'
        if active_source_label
        else ""
    )

    notice_markup = ""
    if message:
        notice_class = "mfg-notice is-success" if success else "mfg-notice is-error"
        notice_markup = f'<div class="{notice_class}">{html.escape(message)}</div>'

    selected_operation_query = (
        f"&operation={urllib.parse.quote(selected_operation_key)}" if selected_operation_key else ""
    )

    def chip_href(entry: dict) -> str:
        entry_kind = str(entry.get("kind", ""))
        if entry_kind == "missing":
            return "#pantolo-missing"
        entry_number = str(entry.get("number", ""))
        target_number = selected_number if entry_kind == "shipment" else entry_number
        target_query = f"production={urllib.parse.quote(target_number)}" if target_number else ""
        if target_query and selected_operation_query:
            return f"{route}?{target_query}{selected_operation_query}"
        if target_query:
            return f"{route}?{target_query}"
        if selected_operation_key:
            return f"{route}?operation={urllib.parse.quote(selected_operation_key)}"
        return route

    def chip_attrs(entry: dict) -> str:
        if str(entry.get("kind", "")) == "missing":
            return 'data-mfg-missing-link data-view-key="pantolo-missing"'
        if str(entry.get("kind", "")) == "shipment":
            view_key = str(entry.get("view_key", ""))
            all_shipments_attr = " data-mfg-all-shipments" if view_key == "shipment::__all__" else ""
            return (
                "data-mfg-shipment-link "
                f'data-view-key="{html.escape(view_key, quote=True)}"{all_shipments_attr}'
            )
        return (
            "data-mfg-production-link "
            f'data-production-number="{html.escape(str(entry.get("number", "")), quote=True)}"'
        )

    def chip_state_class(entry: dict) -> str:
        status = str(entry.get("state_status", "") or "").strip().lower()
        if status == "done":
            return " is-done"
        if status == "red":
            return " is-red"
        if status == "green" or bool(entry.get("is_complete")):
            return " is-complete"
        return ""

    def chip_shipment_date(entry: dict) -> str:
        if str(entry.get("kind", "")) != "shipment" or str(entry.get("view_key", "")) == "shipment::__all__":
            return ""
        value = str(entry.get("shipment_date", "") or "").strip()
        try:
            date.fromisoformat(value)
        except ValueError:
            return ""
        return value

    def chip_date_class(entry: dict) -> str:
        value = chip_shipment_date(entry)
        if not value:
            return ""
        days = (date.fromisoformat(value) - date.today()).days
        tone = "red" if days <= 0 else ("orange" if days <= 7 else "yellow")
        return f" has-shipment-date is-date-{tone}"

    def chip_shipment_date_html(entry: dict) -> str:
        value = chip_shipment_date(entry)
        return f'<span class="mfg-chip-shipment-date">{html.escape(value)}</span>' if value else ""

    def chip_issued_edit_class(entry: dict) -> str:
        return " has-issued-row-edit" if bool(entry.get("has_issued_row_edit")) else ""

    def chip_number_text(entry: dict) -> str:
        entry_number = str(entry.get("number", ""))
        if str(entry.get("kind", "")) == "missing":
            return f"{max(0, int(entry.get('count', 0) or 0))} tétel"
        if str(entry.get("kind", "")) != "shipment":
            return entry_number
        try:
            category_count = max(0, int(entry.get("count", 0) or 0))
        except (TypeError, ValueError):
            category_count = 0
        try:
            issued_count = max(0, int(entry.get("issued_count", 0) or 0))
        except (TypeError, ValueError):
            issued_count = 0
        if category_count:
            ratio_text = f"{min(issued_count, category_count)}/{category_count}"
            if str(entry.get("view_key", "")) == "shipment::__all__":
                return ratio_text
            return f"{entry_number} · {ratio_text}"
        return entry_number

    recent_chips_html = "".join(
        (
            f'<a class="mfg-chip-link{" is-active" if bool(entry.get("is_active")) else ""}{chip_state_class(entry)}{chip_date_class(entry)}{chip_issued_edit_class(entry)}" '
            f'href="{chip_href(entry)}" '
            f"{chip_attrs(entry)}>"
            f'<span class="mfg-chip-date">{html.escape(str(entry.get("date_label", "") or "Dátum nélkül"))}</span>'
            f'<span class="mfg-chip-number">{html.escape(chip_number_text(entry))}</span>'
            f'{chip_shipment_date_html(entry)}'
            f"</a>"
        )
        for entry in recent_productions
    )
    direct_lookup_markup = (
        """
      <form class="mfg-production-lookup" id="mfg-production-lookup">
        <label for="mfg-production-number">Korábbi gyártás</label>
        <div>
          <input id="mfg-production-number" name="production" type="number" min="1" step="1" inputmode="numeric" placeholder="Gyártási szám" required />
          <button type="submit">Betöltés</button>
        </div>
      </form>
        """
        if selected_operation_key and selected_operation_key != "topfloor"
        else ""
    )
    toolbar_markup = (
        f"""
    <section class="mfg-toolbar">
      <div class="mfg-chip-row" id="mfg-chip-row">{recent_chips_html}</div>
      <button class="mfg-cache-refresh-button" id="mfg-cache-refresh" type="button" title="Frissites">&#8635;</button>
    </section>
        """
        if recent_chips_html
        else ""
    )
    picker_href = route
    operation_buttons_html = "".join(
        (
            f'<a class="mfg-operation-button{" is-active" if str(item.get("key", "")) == selected_operation_key else ""}" '
            f'href="{route}?operation={urllib.parse.quote(str(item.get("key", "")))}">'
            f'<strong>{html.escape(str(item.get("label", "")))}</strong>'
            f"</a>"
        )
        for item in operations
    )
    operation_panel_html = f"""
      <section class="mfg-operation-panel">
        <div class="mfg-operation-copy">
          <span class="mfg-kicker">Művelet</span>
          <h2>Mit szeretnél csinálni?</h2>
        </div>
        <div class="mfg-operation-grid">
          {operation_buttons_html}
        </div>
      </section>
    """
    operation_header_html = (
        f"""
      <section class="mfg-operation-header">
        <div class="mfg-operation-heading">
          <div>
            <span class="mfg-kicker">Kiválasztott művelet</span>
            <strong id="mfg-operation-title">{html.escape(str(active_document.get("label", "")))}</strong>
            <span class="mfg-operation-source" id="mfg-operation-source"{"" if active_source_label else " hidden"}>{html.escape(active_source_label)}</span>
          </div>
          {direct_lookup_markup}
        </div>
        <a class="mfg-picker-back" href="{picker_href}">Másik művelet</a>
      </section>
        """
        if active_document is not None
        else ""
    )
    board_class = "mfg-board" if active_document is not None else "mfg-board is-hidden"
    payload_json = _json_script_payload(
        {
            "productionNumber": selected_number,
            "directLookup": direct_lookup,
            "route": route,
            "dataRoute": data_route,
            "folder": bundle.get("folder", ""),
            "documents": visible_documents,
            "currentDocumentKey": selected_operation_key,
            "recentProductions": recent_productions,
            "productionClientCache": production_client_cache or [],
            "selectionState": selection_state,
            "stateRoute": state_route,
            "partialQuantityState": partial_quantity_state,
            "partialQtyRoute": partial_qty_route,
            "reportReadyRoute": report_ready_route,
            "topfloorBoxRoute": topfloor_box_route,
            "topfloorTransferRoute": topfloor_transfer_route,
            "adminRevisionRoute": admin_revision_route,
            "adminChangeRevision": admin_change_revision,
            "topfloorStorageBoxTypes": topfloor_storage_box_types or [],
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
      --mfg-done-bg: #0c8d57;
      --mfg-done-line: #047857;
      --mfg-done-text: #f4fff8;
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
      overflow-x: hidden;
    }}
    body {{
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }}
    a {{ color: inherit; text-decoration: none; }}
    button, input {{ font: inherit; }}
    .mfg-page {{
      width: 100%;
      max-width: 100vw;
      min-height: 100vh;
      padding: 8px 8px 16px;
      display: grid;
      gap: 0;
      align-content: start;
      overflow-x: visible;
    }}
    body.has-mfg-scroll-rail .mfg-page {{
      padding-right: 64px;
    }}
    .mfg-scroll-rail {{
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 30;
      width: 56px;
      display: none;
      touch-action: pan-y;
      background:
        linear-gradient(90deg, rgba(243, 245, 247, 0), rgba(243, 245, 247, 0.96) 34%),
        repeating-linear-gradient(
          180deg,
          rgba(17, 24, 39, 0.16) 0,
          rgba(17, 24, 39, 0.16) 12px,
          rgba(255, 255, 255, 0.7) 12px,
          rgba(255, 255, 255, 0.7) 24px
        );
      border-left: 1px solid rgba(17, 24, 39, 0.12);
    }}
    body.has-mfg-scroll-rail .mfg-scroll-rail {{
      display: block;
    }}
    .mfg-toolbar,
    .mfg-board,
    .mfg-notice {{
      width: min(1280px, calc(100vw - 16px));
      margin: 0 auto;
      justify-self: center;
    }}
    body.has-mfg-scroll-rail .mfg-toolbar,
    body.has-mfg-scroll-rail .mfg-board,
    body.has-mfg-scroll-rail .mfg-notice {{
      width: min(1280px, calc(100vw - 80px));
    }}
    .mfg-toolbar {{
      padding: 8px 10px;
      min-height: 64px;
      border-radius: 18px 18px 0 0;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid rgba(18, 20, 23, 0.08);
      border-bottom: 0;
      box-shadow: 0 10px 22px rgba(17, 24, 39, 0.05);
      display: flex;
      align-items: center;
      gap: 10px;
      overflow: hidden;
    }}
    .mfg-production-lookup {{
      flex: 0 0 auto;
      display: grid;
      gap: 3px;
    }}
    .mfg-production-lookup label {{
      color: var(--mfg-muted);
      font-size: 0.66rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .mfg-production-lookup > div {{
      display: flex;
      gap: 5px;
    }}
    .mfg-production-lookup input {{
      width: 132px;
      min-height: 36px;
      padding: 0 10px;
      border: 1px solid var(--mfg-line);
      border-radius: 10px;
      background: #fff;
      color: var(--mfg-text);
      font-weight: 800;
    }}
    .mfg-production-lookup input:focus {{
      outline: none;
      border-color: #111827;
      box-shadow: 0 0 0 3px rgba(17, 24, 39, 0.08);
    }}
    .mfg-production-lookup button {{
      min-height: 36px;
      padding: 0 11px;
      border: 1px solid #111827;
      border-radius: 10px;
      background: #111827;
      color: #fff;
      font-weight: 800;
      cursor: pointer;
    }}
    .mfg-production-lookup.is-loading {{
      opacity: 0.62;
      pointer-events: none;
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
    .mfg-operation-panel,
    .mfg-operation-header {{
      width: min(1280px, calc(100vw - 16px));
      margin: 0 auto;
      justify-self: center;
      border-radius: var(--mfg-radius-xl);
      border: 1px solid rgba(18, 20, 23, 0.08);
      background: var(--mfg-panel);
      box-shadow: var(--mfg-shadow);
    }}
    body.has-mfg-scroll-rail .mfg-operation-panel,
    body.has-mfg-scroll-rail .mfg-operation-header {{
      width: min(1280px, calc(100vw - 80px));
    }}
    .mfg-operation-panel {{
      padding: 18px;
      display: grid;
      gap: 16px;
      margin-top: 8px;
    }}
    .mfg-operation-copy {{
      display: grid;
      gap: 8px;
    }}
    .mfg-operation-copy h2 {{
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(1.12rem, 1.6vw, 1.5rem);
      line-height: 1.05;
    }}
    .mfg-operation-copy p {{
      margin: 0;
      color: var(--mfg-muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .mfg-operation-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .mfg-operation-button {{
      min-height: 110px;
      padding: 18px 20px;
      border-radius: 22px;
      border: 1px solid var(--mfg-line);
      background: linear-gradient(180deg, #ffffff, #f7fafc);
      display: grid;
      gap: 8px;
      align-content: center;
      transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
    }}
    .mfg-operation-button:hover {{
      transform: translateY(-2px);
      border-color: #111827;
      box-shadow: 0 18px 30px rgba(17, 24, 39, 0.12);
    }}
    .mfg-operation-button.is-active {{
      border-color: #111827;
      background: #111827;
      color: #ffffff;
    }}
    .mfg-operation-button strong {{
      font-size: 1rem;
      font-weight: 800;
    }}
    .mfg-operation-button span {{
      color: var(--mfg-muted);
      font-size: 0.82rem;
      line-height: 1.35;
    }}
    .mfg-operation-button.is-active span {{
      color: rgba(255, 255, 255, 0.76);
    }}
    .mfg-operation-header {{
      margin-top: 8px;
      margin-bottom: 8px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .mfg-operation-heading {{
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 18px;
    }}
    .mfg-operation-heading > div:first-child {{
      flex: 0 1 auto;
      min-width: 0;
    }}
    .mfg-operation-header strong {{
      display: block;
      margin-top: 4px;
      font-size: 1rem;
      font-weight: 800;
    }}
    .mfg-operation-source {{
      display: block;
      margin-top: 2px;
      color: var(--mfg-muted);
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .mfg-picker-back {{
      min-height: 40px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--mfg-line);
      background: #f7f9fb;
      display: inline-flex;
      align-items: center;
      font-size: 0.86rem;
      font-weight: 800;
      white-space: nowrap;
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
    .mfg-issued-edit-warning {{
      margin: 0 0 10px;
      padding: 10px 14px;
      border: 2px solid #dc2626;
      border-radius: 12px;
      background: #fff1f2;
      box-shadow: 0 0 14px rgba(220, 38, 38, 0.28);
      color: #991b1b;
      font-size: 0.82rem;
      font-weight: 900;
    }}
    .mfg-issued-edit-warning[hidden] {{
      display: none;
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
      min-height: 44px;
      overflow-x: auto;
      overflow-y: hidden;
      align-items: center;
      flex-wrap: nowrap;
      flex: 1 1 auto;
      min-width: 0;
    }}
    .mfg-cache-refresh-button {{
      flex: 0 0 auto;
      width: 36px;
      height: 36px;
      border-radius: 999px;
      border: 1px solid var(--mfg-line);
      background: #ffffff;
      color: #111827;
      font-size: 1rem;
      font-weight: 800;
      line-height: 1;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .mfg-cache-refresh-button:hover {{
      border-color: #111827;
      background: #f5f7f9;
    }}
    .mfg-cache-refresh-button.is-loading {{
      opacity: 0.62;
      pointer-events: none;
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
    /* The chip layout sets display explicitly, so reinforce the HTML hidden state. */
    .mfg-chip-link[hidden] {{
      display: none;
    }}
    .mfg-chip-link[data-mfg-all-shipments] {{
      position: sticky;
      left: 0;
      z-index: 3;
      box-shadow: 8px 0 14px rgba(255, 255, 255, 0.92);
    }}
    .mfg-chip-link.is-active {{
      border-color: #111827;
      color: #111827;
      background: #eef2f6;
    }}
    .mfg-chip-link.is-complete {{
      border-color: rgba(12, 141, 87, 0.42);
      background: #e8f8ef;
      color: #0b6c44;
    }}
    .mfg-chip-link.is-complete .mfg-chip-number {{
      color: #0b6c44;
    }}
    .mfg-chip-link.is-complete.is-active {{
      border-color: #0b6c44;
      background: #dcf3e7;
      color: #0b6c44;
    }}
    .mfg-chip-link.is-red {{
      border-color: var(--mfg-red-line);
      background: var(--mfg-red-bg);
      color: var(--mfg-red-text);
    }}
    .mfg-chip-link.is-red .mfg-chip-number {{
      color: var(--mfg-red-text);
    }}
    .mfg-chip-link.is-red.is-active {{
      border-color: var(--mfg-red-text);
      background: #ffdcdc;
      color: var(--mfg-red-text);
    }}
    .mfg-chip-link.is-done {{
      border-color: var(--mfg-done-line);
      background: var(--mfg-done-bg);
      color: var(--mfg-done-text);
    }}
    .mfg-chip-link.is-done .mfg-chip-number {{
      color: rgba(244, 255, 248, 0.86);
    }}
    .mfg-chip-link.is-done.is-active {{
      border-color: #064e3b;
      background: #047857;
      color: #ffffff;
    }}
    .mfg-chip-link.is-done.is-active .mfg-chip-number {{
      color: rgba(255, 255, 255, 0.92);
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
    .mfg-chip-link.has-shipment-date {{
      min-height: 52px;
      border-radius: 18px;
      padding-top: 6px;
      padding-bottom: 6px;
    }}
    .mfg-chip-link.is-date-yellow {{
      border-color: #e5bd36;
      background: #fff3b0;
      color: #624a00;
    }}
    .mfg-chip-link.is-date-orange {{
      border-color: #ed8b2d;
      background: #ffd5a3;
      color: #7a3300;
    }}
    .mfg-chip-link.is-date-red {{
      border-color: #dc2626;
      background: #fecaca;
      color: #991b1b;
    }}
    .mfg-chip-link.is-done.has-shipment-date {{
      border-color: var(--mfg-done-line);
      background: var(--mfg-done-bg);
      color: var(--mfg-done-text);
    }}
    .mfg-chip-link.has-shipment-date.is-active {{
      box-shadow:
        inset 0 0 0 2px #111827,
        0 1px 3px rgba(17, 24, 39, 0.24);
    }}
    .mfg-chip-link.is-done.has-shipment-date.is-active {{
      border-color: #064e3b;
      background: #047857;
      color: #ffffff;
    }}
    .mfg-chip-link.has-issued-row-edit {{
      border-color: #dc2626;
      box-shadow:
        inset 0 0 0 2px #dc2626,
        0 0 12px rgba(220, 38, 38, 0.72);
    }}
    .mfg-chip-link.is-date-yellow .mfg-chip-number,
    .mfg-chip-link.is-date-yellow .mfg-chip-shipment-date {{
      color: #624a00;
    }}
    .mfg-chip-link.is-date-orange .mfg-chip-number,
    .mfg-chip-link.is-date-orange .mfg-chip-shipment-date {{
      color: #7a3300;
    }}
    .mfg-chip-link.is-date-red .mfg-chip-number,
    .mfg-chip-link.is-date-red .mfg-chip-shipment-date {{
      color: #991b1b;
    }}
    .mfg-chip-link.is-done.has-shipment-date .mfg-chip-number,
    .mfg-chip-link.is-done.has-shipment-date .mfg-chip-shipment-date {{
      color: rgba(244, 255, 248, 0.86);
    }}
    .mfg-chip-link.is-done.has-shipment-date.is-active .mfg-chip-number,
    .mfg-chip-link.is-done.has-shipment-date.is-active .mfg-chip-shipment-date {{
      color: rgba(255, 255, 255, 0.92);
    }}
    .mfg-chip-shipment-date {{
      margin-top: 2px;
      font-size: 0.61rem;
      line-height: 1;
      font-weight: 800;
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
      display: block;
      border-top-left-radius: 0;
      border-top-right-radius: 0;
      overflow: visible;
    }}
    .mfg-board > * + * {{
      margin-top: 8px;
    }}
    .mfg-board.is-hidden {{
      display: none;
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
    .mfg-search-row {{
      width: min(50vw, 620px);
      max-width: 100%;
      min-height: 42px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px;
      border: 1px solid rgba(17, 24, 39, 0.08);
      border-radius: 16px;
      background: #f8fafc;
      overflow: hidden;
    }}
    .mfg-search-row[hidden] {{
      display: none;
    }}
    .mfg-search-input {{
      flex: 1 1 auto;
      min-width: 160px;
      height: 32px;
      padding: 0 12px;
      border: 1px solid var(--mfg-line);
      border-radius: 12px;
      background: #ffffff;
      color: var(--mfg-text);
      font-size: 0.86rem;
      font-weight: 700;
      outline: none;
    }}
    .mfg-search-input:focus {{
      border-color: #111827;
      box-shadow: 0 0 0 3px rgba(17, 24, 39, 0.08);
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
    .mfg-status-actions {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .mfg-report-button {{
      min-height: 32px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid #0b6c44;
      background: linear-gradient(180deg, #12a566, #0c8d57);
      color: #ffffff;
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.01em;
      cursor: pointer;
      display: none;
      align-items: center;
      justify-content: center;
      box-shadow: 0 3px 10px rgba(8, 109, 67, 0.24);
      transition: transform 120ms ease, box-shadow 120ms ease, filter 120ms ease;
    }}
    .mfg-report-button.is-loading {{
      position: relative;
      padding-right: 30px;
    }}
    .mfg-report-button.is-loading::after {{
      content: "";
      position: absolute;
      right: 12px;
      top: 50%;
      width: 12px;
      height: 12px;
      margin-top: -6px;
      border-radius: 999px;
      border: 2px solid rgba(255, 255, 255, 0.35);
      border-top-color: #ffffff;
      animation: mfg-report-spin 0.72s linear infinite;
    }}
    @keyframes mfg-report-spin {{
      from {{ transform: rotate(0deg); }}
      to {{ transform: rotate(360deg); }}
    }}
    .mfg-report-button:hover {{
      filter: brightness(1.04);
      box-shadow: 0 5px 14px rgba(8, 109, 67, 0.3);
      transform: translateY(-1px);
    }}
    .mfg-report-button:active {{
      transform: translateY(0);
      box-shadow: 0 2px 8px rgba(8, 109, 67, 0.22);
    }}
    .mfg-report-button:disabled {{
      opacity: 0.55;
      cursor: default;
      transform: none;
      box-shadow: none;
    }}
    .mfg-issued-toggle {{
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(17, 24, 39, 0.12);
      background: #ffffff;
      color: #334155;
      font-size: 0.76rem;
      font-weight: 800;
      cursor: pointer;
      display: none;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }}
    .mfg-issued-toggle.is-active {{
      border-color: var(--mfg-done-line);
      background: var(--mfg-done-bg);
      color: var(--mfg-done-text);
    }}
    .mfg-topfloor-actions {{
      display: grid;
      gap: 8px;
      align-content: start;
      justify-items: start;
    }}
    .mfg-topfloor-box-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }}
    .mfg-topfloor-button-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: nowrap;
    }}
    .mfg-topfloor-title {{
      display: grid;
      gap: 2px;
      font-size: 13px;
      line-height: 1.25;
      color: #111827;
    }}
    .mfg-topfloor-title span {{
      font-weight: 500;
    }}
    .mfg-topfloor-title strong {{
      font-weight: 800;
    }}
    .mfg-topfloor-description {{
      width: min(320px, 42vw);
      max-width: 100%;
      min-height: 34px;
      border: 1px solid rgba(15, 23, 42, 0.16);
      border-radius: 6px;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 700;
      color: #172033;
      background: #ffffff;
    }}
    .mfg-topfloor-button {{
      min-height: 34px;
      min-width: 118px;
      padding: 7px 10px;
      border-radius: 6px;
      border: 1px solid rgba(15, 23, 42, 0.14);
      background: #ffffff;
      color: #172033;
      font-size: 12px;
      font-weight: 800;
      cursor: pointer;
    }}
    .mfg-topfloor-button:not(:disabled):hover {{
      border-color: rgba(22, 101, 52, 0.32);
      color: #166534;
    }}
    .mfg-topfloor-button:disabled {{
      opacity: 0.42;
      cursor: default;
    }}
    .mfg-topfloor-select {{
      min-height: 34px;
      min-width: 170px;
      border: 1px solid rgba(15, 23, 42, 0.14);
      border-radius: 6px;
      padding: 7px 10px;
      background: #ffffff;
      color: #172033;
      font-size: 12px;
      font-weight: 800;
    }}
    .mfg-topfloor-issued {{
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      border-radius: 6px;
      padding: 7px 10px;
      background: rgba(5, 46, 22, 0.24);
      color: #ffffff;
      font-size: 12px;
      font-weight: 900;
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
      padding-bottom: 8px;
      scrollbar-width: thin;
      align-items: stretch;
      flex-wrap: nowrap;
    }}
    .mfg-tab-row {{
      min-height: 50px;
      max-height: 50px;
    }}
    .mfg-section-tab-row {{
      min-height: 42px;
      max-height: 42px;
    }}
    .mfg-subsection-tab-row {{
      display: flex;
      gap: 6px;
      overflow-x: auto;
      overflow-y: hidden;
      padding: 6px 0 10px;
      scrollbar-width: thin;
      align-items: stretch;
      flex-wrap: nowrap;
      min-height: 42px;
      max-height: 42px;
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
      min-width: 190px;
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
    .mfg-subsection-tab {{
      flex: 0 0 auto;
      min-height: 32px;
      max-height: 32px;
      padding: 0 10px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid rgba(17, 24, 39, 0.1);
      background: #f8fafc;
      color: #334155;
      border-radius: 16px;
      cursor: pointer;
      font-weight: 700;
      overflow: hidden;
      transition: background 180ms ease, border-color 180ms ease, color 180ms ease;
    }}
    .mfg-subsection-tab strong {{
      font-size: 0.82rem;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-subsection-tab small {{
      color: #64748b;
      font-size: 0.7rem;
      flex: 0 0 auto;
    }}
    .mfg-subsection-tab.is-active {{
      border-color: #0f172a;
      background: #0f172a;
      color: #fff;
    }}
    .mfg-subsection-tab.is-active small {{
      color: rgba(255, 255, 255, 0.76);
    }}
    .mfg-subsection-tab.is-complete {{
      border-color: var(--mfg-green-line);
      background: var(--mfg-green-bg);
      color: var(--mfg-green-text);
    }}
    .mfg-subsection-tab.is-complete small {{
      color: var(--mfg-green-text);
      opacity: 0.82;
    }}
    .mfg-subsection-tab.is-complete.is-active {{
      border-color: var(--mfg-green-line);
      background: #cdeed9;
      color: var(--mfg-green-text);
    }}
    .mfg-subsection-tab.is-complete.is-active small {{
      color: var(--mfg-green-text);
      opacity: 0.9;
    }}
    .mfg-subsection-tab.is-done {{
      border-color: var(--mfg-done-line);
      background: var(--mfg-done-bg);
      color: var(--mfg-done-text);
    }}
    .mfg-subsection-tab.is-done strong {{
      color: #ffffff;
    }}
    .mfg-subsection-tab.is-done small {{
      color: rgba(255, 255, 255, 0.9);
    }}
    .mfg-subsection-tab.is-done.is-active {{
      border-color: #064e3b;
      background: #047857;
      color: #ffffff;
    }}
    .mfg-subsection-tab.is-done.is-active small {{
      color: rgba(255, 255, 255, 0.9);
    }}
    .mfg-subsection-tab.is-alert {{
      border-color: var(--mfg-red-line);
      background: var(--mfg-red-bg);
      color: var(--mfg-red-text);
    }}
    .mfg-subsection-tab.is-alert small {{
      color: var(--mfg-red-text);
      opacity: 0.82;
    }}
    .mfg-subsection-tab.is-alert.is-active {{
      border-color: var(--mfg-red-line);
      background: #ffdcdc;
      color: var(--mfg-red-text);
    }}
    .mfg-subsection-tab.is-alert.is-active small {{
      color: var(--mfg-red-text);
      opacity: 0.9;
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
    .mfg-section-tab.is-done {{
      border-color: var(--mfg-done-line);
      background: var(--mfg-done-bg);
      color: var(--mfg-done-text);
    }}
    .mfg-section-tab.is-done strong {{
      color: #ffffff;
    }}
    .mfg-section-tab.is-done small {{
      color: rgba(255, 255, 255, 0.9);
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
      min-width: 0;
      width: 100%;
    }}
    .mfg-content.is-overview {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: start;
    }}
    .mfg-content.is-overview:not(.is-split):not(.is-single-column-overview) .mfg-section-card {{
      grid-column: 1 / -1;
    }}
    .mfg-content.is-single-column-overview {{
      display: block;
      min-width: 0;
      width: 100%;
    }}
    .mfg-content.is-single-column-overview .mfg-section-card {{
      width: 100%;
      max-width: 100%;
      min-width: 0;
      display: block;
      overflow: hidden;
      margin-bottom: 8px;
    }}
    .mfg-content.is-single-column-overview .mfg-section-card.is-pantolo {{
      overflow: visible;
    }}
    .mfg-content.is-single-column-overview .mfg-row-list {{
      display: block;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head {{
      grid-template-columns: 1.08fr 0.74fr 0.82fr 0.5fr 2.06fr;
    }}
    .mfg-content.is-single-column-overview .mfg-row {{
      grid-template-columns: 1.08fr 0.74fr 0.82fr 0.5fr 2.06fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head > :nth-child(4),
    .mfg-content.is-single-column-overview .mfg-row > :nth-child(4) {{
      display: none;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-lower,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-lower {{
      grid-template-columns: 1.1fr 0.72fr 0.78fr 0.78fr 0.92fr 0.5fr 0.48fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-upper,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-upper {{
      grid-template-columns: 1.08fr 0.72fr 0.76fr 0.92fr 0.78fr 0.5fr 0.48fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-fiokelo,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-fiokelo {{
      grid-template-columns: 0.8fr 0.98fr 0.9fr 1.12fr 0.62fr 0.64fr 0.46fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-lower.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-lower.is-with-partial {{
      grid-template-columns: 1.02fr 0.72fr 0.78fr 0.72fr 0.86fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-upper.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-upper.is-with-partial {{
      grid-template-columns: 1fr 0.72fr 0.76fr 0.86fr 0.76fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-fiokelo.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-fiokelo.is-with-partial {{
      grid-template-columns: 0.76fr 0.92fr 0.86fr 1.02fr 0.56fr 0.58fr 0.42fr 0.34fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard {{
      grid-template-columns: 0.96fr 0.78fr 0.72fr 0.84fr 0.38fr 2.02fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-with-expander,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-with-expander {{
      grid-template-columns: 0.92fr 0.74fr 0.68fr 0.8fr 0.36fr 1.86fr 0.46fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-no-barcode,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-no-barcode {{
      grid-template-columns: 1fr 0.8fr 0.74fr 0.88fr 0.44fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-no-barcode.is-with-expander {{
      grid-template-columns: 0.96fr 0.76fr 0.7fr 0.82fr 0.4fr 0.46fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-with-partial {{
      grid-template-columns: 0.92fr 0.72fr 0.68fr 0.8fr 0.3fr 0.16fr 2.02fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-with-expander.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-with-expander.is-with-partial {{
      grid-template-columns: 0.88fr 0.68fr 0.64fr 0.76fr 0.28fr 0.16fr 1.86fr 0.44fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-no-barcode.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-no-barcode.is-with-partial {{
      grid-template-columns: 0.98fr 0.78fr 0.72fr 0.86fr 0.34fr 0.18fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard.is-no-barcode.is-with-expander.is-with-partial {{
      grid-template-columns: 0.94fr 0.74fr 0.68fr 0.8fr 0.32fr 0.18fr 0.44fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-topfloor,
    .mfg-content.is-single-column-overview .mfg-row.is-topfloor {{
      grid-template-columns: minmax(0, 1fr) 0.18fr minmax(180px, 0.42fr);
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-lower > :nth-child(4),
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-upper > :nth-child(4),
    .mfg-content.is-single-column-overview .mfg-table-head.is-cnc-fiokelo > :nth-child(4) {{
      display: inline-flex;
    }}
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-lower > :nth-child(4),
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-upper > :nth-child(4),
    .mfg-content.is-single-column-overview .mfg-row.is-cnc-fiokelo > :nth-child(4) {{
      display: grid;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-front-standard > * {{
      display: inline-flex;
    }}
    .mfg-content.is-single-column-overview .mfg-row.is-front-standard > * {{
      display: grid;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo,
    .mfg-content.is-single-column-overview .mfg-row.is-pantolo {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.36fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo.is-with-expander,
    .mfg-content.is-single-column-overview .mfg-row.is-pantolo.is-with-expander {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.46fr 0.46fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-pantolo.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.34fr 0.32fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo.is-with-expander.is-with-partial,
    .mfg-content.is-single-column-overview .mfg-row.is-pantolo.is-with-expander.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.42fr 0.32fr 0.44fr;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo > * {{
      display: inline-flex;
    }}
    .mfg-content.is-single-column-overview .mfg-row.is-pantolo > * {{
      display: grid;
    }}
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo > :nth-child(1),
    .mfg-content.is-single-column-overview .mfg-table-head.is-pantolo > :nth-child(4),
    .mfg-table-head.is-pantolo > :nth-child(1),
    .mfg-table-head.is-pantolo > :nth-child(4) {{
      display: none !important;
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
    .mfg-section-card.is-topfloor-boxed {{
      border-color: rgba(185, 28, 28, 0.62);
      box-shadow: inset 7px 0 0 #b91c1c;
    }}
    .mfg-section-card.is-topfloor-boxed .mfg-section-head {{
      background: #fee2e2;
    }}
    .mfg-section-card.is-topfloor-open {{
      border-color: rgba(5, 150, 105, 0.62);
      box-shadow: inset 7px 0 0 #059669;
    }}
    .mfg-section-card.is-topfloor-open .mfg-section-head {{
      background: #bbf7d0;
    }}
    .mfg-section-card.is-topfloor-done {{
      border-color: rgba(4, 120, 87, 0.82);
      box-shadow: inset 8px 0 0 #047857;
    }}
    .mfg-section-card.is-topfloor-done .mfg-section-head {{
      background: linear-gradient(180deg, #12a566, #0c8d57);
      color: #f4fff8;
    }}
    .mfg-section-card.is-topfloor-done .mfg-topfloor-title,
    .mfg-section-card.is-topfloor-done .mfg-topfloor-title strong {{
      color: #f4fff8;
    }}
    .mfg-section-card.is-topfloor-done .mfg-section-count {{
      color: #ffffff;
      background: rgba(5, 46, 22, 0.42);
      border: 1px solid rgba(255, 255, 255, 0.32);
      border-radius: 999px;
      padding: 7px 10px;
      font-weight: 900;
    }}
    .mfg-table-head {{
      display: grid;
      grid-template-columns: 1fr 0.74fr 0.82fr 0.24fr 0.46fr 1.74fr;
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
    .mfg-section-card.is-pantolo .mfg-section-head {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      position: relative;
      z-index: 8;
      will-change: transform;
    }}
    .mfg-section-card.is-pantolo {{
      overflow: visible;
    }}
    .mfg-section-card.is-pantolo .mfg-section-title {{
      grid-column: 2;
      text-align: center;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-width: 0;
      max-width: 100%;
      white-space: nowrap;
      overflow: hidden;
      font-size: 1.02rem;
      font-weight: 900;
    }}
    .mfg-pantolo-category-main {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-pantolo-category-pill {{
      flex: 0 1 auto;
      min-width: 0;
      max-width: 240px;
      padding: 4px 9px;
      border-radius: 999px;
      background: #ffe4f1;
      border: 1px solid #f5a6ca;
      color: #9d174d;
      font-size: 0.94rem;
      font-weight: 900;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-section-card.is-pantolo .mfg-section-count {{
      grid-column: 3;
      justify-self: end;
    }}
    .mfg-table-head.is-no-barcode {{
      grid-template-columns: 1.14fr 0.78fr 0.8fr 0.44fr 0.56fr;
    }}
    .mfg-table-head.is-no-barcode.is-with-partial {{
      grid-template-columns: 1.1fr 0.82fr 0.92fr 0.46fr 0.58fr 0.36fr;
    }}
    .mfg-table-head.is-cnc-lower {{
      grid-template-columns: 1.1fr 0.72fr 0.78fr 0.78fr 0.92fr 0.5fr 0.48fr;
    }}
    .mfg-table-head.is-cnc-lower.is-with-partial {{
      grid-template-columns: 1.02fr 0.72fr 0.78fr 0.72fr 0.86fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-table-head.is-cnc-upper {{
      grid-template-columns: 1.08fr 0.72fr 0.76fr 0.92fr 0.78fr 0.5fr 0.48fr;
    }}
    .mfg-table-head.is-cnc-upper.is-with-partial {{
      grid-template-columns: 1fr 0.72fr 0.76fr 0.86fr 0.76fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-table-head.is-cnc-fiokelo {{
      grid-template-columns: 0.8fr 0.98fr 0.9fr 1.12fr 0.62fr 0.64fr 0.46fr;
    }}
    .mfg-table-head.is-cnc-fiokelo.is-with-partial {{
      grid-template-columns: 0.76fr 0.92fr 0.86fr 1.02fr 0.56fr 0.58fr 0.42fr 0.34fr;
    }}
    .mfg-table-head.is-pantolo {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.36fr;
    }}
    .mfg-table-head.is-pantolo.is-with-expander {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.46fr 0.46fr;
    }}
    .mfg-table-head.is-pantolo.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.34fr 0.32fr;
    }}
    .mfg-table-head.is-pantolo.is-with-expander.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.42fr 0.32fr 0.44fr;
    }}
    .mfg-table-head.is-front-standard {{
      grid-template-columns: 0.96fr 0.78fr 0.72fr 0.84fr 0.38fr 2.02fr;
    }}
    .mfg-table-head.is-front-standard.is-with-expander {{
      grid-template-columns: 0.92fr 0.74fr 0.68fr 0.8fr 0.36fr 1.86fr 0.46fr;
    }}
    .mfg-table-head.is-front-standard.is-no-barcode {{
      grid-template-columns: 1fr 0.8fr 0.74fr 0.88fr 0.44fr;
    }}
    .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander {{
      grid-template-columns: 0.96fr 0.76fr 0.7fr 0.82fr 0.4fr 0.46fr;
    }}
    .mfg-table-head.is-front-standard.is-with-partial {{
      grid-template-columns: 0.92fr 0.72fr 0.68fr 0.8fr 0.3fr 0.16fr 2.02fr;
    }}
    .mfg-table-head.is-front-standard.is-with-expander.is-with-partial {{
      grid-template-columns: 0.88fr 0.68fr 0.64fr 0.76fr 0.28fr 0.16fr 1.86fr 0.44fr;
    }}
    .mfg-table-head.is-front-standard.is-no-barcode.is-with-partial {{
      grid-template-columns: 1fr 0.82fr 0.76fr 0.88fr 0.36fr 0.34fr;
    }}
    .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander.is-with-partial {{
      grid-template-columns: 0.94fr 0.74fr 0.68fr 0.8fr 0.32fr 0.3fr 0.44fr;
    }}
    .mfg-table-head.is-topfloor,
    .mfg-row.is-topfloor {{
      grid-template-columns: minmax(0, 1fr) 0.2fr minmax(160px, 0.46fr);
    }}
    .mfg-table-head.is-topfloor.is-hettich,
    .mfg-row.is-topfloor.is-hettich {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
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
      max-height: calc(100vh - 244px);
      max-height: calc(100dvh - 244px);
      max-height: min(68vh, calc(100vh - 244px));
      max-height: min(68dvh, calc(100dvh - 244px));
      grid-template-rows: auto auto auto;
    }}
    .mfg-content.is-split .mfg-row-list {{
      max-height: calc(100vh - 338px);
      max-height: calc(100dvh - 338px);
      max-height: min(58vh, calc(100vh - 338px));
      max-height: min(58dvh, calc(100dvh - 338px));
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior: contain;
      scrollbar-width: thin;
      box-sizing: border-box;
      padding-bottom: 40px;
      scroll-padding-bottom: 40px;
    }}
    .mfg-row {{
      width: 100%;
      min-height: 50px;
      padding: 7px 10px;
      border-radius: 0;
      border: 0;
      border-top: 1px solid rgba(17, 24, 39, 0.06);
      background: #fff;
      color: var(--mfg-text);
      text-align: left;
      display: grid;
      grid-template-columns: 1fr 0.74fr 0.82fr 0.24fr 0.46fr 1.74fr;
      gap: 5px;
      align-items: center;
      cursor: pointer;
      transition: background 220ms ease, border-color 220ms ease;
      touch-action: pan-y manipulation;
      user-select: none;
      -webkit-user-select: none;
      -webkit-touch-callout: none;
    }}
    .mfg-row:disabled {{
      cursor: default;
      opacity: 1;
    }}
    .mfg-row.is-no-barcode {{
      grid-template-columns: 1.14fr 0.78fr 0.8fr 0.44fr 0.56fr;
    }}
    .mfg-row.is-no-barcode.is-with-partial {{
      grid-template-columns: 1.1fr 0.82fr 0.92fr 0.46fr 0.58fr 0.36fr;
    }}
    .mfg-row.is-cnc-lower {{
      grid-template-columns: 1.08fr 0.72fr 0.78fr 0.78fr 0.9fr 0.48fr 0.4fr 0.46fr;
    }}
    .mfg-row.is-cnc-lower.is-with-partial {{
      grid-template-columns: 1.02fr 0.72fr 0.78fr 0.72fr 0.86fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-row.is-cnc-upper {{
      grid-template-columns: 1.06fr 0.72fr 0.76fr 0.92fr 0.78fr 0.48fr 0.4fr 0.46fr;
    }}
    .mfg-row.is-cnc-upper.is-with-partial {{
      grid-template-columns: 1fr 0.72fr 0.76fr 0.86fr 0.76fr 0.44fr 0.44fr 0.34fr;
    }}
    .mfg-row.is-cnc-fiokelo {{
      grid-template-columns: 0.8fr 0.96fr 0.9fr 1.08fr 0.58fr 0.62fr 0.38fr 0.44fr;
    }}
    .mfg-row.is-cnc-fiokelo.is-with-partial {{
      grid-template-columns: 0.76fr 0.92fr 0.86fr 1.02fr 0.56fr 0.58fr 0.42fr 0.34fr;
    }}
    .mfg-row.is-pantolo {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.36fr;
    }}
    .mfg-row.is-pantolo.is-with-expander {{
      grid-template-columns: 0.72fr 0.8fr 0.82fr 0.7fr 1.04fr 0.72fr 0.66fr 0.46fr 0.46fr;
    }}
    .mfg-row.is-pantolo.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.34fr 0.32fr;
    }}
    .mfg-row.is-pantolo.is-with-expander.is-with-partial {{
      grid-template-columns: 0.7fr 0.76fr 0.8fr 0.66fr 0.98fr 0.68fr 0.62fr 0.42fr 0.32fr 0.44fr;
    }}
    .mfg-row.is-cnc-fiokelo .mfg-row-meta {{
      padding-top: 2px;
      padding-bottom: 2px;
    }}
    .mfg-row.is-cnc-fiokelo .mfg-row-meta:first-child span {{
      font-weight: 900;
      font-size: 0.92rem;
      letter-spacing: 0.01em;
      color: #0f172a;
    }}
    .mfg-row.is-cnc-fiokelo .mfg-row-meta:nth-child(2) span {{
      font-weight: 900;
      font-size: 0.92rem;
      color: #111827;
    }}
    .mfg-row.is-cnc-fiokelo .mfg-row-meta:nth-child(3) span {{
      font-size: 0.88rem;
      font-weight: 900;
    }}
    .mfg-row.is-front-standard {{
      grid-template-columns: 0.96fr 0.78fr 0.72fr 0.84fr 0.38fr 2.02fr;
    }}
    .mfg-row.is-front-standard.is-with-expander {{
      grid-template-columns: 0.92fr 0.74fr 0.68fr 0.8fr 0.36fr 1.86fr 0.46fr;
    }}
    .mfg-row.is-front-standard.is-no-barcode {{
      grid-template-columns: 1fr 0.8fr 0.74fr 0.88fr 0.44fr;
    }}
    .mfg-row.is-front-standard.is-no-barcode.is-with-expander {{
      grid-template-columns: 0.96fr 0.76fr 0.7fr 0.82fr 0.4fr 0.46fr;
    }}
    .mfg-row.is-front-standard.is-with-partial {{
      grid-template-columns: 0.92fr 0.72fr 0.68fr 0.8fr 0.3fr 0.16fr 2.02fr;
    }}
    .mfg-row.is-front-standard.is-with-expander.is-with-partial {{
      grid-template-columns: 0.88fr 0.68fr 0.64fr 0.76fr 0.28fr 0.16fr 1.86fr 0.44fr;
    }}
    .mfg-row.is-front-standard.is-no-barcode.is-with-partial {{
      grid-template-columns: 1fr 0.82fr 0.76fr 0.88fr 0.36fr 0.34fr;
    }}
    .mfg-row.is-front-standard.is-no-barcode.is-with-expander.is-with-partial {{
      grid-template-columns: 0.94fr 0.74fr 0.68fr 0.8fr 0.32fr 0.3fr 0.44fr;
    }}
    .mfg-table-head.is-front-standard > *,
    .mfg-row.is-front-standard > * {{
      min-width: 0;
    }}
    .mfg-row > * {{
      min-width: 0;
    }}
    .mfg-row.is-front-standard .mfg-row-main {{
      min-width: 0;
      padding-right: 8px;
    }}
    .mfg-row.is-front-standard .mfg-row-main .mfg-row-title {{
      line-height: 1.2;
    }}
    .mfg-row.is-front-standard .mfg-row-meta.is-model {{
      font-weight: 700;
      color: #111827;
    }}
    .mfg-row.is-front-standard .mfg-row-meta.is-model.is-laura-model span {{
      font-style: italic;
    }}
    .mfg-row.is-green {{
      background: var(--mfg-green-bg);
      box-shadow: inset 3px 0 0 var(--mfg-green-line);
    }}
    .mfg-row.is-red {{
      background: var(--mfg-red-bg);
      box-shadow: inset 3px 0 0 var(--mfg-red-line);
    }}
    .mfg-row.is-issued-edited {{
      position: relative;
      z-index: 1;
      border-color: #dc2626;
      box-shadow:
        inset 0 0 0 2px #dc2626,
        0 0 12px rgba(220, 38, 38, 0.62) !important;
    }}
    .mfg-row.is-done {{
      color: #f4fff8;
    }}
    .mfg-row.is-muted {{
      background: #f3f4f6;
    }}
    .mfg-row.is-model-blue {{
      background: #eef4ff;
    }}
    .mfg-row.is-model-violet {{
      background: #f4efff;
    }}
    .mfg-row.is-model-amber {{
      background: #fff6e8;
    }}
    .mfg-row.is-model-cyan {{
      background: #eefafc;
    }}
    .mfg-row.is-model-slate {{
      background: #f3f6f8;
    }}
    .mfg-row.is-model-orange {{
      background: #fff1ea;
    }}
    .mfg-row.is-model-rose {{
      background: #ffe6ee;
    }}
    .mfg-row.is-model-lime {{
      background: #eef8d8;
    }}
    .mfg-row.is-model-teal {{
      background: #ddf6ee;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-blue {{
      background: #dbe8ff;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-violet {{
      background: #ede4ff;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-amber {{
      background: #fef0cb;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-cyan {{
      background: #dcf6fb;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-slate {{
      background: #e9eef3;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-orange {{
      background: #ffe4d6;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-rose {{
      background: #ffdbe7;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-lime {{
      background: #e4f4bf;
    }}
    .mfg-row.is-cnc-fiokelo.is-model-teal {{
      background: #cff1e6;
    }}
    .mfg-row.is-cnc-fiokelo.is-green {{
      background: #c9f0d8;
      box-shadow: inset 5px 0 0 var(--mfg-green-line);
    }}
    .mfg-row.is-cnc-fiokelo.is-red {{
      background: #ffd4d4;
      box-shadow: inset 5px 0 0 var(--mfg-red-line);
    }}
    .mfg-row.is-glass {{
      background: #eef6ff;
      box-shadow: inset 3px 0 0 #2563eb;
    }}
    .mfg-row.is-pullout {{
      background: #fff7ed;
      box-shadow: inset 3px 0 0 #f97316;
    }}
    .mfg-row.is-green {{
      background: #c9f0d8;
      box-shadow: inset 5px 0 0 var(--mfg-green-line);
    }}
    .mfg-row.is-red {{
      background: #ffd4d4;
      box-shadow: inset 5px 0 0 var(--mfg-red-line);
    }}
    .mfg-row.is-mixed {{
      background: #fce7f3;
      box-shadow: inset 5px 0 0 #d946ef;
    }}
    .mfg-row.is-green .mfg-row-meta span,
    .mfg-row.is-green .mfg-row-code {{
      color: var(--mfg-green-text);
    }}
    .mfg-row.is-red .mfg-row-meta span,
    .mfg-row.is-red .mfg-row-code {{
      color: var(--mfg-red-text);
    }}
    .mfg-row.is-mixed .mfg-row-meta span {{
      color: #86198f;
    }}
    .mfg-row.is-done {{
      background: linear-gradient(180deg, #12a566, #0c8d57);
      box-shadow: inset 5px 0 0 #0a7448;
    }}
    .mfg-row.is-glass.is-done,
    .mfg-row.is-pullout.is-done,
    .mfg-row[class*="is-model-"].is-done {{
      background: linear-gradient(180deg, #12a566, #0c8d57);
      box-shadow: inset 5px 0 0 #0a7448;
    }}
    .mfg-row.is-done .mfg-row-title,
    .mfg-row.is-done .mfg-row-meta span,
    .mfg-row.is-done .mfg-row-code {{
      color: #f4fff8;
    }}
    .mfg-row.is-done .mfg-row-subtitle {{
      color: #dcfce7;
      font-weight: 750;
      opacity: 1;
      text-shadow: 0 1px 1px rgba(4, 78, 50, 0.55);
    }}
    .mfg-row.is-done .mfg-row-qty {{
      background: #0a7448;
      color: #ffffff;
    }}
    .mfg-row-main {{
      display: grid;
      gap: 1px;
      min-width: 0;
      align-content: center;
    }}
    .mfg-row-title {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      font-size: 0.78rem;
      font-weight: 800;
      line-height: 1.1;
    }}
    .mfg-row-badge {{
      display: inline-flex;
      align-items: center;
      min-height: 18px;
      padding: 0 6px;
      border-radius: 999px;
      font-size: 0.62rem;
      font-weight: 800;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .mfg-edited-marker {{
      display: inline-block;
      margin-left: 4px;
      color: #b45309;
      font-size: 0.78em;
      line-height: 1;
      vertical-align: 0.08em;
    }}
    .mfg-row-badge.is-glass {{
      background: #dbeafe;
      color: #1d4ed8;
      border: 1px solid rgba(37, 99, 235, 0.16);
    }}
    .mfg-row-badge.is-pullout {{
      background: #ffedd5;
      color: #c2410c;
      border: 1px solid rgba(194, 65, 12, 0.16);
    }}
    .mfg-row-badge.is-curved {{
      background: #f3e8ff;
      color: #7c3aed;
      border: 1px solid rgba(124, 58, 237, 0.18);
    }}
    .mfg-row-badge.is-model-blue {{
      background: #dbe8ff;
      color: #1d4ed8;
      border: 1px solid rgba(37, 99, 235, 0.14);
    }}
    .mfg-row-badge.is-model-violet {{
      background: #ebe2ff;
      color: #6d28d9;
      border: 1px solid rgba(109, 40, 217, 0.14);
    }}
    .mfg-row-badge.is-model-amber {{
      background: #fdecc8;
      color: #b45309;
      border: 1px solid rgba(180, 83, 9, 0.14);
    }}
    .mfg-row-badge.is-model-cyan {{
      background: #d9f4f8;
      color: #0f766e;
      border: 1px solid rgba(15, 118, 110, 0.14);
    }}
    .mfg-row-badge.is-model-slate {{
      background: #e6edf2;
      color: #475569;
      border: 1px solid rgba(71, 85, 105, 0.14);
    }}
    .mfg-row-badge.is-model-orange {{
      background: #fee2d5;
      color: #c2410c;
      border: 1px solid rgba(194, 65, 12, 0.14);
    }}
    .mfg-row-badge.is-model-rose {{
      background: #ffdce7;
      color: #be185d;
      border: 1px solid rgba(190, 24, 93, 0.14);
    }}
    .mfg-row-badge.is-model-lime {{
      background: #e8f3c9;
      color: #4d7c0f;
      border: 1px solid rgba(77, 124, 15, 0.14);
    }}
    .mfg-row-badge.is-model-teal {{
      background: #d4f1e8;
      color: #0f766e;
      border: 1px solid rgba(15, 118, 110, 0.14);
    }}
    .mfg-row-meta span.is-pill-black {{
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      background: #0f172a;
      color: #fff;
      font-weight: 900;
      justify-content: center;
      white-space: nowrap;
      display: inline-flex;
      width: fit-content;
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-mark {{
      min-height: 28px;
      padding: 0 9px;
      border-radius: 999px;
      border: 1px solid transparent;
      color: #ffffff;
      font-weight: 900;
      justify-content: center;
      width: fit-content;
      max-width: 100%;
      white-space: normal;
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-dark-green {{
      background: #065f46;
      border-color: rgba(4, 120, 87, 0.34);
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-lime {{
      background: #84cc16;
      border-color: rgba(77, 124, 15, 0.34);
      color: #1f3708;
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-yellow {{
      background: #facc15;
      border-color: rgba(161, 98, 7, 0.3);
      color: #3f2d05;
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-orange {{
      background: #f97316;
      border-color: rgba(194, 65, 12, 0.32);
      color: #ffffff;
    }}
    .mfg-row.is-pantolo .mfg-row-meta span.is-pantolo-pink {{
      background: #ec4899;
      border-color: rgba(190, 24, 93, 0.3);
      color: #ffffff;
    }}
    .mfg-row.is-pantolo-unit {{
      background: #fbfcfe;
      box-shadow: inset 5px 0 0 #cbd5e1;
    }}
    .mfg-row.is-pantolo-unit.is-green {{
      background: #dcf7e6;
    }}
    .mfg-row.is-pantolo-unit.is-red {{
      background: #ffe0e0;
    }}
    .mfg-row.is-pantolo-group.is-expanded,
    .mfg-row.is-pantolo-unit {{
      border-left: 4px solid #0f172a;
      border-right: 4px solid #0f172a;
    }}
    .mfg-row.is-pantolo-group.is-expanded {{
      border-top: 4px solid #0f172a;
    }}
    .mfg-row.is-pantolo-unit.is-last-unit {{
      border-bottom: 4px solid #0f172a;
    }}
    .mfg-row.is-pantolo-unit.is-opening {{
      overflow: hidden;
      animation: mfg-pantolo-child-open 180ms cubic-bezier(0.22, 1, 0.36, 1) both;
    }}
    .mfg-row.is-pantolo-unit.is-collapsing {{
      overflow: hidden;
      pointer-events: none;
      animation: mfg-pantolo-child-close 160ms cubic-bezier(0.4, 0, 1, 1) both;
    }}
    @keyframes mfg-pantolo-child-open {{
      from {{
        min-height: 0;
        max-height: 0;
        padding-top: 0;
        padding-bottom: 0;
        opacity: 0;
        transform: translateY(-8px);
      }}
      to {{
        min-height: 50px;
        max-height: 72px;
        padding-top: 7px;
        padding-bottom: 7px;
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    @keyframes mfg-pantolo-child-close {{
      from {{
        min-height: 50px;
        max-height: 72px;
        padding-top: 7px;
        padding-bottom: 7px;
        opacity: 1;
        transform: translateY(0);
      }}
      to {{
        min-height: 0;
        max-height: 0;
        padding-top: 0;
        padding-bottom: 0;
        opacity: 0;
        transform: translateY(-8px);
      }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .mfg-row.is-pantolo-unit.is-opening,
      .mfg-row.is-pantolo-unit.is-collapsing {{
        animation: none;
      }}
    }}
    .mfg-pantolo-expand-cell {{
      display: grid;
      align-items: center;
      justify-items: center;
      min-width: 0;
    }}
    .mfg-pantolo-expand {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 42px;
      min-width: 42px;
      height: 38px;
      border-radius: 12px;
      border: 1px solid rgba(17, 24, 39, 0.16);
      background: #0f172a;
      color: #ffffff;
      font-size: 1rem;
      font-weight: 900;
      line-height: 1;
      cursor: pointer;
      touch-action: manipulation;
      user-select: none;
    }}
    .mfg-pantolo-expand.is-empty {{
      pointer-events: none;
      opacity: 0;
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
      overflow: hidden;
      text-overflow: ellipsis;
      word-break: normal;
      overflow-wrap: normal;
      line-height: 1;
      font-size: 0.8rem;
      align-self: center;
      transform: translateY(2px);
    }}
    .mfg-row-meta span.is-color {{
      white-space: nowrap;
      line-height: 1.05;
      padding-left: 8px;
      font-size: 0.8rem;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-row-code {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mfg-row:not(.is-front-standard):not(.is-cnc-fiokelo) .mfg-row-meta {{
      overflow: hidden;
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
      white-space: nowrap;
    }}
    .mfg-row.is-green .mfg-row-qty {{
      background: var(--mfg-green-text);
    }}
    .mfg-row.is-red .mfg-row-qty {{
      background: var(--mfg-red-text);
    }}
    .mfg-row-partial {{
      display: flex;
      align-items: center;
      min-width: 0;
    }}
    .mfg-row-partial-input {{
      width: 100%;
      min-width: 36px;
      max-width: 42px;
      height: 32px;
      border-radius: 9px;
      border: 1px solid rgba(17, 24, 39, 0.16);
      background: rgba(255, 255, 255, 0.92);
      color: #111827;
      font: inherit;
      font-weight: 700;
      padding: 0 6px;
      outline: none;
    }}
    .mfg-row-partial-input:focus {{
      border-color: #111827;
      box-shadow: 0 0 0 3px rgba(17, 24, 39, 0.08);
    }}
    .mfg-row-partial-empty {{
      display: block;
      width: 100%;
      min-height: 34px;
    }}
    .mfg-choice-modal[hidden] {{
      display: none !important;
    }}
    .mfg-choice-modal {{
      position: fixed;
      inset: 0;
      z-index: 90;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(15, 23, 42, 0.32);
    }}
    .mfg-choice-card {{
      width: min(360px, 100%);
      border-radius: 20px;
      background: #fff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
      padding: 20px;
      display: grid;
      gap: 14px;
    }}
    .mfg-choice-title {{
      font-size: 1rem;
      font-weight: 800;
      color: #111827;
    }}
    .mfg-choice-copy {{
      font-size: 0.92rem;
      color: #475569;
      line-height: 1.45;
    }}
    .mfg-choice-actions {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(98px, 1fr));
      gap: 10px;
    }}
    .mfg-choice-button[hidden] {{
      display: none !important;
    }}
    .mfg-choice-button {{
      min-height: 42px;
      border-radius: 12px;
      border: 1px solid rgba(17, 24, 39, 0.14);
      background: #fff;
      color: #111827;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }}
    .mfg-choice-button.is-green {{
      background: #dff8e6;
      border-color: rgba(18, 106, 52, 0.22);
    }}
    .mfg-choice-button.is-red {{
      background: #ffe2e2;
      border-color: rgba(185, 48, 48, 0.24);
      color: #9f2424;
    }}
    .mfg-choice-button.is-plain {{
      background: #f8fafc;
    }}
    .mfg-confirm-modal[hidden] {{
      display: none !important;
    }}
    .mfg-confirm-modal {{
      position: fixed;
      inset: 0;
      z-index: 92;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(15, 23, 42, 0.38);
      backdrop-filter: blur(2px);
    }}
    .mfg-confirm-card {{
      width: min(430px, 100%);
      border-radius: 18px;
      background: #ffffff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      box-shadow: 0 28px 88px rgba(15, 23, 42, 0.2);
      padding: 20px;
      display: grid;
      gap: 14px;
    }}
    .mfg-confirm-title {{
      margin: 0;
      font-size: 1.02rem;
      font-weight: 800;
      color: #0f172a;
    }}
    .mfg-confirm-copy {{
      margin: 0;
      font-size: 0.9rem;
      color: #475569;
      line-height: 1.45;
      white-space: pre-line;
    }}
    .mfg-confirm-actions {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .mfg-confirm-actions.is-single {{
      grid-template-columns: 1fr;
    }}
    .mfg-confirm-actions.is-creator {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .mfg-confirm-button {{
      min-height: 42px;
      border-radius: 12px;
      border: 1px solid rgba(17, 24, 39, 0.14);
      background: #fff;
      color: #111827;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }}
    .mfg-confirm-button.is-confirm {{
      border-color: rgba(11, 108, 68, 0.48);
      background: linear-gradient(180deg, #12a566, #0c8d57);
      color: #fff;
    }}
    .mfg-confirm-button.is-cancel {{
      background: #f8fafc;
    }}
    .mfg-row-barcode-wrap {{
      display: grid;
      gap: 2px;
      align-content: center;
      min-width: 0;
      overflow: hidden;
      justify-self: stretch;
      align-self: center;
      width: 100%;
      max-width: 100%;
    }}
    .mfg-row:not(.is-front-standard):not(.is-cnc-lower):not(.is-cnc-upper):not(.is-cnc-fiokelo) .mfg-row-barcode-wrap {{
      justify-self: end;
      width: min(100%, 216px);
      max-width: 216px;
    }}
    .mfg-row.is-topfloor.is-hettich .mfg-row-barcode-wrap {{
      justify-self: stretch;
      width: 100%;
      max-width: none;
    }}
    .mfg-row.is-topfloor.is-hettich .mfg-row-side {{
      justify-items: center;
    }}
    .mfg-row.is-topfloor.is-hettich .mfg-row-qty {{
      min-width: 44px;
      width: auto;
    }}
    .mfg-row-barcode {{
      min-height: 34px;
      padding: 3px 10px;
      border-radius: 8px;
      background: #fff;
      border: 1px solid rgba(17, 24, 39, 0.08);
      display: grid;
      place-items: center;
      overflow: hidden;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
    }}
    .mfg-row-barcode svg {{
      width: 100%;
      height: 28px;
      display: block;
    }}
    .mfg-row-code {{
      width: 100%;
      display: block;
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
      body.has-mfg-scroll-rail .mfg-page {{
        padding-right: 56px;
      }}
      body.has-mfg-scroll-rail .mfg-toolbar,
      body.has-mfg-scroll-rail .mfg-board,
      body.has-mfg-scroll-rail .mfg-notice,
      body.has-mfg-scroll-rail .mfg-operation-panel,
      body.has-mfg-scroll-rail .mfg-operation-header {{
        width: min(1280px, calc(100vw - 72px));
      }}
      .mfg-scroll-rail {{
        width: 48px;
      }}
      .mfg-content.is-overview {{
        grid-template-columns: minmax(0, 1fr);
      }}
      .mfg-table-head,
      .mfg-row {{
        grid-template-columns: 0.96fr 0.7fr 0.78fr 0.22fr 0.42fr 1.6fr;
      }}
      .mfg-table-head.is-no-barcode,
      .mfg-row.is-no-barcode {{
        grid-template-columns: 1.02fr 0.7fr 0.72fr 0.42fr 0.54fr;
      }}
      .mfg-table-head.is-no-barcode.is-with-partial,
      .mfg-row.is-no-barcode.is-with-partial {{
        grid-template-columns: 1fr 0.7fr 0.74fr 0.38fr 0.48fr 0.32fr;
      }}
      .mfg-table-head.is-cnc-lower,
      .mfg-row.is-cnc-lower {{
        grid-template-columns: 1.04fr 0.7fr 0.72fr 0.74fr 0.86fr 0.48fr 0.46fr;
      }}
      .mfg-table-head.is-cnc-lower.is-with-partial,
      .mfg-row.is-cnc-lower.is-with-partial {{
        grid-template-columns: 0.98fr 0.66fr 0.7fr 0.68fr 0.8fr 0.42fr 0.4fr 0.3fr;
      }}
      .mfg-table-head.is-cnc-upper,
      .mfg-row.is-cnc-upper {{
        grid-template-columns: 1.02fr 0.7fr 0.72fr 0.86fr 0.76fr 0.48fr 0.46fr;
      }}
      .mfg-table-head.is-cnc-upper.is-with-partial,
      .mfg-row.is-cnc-upper.is-with-partial {{
        grid-template-columns: 0.96fr 0.66fr 0.68fr 0.8fr 0.72fr 0.42fr 0.4fr 0.3fr;
      }}
      .mfg-table-head.is-pantolo,
      .mfg-row.is-pantolo {{
        grid-template-columns: 0.64fr 0.72fr 0.76fr 0.62fr 0.9fr 0.64fr 0.58fr 0.34fr;
      }}
      .mfg-table-head.is-pantolo.is-with-expander,
      .mfg-row.is-pantolo.is-with-expander {{
        grid-template-columns: 0.64fr 0.72fr 0.76fr 0.62fr 0.9fr 0.64fr 0.58fr 0.42fr 0.42fr;
      }}
      .mfg-table-head.is-pantolo.is-with-partial,
      .mfg-row.is-pantolo.is-with-partial {{
        grid-template-columns: 0.62fr 0.7fr 0.72fr 0.58fr 0.84fr 0.6fr 0.54fr 0.32fr 0.28fr;
      }}
      .mfg-table-head.is-pantolo.is-with-expander.is-with-partial,
      .mfg-row.is-pantolo.is-with-expander.is-with-partial {{
        grid-template-columns: 0.62fr 0.7fr 0.72fr 0.58fr 0.84fr 0.6fr 0.54fr 0.38fr 0.28fr 0.38fr;
      }}
      .mfg-table-head,
      .mfg-row {{
        grid-template-columns: 0.94fr 0.66fr 0.74fr 0.22fr 0.4fr 1.52fr;
      }}
      .mfg-table-head.is-front-standard,
      .mfg-row.is-front-standard {{
        grid-template-columns: 0.92fr 0.78fr 0.68fr 0.82fr 0.44fr 1.48fr;
      }}
      .mfg-table-head.is-front-standard.is-with-expander,
      .mfg-row.is-front-standard.is-with-expander {{
        grid-template-columns: 0.88fr 0.72fr 0.64fr 0.78fr 0.4fr 1.34fr 0.42fr;
      }}
      .mfg-table-head.is-front-standard.is-no-barcode,
      .mfg-row.is-front-standard.is-no-barcode {{
        grid-template-columns: 0.96fr 0.78fr 0.7fr 0.84fr 0.42fr;
      }}
      .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander,
      .mfg-row.is-front-standard.is-no-barcode.is-with-expander {{
        grid-template-columns: 0.92fr 0.72fr 0.66fr 0.8fr 0.38fr 0.42fr;
      }}
      .mfg-table-head.is-front-standard.is-with-partial,
      .mfg-row.is-front-standard.is-with-partial {{
        grid-template-columns: 0.86fr 0.72fr 0.64fr 0.78fr 0.34fr 0.3fr 1.4fr;
      }}
      .mfg-table-head.is-front-standard.is-with-expander.is-with-partial,
      .mfg-row.is-front-standard.is-with-expander.is-with-partial {{
        grid-template-columns: 0.82fr 0.68fr 0.6fr 0.72fr 0.32fr 0.28fr 1.24fr 0.38fr;
      }}
      .mfg-table-head.is-front-standard.is-no-barcode.is-with-partial,
      .mfg-row.is-front-standard.is-no-barcode.is-with-partial {{
        grid-template-columns: 0.94fr 0.72fr 0.68fr 0.82fr 0.34fr 0.3fr;
      }}
      .mfg-table-head.is-front-standard.is-no-barcode.is-with-expander.is-with-partial,
      .mfg-row.is-front-standard.is-no-barcode.is-with-expander.is-with-partial {{
        grid-template-columns: 0.9fr 0.68fr 0.64fr 0.76fr 0.32fr 0.28fr 0.38fr;
      }}
    }}
    @media (orientation: portrait) {{
      .mfg-content.is-overview.is-split {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .mfg-content.is-split .mfg-table-head {{
        font-size: 0.58rem;
        gap: 4px;
        padding: 0 8px;
      }}
      .mfg-content.is-split .mfg-table-head [data-sort-key="color"] {{
        padding-left: 10px;
      }}
      .mfg-content.is-split .mfg-row {{
        min-height: 52px;
        padding: 7px 8px;
        gap: 4px;
      }}
      .mfg-content.is-split .mfg-row-title {{
        font-size: 0.72rem;
      }}
      .mfg-content.is-split .mfg-row-meta span {{
        font-size: 0.76rem;
        min-height: 26px;
      }}
      .mfg-content.is-split .mfg-row-meta span.is-size {{
        font-size: 0.72rem;
        transform: translateY(1px);
      }}
      .mfg-content.is-split .mfg-row-meta span.is-color {{
        padding-left: 10px;
        line-height: 1.08;
      }}
      .mfg-content.is-split .mfg-row-qty {{
        min-height: 26px;
        padding: 0 6px;
        font-size: 0.76rem;
      }}
      .mfg-content.is-split .mfg-row-barcode {{
        min-height: 34px;
        padding: 3px 8px;
      }}
      .mfg-content.is-split .mfg-row-barcode svg {{
        height: 26px;
      }}
      .mfg-content.is-split .mfg-row-code {{
        font-size: 0.58rem;
        min-height: 14px;
      }}
    }}
  </style>
</head>
<body>
  <div class="mfg-page">
    {notice_markup}

    {toolbar_markup}

    {operation_panel_html if active_document is None else operation_header_html}

    <section class="{board_class}">

      <div class="mfg-tab-row" id="mfg-doc-tabs" style="display:none"></div>
      <div class="mfg-section-tab-row" id="mfg-section-tabs"></div>
      <div class="mfg-subsection-tab-row" id="mfg-subsection-tabs" style="display:none"></div>
      <div class="mfg-search-row" id="mfg-search-row" hidden>
        <input class="mfg-search-input" id="mfg-search-input" type="search" autocomplete="off" spellcheck="false" placeholder="Kereses..." />
      </div>
      <div class="mfg-status-row">
        <div class="mfg-status" id="mfg-status">Érintés: zöld, majd piros, majd üres.</div>
        <div class="mfg-status-actions">
          <button class="mfg-report-button" id="mfg-report-ready" type="button">Készre jelentek</button>
          <button class="mfg-issued-toggle" id="mfg-issued-toggle" type="button" aria-pressed="false">Kiadottak mutatása</button>
          <div class="mfg-layout-toggle" id="mfg-layout-toggle" aria-label="Nézet mód">
            <button class="mfg-layout-button is-active" type="button" data-layout-mode="single" title="Egy kategória">▣</button>
            <button class="mfg-layout-button" type="button" data-layout-mode="double" title="Két kategória">▥</button>
          </div>
        </div>
      </div>
      <div class="mfg-issued-edit-warning" id="mfg-issued-edit-warning" role="alert" hidden></div>
      <div class="mfg-content" id="mfg-content"></div>
      <div class="mfg-scroll-rail" id="mfg-scroll-rail" aria-hidden="true"></div>
    </section>
    <div class="mfg-choice-modal" id="mfg-choice-modal" hidden>
      <div class="mfg-choice-card" role="dialog" aria-modal="true" aria-labelledby="mfg-choice-title">
        <div class="mfg-choice-title" id="mfg-choice-title">Piros tétel áthelyezése</div>
        <div class="mfg-choice-copy">Hova kerüljön a kijelölt piros tétel?</div>
        <div class="mfg-choice-actions">
          <button class="mfg-choice-button is-plain" type="button" data-choice-action="plain">Sima</button>
          <button class="mfg-choice-button is-green" type="button" data-choice-action="green">Zöld</button>
          <button class="mfg-choice-button is-red" type="button" data-choice-action="red" hidden>Piros</button>
        </div>
      </div>
    </div>
    <div class="mfg-confirm-modal" id="mfg-creator-modal" hidden>
      <div class="mfg-confirm-card" role="dialog" aria-modal="true" aria-labelledby="mfg-creator-title">
        <h3 class="mfg-confirm-title" id="mfg-creator-title">Ki hozta létre a dobozt?</h3>
        <p class="mfg-confirm-copy">Válaszd ki a doboz létrehozóját.</p>
        <div class="mfg-confirm-actions is-creator">
          <button class="mfg-confirm-button" type="button" data-creator-action="Andi">Andi</button>
          <button class="mfg-confirm-button" type="button" data-creator-action="Ági">Ági</button>
          <button class="mfg-confirm-button" type="button" data-creator-action="Niki">Niki</button>
        </div>
      </div>
    </div>
    <div class="mfg-confirm-modal" id="mfg-confirm-modal" hidden>
      <div class="mfg-confirm-card" role="dialog" aria-modal="true" aria-labelledby="mfg-confirm-title">
        <h3 class="mfg-confirm-title" id="mfg-confirm-title">Biztosan készre jelented a zöld tételeket?</h3>
        <p class="mfg-confirm-copy">A sikeresen készre jelentett sorok sötétzöldre váltanak és többé nem módosíthatók.</p>
        <div class="mfg-confirm-actions">
          <button class="mfg-confirm-button is-cancel" type="button" data-confirm-action="cancel">Mégse</button>
          <button class="mfg-confirm-button is-confirm" type="button" data-confirm-action="confirm">Igen, készre</button>
        </div>
      </div>
    </div>

    <script type="application/json" id="manufacturing-data">{payload_json}</script>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script>
  </div>

  <script>
    (() => {{
      const dataNode = document.getElementById("manufacturing-data");
      const chipRowNode = document.getElementById("mfg-chip-row");
      const cacheRefreshButtonNode = document.getElementById("mfg-cache-refresh");
      const productionLookupNode = document.getElementById("mfg-production-lookup");
      const productionNumberInputNode = document.getElementById("mfg-production-number");
      const docTabsNode = document.getElementById("mfg-doc-tabs");
      const sectionTabsNode = document.getElementById("mfg-section-tabs");
      const subsectionTabsNode = document.getElementById("mfg-subsection-tabs");
      const searchRowNode = document.getElementById("mfg-search-row");
      const searchInputNode = document.getElementById("mfg-search-input");
      const contentNode = document.getElementById("mfg-content");
      const scrollRailNode = document.getElementById("mfg-scroll-rail");
      const statusNode = document.getElementById("mfg-status");
      const issuedEditWarningNode = document.getElementById("mfg-issued-edit-warning");
      const operationTitleNode = document.getElementById("mfg-operation-title");
      const operationSourceNode = document.getElementById("mfg-operation-source");
      const reportReadyButtonNode = document.getElementById("mfg-report-ready");
      const issuedToggleNode = document.getElementById("mfg-issued-toggle");
      const layoutToggleNode = document.getElementById("mfg-layout-toggle");
      const choiceModalNode = document.getElementById("mfg-choice-modal");
      const creatorModalNode = document.getElementById("mfg-creator-modal");
      const confirmModalNode = document.getElementById("mfg-confirm-modal");
      if (!dataNode || !docTabsNode || !sectionTabsNode || !subsectionTabsNode || !searchRowNode || !searchInputNode || !contentNode || !scrollRailNode || !statusNode || !issuedEditWarningNode || !reportReadyButtonNode || !issuedToggleNode || !layoutToggleNode || !choiceModalNode || !creatorModalNode || !confirmModalNode) return;
      const shopfloorLoadPrefix = "[shopfloor-load]";
      const shopfloorSeconds = (startedAt) => ((performance.now() - startedAt) / 1000).toFixed(3);
      const shopfloorLog = (message, data = null) => {{
        if (data === null || data === undefined) console.log(`${{shopfloorLoadPrefix}} ${{message}}`);
        else console.log(`${{shopfloorLoadPrefix}} ${{message}}`, data);
      }};
      const shopfloorPayloadStats = (nextPayload) => {{
        const nextDocuments = Array.isArray(nextPayload?.documents) ? nextPayload.documents : [];
        const firstDocument = nextDocuments[0] || {{}};
        const sections = Array.isArray(firstDocument.sections) ? firstDocument.sections : [];
        return {{
          operation: String(nextPayload?.currentDocumentKey || firstDocument.key || ""),
          production: String(nextPayload?.productionNumber || ""),
          documents: nextDocuments.length,
          sections: sections.length,
          rows: sections.reduce((sum, section) => sum + (Array.isArray(section?.rows) ? section.rows.length : 0), 0),
          recentProductions: Array.isArray(nextPayload?.recentProductions) ? nextPayload.recentProductions.length : 0,
        }};
      }};

      let payload = {{}};
      try {{
        payload = JSON.parse(dataNode.textContent || "{{}}");
      }} catch (_error) {{
        payload = {{}};
      }}

      let documents = Array.isArray(payload.documents) ? payload.documents : [];
      if (!documents.length) return;
      let selectionState = Object.assign({{}}, payload.selectionState || {{}});
      let partialQuantityState = Object.assign({{}}, payload.partialQuantityState || {{}});
      const stateRoute = String(payload.stateRoute || "");
      const partialQtyRoute = String(payload.partialQtyRoute || "");
      const reportReadyRoute = String(payload.reportReadyRoute || "");
      const topfloorBoxRoute = String(payload.topfloorBoxRoute || "");
      const topfloorTransferRoute = String(payload.topfloorTransferRoute || "");
      const adminRevisionRoute = String(payload.adminRevisionRoute || "");
      let adminChangeRevision = String(payload.adminChangeRevision || "");
      let adminRevisionRefreshInFlight = false;
      const pageRoute = String(payload.route || window.location.pathname || "");
      const dataRoute = String(payload.dataRoute || `${{pageRoute}}/data`);
      const issuedEditCompleteRoute = `${{pageRoute.endsWith("/") ? pageRoute.slice(0, -1) : pageRoute}}/issued-row-edit-complete`;
      let productionNumber = String(payload.productionNumber || "");
      let directLookup = Boolean(payload.directLookup);
      let currentDocKey = String(payload.currentDocumentKey || documents[0]?.key || "");
      if (!documents.some((document) => document.key === currentDocKey)) {{
        currentDocKey = String(documents[0]?.key || "");
      }}
      let currentViewKey = "all";
      let currentSubcategoryKey = "all";
      let secondaryViewKey = "";
      let currentTopfloorShipmentKey = "";
      let topfloorShowIssued = false;
      let layoutMode = "single";
      const sectionSortState = Object.create(null);
      const partialSaveTimers = new Map();
      const expandedPantoloGroups = new Set();
      const openingPantoloGroups = new Set();
      const collapsingPantoloGroups = new Set();
      let pendingRedChoice = null;
      let pendingCreatorResolve = null;
      let pendingConfirmResolve = null;
      let activeSearchText = "";
      let pantoloStickyFrame = 0;
      const topfloorAllShipmentsKey = "shipment::__all__";
      const firstTopfloorShipmentViewKey = () => {{
        const document = currentDocument();
        if (String(document?.key || "") !== "topfloor") return "";
        const views = Array.isArray(document?.topfloorShipmentViews) ? document.topfloorShipmentViews : [];
        const firstView = views.find((view) => String(view?.key || "").startsWith("shipment::"));
        return String(firstView?.key || "");
      }};
      const topfloorShipmentViewForKey = (document, key) => {{
        if (String(document?.key || "") !== "topfloor") return null;
        const views = Array.isArray(document?.topfloorShipmentViews) ? document.topfloorShipmentViews : [];
        return views.find((view) => String(view?.key || "") === String(key || "")) || null;
      }};
      const topfloorShipmentIdFromKey = (key) => {{
        const text = String(key || "").trim();
        return text.startsWith("shipment::") ? text.slice("shipment::".length).trim() : "";
      }};
      const topfloorShipmentKeyIsAll = (key) => String(key || "").trim() === topfloorAllShipmentsKey;
      const topfloorHettichShipmentKey = "shipment::hettich";
      const topfloorShipmentKeyIsHettich = (key) => String(key || "").trim() === topfloorHettichShipmentKey;

      const syncUrlForDocument = () => {{
        try {{
          const url = new URL(window.location.href);
          if (String(currentDocKey || "") === "topfloor") {{
            url.searchParams.delete("production");
          }} else if (productionNumber) {{
            url.searchParams.set("production", productionNumber);
          }} else {{
            url.searchParams.delete("production");
          }}
          if (currentDocKey) url.searchParams.set("operation", currentDocKey);
          window.history.replaceState({{}}, "", url.toString());
        }} catch (_error) {{
        }}
      }};

      const productionPayloadCache = new Map();
      const productionCacheKey = (operationKey, targetProductionNumber) =>
        `${{String(operationKey || "").trim()}}::${{String(targetProductionNumber || "").trim()}}`;
      const cacheProductionPayload = (nextPayload) => {{
        const targetProductionNumber = String(nextPayload?.productionNumber || "").trim();
        const operationKey = String(nextPayload?.currentDocumentKey || currentDocKey || "").trim();
        if (Boolean(nextPayload?.directLookup)) return;
        if (!operationKey || !Array.isArray(nextPayload?.documents) || !nextPayload.documents.length) return;
        if (operationKey !== "topfloor" && !targetProductionNumber) return;
        productionPayloadCache.set(productionCacheKey(operationKey, targetProductionNumber), nextPayload);
      }};
      const storeCurrentProductionPayload = () => {{
        if (directLookup) return;
        cacheProductionPayload({{
          productionNumber,
          route: pageRoute,
          dataRoute,
          folder: String(payload.folder || ""),
          documents,
          currentDocumentKey: currentDocKey,
          recentProductions: Array.isArray(payload.recentProductions) ? payload.recentProductions : [],
          selectionState,
          stateRoute,
          partialQuantityState,
          partialQtyRoute,
          reportReadyRoute,
          topfloorBoxRoute,
          topfloorTransferRoute,
          topfloorStorageBoxTypes,
        }});
      }};
      const productionDataUrl = (targetProductionNumber, operationKey = currentDocKey) => {{
        const url = new URL(dataRoute || `${{pageRoute}}/data`, window.location.origin);
        const normalizedProductionNumber = String(targetProductionNumber || "").trim();
        if (normalizedProductionNumber) url.searchParams.set("production", normalizedProductionNumber);
        if (operationKey) url.searchParams.set("operation", operationKey);
        return url;
      }};
      const fetchProductionPayload = async (targetProductionNumber, operationKey = currentDocKey) => {{
        const cacheKey = productionCacheKey(operationKey, targetProductionNumber);
        const cached = productionPayloadCache.get(cacheKey);
        const startedAt = performance.now();
        if (cached) {{
          shopfloorLog(`payload cache hit operation=${{operationKey || "-"}} production=${{targetProductionNumber || "-"}} took=${{shopfloorSeconds(startedAt)}}s`, shopfloorPayloadStats(cached));
          return cached;
        }}
        const url = productionDataUrl(targetProductionNumber, operationKey);
        shopfloorLog(`payload fetch start operation=${{operationKey || "-"}} production=${{targetProductionNumber || "-"}} url=${{url.pathname + url.search}}`);
        const response = await fetch(url.toString(), {{
          headers: {{ "Accept": "application/json" }},
        }});
        const fetchSeconds = shopfloorSeconds(startedAt);
        const result = await response.json().catch(() => ({{}}));
        if (!response.ok || !result.ok) {{
          shopfloorLog(`payload fetch failed operation=${{operationKey || "-"}} production=${{targetProductionNumber || "-"}} status=${{response.status}} took=${{fetchSeconds}}s`);
          throw new Error(result.error || "A gyártás betöltése nem sikerült.");
        }}
        cacheProductionPayload(result);
        shopfloorLog(`payload fetch done operation=${{operationKey || "-"}} production=${{targetProductionNumber || "-"}} status=${{response.status}} took=${{fetchSeconds}}s`, shopfloorPayloadStats(result));
        return result;
      }};
      const chipHref = (targetProductionNumber, operationKey = currentDocKey) => {{
        const url = new URL(pageRoute || window.location.pathname, window.location.origin);
        const normalizedOperationKey = String(operationKey || "").trim();
        const normalizedProductionNumber = String(targetProductionNumber || "").trim();
        if (normalizedOperationKey !== "topfloor" && normalizedProductionNumber) {{
          url.searchParams.set("production", normalizedProductionNumber);
        }}
        if (operationKey) url.searchParams.set("operation", operationKey);
        return `${{url.pathname}}${{url.search}}`;
      }};
      const chipStatusClass = (status, isComplete = false) => {{
        const normalizedStatus = String(status || "").trim().toLowerCase();
        if (normalizedStatus === "done") return "is-done";
        if (normalizedStatus === "red") return "is-red";
        if (normalizedStatus === "green" || isComplete) return "is-complete";
        return "";
      }};
      const applyChipStatusClass = (link, status, isComplete = false) => {{
        if (!(link instanceof HTMLElement)) return;
        link.classList.remove("is-complete", "is-red", "is-done");
        const statusClass = chipStatusClass(status, isComplete);
        if (statusClass) link.classList.add(statusClass);
      }};
      const shipmentDateTone = (value) => {{
        const cleanValue = String(value || "").trim();
        if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(cleanValue)) return "";
        const target = new Date(`${{cleanValue}}T00:00:00`);
        if (Number.isNaN(target.getTime())) return "";
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const days = Math.round((target.getTime() - today.getTime()) / 86400000);
        return days <= 0 ? "red" : (days <= 7 ? "orange" : "yellow");
      }};
      const applyChipShipmentDate = (link, value) => {{
        if (!(link instanceof HTMLElement)) return;
        link.classList.remove("has-shipment-date", "is-date-yellow", "is-date-orange", "is-date-red");
        link.querySelector(".mfg-chip-shipment-date")?.remove();
        const cleanValue = String(value || "").trim();
        const tone = shipmentDateTone(cleanValue);
        if (!tone) return;
        link.classList.add("has-shipment-date", `is-date-${{tone}}`);
        const shipmentDateNode = document.createElement("span");
        shipmentDateNode.className = "mfg-chip-shipment-date";
        shipmentDateNode.textContent = cleanValue;
        link.append(shipmentDateNode);
      }};
      const renderProductionChips = (recentProductions = []) => {{
        if (!chipRowNode) return;
        chipRowNode.replaceChildren();
        for (const entry of (Array.isArray(recentProductions) ? recentProductions : [])) {{
          const entryNumber = String(entry?.number || "").trim();
          if (!entryNumber) continue;
          const entryKind = String(entry?.kind || "").trim();
          const entryViewKey = String(entry?.view_key || "").trim();
          const link = document.createElement("a");
          link.className = "mfg-chip-link";
          link.classList.toggle("has-issued-row-edit", Boolean(entry?.has_issued_row_edit));
          if (entryKind === "missing") {{
            link.href = "#pantolo-missing";
            link.setAttribute("data-mfg-missing-link", "");
            link.setAttribute("data-view-key", "pantolo-missing");
          }} else if (entryKind === "shipment" && entryViewKey) {{
            link.href = chipHref(productionNumber);
            link.setAttribute("data-mfg-shipment-link", "");
            link.setAttribute("data-view-key", entryViewKey);
            if (entryViewKey === topfloorAllShipmentsKey) {{
              link.setAttribute("data-mfg-all-shipments", "");
            }}
          }} else {{
            link.href = chipHref(entryNumber);
            link.setAttribute("data-mfg-production-link", "");
            link.setAttribute("data-production-number", entryNumber);
          }}
          applyChipStatusClass(link, entry?.state_status || "", Boolean(entry?.is_complete));
          const dateNode = document.createElement("span");
          dateNode.className = "mfg-chip-date";
          dateNode.textContent = String(entry?.date_label || "Dátum nélkül");
          const numberNode = document.createElement("span");
          numberNode.className = "mfg-chip-number";
          const categoryCount = Math.max(0, Number.parseInt(String(entry?.count || "0"), 10) || 0);
          const issuedCount = Math.min(categoryCount, Math.max(0, Number.parseInt(String(entry?.issued_count || "0"), 10) || 0));
          const ratioText = `${{issuedCount}}/${{categoryCount}}`;
          numberNode.textContent = entryKind === "missing"
            ? `${{categoryCount}} tétel`
            : entryKind === "shipment" && categoryCount
              ? (entryViewKey === topfloorAllShipmentsKey ? ratioText : `${{entryNumber}} · ${{ratioText}}`)
              : entryNumber;
          link.append(dateNode, numberNode);
          if (entryKind === "shipment" && entryViewKey !== topfloorAllShipmentsKey) {{
            applyChipShipmentDate(link, entry?.shipment_date || "");
          }}
          chipRowNode.append(link);
        }}
        updateProductionChipState(recentProductions);
      }};
      const updateProductionChipState = (recentProductions = []) => {{
        const statusByNumber = new Map(
          (Array.isArray(recentProductions) ? recentProductions : [])
            .map((entry) => [
              String(entry?.number || ""),
              {{
                status: String(entry?.state_status || "").trim().toLowerCase(),
                isComplete: Boolean(entry?.is_complete),
              }},
            ]),
        );
        document.querySelectorAll("[data-mfg-missing-link]").forEach((link) => {{
          if (!(link instanceof HTMLElement)) return;
          link.classList.toggle("is-active", currentViewKey === "pantolo-missing");
          const missingView = specialViewForKey(currentDocument(), "pantolo-missing");
          const missingCount = Array.isArray(missingView?.sections)
            ? missingView.sections
                .flatMap((section) => Array.isArray(section?.rows) ? section.rows : [])
                .reduce((total, row) => {{
                  const childKeys = Array.isArray(row?.childUnitStateKeys) ? row.childUnitStateKeys : [];
                  if (childKeys.length) return total + childKeys.filter((key) => selectionState[String(key || "")] === "red").length;
                  return total + (rowStateValue(row) === "red" ? pantoloQuantity(row) : 0);
                }}, 0)
            : 0;
          const numberNode = link.querySelector(".mfg-chip-number");
          if (numberNode) numberNode.textContent = `${{missingCount}} tétel`;
          applyChipStatusClass(link, missingCount ? "red" : "plain", false);
        }});
        document.querySelectorAll("[data-mfg-shipment-link]").forEach((link) => {{
          if (!(link instanceof HTMLElement)) return;
          const viewKey = String(link.getAttribute("data-view-key") || "").trim();
          const shipmentComplete = topfloorSectionsComplete(topfloorShipmentSectionsForKey(currentDocument(), viewKey, {{ includeIssued: true }}));
          const shipmentHasIssuedEdit = topfloorShipmentHasIssuedEdit(currentDocument(), viewKey);
          link.hidden = !topfloorShowIssued && !topfloorShipmentKeyIsAll(viewKey) && !topfloorShipmentKeyIsHettich(viewKey) && shipmentComplete && !shipmentHasIssuedEdit;
          link.classList.toggle("has-issued-row-edit", shipmentHasIssuedEdit);
          link.classList.toggle("is-active", viewKey === currentTopfloorShipmentKey);
          const allTabStatus = viewKey === currentTopfloorShipmentKey ? currentAllTabStateStatus() : "";
          applyChipStatusClass(link, allTabStatus || (shipmentComplete ? "done" : ""), shipmentComplete);
        }});
        document.querySelectorAll("[data-mfg-production-link]").forEach((link) => {{
          if (!(link instanceof HTMLElement)) return;
          const linkNumber = String(link.getAttribute("data-production-number") || "").trim();
          const isActiveProduction = linkNumber === productionNumber;
          const cachedPayload = isActiveProduction
            ? null
            : productionPayloadCache.get(productionCacheKey(currentDocKey, linkNumber));
          const alertDocuments = isActiveProduction
            ? documents
            : (Array.isArray(cachedPayload?.documents) ? cachedPayload.documents : []);
          link.classList.toggle(
            "has-issued-row-edit",
            alertDocuments.some((document) => alertRowsForDocument(document).length),
          );
          link.classList.toggle("is-active", isActiveProduction && currentViewKey !== "pantolo-missing");
          if (statusByNumber.has(linkNumber)) {{
            const statusItem = statusByNumber.get(linkNumber) || {{}};
            const cachedStatus = isActiveProduction ? currentAllTabStateStatus() : cachedProductionAllTabStateStatus(linkNumber);
            const nextStatus = cachedStatus !== null ? cachedStatus : (statusItem.status || "");
            applyChipStatusClass(
              link,
              nextStatus,
              cachedStatus !== null ? ["green", "done"].includes(nextStatus) : Boolean(statusItem.isComplete),
            );
          }} else if (isActiveProduction) {{
            applyChipStatusClass(link, currentAllTabStateStatus(), false);
          }}
        }});
      }};
      const refreshOperationHeader = () => {{
        const activeDocument = documents.find((document) => document?.key === currentDocKey) || documents[0] || null;
        if (operationTitleNode) {{
          operationTitleNode.textContent = String(activeDocument?.label || "");
        }}
        if (operationSourceNode) {{
          const shipmentView = String(activeDocument?.key || "") === "topfloor"
            ? topfloorShipmentViewForKey(activeDocument, currentTopfloorShipmentKey || firstTopfloorShipmentViewKey())
            : null;
          const boxCount = Math.max(0, Number.parseInt(String(shipmentView?.count || "0"), 10) || 0);
          const sourceLabel = boxCount
            ? (Boolean(shipmentView?.isHettich) ? `${{boxCount}} kategória` : `${{boxCount}} doboz`)
            : String(activeDocument?.sourceLabel || "").trim();
          operationSourceNode.textContent = sourceLabel;
          operationSourceNode.hidden = !sourceLabel;
        }}
      }};
      const applyProductionPayload = (nextPayload) => {{
        const applyStartedAt = performance.now();
        const nextDocuments = Array.isArray(nextPayload?.documents) ? nextPayload.documents : [];
        if (!nextDocuments.length) throw new Error("A gyártáshoz nincs megjeleníthető adat.");
        shopfloorLog("apply payload start", shopfloorPayloadStats(nextPayload));
        payload = Object.assign({{}}, payload, nextPayload);
        documents = nextDocuments;
        selectionState = Object.assign({{}}, nextPayload.selectionState || {{}});
        partialQuantityState = Object.assign({{}}, nextPayload.partialQuantityState || {{}});
        topfloorStorageBoxTypes = Array.isArray(nextPayload.topfloorStorageBoxTypes) ? nextPayload.topfloorStorageBoxTypes : topfloorStorageBoxTypes;
        productionNumber = String(nextPayload.productionNumber || "");
        directLookup = Boolean(nextPayload.directLookup);
        pendingWriteStorageKey = `mfg-pending-state-writes:${{productionNumber || "unknown"}}`;
        currentDocKey = String(nextPayload.currentDocumentKey || documents[0]?.key || "");
        if (!documents.some((document) => document.key === currentDocKey)) {{
          currentDocKey = String(documents[0]?.key || "");
        }}
        currentViewKey = "all";
        currentSubcategoryKey = "all";
        secondaryViewKey = "";
        currentTopfloorShipmentKey = "";
        activeSearchText = "";
        searchInputNode.value = "";
        applyStoredPendingWritesToLocalState();
        syncUrlForDocument();
        refreshOperationHeader();
        updateProductionChipState(nextPayload.recentProductions);
        const renderStartedAt = performance.now();
        renderAll();
        shopfloorLog(`render after apply took=${{shopfloorSeconds(renderStartedAt)}}s`);
        if (pendingWriteCount()) {{
          setStatus(pendingStatusText(), "is-error");
          void flushPendingWrites();
        }}
        shopfloorLog(`apply payload done took=${{shopfloorSeconds(applyStartedAt)}}s`, shopfloorPayloadStats(nextPayload));
      }};
      if (Array.isArray(payload.productionClientCache)) {{
        for (const cachedPayload of payload.productionClientCache) {{
          cacheProductionPayload(cachedPayload);
        }}
      }}
      cacheProductionPayload(payload);
      const forceRefreshForAdminChange = async (nextRevision) => {{
        if (adminRevisionRefreshInFlight || !currentDocKey) return;
        adminRevisionRefreshInFlight = true;
        const preservedView = {{
          currentViewKey,
          currentSubcategoryKey,
          secondaryViewKey,
          currentTopfloorShipmentKey,
          topfloorShowIssued,
          layoutMode,
          activeSearchText,
          scrollState: captureScrollState(),
        }};
        try {{
          await flushPendingWrites();
          const isTopfloor = String(currentDocKey || "") === "topfloor";
          const url = productionDataUrl(isTopfloor ? "" : productionNumber, currentDocKey);
          url.searchParams.set("admin_revision", String(nextRevision || ""));
          const response = await fetch(url.toString(), {{
            cache: "no-store",
            headers: {{ "Accept": "application/json" }},
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "Az admin módosítás betöltése nem sikerült.");
          }}
          productionPayloadCache.clear();
          cacheProductionPayload(result);
          applyProductionPayload(result);
          currentViewKey = preservedView.currentViewKey;
          currentSubcategoryKey = preservedView.currentSubcategoryKey;
          secondaryViewKey = preservedView.secondaryViewKey;
          currentTopfloorShipmentKey = preservedView.currentTopfloorShipmentKey;
          topfloorShowIssued = preservedView.topfloorShowIssued;
          layoutMode = preservedView.layoutMode;
          activeSearchText = preservedView.activeSearchText;
          searchInputNode.value = preservedView.activeSearchText;
          renderProductionChips(result.recentProductions);
          renderAll(preservedView.scrollState);
          adminChangeRevision = String(nextRevision || "");
          setStatus("Admin módosítás automatikusan betöltve.", "is-success");
        }} catch (error) {{
          setStatus(error instanceof Error ? error.message : "Az admin módosítás betöltése nem sikerült.", "is-error");
        }} finally {{
          adminRevisionRefreshInFlight = false;
        }}
      }};
      const pollAdminChangeRevision = async () => {{
        if (!adminRevisionRoute || adminRevisionRefreshInFlight) return;
        try {{
          const url = new URL(adminRevisionRoute, window.location.origin);
          url.searchParams.set("_", String(Date.now()));
          const response = await fetch(url.toString(), {{
            cache: "no-store",
            headers: {{ "Accept": "application/json" }},
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) return;
          const nextRevision = String(result.revision || "");
          if (!nextRevision || nextRevision === adminChangeRevision) return;
          await forceRefreshForAdminChange(nextRevision);
        }} catch (_error) {{
        }}
      }};
      window.setInterval(() => void pollAdminChangeRevision(), 10000);
      document.addEventListener("visibilitychange", () => {{
        if (!document.hidden) void pollAdminChangeRevision();
      }});

      const refreshProductionClientCache = async () => {{
        if (!currentDocKey) return;
        const refreshStartedAt = performance.now();
        const isTopfloor = String(currentDocKey || "").trim() === "topfloor";
        if (!isTopfloor && !productionNumber) return;
        const refreshProductionNumber = isTopfloor ? "" : productionNumber;
        shopfloorLog(`cache refresh start operation=${{currentDocKey || "-"}} production=${{refreshProductionNumber || "-"}}`);
        if (cacheRefreshButtonNode) cacheRefreshButtonNode.classList.add("is-loading");
        setStatus("Gyártási lista frissítése...");
        try {{
          await flushPendingWrites();
          const url = productionDataUrl(refreshProductionNumber, currentDocKey);
          url.searchParams.set("refresh_cache", "1");
          const fetchStartedAt = performance.now();
          const response = await fetch(url.toString(), {{
            headers: {{ "Accept": "application/json" }},
          }});
          shopfloorLog(`cache refresh fetch took=${{shopfloorSeconds(fetchStartedAt)}}s status=${{response.status}}`);
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "A gyorsítótár frissítése nem sikerült.");
          }}
          productionPayloadCache.clear();
          payload.productionClientCache = Array.isArray(result.productionClientCache) ? result.productionClientCache : [];
          for (const cachedPayload of payload.productionClientCache) {{
            cacheProductionPayload(cachedPayload);
          }}
          cacheProductionPayload(result);
          renderProductionChips(result.recentProductions);
          applyProductionPayload(result);
          shopfloorLog(`cache refresh done operation=${{currentDocKey || "-"}} took=${{shopfloorSeconds(refreshStartedAt)}}s`, shopfloorPayloadStats(result));
          setStatus("Gyorsítótár frissítve.", "is-success");
        }} catch (error) {{
          shopfloorLog(`cache refresh failed operation=${{currentDocKey || "-"}} took=${{shopfloorSeconds(refreshStartedAt)}}s`, error);
          setStatus(error instanceof Error ? error.message : "A gyorsítótár frissítése nem sikerült.", "is-error");
        }} finally {{
          if (cacheRefreshButtonNode) cacheRefreshButtonNode.classList.remove("is-loading");
        }}
      }};

      const escapeHtml = (value) =>
        String(value ?? "").replace(/[&<>"']/g, (character) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[character] || character);
      const rowFieldWasEdited = (row, field) =>
        Array.isArray(row?._rowDataEditedFields) && row._rowDataEditedFields.includes(field);
      const rowEditedMarker = (row, field) =>
        rowFieldWasEdited(row, field)
          ? '<span class="mfg-edited-marker" title="Admin által módosított adat" aria-label="Admin által módosított adat">✎</span>'
          : "";
      const displayRowField = (row, field, fallback = "-") =>
        `${{escapeHtml(row?.[field] || fallback)}}${{rowEditedMarker(row, field)}}`;
      const flattenRows = (document) => (document?.sections || []).flatMap((section) => Array.isArray(section.rows) ? section.rows : []);
      const totalQuantityForRows = (rows) => Array.isArray(rows)
        ? rows.reduce((sum, row) => sum + Number(row?.quantity || 0), 0)
        : 0;
      const totalQuantityForSections = (sections) => (Array.isArray(sections) ? sections : []).reduce(
        (sum, section) => sum + totalQuantityForRows(section?.rows),
        0,
      );
      const currentDocument = () => documents.find((document) => document.key === currentDocKey) || documents[0] || null;
      const documentAllowsSplit = (document) => document?.allowSplit !== false;
      const documentUsesSingleColumnOverview = (document) => document?.singleColumnOverview === true;
      const documentHidesBarcode = (document) => document?.hideBarcodeColumn === true;
      const documentUsesSearch = (document) => Boolean(document);
      const groupColumnLayout = (group) => {{
        const directLayout = String(group?.columnLayout || "").trim();
        if (directLayout) return directLayout;
        const firstRowLayout = String((Array.isArray(group?.rows) && group.rows.length ? group.rows[0]?.columnLayout : "") || "").trim();
        return firstRowLayout;
      }};
      const pantoloCategoryLabelMarkup = (label) => {{
        const parts = String(label || "").split("|").map((part) => part.trim()).filter(Boolean);
        if (parts.length < 3) return `<span class="mfg-pantolo-category-main">${{escapeHtml(label || "")}}</span>`;
        const frontType = parts[0];
        const color = parts[1];
        const model = parts.slice(2).join(" | ");
        return `
          <span class="mfg-pantolo-category-main">${{escapeHtml(frontType)}}</span>
          <span class="mfg-pantolo-category-pill">${{escapeHtml(color)}}</span>
          <span class="mfg-pantolo-category-pill">${{escapeHtml(model)}}</span>
        `;
      }};
      const specialViewsForDocument = (document) => Array.isArray(document?.specialViews) ? document.specialViews : [];
      const specialViewForKey = (document, key) =>
        specialViewsForDocument(document).find((view) => String(view?.key || "") === String(key || "")) || null;
      const overviewSectionsForDocument = (document, includeOverviewOnly = false) => {{
        if (String(document?.key || "") === "cnc_furas") {{
          return specialViewsForDocument(document)
            .filter((view) => includeOverviewOnly || !Boolean(view?.overviewOnly))
            .flatMap((view) => Array.isArray(view?.sections) ? view.sections : []);
        }}
        return Array.isArray(document?.sections) ? document.sections : [];
      }};
      const frontSubcategoriesForView = (document, viewKey) => {{
        if (String(document?.key || "") !== "front_osszekeszites") return [];
        if (!/^front-(folias|butorlapos)-(also|felso)$/.test(String(viewKey || ""))) return [];
        const specialView = specialViewForKey(document, viewKey);
        const sections = Array.isArray(specialView?.sections) ? specialView.sections : [];
        const grouped = new Map();
        for (const section of sections) {{
          const label = String(section?.label || "");
          const sizeLabel = label.includes("·") ? label.split("·", 1)[0].trim() : label.trim();
          if (!sizeLabel) continue;
          const count = totalQuantityForRows(section?.rows);
          grouped.set(sizeLabel, (grouped.get(sizeLabel) || 0) + count);
        }}
        return Array.from(grouped.entries())
          .sort((left, right) => String(left[0]).localeCompare(String(right[0]), "hu-HU", {{ numeric: true, sensitivity: "base" }}))
          .map(([label, count]) => ({{
            key: label,
            label,
            count,
          }}));
      }};
      const korpuszMainViews = (document) => {{
        if (String(document?.key || "") !== "korpusz_osszekeszites") return [];
        return specialViewsForDocument(document).filter((view) => {{
          const key = String(view?.key || "");
          return key === "korpusz-osszekeszito" || key === "korpusz-alkatresz-kesz" || key === "all-productions-red";
        }});
      }};
      const korpuszXmlBackedViewKeys = new Set(["korpusz-osszekeszito", "korpusz-alkatresz-kesz"]);
      const korpuszViewEmptyIsDone = (view) => korpuszXmlBackedViewKeys.has(String(view?.key || ""));
      const specialViewUsesRedFilter = (view) => Boolean(view?.redFilter) || ["current-production-red", "all-productions-red", "pantolo-missing"].includes(String(view?.key || ""));
      const rowStateKey = (row) => String(row?.state_key || row?.row_id || "");
      const rowStorageKey = (row) => String(row?.state_storage_key || row?.row_id || "");
      const rowProductionNumber = (row) => String(row?.production_number || productionNumber || "");
      const isReadyGreenState = (value) => value === "green";
      const isGreenLikeState = (value) => value === "green" || value === "done";
      let topfloorStorageBoxTypes = Array.isArray(payload.topfloorStorageBoxTypes) ? payload.topfloorStorageBoxTypes : [];
      const pantoloQuantity = (row) => Math.max(1, Number(row?.meValue || row?.quantity || 0) || 1);
      const groupedQuantityLayouts = new Set(["pantolo", "front-standard"]);
      const documentUsesGroupedQuantityRows = (document) => ["pantolas", "front_osszekeszites"].includes(String(document?.key || ""));
      const rowUsesGroupedQuantity = (row) => groupedQuantityLayouts.has(String(row?.columnLayout || "").trim());
      const isPantoloRow = (row) => rowUsesGroupedQuantity(row);
      const isPantoloGroupedRow = (row) => isPantoloRow(row) && !row?.isPantoloUnit && (pantoloQuantity(row) > 1 || Boolean(row?.forcePantoloGroup));
      const childUnitRowId = (row, index) => `${{String(row?.row_id || "")}}__child_unit_${{index + 1}}`;
      const isChildUnitRowId = (value) => {{
        const text = String(value || "");
        return text.includes("__child_unit_") || text.includes("__pantolo_unit_");
      }};
      const stateKeyForRowId = (targetProductionNumber, rowId) => `${{targetProductionNumber}}::${{rowId}}`;
      const xmlSourceStateKeyPattern = /^[^:\\s][^:]*::\\d+::[^:]+::\\d+$/;
      const normalizeSelectionKey = (targetProductionNumber, value) => {{
        const text = String(value || "").trim();
        if (!text) return "";
        return xmlSourceStateKeyPattern.test(text) ? text : stateKeyForRowId(targetProductionNumber, text);
      }};
      const childUnitStorageKey = (row, index) => {{
        const explicitKeys = Array.isArray(row?.childUnitStateKeys) ? row.childUnitStateKeys : [];
        const explicitKey = String(explicitKeys[index] || "").trim();
        if (explicitKey) return explicitKey;
        const parentStorageKey = rowStorageKey(row);
        if (xmlSourceStateKeyPattern.test(parentStorageKey)) {{
          return parentStorageKey.replace(/::\\d+$/, `::${{index + 1}}`);
        }}
        return childUnitRowId(row, index);
      }};
      const childUnitStateKey = (row, index) => {{
        const storageKey = childUnitStorageKey(row, index);
        return xmlSourceStateKeyPattern.test(storageKey)
          ? storageKey
          : stateKeyForRowId(rowProductionNumber(row), storageKey);
      }};
      const findRowById = (rowId) => {{
        const targetId = String(rowId || "");
        const visibleMatch = buildGroupsForView(currentDocument())
          .flatMap((section) => Array.isArray(section?.rows) ? section.rows : [])
          .find((row) => String(row?.row_id || "") === targetId);
        if (visibleMatch) return visibleMatch;
        for (const document of documents) {{
          const searchableSections = [
            ...(Array.isArray(document?.sections) ? document.sections : []),
            ...specialViewsForDocument(document).flatMap((view) => Array.isArray(view?.sections) ? view.sections : []),
          ];
          for (const section of searchableSections) {{
            const found = (Array.isArray(section?.rows) ? section.rows : []).find((row) => String(row?.row_id || "") === targetId);
            if (found) return found;
          }}
        }}
        return null;
      }};
      const pantoloHasExplicitUnitState = (row) => {{
        if (!isPantoloGroupedRow(row)) return false;
        for (let index = 0; index < pantoloQuantity(row); index += 1) {{
          if (Object.prototype.hasOwnProperty.call(selectionState, childUnitStateKey(row, index))) return true;
          if (Object.prototype.hasOwnProperty.call(selectionState, stateKeyForRowId(rowProductionNumber(row), childUnitRowId(row, index)))) return true;
        }}
        return false;
      }};
      const childUnitState = (row, index) => {{
        const parentState = selectionState[rowStateKey(row)] || "";
        if (parentState === "done") return "done";
        const unitKey = childUnitStateKey(row, index);
        if (Object.prototype.hasOwnProperty.call(selectionState, unitKey)) return selectionState[unitKey] || "";
        const legacyUnitKey = stateKeyForRowId(rowProductionNumber(row), childUnitRowId(row, index));
        if (Object.prototype.hasOwnProperty.call(selectionState, legacyUnitKey)) return selectionState[legacyUnitKey] || "";
        return pantoloHasExplicitUnitState(row) ? "" : parentState;
      }};
      const pantoloGroupState = (row) => {{
        if (!isPantoloGroupedRow(row)) return selectionState[rowStateKey(row)] || "";
        const parentState = selectionState[rowStateKey(row)] || "";
        if (parentState === "done") return "done";
        const states = Array.from({{ length: pantoloQuantity(row) }}, (_item, index) => childUnitState(row, index));
        if (states.every((state) => !state)) return "";
        if (states.every((state) => state === "red")) return "red";
        if (states.every((state) => state === "done")) return "done";
        if (states.every((state) => isGreenLikeState(state))) return states.includes("green") ? "green" : "done";
        return "mixed";
      }};
      const rowSourceStateKeys = (row) => Array.from(new Set(
        (Array.isArray(row?.sourceRowIds) ? row.sourceRowIds : [])
          .map((value) => normalizeSelectionKey(rowProductionNumber(row), value))
          .filter(Boolean)
      ));
      const sourceBlockState = (row) => {{
        const keys = rowSourceStateKeys(row);
        if (!keys.length) return "";
        const states = keys.map((key) => selectionState[key] || "").filter(Boolean);
        if (!states.length) return "";
        if (states.every((state) => state === states[0])) return states[0];
        if (states.every((state) => isGreenLikeState(state))) return states.includes("green") ? "green" : "done";
        return "mixed";
      }};
      const rowStateValue = (row) => {{
        if (isPantoloGroupedRow(row)) return pantoloGroupState(row);
        if (row?.isPantoloUnit) {{
          const explicitState = selectionState[rowStateKey(row)] || "";
          return explicitState || String(row?.inheritedState || "");
        }}
        const blockState = sourceBlockState(row);
        if (blockState) return blockState;
        if (rowSourceStateKeys(row).length) return "";
        return selectionState[rowStateKey(row)] || "";
      }};
      const pantoloGreenedCount = (row) => {{
        if (isPantoloGroupedRow(row)) {{
          let count = 0;
          for (let index = 0; index < pantoloQuantity(row); index += 1) {{
            if (isGreenLikeState(childUnitState(row, index))) count += 1;
          }}
          return count;
        }}
        return isGreenLikeState(rowStateValue(row)) ? 1 : 0;
      }};
      const pantoloQuantityText = (row) => `${{pantoloGreenedCount(row)}}/${{pantoloQuantity(row)}}`;
      const canReportReadyForCurrentView = (document) => {{
        const documentKey = String(document?.key || "");
        if (!reportReadyRoute) return false;
        if (documentKey === "korpusz_osszekeszites") return currentSubcategoryKey === "green";
        if (documentKey === "front_osszekeszites") return currentViewKey === "green";
        return false;
      }};
      const countStateInDocument = (document, wanted) => flattenRows(document)
        .filter((row) => rowStateValue(row) === wanted)
        .reduce((sum, row) => sum + Number(row?.quantity || 0), 0);
      const countPlainInDocument = (document) => flattenRows(document)
        .filter((row) => !rowStateValue(row))
        .reduce((sum, row) => sum + Number(row?.quantity || 0), 0);
      const countRowsInSections = (sections, predicate = null) =>
        (Array.isArray(sections) ? sections : []).reduce((total, section) => {{
          const rows = Array.isArray(section?.rows) ? section.rows : [];
          return total + rows
            .filter((row) => !predicate || predicate(row))
            .reduce((sum, row) => sum + Number(row?.quantity || 0), 0);
        }}, 0);
      const specialViewKeys = new Set(["all", "plain", "green", "red", "mixed"]);
      const isSpecialViewKey = (key, document = currentDocument()) =>
        specialViewKeys.has(String(key || "")) || Boolean(specialViewForKey(document, key));
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
                width: 0.72,
                height: 30,
                margin: 1,
                displayValue: false,
                background: "transparent",
              }});
              node.removeAttribute("width");
              node.removeAttribute("height");
              node.setAttribute("preserveAspectRatio", "none");
              node.style.width = "100%";
              node.style.height = "28px";
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
      let pendingWriteStorageKey = `mfg-pending-state-writes:${{productionNumber || "unknown"}}`;
      let isFlushingPendingWrites = false;

      const readPendingWrites = () => {{
        try {{
          const value = window.localStorage.getItem(pendingWriteStorageKey);
          const parsed = value ? JSON.parse(value) : [];
          return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item === "object") : [];
        }} catch (_error) {{
          return [];
        }}
      }};

      const writePendingWrites = (writes) => {{
        try {{
          window.localStorage.setItem(pendingWriteStorageKey, JSON.stringify(Array.isArray(writes) ? writes : []));
          return true;
        }} catch (_error) {{
          return false;
        }}
      }};

      const pendingWriteCount = () => readPendingWrites().length;
      const pendingStatusText = () => {{
        const count = pendingWriteCount();
        return count ? `Kapcsolat megszakadt. ${{count}} ment\u00e9s v\u00e1r felt\u00f6lt\u00e9sre.` : "";
      }};

      const removePendingWrite = (id) => {{
        const cleanId = String(id || "");
        if (!cleanId) return;
        writePendingWrites(readPendingWrites().filter((item) => String(item.id || "") !== cleanId));
      }};

      const appendPendingWrite = (write) => {{
        const writes = readPendingWrites();
        const id = `${{Date.now()}}-${{Math.random().toString(36).slice(2)}}`;
        writes.push({{ ...write, id, created_at: Date.now() }});
        if (!writePendingWrites(writes)) {{
          throw new Error("A b\u00f6ng\u00e9sz\u0151 helyi ment\u00e9st\u00e1ra megtelt vagy nem el\u00e9rhet\u0151.");
        }}
        return id;
      }};

      const postJson = async (route, body) => {{
        const response = await fetch(route, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(body || {{}}),
        }});
        const result = await response.json().catch(() => ({{}}));
        if (!response.ok || !result.ok) {{
          const error = new Error(result.error || "A ment\u00e9s nem siker\u00fclt.");
          error.isPermanent = response.status >= 400 && response.status < 500;
          throw error;
        }}
        return result;
      }};

      const applyPendingWriteToLocalState = (write) => {{
        const body = write && write.body && typeof write.body === "object" ? write.body : {{}};
        if (write?.type === "row-state") {{
          const stateKeys = Array.isArray(body.state_keys) ? body.state_keys : [body.state_key];
          const rowIds = Array.isArray(body.row_ids) ? body.row_ids : [body.row_id];
          const cleanStateKeys = stateKeys.map((value) => String(value || "").trim()).filter(Boolean);
          const cleanRowIds = rowIds.map((value) => String(value || "").trim()).filter(Boolean);
          for (const key of cleanStateKeys) {{
            const state = String(body.state || "").trim().toLowerCase();
            if (!state || state === "clear" || state === "none") delete selectionState[key];
            else selectionState[key] = state;
          }}
          for (const key of cleanRowIds) {{
            if (cleanStateKeys.includes(key)) continue;
            delete selectionState[key];
          }}
          return;
        }}
        if (write?.type === "partial-quantity") {{
          const stateKey = String(body.state_key || "").trim();
          const value = String(body.value || "").trim();
          if (!stateKey) return;
          if (value) partialQuantityState[stateKey] = value;
          else delete partialQuantityState[stateKey];
        }}
      }};

      const applyStoredPendingWritesToLocalState = () => {{
        for (const write of readPendingWrites()) {{
          applyPendingWriteToLocalState(write);
        }}
      }};

      const sendPendingWrite = async (write) => {{
        if (write?.type === "row-state") {{
          await postJson(stateRoute, write.body || {{}});
          return;
        }}
        if (write?.type === "partial-quantity") {{
          const result = await postJson(partialQtyRoute, write.body || {{}});
          const stateKey = String(write.body?.state_key || "").trim();
          if (stateKey) {{
            if (result.value) partialQuantityState[stateKey] = String(result.value);
            else delete partialQuantityState[stateKey];
          }}
        }}
      }};

      const flushPendingWrites = async () => {{
        if (isFlushingPendingWrites) return;
        isFlushingPendingWrites = true;
        try {{
          while (true) {{
            const writes = readPendingWrites();
            if (!writes.length) {{
              setStatus("Mentve.", "is-success");
              return;
            }}
            const nextWrite = writes[0];
            try {{
              await sendPendingWrite(nextWrite);
              removePendingWrite(nextWrite.id);
            }} catch (error) {{
              if (error?.isPermanent) {{
                removePendingWrite(nextWrite.id);
                setStatus(error instanceof Error ? error.message : "Egy f\u00fcgg\u0151 ment\u00e9s elutas\u00edtva.", "is-error");
                continue;
              }}
              const message = pendingStatusText() || "Kapcsolat megszakadt. A ment\u00e9s k\u00e9s\u0151bb \u00fajrapr\u00f3b\u00e1lkozik.";
              setStatus(message, "is-error");
              return;
            }}
          }}
        }} finally {{
          isFlushingPendingWrites = false;
        }}
      }};

      const queuePersistentWrite = (write) => {{
        appendPendingWrite(write);
        applyPendingWriteToLocalState(write);
        void flushPendingWrites();
      }};

      window.addEventListener("online", () => void flushPendingWrites());
      window.addEventListener("focus", () => void flushPendingWrites());
      const normalizeSearchText = (value) =>
        String(value ?? "")
          .toLocaleLowerCase("hu-HU")
          .normalize("NFD")
          .replace(/[\\u0300-\\u036f]/g, "")
          .replace(/\\s+/g, " ")
          .trim();
      const activeSearchTerms = () => normalizeSearchText(activeSearchText).split(" ").filter(Boolean);
      const collectSearchParts = (value, parts = []) => {{
        if (value == null) return parts;
        if (Array.isArray(value)) {{
          value.forEach((item) => collectSearchParts(item, parts));
          return parts;
        }}
        if (typeof value === "object") {{
          Object.values(value).forEach((item) => collectSearchParts(item, parts));
          return parts;
        }}
        parts.push(String(value));
        return parts;
      }};
      const rowMatchesSearch = (row, group, terms) => {{
        if (!terms.length) return true;
        const searchable = normalizeSearchText(collectSearchParts(row, [group?.label || "", group?.key || ""]).join(" "));
        return terms.every((term) => searchable.includes(term));
      }};
      const topfloorCategoryMatchesSearch = (group, terms) => {{
        if (!terms.length) return true;
        const category = group?.topfloorCategory || {{}};
        const searchable = normalizeSearchText([
          group?.label || "",
          category.productionID,
          category.buyer,
          category.location,
          category.orderNumber,
          category.buyerID,
          category.orderType,
          category.boxId,
          category.boxDescription,
          category.defaultBoxDescription,
        ].map((value) => String(value || "")).join(" "));
        return terms.every((term) => searchable.includes(term));
      }};
      const filterGroupsBySearch = (groups, document) => {{
        const terms = activeSearchTerms();
        if (!documentUsesSearch(document) || !terms.length) return groups;
        if (String(document?.key || "") === "topfloor") {{
          return (Array.isArray(groups) ? groups : []).filter((group) => topfloorCategoryMatchesSearch(group, terms));
        }}
        return (Array.isArray(groups) ? groups : [])
          .map((group) => ({{
            ...group,
            rows: (Array.isArray(group?.rows) ? group.rows : []).filter((row) => rowMatchesSearch(row, group, terms)),
          }}))
          .filter((group) => Array.isArray(group.rows) && group.rows.length);
      }};
      const updateSearchControls = (activeDocument) => {{
        const enabled = documentUsesSearch(activeDocument);
        searchRowNode.hidden = !enabled;
        if (!enabled) {{
          activeSearchText = "";
          searchInputNode.value = "";
        }} else if (window.document.activeElement !== searchInputNode) {{
          searchInputNode.value = activeSearchText;
        }}
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
      const rowOrderingField = (row, field) =>
        row?._rowDataOriginal && Object.prototype.hasOwnProperty.call(row._rowDataOriginal, field)
          ? row._rowDataOriginal[field]
          : row?.[field];
      const rowSortValue = (row, sortKey) => {{
        if (sortKey === "name") return normalizeSortText(rowOrderingField(row, "name"));
        if (sortKey === "size") return parseSizeParts(rowOrderingField(row, "size"));
        if (sortKey === "model") return normalizeSortText(rowOrderingField(row, "modelLabel"));
        if (sortKey === "color23") return normalizeSortText(rowOrderingField(row, "color23"));
        if (sortKey === "pant_type") return normalizeSortText(rowOrderingField(row, "pantType"));
        if (sortKey === "handle_drill") return normalizeSortText(rowOrderingField(row, "handleDrill"));
        if (sortKey === "handle_type") return normalizeSortText(rowOrderingField(row, "handleType"));
        if (sortKey === "opening_dir") return normalizeSortText(rowOrderingField(row, "openingDir"));
        if (sortKey === "door_type") return normalizeSortText(rowOrderingField(row, "doorType"));
        if (sortKey === "trait") return normalizeSortText(rowOrderingField(row, "frontTrait"));
        if (sortKey === "color") return normalizeSortText(rowOrderingField(row, "color"));
        if (sortKey === "netfront_color") return normalizeSortText(rowOrderingField(row, "netfrontColor"));
        if (sortKey === "drill") return normalizeSortText(rowOrderingField(row, "drillLabel"));
        if (sortKey === "drawer_type") return normalizeSortText(rowOrderingField(row, "drawerType"));
        if (sortKey === "drawer_drill") return normalizeSortText(rowOrderingField(row, "drawer_drill"));
        if (sortKey === "side_type") return normalizeSortText(rowOrderingField(row, "side_type"));
        if (sortKey === "hardware_type") return normalizeSortText(rowOrderingField(row, "hardware_type"));
        if (sortKey === "edge") return normalizeSortText(rowOrderingField(row, "edge"));
        if (sortKey === "quantity") return Number(row.quantity || 0);
        if (sortKey === "code") return normalizeSortText(row.code || row.detail || row.row_id);
        return 0;
      }};
      const normalizedSectionSortKey = (sectionKey) => String(sectionKey || "__default__");
      const activeSectionsForSortLookup = () => {{
        const document = currentDocument();
        if (!document) return [];
        const currentSpecialView = specialViewForKey(document, currentViewKey);
        if (currentSpecialView && Array.isArray(currentSpecialView.sections)) {{
          return currentSpecialView.sections;
        }}
        return Array.isArray(document.sections) ? document.sections : [];
      }};
      const sectionByKeyInDocument = (document, sectionKey) => {{
        if (!document) return null;
        const targetKey = String(sectionKey || "").trim();
        const activeSections = activeSectionsForSortLookup();
        return activeSections.find((section) => String(section?.key || "").trim() === targetKey) || null;
      }};
      const defaultSortStateForSection = (sectionKey) => {{
        const document = currentDocument();
        const section = sectionByKeyInDocument(document, sectionKey);
        const columnLayout = String(section?.columnLayout || "").trim();
        if (columnLayout === "cnc-fiokelo") {{
          return {{ key: "color", direction: "asc" }};
        }}
        return {{ key: "source", direction: "asc" }};
      }};
      const getSectionSortState = (sectionKey) => {{
        const normalizedKey = normalizedSectionSortKey(sectionKey);
        return sectionSortState[normalizedKey] || defaultSortStateForSection(sectionKey);
      }};
      const compareRowsBySort = (leftRow, rightRow, sectionKey) => {{
        const sortState = getSectionSortState(sectionKey);
        if (sortState.key === "source") return 0;
        const leftValue = rowSortValue(leftRow, sortState.key);
        const rightValue = rowSortValue(rightRow, sortState.key);
        let primaryResult = 0;
        if (Array.isArray(leftValue) && Array.isArray(rightValue)) {{
          primaryResult = compareArrays(leftValue, rightValue);
        }} else if (typeof leftValue === "number" && typeof rightValue === "number") {{
          primaryResult = leftValue - rightValue;
        }} else {{
          primaryResult = String(leftValue).localeCompare(String(rightValue), "hu-HU", {{ numeric: true, sensitivity: "base" }});
        }}

        if (primaryResult !== 0) {{
          return sortState.direction === "desc" ? -primaryResult : primaryResult;
        }}

        // Color sort: keep same color grouped, then size descending by default.
        if (sortState.key === "color") {{
          const leftSize = parseSizeParts(rowOrderingField(leftRow, "size") || "");
          const rightSize = parseSizeParts(rowOrderingField(rightRow, "size") || "");
          const section = sectionByKeyInDocument(currentDocument(), sectionKey);
          const columnLayout = String(section?.columnLayout || "").trim();
          const sizeResult =
            columnLayout === "cnc-fiokelo"
              ? compareArrays(leftSize, rightSize)
              : compareArrays(rightSize, leftSize);
          if (sizeResult !== 0) return sizeResult;
        }}
        // Fiókelő default sort: size first, color second.
        if (sortState.key === "size") {{
          const leftColor = normalizeSortText(rowOrderingField(leftRow, "color") || "");
          const rightColor = normalizeSortText(rowOrderingField(rightRow, "color") || "");
          const colorResult = leftColor.localeCompare(rightColor, "hu-HU", {{ numeric: true, sensitivity: "base" }});
          if (colorResult !== 0) return colorResult;
        }}

        let result = 0;
        if (result === 0) {{
          const leftFallback = normalizeSortText(leftRow.code || leftRow.row_id);
          const rightFallback = normalizeSortText(rightRow.code || rightRow.row_id);
          result = leftFallback.localeCompare(rightFallback, "hu-HU", {{ numeric: true, sensitivity: "base" }});
        }}
        return result;
      }};
      const sortedRowsForView = (rows, sectionKey) => {{
        const items = Array.isArray(rows) ? [...rows] : [];
        if (getSectionSortState(sectionKey).key === "source") return items;
        items.sort((leftRow, rightRow) => compareRowsBySort(leftRow, rightRow, sectionKey));
        return items;
      }};
      const sortArrowFor = (sectionKey, sortKey) => {{
        const sortState = getSectionSortState(sectionKey);
        if (sortState.key != sortKey) return "";
        return sortState.direction === "desc" ? "↓" : "↑";
      }};
      const sortButtonMarkup = (sectionKey, sortKey, label) => {{
        const sortState = getSectionSortState(sectionKey);
        const activeClass = sortState.key === sortKey ? " is-active" : "";
        const sortArrowForEscaped = (key, innerSortKey) => {{
          const innerSortState = getSectionSortState(key);
          if (innerSortState.key != innerSortKey) return "";
          return innerSortState.direction === "desc" ? "\\u2193" : "\\u2191";
        }};
        const arrow = sortArrowForEscaped(sectionKey, sortKey);
        return `
          <button class="mfg-sort-head${{activeClass}}" type="button" data-sort-key="${{escapeHtml(sortKey)}}" data-section-key="${{escapeHtml(sectionKey)}}" title="${{escapeHtml(label)}}">
            <span class="mfg-sort-head-label">${{escapeHtml(label)}}</span>
            <span class="mfg-sort-head-arrow">${{escapeHtml(arrow)}}</span>
          </button>
        `;
      }};

      const topfloorHettichActionsMarkup = (group) => {{
        const category = group?.hettichCategory || null;
        if (!category || !topfloorTransferRoute) return "";
        const rows = Array.isArray(group?.rows) ? group.rows : [];
        const ready = rows.length > 0 && rows.every((row) => Boolean(rowStateValue(row)));
        const done = Boolean(category.transferDone);
        return `
          <div class="mfg-topfloor-actions" data-hettich-category="${{escapeHtml(String(category.prdID || ""))}}">
            <div class="mfg-topfloor-button-row">
              ${{done
                ? '<span class="mfg-topfloor-issued">Kész</span>'
                : `<button class="mfg-topfloor-button" type="button" data-hettich-transfer${{ready ? "" : " disabled"}}>Átraktározás</button>`}}
            </div>
          </div>
        `;
      }};
      const topfloorCategoryActionsMarkup = (group) => {{
        if (group?.hettichCategory) return topfloorHettichActionsMarkup(group);
        const category = group?.topfloorCategory || null;
        if (!category || !topfloorBoxRoute) return "";
        const categoryKey = String(category.categoryKey || "");
        const boxId = String(category.boxId || "");
        const boxCreatedBy = String(category.boxCreatedBy || "Err404").trim() || "Err404";
        const createDisabled = category.createEnabled ? "" : " disabled";
        const openDisabled = category.openEnabled ? "" : " disabled";
        const closeDisabled = category.closeEnabled ? "" : " disabled";
        const boxLabel = boxId ? `Doboz: ${{escapeHtml(boxId)}} · ${{escapeHtml(boxCreatedBy)}}` : "Nincs doboz";
        const defaultDescription = String(category.boxDescription || category.defaultBoxDescription || "");
        const isDoneCategory = topfloorCategoryReadyToIssue(group);
        const selectedStorageBox = String(category.storageBoxName || "").trim();
        const issueDisabled = selectedStorageBox && selectedStorageBox !== "Válassz dobozt!" ? "" : " disabled";
        const storageOptions = topfloorStorageBoxTypes.map((item) => `
          <option value="${{escapeHtml(item.name)}}" data-code="${{escapeHtml(item.code)}}" data-id="${{escapeHtml(String(item.id || 0))}}"${{item.name === selectedStorageBox ? " selected" : ""}}>${{escapeHtml(item.name)}}</option>
        `).join("");
        const doneActionMarkup = category.storageBoxIssued
          ? `
              <button class="mfg-topfloor-button" type="button" data-topfloor-action="reprint-label">Címke Újranyomtatása</button>
              <span class="mfg-topfloor-issued">Kiadva</span>
            `
          : `
              <button class="mfg-topfloor-button" type="button" data-topfloor-action="reprint-label">Címke Újranyomtatása</button>
              <button class="mfg-topfloor-button" type="button" data-topfloor-action="issue-storage-box"${{issueDisabled}}>Doboz Kiadása</button>
              <select class="mfg-topfloor-select" data-topfloor-box-type aria-label="Doboz típus">${{storageOptions}}</select>
            `;
        const regularActionMarkup = `
          <button class="mfg-topfloor-button" type="button" data-topfloor-action="create"${{createDisabled}}>Doboz létrehozása</button>
          <button class="mfg-topfloor-button" type="button" data-topfloor-action="open"${{openDisabled}}>Doboz nyitása</button>
          <button class="mfg-topfloor-button" type="button" data-topfloor-action="close"${{closeDisabled}}>Doboz zárása</button>
        `;
        return `
          <div class="mfg-topfloor-actions" data-topfloor-category="${{escapeHtml(categoryKey)}}">
            <div class="mfg-topfloor-box-row">
              <span class="mfg-section-count">${{boxLabel}}</span>
              <input class="mfg-topfloor-description" type="text" value="${{escapeHtml(defaultDescription)}}" data-topfloor-description aria-label="Doboz leírás" />
            </div>
            <div class="mfg-topfloor-button-row">
              ${{category.storageBoxIssued || isDoneCategory ? doneActionMarkup : regularActionMarkup}}
            </div>
          </div>
        `;
      }};
      const topfloorCategoryTitleMarkup = (group) => {{
        if (group?.hettichCategory) {{
          return `<div class="mfg-topfloor-title"><div><span>Termelés:</span> <strong>${{escapeHtml(String(group.hettichCategory.prdID || ""))}}</strong></div></div>`;
        }}
        const category = group?.topfloorCategory || null;
        if (!category) return escapeHtml(group?.label || "");
        const lines = [
          ["Termelés", category.productionID],
          ["Vevő", category.buyer],
          ["Cím", category.location],
          ["Vevő rendelés sz.", category.orderNumber],
          ["Vevő kód", category.buyerID],
          ["Rendelés Típusa", category.orderType],
        ].filter((item) => String(item[1] || "").trim());
        return `
          <div class="mfg-topfloor-title">
            ${{lines.map((item) => `
              <div><span>${{escapeHtml(item[0])}}:</span> <strong>${{escapeHtml(String(item[1] || ""))}}</strong></div>
            `).join("")}}
          </div>
        `;
      }};

      const tabStateClassForRows = (rows, emptyIsDone = false) => {{
        if (!rows.length) return emptyIsDone ? " is-done" : "";
        const states = rows.map((row) => rowStateValue(row));
        if (states.some((state) => !state || state === "mixed")) return "";
        if (states.some((state) => state === "red")) return " is-alert";
        if (states.every((state) => state === "done")) return " is-done";
        if (states.every((state) => isGreenLikeState(state))) return " is-complete";
        return "";
      }};
      const sectionTabStateClass = (section) => {{
        const rows = Array.isArray(section?.rows) ? section.rows : [];
        return tabStateClassForRows(rows);
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
      const cncOverviewOnlySectionsForDocument = (document) => {{
        if (String(document?.key || "") !== "cnc_furas") return [];
        return specialViewsForDocument(document)
          .filter((view) => Boolean(view?.overviewOnly))
          .flatMap((view) => Array.isArray(view?.sections) ? view.sections : [])
          .filter((section) => Array.isArray(section?.rows) && section.rows.length);
      }};
      const appendCncOverviewOnlySections = (document, sections, stateFilter = "") => {{
        const baseSections = Array.isArray(sections) ? sections : [];
        const existingKeys = new Set(baseSections.map((section) => String(section?.key || "")));
        const extraSections = cncOverviewOnlySectionsForDocument(document)
          .filter((section) => !existingKeys.has(String(section?.key || "")))
          .map((section) => {{
            if (!stateFilter) return section;
            return {{
              ...section,
              rows: (Array.isArray(section.rows) ? section.rows : []).filter((row) =>
                stateFilter === "plain" ? !rowStateValue(row) : (stateFilter === "green" ? isReadyGreenState(rowStateValue(row)) : rowStateValue(row) === stateFilter)
              ),
            }};
          }})
          .filter((section) => Array.isArray(section.rows) && section.rows.length);
        return [...baseSections, ...extraSections];
      }};
      const topfloorSectionIsIssued = (section) => Boolean(
        section?.topfloorCategory?.storageBoxIssued || section?.hettichCategory?.transferDone
      );
      const topfloorSectionHasIssuedEdit = (section) =>
        Boolean(section?.topfloorCategory?.hasIssuedRowEdit)
        || (Array.isArray(section?.rows) && section.rows.some((row) => Boolean(row?._editedAfterIssue)));
      const topfloorFilterIssuedSections = (sections, includeIssued = false) =>
        includeIssued
          ? (Array.isArray(sections) ? sections : [])
          : (Array.isArray(sections) ? sections : []).filter((section) => !topfloorSectionIsIssued(section) || topfloorSectionHasIssuedEdit(section));
      const topfloorShipmentSections = (document, options = {{}}) => {{
        const sections = Array.isArray(document?.sections) ? document.sections : [];
        if (String(document?.key || "") !== "topfloor") return sections;
        const shipmentId = topfloorShipmentIdFromKey(currentTopfloorShipmentKey || firstTopfloorShipmentViewKey());
        if (!shipmentId) return [];
        const selectedShipmentKey = currentTopfloorShipmentKey || firstTopfloorShipmentViewKey();
        const shipmentSections = topfloorShipmentKeyIsHettich(selectedShipmentKey)
          ? sections.filter((section) => Boolean(section?.hettichCategory))
          : topfloorShipmentKeyIsAll(selectedShipmentKey)
            ? sections.filter((section) => !section?.hettichCategory)
            : sections.filter((section) => String(section?.topfloorCategory?.shipmentID || "") === shipmentId);
        return topfloorFilterIssuedSections(shipmentSections, Boolean(options?.includeIssued) || topfloorShowIssued);
      }};
      const topfloorShipmentSectionsForKey = (document, shipmentKey, options = {{}}) => {{
        const sections = Array.isArray(document?.sections) ? document.sections : [];
        if (String(document?.key || "") !== "topfloor") return [];
        const shipmentId = topfloorShipmentIdFromKey(shipmentKey);
        if (!shipmentId) return [];
        const shipmentSections = topfloorShipmentKeyIsHettich(shipmentKey)
          ? sections.filter((section) => Boolean(section?.hettichCategory))
          : topfloorShipmentKeyIsAll(shipmentKey)
            ? sections.filter((section) => !section?.hettichCategory)
            : sections.filter((section) => String(section?.topfloorCategory?.shipmentID || "") === shipmentId);
        return topfloorFilterIssuedSections(shipmentSections, Boolean(options?.includeIssued) || topfloorShowIssued);
      }};
      const topfloorShipmentHasIssuedEdit = (document, shipmentKey) =>
        topfloorShipmentSectionsForKey(document, shipmentKey, {{ includeIssued: true }}).some(topfloorSectionHasIssuedEdit);
      const alertSectionsForDocument = (document) => {{
        const sections = Array.isArray(document?.sections) ? [...document.sections] : [];
        for (const collectionKey of ["specialViews", "topfloorShipmentViews"]) {{
          for (const view of (Array.isArray(document?.[collectionKey]) ? document[collectionKey] : [])) {{
            if (Array.isArray(view?.sections)) sections.push(...view.sections);
          }}
        }}
        return Array.from(new Set(sections));
      }};
      const alertRowsForDocument = (document) => Array.from(new Set(
        alertSectionsForDocument(document)
          .flatMap((section) => Array.isArray(section?.rows) ? section.rows : [])
          .filter((row) => Boolean(row?._editedAfterIssue))
      ));
      const syncIssuedEditWarning = () => {{
        const affectedRows = documents.flatMap(alertRowsForDocument);
        const hasNonTopfloorAlert = documents.some((document) =>
          String(document?.key || "") !== "topfloor" && alertRowsForDocument(document).length
        );
        issuedEditWarningNode.hidden = affectedRows.length === 0;
        issuedEditWarningNode.textContent = affectedRows.length
          ? (hasNonTopfloorAlert
              ? `Figyelem: ${{affectedRows.length}} zöldre vagy készre jelölés után adminisztrátor által módosított tétel van. A pirosan kiemelt gyártást és sort ellenőrizni kell.`
              : `Figyelem: ${{affectedRows.length}} dobozba rakás vagy kiadás után adminisztrátor által módosított Anyagraktár-tétel van. A pirosan kiemelt szállítmányt és sort ellenőrizni kell.`)
          : "";
      }};
      const isTopfloorDoneState = (value) => /^\\d{{1,12}}$/.test(String(value || "").trim());
      const topfloorCategoryReadyToIssue = (section) => {{
        const category = section?.topfloorCategory || null;
        const rows = Array.isArray(section?.rows) ? section.rows : [];
        if (!category || category.storageBoxIssued || !String(category.boxId || "").trim() || category.boxOpen || !rows.length) return false;
        return rows.every((row) => isTopfloorDoneState(rowStateValue(row)));
      }};
      const topfloorHettichCategoryReady = (section) => {{
        const rows = Array.isArray(section?.rows) ? section.rows : [];
        return Boolean(section?.hettichCategory) && rows.length > 0 && rows.every((row) => Boolean(rowStateValue(row)));
      }};
      const topfloorSectionComplete = (section) => Boolean(
        section?.topfloorCategory?.storageBoxIssued || section?.hettichCategory?.transferDone
      );
      const topfloorCategoryStateClass = (section) => {{
        if (section?.hettichCategory) {{
          if (section.hettichCategory.transferDone) return " is-topfloor-done";
          return topfloorHettichCategoryReady(section) ? " is-topfloor-open" : "";
        }}
        const category = section?.topfloorCategory || null;
        if (!category || !String(category.boxId || "").trim()) return "";
        if (category.storageBoxIssued) return " is-topfloor-done";
        if (topfloorCategoryReadyToIssue(section)) return " is-topfloor-done";
        if (category.boxOpen) return " is-topfloor-open";
        return " is-topfloor-boxed";
      }};
      const topfloorSectionsComplete = (sections) => {{
        const cleanSections = (Array.isArray(sections) ? sections : []).filter((section) => section?.topfloorCategory || section?.hettichCategory);
        return cleanSections.length > 0 && cleanSections.every((section) => topfloorSectionComplete(section));
      }};
      const topfloorSectionsStateClass = (sections) => topfloorSectionsComplete(sections) ? " is-done" : "";
      const statusFromTabStateClass = (stateClass) => {{
        const text = String(stateClass || "");
        if (text.includes("is-done")) return "done";
        if (text.includes("is-alert")) return "red";
        if (text.includes("is-complete")) return "green";
        return "";
      }};
      const combineAllTabStatuses = (statuses) => {{
        const cleanStatuses = (Array.isArray(statuses) ? statuses : [])
          .map((status) => String(status || "").trim().toLowerCase());
        if (!cleanStatuses.length || cleanStatuses.some((status) => !["red", "green", "done"].includes(status))) return "";
        if (cleanStatuses.some((status) => status === "red")) return "red";
        if (cleanStatuses.every((status) => status === "done")) return "done";
        if (cleanStatuses.every((status) => status === "green" || status === "done")) return "green";
        return "";
      }};
      const allTabStateStatusForDocument = (document, shipmentKey = currentTopfloorShipmentKey) => {{
        if (!document) return "";
        if (String(document?.key || "") === "topfloor") {{
          return combineAllTabStatuses([
            statusFromTabStateClass(topfloorSectionsStateClass(shipmentKey ? topfloorShipmentSectionsForKey(document, shipmentKey) : topfloorShipmentSections(document))),
          ]);
        }}
        const mainKorpuszViews = korpuszMainViews(document);
        if (mainKorpuszViews.length) {{
          return combineAllTabStatuses(
            ["korpusz-osszekeszito", "korpusz-alkatresz-kesz"]
              .map((viewKey) => specialViewForKey(document, viewKey))
              .filter(Boolean)
              .map((view) => {{
                const sections = orderedSectionsForTabs(Array.isArray(view?.sections) ? view.sections : []);
                return statusFromTabStateClass(tabStateClassForRows(sections.flatMap((section) => Array.isArray(section.rows) ? section.rows : []), true));
              }})
          );
        }}
        const overviewSections = overviewSectionsForDocument(document, true);
        return combineAllTabStatuses([
          statusFromTabStateClass(tabStateClassForRows(overviewSections.flatMap((section) => Array.isArray(section.rows) ? section.rows : []))),
        ]);
      }};
      const currentAllTabStateStatus = () => allTabStateStatusForDocument(currentDocument(), currentTopfloorShipmentKey);
      const cachedProductionAllTabStateStatus = (targetProductionNumber) => {{
        const normalizedProductionNumber = String(targetProductionNumber || "").trim();
        if (!normalizedProductionNumber || !currentDocKey) return null;
        const cachedPayload = productionPayloadCache.get(productionCacheKey(currentDocKey, normalizedProductionNumber));
        if (!cachedPayload || !Array.isArray(cachedPayload.documents) || !cachedPayload.documents.length) return null;
        const previousDocuments = documents;
        const previousSelectionState = selectionState;
        const previousProductionNumber = productionNumber;
        const previousDocKey = currentDocKey;
        try {{
          documents = cachedPayload.documents;
          selectionState = Object.assign({{}}, cachedPayload.selectionState || {{}});
          productionNumber = String(cachedPayload.productionNumber || normalizedProductionNumber);
          currentDocKey = String(cachedPayload.currentDocumentKey || previousDocKey);
          const cachedDocument = documents.find((document) => document?.key === currentDocKey) || documents[0] || null;
          return allTabStateStatusForDocument(cachedDocument, "");
        }} finally {{
          documents = previousDocuments;
          selectionState = previousSelectionState;
          productionNumber = previousProductionNumber;
          currentDocKey = previousDocKey;
        }}
      }};
      const topfloorProductionViewKey = (productionId) => `topfloor-production::${{String(productionId || "").trim()}}`;
      const topfloorProductionIdFromViewKey = (key) => {{
        const text = String(key || "").trim();
        return text.startsWith("topfloor-production::") ? text.slice("topfloor-production::".length).trim() : "";
      }};
      const topfloorProductionTabs = (sections) => {{
        const groups = new Map();
        for (const section of (Array.isArray(sections) ? sections : [])) {{
          const productionId = String(section?.topfloorCategory?.productionID || "").trim();
          if (!productionId) continue;
          if (!groups.has(productionId)) groups.set(productionId, []);
          groups.get(productionId).push(section);
        }}
        return Array.from(groups.entries())
          .sort((left, right) => {{
            const leftNum = Number(left[0]);
            const rightNum = Number(right[0]);
            if (Number.isFinite(leftNum) && Number.isFinite(rightNum) && leftNum !== rightNum) return rightNum - leftNum;
            return left[0].localeCompare(right[0], "hu");
          }})
          .map(([productionId, groupSections]) => ({{
            key: topfloorProductionViewKey(productionId),
            label: productionId,
            count: totalQuantityForSections(groupSections),
            sections: groupSections,
            stateClass: topfloorSectionsStateClass(groupSections),
          }}));
      }};
      const topfloorOpenBoxCategory = (document, exceptCategoryKey = "") => {{
        if (String(document?.key || "") !== "topfloor") return null;
        const cleanExcept = String(exceptCategoryKey || "").trim();
        const sections = Array.isArray(document?.sections) ? document.sections : [];
        for (const section of sections) {{
          const category = section?.topfloorCategory || null;
          if (!category || !category.boxOpen) continue;
          if (String(category.categoryKey || "").trim() === cleanExcept) continue;
          return {{
            category,
            label: String(section?.label || "").trim(),
          }};
        }}
        return null;
      }};
      const warnTopfloorOpenBox = (openBox) => {{
        const category = openBox?.category || {{}};
        const boxId = String(category.boxId || "").trim();
        const description = String(category.boxDescription || category.defaultBoxDescription || "").trim();
        const categoryKey = String(category.categoryKey || "").trim();
        const shipmentId = String(category.shipmentID || (categoryKey.split("::")[0] || "")).trim();
        const label = String(openBox?.label || category.categoryKey || "").trim();
        const lines = ["Már van nyitott Anyagraktár doboz."];
        if (shipmentId) lines.push(`Szállítmány: ${{shipmentId}}`);
        if (boxId) lines.push(`Doboz: ${{boxId}}`);
        if (label) lines.push(`Kategória: ${{label}}`);
        if (description) lines.push(`Leírás: ${{description}}`);
        lines.push("Zárd le ezt a dobozt, mielőtt másikat nyitsz.");
        return requestConfirmModal({{
          title: "Nyitott Anyagraktár doboz",
          copy: lines.join("\\n"),
          confirmText: "Vissza",
          singleAction: true,
        }});
      }};
      const topfloorUnissuedDoneBoxCategory = (document) => {{
        if (String(document?.key || "") !== "topfloor") return null;
        const sections = Array.isArray(document?.sections) ? document.sections : [];
        for (const section of sections) {{
          const category = section?.topfloorCategory || null;
          if (!category || category.storageBoxIssued || !topfloorCategoryReadyToIssue(section)) continue;
          return {{
            category,
            label: String(section?.label || "").trim(),
          }};
        }}
        return null;
      }};
      const topfloorGuardBoxPayload = (box) => {{
        const category = box?.category || null;
        if (!category) return null;
        return {{
          category_key: String(category.categoryKey || "").trim(),
          shipment_id: String(category.shipmentID || "").trim(),
          box_id: String(category.boxId || "").trim(),
          label: String(box?.label || category.categoryKey || "").trim(),
          description: String(category.boxDescription || category.defaultBoxDescription || "").trim(),
        }};
      }};
      const warnTopfloorUnissuedDoneBox = (doneBox) => {{
        const category = doneBox?.category || {{}};
        const boxId = String(category.boxId || "").trim();
        const description = String(category.boxDescription || category.defaultBoxDescription || "").trim();
        const categoryKey = String(category.categoryKey || "").trim();
        const shipmentId = String(category.shipmentID || (categoryKey.split("::")[0] || "")).trim();
        const label = String(doneBox?.label || category.categoryKey || "").trim();
        const lines = ["Van lezárt, de még ki nem adott Anyagraktár doboz."];
        if (shipmentId) lines.push(`Szállítmány: ${{shipmentId}}`);
        if (boxId) lines.push(`Doboz: ${{boxId}}`);
        if (label) lines.push(`Kategória: ${{label}}`);
        if (description) lines.push(`Leírás: ${{description}}`);
        lines.push("Add ki ezt a dobozt, mielőtt másik dobozműveletet indítasz.");
        return requestConfirmModal({{
          title: "Kiadatlan Anyagraktár doboz",
          copy: lines.join("\\n"),
          confirmText: "Vissza",
          singleAction: true,
        }});
      }};

      const buildGroupsForView = (document) => {{
        if (!document) return [];
        if (String(document?.key || "") === "topfloor") {{
          const sections = topfloorShipmentSections(document);
          const productionId = topfloorProductionIdFromViewKey(currentViewKey);
          if (productionId) {{
            return sections.filter((section) => String(section?.topfloorCategory?.productionID || "") === productionId);
          }}
          if (currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain") {{
            return sections.filter((section) =>
              (Array.isArray(section.rows) ? section.rows : []).some((row) =>
                currentViewKey === "plain" ? !rowStateValue(row) : (currentViewKey === "green" ? isReadyGreenState(rowStateValue(row)) : rowStateValue(row) === currentViewKey)
              )
            );
          }}
          return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
        }}
        const currentSpecialView = specialViewForKey(document, currentViewKey);
        if (String(document?.key || "") === "korpusz_osszekeszites" && currentSpecialView) {{
          const sections = orderedSectionsForTabs(Array.isArray(currentSpecialView.sections) ? currentSpecialView.sections : []);
          if (currentSubcategoryKey === "all") {{
            return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
          }}
          if (currentSubcategoryKey === "green" || currentSubcategoryKey === "red" || currentSubcategoryKey === "plain") {{
            return sections
              .map((section) => ({{
                ...section,
                rows: (Array.isArray(section.rows) ? section.rows : []).filter((row) =>
                  currentSubcategoryKey === "plain" ? !rowStateValue(row) : (currentSubcategoryKey === "green" ? isReadyGreenState(rowStateValue(row)) : rowStateValue(row) === currentSubcategoryKey)
                ),
              }}))
              .filter((section) => section.rows.length);
          }}
          if (layoutMode === "double") {{
            const pairKey = pairedSectionKey({{ sections }}, currentSubcategoryKey);
            return [currentSubcategoryKey, pairKey]
              .filter((key, index, items) => key && items.indexOf(key) === index)
              .map((key) => sections.find((section) => section.key === key))
              .filter((section) => section && Array.isArray(section.rows) && section.rows.length);
          }}
          const selectedSection = sections.find((section) => section.key === currentSubcategoryKey);
          return selectedSection ? [selectedSection] : [];
        }}
        if (currentSpecialView) {{
          let specialSections = Array.isArray(currentSpecialView.sections) ? currentSpecialView.sections : [];
          if (currentSubcategoryKey !== "all") {{
            specialSections = specialSections.filter((section) => {{
              const label = String(section?.label || "");
              const sizeLabel = label.includes("·") ? label.split("·", 1)[0].trim() : label.trim();
              return sizeLabel === currentSubcategoryKey;
            }});
          }}
          specialSections = appendCncOverviewOnlySections(document, specialSections);
          if (!specialViewUsesRedFilter(currentSpecialView)) {{
            return specialSections;
          }}
          return specialSections
            .map((section) => ({{
              ...section,
              rows: (Array.isArray(section.rows) ? section.rows : []).flatMap((row) => {{
                if (String(currentSpecialView?.key || "") === "pantolo-missing" && Array.isArray(row?.childUnitStateKeys)) {{
                  const redChildKeys = row.childUnitStateKeys.filter((key) => selectionState[String(key || "")] === "red");
                  if (!redChildKeys.length) return [];
                  return [{{ ...row, childUnitStateKeys: redChildKeys, quantity: redChildKeys.length, meValue: redChildKeys.length }}];
                }}
                return rowStateValue(row) === "red" ? [row] : [];
              }}),
            }}))
            .filter((section) => section.rows.length);
        }}
        const overviewSections = overviewSectionsForDocument(document);
        const sections = documentUsesSingleColumnOverview(document) && String(document?.key || "") === "cnc_furas"
          ? appendCncOverviewOnlySections(document, overviewSections)
          : orderedSectionsForTabs(overviewSections);
        if (documentUsesSingleColumnOverview(document) && (currentViewKey === "all" || currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain" || currentViewKey === "mixed")) {{
          if (currentViewKey === "all") {{
            return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
          }}
          if (currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain" || currentViewKey === "mixed") {{
            return appendCncOverviewOnlySections(document, sections, currentViewKey)
              .map((section) => ({{
                ...section,
                rows: (Array.isArray(section.rows) ? section.rows : []).filter((row) =>
                  currentViewKey === "plain" ? !rowStateValue(row) : (currentViewKey === "green" ? isReadyGreenState(rowStateValue(row)) : rowStateValue(row) === currentViewKey)
                ),
              }}))
              .filter((section) => section.rows.length);
          }}
          return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
        }}
        if (false && documentUsesSingleColumnOverview(document) && (currentViewKey === "all" || currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain")) {{
          const combinedRows = sections.flatMap((section) => Array.isArray(section.rows) ? section.rows : []).filter((row) => {{
            if (currentViewKey === "plain") return !rowStateValue(row);
            if (currentViewKey === "green") return isReadyGreenState(rowStateValue(row));
            if (currentViewKey === "red") return rowStateValue(row) === "red";
            return true;
          }});
          if (!combinedRows.length) return [];
          const combinedLabel =
            currentViewKey === "plain" ? "Sima front tételek" :
            currentViewKey === "green" ? "Zöld front tételek" :
            currentViewKey === "red" ? "Piros front tételek" :
            String(document.label || "Front összekészítés");
          return [{{
            key: `overview-${{currentViewKey}}`,
            label: combinedLabel,
            rows: combinedRows,
          }}];
        }}
        if (layoutMode === "double" && !isSpecialViewKey(currentViewKey)) {{
          const selectedKeys = [currentViewKey, secondaryViewKey].filter((key, index, items) => key && items.indexOf(key) === index);
          return selectedKeys
            .map((key) => sections.find((section) => section.key === key))
            .filter((section) => section && Array.isArray(section.rows) && section.rows.length);
        }}
        if (currentViewKey === "all") {{
          return sections.filter((section) => Array.isArray(section.rows) && section.rows.length);
        }}
        if (currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "plain" || currentViewKey === "mixed") {{
          return sections
            .map((section) => ({{
              key: section.key,
              label: section.label,
              rows: (Array.isArray(section.rows) ? section.rows : []).filter((row) =>
                currentViewKey === "plain" ? !rowStateValue(row) : (currentViewKey === "green" ? isReadyGreenState(rowStateValue(row)) : rowStateValue(row) === currentViewKey)
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
          subsectionTabsNode.innerHTML = "";
          subsectionTabsNode.style.display = "none";
          return;
        }}
        if (String(document?.key || "") === "topfloor") {{
          const sections = topfloorShipmentSections(document);
          const productionTabs = topfloorProductionTabs(sections);
          const validKeys = new Set(["all", "plain", "green", "red", ...productionTabs.map((item) => item.key)]);
          if (!validKeys.has(currentViewKey)) {{
            currentViewKey = "all";
          }}
          subsectionTabsNode.innerHTML = "";
          subsectionTabsNode.style.display = "none";
          const tabs = [
            {{ key: "all", label: "Összes", count: countRowsInSections(sections), stateClass: topfloorSectionsStateClass(sections) }},
            {{ key: "plain", label: "Simák", count: countRowsInSections(sections, (row) => !rowStateValue(row)), stateClass: "" }},
            {{ key: "green", label: "Nyitot", count: countRowsInSections(sections, (row) => isReadyGreenState(rowStateValue(row))), stateClass: "" }},
            {{ key: "red", label: "Zártak", count: countRowsInSections(sections, (row) => rowStateValue(row) === "red"), stateClass: "" }},
            ...productionTabs,
          ];
          sectionTabsNode.innerHTML = tabs.map((item) => `
            <button class="mfg-section-tab${{item.key === currentViewKey ? " is-active" : ""}}${{item.stateClass || ""}}" type="button" data-view-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
              <strong>${{escapeHtml(item.label)}}</strong>
              <small>${{item.count}}</small>
            </button>
          `).join("");
          return;
        }}
        const mainKorpuszViews = korpuszMainViews(document);
        if (mainKorpuszViews.length) {{
          if (!mainKorpuszViews.some((item) => item.key === currentViewKey)) {{
            currentViewKey = String(mainKorpuszViews[0]?.key || "all");
          }}
          const currentKorpuszView = specialViewForKey(document, currentViewKey) || mainKorpuszViews[0];
          const currentKorpuszSections = orderedSectionsForTabs(Array.isArray(currentKorpuszView?.sections) ? currentKorpuszView.sections : []);
          const korpuszAllRows = currentKorpuszSections.flatMap((section) => Array.isArray(section.rows) ? section.rows : []);
          const korpuszSubTabs = [
            {{ key: "all", label: "Összes", count: countRowsInSections(currentKorpuszSections), stateClass: tabStateClassForRows(korpuszAllRows, korpuszViewEmptyIsDone(currentKorpuszView)) }},
            {{ key: "plain", label: "Simák", count: countRowsInSections(currentKorpuszSections, (row) => !rowStateValue(row)), stateClass: "" }},
            {{ key: "green", label: "Zöldek", count: countRowsInSections(currentKorpuszSections, (row) => isReadyGreenState(rowStateValue(row))), stateClass: "" }},
            {{ key: "red", label: "Pirosak", count: countRowsInSections(currentKorpuszSections, (row) => rowStateValue(row) === "red"), stateClass: "" }},
            ...currentKorpuszSections.map((section) => ({{
              key: section.key,
              label: section.label,
              count: totalQuantityForRows(section?.rows),
              stateClass: sectionTabStateClass(section),
            }})),
          ];
          if (!korpuszSubTabs.some((item) => item.key === currentSubcategoryKey)) {{
            currentSubcategoryKey = "all";
          }}
          sectionTabsNode.innerHTML = mainKorpuszViews.map((item) => `
            <button class="mfg-section-tab${{item.key === currentViewKey ? " is-active" : ""}}${{tabStateClassForRows(Array.isArray(item?.sections) ? item.sections.flatMap((section) => Array.isArray(section.rows) ? section.rows : []) : [], korpuszViewEmptyIsDone(item))}}" type="button" data-view-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
              <strong>${{escapeHtml(item.label)}}</strong>
              <small>${{totalQuantityForSections(item?.sections)}}</small>
            </button>
          `).join("");
          subsectionTabsNode.style.display = "";
          subsectionTabsNode.innerHTML = korpuszSubTabs.map((item) => `
            <button class="mfg-subsection-tab${{item.key === currentSubcategoryKey ? " is-active" : (layoutMode === "double" && item.key !== "all" && item.key === pairedSectionKey({{ sections: currentKorpuszSections }}, currentSubcategoryKey) ? " is-secondary" : "")}}${{item.stateClass || ""}}" type="button" data-subcategory-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
              <strong>${{escapeHtml(item.label)}}</strong>
              <small>${{item.count}}</small>
            </button>
          `).join("");
          return;
        }}
        const currentSpecialView = specialViewForKey(document, currentViewKey);
        const overviewSections = overviewSectionsForDocument(document, true);
        const stateOverviewSections = overviewSections;
        const usesGroupedMixedView = documentUsesGroupedQuantityRows(document);
        const sections = (currentSpecialView && !specialViewUsesRedFilter(currentSpecialView) && Array.isArray(currentSpecialView.sections))
          ? currentSpecialView.sections
          : overviewSections;
        const documentSpecialViews = specialViewsForDocument(document);
        const specialTabs = [
          {{ key: "all", label: "Összes", count: countRowsInSections(overviewSections), stateClass: tabStateClassForRows(overviewSections.flatMap((section) => Array.isArray(section.rows) ? section.rows : [])) }},
          {{ key: "plain", label: "Simák", count: countRowsInSections(stateOverviewSections, (row) => !rowStateValue(row)), stateClass: "" }},
          {{ key: "green", label: "Zöldek", count: countRowsInSections(stateOverviewSections, (row) => isReadyGreenState(rowStateValue(row))), stateClass: "" }},
          {{ key: "red", label: "Pirosak", count: countRowsInSections(stateOverviewSections, (row) => rowStateValue(row) === "red"), stateClass: "" }},
          ...(usesGroupedMixedView ? [{{ key: "mixed", label: "Vegyes", count: countRowsInSections(stateOverviewSections, (row) => rowStateValue(row) === "mixed"), stateClass: "" }}] : []),
          ...documentSpecialViews.filter((view) => !Boolean(view?.hideTab)).map((view) => {{
            const viewSections = Array.isArray(view?.sections) ? view.sections : [];
            return {{
              key: String(view?.key || ""),
              label: String(view?.label || ""),
              count: specialViewUsesRedFilter(view)
                ? countRowsInSections(viewSections, (row) => rowStateValue(row) === "red")
                : totalQuantityForSections(viewSections),
              stateClass: specialViewUsesRedFilter(view)
                ? ""
                : tabStateClassForRows(viewSections.flatMap((section) => Array.isArray(section.rows) ? section.rows : [])),
            }};
          }}),
        ];
        if (documentUsesSingleColumnOverview(document)) {{
          sectionTabsNode.innerHTML = specialTabs.map((item) => `
            <button class="mfg-section-tab${{item.key === currentViewKey ? " is-active" : ""}}${{item.stateClass || ""}}" type="button" data-view-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
              <strong>${{escapeHtml(item.label)}}</strong>
              <small>${{item.count}}</small>
            </button>
          `).join("");
          const subcategories = frontSubcategoriesForView(document, currentViewKey);
          if (!subcategories.length) {{
            currentSubcategoryKey = "all";
            subsectionTabsNode.innerHTML = "";
            subsectionTabsNode.style.display = "none";
          }} else {{
            if (!["all", ...subcategories.map((item) => item.key)].includes(currentSubcategoryKey)) {{
              currentSubcategoryKey = "all";
            }}
            subsectionTabsNode.style.display = "";
            subsectionTabsNode.innerHTML = [
              {{ key: "all", label: "Összes méret", count: subcategories.reduce((total, item) => total + Number(item.count || 0), 0) }},
              ...subcategories,
            ].map((item) => `
              <button class="mfg-subsection-tab${{item.key === currentSubcategoryKey ? " is-active" : ""}}" type="button" data-subcategory-key="${{escapeHtml(item.key)}}" title="${{escapeHtml(item.label)}}">
                <strong>${{escapeHtml(item.label)}}</strong>
                <small>${{item.count}}</small>
              </button>
            `).join("");
          }}
          return;
        }}
        subsectionTabsNode.innerHTML = "";
        subsectionTabsNode.style.display = "none";
        const sectionTabs = sections.map((section) => ({{
          key: section.key,
          label: section.label,
          count: totalQuantityForRows(section?.rows),
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
        const document = currentDocument();
        const currentSpecialView = specialViewForKey(document, currentViewKey);
        const isOverviewMode = currentViewKey === "all" || currentViewKey === "plain" || currentViewKey === "green" || currentViewKey === "red" || currentViewKey === "mixed" || Boolean(currentSpecialView);
        const isPantoloDocument = String(document?.key || "") === "pantolas";
        const isSplitMode = layoutMode === "double" && groups.length > 1 && (
          !isSpecialViewKey(currentViewKey) ||
          (String(document?.key || "") === "korpusz_osszekeszites" && Boolean(currentSpecialView) && !["all", "plain", "green", "red", "mixed"].includes(currentSubcategoryKey))
        );
        const useSingleColumnOverview = documentUsesSingleColumnOverview(document) && isOverviewMode;
        contentNode.classList.toggle("is-overview", isOverviewMode);
        contentNode.classList.toggle("is-single-column-overview", useSingleColumnOverview);
        contentNode.classList.toggle("is-split", isSplitMode);
        if (!groups.length) {{
          const hasActiveSearch = documentUsesSearch(document) && activeSearchTerms().length > 0;
          const emptyLabel = hasActiveSearch
            ? "A keresesre nincs talalat."
            : currentSpecialView
            ? `${{currentSpecialView.label}} nézetben nincs megjeleníthető sor.`
            : currentViewKey === "green"
              ? "Még nincs zöldre jelölt sor."
              : currentViewKey === "red"
                ? "Még nincs pirosra jelölt sor."
                : currentViewKey === "mixed"
                  ? "Még nincs vegyes állapotú csoport."
                  : currentViewKey === "plain"
                    ? "Minden sor kapott már kijelölést."
                    : String(document?.placeholderMessage || "Ehhez a nézethez nincs megjeleníthető sor.");
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
          const showSectionHeader = isOverviewMode || isSplitMode || (String(document?.key || "") === "topfloor" && (group?.topfloorCategory || group?.hettichCategory));
          const hideBarcode = documentHidesBarcode(document);
          const hideSideTypeColumn = Boolean(group?.hideSideTypeColumn);
          const columnLayout = groupColumnLayout(group);
          const isCncDocument = String(document?.key || "") === "cnc_furas";
          const showPartialColumn = isCncDocument;
          const effectiveHideBarcode = hideBarcode || showPartialColumn;
          const showPantoloExpanderColumn = documentUsesGroupedQuantityRows(document) && rowUsesGroupedQuantity({{ columnLayout }});
          const isPantoloLayout = columnLayout === "pantolo";
          const tableHeadClass = columnLayout === "cnc-lower"
            ? " is-cnc-lower"
            : columnLayout === "cnc-upper"
              ? " is-cnc-upper"
              : columnLayout === "cnc-fiokelo"
                ? " is-cnc-fiokelo"
              : columnLayout === "pantolo"
                ? " is-pantolo"
              : columnLayout === "front-standard"
              ? (" is-front-standard" + (effectiveHideBarcode ? " is-no-barcode" : ""))
              : columnLayout === "topfloor"
              ? ` is-topfloor${{group?.hettichCategory ? " is-hettich" : ""}}`
            : effectiveHideBarcode
              ? " is-no-barcode"
              : "";
          const expanderClass = showPantoloExpanderColumn ? " is-with-expander" : "";
          const rowClass = columnLayout === "cnc-lower"
            ? " is-cnc-lower"
            : columnLayout === "cnc-upper"
              ? " is-cnc-upper"
              : columnLayout === "cnc-fiokelo"
                ? " is-cnc-fiokelo"
              : columnLayout === "pantolo"
                ? " is-pantolo"
              : columnLayout === "front-standard"
                ? (" is-front-standard" + (effectiveHideBarcode ? " is-no-barcode" : ""))
              : columnLayout === "topfloor"
                ? ` is-topfloor${{group?.hettichCategory ? " is-hettich" : ""}}`
              : effectiveHideBarcode
                ? " is-no-barcode"
                : "";
          const totalQuantity = (Array.isArray(group.rows) ? group.rows : []).reduce((sum, row) => sum + Number(row?.quantity || 0), 0);
          const sectionTitleMarkup = String(document?.key || "") === "topfloor" && (group?.topfloorCategory || group?.hettichCategory)
            ? topfloorCategoryTitleMarkup(group)
            : isPantoloLayout
              ? pantoloCategoryLabelMarkup(group.label)
              : escapeHtml(group.label);
          const topfloorActionsMarkup = String(document?.key || "") === "topfloor" ? topfloorCategoryActionsMarkup(group) : "";
          const headMarkup = showSectionHeader
            ? `
              <div class="mfg-section-head">
                <div class="mfg-section-title">${{sectionTitleMarkup}}</div>
                ${{topfloorActionsMarkup || `<div class="mfg-section-count">${{totalQuantity}} db</div>`}}
              </div>
            `
            : "";
          const tableHeadExtraClass = `${{showPartialColumn ? " is-with-partial" : ""}}${{expanderClass}}`;
          const tableHeadMarkup = columnLayout === "topfloor"
            ? ""
            : columnLayout === "cnc-lower"
            ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "Megnevezés")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "drawer_drill", "Fióksín fúrás")}}
                  ${{sortButtonMarkup(group.key, "side_type", "Oldal típus")}}
                  ${{sortButtonMarkup(group.key, "edge", "Élzárás")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Menny.")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                </div>
              `
            : columnLayout === "cnc-upper"
              ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "Megnevezés")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "side_type", "Oldal típus")}}
                  ${{sortButtonMarkup(group.key, "hardware_type", "Vasalat típusa")}}
                  ${{sortButtonMarkup(group.key, "edge", "Élzárás")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Menny.")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                </div>
              `
            : columnLayout === "cnc-fiokelo"
              ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "model", "Modell")}}
                  ${{sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "netfront_color", "NettFrontos szín")}}
                  ${{sortButtonMarkup(group.key, "drill", "Furat")}}
                  ${{sortButtonMarkup(group.key, "drawer_type", "Fióktípus")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Menny.")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                </div>
              `
            : columnLayout === "pantolo"
              ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{currentViewKey === "pantolo-missing" ? "<span>Leírás</span>" : sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "color23", "Szín 2/3")}}
                  ${{sortButtonMarkup(group.key, "pant_type", "Pánt típus")}}
                  ${{sortButtonMarkup(group.key, "model", "Modell")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "handle_drill", "Fogantyú furat")}}
                  ${{sortButtonMarkup(group.key, "handle_type", "Fogantyú típus")}}
                  ${{sortButtonMarkup(group.key, "opening_dir", "Nyitás irány")}}
                  ${{sortButtonMarkup(group.key, "door_type", "Ajtó típus")}}
                  ${{sortButtonMarkup(group.key, "quantity", "ME")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                  ${{showPantoloExpanderColumn ? "<span></span>" : ""}}
                </div>
              `
            : columnLayout === "topfloor"
              ? (group?.hettichCategory ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "itmDescription")}}
                  ${{sortButtonMarkup(group.key, "code", "itmItemNumber")}}
                  ${{sortButtonMarkup(group.key, "quantity", "oriReqQty")}}
                </div>
              ` : `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "Leírás")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Db")}}
                  ${{sortButtonMarkup(group.key, "code", "Vonalkód")}}
                </div>
              `)
            : columnLayout === "front-standard"
              ? `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "Megnevezés")}}
                  ${{sortButtonMarkup(group.key, "model", "Modell")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Menny.")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                  ${{effectiveHideBarcode ? "" : sortButtonMarkup(group.key, "code", "Vonalkód")}}
                  ${{showPantoloExpanderColumn ? "<span></span>" : ""}}
                </div>
              `
            : `
                <div class="mfg-table-head${{tableHeadClass}}${{tableHeadExtraClass}}">
                  ${{sortButtonMarkup(group.key, "name", "Megnevezés")}}
                  ${{sortButtonMarkup(group.key, "size", "Méret")}}
                  ${{sortButtonMarkup(group.key, "color", "Szín")}}
                  ${{sortButtonMarkup(group.key, "edge", "Él")}}
                  ${{sortButtonMarkup(group.key, "quantity", "Menny.")}}
                  ${{showPartialColumn ? "<span>Hiányzik</span>" : ""}}
                  ${{effectiveHideBarcode ? "" : sortButtonMarkup(group.key, "code", "Vonalkód")}}
                </div>
              `;
          const topfloorRowsLocked = String(document?.key || "") === "topfloor" && group?.topfloorCategory && !Boolean(group.topfloorCategory.boxOpen);
          const rowMarkup = sortedRowsForView(group.rows, group.key).map((row) => {{
            const rowState = rowStateValue(row);
            const rowStateClass = String(document?.key || "") === "topfloor" && isTopfloorDoneState(rowState)
              ? " is-done"
              : (rowState ? ` is-${{escapeHtml(rowState)}}` : "");
            const issuedEditAlert = Boolean(row?._editedAfterIssue);
            const issuedEditClass = issuedEditAlert ? " is-issued-edited" : "";
            const partialKey = rowStateKey(row);
            const partialValue = showPartialColumn && rowState === "red" ? String(partialQuantityState[partialKey] || "") : "";
            const partialMarkup = showPartialColumn
              ? (rowState === "red"
                  ? `<div class="mfg-row-partial"><input class="mfg-row-partial-input" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="4" value="${{escapeHtml(partialValue)}}" placeholder="db" data-partial-input data-partial-key="${{escapeHtml(partialKey)}}" data-row-production="${{escapeHtml(rowProductionNumber(row))}}" /></div>`
                  : `<div class="mfg-row-partial-empty"></div>`)
              : "";
            const detailText = row.detail || "";
            const detailWasEdited = rowFieldWasEdited(row, "detail");
            const subtitleMarkup = (!row.hideSubtitle || detailWasEdited) && detailText
              ? `<div class="mfg-row-subtitle">${{displayRowField(row, "detail", "")}}</div>`
              : "";
            const glassBadgeMarkup = row.isGlass ? `<span class="mfg-row-badge is-glass">Üveges</span>` : "";
            const pullOutBadgeMarkup = row.isPullOut ? `<span class="mfg-row-badge is-pullout">Alsó Kihúzható</span>` : "";
            const traitBadgeMarkup = row.frontTrait === "Blende" ? `<span class="mfg-row-badge is-curved">Blende${{rowEditedMarker(row, "frontTrait")}}</span>` : "";
            const curvedBadgeMarkup = row.isCurved ? `<span class="mfg-row-badge is-curved">Íves</span>` : "";
            const modelToneClass = row.modelTone ? ` is-model-${{escapeHtml(String(row.modelTone))}}` : "";
            const modelBadgeMarkup = row.modelLabel
              ? `<span class="mfg-row-badge${{modelToneClass}}">${{displayRowField(row, "modelLabel")}}</span>`
              : "";
            const fiokeloDrillValue = String(row.drillLabel || "-");
            const fiokeloDrawerTypeValue = String(row.drawerType || "-");
            const fiokeloDrillMarkup = fiokeloDrillValue === "Nincs"
              ? `<span class="is-pill-black">${{displayRowField(row, "drillLabel")}}</span>`
              : `<span>${{displayRowField(row, "drillLabel")}}</span>`;
            const fiokeloDrawerTypeMarkup = fiokeloDrawerTypeValue === "HE"
              ? `<span class="is-pill-black">${{displayRowField(row, "drawerType")}}</span>`
              : `<span>${{displayRowField(row, "drawerType")}}</span>`;
            const cncUpperSizeMarkup = row.markSizeBlack
              ? `<span class="is-pill-black">${{displayRowField(row, "size", "Méret nélkül")}}</span>`
              : `<span class="is-size">${{displayRowField(row, "size", "Méret nélkül")}}</span>`;
            const cncUpperSideTypeMarkup = row.markSideTypeBlack
              ? `<span class="is-pill-black">${{displayRowField(row, "side_type")}}</span>`
              : `<span>${{displayRowField(row, "side_type")}}</span>`;
            const pantoloNormalizeMarkText = (value) =>
              String(value || "")
                .trim()
                .toLocaleLowerCase("hu-HU")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ");
            const pantoloCellClass = (baseClass, tone) =>
              [baseClass, tone ? "is-pantolo-mark" : "", tone ? `is-pantolo-${{tone}}` : ""]
                .filter(Boolean)
                .join(" ");
            const pantoloHandleDrillText = pantoloNormalizeMarkText(row.handleDrill);
            const pantoloOpeningText = pantoloNormalizeMarkText(row.openingDir);
            const pantoloDoorText = pantoloNormalizeMarkText(row.doorType);
            const pantoloPantText = pantoloNormalizeMarkText(row.pantType);
            const pantoloDoorIsCorner = pantoloDoorText.includes("sarok") || pantoloDoorText.includes("sar.") || pantoloDoorText === "fsl";
            const pantoloDoorIsKam = pantoloDoorText.includes("kam.");
            const pantoloPantIsSpecial =
              pantoloPantText.includes("3d") ||
              pantoloPantText.includes("hutos") ||
              pantoloPantText.includes("hettich");
            let pantoloPantMark = "";
            let pantoloHandleDrillMark = "";
            let pantoloOpeningMark = "";
            let pantoloDoorMark = "";
            if (pantoloHandleDrillText === "nincs") {{
              pantoloHandleDrillMark = "dark-green";
            }}
            if (pantoloOpeningText === "nincs") {{
              pantoloOpeningMark = "dark-green";
              pantoloDoorMark = "dark-green";
            }} else if (pantoloOpeningText === "felnyilo") {{
              pantoloOpeningMark = "lime";
              pantoloDoorMark = "lime";
            }}
            if (pantoloDoorIsCorner) {{
              pantoloPantMark = "yellow";
              pantoloOpeningMark = "yellow";
              pantoloDoorMark = "yellow";
            }}
            if (pantoloDoorIsKam) {{
              pantoloDoorMark = "orange";
            }}
            if (pantoloPantIsSpecial) {{
              pantoloPantMark = "pink";
            }}
            const pantoloIsGroup = isPantoloGroupedRow(row);
            const pantoloGroupExpanded = pantoloIsGroup && expandedPantoloGroups.has(rowStateKey(row));
            const pantoloGroupOpening = pantoloGroupExpanded && openingPantoloGroups.has(rowStateKey(row));
            const pantoloGroupSourceRowIds = pantoloIsGroup
              ? Array.from({{ length: pantoloQuantity(row) }}, (_item, index) => childUnitStorageKey(row, index))
              : [];
            const sourceRowIdsForRow = pantoloIsGroup
              ? Array.from(new Set([...(Array.isArray(row.sourceRowIds) ? row.sourceRowIds : []), ...pantoloGroupSourceRowIds]))
              : (Array.isArray(row.sourceRowIds) ? row.sourceRowIds : []);
            const pantoloExpandMarkup = pantoloIsGroup
              ? `<span class="mfg-pantolo-expand" role="button" tabindex="0" data-pantolo-expand data-state-key="${{escapeHtml(rowStateKey(row))}}" aria-label="${{pantoloGroupExpanded ? "Bezárás" : "Kinyitás"}}">${{pantoloGroupExpanded ? "\\u25B2" : "\\u25BC"}}</span>`
              : `<span class="mfg-pantolo-expand is-empty" aria-hidden="true"></span>`;
            const pantoloCellsMarkup = (displayRow, quantityText, expandMarkup, rowPartialMarkup = "") => `
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", "")}}">${{currentViewKey === "pantolo-missing" ? displayRowField(displayRow, "missingDescription", "-") : displayRowField(displayRow, "color23")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", pantoloPantMark)}}">${{displayRowField(displayRow, "pantType")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("is-size", "")}}">${{displayRowField(displayRow, "size")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", pantoloHandleDrillMark)}}">${{displayRowField(displayRow, "handleDrill")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", "")}}">${{displayRowField(displayRow, "handleType")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", pantoloOpeningMark)}}">${{displayRowField(displayRow, "openingDir")}}</span></div>
              <div class="mfg-row-meta"><span class="${{pantoloCellClass("", pantoloDoorMark)}}">${{displayRowField(displayRow, "doorType")}}</span></div>
              <div class="mfg-row-meta"><span class="is-pill-black">${{escapeHtml(quantityText)}}</span></div>
              ${{rowPartialMarkup}}
              ${{showPantoloExpanderColumn ? `<div class="mfg-pantolo-expand-cell">${{expandMarkup}}</div>` : ""}}
            `;
            const frontCellsMarkup = (displayRow, quantityText, expandMarkup, rowPartialMarkup = "") => `
              <div class="mfg-row-main">
                <div class="mfg-row-title">${{displayRowField(displayRow, "name", "Névtelen sor")}}${{glassBadgeMarkup}}${{pullOutBadgeMarkup}}${{traitBadgeMarkup}}${{curvedBadgeMarkup}}</div>
                ${{subtitleMarkup}}
              </div>
              <div class="mfg-row-meta is-model${{String(displayRow.modelLabel || "").trim().toLowerCase() === "laura" ? " is-laura-model" : ""}}"><span>${{displayRowField(displayRow, "modelLabel")}}</span></div>
              <div class="mfg-row-meta"><span class="is-size">${{displayRowField(displayRow, "size", "Méret nélkül")}}</span></div>
              <div class="mfg-row-meta"><span class="is-color">${{displayRowField(displayRow, "color", "Szín nélkül")}}</span></div>
              <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(quantityText)}} db</div></div>
              ${{rowPartialMarkup}}
              ${{
                effectiveHideBarcode
                  ? ""
                  : `
                      <div class="mfg-row-barcode-wrap">
                        <div class="mfg-row-code">${{escapeHtml(displayRow.code || "Kód nélkül")}}</div>
                      </div>
                    `
              }}
              ${{showPantoloExpanderColumn ? `<div class="mfg-pantolo-expand-cell">${{expandMarkup}}</div>` : ""}}
            `;
            const groupedQuantityCellsMarkup = (displayRow, quantityText, expandMarkup, rowPartialMarkup = "") =>
              columnLayout === "front-standard"
                ? frontCellsMarkup(displayRow, quantityText, expandMarkup, rowPartialMarkup)
                : pantoloCellsMarkup(displayRow, quantityText, expandMarkup, rowPartialMarkup);
            const pantoloChildRowsMarkup = pantoloGroupExpanded
              ? Array.from({{ length: pantoloQuantity(row) }}, (_item, unitIndex) => {{
                  const unitRowId = childUnitRowId(row, unitIndex);
                  const unitStateKey = childUnitStateKey(row, unitIndex);
                  const unitStorageKey = childUnitStorageKey(row, unitIndex);
                  const unitState = childUnitState(row, unitIndex);
                  const unitRow = {{
                    ...row,
                    row_id: unitRowId,
                    state_key: unitStateKey,
                    state_storage_key: unitStorageKey,
                    quantity: 1,
                    meValue: 1,
                    isPantoloUnit: true,
                    inheritedState: unitState,
                  }};
                  const unitPartialMarkup = showPartialColumn ? `<div class="mfg-row-partial-empty"></div>` : "";
                  const lastUnitClass = unitIndex === pantoloQuantity(row) - 1 ? " is-last-unit" : "";
                  return `
                    <button class="mfg-row${{rowClass}}${{expanderClass}} is-pantolo-unit${{lastUnitClass}}${{pantoloGroupOpening ? " is-opening" : ""}}${{showPartialColumn ? " is-with-partial" : ""}}${{unitState ? ` is-${{unitState}}` : ""}}" type="button" data-mfg-row data-pantolo-unit data-pantolo-state="${{escapeHtml(unitState)}}" data-pantolo-parent-row-id="${{escapeHtml(row.row_id)}}" data-row-id="${{escapeHtml(unitRowId)}}" data-row-production="${{escapeHtml(rowProductionNumber(row))}}" data-state-key="${{escapeHtml(unitStateKey)}}" data-state-storage-key="${{escapeHtml(rowStorageKey(unitRow))}}" data-source-row-ids="">
                      ${{groupedQuantityCellsMarkup(unitRow, pantoloQuantityText(unitRow), `<span class="mfg-pantolo-expand is-empty" aria-hidden="true"></span>`, unitPartialMarkup)}}
                    </button>
                  `;
                }}).join("")
              : "";
            return `
              <button class="mfg-row${{rowClass}}${{expanderClass}}${{pantoloIsGroup ? " is-pantolo-group" : ""}}${{pantoloGroupExpanded ? " is-expanded" : ""}}${{showPartialColumn ? " is-with-partial" : ""}}${{row.isMuted ? " is-muted" : ""}}${{row.isGlass ? " is-glass" : ""}}${{row.isPullOut ? " is-pullout" : ""}}${{row.modelTone ? ` is-model-${{escapeHtml(String(row.modelTone))}}` : ""}}${{rowStateClass}}${{issuedEditClass}}" type="button"${{topfloorRowsLocked && !issuedEditAlert ? " disabled" : ""}} data-mfg-row${{issuedEditAlert ? " data-issued-edit-alert" : ""}}${{pantoloIsGroup ? " data-pantolo-group" : ""}} data-pantolo-state="${{escapeHtml(rowState)}}" data-row-id="${{escapeHtml(row.row_id)}}" data-row-production="${{escapeHtml(rowProductionNumber(row))}}" data-state-key="${{escapeHtml(rowStateKey(row))}}" data-state-storage-key="${{escapeHtml(rowStorageKey(row))}}" data-source-row-ids="${{escapeHtml(sourceRowIdsForRow.join(","))}}">
                ${{
                  columnLayout === "cnc-lower"
                    ? `
                        <div class="mfg-row-main">
                          <div class="mfg-row-title">${{displayRowField(row, "name", "Névtelen sor")}}${{modelBadgeMarkup}}${{glassBadgeMarkup}}${{pullOutBadgeMarkup}}</div>
                          ${{subtitleMarkup}}
                        </div>
                        <div class="mfg-row-meta"><span class="is-size">${{displayRowField(row, "size", "Méret nélkül")}}</span></div>
                        <div class="mfg-row-meta"><span class="is-color">${{displayRowField(row, "color", "Szín nélkül")}}</span></div>
                        <div class="mfg-row-meta"><span>${{displayRowField(row, "drawer_drill")}}</span></div>
                        <div class="mfg-row-meta"><span>${{hideSideTypeColumn ? "-" : displayRowField(row, "side_type")}}</span></div>
                        <div class="mfg-row-meta"><span>${{displayRowField(row, "edge")}}</span></div>
                        <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div></div>
                        ${{partialMarkup}}
                      `
                    : columnLayout === "cnc-upper"
                      ? `
                          <div class="mfg-row-main">
                            <div class="mfg-row-title">${{displayRowField(row, "name", "Névtelen sor")}}${{modelBadgeMarkup}}${{glassBadgeMarkup}}${{pullOutBadgeMarkup}}</div>
                            ${{subtitleMarkup}}
                          </div>
                          <div class="mfg-row-meta">${{cncUpperSizeMarkup}}</div>
                          <div class="mfg-row-meta"><span class="is-color">${{displayRowField(row, "color", "Szín nélkül")}}</span></div>
                          <div class="mfg-row-meta">${{cncUpperSideTypeMarkup}}</div>
                          <div class="mfg-row-meta"><span>${{displayRowField(row, "hardware_type")}}</span></div>
                          <div class="mfg-row-meta"><span>${{displayRowField(row, "edge")}}</span></div>
                          <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div></div>
                          ${{partialMarkup}}
                        `
                      : columnLayout === "cnc-fiokelo"
                        ? `
                            <div class="mfg-row-meta"><span>${{displayRowField(row, "modelLabel")}}</span></div>
                            <div class="mfg-row-meta"><span class="is-color">${{displayRowField(row, "color", "Szín nélkül")}}</span></div>
                            <div class="mfg-row-meta"><span class="is-size">${{displayRowField(row, "size", "Méret nélkül")}}</span></div>
                            <div class="mfg-row-meta"><span>${{displayRowField(row, "netfrontColor")}}</span></div>
                            <div class="mfg-row-meta">${{fiokeloDrillMarkup}}</div>
                            <div class="mfg-row-meta">${{fiokeloDrawerTypeMarkup}}</div>
                            <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div></div>
                            ${{partialMarkup}}
                          `
                        : columnLayout === "pantolo"
                          ? `
                              ${{pantoloCellsMarkup(row, pantoloQuantityText(row), pantoloExpandMarkup, partialMarkup)}}
                            `
                        : columnLayout === "topfloor"
                          ? (group?.hettichCategory ? `
                              <div class="mfg-row-main">
                                <div class="mfg-row-title">${{escapeHtml(String(row.itmDescription || "-"))}}</div>
                              </div>
                              <div class="mfg-row-barcode-wrap">
                                <div class="mfg-row-code">${{escapeHtml(String(row.itmItemNumber || "-"))}}</div>
                              </div>
                              <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(String(row.oriReqQty || 0))}}</div></div>
                            ` : `
                              <div class="mfg-row-main">
                                <div class="mfg-row-title">${{displayRowField(row, "name", "Anyagraktár tétel")}}</div>
                                ${{subtitleMarkup}}
                              </div>
                              <div class="mfg-row-side"><div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div></div>
                              <div class="mfg-row-barcode-wrap">
                                <div class="mfg-row-code">${{escapeHtml(row.code || "Kód nélkül")}}</div>
                              </div>
                            `)
                        : columnLayout === "front-standard"
                          ? `
                              ${{frontCellsMarkup(row, showPantoloExpanderColumn ? pantoloQuantityText(row) : String(row.quantity || 0), pantoloExpandMarkup, partialMarkup)}}
                            `
                          : `
                              <div class="mfg-row-main">
                                <div class="mfg-row-title">${{displayRowField(row, "name", "Névtelen sor")}}${{modelBadgeMarkup}}${{glassBadgeMarkup}}${{pullOutBadgeMarkup}}</div>
                                ${{subtitleMarkup}}
                              </div>
                              <div class="mfg-row-meta">
                                <span class="is-size">${{displayRowField(row, "size", "Méret nélkül")}}</span>
                              </div>
                              <div class="mfg-row-meta">
                                <span class="is-color">${{displayRowField(row, "color", "Szín nélkül")}}</span>
                              </div>
                              <div class="mfg-row-meta">
                                <span>${{displayRowField(row, "edge", "Él nélkül")}}</span>
                              </div>
                              <div class="mfg-row-side">
                                <div class="mfg-row-qty">${{escapeHtml(String(row.quantity || 0))}} db</div>
                              </div>
                              ${{partialMarkup}}
                              ${{
                                effectiveHideBarcode
                                  ? ""
                                  : `
                                      <div class="mfg-row-barcode-wrap">
                                        <div class="mfg-row-barcode">
                                          <svg class="mfg-row-barcode-svg" data-barcode-value="${{escapeHtml(row.code || row.detail || row.row_id)}}"></svg>
                                        </div>
                                        <div class="mfg-row-code">${{escapeHtml(row.code || row.detail || "Kód nélkül")}}</div>
                                      </div>
                                    `
                              }}
                            `
                }}
              </button>
              ${{pantoloChildRowsMarkup}}
            `;
          }}).join("");
          const sectionClass = `${{columnLayout === "pantolo" ? " is-pantolo" : ""}}${{String(document?.key || "") === "topfloor" ? topfloorCategoryStateClass(group) : ""}}`;
          return `<section class="mfg-section-card${{sectionClass}}" data-section-key="${{escapeHtml(group.key || "")}}">${{headMarkup}}${{tableHeadMarkup}}<div class="mfg-row-list" data-section-key="${{escapeHtml(group.key || "")}}">${{rowMarkup}}</div></section>`;
        }}).join("");
      }};

      const normalizePantoloHeaders = () => {{
        const labelMap = {{
          color: "Szin",
          color23: "Szin 2/3",
          pant_type: "Pant tipus",
          model: "Modell",
          size: "Meret",
          handle_drill: "Fogantyu furat",
          handle_type: "Fogantyu tipus",
          opening_dir: "Nyitas irany",
          door_type: "Ajto tipus",
          quantity: "ME",
        }};
        Array.from(contentNode.querySelectorAll(".mfg-table-head.is-pantolo .mfg-sort-head[data-sort-key]")).forEach((button) => {{
          const sortKey = String(button.getAttribute("data-sort-key") || "").trim();
          const labelNode = button.querySelector(".mfg-sort-head-label");
          if (!labelNode || !Object.prototype.hasOwnProperty.call(labelMap, sortKey)) return;
          labelNode.textContent = labelMap[sortKey];
        }});
      }};

      const syncPantoloSectionHeaders = () => {{
        pantoloStickyFrame = 0;
        const isPantoloDocument = String(currentDocument()?.key || "") === "pantolas";
        const sectionCards = Array.from(contentNode.querySelectorAll(".mfg-section-card.is-pantolo"));
        for (const card of sectionCards) {{
          const head = card.querySelector(".mfg-section-head");
          if (!(head instanceof HTMLElement)) continue;
          if (!isPantoloDocument) {{
            head.style.transform = "";
            continue;
          }}
          const cardRect = card.getBoundingClientRect();
          const headHeight = head.offsetHeight || 0;
          const stickyTop = 0;
          const shouldStick = cardRect.top < stickyTop && cardRect.bottom > stickyTop + headHeight;
          if (!shouldStick) {{
            head.style.transform = "";
            continue;
          }}
          const maxTranslate = Math.max(0, cardRect.height - headHeight);
          const translateY = Math.min(Math.max(0, stickyTop - cardRect.top), maxTranslate);
          head.style.transform = translateY ? `translateY(${{translateY}}px)` : "";
        }}
      }};

      const schedulePantoloSectionHeaders = () => {{
        if (pantoloStickyFrame) return;
        pantoloStickyFrame = window.requestAnimationFrame(syncPantoloSectionHeaders);
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
        syncIssuedEditWarning();
        if (String(document?.key || "") === "topfloor") {{
          if (!topfloorShipmentViewForKey(document, currentTopfloorShipmentKey)) {{
            currentTopfloorShipmentKey = firstTopfloorShipmentViewKey();
          }}
          if (
            !topfloorShowIssued
            && !topfloorShipmentKeyIsAll(currentTopfloorShipmentKey)
            && Boolean(topfloorShipmentViewForKey(document, topfloorAllShipmentsKey))
            && !topfloorShipmentHasIssuedEdit(document, currentTopfloorShipmentKey)
            && topfloorSectionsComplete(topfloorShipmentSectionsForKey(document, currentTopfloorShipmentKey, {{ includeIssued: true }}))
          ) {{
            currentTopfloorShipmentKey = topfloorAllShipmentsKey;
            currentViewKey = "all";
          }}
          const productionTabs = topfloorProductionTabs(topfloorShipmentSections(document));
          const validKeys = new Set(["all", "plain", "green", "red", ...productionTabs.map((item) => item.key)]);
          if (!validKeys.has(currentViewKey)) {{
            currentViewKey = "all";
          }}
        }}
        refreshOperationHeader();
        if (String(document?.key || "") !== "topfloor" && documentUsesSingleColumnOverview(document) && !isSpecialViewKey(currentViewKey, document)) {{
          currentViewKey = "all";
          secondaryViewKey = "";
        }}
        renderDocTabs();
        renderSectionTabs(document);
        updateSearchControls(document);
        const visibleGroups = filterGroupsBySearch(buildGroupsForView(document), document);
        const isKorpuszPairedDetailView =
          String(document?.key || "") === "korpusz_osszekeszites" &&
          String(currentViewKey || "") === "korpusz-osszekeszito" &&
          layoutMode === "double" &&
          !["all", "plain", "green", "red", "mixed"].includes(String(currentSubcategoryKey || ""));
        window.document.body.classList.toggle("has-mfg-scroll-rail", Boolean(document) && !isKorpuszPairedDetailView);
        const isTopfloor = String(document?.key || "") === "topfloor";
        issuedToggleNode.style.display = isTopfloor ? "inline-flex" : "none";
        issuedToggleNode.classList.toggle("is-active", topfloorShowIssued);
        issuedToggleNode.setAttribute("aria-pressed", topfloorShowIssued ? "true" : "false");
        issuedToggleNode.textContent = topfloorShowIssued ? "Kiadottak elrejtése" : "Kiadottak mutatása";
        const canReportReady = canReportReadyForCurrentView(document);
        reportReadyButtonNode.style.display = canReportReady ? "inline-flex" : "none";
        if (canReportReady) {{
          const greenRows = visibleGroups
            .flatMap((group) => Array.isArray(group?.rows) ? group.rows : [])
            .filter((row) => isReadyGreenState(rowStateValue(row)));
          reportReadyButtonNode.disabled = greenRows.length === 0;
        }} else {{
          reportReadyButtonNode.disabled = true;
        }}
        layoutToggleNode.style.display = documentAllowsSplit(document) ? "" : "none";
        if (!documentAllowsSplit(document)) {{
          layoutMode = "single";
        }}
        Array.from(layoutToggleNode.querySelectorAll("[data-layout-mode]")).forEach((button) => {{
          const mode = button.getAttribute("data-layout-mode") || "single";
          button.classList.toggle("is-active", mode === layoutMode);
        }});
        updateProductionChipState(Array.isArray(payload.recentProductions) ? payload.recentProductions : []);
        renderRows(visibleGroups);
        normalizePantoloHeaders();
        renderBarcodes();
        requestAnimationFrame(() => {{
          restoreScrollState(scrollState);
          syncPantoloSectionHeaders();
        }});
      }};

      const persistRowState = async (rowId, targetProductionNumber, stateKey, storageKey, nextState, previousStateMap, sourceRowIds = []) => {{
        try {{
          const cleanSourceRowIds = Array.from(new Set(sourceRowIds.map((value) => String(value || "").trim()).filter(Boolean)));
          const uniqueRowIds = Array.from(new Set([rowId, storageKey, ...cleanSourceRowIds].map((value) => String(value || "").trim()).filter(Boolean)));
          const uniqueStateKeys = cleanSourceRowIds.length
            ? cleanSourceRowIds
            : Array.from(new Set([storageKey || rowId].map((value) => String(value || "").trim()).filter(Boolean)));
          const primarySaveKey = uniqueStateKeys[0] || storageKey || rowId;
          queuePersistentWrite({{
            type: "row-state",
            body: {{
              production_number: targetProductionNumber,
              document_key: String(currentDocument()?.key || ""),
              row_id: rowId,
              row_ids: uniqueRowIds,
              state_key: primarySaveKey,
              state_keys: uniqueStateKeys,
              state: nextState || "clear",
            }},
          }});
          setStatus("Mentés...");
        }} catch (error) {{
          for (const [previousKey, previousValue] of previousStateMap.entries()) {{
            if (previousValue) selectionState[previousKey] = previousValue;
            else delete selectionState[previousKey];
          }}
          renderAll();
          setStatus(error instanceof Error ? error.message : "A mentés nem sikerült.", "is-error");
        }}
      }};

      const clearPartialQuantities = (targetProductionNumber, keys) => {{
        const cleanKeys = Array.from(new Set(
          (Array.isArray(keys) ? keys : [])
            .map((value) => String(value || "").trim())
            .filter(Boolean)
        ));
        for (const key of cleanKeys) {{
          if (!Object.prototype.hasOwnProperty.call(partialQuantityState, key)) continue;
          const previousValue = String(partialQuantityState[key] || "");
          delete partialQuantityState[key];
          const existingTimer = partialSaveTimers.get(key);
          if (existingTimer) {{
            clearTimeout(existingTimer);
            partialSaveTimers.delete(key);
          }}
          void persistPartialQuantity(targetProductionNumber, key, "", previousValue);
        }}
      }};

      const applyRowState = (stateKey, storageKey, rowId, targetProductionNumber, targetState, sourceRowIds = []) => {{
        const scrollState = captureScrollState();
        const sourceStateKeys = Array.from(new Set(sourceRowIds.map((sourceRowId) => normalizeSelectionKey(targetProductionNumber, sourceRowId)).filter(Boolean)));
        const primaryStateKeys = sourceStateKeys.length ? sourceStateKeys : [stateKey].map((value) => String(value || "").trim()).filter(Boolean);
        const clearOnlyKeys = sourceStateKeys.length
          ? [stateKey, storageKey].map((value) => String(value || "").trim()).filter((value) => value && !primaryStateKeys.includes(value))
          : [];
        const allStateKeys = Array.from(new Set([...primaryStateKeys, ...clearOnlyKeys]));
        const previousStateMap = new Map(allStateKeys.map((key) => [key, selectionState[key] || ""]));
        for (const key of primaryStateKeys) {{
          if (targetState === "clear") delete selectionState[key];
          else selectionState[key] = targetState;
        }}
        for (const key of clearOnlyKeys) delete selectionState[key];
        if (targetState === "green" && String(currentDocument()?.key || "") === "cnc_furas") {{
          clearPartialQuantities(targetProductionNumber, [rowId, stateKey, storageKey, ...allStateKeys]);
        }}
        renderAll(scrollState);
        setStatus("Mentés...");
        void persistRowState(rowId, targetProductionNumber, stateKey, storageKey, targetState, previousStateMap, sourceRowIds);
      }};

      const persistStateUpdates = async (targetProductionNumber, updates, previousStateMap) => {{
        try {{
          for (const update of updates) {{
            const rowId = String(update.rowId || "").trim();
            const storageKey = String(update.storageKey || rowId).trim();
            if (!rowId) continue;
            queuePersistentWrite({{
              type: "row-state",
              body: {{
                production_number: targetProductionNumber,
                document_key: String(currentDocument()?.key || ""),
                row_id: rowId,
                row_ids: [rowId],
                state_key: storageKey || rowId,
                state_keys: [storageKey || rowId],
                state: update.state || "clear",
              }},
            }});
          }}
          setStatus("Mentés...");
        }} catch (error) {{
          for (const [previousKey, previousValue] of previousStateMap.entries()) {{
            if (previousValue) selectionState[previousKey] = previousValue;
            else delete selectionState[previousKey];
          }}
          renderAll();
          setStatus(error instanceof Error ? error.message : "A mentés nem sikerült.", "is-error");
        }}
      }};

      const normalizedPantoloParentStateFromUnitStates = (states) => {{
        if (states.every((state) => !state)) return "";
        if (states.every((state) => state === "red")) return "red";
        if (states.every((state) => state === "done")) return "done";
        if (states.every((state) => isGreenLikeState(state))) return "green";
        return "";
      }};

      const applyPantoloUnitState = (parentRowId, unitRowId, targetProductionNumber, targetState) => {{
        const parentRow = findRowById(parentRowId);
        if (!parentRow || !unitRowId) return;
        const scrollState = captureScrollState();
        const total = pantoloQuantity(parentRow);
        const parentKey = rowStateKey(parentRow);
        const parentPreviousState = selectionState[parentKey] || "";
        const updatesByRowId = new Map();
        const trackedKeys = [parentKey];
        const nextUnitStates = [];

        for (let index = 0; index < total; index += 1) {{
          const childRowId = childUnitRowId(parentRow, index);
          const childKey = childUnitStateKey(parentRow, index);
          const childStorageKey = childUnitStorageKey(parentRow, index);
          trackedKeys.push(childKey);
          let childState = childUnitState(parentRow, index);
          if (childRowId === unitRowId) {{
            childState = targetState === "clear" ? "" : targetState;
          }}
          nextUnitStates.push(childState);
          const explicitPrevious = selectionState[childKey] || "";
          if (childState !== explicitPrevious) {{
            updatesByRowId.set(childRowId, {{ rowId: childRowId, storageKey: childStorageKey, state: childState }});
          }}
        }}

        const nextParentState = normalizedPantoloParentStateFromUnitStates(nextUnitStates);
        if (nextParentState !== parentPreviousState) {{
          updatesByRowId.set(parentRowId, {{ rowId: parentRowId, storageKey: rowStorageKey(parentRow), state: nextParentState }});
        }}

        const previousStateMap = new Map(trackedKeys.map((key) => [key, selectionState[key] || ""]));
        const partialKeysToClear = [];
        for (let index = 0; index < total; index += 1) {{
          const childRowId = childUnitRowId(parentRow, index);
          const childKey = childUnitStateKey(parentRow, index);
          const childStorageKey = childUnitStorageKey(parentRow, index);
          const childState = nextUnitStates[index] || "";
          if (childState) selectionState[childKey] = childState;
          else delete selectionState[childKey];
          if (childState === "green") partialKeysToClear.push(childRowId, childStorageKey, childKey);
        }}
        if (nextParentState) selectionState[parentKey] = nextParentState;
        else delete selectionState[parentKey];
        if (nextParentState === "green") partialKeysToClear.push(parentRowId, rowStorageKey(parentRow), parentKey);
        if (String(currentDocument()?.key || "") === "cnc_furas") {{
          clearPartialQuantities(targetProductionNumber, partialKeysToClear);
        }}

        renderAll(scrollState);
        setStatus("Mentés...");
        void persistStateUpdates(targetProductionNumber, Array.from(updatesByRowId.values()), previousStateMap);
      }};

      const closeRedChoiceModal = () => {{
        pendingRedChoice = null;
        choiceModalNode.hidden = true;
      }};

      const openRedChoiceModal = (payload) => {{
        pendingRedChoice = payload;
        const titleNode = choiceModalNode.querySelector(".mfg-choice-title");
        const copyNode = choiceModalNode.querySelector(".mfg-choice-copy");
        const redButton = choiceModalNode.querySelector('[data-choice-action="red"]');
        if (titleNode) titleNode.textContent = payload?.allowRed ? "Vegyes csoport" : "Piros tétel áthelyezése";
        if (copyNode) copyNode.textContent = payload?.allowRed ? "Milyen állapotot kapjon az egész csoport?" : "Hova kerüljön a kijelölt piros tétel?";
        if (redButton instanceof HTMLElement) redButton.hidden = !payload?.allowRed;
        choiceModalNode.hidden = false;
      }};

      const closeConfirmModal = (result = false) => {{
        confirmModalNode.hidden = true;
        if (typeof pendingConfirmResolve === "function") {{
          const resolve = pendingConfirmResolve;
          pendingConfirmResolve = null;
          resolve(Boolean(result));
        }}
      }};

      const requestConfirmModal = (options = {{}}) =>
        new Promise((resolve) => {{
          const titleNode = confirmModalNode.querySelector(".mfg-confirm-title");
          const copyNode = confirmModalNode.querySelector(".mfg-confirm-copy");
          const actionsNode = confirmModalNode.querySelector(".mfg-confirm-actions");
          const cancelButton = confirmModalNode.querySelector('[data-confirm-action="cancel"]');
          const confirmButton = confirmModalNode.querySelector('[data-confirm-action="confirm"]');
          if (titleNode) titleNode.textContent = String(options.title || "Biztosan készre jelented a zöld tételeket?");
          if (copyNode) copyNode.textContent = String(options.copy || "A sikeresen készre jelentett sorok sötétzöldre váltanak és többé nem módosíthatók.");
          if (confirmButton instanceof HTMLElement) confirmButton.textContent = String(options.confirmText || "Igen, készre");
          if (cancelButton instanceof HTMLElement) cancelButton.hidden = Boolean(options.singleAction);
          if (actionsNode instanceof HTMLElement) actionsNode.classList.toggle("is-single", Boolean(options.singleAction));
          pendingConfirmResolve = resolve;
          confirmModalNode.hidden = false;
        }});

      const optimisticallyCompleteIssuedEditAlert = (productionId, rowKey, documentKey) => {{
        const previousView = {{ currentTopfloorShipmentKey, currentViewKey, currentSubcategoryKey }};
        const rowSnapshots = [];
        const categorySnapshots = [];
        const entrySnapshots = [];
        const seenRows = new Set();
        const seenCategories = new Set();
        for (const document of documents) {{
          if (documentKey && String(document?.key || "") !== String(documentKey)) continue;
          for (const section of alertSectionsForDocument(document)) {{
            const sectionRows = Array.isArray(section?.rows) ? section.rows : [];
            for (const row of sectionRows) {{
              if (rowProductionNumber(row) !== String(productionId) || rowStorageKey(row) !== String(rowKey)) continue;
              if (seenRows.has(row)) continue;
              seenRows.add(row);
              rowSnapshots.push({{
                row,
                editedAfterIssue: row._editedAfterIssue,
                issuedEditFields: row._issuedEditFields,
              }});
              delete row._editedAfterIssue;
              delete row._issuedEditFields;
            }}
            const category = section?.topfloorCategory;
            if (category && !seenCategories.has(category) && String(category.shipmentID || "") === String(productionId)) {{
              seenCategories.add(category);
              categorySnapshots.push({{ category, value: category.hasIssuedRowEdit }});
              category.hasIssuedRowEdit = sectionRows.some((row) => Boolean(row?._editedAfterIssue));
            }}
          }}
        }}
        if (documentKey === "topfloor") {{
          for (const entry of (Array.isArray(payload.recentProductions) ? payload.recentProductions : [])) {{
            if (String(entry?.view_key || "") !== `shipment::${{productionId}}`) continue;
            entrySnapshots.push({{ entry, value: entry.has_issued_row_edit }});
            entry.has_issued_row_edit = documents.some((document) =>
              String(document?.key || "") === "topfloor"
              && topfloorShipmentHasIssuedEdit(document, `shipment::${{productionId}}`)
            );
          }}
        }}
        renderAll();
        return () => {{
          for (const snapshot of rowSnapshots) {{
            snapshot.row._editedAfterIssue = snapshot.editedAfterIssue;
            snapshot.row._issuedEditFields = snapshot.issuedEditFields;
          }}
          for (const snapshot of categorySnapshots) snapshot.category.hasIssuedRowEdit = snapshot.value;
          for (const snapshot of entrySnapshots) snapshot.entry.has_issued_row_edit = snapshot.value;
          currentTopfloorShipmentKey = previousView.currentTopfloorShipmentKey;
          currentViewKey = previousView.currentViewKey;
          currentSubcategoryKey = previousView.currentSubcategoryKey;
          renderAll();
        }};
      }};

      const completeIssuedEditAlert = async (productionId, rowKey, documentKey) => {{
        const isTopfloorAlert = String(documentKey || "") === "topfloor";
        const confirmed = await requestConfirmModal({{
          title: "Módosítás ellenőrizve?",
          copy: isTopfloorAlert
            ? "Biztosan késznek jelölöd ezt a dobozba rakás vagy kiadás után módosított tételt? A figyelmeztetés megszűnik, és a lezárt tétel ismét elrejthető lesz."
            : "Biztosan ellenőrzöttnek jelölöd ezt a zöldre vagy készre jelölés után módosított tételt? A piros figyelmeztetés megszűnik.",
          confirmText: "Igen, kész",
        }});
        if (!confirmed) return;
        const rollbackOptimisticCompletion = optimisticallyCompleteIssuedEditAlert(productionId, rowKey, documentKey);
        setStatus("Figyelmeztetés lezárása...");
        try {{
          const response = await fetch(issuedEditCompleteRoute, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              production_number: productionId,
              shipment_id: isTopfloorAlert ? productionId : "",
              document_key: documentKey,
              row_key: rowKey,
            }}),
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "A figyelmeztetés lezárása nem sikerült.");
          }}
          await forceRefreshForAdminChange(String(result.admin_change_revision || Date.now()));
          setStatus("A módosított tétel késznek jelölve.", "is-success");
        }} catch (error) {{
          rollbackOptimisticCompletion();
          setStatus(error instanceof Error ? error.message : "A figyelmeztetés lezárása nem sikerült.", "is-error");
        }}
      }};

      const requestCreatorModal = () =>
        new Promise((resolve) => {{
          pendingCreatorResolve = resolve;
          creatorModalNode.hidden = false;
        }});

      const persistPartialQuantity = async (targetProductionNumber, stateKey, value, previousValue) => {{
        try {{
          queuePersistentWrite({{
            type: "partial-quantity",
            body: {{
              production_number: targetProductionNumber,
              state_key: stateKey,
              value,
            }},
          }});
          setStatus("Mentés...");
        }} catch (error) {{
          if (previousValue) partialQuantityState[stateKey] = previousValue;
          else delete partialQuantityState[stateKey];
          renderAll();
          setStatus(error instanceof Error ? error.message : "A mentés nem sikerült.", "is-error");
        }}
      }};

      const queuePartialQuantitySave = (targetProductionNumber, stateKey, value) => {{
        const previousValue = String(partialQuantityState[stateKey] || "");
        const normalizedValue = String(value || "").replace(/[^0-9]/g, "").slice(0, 4);
        if (normalizedValue) partialQuantityState[stateKey] = normalizedValue;
        else delete partialQuantityState[stateKey];
        const existingTimer = partialSaveTimers.get(stateKey);
        if (existingTimer) clearTimeout(existingTimer);
        const nextTimer = setTimeout(() => {{
          partialSaveTimers.delete(stateKey);
          void persistPartialQuantity(targetProductionNumber, stateKey, normalizedValue, previousValue);
        }}, 280);
        partialSaveTimers.set(stateKey, nextTimer);
      }};

      if (cacheRefreshButtonNode) {{
        cacheRefreshButtonNode.addEventListener("click", (event) => {{
          event.preventDefault();
          void refreshProductionClientCache();
        }});
      }}
      if (productionLookupNode instanceof HTMLFormElement && productionNumberInputNode instanceof HTMLInputElement) {{
        productionLookupNode.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const targetProductionNumber = String(productionNumberInputNode.value || "").replace(/[^0-9]/g, "");
          if (!targetProductionNumber || !currentDocKey) {{
            setStatus("Adj meg egy érvényes gyártási számot.", "is-error");
            return;
          }}
          if (targetProductionNumber === productionNumber) return;
          storeCurrentProductionPayload();
          productionLookupNode.classList.add("is-loading");
          setStatus("Korábbi gyártás keresése...");
          try {{
            await flushPendingWrites();
            const nextPayload = await fetchProductionPayload(targetProductionNumber, currentDocKey);
            applyProductionPayload(nextPayload);
            productionNumberInputNode.value = "";
            setStatus(`A ${{targetProductionNumber}} gyártás betöltve.`, "is-success");
          }} catch (error) {{
            setStatus(error instanceof Error ? error.message : "A gyártás betöltése nem sikerült.", "is-error");
          }} finally {{
            productionLookupNode.classList.remove("is-loading");
          }}
        }});
      }}

      document.addEventListener("click", async (event) => {{
        const missingLink = event.target.closest("[data-mfg-missing-link]");
        if (missingLink instanceof HTMLElement) {{
          event.preventDefault();
          const document = currentDocument();
          if (String(document?.key || "") !== "pantolas" || !specialViewForKey(document, "pantolo-missing")) return;
          currentViewKey = "pantolo-missing";
          currentSubcategoryKey = "all";
          secondaryViewKey = "";
          renderAll();
          return;
        }}
        const shipmentLink = event.target.closest("[data-mfg-shipment-link]");
        if (shipmentLink instanceof HTMLElement) {{
          event.preventDefault();
          const shipmentStartedAt = performance.now();
          const nextViewKey = String(shipmentLink.getAttribute("data-view-key") || "").trim();
          const document = currentDocument();
          if (String(document?.key || "") !== "topfloor" || !topfloorShipmentViewForKey(document, nextViewKey)) return;
          shopfloorLog(`shipment view start view=${{nextViewKey || "-"}}`);
          currentTopfloorShipmentKey = nextViewKey;
          currentViewKey = "all";
          currentSubcategoryKey = "all";
          secondaryViewKey = "";
          renderAll();
          shopfloorLog(`shipment view done view=${{nextViewKey || "-"}} took=${{shopfloorSeconds(shipmentStartedAt)}}s`);
          return;
        }}
        const link = event.target.closest("[data-mfg-production-link]");
        if (!(link instanceof HTMLElement)) return;
        const targetProductionNumber = String(link.getAttribute("data-production-number") || "").trim();
        event.preventDefault();
        if (!targetProductionNumber || !currentDocKey) return;
        if (targetProductionNumber === productionNumber) {{
          if (currentViewKey === "pantolo-missing") {{
            currentViewKey = "all";
            currentSubcategoryKey = "all";
            secondaryViewKey = "";
            renderAll();
          }}
          return;
        }}
        const switchStartedAt = performance.now();
        shopfloorLog(`production switch start operation=${{currentDocKey || "-"}} from=${{productionNumber || "-"}} to=${{targetProductionNumber || "-"}}`);
        storeCurrentProductionPayload();
        setStatus("Gyártás betöltése...");
        try {{
          await flushPendingWrites();
          const nextPayload = await fetchProductionPayload(targetProductionNumber, currentDocKey);
          applyProductionPayload(nextPayload);
          shopfloorLog(`production switch done operation=${{currentDocKey || "-"}} to=${{targetProductionNumber || "-"}} took=${{shopfloorSeconds(switchStartedAt)}}s`);
        }} catch (error) {{
          shopfloorLog(`production switch failed operation=${{currentDocKey || "-"}} to=${{targetProductionNumber || "-"}} took=${{shopfloorSeconds(switchStartedAt)}}s`, error);
          setStatus(error instanceof Error ? error.message : "A gyártás betöltése nem sikerült.", "is-error");
          const href = String(link.getAttribute("href") || "");
          if (href) window.location.href = href;
        }}
      }});

      docTabsNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-doc-key]");
        if (!(button instanceof HTMLElement)) return;
        const nextDocKey = button.getAttribute("data-doc-key") || "";
        if (!nextDocKey || nextDocKey === currentDocKey) return;
        currentDocKey = nextDocKey;
        currentViewKey = "all";
        currentSubcategoryKey = "all";
        secondaryViewKey = "";
        syncUrlForDocument();
        renderAll();
      }});

      sectionTabsNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-view-key]");
        if (!(button instanceof HTMLElement)) return;
        const nextViewKey = button.getAttribute("data-view-key") || "all";
        const activeDocument = currentDocument();
        if (isSpecialViewKey(nextViewKey, activeDocument)) {{
          if (nextViewKey === currentViewKey && !secondaryViewKey) return;
          currentViewKey = nextViewKey;
          currentSubcategoryKey = "all";
          secondaryViewKey = "";
          renderAll();
          return;
        }}
        if (!documentAllowsSplit(activeDocument)) {{
          if (nextViewKey === currentViewKey) return;
          currentViewKey = nextViewKey;
          currentSubcategoryKey = "all";
          secondaryViewKey = "";
          renderAll();
          return;
        }}
        if (layoutMode === "double") {{
          if (isSpecialViewKey(currentViewKey, activeDocument)) {{
            currentViewKey = nextViewKey;
            currentSubcategoryKey = "all";
            secondaryViewKey = pairedSectionKey(activeDocument, nextViewKey);
          }} else if (nextViewKey === currentViewKey || nextViewKey === secondaryViewKey) {{
            return;
          }} else {{
            currentViewKey = nextViewKey;
            currentSubcategoryKey = "all";
            secondaryViewKey = pairedSectionKey(activeDocument, nextViewKey);
          }}
        }} else {{
          if (nextViewKey === currentViewKey) return;
          currentViewKey = nextViewKey;
          currentSubcategoryKey = "all";
          secondaryViewKey = "";
        }}
        renderAll();
      }});

      subsectionTabsNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-subcategory-key]");
        if (!(button instanceof HTMLElement)) return;
        const nextSubcategoryKey = button.getAttribute("data-subcategory-key") || "all";
        if (nextSubcategoryKey === currentSubcategoryKey) return;
        currentSubcategoryKey = nextSubcategoryKey;
        renderAll();
      }});

      searchInputNode.addEventListener("keydown", (event) => {{
        if (event.key !== "Enter") return;
        event.preventDefault();
        activeSearchText = searchInputNode.value || "";
        renderAll();
      }});

      searchInputNode.addEventListener("input", () => {{
        activeSearchText = searchInputNode.value || "";
        renderAll();
      }});

      layoutToggleNode.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-layout-mode]");
        if (!(button instanceof HTMLElement)) return;
        const nextMode = button.getAttribute("data-layout-mode") || "single";
        if (!documentAllowsSplit(currentDocument())) return;
        if (nextMode === layoutMode) return;
        layoutMode = nextMode === "double" ? "double" : "single";
        if (layoutMode === "single") {{
          secondaryViewKey = "";
        }} else if (isSpecialViewKey(currentViewKey, currentDocument())) {{
          currentViewKey = "all";
          secondaryViewKey = "";
        }} else {{
          secondaryViewKey = pairedSectionKey(currentDocument(), currentViewKey);
        }}
        renderAll();
      }});

      issuedToggleNode.addEventListener("click", () => {{
        if (String(currentDocument()?.key || "") !== "topfloor") return;
        topfloorShowIssued = !topfloorShowIssued;
        currentViewKey = "all";
        currentSubcategoryKey = "all";
        secondaryViewKey = "";
        renderAll();
      }});

      contentNode.addEventListener("click", async (event) => {{
        const button = event.target.closest("[data-hettich-transfer]");
        if (!(button instanceof HTMLButtonElement) || button.disabled || !topfloorTransferRoute) return;
        event.preventDefault();
        event.stopPropagation();
        const categoryNode = button.closest("[data-hettich-category]");
        const prdId = String(categoryNode?.getAttribute("data-hettich-category") || "").trim();
        const document = currentDocument();
        if (String(document?.key || "") !== "topfloor" || !prdId) return;
        const group = (Array.isArray(document.sections) ? document.sections : []).find(
          (item) => String(item?.hettichCategory?.prdID || "") === prdId
        );
        if (!group || !topfloorHettichCategoryReady(group)) return;
        const entries = (Array.isArray(group.rows) ? group.rows : [])
          .filter((row) => isReadyGreenState(rowStateValue(row)))
          .map((row) => ({{
            item_number: String(row?.itmItemNumber || row?.code || "").trim(),
            itm_id: String(row?.itmID || "").trim(),
            quantity: String(row?.oriReqQty || row?.quantity || "").trim(),
            uom_code: String(row?.PrimaryUOMCode || "").trim(),
            state_key: String(rowStateKey(row) || "").trim(),
          }}))
          .filter((entry) => entry.item_number && entry.itm_id && entry.quantity && entry.uom_code && entry.state_key);
        const confirmed = await requestConfirmModal({{
          title: "Biztosan átraktározod a kijelölt tételeket?",
          copy: entries.length
            ? `${{entries.length}} zöld Hettich tétel kerül át az Anyag raktárból az ÜZEMI raktárba.`
            : "Nincs zöld tétel ebben a kategóriában; nem történik átraktározás.",
          confirmText: "Igen, átraktározom",
        }});
        if (!confirmed) return;
        button.disabled = true;
        setStatus("Hettich átraktározás folyamatban...");
        try {{
          await flushPendingWrites();
          const response = await fetch(topfloorTransferRoute, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ prd_id: prdId, entries }}),
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) throw new Error(result.error || "A Hettich átraktározás nem sikerült.");
          productionPayloadCache.delete(productionCacheKey(currentDocKey, productionNumber));
          const refreshed = await fetchProductionPayload(productionNumber, currentDocKey);
          documents = Array.isArray(refreshed.documents) ? refreshed.documents : documents;
          selectionState = Object.assign({{}}, refreshed.selectionState || selectionState || {{}});
          if (Array.isArray(refreshed.recentProductions)) {{
            payload.recentProductions = refreshed.recentProductions;
            renderProductionChips(refreshed.recentProductions);
          }}
          const failedCount = Array.isArray(result.failed_items) ? result.failed_items.length : 0;
          setStatus(
            failedCount
              ? `Az átraktározás elkészült, de ${{failedCount}} tétel sikertelen volt és pirosra váltott.`
              : "A Hettich átraktározás elkészült.",
            failedCount ? "is-error" : "is-success",
          );
          renderAll();
        }} catch (error) {{
          setStatus(error instanceof Error ? error.message : "A Hettich átraktározás nem sikerült.", "is-error");
          renderAll();
        }}
      }});

      contentNode.addEventListener("click", async (event) => {{
        const button = event.target.closest("[data-topfloor-action]");
        if (!(button instanceof HTMLElement)) return;
        if (button.disabled || !topfloorBoxRoute) return;
        event.preventDefault();
        event.stopPropagation();
        const action = String(button.getAttribute("data-topfloor-action") || "").trim();
        const categoryNode = button.closest("[data-topfloor-category]");
        const categoryKey = String(categoryNode?.getAttribute("data-topfloor-category") || "").trim();
        const descriptionInput = categoryNode?.querySelector("[data-topfloor-description]");
        const conDescription = descriptionInput instanceof HTMLInputElement ? String(descriptionInput.value || "").trim() : "";
        const boxTypeSelect = categoryNode?.querySelector("[data-topfloor-box-type]");
        const selectedBoxOption = boxTypeSelect instanceof HTMLSelectElement ? boxTypeSelect.selectedOptions[0] : null;
        const selectedBoxName = boxTypeSelect instanceof HTMLSelectElement ? String(boxTypeSelect.value || "").trim() : "";
        const selectedBoxType = {{
          name: selectedBoxName,
          code: selectedBoxOption instanceof HTMLOptionElement ? String(selectedBoxOption.getAttribute("data-code") || "").trim() : "",
          id: selectedBoxOption instanceof HTMLOptionElement ? Number(selectedBoxOption.getAttribute("data-id") || 0) || 0 : 0,
        }};
        const document = currentDocument();
        if (String(document?.key || "") !== "topfloor" || !categoryKey) return;
        const groups = filterGroupsBySearch(buildGroupsForView(document), document);
        const group = groups.find((item) => String(item?.topfloorCategory?.categoryKey || "") === categoryKey);
        if (!group) return;
        const category = group.topfloorCategory || {{}};
        const unissuedDoneBox = topfloorUnissuedDoneBoxCategory(document);
        const openBox = topfloorOpenBoxCategory(document, categoryKey);
        const topfloorGuard = {{
          target_exists: true,
          target_ready_to_issue: topfloorCategoryReadyToIssue(group),
          unissued_done_box: topfloorGuardBoxPayload(unissuedDoneBox),
          open_box: topfloorGuardBoxPayload(openBox),
        }};
        if (action !== "issue-storage-box") {{
          if (unissuedDoneBox) {{
            await warnTopfloorUnissuedDoneBox(unissuedDoneBox);
            setStatus("Van lezárt, de még ki nem adott Anyagraktár doboz.", "is-error");
            return;
          }}
        }}
        if (["create", "open", "reprint-label"].includes(action)) {{
          if (openBox) {{
            await warnTopfloorOpenBox(openBox);
            setStatus("Már van nyitott Anyagraktár doboz.", "is-error");
            return;
          }}
        }}
        if (action === "issue-storage-box" && selectedBoxName === "Válassz dobozt!") {{
          setStatus("Válassz dobozt a kiadáshoz.", "is-error");
          return;
        }}
        const entries = action === "close"
          ? (Array.isArray(group.rows) ? group.rows : [])
              .filter((row) => isReadyGreenState(rowStateValue(row)))
              .map((row) => ({{
                code: String(row?.code || "").trim(),
                state_key: String(rowStateKey(row) || "").trim(),
                state_storage_key: String(rowStorageKey(row) || "").trim(),
              }}))
              .filter((entry) => entry.code && entry.state_storage_key)
          : [];
        if (action === "close") {{
          const isConfirmed = await requestConfirmModal({{
            title: "Biztosan lezárod a dobozt?",
            copy: entries.length
              ? `A doboz lezárásakor ${{entries.length}} zöld tétel kerül a dobozba, majd a doboz bezáródik.`
              : "A doboz zöld tétel nélkül lesz lezárva.",
            confirmText: "Igen, lezárom",
          }});
          if (!isConfirmed) return;
        }}
        let boxCreatedBy = "";
        if (action === "create") {{
          boxCreatedBy = String(await requestCreatorModal() || "").trim();
          if (!boxCreatedBy) return;
        }}
        button.disabled = true;
        setStatus("Anyagraktár doboz művelet folyamatban...");
        const topfloorDebugStartedAt = performance.now();
        const topfloorDebugLabel = `[topfloor-box] ${{action}} ${{categoryKey}}`;
        console.log(`${{topfloorDebugLabel}} client checks done, entries=${{entries.length}}`);
        try {{
          const topfloorPostStartedAt = performance.now();
          const response = await fetch(topfloorBoxRoute, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              action,
              category_key: categoryKey,
              shipment_id: String(category.shipmentID || "").trim(),
              buyer: String(category.buyer || "").trim(),
              location: String(category.location || "").trim(),
              buyer_id: String(category.buyerID || "").trim(),
              con_description: conDescription,
              created_by: boxCreatedBy,
              box_type: selectedBoxType,
              guard: topfloorGuard,
              entries,
            }}),
          }});
          console.log(`${{topfloorDebugLabel}} post took ${{((performance.now() - topfloorPostStartedAt) / 1000).toFixed(3)}}s status=${{response.status}}`);
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "Az Anyagraktár doboz művelet nem sikerült.");
          }}
          productionPayloadCache.delete(productionCacheKey(currentDocKey, productionNumber));
          const topfloorRefreshStartedAt = performance.now();
          const refreshed = await fetchProductionPayload(productionNumber, currentDocKey);
          console.log(`${{topfloorDebugLabel}} refresh took ${{((performance.now() - topfloorRefreshStartedAt) / 1000).toFixed(3)}}s`);
          documents = Array.isArray(refreshed.documents) ? refreshed.documents : documents;
          selectionState = Object.assign({{}}, refreshed.selectionState || selectionState || {{}});
          setStatus("Anyagraktár doboz művelet kész.", "is-success");
          renderAll();
        }} catch (error) {{
          setStatus(error instanceof Error ? error.message : "Az Anyagraktár doboz művelet nem sikerült.", "is-error");
          renderAll();
        }} finally {{
          console.log(`${{topfloorDebugLabel}} total took ${{((performance.now() - topfloorDebugStartedAt) / 1000).toFixed(3)}}s`);
        }}
      }});

      contentNode.addEventListener("click", async (event) => {{
        const partialInput = event.target.closest("[data-partial-input]");
        if (partialInput instanceof HTMLElement) {{
          event.stopPropagation();
          return;
        }}
        const sortButton = event.target.closest("[data-sort-key]");
        if (sortButton instanceof HTMLElement) {{
          event.preventDefault();
          event.stopPropagation();
          const nextSortKey = sortButton.getAttribute("data-sort-key") || "source";
          const sectionKey = sortButton.getAttribute("data-section-key") || "__default__";
          const normalizedKey = normalizedSectionSortKey(sectionKey);
          const currentSectionSortState = getSectionSortState(sectionKey);
          if (currentSectionSortState.key !== nextSortKey) {{
            sectionSortState[normalizedKey] = {{ key: nextSortKey, direction: "asc" }};
          }} else if (currentSectionSortState.direction === "asc") {{
            sectionSortState[normalizedKey] = {{ key: nextSortKey, direction: "desc" }};
          }} else {{
            sectionSortState[normalizedKey] = {{ key: "source", direction: "asc" }};
          }}
          renderAll();
          return;
        }}
        const expandButton = event.target.closest("[data-pantolo-expand]");
        if (expandButton instanceof HTMLElement) {{
          event.preventDefault();
          event.stopPropagation();
          const stateKey = expandButton.getAttribute("data-state-key") || "";
          if (!stateKey) return;
          if (collapsingPantoloGroups.has(stateKey)) return;
          if (expandedPantoloGroups.has(stateKey)) {{
            const parentRow = expandButton.closest(".is-pantolo-group");
            const childRows = [];
            let sibling = parentRow?.nextElementSibling || null;
            while (sibling instanceof HTMLElement && sibling.classList.contains("is-pantolo-unit")) {{
              childRows.push(sibling);
              sibling = sibling.nextElementSibling;
            }}
            const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
            if (!childRows.length || reducedMotion) {{
              expandedPantoloGroups.delete(stateKey);
              renderAll();
              return;
            }}
            collapsingPantoloGroups.add(stateKey);
            expandButton.textContent = "\u25BC";
            expandButton.setAttribute("aria-label", "Kinyitás");
            childRows.forEach((childRow) => childRow.classList.add("is-collapsing"));
            window.setTimeout(() => {{
              expandedPantoloGroups.delete(stateKey);
              collapsingPantoloGroups.delete(stateKey);
              renderAll();
            }}, 170);
          }} else {{
            expandedPantoloGroups.add(stateKey);
            openingPantoloGroups.add(stateKey);
            renderAll();
            openingPantoloGroups.delete(stateKey);
          }}
          return;
        }}
        const row = event.target.closest("[data-mfg-row]");
        if (!(row instanceof HTMLElement)) return;
        const rowId = row.getAttribute("data-row-id") || "";
        const targetProductionNumber = row.getAttribute("data-row-production") || productionNumber;
        const stateKey = row.getAttribute("data-state-key") || rowId;
        const storageKey = row.getAttribute("data-state-storage-key") || rowId;
        const sourceRowIds = (row.getAttribute("data-source-row-ids") || "")
          .split(",")
          .map((value) => String(value || "").trim())
          .filter(Boolean);
        if (!rowId) return;
        if (row.hasAttribute("data-issued-edit-alert")) {{
          event.preventDefault();
          event.stopPropagation();
          await completeIssuedEditAlert(targetProductionNumber, storageKey, currentDocKey);
          return;
        }}
        const currentState = row.getAttribute("data-pantolo-state") || selectionState[stateKey] || "";
        if (currentState === "done") {{
          return;
        }}
        if (String(currentDocument()?.key || "") === "topfloor" && /^\\d{{1,12}}$/.test(currentState)) {{
          return;
        }}
        if (row.hasAttribute("data-pantolo-unit")) {{
          const parentRowId = row.getAttribute("data-pantolo-parent-row-id") || "";
          if (currentState === "red") {{
            openRedChoiceModal({{ stateKey, storageKey, rowId, targetProductionNumber, sourceRowIds, pantoloUnitParentRowId: parentRowId }});
            return;
          }}
          applyPantoloUnitState(parentRowId, rowId, targetProductionNumber, nextRowState(currentState));
          return;
        }}
        if (row.hasAttribute("data-pantolo-group") && currentState === "mixed") {{
          openRedChoiceModal({{ stateKey, storageKey, rowId, targetProductionNumber, sourceRowIds, allowRed: true }});
          return;
        }}
        if (currentState === "red") {{
          openRedChoiceModal({{ stateKey, storageKey, rowId, targetProductionNumber, sourceRowIds }});
          return;
        }}
        applyRowState(stateKey, storageKey, rowId, targetProductionNumber, nextRowState(currentState), sourceRowIds);
      }});

      contentNode.addEventListener("input", (event) => {{
        const input = event.target.closest("[data-partial-input]");
        if (!(input instanceof HTMLInputElement)) return;
        event.stopPropagation();
        const stateKey = String(input.getAttribute("data-partial-key") || "").trim();
        const targetProductionNumber = String(input.getAttribute("data-row-production") || productionNumber || "").trim();
        if (!stateKey || !targetProductionNumber) return;
        const normalizedValue = String(input.value || "").replace(/[^0-9]/g, "").slice(0, 4);
        if (input.value !== normalizedValue) input.value = normalizedValue;
        queuePartialQuantitySave(targetProductionNumber, stateKey, normalizedValue);
      }});

      contentNode.addEventListener("change", (event) => {{
        const select = event.target.closest("[data-topfloor-box-type]");
        if (!(select instanceof HTMLSelectElement)) return;
        const categoryNode = select.closest("[data-topfloor-category]");
        const issueButton = categoryNode?.querySelector('[data-topfloor-action="issue-storage-box"]');
        if (issueButton instanceof HTMLButtonElement) {{
          issueButton.disabled = String(select.value || "").trim() === "Válassz dobozt!";
        }}
      }});

      choiceModalNode.addEventListener("click", (event) => {{
        const actionButton = event.target.closest("[data-choice-action]");
        if (actionButton instanceof HTMLElement) {{
          const action = actionButton.getAttribute("data-choice-action") || "";
          const currentChoice = pendingRedChoice;
          closeRedChoiceModal();
          if (!currentChoice) return;
          const targetState = action === "green" ? "green" : (action === "red" ? "red" : "clear");
          if (currentChoice.pantoloUnitParentRowId) {{
            applyPantoloUnitState(
              currentChoice.pantoloUnitParentRowId,
              currentChoice.rowId,
              currentChoice.targetProductionNumber,
              targetState,
            );
            return;
          }}
          applyRowState(
            currentChoice.stateKey,
            currentChoice.storageKey,
            currentChoice.rowId,
            currentChoice.targetProductionNumber,
            targetState,
            currentChoice.sourceRowIds || [],
          );
          return;
        }}
        if (event.target === choiceModalNode) {{
          closeRedChoiceModal();
        }}
      }});

      creatorModalNode.addEventListener("click", (event) => {{
        const actionButton = event.target.closest("[data-creator-action]");
        if (!(actionButton instanceof HTMLElement)) return;
        const creator = String(actionButton.getAttribute("data-creator-action") || "").trim();
        creatorModalNode.hidden = true;
        if (typeof pendingCreatorResolve === "function") {{
          const resolve = pendingCreatorResolve;
          pendingCreatorResolve = null;
          resolve(creator || "");
        }}
      }});

      confirmModalNode.addEventListener("click", (event) => {{
        const actionButton = event.target.closest("[data-confirm-action]");
        if (actionButton instanceof HTMLElement) {{
          const action = actionButton.getAttribute("data-confirm-action") || "";
          closeConfirmModal(action === "confirm");
          return;
        }}
        if (event.target === confirmModalNode) {{
          closeConfirmModal(false);
        }}
      }});

      reportReadyButtonNode.addEventListener("click", async () => {{
        const document = currentDocument();
        const canReportReady = canReportReadyForCurrentView(document);
        if (!canReportReady || reportReadyButtonNode.disabled) return;
        const isConfirmed = await requestConfirmModal();
        if (!isConfirmed) return;
        await flushPendingWrites();
        if (pendingWriteCount()) {{
          setStatus("F\u00fcgg\u0151 ment\u00e9sek vannak. K\u00e9szre jelent\u00e9s el\u0151tt v\u00e1rd meg a kapcsolat vissza\u00e1ll\u00e1s\u00e1t.", "is-error");
          return;
        }}

        const visibleRows = filterGroupsBySearch(buildGroupsForView(document), document)
          .flatMap((group) => Array.isArray(group?.rows) ? group.rows : [])
          .filter((row) => isReadyGreenState(rowStateValue(row)));
        if (!visibleRows.length) {{
          setStatus("Nincs készre jelentendő zöld sor.", "is-error");
          return;
        }}

        const extractConCode = (row) => {{
          const joined = [row?.code, row?.detail, row?.row_id].map((value) => String(value || "")).join(" ");
          const match = joined.toUpperCase().match(/\\bCON\\D*?(\\d{{6,}})\\b/);
          return match ? `CON${{match[1]}}` : "";
        }};
        const documentKey = String(document?.key || "").trim();
        const categoryKey = String(currentViewKey || "").trim();
        const entries = visibleRows
          .filter((row) => !row?.isPantoloUnit && !isChildUnitRowId(row?.row_id))
          .map((row) => {{
            const rowId = String(row?.row_id || "").trim();
            const stateKey = String(rowStateKey(row) || "").trim();
            const stateStorageKey = String(rowStorageKey(row) || rowId).trim();
            const code = extractConCode(row);
            const explicitSourceRowIds = Array.isArray(row?.sourceRowIds)
              ? row.sourceRowIds.map((value) => String(value || "").trim()).filter((value) => value && !isChildUnitRowId(value))
              : [];
            const groupedSourceRowIds = isPantoloGroupedRow(row)
              ? Array.from({{ length: pantoloQuantity(row) }}, (_item, index) => childUnitStorageKey(row, index))
              : [];
            const sourceRowIds = Array.from(new Set([...explicitSourceRowIds, ...groupedSourceRowIds].filter(Boolean)));
            if (!rowId || !stateKey || !code) return null;
            return {{ row_id: rowId, state_key: stateKey, state_storage_key: stateStorageKey, code, document_key: documentKey, category_key: categoryKey, source_row_ids: sourceRowIds }};
          }})
          .filter(Boolean);
        if (!entries.length) {{
          setStatus("A zöld sorokhoz nem találtam érvényes CON kódot.", "is-error");
          return;
        }}

        reportReadyButtonNode.classList.add("is-loading");
        reportReadyButtonNode.disabled = true;
        setStatus("Készre jelentés folyamatban...");
        try {{
          const response = await fetch(reportReadyRoute, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              production_number: productionNumber,
              document_key: documentKey,
              category_key: categoryKey,
              entries,
            }}),
          }});
          const result = await response.json().catch(() => ({{}}));
          if (!response.ok) {{
            throw new Error(result.error || "A készre jelentés nem sikerült.");
          }}
          const doneRowIds = new Set(
            Array.isArray(result.done_row_ids)
              ? result.done_row_ids.map((value) => String(value || "").trim()).filter(Boolean)
              : []
          );
          const doneStateKeys = new Set(
            Array.isArray(result.done_state_keys)
              ? result.done_state_keys.map((value) => String(value || "").trim()).filter(Boolean)
              : []
          );
          for (const stateKey of doneStateKeys) {{
            const entry = entries.find((item) => String(item.state_storage_key || "") === stateKey);
            selectionState[String(entry?.state_key || stateKey)] = "done";
          }}
          for (const rowId of doneRowIds) {{
            selectionState[`${{productionNumber}}::${{rowId}}`] = "done";
          }}
          renderAll();
          const attemptedCount = Number.isFinite(Number(result.attempted_count)) ? Number(result.attempted_count) : entries.length;
          const successCount = Number.isFinite(Number(result.success_count)) ? Number(result.success_count) : doneRowIds.size;
          const failedCount = Number.isFinite(Number(result.failed_count)) ? Number(result.failed_count) : Math.max(0, attemptedCount - successCount);
          window.alert(`Készre jelentés összesítő\n\nPróbált csipogni: ${{attemptedCount}}\nSikerült: ${{successCount}}\nNem sikerült: ${{failedCount}}`);
          if (!result.ok) {{
            setStatus(result.error || `Készre jelentés részben sikerült: ${{successCount}} sikeres, ${{failedCount}} sikertelen.`, "is-error");
            return;
          }}
          setStatus("Készre jelentés sikeres. A tételek zárolva lettek.", "is-success");
        }} catch (error) {{
          setStatus(error instanceof Error ? error.message : "A készre jelentés nem sikerült.", "is-error");
        }} finally {{
          reportReadyButtonNode.classList.remove("is-loading");
          reportReadyButtonNode.disabled = false;
        }}
      }});

      applyStoredPendingWritesToLocalState();
      if (pendingWriteCount()) {{
        setStatus(pendingStatusText(), "is-error");
        void flushPendingWrites();
      }}
      window.addEventListener("scroll", schedulePantoloSectionHeaders, {{ passive: true }});
      window.addEventListener("resize", schedulePantoloSectionHeaders);
      const initialRenderStartedAt = performance.now();
      shopfloorLog("initial render start", shopfloorPayloadStats(payload));
      renderAll();
      shopfloorLog(`initial render done took=${{shopfloorSeconds(initialRenderStartedAt)}}s`, shopfloorPayloadStats(payload));
    }})();
  </script>
  <script src="/script.js"></script>
</body>
</html>"""
    return page.encode("utf-8")
