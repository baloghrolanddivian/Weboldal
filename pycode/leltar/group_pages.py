"""HTML page rendering for inventory group entry points."""

from __future__ import annotations

import html

from .routes import (
    ADMIN_FRONT_INVENTORY_ROUTE,
    ADMIN_MATERIAL_INVENTORY_ROUTE,
    ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE,
    ADMIN_SEMIFINISHED_INVENTORY_ROUTE,
    FRONT_INVENTORY_WORKER_ROUTE,
    MATERIAL_INVENTORY_WORKER_ROUTE,
    SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE,
    SEMIFINISHED_INVENTORY_WORKER_ROUTE,
)


def render_inventory_group_page(group: str) -> bytes:
    """Render the admin or production inventory module chooser page."""
    clean_group = str(group or "").strip().lower()
    is_production = clean_group == "production"
    title = "Gyártás Leltár" if is_production else "Admin Leltár"
    label = "Gyártási leltár nézetek" if is_production else "Admin leltár modulok"
    description = (
        "A kollégák önálló leltárnézetei, közvetlenül a számoláshoz."
        if is_production
        else "A leltárak kezelőfelületei feltöltéshez, lezáráshoz és exporthoz."
    )
    cards = (
        (
            ("Front leltár", "Fóliás frontok számolása méret és szín alapján.", "Front -> számolás", FRONT_INVENTORY_WORKER_ROUTE),
            ("Anyag raktár leltár", "Anyagraktári tételek számolása ICG kód szerinti kategóriákban.", "Anyag -> számolás", MATERIAL_INVENTORY_WORKER_ROUTE),
            ("Félkész raktár leltár", "Félkész raktári tételek számolása szín szerinti kategóriákban.", "Félkész -> számolás", SEMIFINISHED_INVENTORY_WORKER_ROUTE),
            ("Félkész front leltár", "Félkész frontok számolása szín szerinti kategóriákban.", "Félkész front -> számolás", SEMIFINISHED_FRONT_INVENTORY_WORKER_ROUTE),
        )
        if is_production
        else (
            ("Front leltár", "Front készletleltár feltöltése, lezárása és exportjai.", "Admin -> front", ADMIN_FRONT_INVENTORY_ROUTE),
            ("Anyag raktár leltár", "Anyagraktári leltár indítása, követése és InSight exportja.", "Admin -> anyag", ADMIN_MATERIAL_INVENTORY_ROUTE),
            ("Félkész raktár leltár", "Félkész raktári leltár indítása, követése és exportja.", "Admin -> félkész", ADMIN_SEMIFINISHED_INVENTORY_ROUTE),
            ("Félkész front leltár", "Félkész front leltár indítása, követése és exportja.", "Admin -> félkész front", ADMIN_SEMIFINISHED_FRONT_INVENTORY_ROUTE),
        )
    )
    cards_html = "".join(
        f"""
            <article class="module-card reveal">
              <div class="module-top">
                <div class="module-status">Aktív modul</div>
                <div class="module-number">{index:02d}</div>
              </div>
              <h3>{html.escape(card_title)}</h3>
              <p>{html.escape(card_description)}</p>
              <div class="module-meta">{html.escape(card_meta)}</div>
              <a class="button button-secondary" href="{html.escape(card_href)}">Megnyitás</a>
            </article>
        """
        for index, (card_title, card_description, card_meta, card_href) in enumerate(cards, start=1)
    )
    page = f"""<!DOCTYPE html>
<html lang="hu">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Divian-HUB | {html.escape(title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
      rel="stylesheet"
    />
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <div class="site-shell">
      <div class="ambient ambient-one"></div>
      <div class="ambient ambient-two"></div>
      <div class="grid-overlay"></div>

      <header class="topbar">
        <a class="brand" href="/" aria-label="Divian-HUB kezdőoldal">
          <span class="brand-mark"></span>
          <span class="brand-text">
            <strong>Divian-HUB</strong>
            <small>Céges modulplatform</small>
          </span>
        </a>
        <nav class="nav">
          <a href="/">Főoldal</a>
        </nav>
      </header>

      <main class="home-shell">
        <section class="module-section" id="modules">
          <div class="section-head reveal">
            <p class="section-label">{html.escape(label)}</p>
            <h2>{html.escape(title)}</h2>
            <p>{html.escape(description)}</p>
          </div>
          <div class="module-grid">
            {cards_html}
          </div>
        </section>
      </main>
    </div>
    <script src="/script.js"></script>
  </body>
</html>"""
    return page.encode("utf-8")

