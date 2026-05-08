# Jarvis

[![tests](https://img.shields.io/badge/tests-149%20passing-brightgreen)](#)
[![coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](#)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#)
[![voice](https://img.shields.io/badge/voice-live-blue)](#)

Personal-assistant multi-agent system on Claude Code. Single operator. Free-tier first.

```
voice ──┐
chat  ──┼──► jarvis (orchestrator) ──► tempo · scholar · lens · forge · atlas
api   ──┘                                            │
                                              sentinel (background daemon)
```

---

## Status

| Layer | State |
|-------|-------|
| Orchestrator + intent router | live |
| Subsystems (5 + sentinel) | live |
| Sentinel daemon | live, 14 cron routines |
| Voice (wake → STT → router → TTS) | live, free stack, ~$0.001/query |
| Web dashboard | live, Next.js 15 + React 19 |
| ATLAS bridge (Alpaca MCP) | live, paper mode |
| UI/UX redesign | queued |

**Tests:** 149 passing, ~96% coverage. `pytest --cov=jarvis --cov-fail-under=80`.

---

## Recent progress

| Date | Shipped |
|------|---------|
| 2026-05-08 | Repo condense — drop Outlook backend, ATLAS dev agents, gan-harness, web demo seeds. README rewrite. -4,959 lines. |
| 2026-05-08 | Voice phase 5.2 — Andrew +15%, cheap-handler 4-tier router, chime + 6 fillers, cached fact sheet. ~$0.001/query. |
| 2026-05-08 | Voice phase 5.1 — wake → STT → orchestrator → TTS wired on free stack. Andrew Multilingual + faster-whisper + openwakeword. |
| 2026-05-08 | Autostart — 5 Windows launchers in Startup folder (api, sentinel, voice, dashboard, atlas). |
| 2026-05-07 | ATLAS pivot — Kraken executor ripped out, Alpaca MCP sole executor. Migration `002_drop_kraken_legacy.sql`. Freqtrade removed. |
| 2026-05-07 | API surface — `api/routers/control.py` + `pipeline.py` with bearer auth + idempotency + fakes harness. |
| 2026-05-07 | Jarvis ↔ ATLAS — `subsystems/atlas.py`, `daemon/atlas_decision.py`, sentinel `atlas_health` job. |
| 2026-04-26 | Phases 0–7 shipped overnight — orchestrator, 5 subsystems, sentinel, voice scaffold, web dashboard, home automation bridge. |

---

## Agents

| Agent | Role | Model |
|-------|------|-------|
| **jarvis** | Orchestrator — routes intent | Opus 4.7 |
| **tempo** | Mail (Gmail+Drexel) + calendar (iCloud) + tasks | Sonnet 4.6 |
| **scholar** | Academics + study planning | Sonnet 4.6 |
| **lens** | Web research + monitoring | Sonnet 4.6 |
| **forge** | Code-work delegation | Opus 4.7 |
| **atlas** | Trading orchestrator (HTTP client to ATLAS project) | Opus 4.7 |
| **sentinel** | Background watcher daemon | Haiku 4.5 |

Confirmation gates: send-mail · cal mutation · PR push · ATLAS strategy trigger · daemon stop.

---

## Voice (Phase 5.2)

Free stack, all local except TTS:

| Piece | Tool |
|-------|------|
| Wake word | openwakeword `hey_jarvis_v0.1.tflite` |
| VAD | energy-based RMS (no webrtcvad — Py 3.14 wheel gap) |
| STT | faster-whisper `base.en` |
| TTS | edge-tts (`en-US-AndrewMultilingualNeural`, +15%) |
| Router | 4-tier: pattern → Haiku → Sonnet → Orchestrator |
| Fact sheet | `state/voice_context.json`, refreshed every 5 min |

---

## ATLAS bridge

Atlas (the agent here) is a thin HTTP client over the ATLAS project at `C:\Users\jyot2\atlas\`. **ATLAS source is read-only from this repo** — PR there, never edit from here. Executor: Alpaca MCP only (Kraken removed 2026-05-07).

---

## Quickstart

### Install
```powershell
pip install -e ".[dev,voice,web,daemon]"
```

### Run everything
```powershell
# Autostart launchers (already in Startup folder):
scripts\launchers\jarvis-api.bat        # FastAPI
scripts\launchers\jarvis-sentinel.bat   # daemon
scripts\launchers\jarvis-voice.bat      # wake → STT → TTS
scripts\launchers\jarvis-dashboard.bat  # Next.js
```

### Interactive chat
```powershell
cd C:\Users\jyot2\jarvis
claude
> what's on my plate today
```

### Tests
```powershell
pytest --cov=jarvis --cov-fail-under=80
```

---

## Layout

```
jarvis/
├── .claude/
│   ├── CLAUDE.md          # project rules + persona + routing
│   ├── settings.json      # MCP enable list, hooks
│   └── agents/            # 5 runtime + dev-side jarvis-* agents
├── jarvis/
│   ├── orchestrator.py    # intent router
│   ├── subsystems/        # tempo, scholar, lens, forge, atlas, providers
│   ├── voice/             # wake, stt, tts, cheap_handler, fillers
│   ├── daemon/            # sentinel, routines, atlas_decision
│   ├── personas/          # jarvis_soul.md (full + lite)
│   └── web/               # FastAPI api.py + atlas_proxy.py
├── web/                   # Next.js 15 dashboard (Mission Control)
├── scripts/launchers/     # Windows .bat autostart shims
├── docs/
│   ├── setup/phone.md     # phone PWA + Tailscale + ntfy
│   └── design/            # imports + dashboard spec
├── tests/                 # pytest, 149 tests
└── state/                 # runtime (gitignored): inbox.jsonl, logs, db
```

---

## Conventions

- Python 3.11+, type hints required, ruff lint, pytest 80% min
- Files <800 lines, functions <50 lines
- Immutable: return new copies, no in-place mutation
- Secrets via env only — `.env.example` is the contract
- All agents return the contract envelope: `{agent, intent, action, result, follow_ups, confidence, needs_confirm}`

---

## Don't

- Don't edit ATLAS source from here — PR in atlas repo
- Don't reintroduce removed agents (Aide / Chronos / Sherlock / Ledger / Echo / Hearth / Outlook backend)
- Don't bypass confirmation gates
- Don't commit runtime state — `state/` is gitignored, `web/data/*.json` is seed-only

---

## Plan ahead

- UI/UX dashboard redesign (next session)
- Live-trade flip docs (deferred until operator signals real-money go)
- `web/api.py` split (currently 1501 lines, exceeds size limit)
