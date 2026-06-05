# Hermes Multi-Agent Migration Plan

> For Hermes: use subagent-driven-development to implement this plan task-by-task when code changes begin.

Goal: move Jarvis from a Claude Code-centered personal assistant into a Hermes-native multi-agent system with distinct agent personalities, shared state, confirmation gates, Sentinel background work, and a dashboard.

Architecture: hybrid migration. Keep existing Jarvis domain modules and dashboard, introduce Hermes-native orchestration gradually. Avoid destructive rewrites. Protect existing user changes.

Tech stack: Hermes Agent, Python 3.11+, FastAPI, Next.js 15/React 19, JSONL compatibility state, Hermes memory/sessions/cron/delegation/skills.

---

## Phase 0: Safety and baseline

### Task 0.1: Capture repository baseline

Objective: protect existing work before migration.

Files:
- Read: `git status`
- Read: `README.md`
- Read: `ARCHITECTURE.md` if present
- Read: `jarvis/agent.py`
- Read: `jarvis/agents/registry.py`
- Read: `jarvis/apps/api/app.py`

Steps:
1. Run `git status --short`.
2. Do not overwrite existing modified files.
3. Create a migration branch only if the operator approves branch creation.
4. Record baseline notes in `docs/hermes/baseline.md`.

Verification:
- No user changes overwritten.
- New docs only unless implementation phase begins.

### Task 0.2: Add Hermes crew manifest

Objective: create one machine-readable source for agent identities and policies.

Files:
- Create: `docs/hermes/agent-manifest.yaml`

Steps:
1. Define jarvis, tempo, scholar, lens, forge, atlas, sentinel, me.
2. Include role, personality, capabilities, default model tier, risk gates, dashboard color/icon.
3. Keep it readable by both humans and future codegen.

Verification:
- Manifest matches `docs/hermes/agent-personalities.md`.

---

## Phase 1: Hermes adapter layer

### Task 1.1: Create Hermes state adapter design

Objective: define how Hermes events map into Jarvis dashboard state.

Files:
- Create: `jarvis/hermes/__init__.py`
- Create: `jarvis/hermes/events.py`
- Create: `tests/test_hermes_events.py`

Implementation shape:
- `HermesEvent` pydantic model.
- `ApprovalRequest` pydantic model.
- helpers to convert AgentResponse/TraceEvent into dashboard events.

Verification:
- Unit tests cover agent start, done, error, approval-created, cron-done.

### Task 1.2: Add manifest loader

Objective: make agent manifest consumable by API/dashboard.

Files:
- Create: `jarvis/hermes/manifest.py`
- Test: `tests/test_hermes_manifest.py`

Implementation shape:
- Load `docs/hermes/agent-manifest.yaml`.
- Validate required agent IDs.
- Return stable agent card data.

Verification:
- Test fails if any locked agent is missing.

### Task 1.3: Add read-only Hermes dashboard API routes

Objective: expose normalized Hermes-ready data without replacing current API.

Files:
- Modify: `jarvis/apps/api/app.py` or split router if already available.
- Create if splitting: `jarvis/apps/api/hermes_routes.py`
- Test: `tests/test_hermes_api.py`

Endpoints:
- `GET /api/hermes/agents`
- `GET /api/hermes/activity`
- `GET /api/hermes/approvals`
- `GET /api/hermes/inbox`

Verification:
- Existing API tests still pass.
- New endpoints work with mock state.

---

## Phase 2: Hermes-native orchestration

### Task 2.1: Convert Jarvis persona into Hermes skill/profile spec

Objective: make Jarvis identity portable into Hermes.

Files:
- Create: `docs/hermes/profiles/jarvis.md`
- Later optional: install as Hermes skill after operator approval.

Content:
- Chief-of-staff persona.
- Routing policy.
- Approval gates.
- Agent contract.
- Dashboard event expectations.

Verification:
- Persona references the locked agent set and does not reintroduce removed agents.

### Task 2.2: Convert agents into Hermes skill specs

Objective: define each agent as a Hermes-loadable skill/personality.

Files:
- Create: `docs/hermes/profiles/tempo.md`
- Create: `docs/hermes/profiles/scholar.md`
- Create: `docs/hermes/profiles/lens.md`
- Create: `docs/hermes/profiles/forge.md`
- Create: `docs/hermes/profiles/atlas.md`
- Create: `docs/hermes/profiles/sentinel.md`

Verification:
- Each profile has domain, personality, tools, risk policy, dashboard payloads.

### Task 2.3: Route Forge through Hermes delegation

Objective: make Forge use Hermes subagents for code work.

Files:
- Modify: `jarvis/agents/forge/agent.py`
- Modify: `jarvis/agents/forge/runner.py`
- Test: `tests/test_forge_hermes_runner.py`

Behavior:
- Use Hermes `delegate_task` equivalent when running inside Hermes.
- Preserve current fallback runner outside Hermes.
- Emit spec-review and quality-review events.

Verification:
- Mock runner tests pass.
- No remote push without confirmation.

---

## Phase 3: Sentinel on Hermes cron

### Task 3.1: Inventory Sentinel routines

Objective: map current daemon jobs to Hermes cron jobs.

Files:
- Read: `jarvis/apps/sentinel/routines.py`
- Read: `jarvis/apps/sentinel/scheduler.py`
- Create: `docs/hermes/sentinel-cron-map.md`

Verification:
- Every existing routine is classified as script-only, agent-needed, or retired.

### Task 3.2: Create Hermes cron job definitions

Objective: schedule safe routines through Hermes.

Files:
- Create: `docs/hermes/cron-jobs.yaml`

Rules:
- Prefer `no_agent=True` for health checks and simple thresholds.
- Use full agent runs only for summarization/reasoning.
- Deliver alerts to dashboard/inbox.

Verification:
- No duplicate noisy alerts.
- Stop/restart remains confirmation-gated.

---

## Phase 4: Dashboard integration

### Task 4.1: Add Hermes agent roster to dashboard

Objective: render personality-rich agent cards.

Files:
- Modify: `web/src/lib/api-client.ts`
- Modify or create: `web/src/hooks/useHermesAgents.ts`
- Modify: crew/team pages as appropriate.

Verification:
- Dashboard shows agent role, personality, capabilities, status, color/icon.

### Task 4.2: Add live Hermes activity stream

Objective: show live agent handoffs and trace events.

Files:
- Modify websocket hook or create: `web/src/hooks/useHermesActivity.ts`
- Modify activity/swimlane components.

Verification:
- Agent start/done/error events render live.

### Task 4.3: Add approval cockpit

Objective: make risky agent actions obvious and controllable.

Files:
- Modify: `web/src/app/decisions/page.tsx`
- Add API client calls for approve/reject.

Verification:
- Pending approvals appear at top.
- Approve/reject updates state.
- Atlas financial actions show risk styling.

---

## Phase 5: Voice and gateway

### Task 5.1: Keep Jarvis voice stack, route through Hermes orchestrator

Objective: reuse existing wake/STT/TTS but send final text into Hermes Jarvis.

Files:
- Modify: `jarvis/apps/voice/*` as needed.
- Add adapter module only after dashboard/chat path is stable.

Verification:
- Voice query creates dashboard-visible request_id and trace.

---

## First implementation milestone

The first code milestone should be:

1. Add manifest loader.
2. Add read-only `/api/hermes/agents` endpoint.
3. Show personality-rich agent cards in dashboard.
4. Add event models and tests.
5. Do not modify risky integrations yet.

This creates a visible Hermes-shaped skeleton without breaking the current Jarvis runtime.
