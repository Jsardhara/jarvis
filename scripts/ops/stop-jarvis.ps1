# Stop Jarvis stack: kill API, Sentinel, Voice, Dashboard, ATLAS.
$ErrorActionPreference = 'Continue'

Write-Host "=== Stopping running Jarvis processes ===" -ForegroundColor Yellow

$targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match 'jarvis\\(web|voice|sentinel)|jarvis-(api|voice|sentinel|dashboard)|jarvis\.web\.api|run_agent\.py|atlas.*uvicorn|atlas.*main|atlas\\scripts') `
    -and ($_.CommandLine -notmatch 'claude|VSCode|cursor|restart-jarvis|stop-jarvis|desktop_mcp')
}

if ($targets) {
    foreach ($p in $targets) {
        Write-Host "  kill PID $($p.ProcessId) :: $($p.Name)" -ForegroundColor DarkGray
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { Write-Host "    (already gone)" }
    }
} else {
    Write-Host "  (no matching processes)"
}

Write-Host ""
Write-Host "Stack stopped." -ForegroundColor Cyan
