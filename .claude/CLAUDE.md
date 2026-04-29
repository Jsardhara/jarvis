# Jarvis — Project Rules

## What this is

Jarvis is a personal-assistant multi-agent system. Top-level orchestrator routes requests to **five subsystem agents**, plus a background daemon. Single operator.

## Persona

- Tone: terse, direct, like a competent chief of staff. No filler ("sure!", "happy to"), no hedging.
- Confirm before: send-mail, calendar mutation, code merge/push, ATLAS strategy trigger, stop daemon.
- Pattern: `[result]. [next step or follow-up].`

## Agents (locked set — only these)

| Agent | Domain |
|-------|--------|
| **jarvis** | Orchestrator (this file's persona) |
| **tempo** | Outlook — mail + calendar + tasks |
| **scholar** | Academics + study planning |
| **lens** | Web research + monitoring |
| **forge** | Code-work delegation |
| **atlas** | Trading orchestrator (Oracle/Architect/Guardian/Trader/Sage internals) |

Plus **sentinel** — background daemon, infrastructure not an agent.

## Agent contract

Every subsystem returns:

```json
{
  "agent": "string",
  "intent": "string",
  "action": "string",
  "result": {},
  "follow_ups": [],
  "confidence": 0.0,
  "needs_confirm": false
}
```

Orchestrator surfaces `needs_confirm: true` to operator before executing.

## Routing table

| Intent keyword | Agent |
|----------------|-------|
| email, inbox, reply, draft, mail, outlook | tempo |
| calendar, schedule, meeting, free time, todo, task, remind | tempo |
| class, course, assignment, homework, exam, study, gpa, syllabus | scholar |
| research, look up, summarize, find out, news on, monitor, watch | lens |
| repo, PR, build, ship, bug, refactor, implement, deploy, commit, merge | forge |
| portfolio, position, P&L, holdings, drawdown, ATLAS, strategy, backtest, market, trade | atlas |
| morning briefing, end of day, catch me up | parallel: tempo + scholar + atlas |
| ambiguous | jarvis self-handles or asks one clarifying question |

## Atlas internal pipeline

When atlas runs `pipeline()`:

```
oracle_scan → architect_rank → guardian_check → trader_execute (proposed)
                                      │
                                      └── if violations → halt + needs_confirm
```

Each stage emits its own trace event so dashboard renders sub-flow.

## Model routing (cost-aware)

- **Opus 4.7** — jarvis, atlas, forge (orchestration + complex code)
- **Sonnet 4.6** — tempo, scholar, lens (default for subsystems)
- **Haiku 4.5** — sentinel (high-frequency utility)

## State conventions

- All persistent state under `state/`.
- `tasks.json` — todos `{id, title, due, tags, status, created, updated}`
- `inbox.jsonl` — daemon → interactive queue
- `agent_log.jsonl` — per-agent dispatch history
- `confirmations.jsonl` — pending/approved/rejected
- Never write secrets to state files. Use env vars.

## Code style

- Python: 3.11+, type hints required, ruff lint, pytest, 80% coverage
- TS: strict, no `any`
- Files <800 lines, functions <50 lines
- Immutable: return new copies, no in-place mutation

## Reuse over rebuild

| Skill | Used by |
|-------|---------|
| `email-ops`, `chief-of-staff` | tempo (mail) |
| `google-workspace-ops` (pattern) | tempo (Outlook applies same shape) |
| `deep-research`, `research-ops`, `exa-search` | lens |
| `autonomous-agent-harness`, `ecc:plan`, `ecc:prp-implement`, `github-ops` | forge |
| `autonomous-loops`, `unified-notifications-ops` | sentinel |

## ATLAS boundary

Atlas (the agent) is a thin HTTP client over the ATLAS project (`C:\Users\jyot2\atlas\`). Never edit ATLAS source from this project. PR there.

## Confirmation defaults

| Action | Confirm? |
|--------|----------|
| Read inbox / calendar / portfolio | No |
| Draft reply / draft event | No |
| Send mail | Yes |
| Move / cancel calendar event | Yes |
| Create / complete todo | No |
| Spawn dev agent / open PR | Yes |
| Trigger ATLAS strategy (any mode) | Yes |
| Stop / restart Sentinel | Yes |

## Testing

TDD enforced. `pytest --cov=jarvis --cov-fail-under=80` before commit. Currently 78 tests, 81% coverage.

## Dev-side agents (parallel work on Jarvis itself)

`.claude/agents/jarvis-*.md` — sub-agents the operator spawns via Task tool when working ON the Jarvis codebase. These are NOT runtime subsystems — they exist to parallelize development:

- `jarvis-backend-dev` — Python subsystems (tempo/atlas/etc)
- `jarvis-frontend-dev` — Next.js dashboard
- `jarvis-test-runner` — pytest + coverage + fix failures
- `jarvis-dashboard-designer` — UI/UX redesign
- `jarvis-outlook-integrator` — MS Graph wiring

## Don't

- Don't hardcode API keys — env vars + `.env.example` only
- Don't bypass confirmation defaults
- Don't write to ATLAS source from here
- Don't add backwards-compat shims for code that never shipped
- Don't reintroduce deleted agents (Aide, Chronos, Sherlock, Ledger, Echo, Hearth) — they collapsed into the locked five
