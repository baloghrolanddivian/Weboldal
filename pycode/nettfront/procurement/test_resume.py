"""Resume request wiring and preservation of already approved orders."""

import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import import_helper
from .resume_ui import resume_controls, numbered_import_list


class ResumeTests(unittest.TestCase):
    def test_stop_preserves_order_and_numbered_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'A;4\nB;8\nC;12\n'
            (root / 'rendeles_sima.csv').write_bytes(original)
            (root / 'metadata.json').write_bytes(b'{"approved_file":"order.xlsx"}')
            (root / 'order.xlsx').write_bytes(b'approved order')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.object(import_helper, 'get_procurement_helper_state', return_value={'running': True, 'pid': 999999}), patch.object(import_helper.subprocess, 'run'):
                success, _ = import_helper.stop_procurement_helper(root)
            self.assertTrue(success)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)
            self.assertIn('name="start_row"', resume_controls(root))
            self.assertIn('max="3"', resume_controls(root))
            self.assertIn('<td>2</td><td>B</td><td>8</td>', numbered_import_list(root))

    def test_launch_routes_forward_selected_start_row(self):
        import app

        class Handler(app.InvoiceHandler):
            def current_user(self):
                return app.AuthUser('resume-test', 'Resume test', True)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for prefix, operation in [(app.NETTFRONT_ORDER_LAUNCH_PREFIX, 'launch_order_job'), (app.NETTFRONT_PROCUREMENT_LAUNCH_PREFIX, 'launch_procurement_job')]:
                with self.subTest(operation=operation), patch.object(app, operation, return_value=(200, b'<html>ok</html>')) as launch:
                    conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    conn.request('POST', prefix+'/testjob', body='start_row=25', headers={'Content-Type':'application/x-www-form-urlencoded'})
                    response = conn.getresponse()
                    response.read()
                    self.assertEqual(response.status, 200)
                    launch.assert_called_once_with('testjob', start_row='25')
                    conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
