# Jarvis Integration Audit

**Date:** 2026-05-12
**Branch:** `refactor/reorg` (post-reorg, tests green 980/980)
**Question:** "Jarvis isn't acting like a system that works together — each agent does its own thing."
**Verdict:** Correct. Most of the cross-agent reaction layer is wired but dead. Atlas decisions land in the inbox but never trigger downstream behavior. Two parallel dispatch architectures don't share work. Specific findings + ranked fixes below.

---

## TL;DR — the four real problems

1. **The event-driven reaction layer is wired but empty.** `register_inbox_listener(lambda e: fire_for_event(reg, e))` is set up at app startup. `fire_for_event()` is a stub that returns `[]`. Every inbox event flows through a function that does nothing. This is the single biggest cause of "agents not reacting to each other."

2. **Two trigger rules are dead code.** `fire_exam_scheduled` (R1) and `build_guardian_violation_event` (R5) are defined and unit-tested, but **no production code calls them**. Scholar creates an exam → no tempo task. Atlas guardian rejects a strategy → silent, only visible if someone reads the response.

3. **Inbox events go nowhere downstream.** R2/R3/R4 polling rules fire from sentinel every 30 min and write `InboxEvent`s. Then nothing reacts — events sit in `state/inbox.jsonl` until the dashboard renders them. No notification, no follow-up dispatch, no voice surface.

4. **Two dispatch architectures don't share work.** `POST /api/dispatch` uses `Orchestrator.dispatch` which fans out to all matched agents in parallel. `POST /api/jarvis/chat` uses Claude SDK + `delegate` tool, sequential, one agent per LLM turn. The chat path is what voice + chat actually use day-to-day. The fanout-capable orchestrator path is mostly used by tests.

---

## Detailed findings

### F1 — `fire_for_event()` is a stub

`jarvis/core/triggers.py:456-464`:

```python
def fire_for_event(reg, event):
    """...handles R5 (atlas guardian violations surfaced as inbox events)..."""
    fired: list[FiredTrigger] = []
    return fired  # event-driven rules beyond R5 are added here as needed
```

The docstring claims this handles R5, but the body doesn't even reference R5. The function is wired as an inbox listener (`jarvis/apps/api/app.py:1438`) so it runs on every `append_inbox` call — and returns an empty list every time. This is the runtime equivalent of `pass`.

**Why it matters:** Anything that wants cross-agent reactivity ("when atlas writes a crit event, surface it to voice/notify operator" or "when sentinel records a forge dead-letter, escalate") has to go through this function. Right now it's a black hole.

### F2 — R1 (scholar exam → tempo task) is orphan code

`fire_exam_scheduled(reg, exam_result)` exists in `triggers.py:126`. Grep results:

```
jarvis/core/triggers.py    — definition + log statement
tests/test_triggers.py     — 3 test sites
```

Zero production call sites. `jarvis.agents.scholar.agent.exam_session()` creates the exam record but never invokes `fire_exam_scheduled`. So creating an exam never auto-blocks the slot on tempo's calendar.

### F3 — R5 (guardian violation → inbox crit) is orphan code

`build_guardian_violation_event(strategy_id, violations)` exists in `triggers.py:367`. Grep results:

```
jarvis/core/triggers.py        — definition
tests/test_triggers.py         — 2 test sites
jarvis/apps/api/app.py:1471    — string describing it in the rules-listing endpoint
```

Zero production call sites. `jarvis.agents.atlas.agent.guardian_check()` returns violations inside the `AgentResponse.result["violations"]` field — but never builds an inbox event. So:

- Guardian rejects a strategy → result is returned, caller might log it or might not
- Dashboard doesn't see it (no inbox event)
- Voice doesn't see it (no inbox event)
- Morning brief doesn't surface it (no inbox event)
- Operator only finds out if they explicitly inspect the pipeline response

This is the single most safety-critical gap — guardian violations are the trading-safety circuit breaker.

### F4 — R2/R3/R4 trigger but stop at inbox

`scan_periodic(reg)` runs every 30 min from sentinel (`apps/sentinel/scheduler.py:119`, job id `triggers`). It correctly polls:

- R2: imminent exams (`scholar_exams.jsonl` → warn InboxEvent)
- R3: tasks due today with `course:` tag (→ info InboxEvent)
- R4: forge dead-letter records (→ crit InboxEvent)

Events get `append_inbox`'d. After that:

- **API**: `/api/inbox` and `/api/sentinel/snapshot` return them as JSON for the dashboard. ✅ Visible there.
- **No notifier push** — operator only sees them if dashboard is open.
- **No voice surface** — voice_context_tick (5 min) does read inbox into the fact sheet, so eventually they surface in voice replies. Lag = up to 5 min, plus you have to ask voice the right question.
- **No follow-up dispatch** — even a crit forge dead-letter doesn't trigger forge to retry, alert, or escalate.

Compare to atlas_tick (every 5 min): when atlas detects drawdown, it both writes an inbox event AND calls `notifier.push(...)` with priority. R2/R3/R4 skip the notifier.

### F5 — Atlas IS well-wired internally, but its output dead-ends

Atlas integration is actually the best-instrumented agent:

- `atlas_tick` every 5 min (`apps/sentinel/routines.py:148`):
  - Builds snapshot (pnl, positions, agent_state)
  - Runs deterministic `decide(snapshot, policy)` engine
  - Executes actions: noop / alert (push notification) / pause_agent / resume_agent
  - Writes ONE summary InboxEvent
- `atlas_daily_rollup` at 10pm: end-of-day digest, priority matches severity of today's events.
- `mission_control_sync_tick` every 30s: keeps dashboard in sync.

**What's missing:**

- `guardian_check` is only invoked inside `pipeline()` (the manual run). It's never auto-called in sentinel's atlas_tick. So guardian violations only happen when an operator runs `pipeline`. Continuous risk monitoring is absent.
- Atlas inbox events don't trigger reactions in other agents. If atlas writes "drawdown -8%, paused trader", scholar/tempo/forge have no awareness. (Whether they *should* react is a design question — see fixes below.)
- Atlas's `agent_state()` failures are logged but never re-broadcast as inbox events. If ATLAS HTTP goes down for 10 min, the only signal is "atlas degraded" in subsequent snapshots, plus sentinel atlas_health pings (which write health events but not crit-priority inbox).

### F6 — Two parallel dispatch paths

| Path | Used by | Behavior |
|------|---------|----------|
| `POST /api/dispatch` → `Orchestrator.dispatch()` | dashboard "manual dispatch", tests | Regex-classifies intent → primary + parallel agents → `asyncio.gather` fanout → returns combined response |
| `POST /api/jarvis/chat` → `JarvisChat.stream()` | dashboard chat, voice loop | Claude SDK with `delegate(agent, action, args)` MCP tool → LLM picks ONE agent per delegate call → can chain manually |

The router (`jarvis/core/router.py`) has explicit multi-domain fanout patterns:

```python
_MULTI = [
    (r"\b(briefing|morning|catch me up|what's on my plate)\b", ["tempo", "scholar", "atlas"]),
    (r"\b(end of day|wrap up)\b", ["tempo", "scholar", "atlas"]),
]
```

But the chat path (which is what users actually hit) doesn't use the router. JarvisChat's system prompt lists agents and tells the LLM "use delegate to hand work to your team" — the LLM has to figure out fanout on its own. Sometimes it does, sometimes it picks one agent and answers.

### F7 — Briefing aggregates correctly

`GET /api/briefing` → `state.briefing.build_briefing(reg)`. Calls:

- `tempo.triage_status` (with provider fallback to file state)
- Scholar state from files (`scholar_exams.jsonl`, `scholar_problems.jsonl`, `weak_topics.json`)
- `atlas.pnl()` + `atlas.portfolio()`
- `read_agent_log`, dead-letter count, cost rollup
- Renders markdown with one-line "at a glance" + per-section detail

This is actually the synthesized cross-agent view. **It works.** If it feels stale, the cause is upstream — tempo/scholar/atlas not surfacing fresh data, or the dashboard not calling /api/briefing.

### F8 — Memory + context sharing

Each turn through the orchestrator records a dispatch (`record_dispatch` in `state.memory`) and the orchestrator's `gather_context()` reads recent inbox + open tasks. JarvisChat (the chat path) builds a live state block per turn that includes voice-context-cache state (which includes recent inbox).

So context IS shared — both paths see inbox + tasks + atlas health. But nothing in the agents themselves cross-references this. E.g., when you tell tempo "draft a reply to the GBM stress-test email," tempo doesn't check atlas's current pnl to know whether the operator is busy with a drawdown.

---

## Fix list — ranked by impact ÷ effort

Numbered for easy reference in a follow-up PR. "Effort" is rough lines-of-code + design difficulty.

### Tier 1 — do these first (high impact, small effort)

**1. Wire R5: guardian_check publishes violations to inbox.** When `guardian_check` returns `approved=False`, also call `build_guardian_violation_event` and `append_inbox` AND `notifier.push(priority=2)`. ~15 lines in `atlas/agent.py`. Fixes the worst silent-failure mode in the trading path.

**2. Implement `fire_for_event` body.** Match incoming `InboxEvent`s by `(agent, severity, ref keys)` and dispatch follow-ups:
- `atlas` + `crit` (guardian violation) → notify + record confirmation (so operator has to acknowledge)
- `forge` + `crit` (dead-letter) → escalate via notifier (currently silent)
- `scholar` + `warn` (exam imminent within 24h) → write a tempo task auto-blocking the slot
- ~50 lines, behavior-defined. Brings the event-driven reaction layer alive.

**3. Wire R1: scholar.exam_session → tempo.add.** Inside `scholar.exam_session`, after the exam record is persisted, call `fire_exam_scheduled(self._registry, exam_result)`. Requires giving Scholar a reference to the registry (a `set_registry()` method on the agent or pass at construction). ~20 lines + 1 plumbing edit in registry build.

**4. Push notifications for R2/R3/R4 fires.** In `scan_periodic`, after `append_inbox(event)`, call `notifier.push(...)` for warn/crit severity. Currently these polling rules are silent until the dashboard is open. ~10 lines.

### Tier 2 — bigger wins, more design (medium impact, medium effort)

**5. Auto-guardian on atlas_tick.** Don't wait for the operator to run `pipeline()`. Sentinel's atlas_tick should call `guardian_check()` against current open positions and surface continuous violations. Decide policy: every tick? Once an hour? Only when pnl crosses threshold? ~40 lines + 1 design call.

**6. Decide the dispatch-path duality.** Two options:
- (a) Teach JarvisChat to call `Orchestrator.dispatch` for any query that the router's `_MULTI` regex flags as multi-domain. The LLM gets the synthesized cross-agent result instead of guessing whether to fan out.
- (b) Delete the `/api/dispatch` path and route everything through JarvisChat. Forces the LLM to use delegate consistently. Loses the deterministic regex-fanout for `briefing` queries.
- I'd take (a). It's an additive change — chat keeps streaming, but the system prompt instructs the LLM "for multi-domain questions, prefer calling `orchestrator_dispatch` first to get the synthesized view." ~80 lines including new MCP tool.

**7. Atlas events trigger tempo summaries.** When atlas writes a crit/alert inbox event, fire_for_event should also dispatch `tempo.draft_reply` or `tempo.add_task` to log the operator's intended response. Less critical than 1-4 but closes the loop on "I should email someone about this drawdown." ~30 lines.

### Tier 3 — polish (low impact or speculative)

**8. Inbox-event metadata on triggers.** Right now `FiredTrigger` records (rule_name, source_key, outcome) but not the InboxEvent it generated. Worth keeping the link for `/api/triggers/recent` to show "this trigger → wrote inbox event X → which triggered downstream dispatch Y."

**9. Agent contract: codify in code.** The 7-field envelope `{agent, intent, action, result, follow_ups, confidence, needs_confirm}` is documented in CLAUDE.md but not enforced as a Pydantic model on agent outputs. Pre-existing tech debt, not specific to this audit.

**10. Cross-agent context references.** Teach each agent to peek at the others' recent inbox events when relevant. E.g., tempo's draft_reply could prepend a note when atlas is in a known drawdown state. Speculative — depends on whether you actually want agents to "talk."

---

## What I'd ship next

If you want a follow-up PR (call it `feat/integration-revival`), I'd bundle **fixes 1, 2, 3, 4** as one coherent commit set:

- C1: `atlas.guardian_check` → publish violations as inbox crit + push
- C2: implement `fire_for_event` body with three handlers (atlas/crit, forge/crit, scholar/warn)
- C3: `scholar.exam_session` → call `fire_exam_scheduled`; plumb registry to Scholar
- C4: `scan_periodic` → notifier push on warn/crit
- C5: tests for each + integration test that runs a full event-flow scenario

That's the minimum to make Jarvis feel like a system that reacts to itself. Fixes 5–7 (auto-guardian, dispatch unification, atlas → tempo) can land in a second pass once 1–4 are proven.

---

## What does NOT need fixing

- The orchestrator's fanout via `asyncio.gather` works correctly when invoked.
- The router's regex multi-domain patterns are well-defined.
- Briefing aggregation works — it's not where the disconnect is.
- Atlas internal wiring (snapshot → decide → execute → inbox + push) is the cleanest of the five agents. Use it as the template for what the others should look like.
- Sentinel cron schedule is dense and correct. Job IDs, intervals, and arg-passing are fine.

The reorg didn't break anything in the integration layer — those problems pre-date this branch and are independent of where files live. Address them on a fresh branch off `refactor/reorg` once the reorg is merged.
