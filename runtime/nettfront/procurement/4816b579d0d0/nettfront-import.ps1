$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DivianKeyboardState {
    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);
}
"@

$csvPath = 'C:\Users\baloghr\Documents\GitHub\Weboldal\runtime\nettfront\procurement\4816b579d0d0\rendeles_sima.csv'
$stepDelayMs = 220
$insertDelayMs = 2800
$hotkeyPollDelayMs = 90
$postHotkeyDelayMs = 420
$lastStartHotkeyState = $false

function Test-KeyDown([int]$vkCode) {
    return (([DivianKeyboardState]::GetAsyncKeyState($vkCode) -band 0x8000) -ne 0)
}

function Test-StopRequested {
    return Test-KeyDown 0x1B
}

while ($true) {
    if (Test-StopRequested) {
        exit
    }

    $shiftDown = Test-KeyDown 0x10
    $spaceDown = Test-KeyDown 0x20
    $hotkeyDown = $shiftDown -and $spaceDown
    if ($hotkeyDown -and -not $script:lastStartHotkeyState) {
        break
    }

    $script:lastStartHotkeyState = $hotkeyDown
    Start-Sleep -Milliseconds $hotkeyPollDelayMs
}

while (Test-KeyDown 0x10 -or Test-KeyDown 0x20) {
    Start-Sleep -Milliseconds 40
}
Start-Sleep -Milliseconds $postHotkeyDelayMs

$rows = Get-Content -Path $csvPath -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }
foreach ($row in $rows) {
    if (Test-StopRequested) {
        exit
    }

    $parts = $row -split ';'
    if ($parts.Count -lt 2) {
        continue
    }

    $articleCode = $parts[0].Trim()
    $quantity = $parts[1].Trim()
    if ([string]::IsNullOrWhiteSpace($articleCode)) {
        continue
    }

    if (Test-StopRequested) {
        exit
    }
    Set-Clipboard -Value $articleCode
    [System.Windows.Forms.SendKeys]::SendWait('{INSERT}')
    Start-Sleep -Milliseconds $insertDelayMs

    if (Test-StopRequested) {
        exit
    }
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}{TAB}')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {
        exit
    }
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {
        exit
    }
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {
        exit
    }
    Set-Clipboard -Value $quantity
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    if (Test-StopRequested) {
        exit
    }
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}')
    Start-Sleep -Milliseconds 140
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds $stepDelayMs
}
