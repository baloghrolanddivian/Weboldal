$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$UserName,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [Parameter(Mandatory = $true)]
    [string]$ManufacturingRoot,

    [int]$Port = 5000
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runnerScript = Join-Path $repoRoot "tools\divian_hub_runner.ps1"
$taskName = "Divian-HUB-24x7"

$escapedRoot = $ManufacturingRoot.Replace('"', '\"')
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`" -ManufacturingRoot `"$escapedRoot`" -Port $Port"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

$securePassword = ConvertTo-SecureString $Password -AsPlainText -Force
$principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType Password -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Password $Password -Description "Divian-HUB 24/7 startup task" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Output "Installed startup task: $taskName"
Write-Output "Manufacturing root: $ManufacturingRoot"
Write-Output "Port: $Port"
