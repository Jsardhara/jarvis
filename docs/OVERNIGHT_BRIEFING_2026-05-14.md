# Overnight Briefing — 2026-05-14 morning

You said "perfect Jarvis, don't stop, decide on your own." Here's what landed while you slept.

---

## TL;DR

Four implementation passes done — **memory, proactivity, persona, routing**. All synthesis from the J1 audit. 24 files touched (12 modified, 12 created — 6 source modules, 6 test files). Static syntax check: every file parses cleanly. **Tests were not run** — the sandbox is Python 3.10 and the codebase requires 3.11+ (`datetime.UTC` import). You'll need to run pytest on your machine.

Three follow-up items deferred with reasons explained at the bottom. None are blockers.

---

## J2 — Memory (Jarvis remembers across sessions now)

**Behavior change you should feel:**
- Cold-start chat session pulls the last 50 turns from the unified `chat_turns.jsonl` store. Voice turns visible to chat. Chat turns visible to voice tier 1/2. No more "Jarvis the stranger" every restart.
- Every chat turn now runs the recap. Previously only fired on lane switches, so the first turn of every session got zero memory. Same-lane recap is briefer (top-1 semantic hit + last 2 pairs). Lane-switch recap is fuller (top-3 + last 3 pairs).
- Declarative facts get extracted automatically. Say "I prefer dark roast", "call me J", "remember that my flight is at 6am", or "my advisor is Dr. Patel" — pattern matched and persisted to `state/facts.jsonl`. Last fact per key wins (so updates work). Top 30 facts injected into the system prompt on every turn.
- Voice tier 1 (Haiku) and tier 2 (Sonnet) now pull from `chat_turns.read_recent(limit=20)` plus top-3 semantic hits. Voice no longer has amnesia across restarts.

**Files changed:**
- `jarvis/agent.py` — recap-every-turn, `_TURN_LOG_MAX` 12→100, `_hydrate_from_unified_store()` in `__init__`, facts injection into `_build_live_state_block`, `_record_turn` extracts facts on user turns + marks operator-presence.
- `jarvis/apps/voice/cheap_handler.py` — voice tier 1/2 reads cross-surface chat turns + semantic hits, marks operator-presence.
- `jarvis/state/briefing.py` — added `_build_memory_section(today)` rendering yesterday's daily + last 10 turns. Called from `evening_digest`.

**New files:**
- `jarvis/state/facts.py` — `KeyValueFact` dataclass + regex extractor + JSONL store + prompt renderer.
- `tests/test_memory_facts.py` — 9 tests on extraction, dedup-latest-per-key, render formatting, round-trip.
- `tests/test_memory_recall.py` — 3 tests: recap-on-first-turn-same-lane, hydration-from-chat-turns, voice-tier1-reads-chat-turns.

**Known caveat:** `jarvis/agent.py` is now 999 lines — over the 800-line CLAUDE.md cap. Flagged for follow-up extraction (memory helpers into `jarvis/state/recap.py`). Not blocking.

---

## J3 — Proactivity (Jarvis surfaces things before you ask)

**Behavior change you should feel:**
- Meeting countdown: every 2 minutes, sentinel checks `voice_context.next_event`. If the next event starts in ~5/10/15 minutes, you get a push at p=1 with the event title. Per-bucket dedup so you don't get spammed.
- Assignment-due-soon: scholar assignments due within 24h fire a warn-priority push. Dedup per assignment_id.
- Stale tasks: any open task with `created < now - 7d` fires a warn-priority push once per (task_id, ISO week).
- Operator-presence tracking: every chat or voice turn marks you "present." If you go silent for >6h, sentinel emits a warn so Jarvis knows to flag things differently when you're away.
- Real evening digest at 18:00 UTC: previously this slot just re-ran `morning_digest`. Now you get `evening_digest` — closes today, open loops, today's cost rollup, tomorrow's first event, atlas P&L close, plus the new memory section.
- Atlas health push bug fixed (one line): `atlas_health_tick` was writing `severity="alert"` to inbox but never calling `notifier.push`. Atlas going down now actually notifies.

**Files changed:**
- `jarvis/apps/sentinel/scheduler.py` — `atlas_health_tick` notifier.push wired; 18:00 cron switched to `evening_digest`.
- `jarvis/state/briefing.py` — added `evening_digest()` + helpers (`_closes_today`, `_open_loops_at_eod`, `_today_cost_rollup`, `_tomorrow_first_event`, `_atlas_pnl_close`, `_render_evening_markdown`).
- `jarvis/core/triggers.py` — `scan_periodic` wires R6/R7/R8 (new scanners) + R9 (presence).

**New files:**
- `jarvis/core/proactive_scanners.py` — `scan_meeting_imminent`, `scan_assignments_due_soon`, `scan_stale_tasks`. Extracted to keep `triggers.py` under 800 lines.
- `jarvis/state/operator_presence.py` — `PresenceMark` + `mark_present`/`last_seen`/`seconds_since_last_seen`/`scan_presence_stale`.
- `tests/test_evening_digest.py` — 4 tests.
- `tests/test_meeting_imminent.py` — 4 tests (5-min bucket, dedup, no-event >15min, fallback to tempo.today).
- `tests/test_operator_presence.py` — 7 tests.

**Known caveat:** sentinel cron times are still UTC, not your local TZ. The 8am UTC "morning digest" actually fires at 3–4am ET. Audit flagged this but moving to operator-local TZ cascades through `test_briefing.py`, `test_sentinel_atlas_health.py`, and dashboard-expected ISO strings. Deferred with TODO at `scheduler.py:217`. Easy fix later.

---

## J4 — Persona (Jarvis sounds like JARVIS now)

**Behavior change you should feel:**
- `persona.py` rewritten with anticipation, pushback, dry wit, expanded negative list, and form-of-address ("address Jyot by name only when warranted"). The `[result]. [next step or follow-up].` shape from CLAUDE.md is now explicitly modeled.
- `VOICE_WORD_CAP = 22` is one constant imported by `speech.py`, `proactive.py`, and `loop.py`. The three different word caps (25/20/20) are unified.
- TTS voice locked to `en-US-AndrewMultilingualNeural` in both `.env.example` and `config.py`. Aria-the-Alexa is gone.
- Voice fillers replaced with characterful set: "One moment, Jyot." / "Pulling that up." / "Stand by." instead of the bland old set.
- Filler rate now reads from `settings.voice_rate` instead of the hardcoded `+15%` that didn't match `VOICE_RATE`.
- `agents/lens/link_handler.py` imports `PERSONA` (no more parallel "You are Jarvis — terse personal assistant" doctrine).
- `.claude/agents/jarvis.md` rewritten (5 lines → 59 lines) referencing the canonical PERSONA so Claude-Code-side Jarvis sounds like runtime Jarvis.

**Files changed:**
- `jarvis/apps/voice/persona.py`
- `jarvis/apps/voice/fillers.py`
- `jarvis/apps/voice/speech.py`
- `jarvis/apps/voice/proactive.py`
- `jarvis/apps/voice/loop.py`
- `jarvis/config.py`
- `.env.example`
- `jarvis/agents/lens/link_handler.py`
- `.claude/agents/jarvis.md`

---

## J5 — Routing (smarter classification, gated destructive actions)

**Behavior change you should feel:**
- "is anything overdue?" now routes tempo + scholar instead of falling through to jarvis-0.3-confidence.
- "add Nvidia to my watchlist" routes to atlas with action `add_to_watchlist`.
- "pause the trader" routes to atlas with action `pause_agent` (previously bypassed authority gate entirely).
- "is there a TODO in our codebase about timeouts" routes to **forge** instead of tempo (because the new `_CODE_CONTEXT_RE` overrides tempo's `todo` keyword when code keywords are present).
- "check inbox and tell me about my BTC position" now correctly picks **tempo** as primary (earliest-mentioned domain wins, not first-rule-declared).
- Forge `merge`/`push`/`commit` now emit distinct actions so the authority gate's per-action confirmation actually works.
- Unmatched gibberish (low confidence + jarvis fallback) returns `needs_clarification: True` with a clarification prompt instead of silently self-handling.
- Authority gate now also checks response-side actions (`paused`, `halted`, `merged`, `pushed`, `committed`) so post-dispatch confirmation works.

**Files changed:**
- `jarvis/core/router.py` — new keyword rules + action rules + primary-by-earliest-mention + `_CODE_CONTEXT_RE` disambiguation.
- `jarvis/core/orchestrator.py` — clarification return when `confidence < 0.5 AND primary == "jarvis"`.
- `jarvis/core/authority.py` — response-side action gate + expanded `_ALWAYS_CONFIRM_ACTIONS`.
- `tests/test_orchestrator.py` — `test_low_confidence_returns_clarification` added.

**Architectural items I deliberately did NOT do:**
- LLM-backed classifier fallback (audit J1.4 P1). High value but high risk without runtime testing. Defer to a future J5.2.
- Async-generator `Orchestrator.dispatch` for interleaved fan-out. Architectural rewrite affecting every caller. Defer.
- Follow-up turn context inheritance ("actually, also include scholar"). Requires threading `prior_intent` through `classify`. Defer to a future J5.3.

---

## Integration glue I added myself

The J2 and J3 agents each flagged one cross-agent gap. I closed both:

1. **`briefing.py:evening_digest` now calls `_build_memory_section`** (J2 added the function, J3 forgot to invoke it). Evening digest now ends with a `## Memory` section showing yesterday's daily + recent context.
2. **`agent.py:_record_turn` and `cheap_handler.py:handle` now call `operator_presence.mark_present`** (J3 added the module, J2's spec excluded agent.py from J3's scope). Without these hooks, `scan_presence_stale` would never fire. Both hooks are best-effort with try/except — they can't break the chat hot path.

## Extra polish I added on top

After the four agent passes closed out, I added a small polish layer:

**Extended fact extraction (`jarvis/state/facts.py`)** — the original J2 set had four patterns (name, my-X-is, preference, reminder). I added four more:

| Pattern | Key | Example |
|---|---|---|
| `i ('m\|am\|live) in <place>` | `location` | "I'm in Brooklyn this week" |
| `i (work\|am available\|am free) from <hours>` | `hours` | "I work from 9 to 6" |
| `i <verb> every <cadence>` | `routine:<verb>` | "I meditate every morning" → `routine:meditate` |
| `don't / never / do not X` | `avoid` | "don't call me after 10pm" |

These dramatically expand what Jarvis can passively learn from normal conversation. Added 7 new tests to `test_memory_facts.py` covering each pattern + a multi-fact-per-sentence case.

**Sentinel TZ config (`jarvis/apps/sentinel/scheduler.py` + `.env.example`)** — the audit flagged that cron jobs fire at 08:00 / 18:00 UTC, which for EST is 03:00 / 13:00 local — the "morning" digest fires in the middle of the night. The J3 agent deferred fixing this because injecting a clock through every digest helper cascades through too many tests. I added a narrower fix: `JARVIS_TZ` env var (or fallback to `TZ`) controls the **scheduler firing time** only; digest *content* still uses UTC for determinism. Set `JARVIS_TZ=America/New_York` in `.env` to get the morning digest at actual local 8am. Default is UTC for backward compatibility with the existing test suite. Documented in `.env.example`. One new function `_resolve_scheduler_tz()`, one call-site change at `build_scheduler`. ~6 lines.

---

## What you need to run when you wake up

```powershell
cd C:\Users\jyot2\jarvis

# Verify Python side
pytest --cov=jarvis --cov-fail-under=70
ruff check jarvis\

# Verify web side (no UI changes this pass, but sanity-check the build):
cd web
pnpm tsc --noEmit
pnpm build

# Commit if everything's green:
cd C:\Users\jyot2\jarvis
git add -A
git status
git commit -m "perfect-jarvis: J2 memory + J3 proactivity + J4 persona + J5 routing

- J2: hydrate from chat_turns.jsonl, recap every turn, fact extractor,
  voice tier 1/2 cross-surface memory, _build_memory_section.
- J3: meeting/assignment/stale-task/presence scanners, real evening digest,
  atlas_health push bug fix, operator_presence module.
- J4: persona rewrite (anticipation/pushback/form-of-address/[result]+
  [next step]), unified VOICE_WORD_CAP, characterful fillers, single TTS
  voice, PERSONA used by link_handler + .claude/agents/jarvis.md.
- J5: watchlist/overdue/add_assignment/pause_agent rules, primary-by-
  earliest-mention, low-confidence clarification, response-side authority
  gate.

Integration glue: evening_digest calls _build_memory_section; agent.py +
cheap_handler.py mark operator-presence on every turn.

See docs/JARVIS_PERFECTION_AUDIT_2026-05-13.md for the audit this
implementation pass addressed."
git push
```

## Likely test failures you may see

Predictions based on changes:

1. **`tests/test_jarvis_chat_routing.py::test_no_recap_on_same_lane_turn`** — the old behavior was "recap suppressed on same-lane." My change makes recap ALWAYS run but with briefer header. If this test asserts the absence of any recap, it'll fail. Resolution: read the test; it likely asserts the absence of the "Earlier in this thread" header — the same-lane header is now "Rolling thread context", different string, so the test may still pass. If not, update the assertion to expect the new same-lane header.

2. **Tests that import the old voice word cap as a string** — if any test literal-matches "20 words" or "25 words" in a prompt, they'll fail because the new prompts use `f"{VOICE_WORD_CAP} words"`. Unlikely to be many.

3. **`tests/test_briefing.py`** — if any test asserts the evening digest is identical to morning digest, it'll fail because they're now distinct. The audit named this as a real bug, so the test (if it exists) was wrong; update to expect the new evening structure.

If any unexpected test breaks, the diagnosis path is: read the test's assertion, decide if it was locking in a bug we just fixed (update the test) or if our change is wrong (revert the change).

---

## What's still imperfect (deferred items, ranked)

| Item | Why deferred | Effort to land |
|---|---|---|
| Cron TZ → operator-local | Cascades through briefing tests + sentinel-health tests + dashboard ISO expectations | ~1h focused pass |
| LLM-backed classifier fallback (high-value) | Needs runtime testing; tight prompt for `core/classify.py` LLM path | ~2h |
| Follow-up turn context inheritance | Threads `prior_intent` through classify; needs careful test coverage | ~2h |
| `jarvis/agent.py` extraction to `state/recap.py` | Mechanical refactor; would drop agent.py from 999 → ~700 lines | ~30min |
| Async-generator `Orchestrator.dispatch` | Architectural; every caller changes | ~3h |
| Voice proactive `crit` filter (already fixed in earlier pass) | — | done |
| Mark_present on chat done above | — | done |

---

## The "is Jarvis perfect now" honest assessment

**What changed for the better, measurably:**
- Jarvis remembers across sessions (J2 hydration + recap-every-turn).
- Jarvis extracts and uses declarative facts (J2 facts module).
- Voice and chat share the same memory (J2 + the unified chat_turns.jsonl that already existed).
- Jarvis surfaces high-value events proactively (J3 four new scanners + evening digest + atlas health push).
- Jarvis has a coherent voice across all surfaces (J4 PERSONA used everywhere).
- Common operator phrasings ("anything overdue", "add to watchlist", "pause the trader") route correctly (J5).

**What still isn't "JARVIS the movie":**
- No truly LLM-grade intent classification yet — still rules-only.
- No follow-up turn context — each request still classified fresh.
- No presence-aware interrupt-vs-queue ("operator is in a meeting, hold this for 10 min") — the data is available, the rule isn't built.
- No personality continuity across days yet — facts are extracted but "remember when you said X yesterday" needs explicit recall trigger.

Three to five more focused passes get to "indistinguishable from JARVIS" feel. Today's pass got us probably 70% of the way there from the J1 starting point.

See you in the morning.

— me, at midnight or so
