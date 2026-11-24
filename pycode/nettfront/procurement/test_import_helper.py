"""Exercise generated Windows automation without sending real keystrokes."""

import csv
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from nettfront.procurement.import_helper import (
    _build_runtime_powershell_script, _build_runtime_ahk_script,
    get_import_resume, launch_procurement_helper, RESUME_FILE,
)


@unittest.skipUnless(os.name == "nt", "PowerShell integration requires Windows")
class ImportHelperTests(unittest.TestCase):
    def run_import(self, failures, start_row=1):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "rendeles_sima.csv"
            csv_path.write_text("".join(f"PART_{i};{i}\n" for i in range(1, 74)), encoding="utf-8-sig")
            original = csv_path.read_bytes()
            script = _build_runtime_powershell_script(csv_path, start_row)
            # Replace native input and clipboard APIs with a controlled receiver.
            stub = '''
Add-Type @"
using System;
public static class TestReceiver {
    public static int Calls = 0;
    public static int Failures = FAILURE_COUNT;
    public static int Sent = 0;
    public static string Value = "";
    public static void SetText(string value) {
        Calls++;
        if (Calls >= 13 && Failures-- > 0) throw new Exception("Clipboard busy");
        Value = value;
    }
    public static string GetText() { return Value; }
    public static void SendWait(string keys) { if (keys == "{ENTER}") Sent++; }
    public static void Show(string message, string title) { }
}
"@
function Start-Sleep { param($Milliseconds) }
'''.replace("FAILURE_COUNT", str(failures))
            script = script.replace("[System.Windows.Forms.Clipboard]", "[TestReceiver]")
            script = script.replace("[System.Windows.Forms.SendKeys]", "[TestReceiver]")
            script = script.replace("[System.Windows.Forms.MessageBox]", "[TestReceiver]")
            start = script.index("while ($true)")
            end = script.index("$rows = @(", start)
            script = script[:start] + script[end:]
            script = script.replace("return Test-KeyDown 0x1B", "return $false")
            script = stub + script + '\nWrite-Output "Sent=$([TestReceiver]::Sent)"'
            script_path = root / "test.ps1"
            script_path.write_text(script, encoding="utf-8-sig")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(csv_path.read_bytes(), original)
            self.assertEqual(len(list(csv.reader(csv_path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))), 73)
            return result, (root / "nettfront-import.log").read_text(encoding="utf-8-sig")

    def test_clipboard_busy_on_seventh_row_recovers_and_sends_all_73(self):
        result, log = self.run_import(failures=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Sent=73", result.stdout)
        self.assertIn("FINISHED rows=73", log)

    def test_permanent_clipboard_failure_is_logged_without_repeating_rows(self):
        result, log = self.run_import(failures=100)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(log.count("SENT "), 6)
        self.assertIn("ERROR row=7", log)

    def test_resume_from_25_sends_only_remaining_rows_without_changing_order(self):
        result, log = self.run_import(failures=0, start_row=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Sent=49', result.stdout)
        self.assertIn('ROW 25/73 code=PART_25', log)
        self.assertNotIn('ROW 24/73', log)
        self.assertEqual(log.count('SENT '), 49)

    def test_resume_last_row_sends_exactly_one_row(self):
        result, log = self.run_import(failures=0, start_row=73)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Sent=1', result.stdout)
        self.assertIn('ROW 73/73 code=PART_73', log)


class ResumeStateTests(unittest.TestCase):
    def test_existing_order_artifacts_survive_launch_and_resume_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {'rendeles_sima.csv': b'A;1\nB;2\nC;3\n', 'metadata.json': b'{"approved_file":"order.xlsx"}', 'order.xlsx': b'existing approved workbook', 'rows.json': b'[{"quantity":3}]'}
            for name, content in artifacts.items():
                (root / name).write_bytes(content)
            with patch('nettfront.procurement.import_helper.get_procurement_helper_state', return_value={'running': False}), patch('nettfront.procurement.import_helper._find_autohotkey_executable', return_value=None), patch('nettfront.procurement.import_helper.subprocess.Popen') as process:
                process.return_value.pid = 999999
                success, _ = launch_procurement_helper(root, '2')
                self.assertTrue(success)
                process.assert_called_once()
            self.assertEqual(get_import_resume(root)['start_row'], 2)
            self.assertIn('$startRow = 2', (root / 'nettfront-import.ps1').read_text(encoding='utf-8'))
            self.assertIn('startRow := 2', (root / 'nettfront-import.ahk').read_text(encoding='utf-8'))
            for name, content in artifacts.items():
                self.assertEqual((root / name).read_bytes(), content)
            # A changed import list must not silently reuse an old row number.
            (root / 'rendeles_sima.csv').write_bytes(b'NEW;1\nOTHER;2\n')
            self.assertEqual(get_import_resume(root)['start_row'], 1)

    def test_invalid_row_never_launches_or_changes_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'A;1\nB;2\n'
            (root / 'rendeles_sima.csv').write_bytes(original)
            with patch('nettfront.procurement.import_helper.subprocess.Popen') as process:
                for value in ('0', '-1', '3', '', '1.5', True, 'abc'):
                    with self.subTest(value=value):
                        success, _ = launch_procurement_helper(root, value)
                        self.assertFalse(success)
                process.assert_not_called()
            self.assertFalse((root / RESUME_FILE).exists())
            self.assertEqual((root / 'rendeles_sima.csv').read_bytes(), original)

    def test_ahk_skips_before_any_input_for_selected_row(self):
        script = _build_runtime_ahk_script(Path('order.csv'), 25)
        self.assertIn('startRow := 25', script)
        self.assertLess(script.index('if (rowNumber < startRow)'), script.index('A_Clipboard := cikkszam'))
