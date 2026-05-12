# ship-bug-check.ps1 — finalize the bug-check sweep and push to GitHub.
#
# Usage (from PowerShell, in C:\Users\jyot2\jarvis):
#   ./scripts/ship-bug-check.ps1
#
# What it does:
#   1. Removes the stale .git/index.lock (held open by something earlier)
#   2. Stages the renormalized + new files for the bug-check / phone-access work
#   3. Commits with a structured message
#   4. Pushes the current branch (design/v2) AND main (which is 26 commits ahead)

$ErrorActionPreference = 'Stop'
Set-Location -Path "$PSScriptRoot\.."

# 1. Clear stale lock
if (Test-Path .git/index.lock) {
    Remove-Item .git/index.lock -Force
    Write-Host "Removed stale .git/index.lock"
}

# 2. Stage everything that should ship
$paths = @(
    '.gitattributes',
    '.gitignore',
    '.env.example',
    'PHONE.md',
    'pyproject.toml',
    'jarvis/briefing.py',
    'jarvis/config.py',
    'jarvis/daemon/notifier.py',
    'jarvis/orchestrator.py',
    'jarvis/state.py',
    'jarvis/subsystems/scholar_study.py',
    'jarvis/subsystems/study_db.py',
    'jarvis/web/api.py',
    'tests/test_notifier.py',
    'scripts/',
    'web/.env.example',
    'web/next.config.ts',
    'web/package.json',
    'web/public/',
    'web/src/app/api/auth/',
    'web/src/app/apple-icon.tsx',
    'web/src/app/layout.tsx',
    'web/src/components/auth-gate.tsx',
    'web/src/components/sw-register.tsx',
    'web/src/lib/api-client.ts'
)
git add -- $paths

# 3. Commit
$msg = @"
feat(phone+hygiene): tailscale + ntfy + PWA auth gate; ruff sweep; LF normalization

Phone access (PC must be on tailnet):
- ntfy.sh notifier with priority mapping; PushoverNotifier still preferred
- FastAPI CORS now env-driven (JARVIS_CORS_ORIGINS, JARVIS_CORS_REGEX)
- Next.js allowedDevOrigins env-driven (JARVIS_DEV_ORIGINS)
- PWA manifest + service worker + apple icon + maskable icons
- AuthGate client component: probes /api/auth/check, prompts for token,
  persists in localStorage. Token-less local dev still works.
- Tests: 5 new ntfy cases (publish, error, default-picker, pushover preference)
- Docs: PHONE.md with Tailscale + ntfy + PWA install steps
- Helper: scripts/phone-setup.ps1

Code hygiene:
- Ruff fixes: SIM102/SIM105/SIM108/F841/ARG001 in jarvis/{briefing,orchestrator,state,subsystems}
- pyproject: per-file-ignore for SupervisedFailure (N818) and tests SIM117/I001/E741
- .gitattributes: text=auto eol=lf with CRLF carve-outs for *.bat/*.cmd/*.ps1
- .gitignore: pnpm _tmp_* leftovers
"@

git commit -m $msg

# 4. Push design/v2 + main
$current = git rev-parse --abbrev-ref HEAD
git push -u origin $current

git push origin main
