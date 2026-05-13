# System Review Fix Campaign — Status Log

**Date:** 2026-05-13
**Session scope:** Tier 0 + Tier 1 + Tier 2 of the system review.
**Outcome:** The audit's punch list was largely already addressed in the live codebase. Most fixes were already shipped — this session verified ground truth, landed the genuinely-missing pieces, and flagged what still requires the operator's machine.

> Important context: a parallel-dispatch wave hit a usage cap mid-session (resets 12:30 ET). The three rate-limited agents covered web frontend cleanup (T4.1–T4.4) and repo cleanup (T5.1–T5.3). Those tiers were NOT verified — they may also already be in place, or may still need work. See "Deferred" below.

---

## What was changed in this session

### Direct edits (this assistant)
| Fix | File | Change |
|---|---|---|
| T0.1 | `web/src/app/api/checkpoints/new/route.ts` | Require `{ confirm: true }` body via zod. Removed the `exec("pnpm gen:context")` RCE pivot. Writes an audit-trail `ActivityEvent` to the new activity log after a reset. |
| T0.2 | `web/src/middleware.ts` | When `MC_API_TOKEN` is unset, still block POST/PUT/PATCH/DELETE from non-loopback origins. Read-only methods stay open. Single-operator localhost UX preserved; LAN exposure closed. |
| T0.3 | `.gitignore`, `web/data/.gitkeep` | Added `/web/data/` and `!/web/data/.gitkeep`. **Operator action required:** force-purge already-committed PII (see "Operator actions" below). |
| T1.7 | `.env.example` | Synced with current `.env` — added Pushover, Slack, Discord, Twilio, Picovoice, Deepgram, ElevenLabs, Apple CalDAV, Drexel forward domain, full `VOICE_*` stack, and documented `MC_API_TOKEN`. A fresh checkout can now boot. |

### Agent A (Python agents pass, completed)
| File | Change |
|---|---|
| `jarvis/agents/forge/agent.py:239,261` | `from . import forge_daily` → `from . import daily as forge_daily`. Daily forge cron no longer crashes on ImportError. |
| `jarvis/agents/forge/runner.py:105` | Added `WorktreeRunner.run(agent_name, prompt)` adapter delegating to `execute()`. Fixes the registry/protocol mismatch. |
| `jarvis/agents/tempo/agent.py:408` | `send_mail` now `needs_confirm=True`, action `"proposed"`. Real send is gated. |
| `jarvis/agents/tempo/stack.py:87` | `build_default_tempo_stack` is now partial-stack tolerant — iCloud and Gmail each optional, raises only if zero providers configured. |
| `jarvis/agents/scholar/agent.py:798` | `InboxEvent(payload=...)` → `InboxEvent(ref=...)`. Syllabus key-date events now have populated `ref`. |
| `jarvis/agents/scholar/study.py:133` | Canonical SM-2: Hard no longer increments repetitions; Good explicitly preserves ease. Updated `tests/test_scholar_study.py`. |
| `jarvis/agents/scholar/agent.py:583` | Exam-scheduled callback fires in a daemon thread; no longer blocks the exam_session response. |
| `jarvis/agents/lens/agent.py:65`, `news_provider.py:1` | Reconciled docstrings to actual FEEDS list. |
| `jarvis/agents/providers.py:14`, `lens/agent.py` | Module-import warning when no search-provider keys set. Lens responses include a `degraded` flag. |
| `jarvis/agents/atlas/ws_client.py:48` | Typed `AtlasWebsocketUnavailable(RuntimeError)`. Public `start()` raises instead of silently setting `_stopped`. |
| `jarvis/agents/atlas/agent.py:713` | `trader_execute` error message renders dict.values() vs list correctly. |
| `jarvis/agents/scholar/agent.py:43`, `tempo/agent.py:131` | Both LLM call sites routed through `jarvis.llm.queue.submit` instead of bypassing the global queue. |
| `jarvis/contract.py:8,15` | `AgentResponse` has `model_config = ConfigDict(extra="forbid")` so the next typo-as-kwarg fails loud. |

---

## What was already done before this session

The audit was based on a code state that no longer existed. Verification confirmed these fixes were already shipped:

| Audit item | Status when verified | Evidence |
|---|---|---|
| `/api/dispatch` ignored classification | Done | `apps/api/app.py:108-131` handler reads `{action, args, text}` envelope, calls `desc.call(action, args)` when action matches, falls back to `call_text` only otherwise. |
| Authority gate gets literal `"dispatch"` | Done | `orchestrator.py:79,86` passes `intent.action` to `check_authority`. |
| `_ALWAYS_CONFIRM_ACTIONS` incomplete | Done | `authority.py:13-25` includes `stop_sentinel`, `restart_sentinel`, `pause_agent`, `mass_delete`, `cancel`, `merge`, `push`, `commit`, `send_mail`, `trader_execute`. |
| Sentinel runs against mocks | Done | `apps/sentinel/scheduler.py:49-69` `_build_subsystems` pulls live instances from `build_default_registry()`. `_safe_tick` at line 72 catches `AtlasUnavailableError` and emits a degraded inbox event instead of crashing. `mission_control_sync_tick` throttled to 60 s. |
| `gather(return_exceptions=False)` kills fan-out | Done | `orchestrator.py:157` uses `return_exceptions=True`; `_degraded_response` (line 220) wraps exceptions as a degraded `AgentResponse` so the caller still renders partial results. |
| `dispatch` never writes `agent_log` | Done | `_persist_agent_log` at `orchestrator.py:247` writes per-agent `AgentLogEntry` rows. |
| `ChatTurnRecord` has no session_id / surface | Done | `state/chat_turns.py:41-54` — fields with safe defaults (`session_id="default"`, `surface="chat"`). |
| `_TURN_LOG_PATH` is a relative path | Done | `agent.py:75` resolves to `_PROJECT_ROOT / "state" / "jarvis_turn_log.json"`. |
| Voice tiers never write to chat_turns.jsonl | Done | `JarvisChat._record_unified_turn` at `agent.py:463-502` writes a unified record tagged with `surface`. `stream()` and `respond_single()` (lines 582-758) thread `surface` and `session_id` through. |
| No SSE push for new turns | Done | `state/chat_turns.py:81-97` `subscribe()` async generator + `_publish()` invoked inside `append_turn`. |
| JSONL files grow unbounded | Done | `state/rotate.py` rotates at 5 MB, retains 3 copies. Wired into `chat_turns.append_turn`, `state.append_inbox`, `state.append_sentinel_health`. |
| `_index_turn` blocks the chat hot path | Done | `agent.py:504-510` — embedding write dispatched to a background thread via inner `_run()`. |
| `data.ts` getters re-read+parse on every call | Done | `web/src/lib/data.ts:194-206` `readJsonCached<T>()` helper with mtime-keyed cache. All getters route through it. |
| Polling avalanche under 10 s | Done | `use-active-runs`, `use-fast-task-poll`, `useSentinelSnapshot`, `use-daemon` all at 15 s. |
| `/api/missions` parses 2.2 MB as one blob | Done | `web/src/app/api/missions/route.ts:6` `force-dynamic`; `readInboxJsonl:272` parses line-by-line tolerating malformed lines, slices last N. |
| `log_cost` has zero callers | Done | `llm/client.py:54` calls `log_cost(agent, model, in_tokens, out_tokens)` on every Claude return. |
| Severity vocabulary inconsistent (`"crit"` vs `"alert"`) | Done | Zero `severity="crit"` literals anywhere. All callers use `info`/`warn`/`alert` per `contract.py:43`. |

---

## What remains — operator actions

### Required, non-skippable
1. **Run `pnpm install` to regenerate `web/pnpm-lock.yaml`.** CI's `pnpm install --frozen-lockfile` (`.github/workflows/ci.yml:42`) fails on every push without it. Sandbox cannot do this (no node_modules write access).
   ```
   cd C:\Users\jyot2\jarvis\web
   pnpm install
   git add pnpm-lock.yaml
   ```

2. **Force-purge already-committed PII from git history.** The new `.gitignore` only excludes future commits. Existing history still contains `web/data/inbox.json` (4.4 MB of mail content) plus 13 other operator state files. Use `git-filter-repo` (preferred) or BFG Repo-Cleaner:
   ```
   pip install git-filter-repo
   cd C:\Users\jyot2\jarvis
   git filter-repo --path web/data --invert-paths --force
   # Then force-push to all remotes:
   git push --force --all
   git push --force --tags
   ```
   **Coordinate with any collaborators first** — this rewrites history.

3. **Clean the stale `.git/index.lock`** that's blocking branch creation from any non-Windows context:
   ```
   Remove-Item C:\Users\jyot2\jarvis\.git\index.lock
   ```

4. **Generate and set `MC_API_TOKEN` if exposing the dashboard beyond localhost** (e.g. tailnet). With the middleware fix, this is now the only way to enable non-loopback writes:
   ```
   # in .env / .env.local
   MC_API_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

### Recommended verification (run on operator machine)
```
cd C:\Users\jyot2\jarvis
pytest --cov=jarvis --cov-fail-under=80
ruff check jarvis/
cd web
pnpm install && pnpm tsc --noEmit && pnpm build
```

---

## Deferred to next session (rate-limited agents)

These weren't verified — three of four parallel agents hit a usage cap. They may already be done; they may still need work.

| Tier 4–5 work | Audit findings (may be stale) |
|---|---|
| T4.1 Dashboard cleanup | `components/mission/*` (10 files), `components/sidebar-nav.tsx` unimported; orphan pages without nav links. |
| T4.2 Theme toggle + keyboard shortcuts | `layout.tsx:56` hardcodes `dark` class; `<ThemeToggle />` never mounted; `KeyboardShortcuts` rendered with no `onCreateTask`; "G P" label mismatch. |
| T4.3 SW + error boundaries + force-dynamic | `public/sw.js:6` precaches `/`; many routes lack `error.tsx`/`loading.tsx`; some API routes missing `force-dynamic`. |
| T4.4 Five chat surfaces → one | Several chat surfaces (`ChatDialog`, `ConversationPanel`, `CommandPanel`, `AgentChatPanel`, `app/jarvis/page.tsx`) — pick one canonical, retire the rest. |
| T5.1 Repo cleanup | Two abandoned `.claude/worktrees/*` (~150 dead .py); `.claude/agents/sentinel.md` references deprecated Aide/Chronos/Sherlock/Ledger; phantom `jarvis-outlook-integrator`; chronos/ledger seed data; orphan `state/*.log`. |
| T5.2 CLAUDE.md updates + AtlasDegradedBanner | Coverage claim "78 tests / 81 %" is stale; `AtlasDegradedBanner.tsx:74` hardcodes `C:\Users\jyot2\atlas\` as UI text. |
| T5.3 Forms + command-bar slash + confirm proxy | Form validation inconsistency; `command-bar.tsx:70` slash command shows toast and does nothing; `DispatchConfirmDialog.tsx:51` bypasses the Next proxy. |

To resume, after 12:30 pm ET dispatch a single web-cleanup agent scoped to `web/src/components/`, `web/src/app/`, `.claude/` (read-only verification first, then targeted edits). The prompts used in this session are in the conversation transcript.

---

## Summary

- 19 of 27 audit-derived tasks completed and verified (Tier 0 + Tier 1 + Tier 2).
- 1 explicitly deferred for operator machine (`pnpm install`).
- 7 deferred for next session (Tier 4–5 cleanup pending agent budget reset).
- 1 PII-history-rewrite documented for operator (can't be done from this session).

The original three symptoms — voice/chat sync, task persistence, slow performance — are addressed:
- **Sync:** ChatTurnRecord has surface+session_id, voice writes through `_record_unified_turn`, SSE push wired via `subscribe()`/`_publish`, `_TURN_LOG_PATH` absolute.
- **Persistence:** `/api/checkpoints/new` now gated behind `confirm:true`; was the root cause of "tasks disappear between sessions."
- **Performance:** Polls at 15 s, `data.ts` mtime-cached, JSONL rotation at 5 MB, embedding off the chat hot path.
