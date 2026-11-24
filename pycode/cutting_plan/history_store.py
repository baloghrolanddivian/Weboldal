"""Immutable operation snapshots and a server-limited fourteen-day history."""

from datetime import datetime, timedelta, timezone
import hashlib
import json

STAGES = {"szabasz": "Szabászat", "foliazo": "Fóliázás", "elpakolas": "Elpakolás"}


def record_event(conn, stage, source, occurred_at, items):
    if not items:
        return
    event_key = hashlib.sha256(json.dumps([stage, source], ensure_ascii=False).encode("utf-8")).hexdigest()
    conn.execute("INSERT OR IGNORE INTO cutting_history VALUES (?,?,?,?,?)", (event_key, stage, occurred_at, json.dumps(items, ensure_ascii=False), json.dumps(source, ensure_ascii=False)))


def snapshot_item(plan, row, group, quantity, rejected=0):
    return {"colour": plan.get("colour", ""), "width": row.get("width", ""), "height": row.get("height", ""), "strip100": bool(row.get("strip100")), "row_group": group, "quantity": quantity, "rejected": rejected}


def pallet_times(conn, pallet_id):
    row = conn.execute("SELECT COALESCE(d.sent_at,p.updated_at) AS cut_at,w.completed_at AS edged_at FROM pallets p LEFT JOIN pallet_dispatch d ON d.pallet_id=p.id LEFT JOIN pallet_wrapping w ON w.pallet_id=p.id WHERE p.id=?", (pallet_id,)).fetchone()
    return dict(row) if row else {}


def pallet_snapshot(conn, pallet, quantities=None, selected=None):
    record = conn.execute("SELECT plans FROM days WHERE day=?", (pallet["day"],)).fetchone()
    plans = {p["id"]: p for p in json.loads(record[0])} if record else {}
    result = []
    times = pallet_times(conn, pallet["id"])
    for allocation in json.loads(pallet["allocations"]):
        key = json.dumps([allocation["plan_id"], allocation["row_group"], allocation["row_id"]], separators=(",", ":"), ensure_ascii=False)
        if selected is not None and key not in selected:
            continue
        plan = plans.get(allocation["plan_id"], {})
        row = next((r for r in plan.get(allocation["row_group"], []) if r["id"] == allocation["row_id"]), {})
        quantity = quantities.get(key, allocation["quantity"]) if quantities is not None else allocation["quantity"]
        result.append({**snapshot_item(plan, row, allocation["row_group"], quantity, allocation["quantity"] - quantity), **times})
    return result


def initialize_history(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS cutting_history (event_key TEXT PRIMARY KEY, stage TEXT NOT NULL, occurred_at TEXT NOT NULL, items TEXT NOT NULL, source TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS cutting_history_stage_time ON cutting_history(stage,occurred_at)")
    conn.execute("CREATE TABLE IF NOT EXISTS cutting_history_meta (version INTEGER PRIMARY KEY)")
    if conn.execute("SELECT 1 FROM cutting_history_meta WHERE version=1").fetchone():
        return
    conn.execute("BEGIN IMMEDIATE")
    if conn.execute("SELECT 1 FROM cutting_history_meta WHERE version=1").fetchone():
        conn.commit()
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    for progress in conn.execute("SELECT * FROM progress WHERE done=1 AND updated_at>=?", (cutoff,)).fetchall():
        record = conn.execute("SELECT plans FROM days WHERE day=?", (progress["day"],)).fetchone()
        plans = json.loads(record[0]) if record else []
        plan = next((p for p in plans if p["id"] == progress["plan_id"]), {})
        row = next((r for r in plan.get(progress["row_group"], []) if r["id"] == progress["row_id"]), {})
        record_event(conn, "szabasz", [progress[k] for k in ("day", "plan_id", "row_group", "row_id", "revision")], progress["updated_at"], [snapshot_item(plan, row, progress["row_group"], progress["actual"])])
    for pallet in conn.execute("SELECT p.*,w.items,w.updated_at AS wrapped_at,w.revision AS wrapping_revision,q.quantities FROM pallets p JOIN pallet_wrapping w ON w.pallet_id=p.id LEFT JOIN pallet_wrapping_quantities q ON q.pallet_id=p.id WHERE w.updated_at>=?", (cutoff,)).fetchall():
        quantities = json.loads(pallet["quantities"] or "{}")
        selected = {k for k, done in json.loads(pallet["items"]).items() if done}
        record_event(conn, "foliazo", [pallet["id"], pallet["wrapping_revision"]], pallet["wrapped_at"], pallet_snapshot(conn, pallet, quantities, selected))
    for pallet in conn.execute("SELECT p.*,q.quantities FROM pallets p JOIN pallet_wrapping w ON w.pallet_id=p.id LEFT JOIN pallet_wrapping_quantities q ON q.pallet_id=p.id WHERE w.completed_at IS NOT NULL AND (EXISTS (SELECT 1 FROM pallet_putaway_items i WHERE i.pallet_id=p.id AND i.stored_at>=?) OR EXISTS (SELECT 1 FROM pallet_putaway s WHERE s.pallet_id=p.id AND s.stored_at>=?))", (cutoff, cutoff)).fetchall():
        quantities = json.loads(pallet["quantities"] or "{}")
        per_item = conn.execute("SELECT item_key,stored_at FROM pallet_putaway_items WHERE pallet_id=?", (pallet["id"],)).fetchall()
        if per_item:
            for item in per_item:
                if item["stored_at"] >= cutoff:
                    record_event(conn, "elpakolas", [pallet["id"], item["item_key"]], item["stored_at"], pallet_snapshot(conn, pallet, quantities, {item["item_key"]}))
        else:
            stored = conn.execute("SELECT stored_at FROM pallet_putaway WHERE pallet_id=?", (pallet["id"],)).fetchone()
            if stored and stored[0] >= cutoff:
                record_event(conn, "elpakolas", [pallet["id"], "legacy"], stored[0], pallet_snapshot(conn, pallet, quantities))
    conn.execute("INSERT INTO cutting_history_meta VALUES (1)")
    conn.commit()


def list_history(root, stage):
    from .store import _connect

    if stage not in STAGES:
        raise ValueError("Ismeretlen történetnézet.")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    with _connect(root) as conn:
        rows = conn.execute("SELECT event_key,occurred_at,items,source FROM cutting_history WHERE stage=? AND occurred_at>=? AND occurred_at<=? ORDER BY occurred_at DESC,event_key DESC", (stage, cutoff.isoformat(), now.isoformat())).fetchall()
        events, legacy_times = [], {}
        for row in rows:
            items = json.loads(row["items"])
            if stage != "szabasz" and any("cut_at" not in item or "edged_at" not in item for item in items):
                pallet_id = json.loads(row["source"])[0]
                if pallet_id not in legacy_times:
                    legacy_times[pallet_id] = pallet_times(conn, pallet_id)
                items = [{**legacy_times[pallet_id], **item} for item in items]
            event = {"id": row["event_key"], "occurred_at": row["occurred_at"], "items": items}
            if stage == "szabasz":
                event["production_day"] = json.loads(row["source"])[0]
            events.append(event)
    return {"stage": stage, "since": cutoff.isoformat(), "until": now.isoformat(), "events": events}
