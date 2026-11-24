"""Latest matching cut and its downstream pallet operations for manufacturing."""

import json
import re

from .edge_catalog import _fold, load_catalog
from .history_store import snapshot_item
from .store import _connect, _row_signature

ROUTE = "/apps/gyartasi-papirok/alkatresz-elozmeny"


def _pending_counts(conn, matches):
    """Count outstanding work across every planning day, independently of the last cut."""
    result = {"cut_planned_quantity": 0, "awaiting_edge_quantity": 0, "awaiting_putaway_quantity": 0}
    progress = {(p["day"], p["plan_id"], p["row_group"], p["row_id"]): p
                for p in conn.execute("SELECT * FROM progress")}
    cut_items = {}
    for day in conn.execute("SELECT day,plans FROM days"):
        for plan in json.loads(day["plans"]):
            for group in ("mainRows", "offcutRows"):
                for row in plan[group]:
                    if not matches(snapshot_item(plan, row, group, 0)):
                        continue
                    key = (day["day"], plan["id"], group, row["id"])
                    saved = progress.get(key)
                    if saved and saved["signature"] != _row_signature(plan, group, row):
                        saved = None
                    actual = saved["actual"] if saved else 0
                    if not saved or not saved["done"]:
                        result["cut_planned_quantity"] += max(0, int(row.get("pieces") or 0) - actual)
                    cut_items[key] = actual
    wrapped = 0
    stored_items = {(r["pallet_id"], r["item_key"]) for r in conn.execute("SELECT pallet_id,item_key FROM pallet_putaway_items")}
    for pallet in conn.execute("""SELECT p.*,w.items,w.completed_at,q.quantities,s.stored_at
            FROM pallets p LEFT JOIN pallet_wrapping w ON w.pallet_id=p.id
            LEFT JOIN pallet_wrapping_quantities q ON q.pallet_id=p.id
            LEFT JOIN pallet_putaway s ON s.pallet_id=p.id WHERE p.status='ready'"""):
        items = json.loads(pallet["items"] or "{}")
        quantities = json.loads(pallet["quantities"] or "{}")
        for allocation in json.loads(pallet["allocations"]):
            source = [allocation[k] for k in ("plan_id", "row_group", "row_id")]
            if (pallet["day"], *source) not in cut_items:
                continue
            key = json.dumps(source, separators=(",", ":"), ensure_ascii=False)
            if items.get(key):
                # Rejected pieces have also left the edging queue.
                wrapped += allocation["quantity"]
                if pallet["completed_at"] and not pallet["stored_at"] and (pallet["id"], key) not in stored_items:
                    result["awaiting_putaway_quantity"] += quantities.get(key, allocation["quantity"])
    result["awaiting_edge_quantity"] = max(0, sum(cut_items.values()) - wrapped)
    return result


def part_history(root, colour, size):
    if not isinstance(colour, str) or not isinstance(size, str) or len(colour) > 200 or len(size) > 100:
        raise ValueError("Hibás alkatrészadat.")
    parts = re.fullmatch(r"\s*(\d{1,7})\s*[xX×]\s*(\d{1,7})(?:\s*[xX×]\s*\d{1,7})?\s*(?:mm)?\s*", size)
    result = {"cut_at": None, "edged_at": None, "stored_at": None,
              "cut_quantity": 0, "edged_quantity": 0, "stored_quantity": 0,
              "cut_planned_quantity": 0, "awaiting_edge_quantity": 0, "awaiting_putaway_quantity": 0}
    if not parts or not colour.strip():
        return result
    catalog = load_catalog()
    aliases = catalog["aliases"]

    def colour_key(value):
        folded = _fold(value)
        return aliases.get(folded, folded)

    def dimensions(width, height):
        try:
            dims = sorted((int(width), int(height)))
        except (TypeError, ValueError):
            return None
        if dims[0] <= 0:
            return None
        return tuple(sorted(catalog.get("sizeAliases", {}).get(f"{dims[0]}x{dims[1]}", dims)))

    target_size = dimensions(*parts.groups())
    target_colour = colour_key(colour)

    def matches(item):
        return (not (item.get("strip100") and item.get("row_group") == "offcutRows") and target_size is not None
                and dimensions(item.get("width"), item.get("height")) == target_size
                and colour_key(item.get("colour", "")) == target_colour)

    with _connect(root) as conn:
        conn.execute("BEGIN")
        result.update(_pending_counts(conn, matches))
        latest = None
        # Immutable snapshots survive subsequent edits to the planning sheet.
        for event in conn.execute("SELECT occurred_at,items,source FROM cutting_history WHERE stage='szabasz' ORDER BY occurred_at DESC,event_key DESC"):
            item = next((i for i in json.loads(event["items"]) if matches(i)), None)
            if item and item.get("quantity", 0) > 0:
                latest = (event["occurred_at"], json.loads(event["source"])[:4], item)
                break
        # Older installations may have progress predating the history migration.
        for progress in conn.execute("SELECT p.*,d.plans FROM progress p JOIN days d ON d.day=p.day WHERE p.done=1 AND p.actual>0 ORDER BY p.updated_at DESC"):
            if latest and progress["updated_at"] <= latest[0]:
                break
            plan = next((p for p in json.loads(progress["plans"]) if p["id"] == progress["plan_id"]), {})
            row = next((r for r in plan.get(progress["row_group"], []) if r["id"] == progress["row_id"]), None)
            if row is None or progress["signature"] != _row_signature(plan, progress["row_group"], row):
                continue
            item = snapshot_item(plan, row, progress["row_group"], progress["actual"])
            if matches(item):
                latest = (progress["updated_at"], [progress[k] for k in ("day", "plan_id", "row_group", "row_id")], item)
        if latest is None:
            return result
        cut_at, source, item = latest
        result.update(cut_at=cut_at, cut_quantity=item["quantity"])
        day, plan_id, group, row_id = source
        item_key = json.dumps([plan_id, group, row_id], separators=(",", ":"), ensure_ascii=False)
        pallets = conn.execute("""SELECT p.*,COALESCE(d.sent_at,p.updated_at) AS sent_at,
            w.items,w.updated_at AS wrapped_at,q.quantities,s.stored_at,i.stored_at AS item_stored_at
            FROM pallets p LEFT JOIN pallet_dispatch d ON d.pallet_id=p.id
            LEFT JOIN pallet_wrapping w ON w.pallet_id=p.id
            LEFT JOIN pallet_wrapping_quantities q ON q.pallet_id=p.id
            LEFT JOIN pallet_putaway s ON s.pallet_id=p.id
            LEFT JOIN pallet_putaway_items i ON i.pallet_id=p.id AND i.item_key=?
            WHERE p.day=? AND p.status='ready'""", (item_key, day)).fetchall()
        wrapping_times = {}
        for event in conn.execute("SELECT occurred_at,items,source FROM cutting_history WHERE stage='foliazo' ORDER BY occurred_at DESC"):
            pallet_id = json.loads(event["source"])[0]
            if pallet_id not in wrapping_times and any(matches(i) for i in json.loads(event["items"])):
                wrapping_times[pallet_id] = event["occurred_at"]
        for pallet in pallets:
            if pallet["sent_at"] < cut_at:
                continue
            allocation = next((a for a in json.loads(pallet["allocations"])
                               if [a["plan_id"], a["row_group"], a["row_id"]] == source[1:]), None)
            if not allocation or not json.loads(pallet["items"] or "{}").get(item_key):
                continue
            quantity = json.loads(pallet["quantities"] or "{}").get(item_key, allocation["quantity"])
            # Use the item's operation time, not a later save of another pallet item.
            edged_at = wrapping_times.get(pallet["id"], pallet["wrapped_at"])
            result["edged_at"] = max(result["edged_at"] or "", edged_at)
            result["edged_quantity"] += quantity
            stored_at = pallet["item_stored_at"] or pallet["stored_at"]
            if stored_at:
                result["stored_at"] = max(result["stored_at"] or "", stored_at)
                result["stored_quantity"] += quantity
    return result
