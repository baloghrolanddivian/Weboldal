"""HTML page rendering for the Matt inventory value workflow."""

from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal

from .config import alert_workbook_path, render_layout, report_path
from .engine import load_report_from_path
from .jobs import _matt_inventory_saved_price_name, _matt_inventory_saved_stock_name
from .routes import MATT_INVENTORY_DOWNLOAD_ROUTE, MATT_INVENTORY_PROCESS_ROUTE


def _format_eu_number(value: float, decimals: int = 2) -> str:
    """Format format eu number values for display or export."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")

def _matt_inventory_format_money(value: Decimal | float | int) -> str:
    """Format a value as a whole-forint amount for the report UI."""
    number = float(value or 0)
    return f"{_format_eu_number(number, 0)} Ft"

def _matt_inventory_format_quantity(value: Decimal | float | int) -> str:
    """Format a stock quantity with db suffix and Hungarian decimals."""
    number = float(value or 0)
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number))} db"
    return f"{_format_eu_number(number, 2)} db"

def _matt_inventory_format_generated_at(value: str) -> str:
    """Format the persisted ISO timestamp for display."""
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    try:
        parsed = datetime.fromisoformat(clean_value)
    except ValueError:
        return clean_value
    return parsed.strftime("%Y.%m.%d. %H:%M")

def render_matt_inventory_form(message: str = "", success: bool = False) -> bytes:
    """Render the Matt inventory upload/report page."""
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    report = load_report_from_path(report_path())
    saved_price_name = _matt_inventory_saved_price_name()
    saved_stock_name = _matt_inventory_saved_stock_name()

    report_html = """
      <section class="matt-report-card is-empty">
        <div class="matt-report-empty">
          <strong>Még nincs napi matt készletérték.</strong>
          <p>Töltsd fel a fix ártáblát és az aktuális készletfájlt, utána itt jelenik meg a kompakt összesítő.</p>
        </div>
      </section>
    """
    if report is not None:
        rows_html = "".join(
            f"""
              <tr>
                <td>
                  <strong>{html.escape(group.family)}</strong>
                </td>
                <td><span class="matt-color-cell">{html.escape(group.color)}</span></td>
                <td>{html.escape(_matt_inventory_format_quantity(group.quantity))}</td>
                <td class="value-cell">{html.escape(_matt_inventory_format_money(group.total_value))}</td>
              </tr>
            """
            for group in report.groups
        )
        missing_html = ""
        if report.missing_codes:
            preview = ", ".join(html.escape(code) for code in report.missing_codes[:6])
            extra = ""
            if len(report.missing_codes) > 6:
                extra = f" +{len(report.missing_codes) - 6} további"
            missing_html = f"""
              <div class="matt-warning">
                <strong>Hiányzó anyagköltség</strong>
                <p>Ezekhez a cikkszámokhoz nincs ár a fix táblában: {preview}{html.escape(extra)}</p>
              </div>
            """

        report_html = f"""
          <section class="matt-report-card">
            <div class="matt-report-head">
              <div class="matt-head-copy">
                <span class="matt-tag">Napi összesítő</span>
                <strong>Matt front raktárérték</strong>
                <p>Forrás: {html.escape(report.stock_source_name)} · Árforrás: {html.escape(report.price_source_name)}</p>
              </div>
              <div class="matt-head-side">
                <div class="matt-report-stamp">{html.escape(_matt_inventory_format_generated_at(report.generated_at))}</div>
                <div class="matt-head-caption">Napi készletből frissítve</div>
              </div>
            </div>

            <div class="matt-stats">
              <article>
                <span>Összérték</span>
                <strong>{html.escape(_matt_inventory_format_money(report.total_value))}</strong>
              </article>
              <article>
                <span>Összes darab</span>
                <strong>{html.escape(_matt_inventory_format_quantity(report.total_quantity))}</strong>
              </article>
              <article>
                <span>Színcsoport</span>
                <strong>{len(report.groups)}</strong>
              </article>
              <article>
                <span>Talált cikkszám</span>
                <strong>{report.matched_row_count}</strong>
              </article>
            </div>

            <div class="matt-thresholds">
              <article class="matt-threshold-card is-safety">
                <span>Biztonsági készlet felett</span>
                <strong>{report.safety_exceeded_count} front</strong>
                <p>Azok a frontok, ahol a bent maradt készlet már a biztonsági szint fölött van.</p>
              </article>
              <article class="matt-threshold-card is-storage">
                <span>Tárolható mennyiség felett</span>
                <strong>{report.storage_exceeded_count} front</strong>
                <p>Azok a frontok, amelyekből több van bent, mint a tárolható mennyiség.</p>
              </article>
              <article class="matt-threshold-card is-action">
                <span>Küszöbriport</span>
                <strong>Excel export</strong>
                <p>Két munkalapon adja le a biztonsági és tárolható mennyiség feletti frontokat.</p>
                <a class="button button-primary matt-download-button" href="{MATT_INVENTORY_DOWNLOAD_ROUTE}">Riport letöltése</a>
              </article>
            </div>

            <div class="matt-table-wrap">
              <table class="matt-table">
                <thead>
                  <tr>
                    <th>Modell</th>
                    <th>Szín</th>
                    <th>Darabszám</th>
                    <th>Raktárérték</th>
                  </tr>
                </thead>
                <tbody>
                  {rows_html}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Összesen</td>
                    <td>—</td>
                    <td>{html.escape(_matt_inventory_format_quantity(report.total_quantity))}</td>
                    <td class="value-cell">{html.escape(_matt_inventory_format_money(report.total_value))}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            {missing_html}
            <div class="matt-generated-by">generated by Divian-HUB</div>
          </section>
        """

    price_meta_html = ""
    if saved_price_name:
        price_meta_html = f'<div class="matt-meta-chip">Aktív fix árforrás: {html.escape(saved_price_name)}</div>'

    stock_meta_html = ""
    if saved_stock_name:
        stock_meta_html = f'<div class="matt-meta-chip">Utolsó készletállás: {html.escape(saved_stock_name)}</div>'

    content_html = f"""
      <div class="matt-shell">
        <section class="matt-upload-card">
          <div class="matt-upload-head">
            <div class="matt-copy">
              <span class="matt-tag">Napi készletérték</span>
              <strong>Matt front raktárérték.</strong>
              <p>Feltöltöd a fix anyagköltség táblát és a napi készletállást, a rendszer pedig front- és színszinten összesíti a bent maradt értéket.</p>
            </div>
            <div class="matt-visual" aria-hidden="true">
              <div class="matt-visual-pill">Fix ár</div>
              <div class="matt-visual-line"></div>
              <div class="matt-visual-pill">Napi állás</div>
              <div class="matt-visual-line"></div>
              <div class="matt-visual-pill is-strong">Érték</div>
            </div>
          </div>

          <div class="matt-meta-row">
            {price_meta_html}
            {stock_meta_html}
          </div>

          <form class="matt-upload-form" method="post" action="{MATT_INVENTORY_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="matt-upload-grid">
              <label class="matt-field">
                <span>Fix ártábla</span>
                <strong>Alkatrészszám + anyagköltség</strong>
                <input type="file" name="price_file" accept=".xls,.xlsx,.xlsm,.csv" />
                <small>Első alkalommal kötelező. Utána csak akkor töltsd újra, ha frissült.</small>
              </label>

              <label class="matt-field">
                <span>Napi készlet</span>
                <strong>Alkatrészszám + leírás + mennyiség + szín</strong>
                <input type="file" name="stock_file" accept=".xls,.xlsx,.xlsm,.csv" required />
                <small>Ezt elég naponta frissíteni az aktuális állással.</small>
              </label>
            </div>

            <div class="matt-action-row">
              <span class="inline-note">A fix árforrás megmarad, így napi használatra elég az aktuális készletfájlt feltölteni.</span>
              <button class="button button-primary matt-submit-button" type="submit">Érték kiszámítása</button>
            </div>
          </form>
        </section>

        {report_html}
      </div>
    """

    extra_script = """
<style>
  .matt-shell {
    display: grid;
    gap: 18px;
  }
  .matt-upload-card,
  .matt-report-card {
    position: relative;
    overflow: hidden;
    border-radius: 28px;
    border: 1px solid rgba(7, 16, 24, 0.08);
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    color: #0f172a;
    box-shadow: 0 20px 44px rgba(10, 18, 30, 0.08);
  }
  .matt-upload-card::before,
  .matt-report-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top right, rgba(15, 23, 42, 0.04), transparent 28%);
    pointer-events: none;
  }
  .matt-upload-card {
    padding: 22px;
  }
  .matt-upload-head {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
    gap: 20px;
  }
  .matt-copy {
    display: grid;
    gap: 10px;
    max-width: 660px;
  }
  .matt-copy strong,
  .matt-report-head strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.35rem, 2.8vw, 2rem);
    line-height: 1;
    color: #0f172a;
  }
  .matt-copy p,
  .matt-report-head p,
  .matt-field small,
  .matt-report-stamp,
  .matt-generated-by,
  .matt-warning p {
    margin: 0;
    color: #5b6777;
    line-height: 1.55;
  }
  .matt-tag {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    min-height: 28px;
    padding: 0 12px;
    border-radius: 999px;
    background: #eef2ff;
    color: #243b53;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-visual {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-visual-pill {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid rgba(15, 23, 42, 0.1);
    background: #ffffff;
    color: #334155;
    font-size: 0.82rem;
    font-weight: 700;
  }
  .matt-visual-pill.is-strong {
    background: #0f172a;
    border-color: #0f172a;
    color: #ffffff;
  }
  .matt-visual-line {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(15, 23, 42, 0.2), rgba(15, 23, 42, 0.55));
  }
  .matt-meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 16px;
  }
  .matt-meta-chip {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 999px;
    background: #f8fafc;
    border: 1px solid rgba(15, 23, 42, 0.08);
    color: #475569;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .matt-upload-form {
    display: grid;
    gap: 14px;
    margin-top: 18px;
  }
  .matt-upload-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }
  .matt-field {
    display: grid;
    gap: 8px;
    padding: 16px 18px;
    border-radius: 20px;
    background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-field span {
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-field strong {
    color: #0f172a;
    font-size: 1rem;
  }
  .matt-field input[type="file"] {
    width: 100%;
    min-height: 54px;
    padding: 14px 16px;
    border-radius: 16px;
    border: 1px dashed rgba(15, 23, 42, 0.18);
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    color: #0f172a;
  }
  .matt-action-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 4px;
    padding: 6px 2px 0;
  }
  .matt-submit-button {
    min-width: 210px;
    min-height: 52px;
    border-radius: 16px;
    box-shadow: 0 14px 28px rgba(15, 23, 42, 0.18);
  }
  .matt-report-card {
    padding: 22px;
  }
  .matt-report-head {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
  }
  .matt-report-stamp {
    white-space: nowrap;
    font-size: 0.85rem;
    font-weight: 700;
  }
  .matt-head-copy {
    display: grid;
    gap: 10px;
  }
  .matt-head-side {
    display: grid;
    justify-items: end;
    gap: 6px;
    padding: 10px 14px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(15, 23, 42, 0.08);
  }
  .matt-head-caption {
    color: #64748b;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .matt-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .matt-stats article {
    padding: 16px;
    border-radius: 20px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: grid;
    gap: 6px;
  }
  .matt-stats span {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .matt-stats strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.18rem;
  }
  .matt-table-wrap {
    margin-top: 16px;
    overflow: auto;
    border-radius: 20px;
    border: 1px solid rgba(15, 23, 42, 0.08);
    background: #ffffff;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  }
  .matt-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 640px;
  }
  .matt-table thead th {
    padding: 14px 18px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.08);
    background: #f8fafc;
    color: #475569;
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-align: left;
    white-space: nowrap;
  }
  .matt-table tbody td,
  .matt-table tfoot td {
    padding: 16px 18px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    color: #0f172a;
    vertical-align: middle;
  }
  .matt-table tbody tr:nth-child(2n) {
    background: rgba(248, 250, 252, 0.7);
  }
  .matt-table tbody td:first-child strong {
    display: block;
    font-size: 0.98rem;
  }
  .matt-color-cell {
    display: inline-block;
    color: #64748b;
    font-size: 0.92rem;
    font-weight: 600;
  }
  .matt-table .value-cell {
    font-weight: 800;
    white-space: nowrap;
  }
  .matt-table tfoot td {
    background: #f8fafc;
    font-weight: 800;
  }
  .matt-warning {
    margin-top: 14px;
    padding: 14px 16px;
    border-radius: 18px;
    border: 1px solid rgba(220, 38, 38, 0.16);
    background: rgba(254, 242, 242, 0.9);
  }
  .matt-warning strong {
    display: block;
    margin-bottom: 4px;
    color: #991b1b;
  }
  .matt-generated-by {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px dashed rgba(15, 23, 42, 0.12);
    text-align: right;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .matt-thresholds {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;
  }
  .matt-threshold-card {
    padding: 14px 16px;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
    display: grid;
    gap: 5px;
    align-content: start;
    min-height: 148px;
  }
  .matt-threshold-card span {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .matt-threshold-card strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.02rem;
  }
  .matt-threshold-card p {
    margin: 0;
    color: #64748b;
    line-height: 1.45;
    font-size: 0.86rem;
  }
  .matt-threshold-card.is-safety {
    background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  }
  .matt-threshold-card.is-storage {
    background: linear-gradient(180deg, #ffffff 0%, #fffaf5 100%);
  }
  .matt-threshold-card.is-action {
    background: linear-gradient(180deg, #0f172a 0%, #162033 100%);
    border-color: rgba(15, 23, 42, 0.55);
  }
  .matt-threshold-card.is-action span,
  .matt-threshold-card.is-action strong,
  .matt-threshold-card.is-action p {
    color: #ffffff;
  }
  .matt-download-button {
    min-height: 50px;
    width: 100%;
    justify-content: center;
    margin-top: 10px;
    border-radius: 14px;
    box-shadow: 0 16px 28px rgba(15, 23, 42, 0.18);
  }
  .matt-report-card.is-empty {
    padding: 32px 24px;
  }
  .matt-report-empty {
    display: grid;
    gap: 8px;
  }
  .matt-report-empty strong {
    color: #0f172a;
    font-family: "Space Grotesk", sans-serif;
    font-size: 1.2rem;
  }
  @media (max-width: 900px) {
    .matt-upload-head,
    .matt-report-head {
      grid-template-columns: minmax(0, 1fr);
      display: grid;
    }
    .matt-upload-grid,
    .matt-thresholds {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-visual {
      flex-wrap: wrap;
      width: fit-content;
    }
    .matt-stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .matt-head-side {
      justify-items: start;
    }
  }
  @media (max-width: 640px) {
    .matt-upload-card,
    .matt-report-card {
      border-radius: 22px;
    }
    .matt-upload-card {
      padding: 18px;
    }
    .matt-report-card {
      padding: 18px;
    }
    .matt-stats {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-upload-grid {
      grid-template-columns: minmax(0, 1fr);
    }
    .matt-action-row .button {
      width: 100%;
    }
    .matt-download-button {
      width: 100%;
      justify-content: center;
    }
    .matt-submit-button {
      min-width: 0;
    }
  }
</style>
"""

    return render_layout(
        heading="Napi matt front készletérték",
        lead="Fix árforrásból és napi készletállásból kiszámolt, kompakt raktárérték összesítő.",
        intro_label="Value snapshot",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )

