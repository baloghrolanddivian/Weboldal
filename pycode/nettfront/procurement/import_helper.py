"""Automation helper process management for procurement imports.

This module launches, monitors, and stops the AutoHotkey-based helper used to
feed generated procurement CSV data into the NettFront client workflow.

This module is included in the pydoc surface for the NettFront procurement workflow."""

from __future__ import annotations

import os
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


HELPER_PID_FILE = "nettfront-helper.pid"
AHK_SCRIPT_FILE = "nettfront-import.ahk"
POWERSHELL_SCRIPT_FILE = "nettfront-import.ps1"
RESUME_FILE = "nettfront-import-resume.json"


def get_import_resume(job_dir: Path | None) -> dict:
    """Read the selected start row without changing the order or its artifacts."""
    if job_dir is None or not (job_dir / "rendeles_sima.csv").is_file():
        return {"start_row": 1, "row_count": 0}
    content = (job_dir / "rendeles_sima.csv").read_bytes()
    count = sum(bool(line.strip()) for line in content.decode("utf-8-sig").splitlines())
    digest = hashlib.sha256(content).hexdigest()
    try:
        saved = json.loads((job_dir / RESUME_FILE).read_text(encoding="utf-8"))
        start = saved.get("start_row", 1)
        if saved.get("csv_sha256") != digest or type(start) is not int or not 1 <= start <= count:
            start = 1
    except (OSError, ValueError, AttributeError):
        start = 1
    return {"start_row": start, "row_count": count, "csv_sha256": digest}


def validate_start_row(value, row_count: int) -> int:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise ValueError("A kezdő sorszám pozitív egész szám legyen.")
    start = int(value)
    if not 1 <= start <= row_count:
        raise ValueError(f"A kezdő sorszám 1 és {row_count} közötti szám legyen.")
    return start


def _helper_pid_path(job_dir: Path) -> Path:
    """Handle helper pid path logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    return job_dir / HELPER_PID_FILE


def _helper_ahk_path(job_dir: Path) -> Path:
    """Handle helper ahk path logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    return job_dir / AHK_SCRIPT_FILE


def _helper_powershell_path(job_dir: Path) -> Path:
    """Handle helper powershell path logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    return job_dir / POWERSHELL_SCRIPT_FILE


def _clear_helper_state(job_dir: Path) -> None:
    """Handle clear helper state logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    try:
        _helper_pid_path(job_dir).unlink()
    except FileNotFoundError:
        pass


def _read_helper_pid(job_dir: Path) -> int | None:
    """Read helper pid data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    pid_path = _helper_pid_path(job_dir)
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_helper_pid(job_dir: Path, pid: int) -> None:
    """Write helper pid data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    _helper_pid_path(job_dir).write_text(str(pid), encoding="utf-8")


def _is_process_running(pid: int | None) -> bool:
    """Return whether process running is true.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    if not pid or pid <= 0:
        return False

    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if not output:
        return False

    lowered = output.lower()
    if "no tasks are running" in lowered or "nincs futo feladat" in lowered:
        return False
    return str(pid) in output


def get_procurement_helper_state(job_dir: Path | None) -> dict[str, object]:
    """Return procurement helper state data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    if job_dir is None:
        return {"running": False, "pid": None}

    pid = _read_helper_pid(job_dir)
    running = _is_process_running(pid)
    if not running:
        _clear_helper_state(job_dir)
        pid = None
    return {"running": running, "pid": pid}


def stop_procurement_helper(job_dir: Path) -> tuple[bool, list[str]]:
    """Stop procurement helper processing.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    state = get_procurement_helper_state(job_dir)
    pid = state.get("pid")
    if not state.get("running") or not isinstance(pid, int):
        return False, ["Nincs futo import-seged."]

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    else:
        os.kill(pid, 15)

    _clear_helper_state(job_dir)
    return True, ["Az import-seged leallt."]


def _find_autohotkey_executable() -> Path | None:
    """Handle find autohotkey executable logic for the NettFront workflows.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    candidates = [
        shutil.which("AutoHotkey64.exe"),
        shutil.which("AutoHotkey32.exe"),
        shutil.which("AutoHotkey.exe"),
        r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
        r"C:\Program Files\AutoHotkey\v2\AutoHotkey32.exe",
        r"C:\Program Files\AutoHotkey\v2\AutoHotkey.exe",
        r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
        r"C:\Program Files\AutoHotkey\AutoHotkey32.exe",
        r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
        r"C:\Program Files (x86)\AutoHotkey\AutoHotkeyU64.exe",
        r"C:\Program Files (x86)\AutoHotkey\AutoHotkeyU32.exe",
        r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return candidate_path
    return None


def _build_runtime_ahk_script(csv_path: Path, start_row: int = 1) -> str:
    """Build runtime ahk script data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    csv_literal = str(csv_path).replace("\\", "\\\\")
    return f"""; AutoHotkey v2.0+
#SingleInstance Force
Persistent

sleeptime := 300
doublesleeptime := 3000
csvPath := "{csv_literal}"
startRow := {start_row}
isRunning := false

Esc::
{{
    ExitApp
}}

+Space::
{{
    global csvPath, startRow, sleeptime, doublesleeptime, isRunning
    if (isRunning)
        return
    isRunning := true

    try content := FileRead(csvPath, "UTF-8")
    catch {{
        MsgBox "Hiba: Nem sikerult beolvasni a fajlt: " csvPath
        ExitApp
    }}

    lines := StrSplit(content, "`n", "`r")
    rowNumber := 0
    for _, line in lines
    {{
        line := Trim(line)
        if (line = "")
            continue
        rowNumber++
        if (rowNumber < startRow)
            continue
        if GetKeyState("Esc", "P")
            ExitApp

        parts := StrSplit(line, ";")
        if parts.Length < 2
            continue

        cikkszam := Trim(parts[1])
        mennyiseg := Trim(parts[2])
        if (cikkszam = "")
            continue

        A_Clipboard := cikkszam
        Send "{{Insert}}"
        Sleep doublesleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{{Tab 2}}"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "^v"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{{Tab}}"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        A_Clipboard := mennyiseg
        Send "^v"
        Sleep sleeptime

        if GetKeyState("Esc", "P")
            ExitApp
        Send "{{Tab}}"
        Send "{{Enter}}"
        Sleep sleeptime
    }}

    ExitApp
}}
"""


def _build_runtime_powershell_script(csv_path: Path, start_row: int = 1) -> str:
    """Build runtime powershell script data.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    csv_literal = str(csv_path).replace("'", "''")
    return f"""$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DivianKeyboardState {{
    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);
}}
"@

$csvPath = '{csv_literal}'
$startRow = {start_row}
$stepDelayMs = 350
$insertDelayMs = 2800
$saveDelayMs = 1500
$logPath = Join-Path (Split-Path -Parent $csvPath) 'nettfront-import.log'
$rowNumber = 0
$hotkeyPollDelayMs = 90
$postHotkeyDelayMs = 420
$lastStartHotkeyState = $false

function Test-KeyDown([int]$vkCode) {{
    return (([DivianKeyboardState]::GetAsyncKeyState($vkCode) -band 0x8000) -ne 0)
}}

function Test-StopRequested {{
    return Test-KeyDown 0x1B
}}

function Write-ImportLog([string]$message) {{
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "$(Get-Date -Format o) $message"
}}

function Set-ImportClipboard([string]$value) {{
    # The receiving application can briefly lock the clipboard after pasting.
    # Retry only the clipboard operation, never a partially entered row.
    for ($attempt = 1; $attempt -le 20; $attempt++) {{
        if (Test-StopRequested) {{ exit }}
        try {{
            [System.Windows.Forms.Clipboard]::SetText($value)
            if ([System.Windows.Forms.Clipboard]::GetText() -ceq $value) {{ return }}
        }} catch {{
            if ($attempt -eq 20) {{ throw }}
        }}
        Start-Sleep -Milliseconds 150
    }}
    throw 'Nem sikerult beallitani a vagolapot.'
}}

try {{
Write-ImportLog 'WAITING Shift+Space'
while ($true) {{
    if (Test-StopRequested) {{
        exit
    }}

    $shiftDown = Test-KeyDown 0x10
    $spaceDown = Test-KeyDown 0x20
    $hotkeyDown = $shiftDown -and $spaceDown
    if ($hotkeyDown -and -not $script:lastStartHotkeyState) {{
        break
    }}

    $script:lastStartHotkeyState = $hotkeyDown
    Start-Sleep -Milliseconds $hotkeyPollDelayMs
}}

while (Test-KeyDown 0x10 -or Test-KeyDown 0x20) {{
    Start-Sleep -Milliseconds 40
}}
Start-Sleep -Milliseconds $postHotkeyDelayMs

$rows = @(Get-Content -LiteralPath $csvPath -Encoding UTF8 | Where-Object {{ $_.Trim() -ne "" }})
Write-ImportLog "START rows=$($rows.Count)"
foreach ($row in $rows) {{
    $rowNumber++
    if ($rowNumber -lt $startRow) {{ continue }}
    if (Test-StopRequested) {{
        exit
    }}

    $parts = $row -split ';'
    if ($parts.Count -lt 2) {{
        continue
    }}

    $articleCode = $parts[0].Trim()
    $quantity = $parts[1].Trim()
    if ([string]::IsNullOrWhiteSpace($articleCode)) {{
        continue
    }}

    if (Test-StopRequested) {{
        exit
    }}
    Write-ImportLog "ROW $rowNumber/$($rows.Count) code=$articleCode"
    Set-ImportClipboard $articleCode
    [System.Windows.Forms.SendKeys]::SendWait('{{INSERT}}')
    Start-Sleep -Milliseconds $insertDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    [System.Windows.Forms.SendKeys]::SendWait('{{TAB}}{{TAB}}')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    [System.Windows.Forms.SendKeys]::SendWait('{{TAB}}')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    Set-ImportClipboard $quantity
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    [System.Windows.Forms.SendKeys]::SendWait('{{TAB}}')
    Start-Sleep -Milliseconds 140
    [System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
    Start-Sleep -Milliseconds $saveDelayMs
    Write-ImportLog "SENT $rowNumber/$($rows.Count)"
}}
Write-ImportLog "FINISHED rows=$($rows.Count)"
}} catch {{
    Write-ImportLog "ERROR row=$rowNumber $($_.Exception.Message)"
    [System.Windows.Forms.MessageBox]::Show("Az import megallt a(z) $rowNumber. sornal. A rendeles sorai megmaradtak. Hiba: $($_.Exception.Message)", 'NettFront import') | Out-Null
    exit 1
}}
"""


def launch_procurement_helper(job_dir: Path, start_row=None) -> tuple[bool, list[str]]:
    """Launch procurement helper processing.

    This function is part of the pydoc-documented NettFront procurement workflow."""
    job_dir.mkdir(parents=True, exist_ok=True)
    csv_path = job_dir / "rendeles_sima.csv"
    if not csv_path.exists():
        return False, ["A Beszerzes fajl nem talalhato."]

    resume = get_import_resume(job_dir)
    try:
        start_row = validate_start_row(resume["start_row"] if start_row is None else start_row, resume["row_count"])
    except ValueError as exc:
        return False, [str(exc)]

    if os.name != "nt":
        return False, ["Az automatikus import jelenleg Windows alatt erheto el."]

    state = get_procurement_helper_state(job_dir)
    if state.get("running"):
        return True, ["Az import-seged mar fut. Shift + Space: inditas, ESC: leallitas."]

    _clear_helper_state(job_dir)
    _helper_ahk_path(job_dir).write_text(_build_runtime_ahk_script(csv_path, start_row), encoding="utf-8")
    _helper_powershell_path(job_dir).write_text(_build_runtime_powershell_script(csv_path, start_row), encoding="utf-8")

    # Persist only the selection; never trim or regenerate the approved order.
    resume_path = job_dir / RESUME_FILE
    temporary = resume_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**resume, "start_row": start_row}), encoding="utf-8")
    temporary.replace(resume_path)

    autohotkey = _find_autohotkey_executable()
    if autohotkey is not None:
        process = subprocess.Popen(
            [str(autohotkey), str(_helper_ahk_path(job_dir))],
            cwd=str(job_dir),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        process = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_helper_powershell_path(job_dir)),
            ],
            cwd=str(job_dir),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    _write_helper_pid(job_dir, process.pid)
    return True, [f"A bevételezési segéd a(z) {start_row}. sortól indul. Shift + Space: indítás, ESC: leállítás. A teljes rendelés megmaradt."]
