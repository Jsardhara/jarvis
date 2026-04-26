# Jarvis — Project Rules

## What this is

Jarvis is a personal-assistant multi-agent system. Top-level orchestrator routes natural-language requests to 7 subsystem agents covering email, calendar/tasks, research, code delegation, finance (ATLAS bridge), messaging, and a background daemon.

Operator: single user (jyot2). Local-first. No cloud hosting until Phase 6+.

## Persona

- Tone: terse, direct, like a competent chief of staff. No filler ("sure!", "happy to"), no hedging.
- Confirmation: ask before send-email, send-message, calendar-mutation, code-merge, financial-trigger. Never ask before read-only ops.
- Pattern: `[result]. [next step or follow-up].`
- On voice surface (Phase 5): one-sentence confirmations. On terminal: full detail.

## Agent contract

Every subsystem agent returns this JSON envelope when invoked by the orchestrator:

```json
{
  "intent": "string — what request was understood as",
  "action": "string — what was done (or 'proposed' if awaiting confirm)",
  "result": "object — payload (varies per agent)",
  "follow_ups": ["array of suggested next actions"],
  "confidence": "number 0-1",
  "needs_confirm": "bool — true if destructive/external-effect"
}
```

Orchestrator surfaces `needs_confirm: true` to user before executing.

## Routing table (orchestrator → subsystem)

| Intent keyword/regex | Agent |
|----------------------|-------|
| email, inbox, reply, draft, mail | Aide |
| calendar, schedule, meeting, free time, todo, task, remind | Chronos |
| research, look up, summarize, find out, news on | Sherlock |
| code, repo, PR, build, test, ship, fix bug, refactor | Forge |
| portfolio, ATLAS, position, P&L, market, trade | Ledger |
| slack, discord, sms, message, reply to <channel> | Echo |
| ambiguous / multi-domain | Jarvis self-handles or parallel-dispatches |

## Model routing (cost-aware)

- **Opus 4.7** — orchestrator routing on novel/ambiguous requests, multi-agent synthesis, architectural code work in Forge.
- **Sonnet 4.6** — default for subsystem agents.
- **Haiku 4.5** — high-frequency utility (email classification, calendar lookup, simple yes/no).

## State conventions

- All persistent state under `jarvis/state/`.
- `tasks.json` — todos, schema `{id, title, due, tags, status, created, updated}`.
- `inbox.jsonl` — daemon→interactive queue, one event per line `{ts, agent, severity, summary, ref}`.
- `memory/` — Jarvis-scoped narrative memories (separate from claude-mem global).
- Never write secrets to state files. Use OS keyring or env vars.

## Code style (project-specific overlays on global)

- Python: 3.11+, type hints required, ruff for lint, pytest for tests, 80% coverage.
- TS (web phase): strict mode, no `any`, vitest.
- Files <800 lines, functions <50 lines.
- Immutability: never mutate dicts/lists in place — return new copies.
- All agent prompts version-controlled in `.claude/agents/*.md`.

## Reuse over rebuild

Existing skills must be invoked rather than re-implemented:
- `email-ops`, `chief-of-staff` → inside Aide
- `google-workspace-ops`, `ecc:schedule` → inside Chronos
- `deep-research`, `research-ops`, `exa-search` → inside Sherlock
- `autonomous-agent-harness`, `ecc:plan`, `ecc:prp-implement`, `github-ops` → inside Forge
- `messages-ops` → inside Echo
- `autonomous-loops`, `unified-notifications-ops` → inside Sentinel daemon

## ATLAS boundary

Ledger is a thin HTTP client over ATLAS FastAPI (`C:\Users\jyot2\atlas\`). Never edit ATLAS source from this project. If ATLAS needs changes, open a PR there.

## Confirmation defaults

| Action | Confirm? |
|--------|----------|
| Read inbox / calendar / portfolio | No |
| Draft reply / draft event | No |
| Send email / send message | Yes |
| Move/cancel calendar event | Yes |
| Create todo / mark done | No |
| Spawn dev agent / open PR | Yes |
| Trigger ATLAS strategy | Yes |
| Stop daemon / restart Sentinel | Yes |

## Testing

TDD enforced. Write test → fail → implement → pass → refactor. Run `pytest --cov=jarvis --cov-fail-under=80` before any commit.

## Don't

- Don't hardcode API keys — env vars + `.env.example` only.
- Don't bypass confirmation defaults.
- Don't write to ATLAS source.
- Don't add features outside current phase scope.
- Don't add backwards-compat shims for code that has never shipped.
