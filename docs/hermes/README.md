# Jarvis on Hermes

This folder is the migration control center for rebuilding Jarvis as a Hermes Agent-native multi-agent system.

The intent is not to flatten Jarvis into one generic chatbot. The intent is to keep Jarvis as a coordinated crew:

- Jarvis: chief-of-staff orchestrator
- Tempo: time, mail, calendar, tasks
- Scholar: academics, study, course intelligence
- Lens: research, monitoring, external world awareness
- Forge: code/project execution through subagents
- Atlas: markets/trading bridge, paper-mode and confirmation-gated by default
- Sentinel: background watcher, cron, health, alerts
- Me: operator approval and taste layer

Files:

- `quickstart.md` — practical runbook: start backend, start dashboard, edit manifest, run checks.
- `architecture.md` — target system architecture and Hermes mapping.
- `agent-personalities.md` — personality, authority, model, and dashboard identity for every agent.
- `dashboard-contract.md` — dashboard data/API shape for Mission Control.
- `migration-plan.md` — phased implementation plan.
- `agent-manifest.yaml` — machine-readable crew manifest that can be used by dashboard/backend/profile generation later.

Design choice I made: hybrid migration.

Keep the good Jarvis domain code and the Mission Control dashboard. Replace Claude Code-specific orchestration with Hermes primitives: skills, profiles, delegation, cron, kanban, memory, gateway, and approval policy.
