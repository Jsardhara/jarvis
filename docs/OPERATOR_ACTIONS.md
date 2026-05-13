# Operator Actions — Manual Steps to Finalize the Fix Campaign

Run these in order from a Windows PowerShell or Command Prompt in `C:\Users\jyot2\jarvis`. All steps are required to finish what the in-session fix campaign couldn't do from the sandbox.

Time estimate: ~10–15 minutes total. Steps 1–3 are required; step 4 is recommended; step 5 is optional.

---

## Step 1 — Clear the stale git lock (30 seconds)

The sandbox couldn't make branches because a Windows-side `index.lock` file was orphaned from a crashed git operation.

```powershell
Remove-Item C:\Users\jyot2\jarvis\.git\index.lock -ErrorAction SilentlyContinue
Remove-Item C:\Users\jyot2\jarvis\.git\index.lock.bak -ErrorAction SilentlyContinue
Remove-Item C:\Users\jyot2\jarvis\.git\index.lock.stale2 -ErrorAction SilentlyContinue
Remove-Item C:\Users\jyot2\jarvis\.git\index.stash.6.lock.bak -ErrorAction SilentlyContinue
```

Verify:

```powershell
cd C:\Users\jyot2\jarvis
git status
```

You should see normal output (no "fatal:" or "unable to unlink").

---

## Step 2 — Delete files the sandbox couldn't unlink (2 minutes)

Linux mount permissions blocked file deletion from the sandbox. All these files are either dead stubs, abandoned worktrees, or orphan pages confirmed unimported by grep. Safe to delete.

### 2a. Dead component files

```powershell
cd C:\Users\jyot2\jarvis
Remove-Item -Recurse -Force web\src\components\mission
Remove-Item -Force web\src\components\sidebar-nav.tsx
```

### 2b. Abandoned worktrees (~150 dead .py files)

```powershell
# First, properly detach them from git's worktree tracking:
git worktree remove --force .claude\worktrees\hardcore-noyce-3c8ea5
git worktree remove --force .claude\worktrees\intelligent-leakey-995f20

# If git complains the worktrees are already gone, prune the references:
git worktree prune

# Then remove any leftover directories:
Remove-Item -Recurse -Force .claude\worktrees\hardcore-noyce-3c8ea5 -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .claude\worktrees\intelligent-leakey-995f20 -ErrorAction SilentlyContinue
```

### 2c. Orphan pages (you chose to delete these)

```powershell
Remove-Item -Recurse -Force web\src\app\crew
Remove-Item -Recurse -Force web\src\app\skills
Remove-Item -Recurse -Force web\src\app\exports
Remove-Item -Recurse -Force web\src\app\objectives
Remove-Item -Recurse -Force web\src\app\projects
Remove-Item -Recurse -Force web\src\app\team
Remove-Item -Recurse -Force web\src\app\launch
Remove-Item -Recurse -Force web\src\app\jarvis
```

### 2d. Junk in `state/`

```powershell
Remove-Item state\MORNING_BRIEF.md -ErrorAction SilentlyContinue
Remove-Item state\daily_forge_test.log -ErrorAction SilentlyContinue
Remove-Item state\daily_forge_test2.log -ErrorAction SilentlyContinue
Remove-Item state\screenshot.png -ErrorAction SilentlyContinue
# Duplicate scholar seed (linalg_exam.json is identical to linalg.json):
Remove-Item state\scholar_seeds\linalg_exam.json -ErrorAction SilentlyContinue
```

---

## Step 3 — Regenerate the web lockfile and install deps (3 minutes)

CI's `pnpm install --frozen-lockfile` has been failing on every push because `web/pnpm-lock.yaml` is missing. This regenerates it.

```powershell
cd C:\Users\jyot2\jarvis\web
pnpm install
```

If `pnpm` isn't installed:

```powershell
npm install -g pnpm@latest
cd C:\Users\jyot2\jarvis\web
pnpm install
```

After it finishes, you should have a fresh `pnpm-lock.yaml`. Stage it:

```powershell
cd C:\Users\jyot2\jarvis
git add web\pnpm-lock.yaml
```

---

## Step 4 — Purge PII from git history (5–10 minutes — RECOMMENDED)

`web/data/inbox.json` (4.4 MB of operator email content) plus 13 other state files are committed to git history. The new `.gitignore` prevents future commits but does NOT remove existing history. This step rewrites history to scrub them.

**WARNING:** This rewrites every commit hash that touched `web/data/`. Anyone who has cloned the repo will need to re-clone or hard-reset to the new history.

### 4a. Install git-filter-repo

```powershell
pip install git-filter-repo
```

(Or with pipx: `pipx install git-filter-repo`.)

### 4b. Inspect what's currently tracked

```powershell
cd C:\Users\jyot2\jarvis
git ls-files web\data\
```

You should see ~14 files including `inbox.json`, `decisions.json`, `brain-dump.json`, `activity-log.json`, etc.

### 4c. Make a safety backup of the whole repo

```powershell
cd C:\Users\jyot2
Copy-Item -Recurse jarvis jarvis-backup-2026-05-13
```

(Delete this after you've verified everything still works in step 6.)

### 4d. Rewrite history to drop web/data

```powershell
cd C:\Users\jyot2\jarvis
git filter-repo --path web/data --invert-paths --force
```

This drops every commit's blob entries under `web/data/` and rewrites the commit graph.

### 4e. Recreate the directory and stage current state

After history rewrite, `web/data/` will be missing from the working tree. Restore it with the current operator data (which is no longer tracked anyway):

```powershell
mkdir web\data -Force
# Re-copy from the backup if needed:
Copy-Item C:\Users\jyot2\jarvis-backup-2026-05-13\web\data\* web\data\ -Force
```

### 4f. Force-push to all remotes

```powershell
git push --force --all
git push --force --tags
```

If you have collaborators, **tell them first** — they'll need to re-clone.

---

## Step 5 — Set MC_API_TOKEN (OPTIONAL, only if exposing dashboard beyond localhost)

The new middleware in `web/src/middleware.ts` allows reads from anywhere but blocks POST/PUT/PATCH/DELETE from non-loopback origins when `MC_API_TOKEN` is unset. If you only use Jarvis on your own machine, you can skip this. If you expose the dashboard via Tailscale, set a token:

```powershell
cd C:\Users\jyot2\jarvis
# Generate a token:
python -c "import secrets; print('MC_API_TOKEN=' + secrets.token_urlsafe(32))" >> .env
```

Then your dashboard clients (the Next.js frontend, Atlas terminal, etc.) need to send `Authorization: Bearer <that token>` on every `/api/*` call. The `apiFetch` helper in `web/src/lib/api-client.ts` already reads `MC_API_TOKEN` from `process.env`.

---

## Step 6 — Verify everything works (5 minutes)

```powershell
cd C:\Users\jyot2\jarvis

# Python side:
pytest --cov=jarvis --cov-fail-under=70
ruff check jarvis/

# Frontend side:
cd web
pnpm tsc --noEmit
pnpm build

# Smoke test the dashboard:
pnpm dev
# Then open http://localhost:3000 and check:
#   - Sidebar has new WORKSPACE section (Priority Matrix, Activity, Sentinel, Cost, Checkpoints, Preferences)
#   - /jarvis route now 404s (good — deleted)
#   - Creating a task and refreshing the page: task persists
#   - Press "/" to focus command bar, type "/standup" + enter — toast flashes
```

If everything passes, you're done. Commit:

```powershell
cd C:\Users\jyot2\jarvis
git add -A
git status   # review what's about to be committed
git commit -m "system review fix campaign — tier 0/1/2/4/5 (see docs/SYSTEM_REVIEW_2026-05-13_FIX_LOG.md)"
```

Then push.

---

## Step 7 — Delete the backup once you're satisfied

```powershell
Remove-Item -Recurse -Force C:\Users\jyot2\jarvis-backup-2026-05-13
```

---

## Quick reference — what each step fixes

| Step | Closes | Why it had to be manual |
|---|---|---|
| 1 | Stale git lock blocking branch ops | Windows file permissions on `.git/index.lock` |
| 2a | Dead UI components (orphans + stubs) | Linux mount cannot unlink Windows files |
| 2b | Two abandoned worktrees (~150 dead .py) | Same |
| 2c | Eight orphan pages with no nav links | Same |
| 2d | Junk state files (logs, screenshot, dup seed) | Same |
| 3 | Broken CI (missing pnpm-lock.yaml) | Sandbox cannot write to node_modules |
| 4 | PII in git history (operator email content) | History rewrite requires the operator's blessing |
| 5 | LAN write exposure (only if used remotely) | Operator choice |
| 6 | Confirms everything works | Runs on operator's environment |
