# Tailscale Serve / Funnel helper for Jarvis.
#
# Modes:
#   serve   - tailnet-only HTTPS proxy (default, private to your tailnet)
#   funnel  - public HTTPS via *.ts.net (requires tailscale funnel flag enabled)
#
# Routes mounted (proxy -> local port):
#   /        -> http://localhost:3000   (Next.js dashboard)
#   /api     -> http://localhost:8765   (Jarvis FastAPI)
#   /atlas   -> http://localhost:8000   (ATLAS API)
#
# Usage:
#   pwsh -File scripts/tailscale-serve.ps1                      # tailnet-only
#   pwsh -File scripts/tailscale-serve.ps1 -Mode funnel         # public HTTPS
#   pwsh -File scripts/tailscale-serve.ps1 -Stop                # tear down
#
# Prereq: Tailscale installed + 'tailscale up' already run.

param(
    [ValidateSet('serve', 'funnel')]
    [string]$Mode = 'serve',

    [int]$DashboardPort = 3000,
    [int]$ApiPort       = 8765,
    [int]$AtlasPort     = 8000,

    [switch]$Stop
)

$ErrorActionPreference = 'Stop'

function Test-Tailscale {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return }
    $defaultPath = 'C:\Program Files\Tailscale'
    if (Test-Path (Join-Path $defaultPath 'tailscale.exe')) {
        $env:PATH = "$defaultPath;$env:PATH"
        Write-Host "[tailscale] using $defaultPath\tailscale.exe" -ForegroundColor Cyan
        return
    }
    Write-Host "[tailscale] not installed. Get it: https://tailscale.com/download/windows" -ForegroundColor Red
    exit 1
}

function Get-TailnetHost {
    try {
        $status = & tailscale status --json | ConvertFrom-Json
        if ($status.Self.DNSName) {
            return $status.Self.DNSName.TrimEnd('.')
        }
    } catch {
        Write-Host "[tailscale] status query failed - is tailscale logged in? Run: tailscale up" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[tailscale] no Self.DNSName - login required" -ForegroundColor Yellow
    exit 1
}

Test-Tailscale

if ($Stop) {
    Write-Host "[tailscale] tearing down all serve/funnel routes" -ForegroundColor Cyan
    & tailscale serve reset
    & tailscale funnel reset 2>$null
    Write-Host "[tailscale] done." -ForegroundColor Green
    exit 0
}

$tailHost = Get-TailnetHost
Write-Host "[tailscale] tailnet host: $tailHost" -ForegroundColor Green

& tailscale serve reset
if ($Mode -eq 'funnel') { & tailscale funnel reset 2>$null }

$cmd = if ($Mode -eq 'funnel') { 'funnel' } else { 'serve' }

Write-Host "[tailscale] mounting routes via tailscale $cmd" -ForegroundColor Cyan
# Dashboard at root.
& tailscale $cmd --bg --https=443 --set-path=/      "http://localhost:$DashboardPort"
# Jarvis API: keep /api prefix on upstream so FastAPI routes (which all live under
# /api/*) match correctly. tailscale strips the --set-path prefix by default.
& tailscale $cmd --bg --https=443 --set-path=/api   "http://localhost:$ApiPort/api"
# Atlas API: routes are top-level (/system/health, /portfolio, etc.), so strip is OK.
& tailscale $cmd --bg --https=443 --set-path=/atlas "http://localhost:$AtlasPort"

Write-Host ""
Write-Host "[tailscale] active routes:" -ForegroundColor Cyan
& tailscale serve status

if ($Mode -eq 'funnel') {
    Write-Host "[tailscale] funnel public status:" -ForegroundColor Cyan
    & tailscale funnel status
    Write-Host ""
    Write-Host "Public URL:    https://$tailHost/" -ForegroundColor Magenta
} else {
    Write-Host ""
    Write-Host "Tailnet URL:   https://$tailHost/" -ForegroundColor Magenta
}
Write-Host "Dashboard:     https://$tailHost/" -ForegroundColor Green
Write-Host "Jarvis API:    https://$tailHost/api/health" -ForegroundColor Green
Write-Host "ATLAS API:     https://$tailHost/atlas/system/health" -ForegroundColor Green
Write-Host ""
Write-Host "Phone: install Tailscale app, log in, then open the dashboard URL in Safari/Chrome and Add to Home Screen." -ForegroundColor Yellow
