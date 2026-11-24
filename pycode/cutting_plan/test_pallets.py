"""Stock conservation and pallet lifecycle checks."""

from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from . import pallet_store as pallets, store
from .test_days import sample_plan

DAY = "2026-11-18"


def allocation(quantity, group="mainRows", row_id="row-1"):
    return {"plan_id": "colour-1", "row_group": group, "row_id": row_id, "quantity": quantity}


def seed(root):
    store.save_day(root, DAY, sample_plan(), 0)
    store.save_progress(root, DAY, "colour-1", "mainRows", "row-1", 12, True, 0, 1)
    store.save_progress(root, DAY, "colour-1", "offcutRows", "offcut-1", 3, True, 0, 1)


class PalletTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed(self.root)

    def save(self, allocations, pallet_id=None, revision=0, status="draft"):
        return pallets.save_pallet(self.root, DAY, pallet_id, "Raklap", status, allocations, revision)

    def test_split_one_size_and_mix_sizes(self):
        self.save([allocation(8), allocation(2, "offcutRows", "offcut-1")])
        self.save([allocation(4), allocation(1, "offcutRows", "offcut-1")], status="ready")
        state = pallets.load_pallets(self.root, DAY)
        self.assertEqual(sorted(p["total_pieces"] for p in state["pallets"]), [5, 10])
        self.assertEqual([i["available"] for i in state["items"]], [0, 0])
        with self.assertRaises(store.PlanConflict):
            self.save([allocation(1)])

    def test_parallel_pallets_cannot_double_allocate(self):
        def save(_):
            try:
                self.save([allocation(8)])
                return True
            except store.PlanConflict:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(save, range(2))), [False, True])
        self.assertEqual(pallets.load_pallets(self.root, DAY)["items"][0]["available"], 4)

    def test_edit_releases_stock_and_stale_revision_conflicts(self):
        pallet_id = self.save([allocation(8)])
        self.save([allocation(5)], pallet_id, 1)
        self.assertEqual(pallets.load_pallets(self.root, DAY)["items"][0]["available"], 7)
        with self.assertRaises(store.PlanConflict):
            self.save([allocation(7)], pallet_id, 1)
        pallets.delete_pallet(self.root, DAY, pallet_id, 2)
        self.assertEqual(pallets.load_pallets(self.root, DAY)["items"][0]["available"], 12)

    def test_ready_requires_explicit_reopening(self):
        pallet_id = self.save([allocation(8)], status="ready")
        with self.assertRaises(ValueError):
            self.save([allocation(7)], pallet_id, 1)
        with self.assertRaises(ValueError):
            pallets.delete_pallet(self.root, DAY, pallet_id, 1)
        self.save([allocation(8)], pallet_id, 1)
        self.save([allocation(7)], pallet_id, 2)
        self.assertEqual(pallets.load_pallets(self.root, DAY)["items"][0]["available"], 5)

    def test_allocations_protect_cut_quantities_and_plan_identity(self):
        pallet_id = self.save([allocation(8)])
        with self.assertRaises(ValueError):
            store.save_progress(self.root, DAY, "colour-1", "mainRows", "row-1", 7, True, 1, 1)
        plans = sample_plan()
        plans[0]["mainRows"][0]["width"] = "900"
        with self.assertRaises(ValueError):
            store.save_day(self.root, DAY, plans, 1)
        pallets.delete_pallet(self.root, DAY, pallet_id, 1)
        with self.assertRaisesRegex(ValueError, "levágottnak"):
            store.save_day(self.root, DAY, plans, 1)
        self.assertEqual(len(pallets.load_pallets(self.root, DAY)["items"]), 2)

    def test_invalid_quantities_and_duplicate_rows(self):
        for quantity in (0, -1, True, 1.5, "2"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.save([allocation(quantity)])
        with self.assertRaises(ValueError):
            self.save([allocation(1), allocation(2)])
        with self.assertRaises(ValueError):
            self.save([], status="ready")
        with self.assertRaises(ValueError):
            self.save([allocation(1, row_id="missing")])
        self.assertEqual(pallets.load_pallets(self.root, DAY)["pallets"], [])

    def test_failed_creation_retry_does_not_duplicate_pallet(self):
        self.save([allocation(5)], "client-pallet-id", 0)
        with self.assertRaises(store.PlanConflict):
            self.save([allocation(5)], "client-pallet-id", 0)
        self.assertEqual(len(pallets.load_pallets(self.root, DAY)["pallets"]), 1)


class PalletCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def seed_size(self, root, width, height, quantity):
        plans = sample_plan()
        plans[0]["mainRows"][0].update(width=str(width), height=str(height), pieces=str(quantity))
        plans[0]["offcutRows"] = []
        store.save_day(root, DAY, plans, 0)
        store.save_progress(root, DAY, "colour-1", "mainRows", "row-1", quantity, True, 0, 1)

    def test_limits_and_split_quantities_preserve_total(self):
        for width, height, limit in ((724, 505, 144), (720, 330, 216), (505, 724, 144), (330, 720, 216)):
            with self.subTest(size=(width, height)):
                root = self.root / f"{width}-{height}"
                self.seed_size(root, width, height, limit * 2 + 7)
                self.assertEqual(pallets.load_pallets(root, DAY)["items"][0]["pallet_limit"], limit)
                with self.assertRaisesRegex(ValueError, str(limit)):
                    pallets.save_pallet(root, DAY, None, "Túl sok", "draft", [allocation(limit + 1)], 0)
                self.assertEqual(pallets.load_pallets(root, DAY)["pallets"], [])
                first = pallets.save_pallet(root, DAY, None, "Első", "draft", [allocation(limit)], 0)
                with self.assertRaises(ValueError):
                    pallets.save_pallet(root, DAY, first, "Első", "draft", [allocation(limit + 1)], 1)
                pallets.save_pallet(root, DAY, first, "Első", "ready", [allocation(limit)], 1)
                pallets.save_pallet(root, DAY, None, "Második", "ready", [allocation(limit)], 0)
                pallets.save_pallet(root, DAY, None, "Harmadik", "draft", [allocation(7)], 0)
                state = pallets.load_pallets(root, DAY)
                self.assertEqual(sorted(p["total_pieces"] for p in state["pallets"]), [7, limit, limit])
                self.assertEqual(state["items"][0]["available"], 0)

    def test_same_size_combines_across_rows_and_rotations(self):
        plans = sample_plan()
        plans[0]["mainRows"][0].update(width="724", height="505", pieces="200")
        plans[0]["offcutRows"][0].update(width="505", height="724", pieces="100", strip100=False)
        store.save_day(self.root, DAY, plans, 0)
        store.save_progress(self.root, DAY, "colour-1", "mainRows", "row-1", 200, True, 0, 1)
        store.save_progress(self.root, DAY, "colour-1", "offcutRows", "offcut-1", 100, True, 0, 1)
        with self.assertRaises(ValueError):
            pallets.save_pallet(self.root, DAY, None, "Raklap", "draft", [allocation(100), allocation(45, "offcutRows", "offcut-1")], 0)
        pallets.save_pallet(self.root, DAY, None, "Raklap", "ready", [allocation(100), allocation(44, "offcutRows", "offcut-1")], 0)
        self.assertEqual(pallets.load_pallets(self.root, DAY)["pallets"][0]["total_pieces"], 144)

    def test_other_sizes_keep_existing_behavior(self):
        self.seed_size(self.root, 600, 400, 1000)
        pallets.save_pallet(self.root, DAY, None, "Raklap", "ready", [allocation(1000)], 0)
        self.assertEqual(pallets.load_pallets(self.root, DAY)["pallets"][0]["total_pieces"], 1000)


if __name__ == "__main__":
    unittest.main()
