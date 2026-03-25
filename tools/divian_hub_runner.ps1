$ErrorActionPreference = "Stop"

param(
    [string]$ManufacturingRoot = "",
    [int]$Port = 5000
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtimeDir = Join-Path $repoRoot "runtime\server"
$logFile = Join-Path $runtimeDir "divian-hub.log"
$outFile = Join-Path $runtimeDir "divian-hub.out.log"
$errFile = Join-Path $runtimeDir "divian-hub.err.log"
$pidFile = Join-Path $runtimeDir "divian-hub-runner.pid"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Set-Location $repoRoot

[System.IO.File]::WriteAllText($pidFile, $PID.ToString())

try {
    $env:PYTHONUTF8 = "1"
    if (-not $env:DIVIAN_HUB_DEV_RELOAD) {
        $env:DIVIAN_HUB_DEV_RELOAD = "1"
    }
    if ($ManufacturingRoot) {
        $env:DIVIAN_MANUFACTURING_ROOT = $ManufacturingRoot
    }
    $env:DIVIAN_HUB_PORT = [string]$Port

    Add-Content -Path $logFile -Value ("[{0}] Runner started (PID {1})" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $PID)
    if ($ManufacturingRoot) {
        Add-Content -Path $logFile -Value ("[{0}] Manufacturing root: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $ManufacturingRoot)
    }

    while ($true) {
        Add-Content -Path $logFile -Value ("[{0}] Launching app.py" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
        $process = Start-Process -FilePath "py" -ArgumentList "-3", "app.py" -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        Add-Content -Path $logFile -Value ("[{0}] app.py exited with code {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $exitCode)
        Start-Sleep -Seconds 2
    }
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
}
