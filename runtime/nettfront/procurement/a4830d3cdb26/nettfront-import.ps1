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

$csvPath = 'C:\Users\baloghr\Documents\GitHub\Weboldal\runtime\nettfront\procurement\a4830d3cdb26\rendeles_sima.csv'
$pauseFlagPath = 'C:\Users\baloghr\Documents\GitHub\Weboldal\runtime\nettfront\procurement\a4830d3cdb26\nettfront-helper.paused'
$stepDelayMs = 220
$insertDelayMs = 2800
$hotkeyPollDelayMs = 90
$postHotkeyDelayMs = 420
$pauseCheckDelayMs = 120
$paused = $false
$lastStartHotkeyState = $false
$lastPauseHotkeyState = $false

function Set-PausedFlag([bool]$isPaused) {
    if ($isPaused) {
        Set-Content -Path $pauseFlagPath -Value "paused" -Encoding UTF8
    } elseif (Test-Path $pauseFlagPath) {
        Remove-Item -Force $pauseFlagPath
    }
}

function Update-PauseToggle {
    $shiftDown = ([DivianKeyboardState]::GetAsyncKeyState(0x10) -band 0x8000) -ne 0
    $enterDown = ([DivianKeyboardState]::GetAsyncKeyState(0x0D) -band 0x8000) -ne 0
    $pauseHotkeyDown = $shiftDown -and $enterDown
    if ($pauseHotkeyDown -and -not $script:lastPauseHotkeyState) {
        $script:paused = -not $script:paused
        Set-PausedFlag $script:paused
    }
    $script:lastPauseHotkeyState = $pauseHotkeyDown
}

function Wait-WhilePaused {
    while ($script:paused) {
        Update-PauseToggle
        Start-Sleep -Milliseconds $pauseCheckDelayMs
    }
}

Set-PausedFlag $false

while ($true) {
    Update-PauseToggle
    $shiftDown = ([DivianKeyboardState]::GetAsyncKeyState(0x10) -band 0x8000) -ne 0
    $spaceDown = ([DivianKeyboardState]::GetAsyncKeyState(0x20) -band 0x8000) -ne 0
    $hotkeyDown = $shiftDown -and $spaceDown
    if (-not $script:paused -and $hotkeyDown -and -not $script:lastStartHotkeyState) {
        break
    }

    $script:lastStartHotkeyState = $hotkeyDown
    Start-Sleep -Milliseconds $hotkeyPollDelayMs
}

while (([DivianKeyboardState]::GetAsyncKeyState(0x10) -band 0x8000) -ne 0 -or ([DivianKeyboardState]::GetAsyncKeyState(0x20) -band 0x8000) -ne 0) {
    Start-Sleep -Milliseconds 40
}
Start-Sleep -Milliseconds $postHotkeyDelayMs

$rows = Get-Content -Path $csvPath -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }
foreach ($row in $rows) {
    Wait-WhilePaused
    $parts = $row -split ';'
    if ($parts.Count -lt 2) {
        continue
    }

    $articleCode = $parts[0].Trim()
    $quantity = $parts[1].Trim()
    if ([string]::IsNullOrWhiteSpace($articleCode)) {
        continue
    }

    Set-Clipboard -Value $articleCode
    [System.Windows.Forms.SendKeys]::SendWait('{INSERT}')
    Start-Sleep -Milliseconds $insertDelayMs

    Wait-WhilePaused
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}{TAB}')
    Start-Sleep -Milliseconds $stepDelayMs

    Wait-WhilePaused
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    Wait-WhilePaused
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}')
    Start-Sleep -Milliseconds $stepDelayMs

    Wait-WhilePaused
    Set-Clipboard -Value $quantity
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds $stepDelayMs

    Wait-WhilePaused
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}')
    Start-Sleep -Milliseconds 140
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds $stepDelayMs
}

Set-PausedFlag $false
