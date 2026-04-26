# Jarvis

Personal-assistant multi-agent system on Claude Code. Daemon + interactive. Single-operator.

## What it does

| Surface | Status |
|---------|--------|
| CC terminal chat | Phase 1 |
| Background daemon (Sentinel) | Phase 3 |
| Slack/Discord/SMS | Phase 4 |
| Voice (wake word + STT + TTS) | Phase 5 |
| Web dashboard | Phase 6 |
| Home automation | Phase 7 |

## Agents

| Agent | Role |
|-------|------|
| **Jarvis** | Orchestrator — routes to subsystems |
| **Aide** | Email triage + drafts |
| **Chronos** | Calendar + tasks |
| **Sherlock** | Research |
| **Forge** | Code-work delegation |
| **Ledger** | Finance + ATLAS bridge |
| **Echo** | Messaging surfaces |
| **Sentinel** | Daemon watcher |

## Run

### Interactive (Phase 1+)
```bash
cd C:\Users\jyot2\jarvis
claude
> what's on my plate today
```

### Daemon (Phase 3+)
```bash
cd C:\Users\jyot2\jarvis
python -m jarvis.daemon.sentinel
```

## Layout

```
jarvis/
├── .claude/
│   ├── CLAUDE.md          ← project rules + persona
│   ├── settings.json      ← MCP enable list, hooks
│   └── agents/            ← 8 agent prompts
├── daemon/                ← Sentinel (Phase 3)
├── state/                 ← runtime state (gitignored)
├── tests/                 ← pytest, 80%+ coverage
├── web/                   ← Next.js dashboard (Phase 6)
└── voice/                 ← wake/STT/TTS (Phase 5)
```

## Plan

Full plan: `C:\Users\jyot2\.claude\plans\i-want-to-melodic-hopper.md`

## Phase 0 status

- [x] Project skeleton
- [x] CLAUDE.md (rules + persona + routing + agent contract)
- [x] settings.json (MCP enable list)
- [x] 8 agent stub files
- [ ] Gmail / Calendar / Drive MCP OAuth (manual user step)
- [ ] Init git + first commit

## Constraints

- Single-user. Local-first until Phase 6.
- ATLAS at `C:\Users\jyot2\atlas\` is read-only from Jarvis. All interaction over HTTP.
- TDD enforced, 80% coverage.
- Confirmation required for: send-email, send-message, calendar-mutation, dev PR push, ATLAS strategy trigger.
