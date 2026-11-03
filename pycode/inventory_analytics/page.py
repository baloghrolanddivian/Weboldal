"""HTML rendering for the admin inventory analytics dashboard."""

from __future__ import annotations

import html

from .engine import dashboard
from .routes import (
    INVENTORY_ANALYTICS_DISCONTINUED_ROUTE,
    INVENTORY_ANALYTICS_DOORS_DISCONTINUED_ROUTE,
    INVENTORY_ANALYTICS_DOORS_ROUTE,
    INVENTORY_ANALYTICS_DOORS_UPLOAD_ROUTE,
    INVENTORY_ANALYTICS_ROUTE,
    INVENTORY_ANALYTICS_TEMPLATE_ROUTE,
    INVENTORY_ANALYTICS_UPLOAD_ROUTE,
)


def render_inventory_analytics(message: str = "", success: bool = False, period_days: int = 90, dataset: str = "parts") -> bytes:
    data = dashboard(period_days, dataset)
    if data.get("mode") == "erp":
        return _render_erp_inventory(data, message, success)
    kpis = data["kpis"]
    notice = f'<div class="ia-notice {"ok" if success else "bad"}">{html.escape(message)}</div>' if message else ""
    rows_html = "".join(_row_html(row) for row in data["rows"][:250])
    empty = """
      <section class="ia-empty">
        <span>01</span><h2>Még nincs elemzési adat</h2>
        <p>Töltsd le a mintát, exportáld bele a cikktörzset, a mai készletet és legalább 90 nap mozgását, majd töltsd vissza.</p>
      </section>
    """ if not data["rows"] else ""
    table = f"""
      <section class="ia-panel ia-table-panel">
        <div class="ia-section-head"><div><span>Operatív lista</span><h2>Kockázatok és készletpozíciók</h2></div><div class="ia-legend"><i class="red"></i> sürgős <i class="amber"></i> figyelendő</div></div>
        <div class="ia-table-wrap"><table>
          <thead><tr><th>Státusz</th><th>Cikkszám / megnevezés</th><th>ABC/XYZ</th><th>Készlet</th><th>Elérhető</th><th>Érték</th><th>Forgás</th><th>Fedezet</th><th>{data['period_days']} nap kiadás</th><th>Beérkező</th><th>Javaslat</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>
      </section>
    """ if data["rows"] else ""
    upload_history = "".join(
        f"<li><strong>{html.escape(item['file_name'])}</strong><span>{html.escape(item['uploaded_at'].replace('T', ' '))} · {item['movements_count']} új mozgás</span></li>"
        for item in data["uploads"][:5]
    ) or "<li><span>Még nincs feldolgozott feltöltés.</span></li>"
    page = f"""<!doctype html>
<html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Divian-HUB | Készlet Intelligence</title><link rel="stylesheet" href="/styles.css">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<style>{_styles()}</style></head>
<body class="ia-page"><main class="ia-shell">
  <header class="ia-nav"><a href="/" class="ia-brand"><i></i><div><strong>Divian-HUB</strong><span>Inventory Intelligence</span></div></a><nav><a href="#dashboard">Dashboard</a><a href="#upload">Adatfrissítés</a><a href="#method">Módszertan</a><a href="/">Modulok</a></nav></header>
  <section class="ia-hero" id="dashboard">
    <div><span class="ia-kicker">ADMIN · KÉSZLETIRÁNYÍTÁS</span><h1>A készlet ne álljon.<br><em>Dolgozzon.</em></h1><p>Egységes vezetői kép a készletértékről, forgásról, fedezetről és az utánrendelési kockázatokról.</p></div>
    <aside><span>Adatállapot</span><strong>{html.escape(data['latest_snapshot'] or 'Nincs készletpillanatkép')}</strong><small>{kpis['sku_count']} cikk · {data['period_days']} napos elemzési ablak</small></aside>
  </section>
  {notice}
  <section class="ia-kpis">
    {_kpi("Készletérték", _money(kpis["stock_value"]), "Aktuális beszerzési áron")}
    {_kpi("Készletforgás", _decimal(kpis["turnover"], "×"), f"{data['period_days']} napra")}
    {_kpi("Készletnapok", _decimal(kpis["days_inventory"], " nap"), "Átlagos készlettartás")}
    {_kpi("Hiánykockázat", str(kpis["risk_count"]), "Azonnali figyelmet kér")}
    {_kpi("Nem forgó érték", _money(kpis["dead_value"]), "Nincs kiadás az időszakban")}
  </section>
  {empty}{table}
  <section class="ia-grid" id="upload">
    <article class="ia-panel ia-upload">
      <span class="ia-step">ADATFRISSÍTÉS</span><h2>Egy szabványos munkafüzet</h2>
      <p>A sablon négy lapja minden szükséges adatot együtt tart. Az azonos mozgásokat a rendszer automatikusan kiszűri.</p>
      <div class="ia-actions"><a class="ia-btn secondary" href="{INVENTORY_ANALYTICS_TEMPLATE_ROUTE}">Excel-sablon letöltése</a></div>
      <form method="post" action="{INVENTORY_ANALYTICS_UPLOAD_ROUTE}" enctype="multipart/form-data">
        <label><span>Kitöltött munkafüzet</span><input type="file" name="inventory_file" accept=".xlsx,.xlsm" required></label>
        <button class="ia-btn" type="submit">Ellenőrzés és feldolgozás</button>
      </form>
    </article>
    <article class="ia-panel ia-history"><span class="ia-step">NAPLÓ</span><h2>Legutóbbi feltöltések</h2><ul>{upload_history}</ul></article>
  </section>
  <section class="ia-panel ia-method" id="method">
    <div class="ia-section-head"><div><span>ADATSZERZŐDÉS</span><h2>Mit kell minden alkalommal feltölteni?</h2></div></div>
    <div class="ia-method-grid">
      <article><b>01</b><h3>Termékek</h3><p>Cikkszám, név, kategória, egység, egységár, átfutási idő és biztonsági készlet. Változáskor frissítendő.</p></article>
      <article><b>02</b><h3>Készlet</h3><p>Dátum, raktár, cikkszám, könyv szerinti és foglalt mennyiség. Legalább napi vagy heti pillanatkép.</p></article>
      <article><b>03</b><h3>Mozgások</h3><p>Egyedi mozgásazonosító, dátum, raktár, cikk, típus és mennyiség. Minden frissítésnél az új időszak.</p></article>
      <article><b>04</b><h3>Nyitott rendelések</h3><p>Rendeléssor, várható dátum, raktár, cikk és nyitott mennyiség. A pontos hiányelőrejelzéshez.</p></article>
    </div>
    <div class="ia-rule"><strong>Szakmai minimum</strong><span>Heti készletpillanatkép + legalább 90 nap mozgás. Stabil szezonális elemzéshez 12–24 hónap történet ajánlott.</span></div>
  </section>
  <footer><span>Készlet Intelligence · admin modul</span><a href="{INVENTORY_ANALYTICS_ROUTE}?period=30">30 nap</a><a href="{INVENTORY_ANALYTICS_ROUTE}?period=90">90 nap</a><a href="{INVENTORY_ANALYTICS_ROUTE}?period=180">180 nap</a><a href="{INVENTORY_ANALYTICS_ROUTE}?period=365">365 nap</a></footer>
</main></body></html>"""
    return page.encode("utf-8")


def _render_erp_inventory(data: dict, message: str, success: bool) -> bytes:
    kpis = data["kpis"]
    is_doors = data.get("dataset") == "doors"
    upload_route = INVENTORY_ANALYTICS_DOORS_UPLOAD_ROUTE if is_doors else INVENTORY_ANALYTICS_UPLOAD_ROUTE
    discontinued_route = INVENTORY_ANALYTICS_DOORS_DISCONTINUED_ROUTE if is_doors else INVENTORY_ANALYTICS_DISCONTINUED_ROUTE
    dataset_title = "Ajtók" if is_doors else "Alkatrészek"
    notice = f'<div class="erp-notice {"ok" if success else "bad"}">{html.escape(message)}</div>' if message else ""
    window = int(data.get("selected_window", 90))
    rows = data["rows"]
    latest_90_report = next(
        (
            report
            for report in data.get("reports", [])
            if report.get("report_type") == "consumption" and int(report.get("window_days", 0)) == 90
        ),
        None,
    )
    latest_90_label = (
        str(latest_90_report.get("uploaded_at", "")).replace("T", " ")
        if latest_90_report
        else "Még nincs feltöltve"
    )
    chart_bands = (
        [
            ("over6", "6 hónap feletti készlet", "#d84a3a"),
            ("between2and6", "2–6 hónap közötti készlet", "#d99a32"),
            ("between1and2", "1–2 hónap közötti készlet", "#83a62b"),
            ("under1", "1 hónap alatti készlet", "#efa5bc"),
        ]
        if is_doors
        else [
            ("nonmoving", "Nem forgó cikkszámok", "#171c19"),
            ("over6", "6 hónap feletti készlet", "#d84a3a"),
            ("between3and6", "3–6 hónap közötti készlet", "#83a62b"),
            ("under3", "3 hónap alatti készlet", "#efa5bc"),
        ]
    )
    chart_counts = {key: 0 for key, _label, _color in chart_bands}
    for row in rows:
        # Discontinued items remain visible in the operational table, but they
        # are deliberately excluded from inventory-policy statistics.
        if row.get("discontinued"):
            continue
        monthly_average = float(row.get("policy_monthly_average", 0) or 0)
        available_stock = float(row.get("available", 0) or 0)
        if not is_doors and row["status"] == "365 napja nem forgó":
            chart_counts["nonmoving"] += 1
        elif monthly_average > 0:
            stock_months = available_stock / monthly_average
            if is_doors:
                if stock_months > 6:
                    chart_counts["over6"] += 1
                elif stock_months >= 2:
                    chart_counts["between2and6"] += 1
                elif stock_months >= 1:
                    chart_counts["between1and2"] += 1
                else:
                    chart_counts["under1"] += 1
            else:
                if stock_months > 6:
                    chart_counts["over6"] += 1
                elif stock_months >= 3:
                    chart_counts["between3and6"] += 1
                else:
                    chart_counts["under3"] += 1
    chart_total = max(1, sum(chart_counts.values()))
    chart_angles = {}
    cumulative_angle = 0.0
    gradient_parts = []
    for key, _label, color in chart_bands:
        start_angle = cumulative_angle
        cumulative_angle += chart_counts[key] / chart_total * 360
        chart_angles[key] = cumulative_angle
        gradient_parts.append(f"{color} {start_angle:.2f}deg {cumulative_angle:.2f}deg")
    chart_gradient = ",".join(gradient_parts)
    chart_legend = "".join(
        f'<p><i style="background:{color}"></i><span>{label}</span><b>{chart_counts[key]}</b></p>'
        for key, label, color in chart_bands
    )
    category_stats: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.get("discontinued"):
            continue
        item = category_stats.setdefault(
            row["category"],
            {"all": 0, "risk": 0, "stock": 0.0, "monthly_90": 0.0, "monthly_365": 0.0},
        )
        item["all"] += 1
        item["risk"] += int(row["severity"] >= 3)
        item["stock"] += max(0.0, float(row["physical"]))
        item["monthly_90"] += max(0.0, float(row["monthly_90"]))
        item["monthly_365"] += max(0.0, float(row["monthly_365"]))
    for item in category_stats.values():
        item["months_90"] = item["stock"] / item["monthly_90"] if item["monthly_90"] > 0 else None
        item["months_365"] = item["stock"] / item["monthly_365"] if item["monthly_365"] > 0 else None
        item["trend"] = item["monthly_90"] / item["monthly_365"] - 1 if item["monthly_365"] > 0 else None
    category_html = "".join(
        f"""<article class="erp-category-turnover"><div><strong>{html.escape(category)}</strong><span>{int(stats['all'])} cikk · {int(stats['risk'])} kritikus</span></div>
        <section><p><small>90 nap alapján</small><b>{_decimal(stats['months_90'], ' hó')}</b></p>
        <p><small>365 nap alapján</small><b>{_decimal(stats['months_365'], ' hó')}</b></p></section>
        <footer><span>Rövid távú változás</span><strong class="{'up' if stats['trend'] is not None and stats['trend'] > .1 else ('down' if stats['trend'] is not None and stats['trend'] < -.1 else '')}">{'—' if stats['trend'] is None else f"{stats['trend']:+.0%}".replace('.', ',')}</strong></footer></article>"""
        for category, stats in sorted(
            category_stats.items(),
            key=lambda entry: (
                entry[1]["months_90"] is None,
                entry[1]["months_90"] if entry[1]["months_90"] is not None else float("inf"),
                entry[0],
            ),
        )
    )
    rows_html = "".join(_erp_row_html(row) for row in rows)
    latest = str(data.get("latest_snapshot", "")).replace("T", " ") or "Nincs adat"
    page = f"""<!doctype html>
<html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Divian-HUB | Készletszint és készletforgás</title><link rel="stylesheet" href="/styles.css">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<style>{_erp_styles()}
html:has(body.admin-theme.erp-page){{background:#edf1eb!important;min-height:0!important;height:auto!important}}
body.admin-theme.erp-page{{background:#edf1eb!important;background-image:none!important;background-attachment:scroll!important;color:#17211b!important;min-height:0!important;height:auto!important}}
.erp-shell{{max-width:1480px;min-height:0!important;padding-bottom:10px!important}}
.erp-shell>footer{{margin:0!important;padding:18px 0 0!important}}
.erp-shell::after,.erp-page::after{{content:none!important;display:none!important}}
.erp-nav{{height:78px;background:#fff;padding:0 24px;margin-top:18px;border:1px solid #d8e0d9}}
.erp-nav a{{color:#536159!important}}
.erp-nav a.active{{color:#17211b!important;border-bottom:3px solid #9bc42b;padding-bottom:8px}}
.erp-hero{{padding:50px 42px;margin:22px 0;background:#fff;border:1px solid #d8e0d9;grid-template-columns:1fr 320px}}
.erp-hero h1{{font-size:clamp(48px,6vw,82px);color:#17211b;margin:18px 0 22px}}
.erp-hero h1 em{{color:#789619}}
.erp-hero p{{color:#647169}}
.erp-hero aside{{background:#eef5da;color:#17211b;border-top:5px solid #9bc42b}}
.erp-hero aside span,.erp-hero aside small{{color:#66735f}}
.erp-hero aside strong{{color:#17211b}}
.erp-kpis{{box-shadow:0 12px 34px rgba(25,39,30,.06)}}
.erp-chart-only{{min-height:auto;padding:34px}}
.erp-stock-chart{{grid-template-columns:280px minmax(260px,520px);justify-content:center;gap:70px;margin:0}}
.erp-segmented-ring{{width:260px;height:260px}}
.erp-segmented-ring strong{{font-size:42px}}
.erp-chart-legend{{display:flex;flex-direction:column;gap:0}}
.erp-chart-legend p{{display:grid;grid-template-columns:14px 1fr auto;align-items:center;gap:12px;margin:0;padding:14px 0;border-bottom:1px solid #e1e6e2}}
.erp-chart-legend i{{width:12px;height:12px;border-radius:50%}}
.erp-chart-legend span{{font-size:12px;color:#5e6a63}}
.erp-chart-legend b{{font:700 22px Space Grotesk}}
.erp-section-note{{margin:0;color:#6d7971;font-size:10px}}
.erp-category-grid{{grid-template-columns:repeat(4,1fr)!important}}
.erp-category-grid .erp-category-turnover{{min-height:178px!important;padding:20px!important}}
.erp-category-turnover>div{{height:auto!important;min-height:43px}}
.erp-category-turnover>section{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
.erp-category-turnover>section p{{margin:0}}
.erp-category-turnover>section small{{display:block;margin-bottom:5px}}
.erp-category-turnover>section b{{display:block!important;margin:0!important;color:#17211b!important;font-size:21px!important}}
.erp-category-turnover>footer{{display:flex;align-items:center;justify-content:space-between;padding:12px 0 0!important;margin-top:12px;border-top:1px solid #e2e7e3}}
.erp-category-turnover>footer span{{font-size:9px;color:#758178}}
.erp-category-turnover>footer strong{{font-size:13px;color:#59665e}}
.erp-category-turnover>footer strong.up{{color:#6f8e19}}
.erp-category-turnover>footer strong.down{{color:#c34b3b}}
.erp-table-wrap{{position:relative;contain:layout paint}}
.erp-status.discontinued{{background:#e6e8e5;color:#4f5953}}
.erp-discontinued-toggle{{display:inline-flex!important;align-items:center;cursor:pointer}}
.erp-discontinued-toggle input{{position:absolute;opacity:0;pointer-events:none}}
.erp-discontinued-toggle i{{display:block;width:34px;height:19px;border-radius:12px;background:#ccd3ce;position:relative;transition:.18s ease}}
.erp-discontinued-toggle i::after{{content:"";position:absolute;width:13px;height:13px;left:3px;top:3px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.18s ease}}
.erp-discontinued-toggle input:checked+i{{background:#78951e}}
.erp-discontinued-toggle input:checked+i::after{{transform:translateX(15px)}}
.erp-discontinued-toggle input:disabled+i{{opacity:.55}}
.erp-weekly-card{{display:grid;grid-template-columns:minmax(300px,.85fr) minmax(440px,1.15fr);gap:50px;align-items:center;padding:0!important;overflow:hidden;background:#eef5da!important;border:1px solid #d5e3ad!important;border-top:5px solid #9bc42b!important}}
.erp-weekly-copy{{padding:38px 0 38px 42px;color:#17211b}}
.erp-weekly-copy .erp-eyebrow{{color:#66735f}}
.erp-weekly-copy h2{{font:700 34px Space Grotesk;margin:10px 0 14px}}
.erp-weekly-copy p{{max-width:590px;margin:0;color:#657269;font-size:12px;line-height:1.75}}
.erp-weekly-tags{{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}}
.erp-weekly-tags span{{padding:7px 10px;background:#fff;color:#536159;border:1px solid #d9e2ca;font-size:9px;font-weight:800;letter-spacing:.04em}}
.erp-weekly-form{{display:grid!important;grid-template-columns:1fr auto!important;gap:12px!important;align-items:stretch!important;margin:0!important;padding:28px 30px!important;background:#f8fbf1}}
.erp-weekly-drop{{position:relative;display:flex!important;flex-direction:row!important;align-items:center;gap:15px!important;min-height:94px;padding:18px 20px;border:1px dashed #9dae79;background:#fff;cursor:pointer;transition:.2s ease}}
.erp-weekly-drop:hover{{border-color:#6f8d18;background:#fbfdf6;transform:translateY(-1px)}}
.erp-weekly-drop>input{{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}}
.erp-weekly-drop>i{{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:#d9ff3f;color:#17211b;font:700 22px Space Grotesk}}
.erp-weekly-drop>span{{display:flex;flex-direction:column;gap:5px;min-width:0}}
.erp-weekly-drop strong{{font-size:12px;color:#19231d}}
.erp-weekly-drop small{{font-size:10px;color:#78837c;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:330px}}
.erp-weekly-form>button{{display:flex;align-items:center;justify-content:center;gap:22px;min-width:230px;padding:0 22px!important;background:#78951e!important;transition:.2s ease}}
.erp-weekly-form>button:hover{{background:#617b13!important;transform:translateY(-1px)}}
.erp-weekly-form>button i{{font:700 20px Space Grotesk}}
.erp-consumption-card{{background:#f4f7f8!important;border-color:#d5dfe3!important;border-top-color:#4c8196!important}}
.erp-consumption-card .erp-weekly-copy{{background:#e8f1f4}}
.erp-consumption-card .erp-weekly-tags span{{border-color:#cbdde4;color:#486573}}
.erp-consumption-card .erp-weekly-drop{{border-color:#88aab8}}
.erp-consumption-card .erp-weekly-drop>i{{background:#cce8f2}}
.erp-consumption-card .erp-weekly-form>button{{background:#376f85!important}}
.erp-consumption-card .erp-weekly-form>button:hover{{background:#285a6e!important}}
.erp-upload-status{{display:block;margin-top:13px;color:#60736a;font-size:10px}}
@media(max-width:900px){{.erp-category-grid{{grid-template-columns:repeat(2,1fr)!important}}.erp-weekly-card{{grid-template-columns:1fr;gap:0}}.erp-weekly-copy{{padding:30px}}.erp-weekly-form{{grid-template-columns:1fr!important}}.erp-hero{{padding:36px 28px}}}}
@media(max-width:800px){{.erp-nav{{margin-top:10px}}.erp-stock-chart{{grid-template-columns:1fr;gap:28px}}.erp-segmented-ring{{margin:auto}}.erp-weekly-form>button{{min-height:58px}}}}
</style></head><body class="erp-page">
<main class="erp-shell">
  <header class="erp-nav"><a href="/" class="erp-brand"><i></i><div><strong>Divian-HUB</strong><span>Inventory Control</span></div></a>
  <nav><a class="{"active" if not is_doors else ""}" href="{INVENTORY_ANALYTICS_ROUTE}">Alkatrészek</a><a class="{"active" if is_doors else ""}" href="{INVENTORY_ANALYTICS_DOORS_ROUTE}">Ajtók</a><a href="#stock">Készletszint</a><a href="#upload">Adatfrissítés</a><a href="/">Modulok</a></nav></header>
  <section class="erp-hero" id="overview">
    <div><span class="erp-eyebrow">ADMIN · BESZERZÉSI IRÁNYÍTÓPULT · {dataset_title.upper()}</span><h1>{dataset_title}<br><em>készletszint &amp; forgás.</em></h1>
    <p>Az ERP készletáttekintése és fogyási riportjai egyetlen döntési felületen. A sürgős tételek kerülnek előre.</p></div>
    <aside><span>UTOLSÓ KÉSZLETFRISSÍTÉS</span><strong>{html.escape(latest)}</strong><small>{kpis['sku_count']} cikkszám · {window} napos fogyási nézet</small></aside>
  </section>
  {notice}
  <section class="erp-kpis" style="grid-template-columns:repeat(6,1fr)">
    {_erp_kpi("Kritikus készlet", str(kpis["shortage_count"]), "beszerzési beavatkozás")}
    {_erp_kpi("Forgási idő az elmúlt 90 nap alapján", _decimal(kpis["median_turnover_months_90"], " hónap"), "ennyi idő alatt fordul át")}
    {_erp_kpi("Forgási idő az elmúlt 1 év alapján", _decimal(kpis["median_turnover_months_365"], " hónap"), "ennyi idő alatt fordul át")}
    {_erp_kpi("Nem forgó készlet több mint egy éve", str(kpis["dead_count"]), "készleten lévő cikkszám")}
    {_erp_kpi("ERP-egyeztetést igénylő tételek", str(kpis["erp_reconcile_count"]), "negatív készletpozíció")}
    {_erp_kpi("Beszerzés alatt lévő cikkszámok", str(kpis["incoming_count"]), "nyitott beszerzési mennyiséggel")}
  </section>
  <section class="erp-focus-grid" style="grid-template-columns:1fr">
    <article class="erp-focus stock erp-chart-only" id="stock">
      <div class="erp-stock-visual erp-stock-chart">
        <div class="erp-ring erp-segmented-ring" style="background:radial-gradient(circle,#fff 55%,transparent 57%),conic-gradient({chart_gradient})">
          <strong>{sum(chart_counts.values())}</strong><span>besorolt cikk</span>
        </div>
        <div class="erp-chart-legend">
          {chart_legend}
        </div>
      </div>
    </article>
  </section>
  <section class="erp-panel erp-categories"><div class="erp-section-head"><div><span>TERMÉKCSOPORT-ELEMZÉS</span><h2>Forgási idő termékcsoportonként</h2></div><p class="erp-section-note">Készlet ÷ havi átlagfogyás · a gyorsabban forgó csoportok kerülnek előre</p></div><div class="erp-category-grid">{category_html}</div></section>
  <section class="erp-panel erp-data-panel">
    <div class="erp-section-head"><div><span>OPERATÍV DÖNTÉSI LISTA · VÁRHATÓ ELFOGYÁSI SORREND</span><h2>A leghamarabb kifogyó tételek elöl</h2></div>
      <div class="erp-tools"><input id="erp-search" type="search" placeholder="Cikkszám vagy megnevezés…"><select id="erp-status"><option value="">Minden státusz</option>{"<option value=\"__erp_reconcile__\">ERP-egyeztetést igényel</option>" if not is_doors else ""}<option>Kifutó</option><option>Készlethiány</option><option>Beérkezővel is kritikus</option><option>Biztonsági szint alatt</option><option>365 napja nem forgó</option><option>Tárolható mennyiség felett</option><option>Rendben</option></select></div>
    </div>
    <div class="erp-table-wrap"><table id="erp-table"><thead><tr>
      <th>Kifutó</th><th>Státusz</th><th>Cikkszám / megnevezés</th><th>Kategória</th><th>Fizikai</th><th>Elérhető</th><th>Biztonsági ({"1 hó" if is_doors else "3 hó"})</th>
      <th>Nyitott igény</th><th>Beérkező</th><th>Prognózis</th><th>7 nap havi átlag</th><th>90 nap havi átlag</th><th>365 nap havi átlag</th>
      <th>Forgás / év</th><th>Várható elfogyás</th><th>Tárolható ({"2 hó" if is_doors else "6 hó"})</th><th>Trend</th><th>Javasolt rendelés</th>
    </tr></thead><tbody>{rows_html}</tbody></table></div>
  </section>
  <section class="erp-upload-grid" id="upload" style="grid-template-columns:1fr">
    <article class="erp-panel erp-upload weekly erp-weekly-card">
      <div class="erp-weekly-copy">
        <span class="erp-eyebrow">7 NAPOS / HETI FRISSÍTÉS</span>
        <h2>Aktuális készlet és igények</h2>
        <p>A megszokott heti feltöltés változatlanul megmarad: itt töltsd fel az ERP készletáttekintését az aktuális készlettel, igényekkel és nyitott beszerzésekkel.</p>
        <div class="erp-weekly-tags"><span>XLSX / XLSM</span><span>Aktuális készlet</span><span>Igények</span><span>Nyitott beszerzések</span></div>
      </div>
      <form class="erp-weekly-form" method="post" action="{upload_route}" enctype="multipart/form-data">
        <label class="erp-weekly-drop">
          <input id="erp-weekly-file" type="file" name="stock_file" accept=".xlsx,.xlsm" required>
          <i aria-hidden="true">↑</i>
          <span><strong>Fájl kiválasztása</strong><small id="erp-weekly-file-name">Beszerzés készletáttekintés{" ajtók" if is_doors else ""}.xlsx</small></span>
        </label>
        <button type="submit"><span>Készletállapot frissítése</span><i aria-hidden="true">→</i></button>
      </form>
    </article>
    <article class="erp-panel erp-upload weekly erp-weekly-card erp-consumption-card">
      <div class="erp-weekly-copy">
        <span class="erp-eyebrow">90 NAPOS FOGYÁSI ALAP</span>
        <h2>Elmúlt 90 nap átlagfogyása</h2>
        <p>Töltsd fel az ERP 90 napos fogyási riportját. A rendszer a <strong>Havi_atlag</strong> értékeket cikkszámonként elmenti, majd ezekkel számolja a forgási időt, a készletfedezetet és a rendelési javaslatot.</p>
        <div class="erp-weekly-tags"><span>XLSX / XLSM</span><span>90 nap</span><span>Havi átlagfogyás</span></div>
        <small class="erp-upload-status">Legutóbbi 90 napos feltöltés: {html.escape(latest_90_label)}</small>
      </div>
      <form class="erp-weekly-form" method="post" action="{upload_route}" enctype="multipart/form-data">
        <label class="erp-weekly-drop">
          <input id="erp-consumption-90-file" type="file" name="consumption_90_file" accept=".xlsx,.xlsm" required>
          <i aria-hidden="true">↑</i>
          <span><strong>90 napos riport kiválasztása</strong><small id="erp-consumption-90-file-name">90 napos fogyási riport.xlsx</small></span>
        </label>
        <button type="submit"><span>90 napos átlag frissítése</span><i aria-hidden="true">→</i></button>
      </form>
    </article>
  </section>
  <footer><span>ERP-alapú Készlet Intelligence · a pénzbeli készletértékhez egységár szükséges</span><a href="/">Vissza a modulokhoz</a></footer>
</main>
<script>
(() => {{
 const search=document.getElementById('erp-search'), status=document.getElementById('erp-status'), rows=[...document.querySelectorAll('#erp-table tbody tr')];
 const filter=()=>{{const q=search.value.trim().toLowerCase(), s=status.value;rows.forEach(row=>{{const statusMismatch=s==='__erp_reconcile__'?row.dataset.reconcile!=='1':(s&&row.dataset.status!==s);row.hidden=!!((q&&!row.dataset.search.includes(q))||statusMismatch);}});}};
 search.addEventListener('input',filter);status.addEventListener('change',filter);
 document.querySelectorAll('.erp-discontinued').forEach(box=>box.addEventListener('change',async()=>{{
   box.disabled=true;
   try{{
     const body=new URLSearchParams({{sku:box.dataset.sku,discontinued:box.checked?'1':'0'}});
     const response=await fetch('{discontinued_route}',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}},body}});
     if(!response.ok) throw new Error('A mentés nem sikerült.');
     const row=box.closest('tr'), statusBadge=row.querySelector('.erp-status'), orderValue=row.querySelector('.erp-suggested-order');
     row.dataset.status=box.checked?'Kifutó':row.dataset.baseStatus;
     statusBadge.textContent=row.dataset.status;
     statusBadge.className='erp-status '+(box.checked?'discontinued':row.dataset.baseSeverity);
     if(orderValue) orderValue.textContent=box.checked?'0':row.dataset.baseOrder;
     box.disabled=false;
     filter();
   }}catch(error){{box.checked=!box.checked;box.disabled=false;alert(error.message);}}
 }}));
 const weeklyFile=document.getElementById('erp-weekly-file'), weeklyName=document.getElementById('erp-weekly-file-name');
 if(weeklyFile&&weeklyName) weeklyFile.addEventListener('change',()=>{{weeklyName.textContent=weeklyFile.files&&weeklyFile.files[0]?weeklyFile.files[0].name:'Beszerzés készletáttekintés{" ajtók" if is_doors else ""}.xlsx';}});
 const consumption90File=document.getElementById('erp-consumption-90-file'), consumption90Name=document.getElementById('erp-consumption-90-file-name');
 if(consumption90File&&consumption90Name) consumption90File.addEventListener('change',()=>{{consumption90Name.textContent=consumption90File.files&&consumption90File.files[0]?consumption90File.files[0].name:'90 napos fogyási riport.xlsx';}});
}})();
</script></body></html>"""
    return page.encode("utf-8")


def _erp_row_html(row: dict) -> str:
    severity = "discontinued" if row.get("discontinued") else ("critical" if row["severity"] >= 3 else ("watch" if row["severity"] >= 1 else "good"))
    base_severity = "critical" if row["base_severity"] >= 3 else ("watch" if row["base_severity"] >= 1 else "good")
    trend = row["trend_7_90"] if row["trend_7_90"] is not None else row["trend_90_365"]
    trend_text = "—" if trend is None else f"{trend:+.0%}".replace(".", ",")
    trend_class = "up" if trend is not None and trend > 0.2 else ("down" if trend is not None and trend < -0.2 else "")
    search = html.escape(f"{row['sku']} {row['name']} {row['category']}".lower(), quote=True)
    return f"""<tr data-search="{search}" data-status="{html.escape(row['status'], quote=True)}" data-base-status="{html.escape(row['base_status'], quote=True)}" data-base-severity="{base_severity}" data-base-order="{html.escape(_qty(row['base_suggested_order']), quote=True)}" data-reconcile="{'1' if row.get('erp_reconcile') else '0'}">
      <td><label class="erp-discontinued-toggle" title="Kifutó termék"><input class="erp-discontinued" type="checkbox" data-sku="{html.escape(row['sku'], quote=True)}" {"checked" if row.get("discontinued") else ""}><i></i></label></td>
      <td><span class="erp-status {severity}">{html.escape(row['status'])}</span></td>
      <td><strong>{html.escape(row['sku'])}</strong><small>{html.escape(row['name'])}</small></td><td>{html.escape(row['category'])}</td>
      <td>{_qty(row['physical'])}</td><td><b>{_qty(row['available'])}</b></td><td>{_qty(row['safety'])}</td>
      <td>{_qty(row['open_demand'])}</td><td>{_qty(row['incoming'])}</td><td>{_qty(row['projected'])}</td>
      <td>{_qty(row['monthly_7'])}</td><td>{_qty(row['monthly_90'])}</td><td>{_qty(row['monthly_365'])}</td>
      <td><b>{_decimal(row['turnover'], '×')}</b></td><td><b>{_decimal(row['months_to_stockout'], ' hó')}</b></td><td>{_qty(row['capacity'])}</td>
      <td><span class="erp-trend {trend_class}">{trend_text}</span></td><td><b class="erp-suggested-order">{_qty(row['suggested_order'])}</b></td>
    </tr>"""


def _erp_kpi(label: str, value: str, note: str) -> str:
    return f"<article><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small></article>"


def _row_html(row: dict) -> str:
    severity = "critical" if row["severity"] >= 3 else ("watch" if row["severity"] >= 1 else "good")
    return f"""<tr>
      <td><span class="ia-status {severity}">{html.escape(row['status'])}</span></td>
      <td><strong>{html.escape(row['sku'])}</strong><small>{html.escape(row['name'])} · {html.escape(row['category'])}</small></td>
      <td><b class="ia-class">{row['abc']}{row['xyz']}</b></td>
      <td>{_qty(row['on_hand'])} {html.escape(row['unit'])}</td><td>{_qty(row['available'])}</td><td>{_money(row['value'])}</td>
      <td>{_decimal(row['turnover'], '×')}</td><td>{_decimal(row['coverage'], ' nap')}</td><td>{_qty(row['outbound'])}</td>
      <td>{_qty(row['incoming'])}<small>{html.escape(row['expected'])}</small></td><td><strong>{_qty(row['suggested_order'])}</strong></td>
    </tr>"""


def _kpi(label: str, value: str, note: str) -> str:
    return f'<article><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small></article>'


def _money(value: float) -> str:
    return f"{value:,.0f} Ft".replace(",", " ")


def _qty(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ").replace(".0", "")


def _decimal(value, suffix: str) -> str:
    return "—" if value is None else f"{value:.1f}{suffix}".replace(".", ",")


def _styles() -> str:
    return """
*{box-sizing:border-box}.ia-page{margin:0;background:#f3f5f2;color:#142019;font-family:Manrope,sans-serif}.ia-shell{max-width:1500px;margin:auto;padding:0 34px 60px}.ia-nav{height:92px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #ced6cf}.ia-brand{display:flex;gap:12px;align-items:center;color:inherit;text-decoration:none}.ia-brand i{width:30px;height:30px;background:#d8ff3e;border:7px solid #17221b;border-radius:50%}.ia-brand div{display:flex;flex-direction:column}.ia-brand strong{font:700 18px Space Grotesk}.ia-brand span{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#647069}.ia-nav nav{display:flex;gap:26px}.ia-nav nav a,footer a{color:#536059;text-decoration:none;font-size:13px;font-weight:700}.ia-hero{padding:76px 0 54px;display:grid;grid-template-columns:1fr 330px;gap:60px;align-items:end}.ia-kicker,.ia-step,.ia-section-head span{font-size:11px;letter-spacing:.17em;font-weight:800;color:#66736b}.ia-hero h1{font:700 clamp(50px,7vw,100px)/.92 Space Grotesk;margin:20px 0 28px;letter-spacing:-.055em}.ia-hero h1 em{font-style:normal;color:#789100}.ia-hero p{font-size:17px;line-height:1.65;color:#5c6861;max-width:650px}.ia-hero aside{background:#162019;color:white;padding:28px;border-radius:3px;display:flex;flex-direction:column;border-top:5px solid #d8ff3e}.ia-hero aside span,.ia-hero aside small{color:#9eaaa3;font-size:11px}.ia-hero aside strong{font:600 24px Space Grotesk;margin:12px 0}.ia-notice{padding:15px 18px;margin-bottom:20px;border-left:4px solid}.ia-notice.ok{background:#e8f4df;border-color:#6c8d1b}.ia-notice.bad{background:#fae9e5;border-color:#b74736}.ia-kpis{display:grid;grid-template-columns:repeat(5,1fr);background:white;border:1px solid #dbe1dc;margin-bottom:22px}.ia-kpis article{padding:24px;border-right:1px solid #e1e6e2;display:flex;flex-direction:column}.ia-kpis article:last-child{border:0}.ia-kpis span,.ia-kpis small{font-size:11px;color:#718077}.ia-kpis strong{font:700 29px Space Grotesk;margin:9px 0;color:#17221b}.ia-panel{background:#fff;border:1px solid #dbe1dc}.ia-table-panel{margin-bottom:22px}.ia-section-head{display:flex;justify-content:space-between;align-items:end;padding:26px 28px 20px}.ia-section-head h2,.ia-panel h2{font:700 26px Space Grotesk;margin:7px 0 0}.ia-legend{font-size:11px;color:#718077}.ia-legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin:0 5px 0 14px}.ia-legend .red{background:#bd4937}.ia-legend .amber{background:#d39a20}.ia-table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:1250px}th{padding:12px 14px;text-align:left;background:#f2f4f1;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#68756d}td{padding:14px;border-top:1px solid #e6ebe7;font-size:12px;white-space:nowrap}td small{display:block;color:#7b867f;margin-top:4px;max-width:250px;overflow:hidden;text-overflow:ellipsis}.ia-status{padding:6px 9px;border-radius:2px;font-size:10px;font-weight:800}.ia-status.critical{color:#a83d2f;background:#fbe6e1}.ia-status.watch{color:#86600e;background:#fff1cf}.ia-status.good{color:#44711a;background:#eaf4df}.ia-class{display:inline-flex;background:#18231c;color:#d8ff3e;padding:6px 8px}.ia-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:22px;margin-bottom:22px}.ia-upload,.ia-history{padding:30px}.ia-upload>p{color:#68756d;line-height:1.6}.ia-actions{margin:20px 0}.ia-btn{border:0;background:#17221b;color:#fff;text-decoration:none;padding:13px 17px;font:700 12px Manrope;cursor:pointer;display:inline-block}.ia-btn.secondary{background:#e9eddf;color:#26321f}.ia-upload form{display:flex;gap:12px;align-items:end;border-top:1px solid #e1e6e2;padding-top:22px}.ia-upload label{display:flex;flex:1;flex-direction:column;gap:7px;font-size:11px;font-weight:800}.ia-upload input{border:1px solid #ccd5ce;padding:10px;background:#fafbf9}.ia-history ul{padding:0;margin:18px 0 0;list-style:none}.ia-history li{padding:12px 0;border-top:1px solid #e4e9e5;display:flex;flex-direction:column;font-size:12px}.ia-history li span{color:#77837b;margin-top:4px;font-size:10px}.ia-method{padding:10px 0 0}.ia-method-grid{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #e1e6e2}.ia-method-grid article{padding:26px;border-right:1px solid #e1e6e2}.ia-method-grid article:last-child{border:0}.ia-method-grid b{font:700 26px Space Grotesk;color:#a3b75c}.ia-method-grid h3{font:700 17px Space Grotesk}.ia-method-grid p{font-size:12px;line-height:1.65;color:#69766e}.ia-rule{display:flex;gap:28px;padding:20px 26px;background:#17221b;color:white}.ia-rule span{font-size:12px;color:#c0cac3}.ia-empty{text-align:center;background:white;border:1px solid #dbe1dc;padding:65px;margin-bottom:22px}.ia-empty span{font:700 50px Space Grotesk;color:#d8ff3e}.ia-empty h2{font:700 28px Space Grotesk}.ia-empty p{color:#68756d}footer{display:flex;gap:20px;padding-top:26px;color:#738078;font-size:12px}footer span{margin-right:auto}@media(max-width:900px){.ia-shell{padding:0 16px 40px}.ia-nav nav{display:none}.ia-hero{grid-template-columns:1fr;padding-top:50px}.ia-kpis{grid-template-columns:1fr 1fr}.ia-grid{grid-template-columns:1fr}.ia-method-grid{grid-template-columns:1fr 1fr}.ia-upload form{flex-direction:column;align-items:stretch}}@media(max-width:560px){.ia-kpis,.ia-method-grid{grid-template-columns:1fr}.ia-hero h1{font-size:52px}}
"""


def _erp_styles() -> str:
    return """
*{box-sizing:border-box}.erp-page{margin:0;background:#f2f4ef;color:#17211b;font-family:Manrope,sans-serif}.erp-shell{max-width:1560px;margin:auto;padding:0 34px 64px}.erp-nav{height:88px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #cfd7d0}.erp-brand{display:flex;gap:12px;align-items:center;color:inherit;text-decoration:none}.erp-brand i{width:31px;height:31px;border-radius:50%;background:#d9ff3f;border:7px solid #18221c}.erp-brand div{display:flex;flex-direction:column}.erp-brand strong{font:700 18px Space Grotesk}.erp-brand span{font-size:9px;letter-spacing:.18em;color:#6e7a72;text-transform:uppercase}.erp-nav nav{display:flex;gap:24px}.erp-nav a,footer a{font-size:12px;font-weight:800;text-decoration:none;color:#58645d}.erp-hero{display:grid;grid-template-columns:1fr 340px;gap:55px;align-items:end;padding:68px 0 46px}.erp-eyebrow,.erp-focus-title>span,.erp-section-head>div>span{font-size:10px;font-weight:800;letter-spacing:.17em;color:#68766d}.erp-hero h1{font:700 clamp(54px,7vw,104px)/.88 Space Grotesk;letter-spacing:-.06em;margin:20px 0 26px}.erp-hero h1 em{font-style:normal;color:#7d9800}.erp-hero p{font-size:16px;line-height:1.65;color:#627068;max-width:690px}.erp-hero aside{display:flex;flex-direction:column;padding:27px;background:#18221c;color:#fff;border-top:5px solid #d9ff3f}.erp-hero aside span,.erp-hero aside small{font-size:10px;color:#98a49c}.erp-hero aside strong{font:600 21px Space Grotesk;margin:12px 0}.erp-notice{padding:15px 18px;margin-bottom:20px;border-left:4px solid;font-size:13px}.erp-notice.ok{background:#e8f2dc;border-color:#75921a}.erp-notice.bad{background:#f9e5e1;border-color:#b54434}.erp-kpis{display:grid;grid-template-columns:repeat(6,1fr);background:#fff;border:1px solid #d8e0d9;margin-bottom:22px}.erp-kpis article{padding:22px;border-right:1px solid #e1e6e2;display:flex;flex-direction:column;min-width:0}.erp-kpis article:last-child{border:0}.erp-kpis span,.erp-kpis small{font-size:10px;color:#758178}.erp-kpis strong{font:700 27px Space Grotesk;margin:8px 0;white-space:nowrap}.erp-focus-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:22px;margin-bottom:22px}.erp-focus{padding:28px;background:#fff;border:1px solid #d8e0d9;min-height:470px}.erp-focus.turnover{background:#18221c;color:#fff;border:0;border-top:5px solid #d9ff3f}.erp-focus.turnover .erp-focus-title>span{color:#9fac9f}.erp-focus-title h2,.erp-section-head h2,.erp-upload h2{font:700 26px Space Grotesk;margin:7px 0 0}.erp-stock-visual{display:grid;grid-template-columns:180px 1fr;gap:30px;align-items:center;margin:28px 0}.erp-ring{width:170px;height:170px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:radial-gradient(circle,#fff 55%,transparent 57%),conic-gradient(#a7ca28 var(--angle),#edf0eb 0)}.erp-ring strong{font:700 37px Space Grotesk}.erp-ring span{font-size:10px;color:#748078}.erp-focus-metrics p{margin:0;padding:11px 0;border-bottom:1px solid #e4e9e5;display:flex;align-items:center;gap:14px}.erp-focus-metrics b{font:700 24px Space Grotesk;min-width:45px}.erp-focus-metrics span{font-size:11px;color:#69766e}.erp-risk-list{list-style:none;margin:0;padding:0;border-top:1px solid #dde4de}.erp-risk-list li{display:grid;grid-template-columns:1fr auto;gap:4px 16px;padding:10px 0;border-bottom:1px solid #e8ece9}.erp-risk-list li div{display:flex;flex-direction:column}.erp-risk-list span,.erp-risk-list small{font-size:10px;color:#78837c}.erp-risk-list b{font-size:12px;color:#a63d2e}.erp-periods{display:flex;gap:7px;margin:32px 0}.erp-periods a{padding:8px 13px;background:#27322b;color:#aeb9b1;text-decoration:none;font-size:11px;font-weight:800}.erp-periods a.active{background:#d9ff3f;color:#17211b}.erp-turnover-main{padding:22px 0;border-top:1px solid #354139;border-bottom:1px solid #354139}.erp-turnover-main>span{font-size:10px;color:#9aa69e}.erp-turnover-main strong{display:block;font:700 72px Space Grotesk;color:#d9ff3f;margin:10px 0}.erp-turnover-main p{font-size:11px;line-height:1.6;color:#9eaaa2;max-width:420px}.erp-turnover-note{display:flex;align-items:center;gap:17px;padding-top:22px}.erp-turnover-note b{font:700 34px Space Grotesk}.erp-turnover-note span{font-size:11px;color:#abb5ae}.erp-panel{background:#fff;border:1px solid #d8e0d9}.erp-categories{margin-bottom:22px}.erp-section-head{padding:24px 27px 18px;display:flex;align-items:end;justify-content:space-between;gap:20px}.erp-category-grid{display:grid;grid-template-columns:repeat(6,1fr);border-top:1px solid #e1e6e2}.erp-category-grid article{padding:18px;border-right:1px solid #e4e9e5;border-bottom:1px solid #e4e9e5;min-height:110px}.erp-category-grid article div{display:flex;flex-direction:column;height:43px}.erp-category-grid article strong{font-size:11px}.erp-category-grid article span,.erp-category-grid article small{font-size:9px;color:#7a867e}.erp-category-grid article b{font:700 25px Space Grotesk;color:#ab4131;margin-right:6px}.erp-tools{display:flex;gap:8px}.erp-tools input,.erp-tools select{border:1px solid #cdd5cf;background:#f8faf7;padding:10px 12px;font:500 11px Manrope;min-width:220px}.erp-table-wrap{overflow:auto;max-height:720px;border-top:1px solid #e0e6e1}.erp-data-panel table{border-collapse:separate;border-spacing:0;width:100%;min-width:1900px}.erp-data-panel th{position:sticky;top:0;z-index:2;background:#edf1ec;padding:11px 12px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#67736b;border-bottom:1px solid #d8dfd9}.erp-data-panel td{padding:11px 12px;border-bottom:1px solid #e8ece9;font-size:11px;white-space:nowrap}.erp-data-panel td small{display:block;color:#7b867f;margin-top:3px;max-width:220px;overflow:hidden;text-overflow:ellipsis}.erp-data-panel tr:hover td{background:#f8faf5}.erp-status{padding:6px 8px;font-size:9px;font-weight:800;border-radius:2px}.erp-status.critical{background:#f9e3df;color:#a43d30}.erp-status.watch{background:#fff0ca;color:#8b6410}.erp-status.good{background:#e8f2df;color:#47721d}.erp-trend{font-weight:800}.erp-trend.up{color:#b03f30}.erp-trend.down{color:#4c7922}.erp-upload-grid{display:grid;grid-template-columns:1.35fr .65fr;gap:22px;margin-top:22px}.erp-upload{padding:28px}.erp-upload>p{color:#68756d;font-size:12px;line-height:1.6}.erp-upload form{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:10px;align-items:end;margin-top:22px}.erp-upload.weekly form{grid-template-columns:1fr}.erp-upload label{display:flex;flex-direction:column;gap:7px;font-size:10px;font-weight:800}.erp-upload input{padding:9px;border:1px solid #ccd5ce;background:#f8faf7;max-width:100%}.erp-upload button{padding:12px 16px;border:0;background:#18221c;color:#fff;font:800 11px Manrope;cursor:pointer}.erp-upload.weekly{background:#eef5d9;border-color:#d5e3ad}.erp-upload.weekly button{background:#708d17}.erp-upload.weekly h2{font-size:23px}footer{display:flex;justify-content:space-between;padding:28px 0;color:#748077;font-size:10px}tr[hidden]{display:none}@media(max-width:1100px){.erp-kpis{grid-template-columns:repeat(3,1fr)}.erp-category-grid{grid-template-columns:repeat(3,1fr)}.erp-upload form{grid-template-columns:1fr 1fr}.erp-upload-grid{grid-template-columns:1fr}}@media(max-width:800px){.erp-shell{padding:0 15px 40px}.erp-nav nav{display:none}.erp-hero,.erp-focus-grid{grid-template-columns:1fr}.erp-hero{padding-top:50px}.erp-hero h1{font-size:53px}.erp-kpis{grid-template-columns:1fr 1fr}.erp-category-grid{grid-template-columns:1fr 1fr}.erp-section-head{align-items:stretch;flex-direction:column}.erp-tools{flex-direction:column}.erp-upload form{grid-template-columns:1fr}.erp-stock-visual{grid-template-columns:1fr}.erp-ring{margin:auto}}
"""
