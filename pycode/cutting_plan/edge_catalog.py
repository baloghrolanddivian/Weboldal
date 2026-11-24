"""Serve a local, evidence-based edge lookup without network-drive requests."""

from functools import lru_cache
import json
from pathlib import Path
import unicodedata

DATA_ROOT = Path(__file__).resolve().parents[2] / 'data'
CATALOG_PATH = DATA_ROOT / 'cutting-edge-catalog.json'
COLOUR_PATH = DATA_ROOT / 'korpusz-alkatresz-meretek.json'
OVERRIDE_PATH = DATA_ROOT / 'cutting-edge-overrides.json'


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if c.isalnum())


@lru_cache(maxsize=4)
def _load(catalog_path, colour_path, override_path, signature):
    aliases = {}
    try:
        colours = json.loads(Path(colour_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        colours = []
    for row in colours:
        for field in ('colour', 'colour_name', 'colour_code'):
            if row.get(field):
                aliases[_fold(row[field])] = _fold(row['colour'])
    try:
        records = json.loads(Path(catalog_path).read_text(encoding='utf-8')).get('records', [])
    except (OSError, ValueError):
        records = []
    try:
        overrides = json.loads(Path(override_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        overrides = {}
    records = records + [{**row, 'manual': True} for row in overrides.get('records', [])]
    sizes = {}
    for row in records:
        width, height = sorted((int(row['width']), int(row['height'])))
        colour = _fold(row.get('colour', ''))
        entry = {'colour': aliases.get(colour, colour), 'edge': row['edge'], 'descriptions': row.get('descriptions', [])}
        if row.get('manual'):
            entry['manual'] = True
        values = sizes.setdefault(f'{width}x{height}', [])
        if entry not in values:
            values.append(entry)
    return {'aliases': aliases, 'sizes': sizes, 'sizeAliases': overrides.get('size_aliases', {})}


def load_catalog(catalog_path=CATALOG_PATH, colour_path=COLOUR_PATH, override_path=OVERRIDE_PATH):
    paths = [Path(catalog_path), Path(colour_path), Path(override_path)]
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in paths)
    return _load(str(catalog_path), str(colour_path), str(override_path), signature)


def with_edge_lookup(page):
    data = json.dumps(load_catalog(), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    logic = Path(__file__).with_name('edge_lookup.js').read_text(encoding='utf-8').replace('{{EDGE_CATALOG}}', data)
    return page.replace('</head>', '<script>' + logic + '</script></head>', 1)
