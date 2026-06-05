# Hermes-native Jarvis quickstart

This is the practical operator guide for the hybrid Jarvis → Hermes migration.

## 1. Mental model

Jarvis is now being split into three layers:

1. Manifest layer
   - Source of truth: `docs/hermes/agent-manifest.yaml`
   - Describes the crew: names, roles, personalities, tools, safety gates, and dashboard widgets.

2. Backend bridge
   - Code: `jarvis/hermes/manifest.py`
   - API: `GET /api/hermes/agents`
   - Turns the manifest into JSON the dashboard can consume.

3. Mission Control dashboard
   - Main HUD: `web/src/components/hud/HudMissionControl.tsx`
   - Fetches `/api/hermes/agents` first.
   - Falls back to legacy `/api/agents` if the Hermes endpoint is unavailable.

## 2. The crew

- Jarvis: orchestrator and final-response coordinator.
- Tempo: mail, calendar, tasks, daily rhythm.
- Scholar: academics, study plans, course documents.
- Lens: research, monitoring, news, evidence synthesis.
- Forge: code work, repo inspection, tests, PR/review workflows.
- Atlas: trading bridge, paper mode by default, confirmation-gated.
- Sentinel: cron/background watcher, health, alerts.
- Me: operator approvals and final authority.

## 3. Start the backend

From repo root:

```bash
cd /c/Users/jyot2/jarvis
```

On this Windows setup, unset `PYTHONHOME` when using Python/uv:

```bash
env -u PYTHONHOME uv run uvicorn jarvis.apps.api.app:make_app --factory --host 127.0.0.1 --port 8765
```

If you use an API token, set it before startup:

```bash
export JARVIS_API_TOKEN="your-token"
```

Then test the Hermes endpoint:

```bash
curl http://127.0.0.1:8765/api/hermes/agents
```

With a token, replace `example-value` with the value you exported:

```bash
curl -H 'Authorization: Bearer ***' http://127.0.0.1:8765/api/hermes/agents
```

You can also inspect the approval gate contract:

```bash
curl http://127.0.0.1:8765/api/hermes/approval-policy
curl 'http://127.0.0.1:8765/api/hermes/approvals?status=pending'
```

## 4. Start the dashboard

In another terminal:

```bash
cd /c/Users/jyot2/jarvis/web
export NEXT_PUBLIC_JARVIS_API="http://127.0.0.1:8765"
pnpm dev
```

Open the URL printed by Next.js, usually:

```text
http://localhost:3000
```

Mission Control should show the Hermes crew cards across the top.

## 5. Change an agent

Edit:

```text
docs/hermes/agent-manifest.yaml
```

Common edits:

- Change the card label: `name`
- Change the mission description: `role`
- Change behavior/voice: `personality`
- Change dashboard bullets: `dashboard.primary_widgets`
- Add/remove safe capabilities: `capabilities`
- Add confirmation requirements: `confirmation_gates`

Then restart the backend or refresh the endpoint, depending on how the server is running.

## 6. Safety rules

Keep these confirmation-gated:

- Tempo sending mail.
- Tempo changing calendar events.
- Forge pushing code, opening PRs, or merging PRs.
- Atlas triggering strategy runs, placing orders, or switching live mode.
- Sentinel stopping/restarting background services.
- Deleting memory or state.

Atlas remains paper-mode by default in the manifest.

The current Hermes approval API is:

- `GET /api/hermes/approval-policy` — show which actions require confirmation.
- `GET /api/hermes/approvals?status=pending` — list pending approvals in dashboard shape.
- `POST /api/hermes/approvals/{id}/approve` — approve and replay the original gated request.
- `POST /api/hermes/approvals/{id}/reject` — reject without replaying anything.

Use approve only when you understand the payload. Reject is always safe.

## 7. Run checks

Backend targeted checks:

```bash
cd /c/Users/jyot2/jarvis
env -u PYTHONHOME uv run pytest tests/test_hermes_manifest.py tests/test_hermes_api.py tests/test_hermes_approvals.py tests/test_api_bearer_auth.py -q --tb=short
env -u PYTHONHOME uv run ruff check jarvis/hermes tests/test_hermes_manifest.py tests/test_hermes_api.py tests/test_hermes_approvals.py
```

Frontend checks:

```bash
cd /c/Users/jyot2/jarvis/web
pnpm tsc --noEmit
pnpm lint
```

## 8. Current migration status

Done:

- Manifest-backed crew definition.
- Read-only backend endpoint.
- Approval policy adapter and Hermes approval queue endpoints.
- Dashboard agent-row integration.
- Targeted backend and frontend verification.

Next recommended steps:

1. Add a real Mission Control page section for pending approvals.
2. Add Sentinel cron/job state endpoint.
3. Add run/event stream endpoint for Hermes delegate_task/cron results.
4. Generate Hermes skills/profiles from `agent-manifest.yaml`.
5. Wire real Hermes delegation into Forge/Sentinel workflows.
