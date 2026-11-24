"""Cross-module part matching and downstream batch history."""

from datetime import datetime, timezone
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from . import pallet_store, store
from .part_history import part_history
from .test_days import sample_plan
from .test_pallets import DAY, allocation, seed


class PartHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed(self.root)

    def lookup(self, colour='Antracit', size='400 x 600 x 18'):
        return part_history(self.root, colour, size)

    def test_matches_rotated_size_and_normalized_colour_without_other_parts(self):
        self.assertTrue(self.lookup(' ANTRACIT ', '600 × 400 mm')['cut_at'])
        for colour, size in [('Fehér', '600 x 400 x 18'), ('Antracit', '601 x 400 x 18'), ('', '600 x 400'), ('Antracit', ''), ('Antracit', '0 x 400')]:
            with self.subTest(colour=colour, size=size):
                self.assertIsNone(self.lookup(colour, size)['cut_at'])

    def test_partial_wrapping_and_item_putaway(self):
        pallet = pallet_store.save_pallet(self.root, DAY, None, 'Raklap', 'ready', [allocation(5), allocation(2, 'offcutRows', 'offcut-1')], 0)
        first = pallet_store.wrapping_key(allocation(5))
        other = pallet_store.wrapping_key(allocation(2, 'offcutRows', 'offcut-1'))
        with patch.object(pallet_store, 'datetime') as clock:
            clock.now.return_value = datetime(2027, 1, 10, 8, 25, tzinfo=timezone.utc)
            pallet_store.save_wrapping(self.root, pallet, 0, 1, {first: True, other: False})
            first_time = self.lookup()['edged_at']
            clock.now.return_value = datetime(2027, 1, 10, 9, 40, tzinfo=timezone.utc)
            pallet_store.save_wrapping(self.root, pallet, 1, 1, {first: True, other: True}, True)
        history = self.lookup()
        self.assertEqual(history['cut_quantity'], 12)
        self.assertEqual(history['edged_quantity'], 5)
        self.assertEqual(history['edged_at'], first_time)
        self.assertIsNone(history['stored_at'])
        pallet_store.save_putaway(self.root, pallet, [first])
        history = self.lookup()
        self.assertEqual(history['stored_quantity'], 5)
        self.assertTrue(history['stored_at'])

    def test_latest_cut_does_not_inherit_previous_batch_finishing(self):
        pallet = pallet_store.save_pallet(self.root, DAY, None, 'Raklap', 'ready', [allocation(12)], 0)
        key = pallet_store.wrapping_key(allocation(12))
        pallet_store.save_wrapping(self.root, pallet, 0, 1, {key: True}, True)
        pallet_store.save_putaway(self.root, pallet, [key])
        self.assertTrue(self.lookup()['stored_at'])
        new_day = '2026-11-24'
        store.save_day(self.root, new_day, sample_plan(), 0)
        store.save_progress(self.root, new_day, 'colour-1', 'mainRows', 'row-1', 12, True, 0, 1)
        result = self.lookup()
        self.assertTrue(result['cut_at'])
        self.assertIsNone(result['edged_at'])
        self.assertIsNone(result['stored_at'])

    def test_pre_migration_progress_and_explicit_size_and_colour_aliases(self):
        with store._connect(self.root) as conn:
            conn.execute('DELETE FROM cutting_history')
        with patch('cutting_plan.part_history.load_catalog', return_value={'aliases': {'u999': 'antracit'}, 'sizeAliases': {'402x602': [400, 600]}}):
            self.assertTrue(self.lookup('U999', '602 x 402 x 18')['cut_at'])

    def test_history_is_not_limited_to_fourteen_days(self):
        with store._connect(self.root) as conn:
            conn.execute("UPDATE cutting_history SET occurred_at='2020-01-01T08:00:00+00:00'")
            conn.execute('DELETE FROM progress')
        self.assertEqual(self.lookup()['cut_at'], '2020-01-01T08:00:00+00:00')

    def test_current_queues_include_older_batches_and_exclude_putaway_and_scrap(self):
        pallet = pallet_store.save_pallet(self.root, DAY, None, 'Raklap', 'ready', [allocation(5)], 0)
        key = pallet_store.wrapping_key(allocation(5))
        initial = self.lookup()
        self.assertEqual(initial['awaiting_edge_quantity'], 12)
        self.assertEqual(initial['awaiting_putaway_quantity'], 0)
        pallet_store.save_wrapping(self.root, pallet, 0, 1, {key: True}, True, {key: 4})
        new_day = '2026-11-25'
        store.save_day(self.root, new_day, sample_plan(), 0)
        pending = self.lookup()
        self.assertEqual(pending['cut_planned_quantity'], 12)
        self.assertEqual(pending['awaiting_edge_quantity'], 7)
        self.assertEqual(pending['awaiting_putaway_quantity'], 4)
        store.save_progress(self.root, new_day, 'colour-1', 'mainRows', 'row-1', 12, True, 0, 1)
        pending = self.lookup()
        self.assertEqual(pending['cut_planned_quantity'], 0)
        self.assertEqual(pending['awaiting_edge_quantity'], 19)
        self.assertEqual(pending['awaiting_putaway_quantity'], 4)
        pallet_store.save_putaway(self.root, pallet, [key])
        self.assertEqual(self.lookup()['awaiting_putaway_quantity'], 0)

    def test_planned_work_is_visible_before_first_cut_and_tracks_plan_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = sample_plan()
            store.save_day(root, DAY, plan, 0)
            history = part_history(root, 'Antracit', '600 x 400')
            self.assertIsNone(history['cut_at'])
            self.assertEqual(history['cut_planned_quantity'], 12)
            self.assertEqual(history['awaiting_edge_quantity'], 0)
            plan[0]['mainRows'][0]['width'] = '650'
            store.save_day(root, DAY, plan, 1)
            self.assertEqual(part_history(root, 'Antracit', '600 x 400')['cut_planned_quantity'], 0)

    def test_partial_item_putaway_only_counts_items_still_in_queue(self):
        plans = sample_plan()
        plans[0]['mainRows'].append({**plans[0]['mainRows'][0], 'id': 'row-2'})
        store.save_day(self.root, DAY, plans, 1)
        store.save_progress(self.root, DAY, 'colour-1', 'mainRows', 'row-2', 12, True, 0, 2)
        allocations = [allocation(5), allocation(3, row_id='row-2')]
        pallet = pallet_store.save_pallet(self.root, DAY, None, 'Raklap', 'ready', allocations, 0)
        keys = {pallet_store.wrapping_key(a): True for a in allocations}
        pallet_store.save_wrapping(self.root, pallet, 0, 1, keys, True)
        self.assertEqual(self.lookup()['awaiting_putaway_quantity'], 8)
        pallet_store.save_putaway(self.root, pallet, [pallet_store.wrapping_key(allocations[0])])
        self.assertEqual(self.lookup()['awaiting_putaway_quantity'], 3)

    def test_manufacturing_history_endpoint_and_invalid_input(self):
        import app
        from .part_history import ROUTE

        class Handler(app.InvoiceHandler):
            def current_user(self):
                return app.AuthUser('history-test', 'History test', True)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        runtime = self.root / 'runtime'
        seed(runtime / 'szabasterv')
        with patch.object(app, 'RUNTIME_DIR', runtime):
            thread.start()
            try:
                for colour, expected_status in [('Antracit', 200), ('a' * 201, 400)]:
                    with self.subTest(colour=colour):
                        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                        conn.request('GET', ROUTE + '?' + urlencode({'colour': colour, 'size': '600 x 400 x 18'}))
                        response = conn.getresponse()
                        body = json.loads(response.read())
                        self.assertEqual(response.status, expected_status)
                        if expected_status == 200:
                            self.assertTrue(body['history']['cut_at'])
                        else:
                            self.assertFalse(body['ok'])
                        conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
