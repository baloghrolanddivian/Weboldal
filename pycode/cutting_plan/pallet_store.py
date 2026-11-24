"""Transactional allocation of cut pieces to mixed or split pallets."""

import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .store import PlanConflict, _allocated_totals, _connect, _row_signature, validate_day
from .history_store import record_event, pallet_snapshot


PALLET_LIMITS = {(505, 724): 144, (330, 720): 216}


def _size_key(item):
    try:
        return tuple(sorted((int(item.get("width", "")), int(item.get("height", "")))))
    except (TypeError, ValueError):
        return None


def _items(conn, day):
    record = conn.execute("SELECT plans FROM days WHERE day=?", (day,)).fetchone()
    if record is None:
        raise ValueError("A napi terv nem található.")
    progress = {(p["plan_id"], p["row_group"], p["row_id"]): p for p in conn.execute("SELECT * FROM progress WHERE day=?", (day,))}
    items = []
    for plan in json.loads(record["plans"]):
        for group in ("mainRows", "offcutRows"):
            for row in plan[group]:
                p = progress.get((plan["id"], group, row["id"]))
                if not p or p["actual"] <= 0 or p["signature"] != _row_signature(plan, group, row):
                    continue
                items.append({"plan_id": plan["id"], "row_group": group, "row_id": row["id"], "colour": plan["colour"], "material": plan["material"], "width": row.get("width", ""), "height": row.get("height", ""), "strip100": bool(row.get("strip100", False)), "actual": p["actual"], "pallet_limit": PALLET_LIMITS.get(_size_key(row))})
    return items


def load_pallets(root, day):
    validate_day(day)
    with _connect(root) as conn:
        conn.execute("BEGIN")
        items = _items(conn, day)
        totals = _allocated_totals(conn, day)
        pallets = [dict(p) for p in conn.execute("SELECT * FROM pallets WHERE day=? ORDER BY updated_at DESC, id", (day,))]
    for item in items:
        item["allocated"] = totals.get((item["plan_id"], item["row_group"], item["row_id"]), 0)
        item["available"] = item["actual"] - item["allocated"]
    for pallet in pallets:
        pallet["allocations"] = json.loads(pallet["allocations"])
        pallet["total_pieces"] = sum(item["quantity"] for item in pallet["allocations"])
    return {"day": day, "items": items, "pallets": pallets}


def save_pallet(root, day, pallet_id, name, status, allocations, revision):
    validate_day(day)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("Adj meg egy legfeljebb 100 karakteres raklapnevet.")
    if status not in ("draft", "ready") or type(revision) is not int or revision < 0:
        raise ValueError("Hibás raklapállapot vagy verzió.")
    if pallet_id is not None and (not isinstance(pallet_id, str) or len(pallet_id) > 64):
        raise ValueError("Hibás raklapazonosító.")
    if not isinstance(allocations, list) or len(allocations) > 1000 or (status == "ready" and not allocations):
        raise ValueError("A kész raklapra legalább egy tétel szükséges.")
    cleaned, keys = [], set()
    for item in allocations:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("plan_id", "row_group", "row_id")):
            raise ValueError("Hibás raklaptétel.")
        key = (item["plan_id"], item["row_group"], item["row_id"])
        quantity = item.get("quantity")
        if key in keys or type(quantity) is not int or not 0 < quantity <= 9999999:
            raise ValueError("Egy méret egyszer szerepelhet a raklapon, pozitív egész darabszámmal.")
        keys.add(key)
        cleaned.append(dict(zip(("plan_id", "row_group", "row_id", "quantity"), (*key, quantity))))
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT * FROM pallets WHERE id=?", (pallet_id,)).fetchone() if pallet_id else None
        if pallet_id is not None and previous is None and revision != 0:
            raise PlanConflict("A raklap nem található. Frissítsd a listát.")
        if previous and previous["day"] != day:
            raise ValueError("A raklap másik naphoz tartozik.")
        if (previous["revision"] if previous else 0) != revision:
            raise PlanConflict("Ezt a raklapot közben más is mentette. Nyisd meg újra a friss adatokhoz.")
        if previous and previous["status"] == "ready":
            if status != "draft" or cleaned != json.loads(previous["allocations"]) or name.strip() != previous["name"]:
                raise ValueError("A kész raklapot előbb nyisd vissza szerkesztésre.")
            wrapping = conn.execute("SELECT * FROM pallet_wrapping WHERE pallet_id=?", (pallet_id,)).fetchone()
            saved_quantities = conn.execute("SELECT quantities FROM pallet_wrapping_quantities WHERE pallet_id=?", (pallet_id,)).fetchone()
            quantities = json.loads(saved_quantities[0]) if saved_quantities else {}
            quality_recorded = any(quantities.get(wrapping_key(a), a["quantity"]) != a["quantity"] for a in json.loads(previous["allocations"]))
            if wrapping and (wrapping["completed_at"] or any(json.loads(wrapping["items"]).values()) or quality_recorded):
                raise ValueError("A raklap fóliázása már elkezdődött, a tartalma nem módosítható.")
            conn.execute("DELETE FROM pallet_wrapping WHERE pallet_id=?", (pallet_id,))
            conn.execute("DELETE FROM pallet_wrapping_quantities WHERE pallet_id=?", (pallet_id,))
        available = {(i["plan_id"], i["row_group"], i["row_id"]): i for i in _items(conn, day)}
        used = _allocated_totals(conn, day, exclude=pallet_id)
        size_totals = {}
        for item in cleaned:
            key = (item["plan_id"], item["row_group"], item["row_id"])
            source = available.get(key)
            if not source:
                raise ValueError("Csak mentett, aktuális vágási mennyiség osztható raklapra.")
            remaining = source["actual"] - used.get(key, 0)
            if item["quantity"] > remaining:
                raise PlanConflict(f"Ebből a tételből legfeljebb {remaining} db osztható erre a raklapra. Frissítsd az elérhető mennyiségeket.")
            size_key = _size_key(source)
            if size_key in PALLET_LIMITS:
                size_totals[size_key] = size_totals.get(size_key, 0) + item["quantity"]
                limit = PALLET_LIMITS[size_key]
                if size_totals[size_key] > limit:
                    raise ValueError(f"A(z) {size_key[1]} × {size_key[0]} mm méretből legfeljebb {limit} db kerülhet egy raklapra. A többletet másik raklapra tedd.")
        pallet_id = pallet_id or uuid.uuid4().hex
        updated_at = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO pallets VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,status=excluded.status,allocations=excluded.allocations,revision=excluded.revision,updated_at=excluded.updated_at", (pallet_id, day, name.strip(), status, json.dumps(cleaned, ensure_ascii=False), revision + 1, updated_at))
        if status == "ready":
            conn.execute("INSERT INTO pallet_dispatch VALUES (?,?) ON CONFLICT(pallet_id) DO UPDATE SET sent_at=excluded.sent_at", (pallet_id, updated_at))
    return pallet_id


def list_ready_pallets(root, *, for_putaway=False):
    """Return unfinished wrapping pallets across all planning and dispatch days."""
    local_zone = ZoneInfo("Europe/Budapest")
    with _connect(root) as conn:
        conn.execute("BEGIN")
        rows = conn.execute("SELECT p.*, (SELECT status FROM pallet_print_jobs j WHERE j.pallet_id=p.id AND j.pallet_revision=p.revision) AS print_status, (SELECT error FROM pallet_print_jobs j WHERE j.pallet_id=p.id AND j.pallet_revision=p.revision) AS print_error, COALESCE(d.sent_at,p.updated_at) AS sent_at, w.items AS wrapping_items, w.revision AS wrapping_revision, w.completed_at, q.quantities AS wrapping_quantities FROM pallets p LEFT JOIN pallet_dispatch d ON d.pallet_id=p.id LEFT JOIN pallet_wrapping w ON w.pallet_id=p.id LEFT JOIN pallet_wrapping_quantities q ON q.pallet_id=p.id WHERE p.status='ready' ORDER BY sent_at DESC,p.id").fetchall()
        result, sources = [], {}
        stored = {row[0] for row in conn.execute("SELECT pallet_id FROM pallet_putaway")} if for_putaway else set()
        putaway_items = {}
        if for_putaway:
            for item in conn.execute("SELECT pallet_id, item_key FROM pallet_putaway_items"):
                putaway_items.setdefault(item["pallet_id"], []).append(item["item_key"])
        for row in rows:
            if bool(row["completed_at"]) != for_putaway or row["id"] in stored:
                continue
            local = datetime.fromisoformat(row["sent_at"]).astimezone(local_zone)
            day = local.date().isoformat()
            if row["day"] not in sources:
                sources[row["day"]] = {(i["plan_id"], i["row_group"], i["row_id"]): i for i in _items(conn, row["day"])}
            pallet = dict(row)
            pallet["allocations"] = [{**sources[row["day"]].get((a["plan_id"], a["row_group"], a["row_id"]), {}), **a} for a in json.loads(row["allocations"])]
            pallet["wrapping_items"] = json.loads(pallet["wrapping_items"] or "{}")
            if for_putaway:
                pallet["putaway_items"] = putaway_items.get(pallet["id"], [])
            pallet["wrapping_revision"] = pallet["wrapping_revision"] or 0
            stored_quantities = json.loads(pallet["wrapping_quantities"] or "{}")
            pallet["wrapping_quantities"] = {wrapping_key(a): stored_quantities.get(wrapping_key(a), a["quantity"]) for a in pallet["allocations"]}
            pallet["successful_pieces"] = sum(pallet["wrapping_quantities"][wrapping_key(a)] for a in pallet["allocations"] if pallet["wrapping_items"].get(wrapping_key(a)))
            pallet["rejected_pieces"] = sum(a["quantity"] - pallet["wrapping_quantities"][wrapping_key(a)] for a in pallet["allocations"] if pallet["wrapping_items"].get(wrapping_key(a)))
            pallet["wrapped_count"] = sum(pallet["wrapping_items"].values())
            pallet["wrapping_status"] = "completed" if pallet["completed_at"] else "in_progress" if pallet["wrapped_count"] else "waiting"
            pallet.update(sent_date=day, sent_time=local.strftime("%H:%M"), total_pieces=sum(a["quantity"] for a in pallet["allocations"]))
            result.append(pallet)
    return {"pallets": result}


def list_putaway_pallets(root):
    """Return completed wrapping pallets that have not been put away yet."""
    return list_ready_pallets(root, for_putaway=True)


def save_putaway(root, pallet_id, items=None):
    if not isinstance(pallet_id, str) or not pallet_id or len(pallet_id) > 64:
        raise ValueError("Hibás raklapazonosító.")
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pallet = conn.execute("SELECT p.* FROM pallets p JOIN pallet_wrapping w ON w.pallet_id=p.id WHERE p.id=? AND p.status='ready' AND w.completed_at IS NOT NULL", (pallet_id,)).fetchone()
        if not pallet:
            raise ValueError("Csak készre fóliázott raklap jelölhető elpakoltnak.")
        keys = {wrapping_key(item) for item in json.loads(pallet["allocations"])}
        if items is not None and (not isinstance(items, list) or not items or any(not isinstance(key, str) or key not in keys for key in items)):
            raise ValueError("Válassz a raklapon szereplő méretek közül.")
        selected = keys if items is None else set(items)
        now = datetime.now(timezone.utc).isoformat()
        existing_items = {row[0] for row in conn.execute("SELECT item_key FROM pallet_putaway_items WHERE pallet_id=?", (pallet_id,))}
        previously_stored = conn.execute("SELECT 1 FROM pallet_putaway WHERE pallet_id=?", (pallet_id,)).fetchone()
        conn.executemany("INSERT OR IGNORE INTO pallet_putaway_items VALUES (?,?,?)", [(pallet_id, key, now) for key in selected])
        saved = {row[0] for row in conn.execute("SELECT item_key FROM pallet_putaway_items WHERE pallet_id=?", (pallet_id,))}
        previous = conn.execute("SELECT stored_at FROM pallet_putaway WHERE pallet_id=?", (pallet_id,)).fetchone()
        if previous:
            saved = keys
        if keys <= saved:
            conn.execute("INSERT OR IGNORE INTO pallet_putaway VALUES (?,?)", (pallet_id, now))
            stored_at = conn.execute("SELECT stored_at FROM pallet_putaway WHERE pallet_id=?", (pallet_id,)).fetchone()[0]
        else:
            stored_at = None
        if not previously_stored:
            quantities_record = conn.execute("SELECT quantities FROM pallet_wrapping_quantities WHERE pallet_id=?", (pallet_id,)).fetchone()
            quantities = json.loads(quantities_record[0]) if quantities_record else {}
            for key in selected - existing_items:
                record_event(conn, "elpakolas", [pallet_id, key], now, pallet_snapshot(conn, pallet, quantities, {key}))
    return {"id": pallet_id, "stored_at": stored_at, "items": sorted(saved)}


def wrapping_key(item):
    return json.dumps([item["plan_id"], item["row_group"], item["row_id"]], separators=(",", ":"), ensure_ascii=False)


def save_wrapping(root, pallet_id, revision, pallet_revision, items, complete=False, quantities=None):
    if not isinstance(pallet_id, str) or type(revision) is not int or revision < 0 or type(pallet_revision) is not int or type(complete) is not bool:
        raise ValueError("Hibás fóliázási kérés vagy verzió.")
    if not isinstance(items, dict) or not all(isinstance(key, str) and type(value) is bool for key, value in items.items()):
        raise ValueError("Hibás tételjelölések.")
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pallet = conn.execute("SELECT * FROM pallets WHERE id=?", (pallet_id,)).fetchone()
        if not pallet or pallet["status"] != "ready":
            raise ValueError("Csak fóliázásra küldött raklap kezelhető.")
        if pallet["revision"] != pallet_revision:
            raise PlanConflict("A raklap tartalma közben módosult. Nyisd meg újra a friss adatokhoz.")
        previous = conn.execute("SELECT * FROM pallet_wrapping WHERE pallet_id=?", (pallet_id,)).fetchone()
        if (previous["revision"] if previous else 0) != revision:
            raise PlanConflict("Ezt a raklapot közben más is fóliázta. Frissítsd a raklapot a jelölések folytatásához.")
        if previous and previous["completed_at"]:
            raise ValueError("A raklap már készre van jelentve.")
        limits = {wrapping_key(item): item["quantity"] for item in json.loads(pallet["allocations"])}
        keys = set(limits)
        if set(items) != keys:
            raise ValueError("A jelölések nem egyeznek a raklap tételeivel.")
        if quantities is None:
            previous_quantities = conn.execute("SELECT quantities FROM pallet_wrapping_quantities WHERE pallet_id=?", (pallet_id,)).fetchone()
            quantities = json.loads(previous_quantities[0]) if previous_quantities else dict(limits)
        if not isinstance(quantities, dict) or set(quantities) != keys or any(type(quantities[k]) is not int or not 0 <= quantities[k] <= limits[k] for k in keys):
            raise ValueError("A sikeresen fóliázott darabszám 0 és a raklapon lévő mennyiség közötti egész szám legyen.")
        if complete and (not keys or not all(items.values())):
            raise ValueError("Készre jelentéshez előbb minden tétel fóliázását jelöld.")
        completed_at = updated_at if complete else None
        previous_items = json.loads(previous["items"]) if previous else {}
        previous_quantities_record = conn.execute("SELECT quantities FROM pallet_wrapping_quantities WHERE pallet_id=?", (pallet_id,)).fetchone()
        old_quantities = json.loads(previous_quantities_record[0]) if previous_quantities_record else {}
        changed = {key for key in keys if items[key] and (not previous_items.get(key) or quantities[key] != old_quantities.get(key, limits[key]))}
        conn.execute("INSERT INTO pallet_wrapping VALUES (?,?,?,?,?) ON CONFLICT(pallet_id) DO UPDATE SET items=excluded.items,revision=excluded.revision,completed_at=excluded.completed_at,updated_at=excluded.updated_at", (pallet_id, json.dumps(items, ensure_ascii=False), revision + 1, completed_at, updated_at))
        conn.execute("INSERT INTO pallet_wrapping_quantities VALUES (?,?) ON CONFLICT(pallet_id) DO UPDATE SET quantities=excluded.quantities", (pallet_id, json.dumps(quantities, ensure_ascii=False)))
        record_event(conn, "foliazo", [pallet_id, revision + 1], updated_at, pallet_snapshot(conn, pallet, quantities, changed))
    return {"id": pallet_id, "wrapping_items": items, "wrapping_quantities": quantities, "successful_pieces": sum(quantities[k] for k in keys if items[k]), "rejected_pieces": sum(limits[k]-quantities[k] for k in keys if items[k]), "wrapping_revision": revision + 1, "wrapped_count": sum(items.values()), "completed_at": completed_at, "wrapping_status": "completed" if complete else "in_progress" if any(items.values()) else "waiting"}


def delete_pallet(root, day, pallet_id, revision):
    validate_day(day)
    if not isinstance(pallet_id, str) or type(revision) is not int:
        raise ValueError("Hibás raklapazonosító vagy verzió.")
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM pallets WHERE id=? AND day=?", (pallet_id, day)).fetchone()
        if not row or row["revision"] != revision:
            raise PlanConflict("A raklap közben módosult. Frissítsd a listát.")
        if row["status"] != "draft":
            raise ValueError("Csak szerkesztés alatt álló raklap törölhető.")
        conn.execute("DELETE FROM pallets WHERE id=?", (pallet_id,))
