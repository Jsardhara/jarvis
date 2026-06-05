# Mission Control Dashboard Contract for Hermes-Jarvis

## Purpose

The dashboard should be the visible cockpit for Hermes-native Jarvis. It should not be a passive status page. It should show live agent work, let the operator approve decisions, and make background automation legible.

## Core views

1. Home
   - daily briefing
   - active runs
   - pending approvals
   - critical inbox events
   - next Sentinel jobs

2. Crew
   - agent cards
   - personality summary
   - status
   - tools/capabilities
   - recent actions
   - cost and reliability

3. Activity
   - unified agent log
   - trace events
   - errors and retries
   - filter by agent/request/risk

4. Decisions
   - pending confirmations
   - approve/reject
   - audit history
   - risk class and proposed payload

5. Sentinel
   - cron job grid
   - next/last run
   - failure count
   - health timeline

6. Forge
   - active implementation tasks
   - subagent roster
   - spec-review and quality-review gates
   - branch/PR/test state

7. Atlas
   - paper/live mode badge
   - portfolio/P&L/positions
   - Oracle → Architect → Guardian → Trader → Sage swimlane
   - risk alerts

8. Tempo, Scholar, Lens
   - domain-specific surfaces for current state and recent outputs

## Event envelope

All live dashboard events should fit this shape:

```json
{
  "id": "evt_...",
  "ts": "2026-05-28T00:00:00Z",
  "type": "agent.start | agent.done | agent.error | approval.created | cron.done | inbox.event",
  "request_id": "req_...",
  "agent": "tempo",
  "risk": "read | draft | mutate | external | financial | system",
  "severity": "info | warn | alert",
  "title": "Short operator-facing title",
  "payload": {},
  "trace": []
}
```

## Agent card shape

```json
{
  "id": "tempo",
  "name": "Tempo",
  "role": "Mail, calendar, tasks, daily rhythm",
  "personality": "Crisp executive assistant",
  "status": "active | idle | degraded | disabled",
  "mode": "live | mock | paper",
  "model": "balanced",
  "color": "blue",
  "icon": "Mail",
  "capabilities": ["mail", "calendar", "tasks", "scheduling"],
  "confirmation_gates": ["send_mail", "calendar_mutation"],
  "recent": [],
  "metrics": {
    "runs_today": 0,
    "errors_today": 0,
    "cost_today_usd": 0.0,
    "avg_duration_ms": 0
  }
}
```

## Approval shape

```json
{
  "id": "conf_...",
  "created_at": "2026-05-28T00:00:00Z",
  "agent": "atlas",
  "action": "trader_execute",
  "risk": "financial",
  "summary": "Proposed paper trade execution",
  "payload": {},
  "status": "pending | approved | rejected | expired",
  "expires_at": null
}
```

## API surface

Short-term adapter endpoints:

- `GET /api/hermes/agents`
- `GET /api/hermes/activity?agent=&limit=`
- `GET /api/hermes/approvals`
- `POST /api/hermes/approvals/{id}/approve`
- `POST /api/hermes/approvals/{id}/reject`
- `GET /api/hermes/cron`
- `GET /api/hermes/inbox`
- `GET /api/hermes/cost/rollup`
- `GET /api/hermes/memory/summary`
- `WS /ws/hermes`

The existing API can keep its current routes while these new routes normalize Hermes state for the dashboard.

## Dashboard behavior

- Show paper/live mode prominently for Atlas.
- Show “waiting on you” approvals at the top.
- Collapse low-severity Sentinel noise into rollups.
- Make every agent run inspectable with trace and raw payload.
- Separate draft/proposed actions from completed actions.
- Never hide errors; degrade loudly but gracefully.
