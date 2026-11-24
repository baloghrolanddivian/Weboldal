"""Durable daily cutting plans with optimistic concurrency control."""

import json
import hashlib
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from .history_store import initialize_history, record_event, snapshot_item


class PlanConflict(ValueError):
    """A day was saved by another editor."""


def validate_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Válassz érvényes napot.")
    date.fromisoformat(value)
    return value


def validate_plans(plans):
    if not isinstance(plans, list) or len(plans) > 100:
        raise ValueError("Legfeljebb 100 színblokk menthető.")
    ids = set()
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("Hibás színblokk.")
        for key in ("id", "colour", "material", "boardSize"):
            if not isinstance(plan.get(key), str) or not plan[key].strip() or len(plan[key]) > 200:
                raise ValueError("Hiányzó vagy túl hosszú színblokk-adat.")
        if plan["id"] in ids:
            raise ValueError("Ismétlődő színblokk-azonosító.")
        ids.add(plan["id"])
        for group in ("mainRows", "offcutRows"):
            rows = plan.get(group)
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError("Hibás vagy túl sok méretsor.")
            row_ids = set()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or len(row["id"]) > 200 or row["id"] in row_ids:
                    raise ValueError("Hibás méretsor-azonosító.")
                row_ids.add(row["id"])
                mode = row.get("sizeMode", "")
                if not isinstance(mode, str) or not re.fullmatch(r"(?:manual|\d{1,7}x\d{1,7})?", mode):
                    raise ValueError("Hibás méretválasztás.")
                for field in ("width", "height", "pieces") + (("boards",) if group == "mainRows" else ()):
                    number = row.get(field, "")
                    if isinstance(number, bool) or not isinstance(number, (str, int)) or not re.fullmatch(r"\d{0,7}", str(number)):
                        raise ValueError("A méretek és darabszámok nemnegatív egész számok lehetnek.")
                if not isinstance(row.get("strip100", False), bool):
                    raise ValueError("Hibás +100 jelölés.")
    return plans


@contextmanager
def _connect(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "daily-plans.sqlite3", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, plans TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS progress (day TEXT NOT NULL, plan_id TEXT NOT NULL, row_group TEXT NOT NULL, row_id TEXT NOT NULL, actual INTEGER NOT NULL, done INTEGER NOT NULL, revision INTEGER NOT NULL, signature TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(day, plan_id, row_group, row_id))")
            conn.execute("CREATE TABLE IF NOT EXISTS pallets (id TEXT PRIMARY KEY, day TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, allocations TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_dispatch (pallet_id TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_wrapping (pallet_id TEXT PRIMARY KEY, items TEXT NOT NULL, revision INTEGER NOT NULL, completed_at TEXT, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_wrapping_quantities (pallet_id TEXT PRIMARY KEY, quantities TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_putaway (pallet_id TEXT PRIMARY KEY, stored_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_putaway_items (pallet_id TEXT NOT NULL, item_key TEXT NOT NULL, stored_at TEXT NOT NULL, PRIMARY KEY(pallet_id,item_key))")
            conn.execute("CREATE TABLE IF NOT EXISTS pallet_print_jobs (pallet_id TEXT NOT NULL, pallet_revision INTEGER NOT NULL, status TEXT NOT NULL, job_id INTEGER, error TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(pallet_id,pallet_revision))")
            initialize_history(conn)
            yield conn
    finally:
        conn.close()


def list_days(root):
    with _connect(root) as conn:
        days = []
        for row in conn.execute("SELECT day, plans, revision, updated_at FROM days ORDER BY day DESC"):
            record = dict(row)
            totals = {}
            for plan in json.loads(record.pop("plans")):
                colour = plan["colour"]
                totals[colour] = totals.get(colour, 0) + sum(int(item.get("boards") or 0) for item in plan.get("mainRows", []))
            record["colours"] = [{"colour": colour, "boards": boards} for colour, boards in sorted(totals.items(), key=lambda item: item[0].casefold())]
            record["total_boards"] = sum(totals.values())
            days.append(record)
        return days


def load_day(root, day):
    validate_day(day)
    with _connect(root) as conn:
        row = conn.execute("SELECT * FROM days WHERE day = ?", (day,)).fetchone()
        progress = [dict(item) for item in conn.execute("SELECT * FROM progress WHERE day = ?", (day,))]
    if row is None:
        return {"day": day, "plans": [], "revision": 0, "updated_at": None, "progress": []}
    plans = json.loads(row["plans"])
    signatures = {(plan["id"], group, item["id"]): _row_signature(plan, group, item) for plan in plans for group in ("mainRows", "offcutRows") for item in plan[group]}
    for item in progress:
        item["done"] = bool(item["done"])
        item["matches_plan"] = item.pop("signature") == signatures.get((item["plan_id"], item["row_group"], item["row_id"]))
    return {**dict(row), "plans": plans, "progress": progress}


def _row_signature(plan, group, row):
    values = [plan["colour"], plan["material"], plan["boardSize"], group, *[row.get(key, "") for key in ("width", "height", "boards", "pieces", "strip100")]]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def _allocated_totals(conn, day, exclude=None):
    totals = {}
    for pallet in conn.execute("SELECT id, allocations FROM pallets WHERE day=?", (day,)):
        if pallet["id"] == exclude:
            continue
        for item in json.loads(pallet["allocations"]):
            key = (item["plan_id"], item["row_group"], item["row_id"])
            totals[key] = totals.get(key, 0) + item["quantity"]
    return totals


def save_progress(root, day, plan_id, row_group, row_id, actual, done, revision, plan_revision):
    validate_day(day)
    if type(actual) is not int or not 0 <= actual <= 9999999 or type(done) is not bool:
        raise ValueError("A tényleges darabszám nemnegatív egész szám legyen.")
    if type(revision) is not int or revision < 0 or type(plan_revision) is not int:
        raise ValueError("Hibás verzió.")
    if row_group not in ("mainRows", "offcutRows") or not isinstance(plan_id, str) or not isinstance(row_id, str):
        raise ValueError("Hibás tételazonosító.")
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        record = conn.execute("SELECT * FROM days WHERE day = ?", (day,)).fetchone()
        if record is None:
            raise ValueError("A napi terv nem található.")
        if record["revision"] != plan_revision:
            raise PlanConflict("A szabászmester módosította a tervet. Nyisd meg újra a napot az aktuális tételekhez.")
        plans = json.loads(record["plans"])
        plan = next((item for item in plans if item["id"] == plan_id), None)
        row = next((item for item in plan[row_group] if item["id"] == row_id), None) if plan else None
        if row is None:
            raise ValueError("A tétel már nem található a napi tervben.")
        key = (day, plan_id, row_group, row_id)
        previous = conn.execute("SELECT revision FROM progress WHERE day=? AND plan_id=? AND row_group=? AND row_id=?", key).fetchone()
        if (previous[0] if previous else 0) != revision:
            raise PlanConflict("Ezt a tételt közben más is mentette. Nyisd meg újra a napot a friss adatokhoz.")
        allocated = _allocated_totals(conn, day).get((plan_id, row_group, row_id), 0)
        if actual < allocated:
            raise ValueError(f"Ebből a tételből már {allocated} db raklapra került. Előbb javítsd a raklapok tartalmát.")
        conn.execute("INSERT INTO progress VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(day,plan_id,row_group,row_id) DO UPDATE SET actual=excluded.actual,done=excluded.done,revision=excluded.revision,signature=excluded.signature,updated_at=excluded.updated_at", (*key, actual, done, revision + 1, _row_signature(plan, row_group, row), updated_at))
        if done:
            record_event(conn, "szabasz", [*key, revision + 1], updated_at, [snapshot_item(plan, row, row_group, actual)])
    return {"day": day, "plan_id": plan_id, "row_group": row_group, "row_id": row_id, "actual": actual, "done": done, "revision": revision + 1, "matches_plan": True, "updated_at": updated_at}


def save_day(root, day, plans, revision):
    validate_day(day)
    validate_plans(plans)
    if type(revision) is not int or revision < 0:
        raise ValueError("Hibás tervverzió.")
    encoded = json.dumps(plans, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("A napi terv túl nagy.")
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT revision, plans FROM days WHERE day = ?", (day,)).fetchone()
        if (row[0] if row else 0) != revision:
            raise PlanConflict("Ezt a napot közben más is mentette. A saját módosításaid megmaradtak; az új verzió megnyitásához töltsd újra a napot.")
        if row:
            old = {(p["id"], g, r["id"]): _row_signature(p, g, r) for p in json.loads(row["plans"]) for g in ("mainRows", "offcutRows") for r in p[g]}
            new = {(p["id"], g, r["id"]): _row_signature(p, g, r) for p in plans for g in ("mainRows", "offcutRows") for r in p[g]}
            completed = conn.execute("SELECT plan_id, row_group, row_id FROM progress WHERE day=? AND done=1", (day,))
            if any(old.get(tuple(item)) != new.get(tuple(item)) for item in completed):
                raise ValueError("A szabász által levágottnak jelölt tétel nem módosítható vagy törölhető. Nyisd meg újra a napot az aktuális állapothoz.")
            if any(old.get(key) != new.get(key) for key, quantity in _allocated_totals(conn, day).items() if quantity):
                raise ValueError("Raklapra osztott tétel nem módosítható vagy törölhető. Előbb vedd le a raklapokról.")
        conn.execute("INSERT INTO days VALUES (?, ?, ?, ?) ON CONFLICT(day) DO UPDATE SET plans=excluded.plans, revision=excluded.revision, updated_at=excluded.updated_at", (day, encoded, revision + 1, updated_at))
    return {"day": day, "plans": plans, "revision": revision + 1, "updated_at": updated_at}
