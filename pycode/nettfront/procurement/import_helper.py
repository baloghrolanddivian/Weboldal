from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


HELPER_PID_FILE = "nettfront-helper.pid"
AHK_SCRIPT_FILE = "nettfront-import.ahk"
POWERSHELL_SCRIPT_FILE = "nettfront-import.ps1"


def _helper_pid_path(job_dir: Path) -> Path:
    return job_dir / HELPER_PID_FILE


def _helper_ahk_path(job_dir: Path) -> Path:
    return job_dir / AHK_SCRIPT_FILE


def _helper_powershell_path(job_dir: Path) -> Path:
    return job_dir / POWERSHELL_SCRIPT_FILE


def _clear_helper_state(job_dir: Path) -> None:
    try:
        _helper_pid_path(job_dir).unlink()
    except FileNotFoundError:
        pass


def _read_helper_pid(job_dir: Path) -> int | None:
    pid_path = _helper_pid_path(job_dir)
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_helper_pid(job_dir: Path, pid: int) -> None:
    _helper_pid_path(job_dir).write_text(str(pid), encoding="utf-8")


def _is_process_running(pid: int | None) -> bool:
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
    if job_dir is None:
        return {"running": False, "pid": None}

    pid = _read_helper_pid(job_dir)
    running = _is_process_running(pid)
    if not running:
        _clear_helper_state(job_dir)
        pid = None
    return {"running": running, "pid": pid}


def stop_procurement_helper(job_dir: Path) -> tuple[bool, list[str]]:
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


def _build_runtime_ahk_script(csv_path: Path) -> str:
    csv_literal = str(csv_path).replace("\\", "\\\\")
    return f"""; AutoHotkey v2.0+
#SingleInstance Force
Persistent

sleeptime := 300
doublesleeptime := 3000
csvPath := "{csv_literal}"
isRunning := false

Esc::
{{
    ExitApp
}}

+Space::
{{
    global csvPath, sleeptime, doublesleeptime, isRunning
    if (isRunning)
        return
    isRunning := true

    try content := FileRead(csvPath, "UTF-8")
    catch {{
        MsgBox "Hiba: Nem sikerult beolvasni a fajlt: " csvPath
        ExitApp
    }}

    lines := StrSplit(content, "`n", "`r")
    for _, line in lines
    {{
        line := Trim(line)
        if (line = "")
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


def _build_runtime_powershell_script(csv_path: Path) -> str:
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
$stepDelayMs = 220
$insertDelayMs = 2800
$hotkeyPollDelayMs = 90
$postHotkeyDelayMs = 420
$lastStartHotkeyState = $false

function Test-KeyDown([int]$vkCode) {{
    return (([DivianKeyboardState]::GetAsyncKeyState($vkCode) -band 0x8000) -ne 0)
}}

function Test-StopRequested {{
    return Test-KeyDown 0x1B
}}

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

$rows = Get-Content -Path $csvPath -Encoding UTF8 | Where-Object {{ $_.Trim() -ne "" }}
foreach ($row in $rows) {{
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
    Set-Clipboard -Value $articleCode
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
    Set-Clipboard -Value $quantity
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {{
        exit
    }}
    [System.Windows.Forms.SendKeys]::SendWait('{{TAB}}')
    Start-Sleep -Milliseconds 140
    [System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
    Start-Sleep -Milliseconds $stepDelayMs
}}
"""


def launch_procurement_helper(job_dir: Path) -> tuple[bool, list[str]]:
    job_dir.mkdir(parents=True, exist_ok=True)
    csv_path = job_dir / "rendeles_sima.csv"
    if not csv_path.exists():
        return False, ["A Beszerzes fajl nem talalhato."]

    if os.name != "nt":
        return False, ["Az automatikus import jelenleg Windows alatt erheto el."]

    state = get_procurement_helper_state(job_dir)
    if state.get("running"):
        return True, ["Az import-seged mar fut. Shift + Space: inditas, ESC: leallitas."]

    _clear_helper_state(job_dir)
    _helper_ahk_path(job_dir).write_text(_build_runtime_ahk_script(csv_path), encoding="utf-8")
    _helper_powershell_path(job_dir).write_text(_build_runtime_powershell_script(csv_path), encoding="utf-8")

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
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_helper_powershell_path(job_dir)),
            ],
            cwd=str(job_dir),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    _write_helper_pid(job_dir, process.pid)
    return True, ["Az import-seged elindult. Shift + Space: inditas, ESC: leallitas."]
