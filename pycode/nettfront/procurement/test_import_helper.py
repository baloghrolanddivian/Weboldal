"""Exercise generated Windows automation without sending real keystrokes."""

import csv
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from nettfront.procurement.import_helper import _build_runtime_powershell_script


@unittest.skipUnless(os.name == "nt", "PowerShell integration requires Windows")
class ImportHelperTests(unittest.TestCase):
    def run_import(self, failures):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "rendeles_sima.csv"
            csv_path.write_text("".join(f"PART_{i};{i}\n" for i in range(1, 74)), encoding="utf-8-sig")
            original = csv_path.read_bytes()
            script = _build_runtime_powershell_script(csv_path)
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
