# Jarvis Repo Reorganization — Proposal

**Status:** APPROVED, executing on `refactor/reorg`. C1 committed.

**Scope adjustments after start:**
- **`src/` layout deferred** — keeping `jarvis/` at repo root. Avoids editable-install friction. Phase 2 candidate.
- **C2 (api.py split) and C3 (atlas.py split) deferred** — both require extracting closures / module-level refactoring that exceeds "move + light cleanup". The 800-line violation is pre-existing; this PR keeps the rule violations but reorganizes everything around them. Splits go in a follow-up PR with their own test pass.


**Branch (to create on approval):** `refactor/reorg`
**Scope:** Python package layout, large-file splits, service launchers, CI. **Not** touched: `web/` (Next.js dashboard), `state/`, `docs/`, `.git/`, ATLAS project.

---

## 1. Why

Current `jarvis/` Python package has accumulated drift typical of a fast-shipping single-operator codebase:

- **22 loose modules at the package root** mixing pure logic (`classify`, `router`, `contract`), Claude/LLM glue (`llm`, `claude_queue`, `model_router`, `jarvis_agent`), persistence (`state`, `memory`, `memory_index`, `exports`, `chat_turns`), and runtime utilities (`triggers`, `verify`, `briefing`, `search`).
- **`jarvis/subsystems/` is flat with 21 files** — agent code (`tempo.py`, `atlas.py`, `scholar.py`...) lives next to its helpers (`tempo_stack.py`, `scholar_study.py`, `forge_runner.py`...) and next to mail/cal providers (`gmail_imap_provider.py`, `icloud_provider.py`...). No grouping by agent.
- **Two files over the 800-line ceiling** set by `~/.claude/rules/common/coding-style.md`:
  - `jarvis/web/api.py` — 1524 lines (one mega-file with all FastAPI routes, WebSocket bus, atlas merge logic, preferences validation)
  - `jarvis/subsystems/atlas.py` — 1003 lines (bridge + orchestrator + mocks + pipeline parsing all in one)
- **Stale ruff per-file-ignores** in `pyproject.toml` reference files that no longer exist (`jarvis/subsystems/ledger.py`, `jarvis/web/webhooks.py`).
- No `src/` layout — current setup allows accidental `import jarvis` from cwd shadowing the installed package.

This is a one-time reorg into the shape a Python codebase of this size would have at any organization with a coding-standards bar. Per-call behavior is preserved; only file paths and import statements change.

---

## 2. Decisions baked in

From the clarifying answers:

| Decision | Choice |
|----------|--------|
| Target layout | **I propose; you approve** — see §3 |
| Refactor depth | **Move + light cleanup** — split files >800 lines, regroup, no behavior changes |
| Delivery | **Branch + PR** on `refactor/reorg`, staged commits, history preserved via `git mv` |
| Service paths | **Updated as part of the reorg** — `.bat` launchers, `install-services.ps1`, CI |

---

## 3. Target tree

```
jarvis/                                       # repo root (unchanged path)
├── .claude/                                  # unchanged
├── .github/workflows/ci.yml                  # paths bumped
├── docs/                                     # unchanged
├── scripts/                                  # reorganized within (see §6)
├── state/                                    # runtime data — NOT touched
├── tests/                                    # imports updated; structure unchanged (Phase 1)
├── web/                                      # Next.js — not touched
├── src/                                      # NEW: src/ layout
│   └── jarvis/
│       ├── __init__.py
│       ├── config.py                         # (moved from jarvis/config.py)
│       ├── contract.py                       # (moved from jarvis/contract.py)
│       ├── agent.py                          # was jarvis_agent.py — top-level: it IS the agent
│       ├── search.py                         # stays — used by many subsystems
│       │
│       ├── core/                             # pure orchestration, no IO
│       │   ├── __init__.py
│       │   ├── classify.py                   # was classify.py
│       │   ├── router.py                     # was router.py
│       │   ├── orchestrator.py               # was orchestrator.py
│       │   ├── authority.py                  # was authority.py
│       │   ├── supervisor.py                 # was supervisor.py
│       │   ├── verify.py                     # was verify.py
│       │   └── triggers.py                   # was triggers.py
│       │
│       ├── llm/                              # Claude/LLM glue
│       │   ├── __init__.py
│       │   ├── client.py                     # was llm.py
│       │   ├── queue.py                      # was claude_queue.py
│       │   ├── model_router.py               # was model_router.py
│       │   └── cost.py                       # was cost.py
│       │
│       ├── state/                            # persistence
│       │   ├── __init__.py                   # barrel — re-exports public API for back-compat
│       │   ├── tasks.py                      # split from state.py
│       │   ├── inbox.py                      # split from state.py
│       │   ├── agent_log.py                  # split from state.py
│       │   ├── confirmations.py              # split from state.py
│       │   ├── chat_turns.py                 # was chat_turns.py
│       │   ├── memory.py                     # was memory.py
│       │   ├── memory_index.py               # was memory_index.py
│       │   ├── exports.py                    # was exports.py
│       │   └── briefing.py                   # was briefing.py
│       │
│       ├── agents/                           # was subsystems/, now grouped per agent
│       │   ├── __init__.py
│       │   ├── registry.py                   # was subsystems/registry.py
│       │   ├── tempo/
│       │   │   ├── __init__.py               # re-exports agent class
│       │   │   ├── agent.py                  # was subsystems/tempo.py
│       │   │   ├── stack.py                  # was subsystems/tempo_stack.py
│       │   │   └── providers/
│       │   │       ├── __init__.py
│       │   │       ├── base.py               # was subsystems/providers.py
│       │   │       ├── gmail_imap.py         # was subsystems/gmail_imap_provider.py
│       │   │       ├── drexel_oauth.py       # was subsystems/drexel_oauth_provider.py
│       │   │       ├── icloud.py             # was subsystems/icloud_provider.py
│       │   │       └── multi_mail.py         # was subsystems/multi_mail_provider.py
│       │   ├── scholar/
│       │   │   ├── __init__.py
│       │   │   ├── agent.py                  # was subsystems/scholar.py
│       │   │   ├── study.py                  # was subsystems/scholar_study.py
│       │   │   └── db.py                     # was subsystems/study_db.py
│       │   ├── lens/
│       │   │   ├── __init__.py
│       │   │   ├── agent.py                  # was subsystems/lens.py
│       │   │   ├── link_handler.py           # was subsystems/link_handler.py
│       │   │   └── news_provider.py          # was subsystems/news_provider.py
│       │   ├── forge/
│       │   │   ├── __init__.py
│       │   │   ├── agent.py                  # was subsystems/forge.py
│       │   │   ├── daily.py                  # was subsystems/forge_daily.py
│       │   │   ├── github.py                 # was subsystems/forge_github.py
│       │   │   └── runner.py                 # was subsystems/forge_runner.py
│       │   └── atlas/
│       │       ├── __init__.py
│       │       ├── bridge.py                 # split from subsystems/atlas.py (~265 lines)
│       │       ├── orchestrator.py           # split from subsystems/atlas.py (~620 lines)
│       │       ├── pipeline.py               # split from subsystems/atlas.py (envelope parse)
│       │       ├── mocks.py                  # split from subsystems/atlas.py (mock_*)
│       │       ├── ws_client.py              # was subsystems/atlas_ws_client.py
│       │       └── budget.py                 # was subsystems/budget.py (atlas-scoped)
│       │
│       ├── apps/                             # was web/, daemon/, voice/ — top-level deployables
│       │   ├── __init__.py
│       │   ├── api/                          # was jarvis/web/
│       │   │   ├── __init__.py
│       │   │   ├── __main__.py               # `python -m jarvis.apps.api` shortcut
│       │   │   ├── app.py                    # make_app() + lifespan (slim)
│       │   │   ├── deps.py                   # shared bus + push helpers
│       │   │   ├── atlas_proxy.py            # was web/atlas_proxy.py
│       │   │   └── routers/                  # SPLIT of api.py (1524 → ~6 files of ~250 lines)
│       │   │       ├── __init__.py
│       │   │       ├── inbox.py
│       │   │       ├── tasks.py
│       │   │       ├── confirmations.py
│       │   │       ├── chat.py
│       │   │       ├── atlas.py
│       │   │       ├── briefing.py
│       │   │       ├── preferences.py
│       │   │       └── ws.py                 # _Broadcaster + websocket endpoints
│       │   ├── sentinel/                     # was jarvis/daemon/
│       │   │   ├── __init__.py
│       │   │   ├── __main__.py
│       │   │   ├── scheduler.py              # was daemon/sentinel.py (renamed for clarity)
│       │   │   ├── routines.py               # was daemon/routines.py
│       │   │   ├── notifier.py               # was daemon/notifier.py
│       │   │   ├── mission_control_bridge.py # was daemon/mission_control_bridge.py
│       │   │   ├── atlas_decision.py         # was daemon/atlas_decision.py
│       │   │   └── voice_context_tick.py     # was daemon/voice_context_tick.py
│       │   └── voice/                        # was jarvis/voice/  (kept flat — own discipline)
│       │       ├── __init__.py
│       │       ├── __main__.py
│       │       └── (existing 18 files — unchanged internal layout)
│       │
│       ├── tools/
│       │   └── desktop_mcp.py
│       └── personas/
│           ├── jarvis_soul.md
│           └── jarvis_soul_lite.md
│
├── pyproject.toml                            # `where=["src"]`, stale ignores removed
├── README.md                                 # tree diagram refreshed
├── .env.example
└── .gitignore
```

### Module-path mapping

Every public name keeps working. The runtime entrypoints change as follows.

| Was | Becomes |
|-----|---------|
| `jarvis.web.api:app` | `jarvis.apps.api.app:app` |
| `python -m jarvis.daemon.sentinel` | `python -m jarvis.apps.sentinel` |
| `python -m jarvis.voice` | `python -m jarvis.apps.voice` |
| `from jarvis.subsystems.tempo import ...` | `from jarvis.agents.tempo import ...` |
| `from jarvis.subsystems.atlas import AtlasBridge, AtlasOrchestrator` | `from jarvis.agents.atlas import AtlasBridge, AtlasOrchestrator` (via `__init__.py` barrel) |
| `from jarvis.orchestrator import ...` | `from jarvis.core.orchestrator import ...` |
| `from jarvis.classify import ...` | `from jarvis.core.classify import ...` |
| `from jarvis.router import ...` | `from jarvis.core.router import ...` |
| `from jarvis.llm import ...` | `from jarvis.llm.client import ...` |
| `from jarvis.claude_queue import ...` | `from jarvis.llm.queue import ...` |
| `from jarvis.state import add_task, append_inbox` | unchanged (state/__init__.py barrel re-exports) |
| `from jarvis.config import get_settings` | unchanged |
| `from jarvis.contract import AgentResponse` | unchanged |
| `from jarvis.jarvis_agent import JarvisChat` | `from jarvis.agent import JarvisChat` |

`jarvis.config`, `jarvis.contract` stay at the package root — they are referenced everywhere and have no peers to group with. Moving them buys nothing.

### Test imports

Phase 1 keeps `tests/` flat; only the `from jarvis.x` strings change to match new module paths. A find-and-replace script handles this mechanically.

Phase 2 (deferred, optional): mirror `tests/` into `tests/core/`, `tests/agents/tempo/`, etc.

---

## 4. File splits (>800-line rule)

### `jarvis/web/api.py` (1524 lines) → `jarvis/apps/api/`

Split by FastAPI router boundary. Each router owns its routes + the helpers only it uses.

| New file | Contents | Approx lines |
|----------|----------|--------------|
| `app.py` | `make_app()`, lifespan, CORS, error handlers | ~140 |
| `deps.py` | `_Broadcaster`, `_push_inbox_event`, `_push_voice_frame`, registry/orchestrator factories | ~180 |
| `routers/inbox.py` | inbox CRUD + listeners | ~140 |
| `routers/tasks.py` | tasks endpoints | ~120 |
| `routers/confirmations.py` | pending/approve/reject | ~130 |
| `routers/chat.py` | `/api/jarvis/chat` SSE + turns | ~250 |
| `routers/atlas.py` | atlas snapshot, pipeline, cost merge (`_atlas_snapshot_data`, `_fetch_atlas_cost_rollup`, `_merge_cost_rollups`) | ~280 |
| `routers/briefing.py` | morning brief + search | ~90 |
| `routers/preferences.py` | preferences GET/PUT + `_validate_preferences_payload` | ~80 |
| `routers/ws.py` | websocket endpoints (`/ws/inbox`, `/ws/voice`) | ~110 |

### `jarvis/subsystems/atlas.py` (1003 lines) → `jarvis/agents/atlas/`

| New file | Contents | Approx lines |
|----------|----------|--------------|
| `bridge.py` | `AtlasUnavailableError`, `AtlasBridge` (HTTP client, auth, retries, SSE) | ~250 |
| `pipeline.py` | `_parse_pipeline_envelope`, trace-event helpers | ~70 |
| `orchestrator.py` | `AtlasOrchestrator` (the agent surface) | ~600 |
| `mocks.py` | `_mock_portfolio`, `_mock_positions`, `_mock_pnl`, `_mock_market_scan`, `_mock_strategies` | ~70 |

`jarvis/agents/atlas/__init__.py` re-exports the public names so importers don't notice.

### Files near the line (no split now, watch in Phase 2)

`jarvis/subsystems/scholar.py` (788), `jarvis/jarvis_agent.py` (779), `jarvis/daemon/routines.py` (540). All under 800; leave them.

---

## 5. `pyproject.toml` changes

```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["jarvis*"]

# Update per-file-ignores to new paths and drop stale entries
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["ARG", "B", "E402", "SIM117", "I001", "E741"]
"src/jarvis/apps/api/routers/*.py" = ["ARG001", "N806", "B008"]   # was jarvis/web/api.py
"src/jarvis/apps/sentinel/routines.py" = ["ARG001"]               # was daemon/routines.py
"src/jarvis/apps/sentinel/scheduler.py" = ["ARG001", "SIM105"]    # was daemon/sentinel.py
"src/jarvis/apps/voice/wake.py" = ["SIM110"]
"src/jarvis/apps/voice/stt.py" = ["ARG002"]
"src/jarvis/core/supervisor.py" = ["N818"]
# DROPPED: jarvis/subsystems/ledger.py (file does not exist)
# DROPPED: jarvis/web/webhooks.py (file does not exist)
```

`pytest`, `coverage`, ruff `select` rules unchanged.

---

## 6. Service launchers + CI

### `scripts/launchers/` (auto-regenerated by `install-services.ps1`)

| File | Old command | New command |
|------|------------|-------------|
| `jarvis-api.bat` | `python -m uvicorn jarvis.web.api:app --host 0.0.0.0 --port 8765` | `python -m uvicorn jarvis.apps.api.app:app --host 0.0.0.0 --port 8765` |
| `jarvis-sentinel.bat` | `python -m jarvis.daemon.sentinel` | `python -m jarvis.apps.sentinel` |
| `jarvis-voice.bat` | `python -m jarvis.voice` | `python -m jarvis.apps.voice` |
| `jarvis-dashboard.bat` | `cd web && pnpm dev` | unchanged |

### `scripts/install-services.ps1`

Same module-path edits in the `$tasks` array. Operator runs `pwsh -File scripts/install-services.ps1` once after merge to re-register.

### `scripts/` reorganization

Light grouping — pure cleanup, no behavior change:

```
scripts/
├── install-services.ps1
├── launchers/                     # unchanged (file contents updated)
├── ops/                           # NEW
│   ├── restart-jarvis.ps1
│   ├── stop-jarvis.ps1
│   └── ship-bug-check.ps1
├── tunnel/                        # NEW
│   ├── phone-setup.ps1
│   └── tailscale-serve.ps1
└── dev/                           # NEW
    ├── test_daily_forge.py
    └── voice_sample.py
```

### `.github/workflows/ci.yml`

```yaml
- name: Lint with ruff
  run: ruff check src tests              # was: ruff check jarvis tests

- name: Run tests with coverage
  run: pytest --cov=jarvis --cov-fail-under=70 --cov-report=xml --cov-report=term
```

`--cov=jarvis` still works after editable install picks up `src/jarvis/`. No change needed there.

### `.claude/settings.json`

- `JARVIS_PROJECT_ROOT` env var — unchanged (still `C:\Users\jyot2\jarvis`)
- `Bash(python -m jarvis.*)` permission — still matches all new module paths
- `Bash(uvicorn *)` — unchanged
- Hook command `python .claude/hooks/session_start_inbox.py` — hook does not import `jarvis`, so it survives untouched

### `.claude/hooks/session_start_inbox.py`

No change. It reads `state/inbox.jsonl` via `Path` only; no `jarvis` imports.

---

## 7. Commit staging

Each commit leaves the test suite green. Operator can bisect cleanly.

| # | Subject | Touches |
|---|---------|---------|
| **C1** | `refactor: scaffold src/ layout + empty subpackages` | Create `src/jarvis/{core,llm,state,agents,apps,...}/__init__.py`, update `pyproject.toml` for `where=["src"]`, **move existing `jarvis/`** under `src/` via `git mv` (one big rename, zero import changes). Run tests — should still pass since import paths are unchanged. |
| **C2** | `refactor: split web/api.py into routers` | Inside `src/jarvis/web/` for now — split the 1524-line file into routers. All imports stay `jarvis.web.api:app`. |
| **C3** | `refactor: split subsystems/atlas.py into modules` | Inside `src/jarvis/subsystems/atlas/` package — split, keep public `__init__.py` re-exports. |
| **C4** | `refactor: group subsystems → agents/{tempo,scholar,lens,forge,atlas}` | `git mv` per-agent. Update only intra-agent imports. Top-level still `from jarvis.subsystems.tempo` — leave a temporary alias module that re-exports from the new home. |
| **C5** | `refactor: move daemon/voice/web under apps/` | `git mv jarvis/web → jarvis/apps/api`, `daemon → apps/sentinel`, `voice → apps/voice`. Update `__main__.py` paths. |
| **C6** | `refactor: regroup loose root files into core/, llm/, state/` | `git mv` orchestrator, router, classify, authority, supervisor, verify, triggers → `core/`. llm, claude_queue, model_router, cost → `llm/`. memory, memory_index, exports, briefing, chat_turns + split state.py → `state/`. Add barrel `__init__.py` for `state` to re-export old surface. |
| **C7** | `refactor: rewrite imports across codebase and tests` | Mechanical sed pass: `from jarvis.subsystems.X → from jarvis.agents.X`, `from jarvis.orchestrator → from jarvis.core.orchestrator`, etc. Remove the temporary subsystems alias module. Run full suite. |
| **C8** | `chore: update launchers, install-services.ps1, CI lint path` | `.bat` files, `install-services.ps1`, `ci.yml` ruff path. |
| **C9** | `chore: scripts/ subgrouping (ops/, tunnel/, dev/)` | `git mv` ten scripts. No behavior change. |
| **C10** | `docs: refresh README diagram + add ARCHITECTURE.md` | Update repo tree in README; add a short architecture doc that names the new layers. |

Roughly 10 commits. C7 is the largest; everything else is incremental.

---

## 8. Risk & rollback

| Risk | Mitigation |
|------|------------|
| Sentinel running locally breaks mid-merge | Reorg lands on `refactor/reorg`; main keeps running. Sentinel only switches on `install-services.ps1` re-run after merge. |
| Editable install drift (`pip install -e .` needs re-running) | Document in PR description; CI fresh-installs from `pyproject.toml` so it self-validates. |
| Tests pass but a non-tested import path breaks at runtime (e.g. a string-referenced module in `claude_queue`, FastAPI's `"jarvis.web.api:app"` string) | Grep for `jarvis.web`, `jarvis.daemon`, `jarvis.subsystems`, `jarvis.voice`, `jarvis.orchestrator`, etc. as **strings** (not just imports) — `.bat`, `.ps1`, `.json`, `.md`, `.yml`, `Dockerfile`, `__main__.py` blocks. Done as part of C8 review. |
| `state/__init__.py` barrel hides circular imports | Barrel only re-exports leaf modules; no internal cross-import. If a cycle appears, drop the barrel and rewrite test imports. |
| `git mv` history hard to follow if rename is too aggressive | Each `git mv` happens in a small commit (C1, C4, C5, C6) — `git log --follow` works file-by-file. |
| Hooks in `.claude/settings.json` PostToolUse run `ruff check --fix --quiet jarvis/ tests/` | Update to `ruff check --fix --quiet src/ tests/` in C8. |

Full rollback: `git checkout main` — `refactor/reorg` is orphan until merged.

---

## 9. What this proposal does NOT do

Out of scope intentionally — call out separately if you want any of these:

- **No behavior changes.** Every function returns the same thing. Every endpoint serves the same payload.
- **No new dependencies.**
- **No test reorg.** `tests/` stays flat in Phase 1; mirroring is Phase 2.
- **No Next.js (`web/`) changes.** Frontend is a separate sub-project with its own conventions.
- **No `state/` schema migration.** Runtime files keep their current shape and location.
- **No agent-contract enforcement in code.** The contract dict in CLAUDE.md is currently informal; codifying it as a Pydantic model is a follow-up.
- **No removal of the `jarvis-*` dev sub-agents** in `.claude/agents/`. Their internal references to `jarvis/subsystems/*` and `jarvis/web/*` get a one-pass rewrite in C8.
- **No CHANGELOG or version bump.** This is internal hygiene. If you want a `0.2.0` cut on merge, say so.

---

## 10. Approval checklist

Please confirm or amend any of these before I start:

1. **Layout** — `src/jarvis/{core,llm,state,agents,apps,tools,personas}` as drawn in §3. ☐
2. **Atlas split** — `bridge.py + pipeline.py + orchestrator.py + mocks.py` under `agents/atlas/`. ☐
3. **API split** — 9 routers as listed in §4. ☐
4. **Module renames OK** — `jarvis_agent.py → agent.py`, `daemon/sentinel.py → apps/sentinel/scheduler.py`, `llm.py → llm/client.py`, `claude_queue.py → llm/queue.py`. ☐
5. **`state/__init__.py` back-compat barrel** stays (keeps test imports stable). Phase 2 removes it. ☐
6. **Scripts subgrouping** (`ops/`, `tunnel/`, `dev/`) as in §6. ☐
7. **Commit stage count** — ~10 commits, single PR. Or do you want 2 PRs (one for moves, one for splits)? ☐
8. **Branch name** — `refactor/reorg`. ☐

Reply with corrections or `lgtm proceed` and I'll start with commit C1.
