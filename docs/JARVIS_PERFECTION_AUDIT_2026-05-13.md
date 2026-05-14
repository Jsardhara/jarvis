# Jarvis Perfection — J1 Audit Synthesis

**Date:** 2026-05-13
**Scope:** Concrete gap list across persona, memory, proactivity, and routing — the four dimensions that separate "an LLM chat with my data" from "Iron Man's JARVIS."
**Method:** Four parallel agents read every file involved in each dimension and produced file:line citations of every concrete gap.

This doc is the foundation for the J2–J5 implementation passes. Read once; then we ship.

---

## TL;DR — 10 highest-leverage gaps

Numbered by overall priority (not dimension):

1. **Recap only fires on lane switch** (`agent.py:639`). First turn of every session = no memory of prior conversations. Single biggest "Jarvis is a stranger" cause.
2. **`_turn_log` loads from the wrong file** (`agent.py:283`). Reads `jarvis_turn_log.json` (12-entry rolling cap), not the unified `chat_turns.jsonl` we built. Voice turns invisible to chat and vice versa.
3. **Voice tier 1/2 has zero persistent memory** (`cheap_handler.py:121`). In-process deque dies on restart. Most voice utterances (which go to tier 1/2) cannot reference anything from a prior session.
4. **Evening digest is the morning digest** (`scheduler.py:199`). Reuses `morning_digest` verbatim at 18:00 UTC. No "what closed today / open loops / tomorrow's first event."
5. **No anticipation/dry-wit/pushback instruction anywhere** (`apps/voice/persona.py:14`). Jarvis is told to be terse and observant but never told to ANTICIPATE Tony's next move or push back on stupid premises. This is THE Iron Man JARVIS signature.
6. **No "meeting in N minutes" countdown.** Calendar tick (`routines.py:54`) fetches today's events once an hour with severity=info, never pushes. The single most-expected proactive feature is missing.
7. **`[result]. [next step]` pattern from CLAUDE.md never enforced in any prompt.** Documented policy without a teeth.
8. **Routing primary-agent selection ignores intent.** "Check inbox and BTC position" routes atlas first because atlas rule appears before tempo in `router.py`. Should pick the *earliest-mentioned* domain as primary.
9. **`atlas_health_tick` writes alert but never calls notifier.push** (`scheduler.py:138`). One-line bug. Atlas going down doesn't notify the operator.
10. **TTS voice mismatch:** `.env.example` defaults to `en-US-AriaNeural` (generic Alexa-tier voice), `config.py` defaults to `en-US-AndrewMultilingualNeural`. Whichever wins isn't characterful. JARVIS without a butler voice is hard to feel.

---

## Persona (J1.1) — 13 prompt sites, drift across 4 of them

**Canonical persona:** `jarvis/apps/voice/persona.py:14-45` — terse, observant, dry, but soft.

**Drift sites (re-using PERSONA constant fails):**
- `agents/lens/link_handler.py:467` — own self-introduction, 4–6 sentence ceiling vs PERSONA's 1–2.
- `.claude/agents/jarvis.md:10` — "You are Jarvis. Terse, direct." 5 words. Dev-side Claude Code sees a different brain.
- `state/briefing.py:282` — deterministic markdown; not LLM-rendered through PERSONA.

**Critical missing in PERSONA:**
- No "anticipate the next request" line.
- No "make dry observations when warranted" license.
- No "push back when the operator's premise is wrong" line.
- No `[result]. [next step]` shape modeling (CLAUDE.md says it, prompt doesn't).
- Negative list ("don't say 'sure', 'happy to', 'I'd be happy to'") is short — missing common LLM tics like "Great question", "Let me know if you need anything else", apology spam.
- No form-of-address convention. Should Jarvis say "sir" / "Jyot" / nothing? Currently undefined.

**Inconsistencies:**
- Three different word caps for voice — speech.py:90 says ~25 words, proactive.py:35 says ~20, loop.py:31 says ~20. Pick one.
- Voice tier 1/2 (Haiku/Sonnet) gets PERSONA only. Tier 3 (Opus/chat) gets PERSONA + 40-line addendum + full soul.md. Sonnet voice and Opus chat sound like different assistants.
- Voice fillers (`fillers.py:22-29`) are Alexa-generic: "One moment.", "Let me check.", "Looking into it." Replace with characterful set.

**Voice config bugs:**
- `.env.example:94 VOICE_NAME=en-US-AriaNeural` vs `config.py:34` default `en-US-AndrewMultilingualNeural`. They disagree.
- Filler MP3s baked at +15% rate (`fillers.py:46`) while voice runs at `VOICE_RATE=+0%` — fillers sound clipped vs replies.

---

## Memory (J1.2) — Jarvis is a stranger every session

**Write paths today:**
- Chat: `_record_turn` → `state/jarvis_turn_log.json` (12 entries max) + background `_index_turn` → `state/jarvis_chat_index.jsonl` (semantic, unbounded).
- Voice: `cheap_handler._persist_voice_turn` → `state/chat_turns.jsonl` (unified, rotated).
- Both: `_record_unified_turn` → `chat_turns.jsonl`.
- Sentinel: `routines.py:384` writes to `state/memory/daily/`.

**Read paths today on each chat turn:**
- `_recap()` — only fires on lane switch. Reads in-memory `_turn_log` + top-3 semantic hits.
- `_build_live_state_block` — pnl/mail/tasks fact sheet.
- **Nothing else.** No `read_daily`, no `read_longterm`, no `chat_turns.read_recent`.

**The "Jarvis forgot me" gaps:**
1. `agent.py:639` recap-only-on-switch — first turn of every session gets no recap.
2. `agent.py:283` loads `jarvis_turn_log.json` (12 max). Cross-surface unified store `chat_turns.jsonl` never hydrated.
3. `cheap_handler.py:121` voice tier 1/2 — process-local deque only.
4. `memory.py:104` daily/longterm files exist but only sentinel writes; nothing reads them into chat context.
5. `briefing.py` morning brief pulls zero memory — can't say "yesterday you asked about X".
6. No declarative-fact extractor. "I prefer dark roast" / "call me J" / "remember that Y" become raw turn text. No structured preference graph.
7. `jarvis_chat_index.jsonl` grows forever, no compaction, no summarization, no rotation. Linear-time recall.

**What "memory works" looks like (Phase J2 target):**
- `_recap()` runs every turn, not just on switch.
- `_turn_log` hydrates from `chat_turns.jsonl` on init (last 50 turns).
- `KeyValueFact` store extracts "I prefer X" / "remember Y" / "call me Z" automatically.
- `read_longterm(limit=50)` injected into system prompt.
- Voice tier 1/2 reads `chat_turns.read_recent` so it sees prior conversation across restarts.
- Nightly sentinel job summarizes >30-day turns into longterm bullets, drops them from the index.

---

## Proactivity (J1.3) — events fire, operator never hears

**18 triggers exist today. 6 of them are silent (inbox-only, no push):**
- Calendar today count
- Atlas open-pos cap
- News watchlist hits
- Atlas health 503 transition (write="alert" but no `notifier.push` call — one-line bug)
- Sentinel heartbeat
- R3 task-due-today (info severity dropped at push gate)

**Critical missing triggers:**
- **No meeting-imminent countdown.** Should be a 2-minute tick reading `voice_context.next_event` and pushing at 5/10/15-min boundaries.
- **No assignment-due reminder.** Scholar walks `count >= 5` but never scans `due` dates.
- **No watchlist price/news delta.** Lens monitors but `news_tick` only logs count.
- **No stale-task alert.** Tasks open >7 days never surface.
- **No operator-presence tracking.** No `state/operator_presence.jsonl`. Without "last_seen" we can't do pattern-based proactivity ("you usually check mail by 9, it's 10:30").

**Routing bugs:**
- Voice proactive filter excludes `crit` events (proactive.py:153). Forge dead-letter / guardian violation never voiced.
- Push priority inversion: emails at p=1, forge failures at p=2 — inconsistent severity-to-priority mapping.
- Evening digest is morning digest verbatim (scheduler.py:199).
- Cron is UTC; 8am UTC = 3–4am ET. "Morning briefing" misnamed unless operator is in UTC.

**Interrupt vs queue:**
- No quiet hours. Pushover fires 24/7.
- No "in a meeting" detection (calendar gives the data, never consumed).
- No severity-based time-of-day gating.

---

## Routing (J1.4) — silent misrouting on common phrasings

**Audit test cases and actual classifications:**

| Request | Should route | Actually routes | Verdict |
|---|---|---|---|
| "what's my schedule today?" | tempo | tempo | OK |
| "check inbox and tell me about my BTC position" | tempo + atlas | atlas (primary), tempo (parallel) | **WRONG** — primary should follow intent order |
| "summarize news on Nvidia and add to watchlist" | lens + atlas | lens only | **WRONG** — no watchlist rule |
| "draft email to professor about exam" | tempo + scholar | tempo + scholar | OK |
| "morning briefing about my PR and markets" | tempo + scholar + atlas + forge | all four | OK (compound) |
| "is anything overdue?" | tempo + scholar | jarvis 0.3 fallback | **WRONG** — no rule for "overdue" |
| "TODO in our codebase" | forge | tempo | **WRONG** — "todo" routes tempo before forge |

**Confidence emitted but never consulted:**
- Classifier returns 0.3/0.7/0.85/0.9 (`router.py:194-231`).
- `Orchestrator.dispatch` and `_build_orchestrator` neither check the value.
- No clarification flow. Low-confidence requests silently self-handle.

**Follow-up turn context:**
- Each `dispatch()` classifies in isolation.
- "Actually, also include scholar" cannot retroactively widen the previous turn's fan-out.
- `JarvisChat._recap()` reinjects context only on lane switches.

**Action-level routing gaps:**
- "Pause the trader" → action="dispatch" (no rule match), bypasses authority gate. The agent code has `pause_agent` but classifier never emits that action.
- Forge merge/push/commit all collapse to action="execute". Authority gate per-action confirmations for those are dead code.
- Scholar `add_assignment` action never reached — "add CS401 homework due Friday" matches `list_assignments` instead.

**Fan-out:**
- `asyncio.gather` blocks until all handlers finish. Slowest agent caps morning-briefing latency.

---

## Files most needing change (sorted by # of cross-dimension hits)

| File | Persona | Memory | Proactivity | Routing | Net hits |
|---|---|---|---|---|---|
| `jarvis/agent.py` | 1 | 6 | 0 | 1 | **8** |
| `jarvis/apps/voice/persona.py` | 4 | 0 | 0 | 0 | 4 |
| `jarvis/state/briefing.py` | 1 | 1 | 2 | 0 | 4 |
| `jarvis/apps/sentinel/scheduler.py` | 0 | 0 | 3 | 0 | 3 |
| `jarvis/apps/sentinel/routines.py` | 0 | 0 | 3 | 0 | 3 |
| `jarvis/core/router.py` | 0 | 0 | 0 | 6 | 6 |
| `jarvis/state/memory.py` | 0 | 3 | 0 | 0 | 3 |
| `jarvis/state/memory_index.py` | 0 | 3 | 0 | 0 | 3 |
| `jarvis/apps/voice/cheap_handler.py` | 1 | 2 | 0 | 0 | 3 |
| `jarvis/core/triggers.py` | 0 | 0 | 3 | 0 | 3 |

**`jarvis/agent.py` is the single highest-leverage file** for the perfection campaign.

---

## Sequence proposal

### J2 — Memory (most impact, foundation for J3+)
1. Hydrate `_turn_log` from `chat_turns.jsonl` on `JarvisChat.__init__` (last 50 turns, dedup by turn_id).
2. Run `_recap()` every turn, not just on lane switch. Move the lane-switch gate inside `_recap` to control verbosity, not whether it runs.
3. Add `jarvis/state/facts.py` with `KeyValueFact` schema + a pattern matcher invoked from `_record_turn` that catches "I prefer X" / "remember Y" / "call me Z".
4. Inject `read_longterm(limit=50)` + extracted facts into `_build_live_state_block`.
5. Wire `cheap_handler._ask_claude` (voice tier 1/2) to read `chat_turns.read_recent(user_id, limit=20)` and top-3 semantic hits.
6. Add nightly sentinel job: summarize >30d turns into longterm bullets, drop from index.
7. Tests: cross-session recall, preference extraction, semantic recall quality.

### J3 — Proactivity (after memory; uses preference graph for "interrupt vs queue")
1. Build `meeting_imminent_tick` (calendar countdown).
2. Build `scan_assignments_due_soon` (mirror of exam scanner).
3. Build `stale_task_tick` (open >7d).
4. Build `watchlist_delta_tick` (price/news delta with `state/lens_snapshot.json` baseline).
5. Add `state/operator_presence.jsonl` (last_seen on every turn). Build "you haven't checked inbox in N hours" rule.
6. Real `evening_digest` (separate from morning) — closed-today / open-loops / tomorrow's first event.
7. Fix one-line atlas_health_tick push bug.
8. Add quiet hours config + severity-gated push.
9. Move sentinel cron to operator-local timezone.

### J4 — Persona (polish on top of substance)
1. Rewrite `persona.py` with anticipation/dry-wit/pushback paragraph + `[result]. [next step]` shape + expanded negative list + form-of-address policy.
2. Pin TTS to single characterful voice across `.env.example` + `config.py` + `fillers.py`.
3. Replace 6 generic fillers with characterful set.
4. Make `link_handler.py` + `.claude/agents/jarvis.md` import `PERSONA`.
5. Unify the three word-count caps to a single source.
6. Render `briefing.py` through PERSONA for the spoken channel.

### J5 — Routing (the bones already work; targeted patches)
1. Add `watchlist`, `overdue`, `add assignment` rules to `router.py`.
2. Fix "todo in codebase" → forge by requiring codebase context for forge `todo` matches and de-prioritizing tempo's `todo` rule when code context present.
3. Make primary agent = earliest-mentioned domain (use `re.match.start()`).
4. Consult `intent.confidence` in `Orchestrator.dispatch`; ask clarification on `<0.5`.
5. Pass `prior_intent` into `classify()` for follow-up turn context.
6. Add `pause_agent` rule + extend authority gate to check response.action.
7. Split forge `execute` into `merge` / `push` / `commit` action emits.

Each phase is one focused session. Memory (J2) is the prerequisite for everything else feeling like JARVIS instead of a search engine you query.
