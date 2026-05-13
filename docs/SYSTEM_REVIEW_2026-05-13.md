# Jarvis System Review — 2026-05-13

**Verdict:** Jarvis is not one assistant. It's ~6 parallel programs sharing a folder. Three of the five subsystem agents are partly or fully broken in their live paths. The dashboard runs 15+ polling timers, a 2 MB JSONL is parsed wrong on every mission fetch, and a single unauthenticated POST wipes nine state files. Auth middleware is effectively off. PII is in git.

The three symptoms you named are the visible surface of deeper structural problems. Full punch list below, ranked.

---

## TIER 0 — Ship-blockers (assistant cannot work correctly)

### 0.1 Voice and chat have no shared brain

- **Two `JarvisChat` instances, two processes.** `jarvis/apps/api/app.py:1261` instantiates one in FastAPI. `jarvis/apps/voice/cheap_handler.py:125` instantiates another inside the voice daemon. The docstring at `cheap_handler.py:130` claims "Voice and dashboard chat share this single brain" — it is false. Different memory, different turn log, different SDK session.
- **Three turn stores, no cross-reads.** Chat HTTP writes `state/chat_turns.jsonl`. Voice Tier-3 writes `state/jarvis_turn_log.json`. Voice Tiers 0/1/2 (most utterances) write to an in-RAM `deque(maxlen=6)` in `jarvis/apps/voice/conversation_memory.py:28` that vanishes on restart.
- **`ChatTurnRecord` has no `session_id` or `surface` field** (`jarvis/state/chat_turns.py:26`). Nothing in the model knows whether a turn came from voice or chat.
- **`useChatTurns.ts:64` polls only on mount + after send.** A voice turn from another process never triggers a reload because there is no push channel.
- **`jarvis/agent.py:70`** `_TURN_LOG_PATH = Path("state/jarvis_turn_log.json")` is a **relative path**. Breaks when uvicorn or the voice daemon are launched from any other cwd, and there is no locking — two processes will clobber each other's writes (`agent.py:97-105`).

### 0.2 Sentinel runs against mocks, not real subsystems

`jarvis/apps/sentinel/scheduler.py:47-53` and lines 104-116 — `_build_subsystems()` returns `Tempo(MockOutlook())`, `AtlasOrchestrator(allow_mock=True)`, `Lens(MockSearch())`, `Scholar()`. These mocks are wired into `email_tick`, `calendar_tick`, `atlas_tick`, `news_tick`, `scholar_tick`. **Every recurring inbox event the daemon produces is fake.** The dashboard, briefings, and `voice_context_tick` all derive from this fake data.

### 0.3 Forge is dead on its main path

- `jarvis/agents/forge/agent.py:239,261` — `from . import forge_daily` raises ImportError. The module is `daily.py`, not `forge_daily.py`. Every call to `pick_project` and `scaffold_daily` crashes. The 10:00 UTC daily cron has been crashing every day.
- `jarvis/agents/registry.py:106` constructs `RealWorktreeRunner` but `Forge.execute` calls `self.runner.run(agent_name, prompt)` — wrong method (`runner.py:73` exposes `.execute()`). First live forge stage = `AttributeError`. Mock path works because `MockRunner.run` exists; that's why nobody noticed.
- Two different `WorktreeRunner` classes (one in `agent.py:64`, one in `runner.py:60`) share a name — registry imports the wrong one.

### 0.4 `/api/dispatch` ignores classification

`jarvis/apps/api/app.py:108` — every handler resolves to `desc.call_text(req)` which hard-codes a single action per agent (tempo → `today()`, atlas → `portfolio()`, scholar → `list_assignments()`, forge → `execute(repo='?')`, lens → `quick_search(text)`). The router/classifier picks the right agent, then the handler ignores the action. **`send_mail`, `schedule`, `cancel`, `trader_execute` are unreachable through `/api/dispatch`.** Only the direct `/api/agents/{name}/dispatch` endpoint can trigger them — and that path bypasses verification (`apps/api/app.py:627`).

### 0.5 Authority gate never sees real action names

`jarvis/core/orchestrator.py:79` — `check_authority(action="dispatch", …)`. The literal string `"dispatch"` is passed, never `send_mail` / `trader_execute`. `_ALWAYS_CONFIRM_ACTIONS` (`core/authority.py:11`) is therefore dead code on this path. Tier-1 keyword matching in `classify.py:25` can still catch some, but `tempo.send_mail` returns `confidence=1.0, needs_confirm=False` (`agents/tempo/agent.py:408`). **A direct call to `send_mail` will fire without confirmation**, violating the CLAUDE.md confirmation matrix.

### 0.6 PII is committed to git

`web/data/inbox.json` (4.4 MB of mail content) is tracked by git. `.gitignore` excludes `/state/` only, not `/web/data/`. `git ls-files web/data/` returns 14 operator data files. Every commit leaks mail content.

### 0.7 Auth middleware is effectively off

`web/src/middleware.ts:30` — `if (!token) return NextResponse.next();`. `MC_API_TOKEN` is not in `.env`, so every `/api/*` endpoint, including destructive ones, is open to anyone on the LAN. `dev:lan` binds `0.0.0.0:3000`. The `AuthGate` component is cosmetic when the server lets everything through.

### 0.8 One-click data wipe

`web/src/app/api/checkpoints/new/route.ts:85-93` resets nine state files to empty arrays in one call — tasks, goals, projects, brain-dump, inbox, decisions, agents, skills, activity-log. No confirmation. No auth check. Then `exec("pnpm gen:context")` (line 96) is an unauthenticated RCE pivot given §0.7. **This is the root cause of "tasks don't persist."** The mtime fingerprint on `web/data/*.json` shows a single batched reset at `13:49:02` today — classic `checkpoints/new` signature.

---

## TIER 1 — Severe (degrades daily experience)

### 1.1 Polling avalanche — 15+ concurrent timers, several under 10 s

Per-page intervals before counting the HUD: `use-active-runs` (3 s), `use-fast-task-poll` (5 s), `use-daemon` (5 s), `useSentinelSnapshot` (5 s), `ConfirmationDeck` (5 s), `RightSidebar` (8 s), `LeftSidebar` (8 s), `use-sidebar` (10 s), `BottomStatusRow` (10 s), `NewspaperView` (12 s), `use-dashboard-data` (15 s), `useForge` (15 s), `useTempo` (×3 separate 30 s timers — lines 73, 132, 165), `useAtlasMode` (60 s), `inbox/page.tsx:203` (3 s in addition to its WebSocket). Plus duplicate WS connections in `HudMissionControl.tsx:54` calling `useVoiceState` AND `useMissionBus` (which already calls `useVoiceState`).

### 1.2 `/api/missions` parses a 2.2 MB JSONL as one blob

`web/src/app/api/missions/route.ts:255-259` — `readFileSync(inbox.jsonl)` then `JSON.parse` of the whole buffer. JSONL is line-delimited; parsing it as a single document is broken AND expensive. Combine with §1.1 and this is your biggest perf hit.

### 1.3 No file caching in `web/src/lib/data.ts`

`data.ts:175-226` — every getter does `readFile + JSON.parse` per request, no mtime cache. `/api/sidebar` fans out to four getters every 10 s. Multiply by tabs.

### 1.4 No JSONL rotation anywhere

Current sizes: `state/inbox.jsonl` 2.29 MB, `state/sentinel_health.jsonl` 1.24 MB, `state/sentinel.log` 912 KB, `state/chat_turns.jsonl` 181 KB. All append-only, no rotation, no size guard (`jarvis/state/__init__.py:117`, `chat_turns.py:43`).

### 1.5 Embedding write is synchronous on the chat hot path

`jarvis/agent.py:447-470` — `_index_turn` writes an embedding inside the response loop. Plus `_save_turn_log` writes JSON to disk every record. Each user turn = 2 disk writes + 1 embedding call before the reply returns. Move to `asyncio.create_task` and the perceived latency drops.

### 1.6 Lockfile drift breaks CI

`web/pnpm-lock.yaml` and `web/package-lock.json` are both **missing**. `.github/workflows/ci.yml:42` runs `pnpm install --frozen-lockfile` — the web job has been failing on every push. All deps in `web/package.json` are `^` floating (Next `^15.3.3`, React `^19.1.0`, zod `^4.3.6`).

### 1.7 `.env` drifts from `.env.example`

Keys in `.env` not in example: `PUSHOVER_*`, `SLACK_*`, `DISCORD_*`, `TWILIO_*`, `PICOVOICE_*`, `DEEPGRAM_*`, `ELEVENLABS_*`, `APPLE_CALDAV_URL`, `DREXEL_*`, `VOICE_*`. Keys in example not in `.env`: `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `EXA_API_KEY`, `OUTLOOK_*`, `JARVIS_CHAT_URL`, `JARVIS_CORS_ORIGINS`, `NTFY_TOPIC`. **A fresh checkout cannot boot from the example.**

### 1.8 Cost telemetry is decorative

`jarvis/llm/cost.py:46-66` `log_cost` is defined but **has zero callers in the codebase**. The dashboard reads an empty `cost_log.jsonl`. Budgets are never enforced (`sentinel/routines.py:432` always passes because `record_spend` is only called inside the unreachable forge daily path).

---

## TIER 2 — Significant

### 2.1 Two parallel UIs, half of them dead

- `components/mission/*` (10 files: `MissionControl`, `ChatDialog`, `ConversationPanel`, `VoicePanel`, `VoiceWaveform`, `ConfirmationDeck`, `ActivitySwimlanes`, `AgentFleet*`, `AtlasSubFlowRail`, `DispatchGraph`) — **not imported anywhere**. `components/hud/*` is the live UI.
- `components/sidebar-nav.tsx` is unimported. `app-sidebar.tsx` is live.
- Several orphan pages have no nav links: `/jarvis`, `/crew`, `/skills`, `/exports`, `/objectives`, `/projects`, `/preferences`, `/activity`, `/checkpoints`, `/cost`, `/launch`, `/priority-matrix`, `/brain-dump`, `/team/*`, `/sentinel`.

### 2.2 Five separate chat surfaces

`ChatDialog.tsx:25` local-only turns, `ConversationPanel.tsx` uses `useChatTurns`, `CommandPanel.tsx` uses `useChatTurns`, `AgentChatPanel.tsx` runs its own SSE with no shared history, and `app/jarvis/page.tsx` (1289 lines) is a standalone implementation. No single chat surface across the app.

### 2.3 Theme toggle never mounted

`web/src/app/layout.tsx:56` hardcodes `className="dark"`. `<ThemeToggle />` exists but is referenced only in its own file. There is no UI to switch theme.

### 2.4 Keyboard shortcuts wired to no-ops

`layout-shell.tsx:123` renders `<KeyboardShortcuts />` with no props. `keyboard-shortcuts.tsx:84` calls `onCreateTask?.()` — undefined. "N" does nothing. `G P` label says "Go to Missions" but pushes `/projects` (`keyboard-shortcuts.tsx:21`).

### 2.5 Service worker caches the HTML shell forever

`web/public/sw.js:6` precaches `/`, cache-first. Even after deploy, the root is served from the SW cache until VERSION bumps. Contributes to the "doesn't save" perception when API succeeded but UI is stale.

### 2.6 Pages without error or loading boundaries

Most routes (`inbox`, `decisions`, `forge`, `lens`, `tempo`, `scholar`, `objectives`, `projects`, `crew`, `skills`, `cost`, `exports`, `preferences`, `activity`, `checkpoints`, `launch`, `priority-matrix`, `status-board`, `jarvis`, `news`, `architecture`, `sentinel`, all `atlas/agents/*`) have no `error.tsx`. A single thrown render error blows up the shell.

### 2.7 Confirmation dialog bypasses the proxy

`web/src/components/DispatchConfirmDialog.tsx:51` calls `${JARVIS_API}/api/confirmations/{id}/approve` directly to FastAPI on port 8765 instead of going through `/api/confirmations/[id]/[decision]/route.ts`. Two parallel approve endpoints; CORS/auth differ.

### 2.8 `confirmations.jsonl` is append-only with O(N²) reads

`jarvis/state/__init__.py:200-209` — every status update appends a new line. `read_confirmations` reads everything and dedupes in-memory by id every call. Grows forever, degrades over time.

### 2.9 Cron daemon fires without confirmation policy

`web/data/daemon-config.json` schedules `dailyPlan` 07:00, `standup` 09:00 weekdays, `weeklyReview` 17:00 Fridays. `web/scripts/daemon/index.ts` runs them via `node-cron`. None are gated by the confirmation matrix in CLAUDE.md.

### 2.10 Optimistic UI hides backend failures

`web/src/hooks/use-data.ts:81-105` `update()` and line 107 `remove()` apply the optimistic mutation immediately, then on a failed PUT/DELETE call `refetch()` to "revert" — but if `refetch()` reads from a just-wiped store (see §0.8), the UI permanently shows zero tasks. User concludes "didn't save."

### 2.11 Files over the 800-line CLAUDE.md cap

`app/team/scholar/page.tsx` 1339, `app/jarvis/page.tsx` 1289. Close to cap: `app/scholar/ExamMode.tsx` 701, `launch/page.tsx` 683, `status-board/page.tsx` 674, `inbox/page.tsx` 674, `scholar/page.tsx` 654, `task-form.tsx` 635.

---

## TIER 3 — Per-agent bugs

### Tempo
- `agents/tempo/agent.py:131` `_classify_batch_with_llm` calls `query_claude_sync` outside the global queue — skips rate-limit serialization.
- `agents/tempo/stack.py:87-120` `build_default_tempo_stack` requires `APPLE_ID` + `APPLE_APP_PASSWORD` + `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`. `registry.py:46-47` declares live mode if EITHER is set, then the constructor raises and falls back to mock — silently degraded.
- Outlook backend was retired (`agents/tempo/agent.py:9` docstring) but `core/verify.py:36-46` still returns evidence `"re-fetch pending MS Graph wiring"` for every tempo write. Verification status is a stale lie.
- Drexel OAuth (`tempo/providers/drexel_oauth.py`) is included in the stack though docstring says it's legacy.

### Scholar
- `agents/scholar/agent.py:798` — `InboxEvent(... payload=...)` uses wrong field name; model has `ref`. Pydantic silently drops the kwarg (no `extra="forbid"`, see contract §3.5 below). Syllabus key-date events ship with empty `ref`.
- `agents/scholar/study.py:133-161` — SM-2 deviates from canonical: Hard increments reps (canonical doesn't); Good never adjusts ease. Cards drift over weeks of use.
- `agents/scholar/agent.py:520-595` — `exam_session` fires `on_exam_scheduled` synchronously inside the response loop. Cascades to `tempo.add` → `state/tasks.json` write. Exam scheduling can block multiple seconds.
- `_query_claude` (line 42) also bypasses the queue.

### Lens
- `agents/lens/agent.py:73` references `news_provider.FEEDS` as BBC/NPR/AlJazeera/Google News; `news_provider.py:1` docstring says Reuters/AP/BBC. Stale doc.
- `agents/providers.py:296-378` — BraveSearch silently falls back to mock when `BRAVE_SEARCH_API_KEY` missing. No banner distinguishes "live but degraded" from "mock by design."

### Atlas
- `agents/atlas/agent.py:380` — `AtlasBridge()` raises `AtlasUnavailableError` from inside agent methods when ATLAS HTTP is down. `Orchestrator._run_one` re-raises (§3.2 below), so one unreachable bridge kills the whole `gather()`.
- `agents/atlas/ws_client.py:140-144` — `import websockets` inside `_connect_and_consume`. If the package is missing it silently sets `_stopped = True` and exits. **No outer caller is notified that the WS is dead.** Atlas event ticker goes silent and nobody knows why.
- `core/verify.py:48-58` — `verify_atlas` labels paper-mode `action="proposed"` as `"inference"` even when ATLAS confirmed the paper trade. Confusing semantics.

### Forge (in addition to §0.3)
- `agents/forge/runner.py:79-94` uses `Path.cwd()` as default `repo_root`. When run from uvicorn the cwd is wherever the user launched from. Worktrees scatter.

### Sentinel
- `apps/sentinel/routines.py:46` uses InboxEvent severity `"alert"`; `triggers.py:434-441` expects `"crit"|"warn"`; atlas guardian uses `"crit"`; contract docstring (`contract.py:39-40`) says `"info|warn|alert"`. Inconsistent severity vocabulary across the codebase.
- `apps/sentinel/scheduler.py:124` `mission_control_sync_tick` runs every 30 s with no rate limiting against downstream.

---

## TIER 4 — Architectural / cross-cutting

### 3.1 Multiple sources of truth for the same data

- Tasks: `state/tasks.json` (Python, stale, last write Apr 29) AND `web/data/tasks.json` (Next.js, live). `voice/context_cache.py:107` and `sentinel/mission_control_bridge.py:52` already document the divergence.
- Inbox: `state/inbox.jsonl` (Python, line-per-event, 2.29 MB) AND `web/data/inbox.json` (Next.js, `{messages: [...]}` object, 4.4 MB). Two schemas, no sync.
- Chat turns: three stores (§0.1).
- Memory: `state/memory/daily/` is one file per day, append-only forever; `memory.py:101-145` never decays, dedups, or compacts.

### 3.2 `Orchestrator._run_one` re-raises on failure with `gather(return_exceptions=False)`

`core/orchestrator.py:177-182` — one bad agent kills the whole fan-out. Morning briefings die when any single subsystem errors.

### 3.3 `Orchestrator.dispatch` never writes `agent_log.jsonl`

`core/orchestrator.py:69-95` — records in-memory session only. `state/agent_log.jsonl` only fills from the direct `/api/agents/{name}/dispatch` path. "Verification health" widget is permanently sparse.

### 3.4 Classifier is rules-only

`core/classify.py:147-149` — LLM fallback was removed per the docstring at lines 12-15. Fixed confidences (0.9/0.7/0.3). Multi-rule path packs duplicates into `parallel` but `_MULTI`'s briefing list silently drops some intents (e.g. a "morning briefing about my code PR" routes to tempo+scholar+atlas, drops forge).

### 3.5 `AgentResponse` has no `extra="forbid"`

`contract.py:15-31` — pydantic v2 default is `ignore`, so silent field-drop bugs (like Scholar's `payload=` typo at `agents/scholar/agent.py:798`) never raise.

### 3.6 Confirmation re-run replays the wrong action

`apps/api/app.py:725` — `dispatch_result = await o.dispatch(conf.request, confirmed=True)` re-runs the classifier on the original request text. Combined with §0.4, approving a confirmation runs `tempo.today()` instead of the action the operator approved.

---

## TIER 5 — Cleanup

### 5.1 Two abandoned worktrees

`.claude/worktrees/hardcore-noyce-3c8ea5/` and `.claude/worktrees/intelligent-leakey-995f20/` — both on the pre-reorg flat layout (`jarvis/jarvis_agent.py`, `jarvis/claude_queue.py`, `jarvis/daemon/`, `jarvis/voice/`). Tests reference deleted modules. ~150 .py files of dead code.

### 5.2 References to deprecated agents

- `.claude/agents/sentinel.md:15-18` references Aide/Chronos/Sherlock/Ledger by name as live jobs. **Direct violation of CLAUDE.md's "Don't reintroduce deleted agents" rule.**
- `.claude/CLAUDE.md:130` references `jarvis-outlook-integrator` but no such file exists in `.claude/agents/`.
- `web/data/activity-log.json` and `inbox.json` contain 46 + 42 references to `chronos`/`ledger` (seeded demo fixtures). The dashboard renders deprecated agent names.

### 5.3 Orphan files in `state/`

`MORNING_BRIEF.md` (8 May, never re-read), `daily_forge_test.log`, `daily_forge_test2.log` (4 May, one-offs), `jarvis_api.log`, `uvicorn.log`, `next.log`, `screenshot.png` (238 KB), `forge_runs/` (empty since Apr 29), duplicate scholar seeds (`linalg.json` == `linalg_exam.json`).

### 5.4 Coverage claim is stale

CLAUDE.md says "78 tests, 81% coverage." Reality: 88 test files, 882 `def test_` functions. CI threshold (`.github/workflows/ci.yml:19`) is `--cov-fail-under=70`, not 80. Number in CLAUDE.md is wrong and below the documented standard.

### 5.5 Missing `force-dynamic`

`web/src/app/api/inbox/route.ts`, `tasks/route.ts`, `sentinel/snapshot/route.ts` — Next.js may serve stale cached state.

### 5.6 `command-bar.tsx:70-80` slash command is a stub

Shows a 5-second `slashNotification` toast and clears the input. Doesn't dispatch.

### 5.7 Forms inconsistently validate

`task-form.tsx:19` and API routes import `@/lib/validations`. `create-goal-dialog.tsx`, `create-project-dialog.tsx`, `edit-goal-dialog.tsx`, `edit-project-dialog.tsx` only check for empty title and rely on a 400 from the API.

### 5.8 Banner pile-up on `/atlas/*`

`AtlasDegradedBanner` (mounted in `layout-shell.tsx:72`) and `MockModeBanner` (in atlas pages) can both render at once — two stacked amber banners. `AtlasDegradedBanner` line 74 also hardcodes `C:\Users\jyot2\atlas\` as user-facing text.

---

## Recommended fix order

**Stop the bleeding first (a few hours of work, big impact):**

1. Add a body-required `confirm: true` guard to `POST /api/checkpoints/new` — §0.8. This alone restores the "tasks persist" experience.
2. Fix the auth middleware — set `MC_API_TOKEN` and ensure the early-return at `middleware.ts:30` requires it — §0.7.
3. Add `web/data/` to `.gitignore`, force-purge those files from history, regenerate `.env.example` from current `.env` keys — §0.6, §1.7.
4. Restore `web/pnpm-lock.yaml` so CI runs again — §1.6.
5. Rename `daily.py` → `forge_daily.py` or fix the import; fix `WorktreeRunner` registry wiring — §0.3.

**Then unify the brain (the core of "doesn't feel like JARVIS"):**

6. Make `JarvisChat` a single process with HTTP and the voice loop both calling it (or have voice write to the same `chat_turns.jsonl` that chat reads from). Add `session_id` and `surface` fields to `ChatTurnRecord`. Push new turns via SSE so both UIs see voice in real time — §0.1.
7. Replace mocks in `_build_subsystems()` with the live registry. Atlas should fall back to a banner, not crash the gather — §0.2, §3.2.
8. Fix `/api/dispatch` to actually call the classified action, not `call_text`. Pass real action names into `check_authority` — §0.4, §0.5.

**Then performance (one afternoon):**

9. Stream `state/inbox.jsonl` line-by-line in `/api/missions`, or migrate that endpoint to the canonical `web/data/inbox.json` — §1.2.
10. Mtime-cache the `data.ts` getters — §1.3.
11. Bump all sub-10 s polls to ≥15 s; consolidate `useTempo`'s three intervals — §1.1.
12. Add JSONL rotation (size or age based) — §1.4.
13. Make `_index_turn` and `_save_turn_log` fire-and-forget — §1.5.

**Then cleanup:**

14. Delete `components/mission/*`, `components/sidebar-nav.tsx`, both worktrees, `.claude/agents/sentinel.md`'s stale section, the `chronos`/`ledger` seed data — §2.1, §5.1, §5.2.
15. Either decide the orphan pages are nav-worthy or delete them.
16. Pick one chat surface and remove the other four — §2.2.
17. Add `extra="forbid"` to `AgentResponse` so the next typo fails loud — §3.5.

---

**Total visible issues catalogued: 56 across 5 tiers.** This is recoverable — most of the bugs are localized fixes, not architectural rewrites. The single highest-leverage move is unifying the chat brain (§0.1), because that's what makes Jarvis feel like JARVIS instead of a folder of scripts.
