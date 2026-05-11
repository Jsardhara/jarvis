# Restart Jarvis stack: kill running services then relaunch all 4 launchers + ATLAS.
# Idempotent: safe to run when nothing is running.

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$launchers = Join-Path $root 'scripts\launchers'

Write-Host "=== Stopping running Jarvis processes ===" -ForegroundColor Yellow

$targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match 'jarvis\\(web|voice|sentinel)|jarvis-(api|voice|sentinel|dashboard)|atlas.*uvicorn|atlas.*main') `
    -and ($_.CommandLine -notmatch 'claude|VSCode|cursor|restart-jarvis')
}

if ($targets) {
    foreach ($p in $targets) {
        Write-Host "  kill PID $($p.ProcessId) :: $($p.Name)" -ForegroundColor DarkGray
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { Write-Host "    (already gone)" }
    }
} else {
    Write-Host "  (no matching processes)"
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== Launching stack ===" -ForegroundColor Green

$batches = @(
    'jarvis-api.bat',
    'jarvis-sentinel.bat',
    'jarvis-voice.bat',
    'jarvis-dashboard.bat'
)

foreach ($b in $batches) {
    $path = Join-Path $launchers $b
    if (Test-Path $path) {
        Write-Host "  start $b"
        Start-Process -FilePath $path -WindowStyle Minimized
    } else {
        Write-Host "  MISSING: $path" -ForegroundColor Red
    }
}

# ATLAS launcher (Startup folder)
$atlasLauncher = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\atlas.bat"
if (Test-Path $atlasLauncher) {
    Write-Host "  start atlas.bat (Startup)"
    Start-Process -FilePath $atlasLauncher -WindowStyle Minimized
}

Write-Host ""
Write-Host "Stack restarting in background. API ready in ~5s." -ForegroundColor Cyan
