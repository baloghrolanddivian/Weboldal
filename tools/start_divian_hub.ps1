$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtimeDir = Join-Path $repoRoot "runtime\server"
$pidFile = Join-Path $runtimeDir "divian-hub-runner.pid"
$runnerScript = Join-Path $repoRoot "tools\divian_hub_runner.ps1"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

if (Test-Path $pidFile) {
    $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existingPid -and (Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue)) {
        Write-Output "Divian-HUB runner already running (PID $existingPid)."
        exit 0
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
}

$process = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runnerScript -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
Write-Output ("Divian-HUB runner started (PID {0})." -f $process.Id)
