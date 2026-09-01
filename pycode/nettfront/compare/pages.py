"""HTML page rendering for the NettFront comparison workflow.

This module is included in the pydoc surface for the NettFront comparison workflow."""

from __future__ import annotations

import html

from .config import render_file_bind_script, render_layout
from .routes import NETTFRONT_COMPARE_DOWNLOAD_PREFIX, NETTFRONT_COMPARE_PROCESS_ROUTE, NETTFRONT_COMPARE_ROUTE

NETTFRONT_ROUTE = "/apps/nettfront-olvaso"


def render_nettfront_compare_form(message: str = "") -> bytes:
    """Render the comparison upload form.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Invoice vs procurement</div>
      <h2>NettFront számla és meglévő beszerzés összehasonlítása</h2>
      <p class="muted-copy">
        Töltsd fel a számlát és a meglévő rendelési fájlt. A rendszer elkészít egy két munkalapos,
        színezett Excel riportot, amiből gyorsan látszik minden eltérés.
      </p>

      <form id="nettfront-compare-form" class="upload-grid" method="post" action="{NETTFRONT_COMPARE_PROCESS_ROUTE}" enctype="multipart/form-data">
        <label class="upload-field">
          <strong>Számla PDF</strong>
          <span class="field-hint">Kötelező. Ebből készül az invoice sorstruktúra.</span>
          <input id="nettfront-compare-invoice" type="file" name="invoice_pdf" accept=".pdf,application/pdf" required />
          <span class="field-hint" id="nettfront-compare-invoice-state">Támogatott formátum: PDF</span>
        </label>

        <label class="upload-field">
          <strong>Meglévő rendelés</strong>
          <span class="field-hint">Kötelező. XLS, XLSX, XLSM vagy CSV formátum.</span>
          <input id="nettfront-compare-order" type="file" name="order_file" accept=".xls,.xlsx,.xlsm,.csv" required />
          <span class="field-hint" id="nettfront-compare-order-state">Támogatott formátum: XLS, XLSX, XLSM, CSV</span>
        </label>
      </form>

      <div class="action-row">
        <button class="button button-primary" type="submit" form="nettfront-compare-form">Összehasonlító riport készítése</button>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Kimenetek</h3>
        <ul>
          <li>`compare-output.xlsx` két munkalappal</li>
          <li>`invoice-output.csv` a visszakövetéshez</li>
          <li>egyben letölthető ZIP</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mire jó?</h3>
        <p>
          Akkor hasznos, ha a beszerzés már létezik, és a számlával akarod kontrollálni, hogy a kódok,
          mennyiségek és árak ténylegesen egyeznek-e.
        </p>
      </article>
    """

    return render_layout(
        heading="Meglévő beszerzés és számla összehasonlítása",
        lead="Külön felület csak az ellenőrzésre, hogy a már kész rendelés és az érkező számla pontosan összevethető legyen.",
        intro_label="Comparison module",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
        extra_script=render_file_bind_script(
            [
                ("nettfront-compare-invoice", "nettfront-compare-invoice-state", "Támogatott formátum: PDF"),
                ("nettfront-compare-order", "nettfront-compare-order-state", "Támogatott formátum: XLS, XLSX, XLSM, CSV"),
            ]
        ),
    )


def render_nettfront_compare_result(job_id: str, metadata: dict, message: str = "") -> bytes:
    """Render a completed comparison job page.

    This function is part of the pydoc-documented NettFront comparison workflow."""
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Comparison output ready</div>
      <h2>Az összehasonlító riport elkészült</h2>
      <p class="muted-copy">
        Elkészült a számla és a meglévő beszerzés összevetése. Innen letölthető a színezett Excel riport és a kapcsolódó fájlok.
      </p>

      <div class="summary-grid">
        <article class="summary-card">
          <strong>{metadata.get("invoice_row_count", 0)}</strong>
          <span>felismert számlasor</span>
        </article>
        <article class="summary-card">
          <strong>{metadata.get("order_row_count", 0)}</strong>
          <span>beolvasott rendelési sor</span>
        </article>
        <article class="summary-card">
          <strong>Excel</strong>
          <span>két munkalapos riport</span>
        </article>
      </div>

      <div class="download-grid">
        <article class="download-card">
          <strong>Compare Excel</strong>
          <p>Színezett riport két összevetési nézettel.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/compare-xlsx">compare-output.xlsx</a>
        </article>

        <article class="download-card">
          <strong>Invoice CSV</strong>
          <p>A feldolgozott számlasorok külön is letölthetők.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/invoice-csv">invoice-output.csv</a>
        </article>

        <article class="download-card">
          <strong>Teljes csomag</strong>
          <p>Minden generált fájl egy ZIP-ben.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/bundle-zip">compare-output.zip</a>
        </article>
      </div>

      <div class="action-row">
        <a class="button button-primary" href="{NETTFRONT_COMPARE_ROUTE}">Új összehasonlítás</a>
        <a class="button button-secondary" href="{NETTFRONT_ROUTE}">Vissza a NettFront modulokhoz</a>
      </div>
    """

    side_html = f"""
      <article class="stack-card">
        <h3>Állapot</h3>
        <ul class="status-list">
          <li>Invoice sorok: {metadata.get("invoice_row_count", 0)}</li>
          <li>Rendelési sorok: {metadata.get("order_row_count", 0)}</li>
          <li>Riport: elkészült</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mit kapsz?</h3>
        <p>
          A compare Excel külön munkalapokon mutatja az order->invoice és invoice->order nézetet, így gyorsan
          látszanak a hiányzó vagy eltérő sorok.
        </p>
      </article>
    """

    return render_layout(
        heading="Az összehasonlítás lefutott",
        lead="A meglévő rendelés és a számla közötti eltérések most már külön riportban átnézhetők.",
        intro_label="Compare ready",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )
