# Install Windows scheduled tasks so jarvis API, sentinel daemon, and the
# Next.js dashboard start automatically at user logon and restart on crash.
#
# Tasks installed:
#   Jarvis-API        — `python -m uvicorn jarvis.web.api:app --host 0.0.0.0 --port 8765`
#   Jarvis-Sentinel   — `python -m jarvis.daemon.sentinel`
#   Jarvis-Dashboard  — `pnpm dev` (or `pnpm start` if -Mode prod) inside web/
#
# Usage:
#   pwsh -File scripts/install-services.ps1                  # dev mode (next dev)
#   pwsh -File scripts/install-services.ps1 -Mode prod       # built next start
#   pwsh -File scripts/install-services.ps1 -Uninstall       # remove all 3 tasks
#
# Notes:
# - Tasks run as the current user, at logon, with restart on failure (3x, 1 min).
# - Logs go to %LOCALAPPDATA%\Jarvis\logs\<task>.log
# - Requires PowerShell 5.1+ (built into Windows 10/11) — no admin needed for
#   per-user logon tasks.

param(
    [ValidateSet('dev', 'prod')]
    [string]$Mode = 'dev',

    [int]$ApiPort = 8765,
    [int]$WebPort = 3000,

    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir      = Join-Path $env:LOCALAPPDATA 'Jarvis\logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$tasks = @(
    @{
        Name        = 'Jarvis-API'
        Description = 'Jarvis FastAPI on 0.0.0.0:' + $ApiPort
        Cmd         = 'python'
        Args        = "-m uvicorn jarvis.web.api:app --host 0.0.0.0 --port $ApiPort"
        WorkDir     = $projectRoot
        Log         = Join-Path $logDir 'api.log'
    },
    @{
        Name        = 'Jarvis-Sentinel'
        Description = 'Jarvis sentinel background daemon'
        Cmd         = 'python'
        Args        = '-m jarvis.daemon.sentinel'
        WorkDir     = $projectRoot
        Log         = Join-Path $logDir 'sentinel.log'
    },
    @{
        Name        = 'Jarvis-Dashboard'
        Description = "Jarvis Next.js dashboard ($Mode) on :$WebPort"
        Cmd         = 'pnpm'
        Args        = if ($Mode -eq 'prod') { 'start --port ' + $WebPort } else { 'dev --port ' + $WebPort }
        WorkDir     = Join-Path $projectRoot 'web'
        Log         = Join-Path $logDir 'dashboard.log'
    }
)

function Remove-JarvisTask {
    param([string]$Name)
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "[install-services] removed: $Name" -ForegroundColor Yellow
    }
}

if ($Uninstall) {
    foreach ($t in $tasks) {
        Remove-JarvisTask -Name $t.Name
    }
    Write-Host "[install-services] uninstall complete" -ForegroundColor Green
    exit 0
}

# Always remove first so re-running picks up new args.
foreach ($t in $tasks) {
    Remove-JarvisTask -Name $t.Name
}

$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

foreach ($t in $tasks) {
    # Wrap each command so stdout+stderr append to the per-task log file.
    $logEsc = $t.Log -replace '"', '\"'
    $wrapped = "cmd.exe /c `"cd /d `"$($t.WorkDir)`" && $($t.Cmd) $($t.Args) >> `"$logEsc`" 2>&1`""

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument @"
-NoProfile -WindowStyle Hidden -Command "$wrapped"
"@

    Register-ScheduledTask `
        -TaskName    $t.Name `
        -Description $t.Description `
        -Action      $action `
        -Trigger     $trigger `
        -Settings    $settings `
        -Principal   $principal `
        -Force | Out-Null
    Write-Host "[install-services] installed: $($t.Name)  →  $($t.Log)" -ForegroundColor Green
}

Write-Host ""
Write-Host "[install-services] done. Tasks fire on next logon." -ForegroundColor Cyan
Write-Host "Start now:        Get-ScheduledTask -TaskName 'Jarvis-*' | Start-ScheduledTask" -ForegroundColor Cyan
Write-Host "Stop now:         Get-ScheduledTask -TaskName 'Jarvis-*' | Stop-ScheduledTask" -ForegroundColor Cyan
Write-Host "Tail logs:        Get-Content -Wait $logDir\*.log" -ForegroundColor Cyan
