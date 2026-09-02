"""HTML page rendering for the NettFront procurement workflow.

This module is included in the pydoc surface for the NettFront procurement workflow."""

from __future__ import annotations

import csv
import html
import io

from .config import procurement_runtime_dir, render_layout
from .import_helper import get_procurement_helper_state
from .jobs import read_procurement_job
from .routes import (
    NETTFRONT_PROCUREMENT_LAUNCH_PREFIX,
    NETTFRONT_PROCUREMENT_PARTS_PREFIX,
    NETTFRONT_PROCUREMENT_PROCESS_ROUTE,
    NETTFRONT_PROCUREMENT_ROUTE,
    NETTFRONT_PROCUREMENT_STOP_PREFIX,
)


def render_nettfront_procurement_form(message: str = "") -> bytes:
    """Render the procurement upload form.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="procurement-shell">
        <section class="procurement-hero-card">
          <div class="procurement-hero-grid">
            <div class="procurement-copy">
              <div class="tag">Invoice -> beszerzés</div>
              <strong>NettFront számlából beszerzés.</strong>
              <p>Egy feltöltés után elkészül minden fájl, ami kell a következő lépéshez.</p>
              <div class="procurement-flow" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>CSV</span>
              </div>
            </div>

            <div class="procurement-visual" aria-hidden="true">
              <div class="procurement-orbit"></div>
              <div class="procurement-doc is-source">
                <span class="procurement-doc-label">Számla</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
              <div class="procurement-transfer"></div>
              <div class="procurement-doc is-target">
                <span class="procurement-doc-label">Beszerzés</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="procurement-upload-card" id="feltoltes">
          <div class="procurement-surface-title">
            <strong>Feltöltés</strong>
            <p>Fájl kiválasztása, majd indítás.</p>
          </div>

          <form id="nettfront-procurement-form" method="post" action="{NETTFRONT_PROCUREMENT_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="procurement-upload-shell" id="nettfront-procurement-shell">
              <input
                class="procurement-file-input"
                id="nettfront-procurement-invoice"
                type="file"
                name="invoice_pdf"
                accept=".pdf,application/pdf"
                required
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-invoice">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">PDF</div>
                  <div class="procurement-upload-copy">
                    <strong>Számla kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Számla</span>
                  <i></i>
                  <span>Feldolgozás</span>
                  <i></i>
                  <span>Beszerzési csomag</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-invoice-state">Támogatott formátum: PDF</span>
              </label>

              <input
                class="procurement-file-input"
                id="nettfront-procurement-parts"
                type="file"
                name="parts_file"
                accept=".xls,.xlsx,.xlsm,.csv,application/vnd.ms-excel,text/csv"
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-parts">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">XLSX</div>
                  <div class="procurement-upload-copy">
                    <strong>Friss alkatrészlista</strong>
                    <p>Opcionális. Ha most feltöltöd, már ebből építjük a Beszerzést.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Alkatrészlista</span>
                  <i></i>
                  <span>Kódfrissítés</span>
                  <i></i>
                  <span>Pontosabb Beszerzés</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-parts-state">Támogatott formátum: XLS, XLSX, XLSM, CSV</span>
              </label>

              <div class="procurement-action-row">
                <button class="button button-primary" type="submit" id="nettfront-procurement-submit">Beszerzés készítése</button>
                <span class="inline-note">Az eredmény külön oldalon nyílik meg.</span>
              </div>
            </div>
          </form>

          <div class="procurement-output-footer">
            <strong>Elkészül</strong>
            <span class="procurement-pill">invoice-output.csv</span>
            <span class="procurement-pill">Beszerzés</span>
            <span class="procurement-pill">ZIP csomag</span>
          </div>
        </section>
      </div>
    """

    extra_script = """
<script>
  (() => {
    const invoiceInput = document.getElementById("nettfront-procurement-invoice");
    const invoiceState = document.getElementById("nettfront-procurement-invoice-state");
    const partsInput = document.getElementById("nettfront-procurement-parts");
    const partsState = document.getElementById("nettfront-procurement-parts-state");
    const shell = document.getElementById("nettfront-procurement-shell");
    const form = document.getElementById("nettfront-procurement-form");
    const submitButton = document.getElementById("nettfront-procurement-submit");
    if (!invoiceInput || !invoiceState || !partsInput || !partsState || !shell || !form || !submitButton) return;

    const updateState = (input, state, emptyText) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyText;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    ["dragenter", "dragover"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.add("is-dragover");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.remove("is-dragover");
      });
    });

    invoiceInput.addEventListener("change", () => updateState(invoiceInput, invoiceState, "Támogatott formátum: PDF"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLS, XLSX, XLSM, CSV"));

    form.addEventListener("submit", () => {
      submitButton.textContent = "Beszerzés készül...";
      submitButton.disabled = true;
    });
  })();
</script>"""

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


def _read_procurement_preview_rows(job_id: str, limit: int | None = None) -> tuple[list[list[str]], int]:
    """Read procurement preview rows data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    job_dir, _ = read_procurement_job(job_id)
    if job_dir is None:
        return [], 0

    csv_path = job_dir / "rendeles_sima.csv"
    if not csv_path.exists():
        return [], 0

    raw_bytes = csv_path.read_bytes()
    text = raw_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows: list[list[str]] = []
    total_rows = 0
    for row in reader:
        clean_row = [str(value).strip() for value in row[:2]]
        if not any(clean_row):
            continue
        total_rows += 1
        if limit is None or len(rows) < limit:
            rows.append(clean_row)
    return rows, total_rows


def render_nettfront_procurement_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    """Render a completed procurement job page.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    notice_html = ""
    if message:
        lowered_message = message.casefold()
        helper_message = (
            "import-segéd" in lowered_message
            or "import-seged" in lowered_message
            or "shift + space" in lowered_message
            or "esc" in lowered_message
        )
        if not helper_message:
            extra_class = " success" if success else ""
            notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    missing_codes = metadata.get("missing_codes") or []
    job_dir = procurement_runtime_dir() / job_id
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    preview_rows, preview_total = _read_procurement_preview_rows(job_id)
    uploaded_parts_name = str(metadata.get("uploaded_parts_name", "")).strip()
    missing_html = '<div class="procurement-result-meta"><span class="procurement-result-pill">Nincs hiányzó kód</span></div>'
    if missing_codes:
        visible_codes = missing_codes[:10]
        more_count = len(missing_codes) - len(visible_codes)
        code_chips = "".join(f'<span class="procurement-code-chip">{html.escape(code)}</span>' for code in visible_codes)
        more_html = f'<span class="procurement-code-chip">+{more_count} további</span>' if more_count > 0 else ""
        missing_html = f"""
          <div class="procurement-result-meta">
            <span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>
          </div>
          <div class="procurement-code-list">
            {code_chips}
            {more_html}
          </div>
        """

    preview_html = '<div class="procurement-preview-empty">A Beszerzés most nem elérhető.</div>'
    if preview_rows:
        preview_rows_html = "".join(
            f"<tr><td>{html.escape(row[0] if len(row) > 0 else '')}</td><td>{html.escape(row[1] if len(row) > 1 else '')}</td></tr>"
            for row in preview_rows
        )
        preview_html = f"""
          <div class="procurement-preview-table-wrap">
            <table class="procurement-preview-table">
              <thead>
                <tr>
                  <th>Cikkszám</th>
                  <th>Mennyiség</th>
                </tr>
              </thead>
              <tbody>
                {preview_rows_html}
              </tbody>
            </table>
          </div>
        """

    helper_status_pill = '<span class="procurement-result-pill">Import-segéd nincs elindítva</span>'
    helper_status_copy = "A Beszerzés elkészült. Indítsd a segédet, majd Shift + Space-re elindul az import."
    action_html = f"""
      <form class="launch-form" method="post" action="{NETTFRONT_PROCUREMENT_LAUNCH_PREFIX}/{job_id}">
        <div class="procurement-launch-row">
          <button class="button button-primary" type="submit">Beszerzés indítása</button>
          <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
        </div>
      </form>
    """
    if missing_codes:
        uploaded_meta_html = ""
        if uploaded_parts_name:
            uploaded_meta_html = f'<div class="procurement-remap-meta">Utolsó feltöltött lista: {html.escape(uploaded_parts_name)}</div>'
        helper_status_pill = f'<span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>'
        helper_status_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
        action_html = f"""
          <article class="procurement-remap-card">
            <strong>Alkatrészlista feltöltése</strong>
            <p>Hiányzó kódokat találtunk. Tölts fel egy friss alkatrészlistát, és újraépítjük a Beszerzést.</p>
            {uploaded_meta_html}
            <form class="procurement-remap-form" method="post" action="{NETTFRONT_PROCUREMENT_PARTS_PREFIX}/{job_id}" enctype="multipart/form-data">
              <input class="procurement-remap-input" type="file" name="parts_file" accept=".xls,.xlsx,.xlsm,.csv,application/vnd.ms-excel,text/csv" required />
              <div class="procurement-launch-row">
                <button class="button button-primary" type="submit">Alkatrészlista feltöltése</button>
                <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
              </div>
            </form>
          </article>
        """
    elif helper_running:
        helper_status_pill = '<span class="procurement-result-pill">Import-segéd fut</span>'
        helper_status_copy = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megszakítja."
        action_html = f"""
          <div class="procurement-launch-row">
            <form method="post" action="{NETTFRONT_PROCUREMENT_STOP_PREFIX}/{job_id}">
              <button class="button button-primary" type="submit">Leállítás</button>
            </form>
            <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
          </div>
        """

    lead_copy = "A Beszerzés elkészült. Ha minden kód megvan, a segéd automatikusan elindul."
    if missing_codes:
        lead_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
    elif helper_running:
        lead_copy = "A segéd fut: Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."
    elif message and "automatikus indítása nem sikerült" in message:
        lead_copy = "Az automatikus indítás most nem sikerült. Nyomd meg a Beszerzés indítása gombot."

    warning_modal_html = ""
    extra_script = ""
    if not missing_codes:
        warning_modal_html = f"""
          <div class="procurement-warning-modal" id="procurement-warning-modal" aria-hidden="true">
            <div class="procurement-warning-card" role="dialog" aria-modal="true" aria-labelledby="procurement-warning-title">
              <strong id="procurement-warning-title">Figyelem</strong>
              <p>
                A beszerzést a gép billentyűkkel fogja kezelni az InSight-ban. Csak akkor indítsd el,
                ha biztosan tudod mit csinálsz. Nyiss egy üres beszerzést az InSight-ban, majd nyomd meg a
                <strong>Shift + Space</strong> billentyűkombinációt. Ha baj van, a <strong>Leállítás</strong>
                gomb azonnal megszakítja a segédet.
              </p>
              <div class="procurement-warning-actions">
                <button class="button button-primary" type="button" id="procurement-warning-close">Értem</button>
              </div>
            </div>
          </div>
        """
        extra_script = f"""
<script>
  (() => {{
    const modal = document.getElementById("procurement-warning-modal");
    const closeButton = document.getElementById("procurement-warning-close");
    if (!modal || !closeButton) return;

    const storageKey = "divian-procurement-warning:{job_id}";
    if (!window.sessionStorage.getItem(storageKey)) {{
      modal.classList.add("is-visible");
      modal.setAttribute("aria-hidden", "false");
    }}

    const closeModal = () => {{
      modal.classList.remove("is-visible");
      modal.setAttribute("aria-hidden", "true");
      window.sessionStorage.setItem(storageKey, "1");
    }};

    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) {{
        closeModal();
      }}
    }});
  }})();
</script>"""

    content_html = f"""
      <div class="procurement-result-shell">
        <div class="tag">Procurement ready</div>
        <h2>A beszerzés elő van készítve</h2>
        <p class="muted-copy">{lead_copy}</p>

        <div class="procurement-result-grid">
          <article class="procurement-result-card">
            <strong>Állapot</strong>
            <div class="procurement-result-meta">
              <span class="procurement-result-pill">{metadata.get("invoice_row_count", 0)} számlasor</span>
              <span class="procurement-result-pill">{preview_total} beszerzési sor</span>
              {helper_status_pill}
            </div>
            <p class="procurement-result-copy">{helper_status_copy}</p>
          </article>

          <article class="procurement-result-card">
            <strong>Hiányzó kódok</strong>
            {missing_html}
          </article>
        </div>

        <article class="procurement-preview-card">
          <div class="procurement-preview-head">
            <div>
              <strong>Beszerzés</strong>
              <p>Előnézet a kész beszerzési listából.</p>
            </div>
            <p>{preview_total} / {preview_total} sor látszik</p>
          </div>
          {preview_html}
        </article>

        {action_html}
      </div>
      {warning_modal_html}
    """

    layout_lead = "A kész Beszerzésnél a segéd automatikusan indul. Ha baj van, a Leállítás gombbal azonnal megállítható."
    if missing_codes:
        layout_lead = "Hiányzó kódoknál tölts fel alkatrészlistát, és a rendszer újraépíti a Beszerzést."
    elif helper_running:
        layout_lead = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."

    return render_layout(
        heading="Beszerzés kész",
        lead=layout_lead,
        intro_label="Procurement ready",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )
