"""HTML page rendering for the NettFront order suggestion workflow."""

from __future__ import annotations

import html

from .config import render_layout
from .jobs import (
    _count_positive_order_rows,
    _format_order_input_value,
    _format_order_metric,
    _order_safe_number,
    _read_nettfront_order_rows,
    read_order_job,
)
from .engine import calc_total_m2_from_rows
from .import_helper import get_procurement_helper_state
from .routes import (
    NETTFRONT_ORDER_APPROVE_PREFIX,
    NETTFRONT_ORDER_DOWNLOAD_PREFIX,
    NETTFRONT_ORDER_LAUNCH_PREFIX,
    NETTFRONT_ORDER_PROCESS_ROUTE,
    NETTFRONT_ORDER_ROUTE,
    NETTFRONT_ORDER_STOP_PREFIX,
)


def render_nettfront_order_form(message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    content_html = f"""
      <div class="order-shell">
        <section class="order-hero-card">
          <div class="order-hero-grid">
            <div class="order-copy">
              <div class="tag">Excel -> rendelési javaslat</div>
              <strong>NettFront rendelési javaslat.</strong>
              <p>Feltöltöd a raktár Excelt, átnézed a javasolt darabszámokat, majd jóváhagyod a kész rendelést.</p>
              <div class="order-flow" aria-hidden="true">
                <span>Excel</span>
                <i></i>
                <span>Javaslat</span>
                <i></i>
                <span>Kész rendelés</span>
              </div>
            </div>

            <div class="order-visual" aria-hidden="true">
              <div class="order-visual-list">
                <div class="order-visual-row">
                  <span>Excel</span>
                  <i></i>
                  <strong>Beolvasás</strong>
                </div>
                <div class="order-visual-row">
                  <span>Javaslat</span>
                  <i></i>
                  <strong>Ellenőrzés</strong>
                </div>
                <div class="order-visual-row">
                  <span>Rendelés</span>
                  <i></i>
                  <strong>Jóváhagyás</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="order-upload-card">
          <div class="order-upload-head">
            <strong>Feltöltés</strong>
            <p>Egy raktár Excel kell. A rendszer kiszámolja a rendelési javaslatot.</p>
          </div>

          <form id="nettfront-order-form" class="order-upload-form" method="post" action="{NETTFRONT_ORDER_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="order-dropzone" id="nettfront-order-dropzone">
              <input
                id="nettfront-order-stock"
                class="order-file-input"
                type="file"
                name="stock_file"
                accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                required
              />
              <label class="order-dropzone-surface" for="nettfront-order-stock">
                <div class="order-dropzone-copy">
                  <span class="order-dropzone-chip">Excel</span>
                  <strong>Raktárfájl kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                  <div class="order-columns-note">
                    <span class="order-columns-title">Szükséges oszlopok</span>
                    <span><code>Alkatr.szám</code>, <code>Alkatr.leírás</code>, <code>Rend.áll.rakt.készl. ME</code>, <code>Rend.áll</code>, <code>Biztonsági készlet</code>, <code>Tárolh.menny.</code></span>
                  </div>
                </div>
                <span class="order-file-state" id="nettfront-order-stock-state">Támogatott formátum: XLSX, XLSM, CSV</span>
              </label>
            </div>

            <div class="order-optional-upload">
              <div class="order-optional-copy">
                <strong>Friss alkatrészlista</strong>
                <p>Opcionális egyoszlopos lista. A jóváhagyásnál ebből ellenőrizzük a kiválasztott cikkszámokat, hogy a kész rendelés bevételezhető legyen.</p>
              </div>

              <div class="order-dropzone is-secondary" id="nettfront-order-parts-dropzone">
                <input
                  id="nettfront-order-parts"
                  class="order-file-input"
                  type="file"
                  name="parts_file"
                  accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                />
                <label class="order-dropzone-surface" for="nettfront-order-parts">
                  <div class="order-dropzone-copy">
                    <span class="order-dropzone-chip">Opcionális</span>
                    <strong>Friss lista kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                    <div class="order-columns-note">
                      <span class="order-columns-title">Elvárt tartalom</span>
                      <span>Egyszerű, egyoszlopos cikkszámlista. Az első oszlopban csak az alkatrészszámok szerepeljenek.</span>
                    </div>
                  </div>
                  <span class="order-file-state" id="nettfront-order-parts-state">Támogatott formátum: XLSX, XLSM, CSV</span>
                </label>
              </div>
            </div>

            <div class="order-action-row">
              <button class="button button-primary" type="submit" id="nettfront-order-submit">Javaslat készítése</button>
              <span class="inline-note">A kész lista külön oldalon nyílik meg, ott tudod jóváhagyni.</span>
            </div>
          </form>
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-shell {
    display: grid;
    gap: 16px;
  }
  .order-hero-card,
  .order-upload-card {
    position: relative;
    overflow: hidden;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-hero-card::before,
  .order-upload-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top left, rgba(67, 222, 207, 0.1), transparent 32%);
    pointer-events: none;
  }
  .order-hero-grid {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
    gap: 16px;
    align-items: stretch;
    padding: 24px;
  }
  .order-copy {
    display: grid;
    gap: 12px;
    align-content: start;
  }
  .order-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.7rem, 3.8vw, 2.5rem);
    line-height: 1;
  }
  .order-copy p,
  .order-upload-head p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    max-width: 58ch;
  }
  .order-flow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 2px;
    color: var(--muted);
    font-size: 0.84rem;
  }
  .order-flow span {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.035);
  }
  .order-flow i {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.18), rgba(67, 222, 207, 0.62));
  }
  .order-visual {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 212px;
    padding: 18px;
    border-radius: 22px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.02));
  }
  .order-visual-list {
    display: grid;
    gap: 12px;
    width: min(100%, 240px);
  }
  .order-visual-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    align-items: center;
    min-height: 56px;
    padding: 0 16px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-visual-row span {
    color: var(--muted);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-visual-row i {
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.16), rgba(67, 222, 207, 0.56));
  }
  .order-visual-row strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.94rem;
    font-weight: 600;
  }
  .order-upload-card {
    padding: 22px;
  }
  .order-upload-head {
    display: grid;
    gap: 6px;
    margin-bottom: 14px;
  }
  .order-upload-head strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-upload-form {
    display: grid;
    gap: 16px;
  }
  .order-optional-upload {
    display: grid;
    gap: 12px;
    padding: 16px;
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.025);
  }
  .order-optional-copy {
    display: grid;
    gap: 6px;
  }
  .order-optional-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.96rem;
  }
  .order-optional-copy p {
    margin: 0;
    color: var(--muted);
    line-height: 1.5;
  }
  .order-dropzone {
    position: relative;
  }
  .order-dropzone.is-secondary .order-dropzone-surface {
    min-height: 138px;
    padding: 18px 20px;
    border-radius: 20px;
    border-style: solid;
    border-color: rgba(255, 255, 255, 0.1);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.012));
  }
  .order-file-input {
    position: absolute;
    inset: 0;
    opacity: 0;
    pointer-events: none;
  }
  .order-dropzone-surface {
    display: grid;
    gap: 14px;
    min-height: 176px;
    padding: 22px;
    border-radius: 24px;
    border: 1px dashed rgba(67, 222, 207, 0.24);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.016));
    cursor: pointer;
    transition:
      border-color 180ms ease,
      transform 180ms ease,
      box-shadow 180ms ease;
  }
  .order-dropzone.is-dragover .order-dropzone-surface,
  .order-dropzone-surface:hover {
    border-color: rgba(67, 222, 207, 0.42);
    transform: translateY(-1px);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.22);
  }
  .order-dropzone-copy {
    display: grid;
    gap: 8px;
    justify-items: start;
  }
  .order-columns-note {
    display: grid;
    gap: 4px;
    margin-top: 4px;
    padding: 10px 12px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.45;
  }
  .order-columns-title {
    color: var(--text);
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .order-dropzone-chip {
    display: inline-flex;
    align-items: center;
    min-height: 30px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.04);
    color: var(--muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .order-dropzone-copy strong {
    font-size: 1rem;
  }
  .order-file-state {
    font-size: 0.9rem;
    color: var(--muted);
  }
  .order-action-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  @media (max-width: 960px) {
    .order-hero-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-hero-grid,
    .order-upload-card {
      padding: 18px;
    }
    .order-dropzone-surface {
      min-height: 156px;
      padding: 18px;
    }
    .order-action-row {
      align-items: stretch;
      flex-direction: column;
    }
    .order-action-row .button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const stockInput = document.getElementById("nettfront-order-stock");
    const stockState = document.getElementById("nettfront-order-stock-state");
    const stockDropzone = document.getElementById("nettfront-order-dropzone");
    const partsInput = document.getElementById("nettfront-order-parts");
    const partsState = document.getElementById("nettfront-order-parts-state");
    const partsDropzone = document.getElementById("nettfront-order-parts-dropzone");
    const form = document.getElementById("nettfront-order-form");
    const submitButton = document.getElementById("nettfront-order-submit");
    if (!stockInput || !stockState || !stockDropzone || !partsInput || !partsState || !partsDropzone || !form || !submitButton) return;

    const updateState = (input, state, emptyLabel) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyLabel;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    const bindDropzone = (dropzone) => {
      ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.add("is-dragover");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.remove("is-dragover");
        });
      });
    };

    bindDropzone(stockDropzone);
    bindDropzone(partsDropzone);

    stockInput.addEventListener("change", () => updateState(stockInput, stockState, "Támogatott formátum: XLSX, XLSM, CSV"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLSX, XLSM, CSV"));
    form.addEventListener("submit", () => {
      submitButton.textContent = "Javaslat készül...";
      submitButton.disabled = true;
    });
  })();
</script>
"""

    return render_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_order_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    job_dir, _ = read_order_job(job_id)
    rows = _read_nettfront_order_rows(job_dir) if job_dir is not None else []
    suggestion_count = len(rows)
    positive_count = _count_positive_order_rows(rows)
    total_m2 = calc_total_m2_from_rows(rows)
    approved_file = str(metadata.get("approved_file", "")).strip()
    approved_ready = bool(approved_file and job_dir is not None and (job_dir / approved_file).exists())
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    import_file = str(metadata.get("import_file", "")).strip()
    import_ready = bool(import_file and job_dir is not None and (job_dir / import_file).exists())
    source_stock_name = str(metadata.get("source_stock_name", "")).strip() or "Feltöltött raktárfájl"
    source_parts_name = str(metadata.get("source_parts_name", "")).strip() or str(metadata.get("source_average_name", "")).strip()
    source_parts_count = int(metadata.get("source_parts_count", 0) or 0)

    table_html = """
      <div class="order-empty-state">
        <strong>Nincs rendelési javaslat.</strong>
        <p>A feltöltött fájl alapján most nem találtam rendelésre váró tételt.</p>
      </div>
    """
    if rows:
        row_html = []
        for row in rows:
            description = html.escape(row.description or "Megnevezés nélkül")
            display_part_number = _nettfront_order_display_part_number(row.part_number)
            part_number = html.escape(display_part_number or row.part_number or "Nincs cikkszám")
            color_value = html.escape(row.color.strip() or "Nincs színadat")
            current_stock = html.escape(_format_order_metric(row.current_stock))
            safe_stock = html.escape(_format_order_metric(row.safe_stock))
            capacity = html.escape(_format_order_metric(row.capacity))
            qty_value = html.escape(_format_order_input_value(row.order_qty))
            super_matt_html = '<span class="order-inline-badge">SM</span>' if row.is_super_matt else ""
            row_html.append(
                f"""
                <tr>
                  <td>
                    <div class="order-item-main">
                      <strong>{description}</strong>
                      <span>{part_number}</span>
                    </div>
                  </td>
                  <td>
                    <div class="order-color-stack">
                      <span class="order-color-text">{color_value}</span>
                      {super_matt_html}
                    </div>
                  </td>
                  <td class="is-metric">{current_stock}</td>
                  <td class="is-metric">{safe_stock}</td>
                  <td class="is-metric">{capacity}</td>
                  <td>
                    <input
                      class="order-qty-input"
                      type="text"
                      inputmode="decimal"
                      name="qty__{html.escape(row.row_id)}"
                      value="{qty_value}"
                    />
                  </td>
                </tr>
                """
            )
        table_html = f"""
          <form method="post" action="{NETTFRONT_ORDER_APPROVE_PREFIX}/{job_id}">
            <div class="order-table-wrap">
              <table class="order-table">
                <thead>
                  <tr>
                    <th>Tétel</th>
                    <th>Szín</th>
                    <th class="is-metric">Rend.áll</th>
                    <th class="is-metric">Biztonsági</th>
                    <th class="is-metric">Tárolható</th>
                    <th class="is-metric">Rendelés</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(row_html)}
                </tbody>
              </table>
            </div>

            <div class="order-approve-bar">
              <span class="inline-note">A 0 mennyiség azt jelenti, hogy az adott tétel nem kerül be a kész rendelésbe.</span>
              <button class="button button-primary" type="submit">Jóváhagyás és kész rendelés</button>
            </div>
          </form>
        """

    helper_action_html = ""
    helper_hint_html = ""
    if approved_ready and import_ready:
        if helper_running:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_STOP_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Leállítás</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A bevételezési segéd fut. Nyisd meg a bevételezési ablakot, majd Shift + Space indítja az importot. Kilépés: ESC.</p>'
        else:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_LAUNCH_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Bevételezés indítása</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A kész rendelés bevételezhető. Indítsd a segédet, majd a bevételezési ablakban Shift + Space indítja az importot. Kilépés: ESC.</p>'

    content_html = f"""
      <div class="order-result-shell">
        <section class="order-result-card">
          <div class="order-result-head">
            <div class="tag">Rendelési javaslat</div>
            <strong>Átnézés után egy gombbal kész rendelés lesz belőle.</strong>
            <p>{html.escape(source_stock_name)}</p>
          </div>

          <div class="order-summary-grid">
            <article class="order-summary-card">
              <strong>{suggestion_count}</strong>
              <span>javasolt tétel</span>
            </article>
            <article class="order-summary-card">
              <strong>{positive_count}</strong>
              <span>jóváhagyásra kész sor</span>
            </article>
            <article class="order-summary-card">
              <strong>{html.escape(_format_order_metric(total_m2))}</strong>
              <span>becsült összes m²</span>
            </article>
          </div>

          <div class="order-meta-strip">
            <span>Összevont variánsok: {metadata.get("merged_variant_count", 0)}</span>
            <span>Küszöb alatti tételek: {metadata.get("filtered_stock_count", 0)}</span>
            <span>SM sorok: {metadata.get("added_super_matt_count", 0)}</span>
            <span>Átlagolt alkatrészek: {metadata.get("avg_row_count", 0)}</span>
            {"<span>Friss alkatrészlista: " + html.escape(source_parts_name) + (f' • {source_parts_count} tétel' if source_parts_count else '') + "</span>" if source_parts_name else ""}
            {"<span>Bevételezési segéd fut</span>" if helper_running else ""}
          </div>

          <div class="order-toolbar">
            <button class="button button-secondary order-toggle-button" type="button" id="order-table-toggle">Javaslat megmutatása</button>
            <a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/suggestion-xlsx">Javaslat letöltése</a>
            {f'<a class="button button-primary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/approved-xlsx">Kész rendelés letöltése</a>' if approved_ready else ''}
            {f'<a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/import-csv">Bevételezési lista</a>' if import_ready else ''}
            {helper_action_html}
            <a class="button button-secondary" href="{NETTFRONT_ORDER_ROUTE}">Új feltöltés</a>
          </div>
          {helper_hint_html}
        </section>

        <section class="order-table-card" id="order-table-card" hidden>
          <div class="order-result-head">
            <strong>Rendelési javaslat</strong>
            <p>Itt módosíthatod a mennyiségeket, majd jóváhagyhatod a kész rendelést.</p>
          </div>
          {table_html}
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-result-card,
  .order-table-card {
    position: relative;
    overflow: hidden;
    padding: 22px;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-result-shell {
    display: grid;
    gap: 16px;
  }
  .order-result-head,
  .order-item-main,
  .order-empty-state {
    display: grid;
    gap: 6px;
  }
  .order-result-head strong,
  .order-summary-card strong,
  .order-item-main strong,
  .order-empty-state strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-result-head p,
  .order-summary-card span,
  .order-meta-strip span,
  .order-item-main span,
  .order-empty-state p {
    margin: 0;
    color: var(--muted);
  }
  .order-summary-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 6px;
  }
  .order-summary-card {
    padding: 16px 18px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-summary-card strong {
    display: block;
    margin-bottom: 4px;
    font-size: 1.65rem;
    line-height: 1;
  }
  .order-meta-strip,
  .order-toolbar,
  .order-approve-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .order-meta-strip {
    gap: 8px 14px;
    padding-top: 2px;
    color: var(--muted);
  }
  .order-meta-strip span {
    font-size: 0.88rem;
  }
  .order-toolbar {
    margin-top: 4px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .order-helper-copy {
    margin: 10px 0 0;
    color: var(--muted);
    line-height: 1.55;
  }
  .order-toggle-button {
    min-width: 200px;
  }
  .order-table-wrap {
    overflow: auto;
    margin-top: 14px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(7, 12, 20, 0.84);
  }
  .order-table {
    width: 100%;
    min-width: 860px;
    border-collapse: collapse;
    background: transparent;
  }
  .order-table th,
  .order-table td {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.045);
    text-align: left;
    vertical-align: middle;
  }
  .order-table th {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-soft);
    font-size: 0.76rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-table th.is-metric,
  .order-table td.is-metric {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .order-table tbody tr:nth-child(odd) td {
    background: rgba(255, 255, 255, 0.012);
  }
  .order-table tbody tr:nth-child(even) td {
    background: rgba(255, 255, 255, 0.022);
  }
  .order-table tbody tr:hover {
    background: transparent;
  }
  .order-table tbody tr:hover td {
    background: rgba(255, 255, 255, 0.05);
  }
  .order-item-main strong {
    font-size: 0.96rem;
    line-height: 1.35;
  }
  .order-item-main span {
    font-size: 0.82rem;
  }
  .order-color-stack {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .order-color-text {
    color: var(--text);
    line-height: 1.45;
  }
  .order-inline-badge {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 0 8px;
    border-radius: 999px;
    background: rgba(67, 222, 207, 0.1);
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .order-qty-input {
    width: 96px;
    min-height: 42px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
    font: inherit;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .order-qty-input:focus {
    outline: none;
    border-color: rgba(67, 222, 207, 0.48);
    box-shadow: 0 0 0 4px rgba(67, 222, 207, 0.12);
  }
  .order-empty-state {
    padding: 20px;
    border-radius: 18px;
    border: 1px dashed rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-approve-bar {
    justify-content: space-between;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  @media (max-width: 960px) {
    .order-summary-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-result-card,
    .order-table-card {
      padding: 18px;
    }
    .order-toolbar,
    .order-approve-bar {
      align-items: stretch;
      flex-direction: column;
    }
    .order-toolbar .button,
    .order-approve-bar .button,
    .order-toggle-button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const button = document.getElementById("order-table-toggle");
    const card = document.getElementById("order-table-card");
    if (!button || !card) return;

    const sync = () => {
      button.textContent = card.hidden ? "Javaslat megmutatása" : "Javaslat elrejtése";
    };

    button.addEventListener("click", () => {
      card.hidden = !card.hidden;
      sync();
      if (!card.hidden) {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

    sync();
  })();
</script>
"""

    return render_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )
