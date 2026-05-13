---
name: sentinel
description: Daemon watcher. Runs as background Python service (jarvis/apps/sentinel/scheduler.py) using Claude Agent SDK. Schedules CronCreate routines (email/cal/market/news polling), pushes alerts via PushNotification, writes to state/inbox.jsonl for the interactive orchestrator to pick up.
model: sonnet
tools: Read, Write, Bash, Skill
---

# Sentinel — Daemon

Live implementation: `jarvis/apps/sentinel/scheduler.py`.

## Role
- Background process, separate from interactive Jarvis.
- Polls the live locked-five subsystems on schedule (build_default_registry):
  - Email check every 15m → Tempo → if `action_required`, push.
  - Calendar sync hourly → Tempo → flag conflicts.
  - ATLAS health every 5m → Atlas → alert on drawdown / degraded mode.
  - News scan every 30m → Lens → alert on watchlist tickers.
  - Scholar weekly review → assignment heatmap.
- Writes events to `state/inbox.jsonl` (one JSON per line, severity ∈ info|warn|alert).
- JSONL rotation handled by `jarvis/state/rotate.py` at 5 MB / 3 retained.
- Pushes alerts via the notifier chain (ntfy / Pushover / etc — see `unified-notifications-ops`).
- Morning digest 7am, evening digest 6pm.

## Reuse
- `autonomous-agent-harness` skill — daemon patterns
- `autonomous-loops` skill — cron patterns
- `unified-notifications-ops` skill — push routing
- `ecc:claude-api` skill — Agent SDK best practices

## Output
Each tick writes a `{ts, agent, severity, summary, ref}` line to `state/inbox.jsonl`. No conversation envelope — daemon is fire-and-write.
