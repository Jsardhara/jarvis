# Jarvis Web

Next.js 15 + React 19 dashboard. Talks to FastAPI backend at `http://localhost:8765`.

## Run

```bash
# Backend (one terminal)
cd ../
uvicorn jarvis.web.api:app --reload --port 8765

# Frontend (another terminal)
cd web/
bun install   # or: npm install
bun run dev
```

Open http://localhost:3000.

## Pages

- `/` — Briefing (alerts, open tasks, recent agent activity)
- `/inbox` — daemon event queue (auto-refresh 15s)
- `/tasks` — todo CRUD
- `/atlas` — portfolio + holdings (mock until ATLAS API up)
- `/console` — free-form dispatch to orchestrator, see per-agent envelopes

## Env

- `JARVIS_API_URL` — backend URL (default `http://localhost:8765`). Set in `.env.local`.

## Phase 6.1 todo

- WebSocket live agent activity stream (backend already emits to `/ws`)
- Confirmation modal flow for `needs_confirm` responses
- Auth (single-user local JWT)
- Dark/light toggle (currently dark-only)
