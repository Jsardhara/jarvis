# Install Jarvis auto-start launchers in the user Startup folder.
#
# Drops three .bat files into:
#   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
# Each runs the corresponding service in a hidden console at logon. No admin
# needed (this is the user-scoped startup folder, not All Users).
#
# Tasks installed:
#   jarvis-api.bat        - python -m uvicorn jarvis.web.api:app --host 0.0.0.0 --port 8765
#   jarvis-sentinel.bat   - python -m jarvis.daemon.sentinel
#   jarvis-voice.bat      - python -m jarvis.voice  (gated on VOICE_ENABLED=true in .env)
#   jarvis-dashboard.bat  - pnpm dev (or pnpm start if -Mode prod) inside web/
#
# Usage:
#   pwsh -File scripts/install-services.ps1                  # dev mode
#   pwsh -File scripts/install-services.ps1 -Mode prod       # built next start
#   pwsh -File scripts/install-services.ps1 -Uninstall       # remove launchers

param(
    [ValidateSet('dev', 'prod')]
    [string]$Mode = 'dev',

    [int]$ApiPort = 8765,
    [int]$WebPort = 3000,

    [switch]$Uninstall
)

$ErrorActionPreference = 'Continue'

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir      = Join-Path $env:LOCALAPPDATA 'Jarvis\logs'
$startupDir  = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

if (-not (Test-Path $startupDir)) {
    Write-Host "[install-services] startup dir missing: $startupDir" -ForegroundColor Red
    exit 1
}

$dashCmd = if ($Mode -eq 'prod') { 'pnpm start --port ' + $WebPort } else { 'pnpm dev --port ' + $WebPort }

$tasks = @(
    @{
        Name    = 'jarvis-api.bat'
        WorkDir = $projectRoot
        Cmd     = "python -m uvicorn jarvis.web.api:app --host 0.0.0.0 --port $ApiPort"
        Log     = Join-Path $logDir 'api.log'
    },
    @{
        Name    = 'jarvis-sentinel.bat'
        WorkDir = $projectRoot
        Cmd     = 'python -m jarvis.daemon.sentinel'
        Log     = Join-Path $logDir 'sentinel.log'
    },
    @{
        Name    = 'jarvis-voice.bat'
        WorkDir = $projectRoot
        Cmd     = 'python -m jarvis.voice'
        Log     = Join-Path $logDir 'voice.log'
    },
    @{
        Name    = 'jarvis-dashboard.bat'
        WorkDir = (Join-Path $projectRoot 'web')
        Cmd     = $dashCmd
        Log     = Join-Path $logDir 'dashboard.log'
    }
)

if ($Uninstall) {
    foreach ($t in $tasks) {
        $path = Join-Path $startupDir $t.Name
        if (Test-Path $path) {
            Remove-Item -Force $path
            Write-Host "[install-services] removed: $($t.Name)" -ForegroundColor Yellow
        }
    }
    Write-Host "[install-services] uninstall complete" -ForegroundColor Green
    exit 0
}

foreach ($t in $tasks) {
    $batPath = Join-Path $startupDir $t.Name

    # @echo off + start /B runs the command in the background without spawning
    # a visible console window per service. Output is redirected to the log.
    $bat = @"
@echo off
cd /d "$($t.WorkDir)"
start "" /B cmd /c "$($t.Cmd) >> ""$($t.Log)"" 2>&1"
"@
    Set-Content -Path $batPath -Value $bat -Encoding ASCII
    Write-Host "[install-services] installed: $batPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "[install-services] done. Services launch on next logon." -ForegroundColor Cyan
Write-Host "Start now:    foreach name in jarvis-api jarvis-sentinel jarvis-dashboard, run the matching .bat in $startupDir" -ForegroundColor Cyan
Write-Host "Stop now:     kill the python.exe / node.exe processes via Task Manager" -ForegroundColor Cyan
Write-Host "Tail logs:    Get-Content -Wait $logDir\*.log" -ForegroundColor Cyan
