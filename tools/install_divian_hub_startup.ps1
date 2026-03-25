$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$startScript = Join-Path $repoRoot "tools\start_divian_hub.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$startupFile = Join-Path $startupDir "Divian-HUB.cmd"

$content = "@echo off`r`n" +
    "powershell -NoProfile -ExecutionPolicy Bypass -File `"$startScript`"`r`n"

[System.IO.File]::WriteAllText($startupFile, $content, [System.Text.Encoding]::ASCII)
Write-Output "Startup launcher created: $startupFile"
