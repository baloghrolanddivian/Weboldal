$ErrorActionPreference = "SilentlyContinue"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtimeDir = Join-Path $repoRoot "runtime\server"
$pidFile = Join-Path $runtimeDir "divian-hub-runner.pid"

if (Test-Path $pidFile) {
    $runnerPid = Get-Content $pidFile | Select-Object -First 1
    if ($runnerPid) {
        Stop-Process -Id ([int]$runnerPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
}

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match "python|py|powershell" -and $_.CommandLine -match "app\.py|divian_hub_runner\.ps1" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Output "Divian-HUB stopped."
