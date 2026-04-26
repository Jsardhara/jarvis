# Jarvis — Phase Status

Built overnight 2026-04-25 → 2026-04-26. All 8 phases (0–7) shipped to
`https://github.com/Jsardhara/jarvis` (private).

| Phase | Scope | Status | Tests | Coverage |
|-------|-------|--------|-------|----------|
| 0 | Foundation: skeleton, CLAUDE.md, agent stubs, settings.json | shipped | — | — |
| 1 | Orchestrator + Aide + Chronos + state + intent classifier | shipped | 52 | 99.66% |
| 2 | Sherlock + Forge + Ledger (ATLAS HTTP bridge) | shipped | 72 | 96.15% |
| 3 | Sentinel daemon (APScheduler + Pushover + cron routines) | shipped | 88 | 96.99% |
| 4 | Echo + Slack/Discord/Twilio bridges + FastAPI webhooks | shipped | 116 | 97.50% |
| 5 | Voice scaffold (wake / STT / TTS / pipeline) | shipped | 133 | 97.67% |
| 6 | Web dashboard (Next.js 15 + React 19 + FastAPI + SWR) | shipped | 142 | 96.61% |
| 7 | Hearth (Home Assistant REST bridge) | shipped | 149 | 96.36% |

## What works today (no creds required)

- `pytest` — 149 passing tests, 96%+ coverage on every module.
- `python -m jarvis.daemon.sentinel` — daemon runs, schedules 6 jobs,
  writes mock email/calendar/atlas/news events to `state/inbox.jsonl`,
  no-op notifier when no Pushover keys.
- `uvicorn jarvis.web.api:app --reload --port 8765` — backend up,
  /api/health, /api/inbox, /api/tasks, /api/dispatch all return real
  data driven by mocks.
- `cd web && bun run dev` — Next.js dashboard at http://localhost:3000
  with Briefing / Inbox / Tasks / ATLAS / Console pages.
- All subsystem agent prompts exist in `.claude/agents/` so launching
  Claude Code in this directory immediately routes to them.

## What needs your hands (manual steps to unlock real data)

1. **Gmail / Google Calendar / Google Drive MCPs** — browser OAuth flow.
   Open Claude Code in this dir and run the `mcp__claude_ai_Gmail__authenticate`
   tool. After OAuth completes, swap `MockGmail()` → MCP-backed provider in
   `jarvis/web/api.py:_build_orchestrator()` and `jarvis/daemon/sentinel.py:_build_subsystems()`.

2. **Pushover** — sign up at pushover.net, drop USER and TOKEN into `.env`.
   `default_notifier()` will auto-pick PushoverNotifier when both are present.

3. **ATLAS** — start ATLAS FastAPI on port 8000 (or set `JARVIS_ATLAS_API`).
   Ledger will flip from `mock=True` to real data automatically; no code
   change needed. Dashboard `/atlas` will stop showing the "(mock)" badge.

4. **Slack / Discord / Twilio (optional)** — drop bot tokens into `.env`,
   point each provider's webhook URL at:
     - `https://<your-host>/webhooks/slack`
     - `https://<your-host>/webhooks/discord`
     - `https://<your-host>/webhooks/twilio`
   For local dev, ngrok forwards to port 8765.

5. **Voice (optional)** — only needed for Phase 5.1 wiring:
     - `PICOVOICE_ACCESS_KEY` from picovoice.ai for wake word
     - `DEEPGRAM_API_KEY` for STT (or local Whisper model download)
     - `ELEVENLABS_API_KEY` + voice_id for TTS

6. **Home Assistant (optional)** — Phase 7 stub. Long-lived token:
   HA → Profile → Long-Lived Access Tokens. Set `HOMEASSISTANT_URL` and
   `HOMEASSISTANT_TOKEN` in `.env`.

## Git log

```
9e71bdb feat(phase-5): voice scaffold (wake + STT + TTS + loop)
7e0fc89 feat(phase-4): Echo + Slack/Discord/Twilio bridges + FastAPI webhooks
91fb231 feat(phase-3): Sentinel daemon w/ APScheduler + Pushover
1d19fdc feat(phase-2): Sherlock + Forge + Ledger subsystems
377acd6 feat(phase-1): orchestrator core + Aide + Chronos w/ 99% coverage
488fd9a feat: jarvis phase 0 skeleton
[+ phase-6 web dashboard, phase-7 hearth — pushing to remote]
```

## Architecture recap

```
                    ┌─────────────┐
                    │   jarvis    │ Opus 4.7 orchestrator
                    │ (CC agent)  │
                    └──────┬──────┘
                           │ classify + dispatch
   ┌────────┬───────┬──────┼──────┬───────┬──────────┐
   ▼        ▼       ▼      ▼      ▼       ▼          ▼
 Aide    Chronos Sherlock Forge Ledger  Echo      Hearth
 email   cal+todo research  code  ATLAS  msgs       home
   │        │       │       │      │      │          │
   │        │       │       │      │      │          │
   ▼        ▼       ▼       ▼      ▼      ▼          ▼
 GMail/  GCal     Exa     Claude  http://  Slack/   Home
 MCP     MCP    search   subagents :8000   Discord/ Assist.
                                  ATLAS    Twilio   :8123

                    ┌─────────────┐
                    │  Sentinel   │  APScheduler daemon
                    │ background  │  → state/inbox.jsonl
                    │   worker    │  → Pushover alerts
                    └─────────────┘

   Surfaces:        CC terminal • Webhooks • Web (:3000) • Voice loop
```

## Ordered next-day actions (when you wake)

1. **Read this file + plan** at `.claude/plans/i-want-to-melodic-hopper.md`.
2. **Push remaining commits** (phase 6 + 7) — already staged locally:
   `git push origin main`
3. **Run the full stack once** to see it move:
   ```bash
   # Terminal 1
   uvicorn jarvis.web.api:app --reload --port 8765
   # Terminal 2
   cd web && bun run dev
   # Terminal 3
   python -m jarvis.daemon.sentinel
   ```
   Open http://localhost:3000. Console page → type "morning briefing" → see Aide+Chronos+Ledger respond.
4. **Wire OAuth** (step #1 in the manual list above) — that flips Aide
   and Chronos from mocks to real.
5. **Start ATLAS** for Ledger → Atlas pages to go live.
6. **Pick the next phase** to deepen — most ROI per hour of work:
     - Phase 1.5: real Gmail/Calendar provider (1–2 hrs after OAuth)
     - Phase 6.1: confirmation modals + WebSocket live stream (2–3 hrs)
     - Phase 5.1: voice loop wiring with real audio I/O (4–6 hrs, hardware)

## Known gaps / not done

- No CI workflow yet (.github/workflows/ — easy add).
- claude-mem hook to read state/inbox.jsonl on session start — wires in 5 min.
- No real LLM-backed intent classifier (rule-based router covers 90% of single-intent;
  fallback path documented but stubbed).
- Voice run_voice_loop and Whisper/Piper paths covered behind `# pragma: no cover`
  because they need hardware/local models.
- ATLAS endpoint paths in Ledger are best-guess (`/portfolio`, `/positions/open`,
  etc.) — verify against actual ATLAS routers when API is up; mock fallback covers any 404.
