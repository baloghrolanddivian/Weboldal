$ErrorActionPreference = "Stop"

$taskName = "Divian-HUB"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$startScript = Join-Path $repoRoot "tools\start_divian_hub.ps1"
$workingDir = $repoRoot

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`"" -WorkingDirectory $workingDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Divian-HUB auto start and auto restart runner" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Scheduled task installed and started: $taskName"
