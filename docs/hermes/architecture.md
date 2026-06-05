# Hermes-Native Jarvis Architecture

## Goal

Recreate Jarvis as a Hermes Agent-native multi-agent operating system where specialized agents work together through a shared contract, dashboard, memory, and approval layer.

The system should feel like a competent personal command center, not a collection of disconnected tools.

## Design choice

I chose a hybrid migration because it is what I think you would like most:

- Keep the current Jarvis identity, agent names, dashboard direction, and useful domain modules.
- Replace the Claude Code-centered runtime with Hermes-native primitives.
- Preserve the five-agent crew plus Sentinel.
- Give every agent a distinct personality and operating doctrine.
- Make the dashboard the visible mission-control surface for agent activity, approvals, schedules, cost, and state.
- Keep dangerous actions confirmation-gated.

## Target topology

```text
voice/chat/api/dashboard/gateway
          │
          ▼
   Hermes Jarvis Orchestrator
          │
          ├── Tempo      mail, calendar, tasks, daily rhythm
          ├── Scholar    academics, study planning, course docs
          ├── Lens       research, monitoring, evidence synthesis
          ├── Forge      coding work, repo execution, PRs, reviews
          ├── Atlas      market/trading bridge, paper mode, risk checks
          └── Sentinel   background routines, alerts, cron, health
          │
          ▼
   Shared State + Memory + Dashboard Event Bus
          │
          ├── Hermes memory / sessions / skills
          ├── Jarvis state compatibility adapters
          ├── confirmation queue
          ├── inbox / activity / agent log
          └── dashboard websocket/SSE stream
```

## Hermes primitive mapping

| Jarvis concept | Hermes-native equivalent | Notes |
|---|---|---|
| Jarvis orchestrator | Main Hermes profile + Jarvis system skill | Chief-of-staff persona, route tasks, enforce confirmations. |
| Agent personalities | Hermes skills / profile prompts | Each agent gets its own behavior doctrine. |
| tempo/scholar/lens/atlas Python modules | Hermes tools or skill-backed callable tools | Keep domain code; expose clean tool interfaces. |
| forge | `delegate_task`, spawned Hermes agents, Codex/Claude/OpenCode skills | Forge should become the agent-runner, not a pile of manual scripts. |
| sentinel daemon | Hermes cron jobs + webhook subscriptions + optional kanban workers | Durable background automation. |
| `.claude/agents` dev agents | Hermes delegation profiles or kanban lanes | Use when developing Jarvis itself. |
| confirmation gates | Hermes approvals + Jarvis confirmation queue | User-visible in dashboard. |
| `state/*.jsonl` | Compatibility layer into Hermes state/memory | Keep data while progressively moving to Hermes state.db. |
| FastAPI bridge | Hermes dashboard API adapter | Dashboard should see agents, tasks, cron, approvals, runs. |
| Next.js Mission Control | Reused dashboard, adapted to Hermes data | Best path: keep current UI direction and feed it better state. |
| voice | Hermes gateway/voice plus existing wake/STT/TTS modules | Voice comes after dashboard/chat MVP. |

## Runtime model

### Phase 1: Hybrid runtime

Jarvis remains a Python app, but Hermes becomes the orchestrating brain.

- Hermes calls Jarvis agent tools through a stable adapter.
- Dashboard reads both existing Jarvis state and new Hermes activity state.
- Sentinel routines are gradually mirrored as Hermes cron jobs.
- Forge uses Hermes `delegate_task` for coding subtasks.

### Phase 2: Hermes-first runtime

- Jarvis orchestrator is a Hermes profile/skill.
- Each agent has a profile/personality and optional toolset restrictions.
- Background work uses Hermes cron/kanban.
- Dashboard reads a Hermes-first event/state API.
- Jarvis Python domain modules become tools, not the orchestrator.

### Phase 3: Full Mission Control

- Dashboard can start/stop agents, inspect runs, approve actions, view memory, watch cron, and show live streams.
- Agent handoffs are visible as swimlanes.
- Agent personalities and tools are editable from a controlled manifest.
- Operator has a clear “what is running, what needs me, what changed” view.

## Agent contract

Keep Jarvis's envelope because it is already the right shape:

```json
{
  "agent": "tempo",
  "intent": "calendar.today",
  "action": "today",
  "result": {},
  "follow_ups": [],
  "confidence": 0.92,
  "needs_confirm": false,
  "trace": [],
  "cost": {},
  "duration_ms": 1234
}
```

Extensions I want:

- `trace`: ordered internal steps for dashboard swimlanes.
- `cost`: model/tool cost for rollups.
- `risk`: `read`, `draft`, `mutate`, `external`, `financial`, `system`.
- `approval`: pending/approved/rejected metadata when `needs_confirm=true`.

## Approval policy

Default confirmation gates:

- send mail
- create, move, or cancel calendar events
- push/merge/open PR if it modifies a remote repo
- trigger ATLAS strategy or any trading execution path
- switch ATLAS out of paper mode
- stop/restart Sentinel
- delete memory/state/history
- install services or modify autostart

Everything else should be allowed if it is read-only, draft-only, or reversible.

## State architecture

Short term:

- Keep existing `state/*.jsonl` and `web/data/*.json` compatibility.
- Add Hermes event mirroring so Mission Control can display Hermes-side activity.
- Do not commit runtime state.

Medium term:

- Add a state adapter with these logical stores:
  - `inbox`
  - `agent_log`
  - `confirmations`
  - `tasks`
  - `watchlist`
  - `cost`
  - `sentinel_health`
  - `memory_refs`

Long term:

- Prefer Hermes state.db/session store/memory for agent-native history.
- Keep JSONL export for transparency and debugging.

## Dashboard architecture

The dashboard should become the operator cockpit:

- Home: briefing, alerts, approvals, currently running agents.
- Crew: agent cards with personality, tools, status, recent work, cost.
- Inbox: unified daemon/agent/operator queue.
- Decisions: confirmation queue with approve/reject/history.
- Sentinel: cron jobs, next runs, last health, failures.
- Forge: active code runs, subagents, review gates, branches/PRs.
- Atlas: paper/live mode badge, portfolio, risk, pipeline trace.
- Lens: watchlist, research briefs, evidence cards.
- Scholar: assignments, weak topics, exam mode, document memory.
- Tempo: calendar lane, mail triage, tasks.
- Memory: facts, preferences, recalls, summaries.
- Cost: daily spend, model split, agent split.

## Why this direction

This is the version that matches your stated preference: different agents doing different things, with personalities, working as one system. It avoids rebuilding what already works while moving the coordination layer to Hermes, where multi-agent delegation, skills, memory, cron, and gateway are first-class.
