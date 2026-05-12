# Jarvis phone-mode launcher.
#
# Starts FastAPI + Next.js bound to all interfaces so the tailnet phone client
# can reach them. Reads .env from project root.
#
# Usage:  pwsh -File scripts/phone-setup.ps1
#         pwsh -File scripts/phone-setup.ps1 -Mode prod   # prod-build mode

param(
    [ValidateSet('dev', 'prod')]
    [string]$Mode = 'dev',
    [int]$ApiPort = 8765,
    [int]$WebPort = 3000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "[jarvis] project root: $projectRoot" -ForegroundColor Cyan

# ── 1. Resolve tailnet hostname ────────────────────────────────────────────
$tailHost = $null
try {
    $status = & tailscale status --json 2>$null | ConvertFrom-Json
    if ($status -and $status.Self -and $status.Self.DNSName) {
        $tailHost = $status.Self.DNSName.TrimEnd('.')
    }
} catch {
    Write-Host "[jarvis] tailscale not detected. Install: https://tailscale.com/download" -ForegroundColor Yellow
}

if ($tailHost) {
    Write-Host "[jarvis] tailnet host: $tailHost" -ForegroundColor Green
} else {
    $tailHost = "$env:COMPUTERNAME"
    Write-Host "[jarvis] no tailnet — falling back to LAN hostname: $tailHost" -ForegroundColor Yellow
}

# ── 2. Compose origin list for CORS / dev-origin allowlist ─────────────────
$apiOrigin = "http://${tailHost}:$ApiPort"
$webOrigin = "http://${tailHost}:$WebPort"
$env:JARVIS_CORS_ORIGINS = "http://localhost:$WebPort,$webOrigin"
$env:JARVIS_DEV_ORIGINS = $webOrigin
$env:NEXT_PUBLIC_JARVIS_API = $apiOrigin

# ── 3. Verify auth token exists, generate if missing ───────────────────────
$envWeb = Join-Path $projectRoot 'web/.env.local'
if (-not (Test-Path $envWeb)) {
    $token = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
    @"
MC_API_TOKEN=$token
NEXT_PUBLIC_MC_API_TOKEN=$token
NEXT_PUBLIC_JARVIS_API=$apiOrigin
"@ | Out-File -FilePath $envWeb -Encoding utf8
    Write-Host "[jarvis] generated auth token in $envWeb" -ForegroundColor Green
    Write-Host "[jarvis] token: $token" -ForegroundColor Magenta
    Write-Host "[jarvis] enter this token on first phone connection" -ForegroundColor Magenta
} else {
    $token = (Get-Content $envWeb | Select-String -Pattern '^MC_API_TOKEN=(.+)$' | ForEach-Object { $_.Matches[0].Groups[1].Value }) -join ''
    Write-Host "[jarvis] using existing token from $envWeb" -ForegroundColor Cyan
    if ($token) {
        Write-Host "[jarvis] token: $token" -ForegroundColor Magenta
    }
}

# ── 4. Start FastAPI on 0.0.0.0 ────────────────────────────────────────────
Write-Host "[jarvis] starting FastAPI on $apiOrigin" -ForegroundColor Cyan
$apiProc = Start-Process -PassThru -NoNewWindow -FilePath 'python' `
    -ArgumentList '-m', 'uvicorn', 'jarvis.apps.api.app:app', '--host', '0.0.0.0', '--port', "$ApiPort"

Start-Sleep -Seconds 2

# ── 5. Start Next.js ───────────────────────────────────────────────────────
Push-Location (Join-Path $projectRoot 'web')
try {
    if ($Mode -eq 'prod') {
        Write-Host "[jarvis] building Next.js (prod)" -ForegroundColor Cyan
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw 'pnpm build failed' }
        Write-Host "[jarvis] starting Next.js (prod) on $webOrigin" -ForegroundColor Cyan
        $webProc = Start-Process -PassThru -NoNewWindow -FilePath 'pnpm' -ArgumentList 'start:lan'
    } else {
        Write-Host "[jarvis] starting Next.js (dev) on $webOrigin" -ForegroundColor Cyan
        $webProc = Start-Process -PassThru -NoNewWindow -FilePath 'pnpm' -ArgumentList 'dev:lan'
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "──────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "  PHONE READY" -ForegroundColor Green
Write-Host "  open on phone:  $webOrigin" -ForegroundColor Green
Write-Host "  api:            $apiOrigin" -ForegroundColor Green
Write-Host "  Ctrl+C to stop both"
Write-Host "──────────────────────────────────────────────────────" -ForegroundColor Cyan

try {
    Wait-Process -Id $apiProc.Id, $webProc.Id
} finally {
    if ($apiProc -and -not $apiProc.HasExited) { Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue }
    if ($webProc -and -not $webProc.HasExited) { Stop-Process -Id $webProc.Id -Force -ErrorAction SilentlyContinue }
}
