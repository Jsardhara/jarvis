# Jarvis Architecture

Single-operator personal-assistant multi-agent system. This doc maps the package layout to responsibilities. For the locked agent set and confirmation gates, see `.claude/CLAUDE.md`. For the rationale behind the current shape, see `REORG_PLAN.md`.

## The four layers

The Python package `jarvis/` is organized as four layers, each with a defined responsibility and a defined direction of dependency.

**`jarvis.core` — pure orchestration.** Intent classification (`router`), tier-based authority (`classify` + `authority`), the main dispatch loop (`orchestrator`), retry / dead-letter (`supervisor`), event-driven cross-agent rules (`triggers`), and per-response verification (`verify`). No IO, no external calls. This layer is fully unit-testable with mocks.

**`jarvis.llm` — Claude glue.** A single global FIFO queue (`queue`) so every LLM call funnels through one rate-limited surface, a synchronous client wrapper (`client`), per-turn model selection (`model_router` — Sonnet vs Opus), and cost telemetry (`cost`). Subsystems depend on this layer instead of importing `claude-agent-sdk` directly.

**`jarvis.state` — persistence and memory.** The `__init__.py` exposes the operational state API (`add_task`, `append_inbox`, `read_agent_log`, `read_confirmations`, etc. — backed by `state/*.jsonl` files). Submodules: three-tier `memory` (session / daily / long-term), semantic chat-history `memory_index`, deterministic markdown digests (`briefing`, `exports`), and cross-device chat persistence (`chat_turns`). Everything that touches disk lives here.

**`jarvis.agents` — subsystem agents.** One subpackage per locked agent (`tempo`, `scholar`, `lens`, `forge`, `atlas`). Each follows the same shape: `agent.py` is the public surface returning an `AgentResponse`, sibling modules hold helpers, and `providers/` (where applicable) holds the swappable real/mock IO backends. The agent registry (`registry.py`) wires them into a `name → AgentDescriptor` map that the orchestrator dispatches against. Shared protocol classes and provider implementations that cross agent boundaries live at `agents/providers.py`.

A fifth direction — `jarvis.apps` — holds the deployable processes that wrap the layers above: the FastAPI server (`apps.api`), the Sentinel daemon (`apps.sentinel`), and the voice loop (`apps.voice`). Apps depend down into core/llm/state/agents but never the reverse.

## Dependency direction

Strict downward: `apps → agents → state → llm → core → contract/config`. Anything in `core/` may not import from `agents/`, `apps/`, or any IO-touching module. Anything in `agents/` may not import from `apps/`. `contract.py` and `config.py` sit at the package root because they're consumed everywhere and have no peer to group with.

## Runtime entrypoints

```
python -m uvicorn jarvis.apps.api.app:app --host 0.0.0.0 --port 8765
python -m jarvis.apps.sentinel
python -m jarvis.apps.voice
```

The four `.bat` launchers under `scripts/launchers/` invoke these from the Windows Startup folder. `scripts/install-services.ps1` regenerates the launchers when paths change.

## Request lifecycle

A user request — voice, chat, or HTTP — enters `apps.api.app` or `apps.voice.loop`, reaches `agent.JarvisChat` (the top-level entrypoint), is routed to a model lane by `llm.model_router`, classified to a tier by `core.classify`, and dispatched by `core.orchestrator`. The orchestrator builds a registry-backed handler for each requested agent in `agents/`, gates execution through `core.authority` if the action requires operator confirmation, runs the agent, and writes the result through `state.*` (inbox event, agent log, confirmation record). The verification envelope from `core.verify` wraps the result before it returns up the stack.

`apps.sentinel.scheduler` runs the same agents on cron from `apps.sentinel.routines`, writing into the same `state.*` surface that the API reads. Sentinel never returns to the user directly — it raises inbox events that surface in the next interactive session via the `.claude/hooks/session_start_inbox.py` digest.

## Known violations and pre-existing rule deviations

Two files exceed the 800-line ceiling from `~/.claude/rules/common/coding-style.md` and were intentionally **not** split in the reorg:

- `jarvis/apps/api/app.py` — 1524 lines. Splitting requires lifting closures over shared state (`bus`, `reg`, `o`) out of `make_app()` into module-level routers using `app.state` or factory functions. That's a behavior-preserving but structural change; bundling it with the reorg quadruples blast radius. Phase-2 PR.
- `jarvis/agents/atlas/agent.py` — 1003 lines. Cleaner candidate (mostly module-level classes), but split into `bridge.py + orchestrator.py + pipeline.py + mocks.py` was deferred for the same isolation reason.

Both are tracked in the README "Plan ahead" section and `REORG_PLAN.md §2`.

## What deliberately did NOT move

- `web/` (Next.js dashboard) keeps its own conventions — Python reorg does not touch it.
- `state/` (runtime data — JSONL, logs, SQLite) is not moved; the package change is purely import-path.
- `tests/` stays flat. Mirroring `tests/` into `tests/core/`, `tests/agents/tempo/`, etc. is a Phase-2 follow-up.
- `jarvis/contract.py`, `jarvis/config.py`, `jarvis/search.py` stay at the package root. They have no peers to group with and moving them buys nothing.
- The agent contract envelope is still informal — codifying it as a Pydantic model is a separate refactor.

## File-system leftovers

The reorg moves files via the Linux sandbox over a virtiofs mount; `rmdir` on the now-empty `jarvis/{subsystems,daemon,voice,web}/` directories was rejected by the mount layer. The directories still exist on disk with empty `__init__.py` files and stale `__pycache__/` entries. They cause no runtime breakage — nothing imports them — but should be removed from PowerShell:

```powershell
Remove-Item -Recurse -Force jarvis\subsystems, jarvis\daemon, jarvis\voice, jarvis\web
```

Same for the regenerated launchers — re-run `scripts/install-services.ps1` after merge so the Windows Startup folder picks up the new module paths.
