"""Printing is tested with a fake spooler: tests never consume printer paper."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import pallet_printer as printer, pallet_store
from .test_pallet_print import DAY, seed
from .test_days import BROWSER


class DirectPrinterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pallet_id = seed(self.root)

    def test_repeated_requests_do_not_print_twice(self):
        with patch.object(printer, '_render_pdf', return_value=Path('label.pdf')) as render, patch.object(printer, '_spool_pdf', return_value=42) as spool:
            result = printer.print_pallet(self.root, DAY, self.pallet_id)
            self.assertTrue(result['ok'])
            self.assertEqual(result['job_id'], 42)
            self.assertEqual(printer.print_pallet(self.root, DAY, self.pallet_id, retry=True)['job_id'], 42)
            self.assertEqual(spool.call_count, 1)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(spool.call_args.args[1], printer.DEFAULT_PRINTER)

    def test_failed_print_keeps_closed_pallet_and_can_retry_without_duplicate(self):
        with patch.object(printer, '_render_pdf', return_value=Path('label.pdf')), patch.object(printer, '_spool_pdf', side_effect=[RuntimeError('Printer offline'), 43]) as spool:
            self.assertFalse(printer.print_pallet(self.root, DAY, self.pallet_id)['ok'])
            self.assertFalse(printer.print_pallet(self.root, DAY, self.pallet_id)['ok'])
            state = pallet_store.load_pallets(self.root, DAY)
            self.assertEqual(len(state['pallets']), 1)
            self.assertEqual(state['pallets'][0]['status'], 'ready')
            ready = pallet_store.list_ready_pallets(self.root)
            self.assertEqual(ready['pallets'][0]['print_status'], 'error')
            self.assertTrue(printer.print_pallet(self.root, DAY, self.pallet_id, retry=True)['ok'])
            self.assertEqual(spool.call_count, 2)
            self.assertEqual(pallet_store.list_ready_pallets(self.root)['pallets'][0]['print_status'], 'sent')

    def test_concurrent_request_does_not_queue_second_copy(self):
        entered, release = threading.Event(), threading.Event()

        def render(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timeout')
            return Path('label.pdf')

        with patch.object(printer, '_render_pdf', side_effect=render), patch.object(printer, '_spool_pdf', return_value=44) as spool, ThreadPoolExecutor(2) as pool:
            future = pool.submit(printer.print_pallet, self.root, DAY, self.pallet_id)
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(printer.print_pallet(self.root, DAY, self.pallet_id)['status'], 'printing')
            finally:
                release.set()
            self.assertTrue(future.result()['ok'])
            self.assertEqual(spool.call_count, 1)

    def test_draft_cannot_print(self):
        pallet = pallet_store.load_pallets(self.root, DAY)['pallets'][0]
        pallet_store.save_pallet(self.root, DAY, self.pallet_id, pallet['name'], 'draft', pallet['allocations'], pallet['revision'])
        with patch.object(printer, '_spool_pdf') as spool, self.assertRaises(ValueError):
            printer.print_pallet(self.root, DAY, self.pallet_id)
        spool.assert_not_called()

    @unittest.skipUnless(BROWSER, 'Chromium is required')
    def test_automatic_print_pdf_is_the_a4_label_without_spooling(self):
        from pypdf import PdfReader

        folder = self.root / 'render'
        folder.mkdir()
        with patch.dict('os.environ', {'CUTTING_PALLET_PRINT_FORMAT': 'label'}):
            pdf = printer._render_pdf(self.root, DAY, self.pallet_id, folder)
        reader = PdfReader(pdf)
        self.assertEqual(len(reader.pages), 1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width)*25.4/72, 210, delta=.5)
        self.assertIn('600 × 400 mm', reader.pages[0].extract_text())


if __name__ == '__main__':
    unittest.main()
