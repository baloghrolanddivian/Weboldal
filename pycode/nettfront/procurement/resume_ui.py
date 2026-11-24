"""Resume controls tied to the existing import list's one-based row numbers."""

import csv
import html
import io

from .import_helper import get_import_resume


def resume_controls(job_dir):
    state = get_import_resume(job_dir)
    return f'''<div class="nettfront-resume-controls">
      <label style="display:grid;gap:6px;margin-bottom:10px">Bevételezés kezdő sorszáma
        <input type="number" name="start_row" min="1" max="{state['row_count']}" step="1" value="{state['start_row']}" required style="width:120px;max-width:100%;padding:10px;border:1px solid var(--line,#637078);border-radius:10px;background:var(--panel-strong,#fff);color:var(--text,inherit);font:inherit" />
      </label>
      <p style="max-width:480px;margin:0 0 12px;color:var(--muted);line-height:1.5">A megadott sortól folytatja, azt a sort is beleértve. A teljes rendelés megmarad. Folytatáskor az InSight-ban a meglévő beszerzést nyisd meg.</p>
    </div>'''


def numbered_import_list(job_dir):
    if job_dir is None or not (job_dir / 'rendeles_sima.csv').is_file():
        return ''
    text = (job_dir / 'rendeles_sima.csv').read_text(encoding='utf-8-sig')
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=';') if any(value.strip() for value in row)]
    entries = ''.join(f'<tr><td>{index}</td><td>{html.escape(row[0])}</td><td>{html.escape(row[1] if len(row) > 1 else "")}</td></tr>' for index, row in enumerate(rows, 1))
    return f'''<details style="margin:16px 0"><summary>Bevételezési lista sorszámokkal ({len(rows)} sor)</summary>
      <div class="order-table-wrap"><table class="order-table"><thead><tr><th>Sorszám</th><th>Cikkszám</th><th>Mennyiség</th></tr></thead><tbody>{entries}</tbody></table></div>
    </details>'''
