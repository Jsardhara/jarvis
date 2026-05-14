"""FastAPI bridge for the web dashboard.

Exposes orchestrator functionality over HTTP for the Next.js front-end and
streams agent activity over WebSocket. Run alongside webhooks:

    uvicorn jarvis.apps.api.app:app --reload --port 8765
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from fastapi import (
        FastAPI,
        File,
        HTTPException,
        Request,
        UploadFile,
        WebSocket,
        WebSocketDisconnect,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

from jarvis import (
    config,  # noqa: F401  side-effect: load_dotenv() so APPLE_ID/GMAIL_* reach subsystems
)
from jarvis.agents.registry import AgentDescriptor, build_default_registry
from jarvis.contract import AgentLogEntry, Confirmation, InboxEvent, Task, TraceEvent
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm.cost import daily_rollup
from jarvis.state import (
    add_confirmation,
    add_task,
    append_agent_log,
    load_tasks,
    load_watchlist,
    read_agent_log,
    read_confirmations,
    read_inbox,
    read_sentinel_health,
    register_inbox_listener,
    save_watchlist,
    unregister_inbox_listener,
    update_confirmation,
    update_task,
)
from jarvis.state.chat_turns import (
    ChatTurnRecord,
    append_turn,
    read_recent,
    user_id_from_token,
)
from jarvis.state.memory import OperatorPreferences, load_preferences, save_preferences

log = logging.getLogger(__name__)

# ── Module-level inbox push helper (synchronous; tests call it directly) ──

_active_bus: _Broadcaster | None = None
_active_loop: asyncio.AbstractEventLoop | None = None


def _push_inbox_event(event: InboxEvent) -> None:
    """Fire an inbox.event broadcast if a bus is active.

    Schedules the broadcast on the captured app event loop using
    `run_coroutine_threadsafe` so calls from any thread (sentinel,
    test main thread) are safely delivered without relying on the
    py3.10+-deprecated implicit-loop behaviour.
    """
    if _active_bus is None or _active_loop is None:
        return
    payload = {"type": "inbox.event", "event": event.model_dump()}
    if _active_loop.is_running():
        asyncio.run_coroutine_threadsafe(_active_bus.broadcast(payload), _active_loop)


def _push_voice_frame(payload: dict[str, Any]) -> None:
    """Voice loop hook — broadcasts ``voice.state`` / ``voice.level`` frames.

    Called synchronously from any thread (the voice loop runs in its own
    process); schedules onto the API event loop for actual delivery.
    """
    if _active_bus is None or _active_loop is None:
        return
    if _active_loop.is_running():
        asyncio.run_coroutine_threadsafe(_active_bus.broadcast(payload), _active_loop)


def _build_orchestrator(registry: dict[str, AgentDescriptor]) -> Orchestrator:
    o = Orchestrator()
    for name, desc in registry.items():

        async def _handler(req: str, _desc: AgentDescriptor = desc, _name: str = name) -> Any:
            # Prefer a classifier-selected action when the orchestrator has
            # threaded one onto the dispatch envelope; otherwise fall back to
            # the descriptor's free-text default (current behaviour).
            action: str | None = None
            args: dict[str, Any] = {}
            if isinstance(req, dict):
                action = req.get("action")
                args = dict(req.get("args") or {})
                text = str(req.get("text", ""))
            else:
                text = str(req)

            if action and action in _desc.actions:
                return _desc.call(action, args)

            if action:
                log.debug(
                    "orchestrator: action %r unknown for agent %r; "
                    "falling back to call_text",
                    action,
                    _name,
                )
            return _desc.call_text(text)

        o.register(name, _handler)
    return o


class _Broadcaster:
    """Tiny WebSocket fan-out for live agent activity."""

    def __init__(self) -> None:
        self._subs: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subs.append(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._subs:
                self._subs.remove(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload)
        async with self._lock:
            stale = []
            for ws in self._subs:
                try:
                    await ws.send_text(msg)
                except RuntimeError:
                    stale.append(ws)
            for s in stale:
                self._subs.remove(s)


def _summarize_result(result: dict[str, Any]) -> str:
    for key in ("count", "total"):
        if isinstance(result.get(key), int):
            return f"{key}={result[key]}"
    if "portfolio" in result:
        port = result["portfolio"]
        if isinstance(port, dict) and "total_value_usd" in port:
            return f"value=${port['total_value_usd']:.0f}"
    return ""


def _make_event_sink(bus: _Broadcaster) -> Any:
    """Build an EventSink that broadcasts + persists agent_log + auto-confirmations."""

    async def sink(event: TraceEvent) -> None:
        # Broadcast every trace event
        await bus.broadcast({"type": event.type, **event.model_dump()})

        # Persist agent_log on done/error
        if event.type == "agent.done" and event.agent:
            payload = event.payload or {}
            entry = AgentLogEntry(
                ts=event.ts,
                request_id=event.request_id,
                agent=event.agent,
                action=payload.get("action", "?"),
                status="proposed" if payload.get("needs_confirm") else "ok",
                duration_ms=int(payload.get("duration_ms", 0)),
                confidence=float(payload.get("confidence", 1.0)),
                needs_confirm=bool(payload.get("needs_confirm")),
                summary="",
            )
            append_agent_log(entry)
        elif event.type == "agent.error" and event.agent:
            payload = event.payload or {}
            append_agent_log(
                AgentLogEntry(
                    ts=event.ts,
                    request_id=event.request_id,
                    agent=event.agent,
                    action="?",
                    status="error",
                    duration_ms=int(payload.get("duration_ms", 0)),
                    error=str(payload.get("error", "")),
                )
            )

    return sink


def _atlas_snapshot_data(reg: dict[str, AgentDescriptor]) -> dict[str, Any]:
    """Build atlas snapshot payload; returns degraded=True on any failure."""
    ts = datetime.now(UTC).isoformat()
    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return {"portfolio": {}, "pnl": {}, "positions": [], "degraded": True, "ts": ts}
    try:
        portfolio = atlas_desc.call("portfolio").result
        pnl = atlas_desc.call("pnl").result
        positions_resp = atlas_desc.call("positions").result
        if isinstance(positions_resp, list):
            positions = positions_resp
        else:
            positions = positions_resp.get("positions", [])
        # Normalize position shape so frontend has stable keys (id→position_id, side→direction)
        from .atlas_proxy import _normalize_position

        positions = [_normalize_position(p) for p in positions if isinstance(p, dict)]
        degraded = bool(portfolio.get("mock") or pnl.get("mock"))
    except Exception:
        log.warning("atlas snapshot failed — returning degraded mock", exc_info=True)
        return {"portfolio": {}, "pnl": {}, "positions": [], "degraded": True, "ts": ts}
    return {
        "portfolio": portfolio,
        "pnl": pnl,
        "positions": positions,
        "degraded": degraded,
        "ts": ts,
    }


def _fetch_atlas_cost_rollup(
    reg: dict[str, AgentDescriptor], date_str: str
) -> dict[str, Any] | None:
    """Fetch Atlas /api/cost/rollup for date_str; return None on any failure."""
    from jarvis.agents.atlas.agent import AtlasOrchestrator

    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return None
    inst = atlas_desc.instance
    if not isinstance(inst, AtlasOrchestrator):
        return None
    if inst.mode != "live":
        return None
    try:
        return inst.bridge.cost_rollup(date_str)
    except Exception as exc:
        log.debug("atlas cost_rollup fetch failed: %s", exc)
        return None


def _merge_cost_rollups(
    jarvis: dict[str, Any], atlas: dict[str, Any]
) -> dict[str, Any]:
    """Merge Jarvis and Atlas daily_rollup dicts into one flat RawRollup.

    Atlas by_agent values may be objects ``{cost_usd, calls, ...}`` or bare
    floats. Both are normalised to bare floats before union.
    Jarvis entries already use bare floats.
    """
    # Flatten Atlas by_agent: {agent: {cost_usd, ...}} → {agent: float}
    atlas_by_agent_raw: dict[str, Any] = atlas.get("by_agent", {})
    atlas_by_agent: dict[str, float] = {}
    for agent, val in atlas_by_agent_raw.items():
        if isinstance(val, dict):
            atlas_by_agent[agent] = float(val.get("cost_usd", 0.0))
        else:
            atlas_by_agent[agent] = float(val)

    atlas_by_model_raw: dict[str, Any] = atlas.get("by_model", {})
    atlas_by_model: dict[str, float] = {}
    for model, val in atlas_by_model_raw.items():
        if isinstance(val, dict):
            atlas_by_model[model] = float(val.get("cost_usd", 0.0))
        else:
            atlas_by_model[model] = float(val)

    merged_by_agent = dict(jarvis.get("by_agent", {}))
    for agent, cost in atlas_by_agent.items():
        merged_by_agent[agent] = round(merged_by_agent.get(agent, 0.0) + cost, 8)

    merged_by_model = dict(jarvis.get("by_model", {}))
    for model, cost in atlas_by_model.items():
        merged_by_model[model] = round(merged_by_model.get(model, 0.0) + cost, 8)

    total = round(
        float(jarvis.get("total_usd", 0.0)) + float(atlas.get("total_usd", 0.0)), 6
    )
    call_count = int(jarvis.get("call_count", 0)) + int(atlas.get("call_count", 0))

    return {
        "date": jarvis["date"],
        "total_usd": total,
        "by_agent": merged_by_agent,
        "by_model": merged_by_model,
        "call_count": call_count,
    }


def _validate_preferences_payload(payload: dict[str, Any]) -> OperatorPreferences:
    """Parse + validate PUT /api/preferences body; raise HTTPException on bad input."""
    senders_raw = payload.get("important_senders", ())
    lead_raw = payload.get("scholar_lead_time_days", 7)
    risk_raw = payload.get("atlas_risk_tolerance", 0.05)

    if not isinstance(senders_raw, (list, tuple)):
        raise HTTPException(status_code=422, detail="important_senders must be a list")
    if not all(isinstance(s, str) for s in senders_raw):
        raise HTTPException(status_code=422, detail="important_senders items must be strings")
    if not isinstance(lead_raw, int) or isinstance(lead_raw, bool):
        raise HTTPException(status_code=422, detail="scholar_lead_time_days must be an integer")
    if lead_raw < 0:
        raise HTTPException(status_code=422, detail="scholar_lead_time_days must be >= 0")
    try:
        risk = float(risk_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="atlas_risk_tolerance must be a number") from None
    if not (0.0 <= risk <= 1.0):
        raise HTTPException(
            status_code=422, detail="atlas_risk_tolerance must be between 0.0 and 1.0"
        )

    from datetime import UTC, datetime

    return OperatorPreferences(
        important_senders=tuple(senders_raw),
        scholar_lead_time_days=int(lead_raw),
        atlas_risk_tolerance=risk,
        updated_at=datetime.now(UTC).isoformat(),
    )


def make_app(
    orchestrator: Orchestrator | None = None,
    registry: dict[str, AgentDescriptor] | None = None,
) -> FastAPI:
    global _active_bus
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi not installed — pip install jarvis[web]")
    reg = registry or build_default_registry()
    o = orchestrator or _build_orchestrator(reg)
    bus = _Broadcaster()
    _active_bus = bus
    o.set_event_sink(_make_event_sink(bus))

    # Register inbox listener so sentinel-written events reach the WS bus.
    register_inbox_listener(_push_inbox_event)

    # Register voice broadcaster so voice.state / voice.level frames reach
    # the WS bus regardless of whether the voice loop runs in-process.
    from jarvis.apps.voice.voice_state import register_broadcaster as _voice_register
    _voice_register(_push_voice_frame)

    app = FastAPI(title="Jarvis API", version="0.2.0")

    # Bearer auth — required on every non-health route when JARVIS_API_TOKEN is set.
    # Falls open (no auth) when the env var is absent so localhost dev still works.
    # Excludes /api/health for liveness probes, WebSocket upgrades, and CORS preflight.
    import hmac as _hmac
    import os as _auth_os

    _AUTH_TOKEN: str = _auth_os.environ.get("JARVIS_API_TOKEN", "") or _auth_os.environ.get(
        "MC_API_TOKEN", ""
    )

    if _AUTH_TOKEN:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse

        _OPEN_PATHS = {"/api/health", "/openapi.json", "/docs", "/redoc"}

        class _BearerAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
                # Skip preflight (CORS handles it), liveness, and docs.
                if request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
                    return await call_next(request)
                # WebSocket upgrades carry token via query param (browsers can't set headers).
                if request.url.path.startswith("/ws"):
                    qp_token = request.query_params.get("token", "")
                    if qp_token and _hmac.compare_digest(qp_token, _AUTH_TOKEN):
                        return await call_next(request)
                    return JSONResponse(
                        {"error": "unauthorized"}, status_code=401
                    )
                header = request.headers.get("authorization", "")
                if not header.startswith("Bearer "):
                    return JSONResponse(
                        {"error": "missing or malformed Authorization header"},
                        status_code=401,
                    )
                supplied = header.removeprefix("Bearer ").strip()
                if not _hmac.compare_digest(supplied, _AUTH_TOKEN):
                    return JSONResponse(
                        {"error": "invalid token"}, status_code=401
                    )
                return await call_next(request)

        app.add_middleware(_BearerAuthMiddleware)

    # CORS — env-driven so tailnet / LAN origins can be allowed without code changes.
    # JARVIS_CORS_ORIGINS: comma-separated explicit origins (overrides default).
    # JARVIS_CORS_REGEX: regex for tailnet/LAN ranges (e.g. r"https?://.*\.ts\.net(:\d+)?").
    import os as _os
    _origins_env = _os.environ.get("JARVIS_CORS_ORIGINS", "")
    _origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
    _origin_regex = _os.environ.get("JARVIS_CORS_REGEX") or None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_origin_regex=_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.on_event("shutdown")
    async def _cleanup() -> None:
        unregister_inbox_listener(_push_inbox_event)

    # ── Atlas proxy routes (must register before /api/atlas/snapshot so that
    #    specific static paths like /trades/open beat param routes) ────────────
    from .atlas_proxy import register_atlas_proxy

    register_atlas_proxy(app, reg)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "jarvis-api"}

    @app.get("/api/voice/state")
    async def voice_state_route() -> dict[str, Any]:
        """Mission Control reads this on cold start; live updates over WS."""
        from jarvis.apps.voice.voice_state import read_state as _read_voice_state
        return _read_voice_state()

    @app.get("/api/inbox")
    async def inbox(limit: int = 50) -> dict[str, Any]:
        return {"events": [e.model_dump() for e in read_inbox(limit=limit)]}

    @app.get("/api/sentinel/snapshot")
    async def sentinel_snapshot(
        events_limit: int = 80, heartbeat_limit: int = 60
    ) -> dict[str, Any]:
        """Bundle daemon state for the /sentinel dashboard.

        - last_heartbeat: ts of latest sentinel_health.jsonl line
        - jobs: [{name, status}] from latest heartbeat
        - heartbeats: tail of sentinel_health.jsonl (sparkline source)
        - events: tail of state/inbox.jsonl
        """
        heartbeats_raw = read_sentinel_health(limit=heartbeat_limit)
        heartbeats = [hb.model_dump() for hb in heartbeats_raw]
        last_heartbeat = heartbeats[-1]["ts"] if heartbeats else None
        jobs_map: dict[str, str] = heartbeats[-1]["jobs"] if heartbeats else {}
        jobs = [{"name": name, "status": status} for name, status in jobs_map.items()]
        events = [e.model_dump() for e in read_inbox(limit=events_limit)]
        return {
            "last_heartbeat": last_heartbeat,
            "jobs": jobs,
            "heartbeats": heartbeats,
            "events": events,
        }

    @app.get("/api/forge/snapshot")
    async def forge_snapshot(limit: int = 30) -> dict[str, Any]:
        """Bundle Forge state for the /forge dashboard.

        - daily_runs: tail of state/daily_projects.jsonl (autonomous forge picks)
        - next_daily_iso: next 10:00 UTC fire window for the daily_forge job
        """
        from datetime import UTC, datetime, timedelta

        from jarvis.state import read_daily_forge as _read_daily_forge

        daily = _read_daily_forge(limit=limit)
        now = datetime.now(UTC)
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        statuses: dict[str, int] = {}
        for r in daily:
            s = str(r.get("status", "unknown"))
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "daily_runs": daily,
            "next_daily_iso": next_run.isoformat(),
            "status_counts": statuses,
        }

    @app.get("/api/activity")
    async def activity(limit: int = 100) -> dict[str, Any]:
        """Return recent agent_log entries — mirrors /api/inbox shape."""
        return {"entries": [e.model_dump() for e in read_agent_log(limit=limit)]}

    @app.get("/api/atlas/snapshot")
    async def atlas_snapshot() -> dict[str, Any]:
        """Combine portfolio + pnl + positions; set degraded=True when ATLAS is offline."""
        return _atlas_snapshot_data(reg)

    @app.get("/api/dead-letter")
    async def dead_letter(limit: int = 50) -> dict[str, Any]:
        """Recent dead-letter records from the failure supervisor."""
        from jarvis.core.supervisor import read_dead_letter

        records = read_dead_letter(limit=limit)
        return {"data": [r.model_dump() for r in records], "error": None}

    @app.get("/api/tasks")
    async def tasks() -> dict[str, Any]:
        return {"tasks": [t.model_dump() for t in load_tasks()]}

    @app.post("/api/tasks")
    async def create_task(payload: dict[str, Any]) -> dict[str, Any]:
        t = add_task(
            Task(
                title=payload["title"],
                due=payload.get("due"),
                tags=payload.get("tags", []),
            )
        )
        return t.model_dump()

    @app.patch("/api/tasks/{task_id}")
    async def patch_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        updated = update_task(task_id, **payload)
        return updated.model_dump() if updated else {"error": "not_found"}

    @app.post("/api/dispatch")
    async def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
        request = payload.get("request", "")
        result = await o.dispatch(request)
        await bus.broadcast({"type": "dispatch", "request": request, "result": result})

        # Auto-capture confirmations from any agent that needs_confirm.
        # Return the id of the first confirmation created (for the C2 dialog).
        first_conf_id: str | None = None
        for agent_name, resp in result.get("responses", {}).items():
            if resp.get("needs_confirm"):
                conf = add_confirmation(
                    Confirmation(
                        agent=agent_name,
                        intent=resp.get("intent", ""),
                        request=request,
                        args=resp.get("result", {}),
                        summary=", ".join(resp.get("follow_ups", []))[:160],
                    )
                )
                if first_conf_id is None:
                    first_conf_id = conf.id
                await bus.broadcast(
                    {
                        "type": "confirmation.created",
                        **TraceEvent(
                            type="confirmation.created",
                            request_id=result.get("request_id", ""),
                            agent=agent_name,
                            payload={"confirmation": conf.model_dump()},
                        ).model_dump(),
                    }
                )

        # Also handle authority-blocked dispatches (confirmation_required path)
        if result.get("confirmation_required") and first_conf_id is None:
            intent_data = result.get("intent", {})
            agent_name = intent_data.get("primary", "unknown")
            conf = add_confirmation(
                Confirmation(
                    agent=agent_name,
                    intent=intent_data.get("raw_request", request),
                    request=request,
                    summary=result.get("authority_error", "")[:160],
                )
            )
            first_conf_id = conf.id
            await bus.broadcast(
                {
                    "type": "confirmation.created",
                    **TraceEvent(
                        type="confirmation.created",
                        request_id=result.get("request_id", ""),
                        agent=agent_name,
                        payload={"confirmation": conf.model_dump()},
                    ).model_dump(),
                }
            )

        if first_conf_id is not None:
            return {**result, "confirmation_id": first_conf_id}
        return result

    # --- Mission-control: per-agent + confirmations endpoints ---

    @app.get("/api/agents")
    async def list_agents() -> dict[str, Any]:
        return {
            "agents": [
                {
                    "name": d.name,
                    "description": d.description,
                    "mode": d.mode,
                    "actions": list(d.actions.keys()),
                }
                for d in reg.values()
            ]
        }

    @app.post("/api/agents/{name}/dispatch")
    async def agent_dispatch(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        desc = reg.get(name)
        if desc is None:
            raise HTTPException(status_code=404, detail=f"unknown agent '{name}'")
        request_id = uuid4().hex[:12]
        action = payload.get("action")
        text = payload.get("text", "")

        await bus.broadcast(
            {
                "type": "agent.start",
                **TraceEvent(
                    type="agent.start",
                    request_id=request_id,
                    agent=name,
                    payload={"text": text, "action": action},
                ).model_dump(),
            }
        )
        started = time.perf_counter()
        try:
            resp = (
                desc.call(action, payload.get("args", {})) if action else desc.call_text(text)
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            append_agent_log(
                AgentLogEntry(
                    request_id=request_id,
                    agent=name,
                    action=action or "text",
                    status="error",
                    duration_ms=duration,
                    error=str(exc),
                )
            )
            await bus.broadcast(
                {
                    "type": "agent.error",
                    **TraceEvent(
                        type="agent.error",
                        request_id=request_id,
                        agent=name,
                        payload={"error": str(exc), "duration_ms": duration},
                    ).model_dump(),
                }
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        duration = int((time.perf_counter() - started) * 1000)
        append_agent_log(
            AgentLogEntry(
                request_id=request_id,
                agent=name,
                action=resp.action,
                status="proposed" if resp.needs_confirm else "ok",
                duration_ms=duration,
                confidence=resp.confidence,
                needs_confirm=resp.needs_confirm,
            )
        )
        await bus.broadcast(
            {
                "type": "agent.done",
                **TraceEvent(
                    type="agent.done",
                    request_id=request_id,
                    agent=name,
                    payload={
                        "duration_ms": duration,
                        "action": resp.action,
                        "confidence": resp.confidence,
                        "needs_confirm": resp.needs_confirm,
                    },
                ).model_dump(),
            }
        )
        if resp.needs_confirm:
            conf = add_confirmation(
                Confirmation(
                    agent=name,
                    intent=resp.intent,
                    args=resp.result,
                    summary=", ".join(resp.follow_ups)[:160],
                )
            )
            await bus.broadcast(
                {
                    "type": "confirmation.created",
                    **TraceEvent(
                        type="confirmation.created",
                        request_id=request_id,
                        agent=name,
                        payload={"confirmation": conf.model_dump()},
                    ).model_dump(),
                }
            )
        return resp.model_dump()

    @app.get("/api/agents/{name}/history")
    async def agent_history(name: str, limit: int = 50) -> dict[str, Any]:
        if name not in reg:
            raise HTTPException(status_code=404, detail=f"unknown agent '{name}'")
        entries = read_agent_log(agent=name, limit=limit)
        return {"entries": [e.model_dump() for e in entries]}

    @app.get("/api/confirmations")
    async def list_confirmations(
        status: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        items = read_confirmations(status=status, limit=limit)
        return {"confirmations": [c.model_dump() for c in items]}

    @app.post("/api/confirmations/{confirmation_id}/approve")
    async def approve_confirmation(confirmation_id: str) -> dict[str, Any]:
        conf = update_confirmation(confirmation_id, status="approved")
        if conf is None:
            raise HTTPException(status_code=404, detail="confirmation not found")

        # Replay the original request with confirmed=True. The orchestrator
        # re-classifies via the action-aware router, so send_mail / schedule
        # / cancel / trader_execute reach the real descriptor action; the
        # ``confirmed=True`` flag lets ``check_authority`` skip the gate.
        dispatch_result = await o.dispatch(conf.request, confirmed=True)

        # Persist the replay result back onto the confirmation record
        conf = update_confirmation(
            confirmation_id,
            status="approved",
            resolved_result=dispatch_result,
        )

        await bus.broadcast(
            {
                "type": "confirmation.resolved",
                **TraceEvent(
                    type="confirmation.resolved",
                    request_id=confirmation_id,
                    agent=conf.agent,
                    payload={"confirmation": conf.model_dump()},
                ).model_dump(),
            }
        )
        return {"status": "approved", "id": confirmation_id, "dispatch_result": dispatch_result}

    @app.post("/api/confirmations/{confirmation_id}/reject")
    async def reject_confirmation(confirmation_id: str) -> dict[str, Any]:
        updated = update_confirmation(confirmation_id, status="rejected")
        if updated is None:
            raise HTTPException(status_code=404, detail="confirmation not found")
        await bus.broadcast(
            {
                "type": "confirmation.resolved",
                **TraceEvent(
                    type="confirmation.resolved",
                    request_id=confirmation_id,
                    agent=updated.agent,
                    payload={"confirmation": updated.model_dump()},
                ).model_dump(),
            }
        )
        return {"ok": True, "id": confirmation_id, "status": "rejected"}

    # ─── Watchlist ────────────────────────────────────────────────────────────

    @app.get("/api/watchlist")
    async def get_watchlist() -> dict[str, Any]:
        return {"items": load_watchlist()}

    @app.put("/api/watchlist")
    async def put_watchlist(payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise HTTPException(status_code=422, detail="items must be a list")
        if not all(isinstance(i, str) for i in items):
            raise HTTPException(status_code=422, detail="all items must be strings")
        save_watchlist(items)
        return {"items": load_watchlist()}

    # ─── Morning briefing ─────────────────────────────────────────────────────

    @app.get("/api/briefing")
    async def morning_briefing() -> dict[str, Any]:
        """Aggregate real state from every subsystem and return a smart briefing."""
        from jarvis.state.briefing import build_briefing

        try:
            brief = build_briefing(reg)
        except Exception as exc:
            log.warning("briefing failed: %s", exc, exc_info=True)
            return {"data": None, "error": str(exc)}
        return {"data": brief, "error": None}

    # ─── Cost telemetry ───────────────────────────────────────────────────────

    @app.get("/api/cost/rollup")
    async def cost_rollup(date_str: str | None = None) -> dict[str, Any]:
        """Return daily cost rollup merged with Atlas costs.

        Query param ``date_str`` accepts YYYY-MM-DD.
        Fetches Jarvis own LLM costs + Atlas costs and unions them.
        Atlas ``by_agent`` nested objects are flattened to bare cost_usd numbers
        to match ``useDailyCost.ts`` ``RawRollup`` shape.
        """
        target: date | None = None
        if date_str is not None:
            try:
                target = date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="date must be YYYY-MM-DD"
                ) from None
        jarvis_rollup = daily_rollup(target)
        resolved_date_str = jarvis_rollup["date"]

        # Attempt to fetch Atlas costs and merge; never fail if Atlas is down
        atlas_rollup = _fetch_atlas_cost_rollup(reg, resolved_date_str)
        if atlas_rollup is not None:
            jarvis_rollup = _merge_cost_rollups(jarvis_rollup, atlas_rollup)

        return jarvis_rollup

    # ─── Digest exports ──────────────────────────────────────────────────────

    @app.get("/api/exports/daily")
    async def exports_daily(date_str: str | None = None) -> dict[str, Any]:
        """Return a markdown daily digest. Query param date_str=YYYY-MM-DD optional."""
        from jarvis.state.exports import daily_digest

        target: date | None = None
        if date_str is not None:
            try:
                target = date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="date_str must be YYYY-MM-DD"
                ) from None
        resolved = target or datetime.now(UTC).date()
        md = daily_digest(resolved)
        return {"data": {"markdown": md, "date": resolved.isoformat()}, "error": None}

    @app.get("/api/exports/weekly")
    async def exports_weekly(end_date: str | None = None) -> dict[str, Any]:
        """Return a markdown weekly digest. Query param end_date=YYYY-MM-DD optional."""
        from jarvis.state.exports import weekly_digest

        end: date | None = None
        if end_date is not None:
            try:
                end = date.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="end_date must be YYYY-MM-DD"
                ) from None
        resolved_end = end or datetime.now(UTC).date()
        resolved_start = resolved_end - timedelta(days=6)
        md = weekly_digest(resolved_end)
        return {
            "data": {
                "markdown": md,
                "start": resolved_start.isoformat(),
                "end": resolved_end.isoformat(),
            },
            "error": None,
        }

    # ─── Operator preferences ─────────────────────────────────────────────────

    @app.get("/api/preferences")
    async def get_preferences() -> dict[str, Any]:
        prefs = load_preferences()
        data = asdict(prefs)
        data["important_senders"] = list(data["important_senders"])
        return data

    @app.put("/api/preferences")
    async def put_preferences(payload: dict[str, Any]) -> dict[str, Any]:
        prefs = _validate_preferences_payload(payload)
        save_preferences(prefs)
        data = asdict(prefs)
        data["important_senders"] = list(data["important_senders"])
        return data

    # ─── Tempo smart-triage ───────────────────────────────────────────────────

    @app.get("/api/tempo/triage-smart")
    async def tempo_triage_smart() -> dict[str, Any]:
        from jarvis.core.supervisor import supervise_call

        resp = supervise_call(reg, "tempo", "triage_smart")
        return {"data": resp.result, "error": None}

    @app.post("/api/tempo/snooze")
    async def tempo_snooze(payload: dict[str, Any]) -> dict[str, Any]:
        from jarvis.core.supervisor import supervise_call

        msg_id = str(payload.get("msg_id", "")).strip()
        until_iso = str(payload.get("until_iso", "")).strip()
        if not msg_id:
            raise HTTPException(status_code=400, detail="msg_id required")
        if not until_iso:
            raise HTTPException(status_code=400, detail="until_iso required")
        resp = supervise_call(reg, "tempo", "snooze_mail", {"msg_id": msg_id, "until_iso": until_iso})
        return {"data": resp.result, "error": None}

    @app.get("/api/tempo/triage-status")
    async def tempo_triage_status() -> dict[str, Any]:
        from jarvis.core.supervisor import supervise_call

        resp = supervise_call(reg, "tempo", "triage_status")
        return {"data": resp.result, "error": None}

    @app.get("/api/tempo/search")
    async def tempo_search_mail(query: str, max_results: int = 25) -> dict[str, Any]:
        from jarvis.core.supervisor import supervise_call

        q = (query or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="query required")
        resp = supervise_call(
            reg, "tempo", "search_mail", {"query": q, "max_results": max_results}
        )
        return {"data": resp.result, "error": None}

    @app.get("/api/tempo/recent")
    async def tempo_list_recent(max_results: int = 25) -> dict[str, Any]:
        from jarvis.core.supervisor import supervise_call

        resp = supervise_call(
            reg, "tempo", "list_recent_mail", {"max_results": max_results}
        )
        return {"data": resp.result, "error": None}

    # ─── Scholar ingest — file upload → summary + auto-assignment ────────────

    _DEADLINE_RE = re.compile(
        r"due\s+(?:by|on)?\s*([A-Z][a-z]+\s+\d{1,2}(?:,?\s*\d{4})?)",
        re.IGNORECASE,
    )

    def _extract_text_from_upload(filename: str, content: bytes, content_type: str) -> str:
        name_lower = filename.lower()
        if name_lower.endswith(".pdf") or content_type == "application/pdf":
            try:
                import io

                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(content))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:
                log.warning("pdf parse failed for %s: %s", filename, exc)
                return ""
        if name_lower.endswith((".txt", ".md")) or content_type.startswith("text/"):
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                return content.decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"unsupported file type: {filename}")

    @app.post("/api/scholar/ingest")
    async def scholar_ingest(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        filename = file.filename or "upload"
        text = _extract_text_from_upload(filename, content, file.content_type or "")

        lens_desc = reg.get("lens")
        scholar_desc = reg.get("scholar")
        if lens_desc is None or scholar_desc is None:
            raise HTTPException(status_code=503, detail="lens/scholar not registered")

        lens_resp = lens_desc.instance.deep_research(text, depth=2)
        summary = lens_resp.result.get("markdown", "")

        assignment_dump: dict[str, Any] | None = None
        match = _DEADLINE_RE.search(text)
        if match:
            due_str = match.group(1).strip()
            sch_resp = scholar_desc.instance.add_assignment(
                title=f"Ingested: {filename}",
                course="?",
                due=due_str,
            )
            assignment_dump = sch_resp.result.get("assignment")

        return {
            "filename": filename,
            "summary": summary,
            "assignment": assignment_dump,
        }

    # ─── Scholar Study Companion ─────────────────────────────────────────────

    def _get_study_service():  # type: ignore[return]
        from jarvis.agents.scholar.db import init_db
        from jarvis.agents.scholar.study import StudyService

        init_db()
        return StudyService()

    @app.get("/api/scholar/documents")
    async def scholar_list_docs() -> dict[str, Any]:
        svc = _get_study_service()
        return {"data": svc.list_documents(), "error": None}

    @app.post("/api/scholar/documents")
    async def scholar_upload_doc(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        filename = file.filename or "upload"
        svc = _get_study_service()
        try:
            doc = svc.upload_document(filename, content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"data": doc, "error": None}

    @app.get("/api/scholar/documents/{doc_id}")
    async def scholar_get_doc(doc_id: str) -> dict[str, Any]:
        svc = _get_study_service()
        doc = svc.get_document(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        return {"data": doc, "error": None}

    @app.delete("/api/scholar/documents/{doc_id}")
    async def scholar_delete_doc(doc_id: str) -> dict[str, Any]:
        svc = _get_study_service()
        ok = svc.delete_document(doc_id)
        if not ok:
            raise HTTPException(status_code=404, detail="document not found")
        return {"data": {"deleted": True}, "error": None}

    @app.get("/api/scholar/documents/{doc_id}/summary")
    async def scholar_get_summary(doc_id: str) -> dict[str, Any]:
        svc = _get_study_service()
        try:
            summary = svc.get_summary(doc_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"data": summary, "error": None}

    @app.get("/api/scholar/documents/{doc_id}/flashcards")
    async def scholar_list_flashcards(doc_id: str) -> dict[str, Any]:
        svc = _get_study_service()
        cards = svc.get_flashcards(doc_id)
        return {"data": cards, "error": None}

    @app.post("/api/scholar/documents/{doc_id}/flashcards")
    async def scholar_generate_flashcards(doc_id: str) -> dict[str, Any]:
        svc = _get_study_service()
        try:
            cards = svc.generate_flashcards(doc_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"data": cards, "error": None}

    @app.post("/api/scholar/flashcards/{card_id}/rate")
    async def scholar_rate_card(card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rating = payload.get("rating")
        if rating not in (0, 1, 2, 3):
            raise HTTPException(status_code=400, detail="rating must be 0-3")
        svc = _get_study_service()
        try:
            card = svc.rate_card(card_id, int(rating))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"data": card, "error": None}

    @app.get("/api/scholar/due")
    async def scholar_due_cards(course: str | None = None) -> dict[str, Any]:
        try:
            resp = reg["scholar"].call("due_flashcards", {"course": course})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result.get("flashcards", []), "error": None}

    # ─── Frontend-friendly aliases (shorter paths, body-based rate) ──────────

    @app.get("/api/scholar/docs")
    async def scholar_list_docs_alias() -> dict[str, Any]:
        svc = _get_study_service()
        return {"data": svc.list_documents(), "error": None}

    @app.post("/api/scholar/rate")
    async def scholar_rate_card_alias(payload: dict[str, Any]) -> dict[str, Any]:
        card_id = str(payload.get("card_id", "")).strip()
        rating = payload.get("rating")
        if not card_id:
            raise HTTPException(status_code=400, detail="card_id required")
        if rating not in (0, 1, 2, 3, 4, 5):
            raise HTTPException(status_code=400, detail="rating must be 0-5")
        # Map 0-5 SM-2 scale → 0-3 Anki scale used by StudyService
        sm2_to_anki = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2, 5: 3}
        mapped = sm2_to_anki[int(rating)]
        svc = _get_study_service()
        try:
            card = svc.rate_card(card_id, mapped)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"data": card, "error": None}

    # ─── Problem solver / exam mode / weak topics (Linalg companion) ─────────

    @app.post("/api/scholar/solve")
    async def scholar_solve(payload: dict[str, Any]) -> dict[str, Any]:
        problem = str(payload.get("problem", "")).strip()
        if not problem:
            raise HTTPException(status_code=400, detail="problem required")
        course = payload.get("course")
        course_str = str(course) if course else None
        try:
            resp = reg["scholar"].call("solve_problem", {"problem": problem, "course": course_str})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.post("/api/scholar/rate-problem")
    async def scholar_rate_problem(payload: dict[str, Any]) -> dict[str, Any]:
        problem_id = str(payload.get("problem_id", "")).strip()
        if not problem_id:
            raise HTTPException(status_code=400, detail="problem_id required")
        correct = bool(payload.get("correct"))
        try:
            resp = reg["scholar"].call("rate_problem", {"problem_id": problem_id, "correct": correct})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.get("/api/scholar/weak")
    async def scholar_weak(
        top_n: int = 8, course: str | None = None
    ) -> dict[str, Any]:
        try:
            resp = reg["scholar"].call(
                "weak_topics", {"top_n": int(top_n), "course": course}
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.post("/api/scholar/exam")
    async def scholar_exam(payload: dict[str, Any]) -> dict[str, Any]:
        course = str(payload.get("course", "")).strip()
        if not course:
            raise HTTPException(status_code=400, detail="course required")
        duration_min = int(payload.get("duration_min", 60))
        problem_count = int(payload.get("problem_count", 5))
        try:
            resp = reg["scholar"].call(
                "exam_session",
                {"course": course, "duration_min": duration_min, "problem_count": problem_count},
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.post("/api/scholar/seed/{seed_name}")
    async def scholar_seed(
        seed_name: str, course: str | None = None
    ) -> dict[str, Any]:
        try:
            resp = reg["scholar"].call(
                "import_seed", {"seed_name": seed_name, "course": course}
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.post("/api/scholar/ingest-syllabus")
    async def scholar_ingest_syllabus(payload: dict[str, Any]) -> dict[str, Any]:
        filename = str(payload.get("filename", "")).strip()
        content_b64 = str(payload.get("content_b64", "")).strip()
        course = str(payload.get("course", "")).strip()
        if not filename or not content_b64 or not course:
            raise HTTPException(
                status_code=400,
                detail="filename, content_b64, and course are required",
            )
        try:
            tempo_inst = reg["tempo"].instance
            resp = reg["scholar"].instance.ingest_syllabus(
                filename=filename,
                content_b64=content_b64,
                course=course,
                tempo=tempo_inst,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    # ─── Forge runs ──────────────────────────────────────────────────────────

    @app.post("/api/forge/execute")
    async def forge_execute(payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a forge task and return the run record."""
        repo = str(payload.get("repo", "")).strip()
        task = str(payload.get("task", "")).strip()
        if not task:
            raise HTTPException(status_code=400, detail="task required")
        push = bool(payload.get("push", False))
        forge_desc = reg.get("forge")
        if forge_desc is None:
            raise HTTPException(status_code=503, detail="forge not registered")
        try:
            resp = forge_desc.call("execute", {"repo": repo, "task": task, "push": push})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.get("/api/forge/runs")
    async def forge_list_runs(limit: int = 50) -> dict[str, Any]:
        """List recent forge runs."""
        forge_desc = reg.get("forge")
        if forge_desc is None:
            raise HTTPException(status_code=503, detail="forge not registered")
        try:
            resp = forge_desc.call("list_runs", {"limit": limit})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"data": resp.result, "error": None}

    @app.get("/api/forge/runs/{run_id}")
    async def forge_get_run(run_id: str) -> dict[str, Any]:
        """Fetch a single forge run by ID."""
        forge_desc = reg.get("forge")
        if forge_desc is None:
            raise HTTPException(status_code=503, detail="forge not registered")
        try:
            resp = forge_desc.call("get_run", {"run_id": run_id})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if resp.action == "not_found":
            raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
        return {"data": resp.result, "error": None}

    @app.get("/api/forge/runs/{run_id}/log")
    async def forge_run_log(run_id: str) -> Any:
        """Return the raw log for a forge run as plain text."""
        from fastapi.responses import PlainTextResponse

        forge_desc = reg.get("forge")
        if forge_desc is None:
            raise HTTPException(status_code=503, detail="forge not registered")
        resp = forge_desc.call("get_run", {"run_id": run_id})
        if resp.action == "not_found":
            raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
        log_path = resp.result.get("run", {}).get("log_path", "")
        if not log_path:
            raise HTTPException(status_code=404, detail="log_path not set on run")
        try:
            text = Path(log_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="log file not found") from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return PlainTextResponse(text)

    # ─── Jarvis chatbot (Claude Opus 4.7 + OpenClaw soul) ────────────────────

    _jarvis_chat: dict[str, Any] = {"instance": None}

    def _get_jarvis():
        if _jarvis_chat["instance"] is None:
            from jarvis.agent import JarvisChat

            _jarvis_chat["instance"] = JarvisChat(registry=reg)
        return _jarvis_chat["instance"]

    def _bearer_user_id(request: Request) -> str:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        return user_id_from_token(token)

    @app.post("/api/jarvis/chat")
    async def jarvis_chat(payload: dict[str, Any], request: Request) -> StreamingResponse:
        message = str(payload.get("message", "")).strip()
        # Optional image attachment: base64-encoded bytes + media type.
        # When present, route through the multimodal vision path so Claude
        # can see the screenshot/diagram/PDF page the operator dropped in.
        image_b64 = payload.get("image_b64") or payload.get("image")
        image_media_type = str(
            payload.get("image_media_type")
            or payload.get("media_type")
            or "image/png"
        )
        if not message and not image_b64:
            raise HTTPException(status_code=400, detail="message or image required")
        # Image without prompt is OK — fall back to a default question.
        if not message:
            message = "What's in this image?"
        chat = _get_jarvis()
        user_id = _bearer_user_id(request)
        turn_id = uuid4().hex

        async def gen():
            assistant_buf: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            tool_call_index: dict[str, int] = {}
            model = ""
            cost_usd = 0.0
            duration_ms = 0
            try:
                if image_b64:
                    stream_iter = chat.stream_with_image(
                        message,
                        str(image_b64),
                        media_type=image_media_type,
                        surface="chat",
                        session_id=user_id,
                    )
                else:
                    stream_iter = chat.stream(
                        message, surface="chat", session_id=user_id
                    )
                async for ev in stream_iter:
                    if ev.type == "text":
                        assistant_buf.append(str(ev.payload.get("delta", "")))
                    elif ev.type == "model":
                        model = str(ev.payload.get("model", ""))
                    elif ev.type == "tool_use":
                        tool_use_id = str(ev.payload.get("tool_use_id", ""))
                        tool_call_index[tool_use_id] = len(tool_calls)
                        tool_calls.append(
                            {
                                "tool_use_id": tool_use_id,
                                "agent": str(ev.payload.get("agent", "")),
                                "action": str(ev.payload.get("action", "")),
                                "args": ev.payload.get("args") or {},
                                "result": None,
                            }
                        )
                    elif ev.type == "tool_result":
                        tool_use_id = str(ev.payload.get("tool_use_id", ""))
                        if tool_use_id in tool_call_index:
                            tool_calls[tool_call_index[tool_use_id]]["result"] = {
                                "text": str(ev.payload.get("text", "")),
                                "is_error": bool(ev.payload.get("is_error", False)),
                            }
                    elif ev.type == "done":
                        if isinstance(ev.payload.get("total_cost_usd"), (int, float)):
                            cost_usd = float(ev.payload["total_cost_usd"])
                        if isinstance(ev.payload.get("duration_ms"), (int, float)):
                            duration_ms = int(ev.payload["duration_ms"])

                    line = json.dumps(
                        {"type": ev.type, "turn_id": turn_id, **ev.payload}, default=str
                    )
                    yield f"data: {line}\n\n"
            except Exception as exc:  # pragma: no cover
                log.exception("jarvis chat stream failed")
                err = json.dumps({"type": "error", "message": str(exc)})
                yield f"data: {err}\n\n"
                return

            try:
                append_turn(
                    ChatTurnRecord(
                        user_id=user_id,
                        turn_id=turn_id,
                        user_text=message,
                        assistant_text="".join(assistant_buf),
                        tool_calls=tool_calls,
                        model=model,
                        cost_usd=cost_usd,
                        duration_ms=duration_ms,
                        ts=datetime.now(UTC).isoformat(),
                        session_id=user_id,
                        surface="chat",
                    )
                )
            except Exception:
                log.exception("failed to persist chat turn")

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/jarvis/turns")
    async def jarvis_turns(request: Request, limit: int = 50) -> dict[str, Any]:
        """Recent chat turns for the bearer-derived user, oldest-first."""
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=422, detail="limit must be 1-500")
        user_id = _bearer_user_id(request)
        records = read_recent(user_id, limit=limit)
        return {"data": [asdict(r) for r in records], "error": None}

    @app.get("/api/jarvis/turns/stream")
    async def jarvis_turns_stream(request: Request) -> StreamingResponse:
        """SSE push of every new chat turn as it lands in chat_turns.jsonl.

        Lets the dashboard see voice-originated turns the instant the
        voice daemon writes them, without polling. The bearer token
        scopes which turns the subscriber receives (matches user_id);
        voice turns persisted under user_id="default" are also passed
        through so a logged-out dashboard still receives them.
        """
        from jarvis.state.chat_turns import subscribe as _subscribe

        user_id = _bearer_user_id(request)

        async def gen():
            # Comment line keeps the SSE connection alive through proxies.
            yield ": connected\n\n"
            try:
                async for payload in _subscribe():
                    record_user = payload.get("user_id", "")
                    if record_user and record_user != user_id and record_user != "default":
                        continue
                    line = json.dumps({"turn": payload}, default=str)
                    yield f"data: {line}\n\n"
                    if await request.is_disconnected():
                        return
            except asyncio.CancelledError:
                return

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/jarvis/terminal")
    async def jarvis_terminal_chat(payload: dict[str, Any]) -> dict[str, Any]:
        """Non-streaming chat endpoint for Atlas terminal reverse-path.

        Atlas terminal.py POSTs unprefixed messages here with
        ``{"message": str, "session_id": str}``. Returns
        ``{"response": str, "session_id": str}``.
        """
        message = str(payload.get("message", "")).strip()
        session_id = str(payload.get("session_id", ""))
        if not message:
            raise HTTPException(status_code=400, detail="message required")
        chat = _get_jarvis()
        chunks: list[str] = []
        try:
            async for ev in chat.stream(message):
                if ev.type == "text":
                    chunks.append(ev.payload.get("delta", ""))
        except Exception as exc:
            log.warning("jarvis terminal chat error: %s", exc)
            return {"response": f"error: {exc}", "session_id": session_id}
        return {"response": "".join(chunks), "session_id": session_id}

    @app.post("/api/jarvis/recall")
    async def jarvis_recall(payload: dict[str, Any]) -> dict[str, Any]:
        """Semantic search over long-term chat history.

        Body: {query: str, top_k?: int}
        Response: {data: [{score, role, text, ts, lane}], error: null | str}
        """
        query = str(payload.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=400, detail="query required")
        top_k = int(payload.get("top_k", 5))
        if top_k < 1 or top_k > 50:
            raise HTTPException(status_code=422, detail="top_k must be 1-50")
        chat = _get_jarvis()
        try:
            results = chat.semantic_search(query, top_k=top_k)
        except Exception as exc:
            log.warning("recall failed: %s", exc)
            return {"data": [], "error": str(exc)}
        return {"data": results, "error": None}

    # ─── Cross-agent triggers ─────────────────────────────────────────────────

    # ─── Global search ────────────────────────────────────────────────────────

    @app.get("/api/search")
    async def global_search(q: str = "", limit_per_kind: int = 5) -> dict[str, Any]:
        """Keyword + semantic search across inbox, tasks, decisions, logs, chat.

        Query params:
          q              — search query string
          limit_per_kind — max results per source (default 5)
        """
        from dataclasses import asdict

        from jarvis.search import search_all

        if limit_per_kind < 1 or limit_per_kind > 20:
            raise HTTPException(status_code=422, detail="limit_per_kind must be 1-20")
        try:
            hits = search_all(q, limit_per_kind=limit_per_kind)
        except Exception as exc:
            log.warning("search_all failed: %s", exc)
            return {"data": [], "error": str(exc)}
        return {"data": [asdict(h) for h in hits], "error": None}

    # Wire inbox listener so every append_inbox call fans out to trigger rules.
    # The notifier is injected so atlas/forge alert events surface as pushes
    # (priority=2) from this process too — guardian violations triggered by
    # /api/dispatch or /api/jarvis/chat are visible immediately on phone/desktop
    # without waiting for the dashboard to refresh.
    from jarvis.core.triggers import fire_for_event as _fire_for_event
    from jarvis.core.triggers import list_recent_fires as _list_recent_fires

    _trigger_notifier: Any | None = None
    try:
        from jarvis.apps.sentinel.notifier import default_notifier as _default_notifier
        _trigger_notifier = _default_notifier()
    except Exception:  # pragma: no cover — degrade to no-op
        log.debug("api: notifier unavailable; trigger pushes will fall back to noop")

    register_inbox_listener(lambda e: _fire_for_event(reg, e, notifier=_trigger_notifier))

    @app.get("/api/triggers/recent")
    async def triggers_recent(limit: int = 50) -> dict[str, Any]:
        """Return the most recent trigger fire records."""
        return {"data": _list_recent_fires(limit=limit), "error": None}

    @app.get("/api/triggers/rules")
    async def triggers_rules() -> dict[str, Any]:
        """Return static list of rule names and descriptions."""
        rules = [
            {
                "name": "scholar_exam_scheduled",
                "description": "scholar.exam_session success → tempo.add blocks exam as a task",
                "trigger": "event-driven (after exam_session call)",
            },
            {
                "name": "scholar_exam_imminent",
                "description": "Exam starting within 24h → warn InboxEvent surfaced on /scholar",
                "trigger": "periodic (every 30 min via sentinel)",
            },
            {
                "name": "tempo_task_due_today",
                "description": "Task with course: tag due today → info InboxEvent on /scholar",
                "trigger": "periodic (every 30 min via sentinel)",
            },
            {
                "name": "forge_run_failed",
                "description": "Forge dead-letter record → alert InboxEvent on /inbox",
                "trigger": "periodic (every 30 min via sentinel)",
            },
            {
                "name": "atlas_guardian_violation",
                "description": "Atlas guardian_check violation → alert InboxEvent (caller-driven)",
                "trigger": "event-driven (atlas pipeline)",
            },
        ]
        return {"data": rules, "error": None}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):  # pragma: no cover - websocket runtime
        global _active_loop
        _active_loop = asyncio.get_running_loop()
        await websocket.accept()
        await bus.add(websocket)
        try:
            while True:
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            await bus.remove(websocket)

    # Atlas WS client — started on startup when atlas mode is live
    from jarvis.agents.atlas.ws_client import AtlasWsClient as _AtlasWsClient

    _atlas_ws: dict[str, Any] = {"client": None}

    @app.on_event("startup")
    async def _capture_loop() -> None:
        global _active_loop
        _active_loop = asyncio.get_running_loop()
        atlas_desc = reg.get("atlas")
        if atlas_desc is not None:
            from jarvis.agents.atlas.agent import AtlasOrchestrator

            orchestrator_inst = atlas_desc.instance
            if isinstance(orchestrator_inst, AtlasOrchestrator) and orchestrator_inst.mode == "live":
                ws_client = _AtlasWsClient(_make_event_sink(bus))
                _atlas_ws["client"] = ws_client
                await ws_client.start_ws()

    @app.on_event("shutdown")
    async def _ws_shutdown() -> None:
        client = _atlas_ws.get("client")
        if client is not None:
            await client.stop()

    # Test helper: surface bus + registry as app.state so tests can inspect
    app.state.broadcaster = bus
    app.state.registry = reg
    # Expose _jarvis_chat dict so tests can inject a mock chat instance
    app.state.jarvis_chat = _jarvis_chat
    return app


app = None
if HAS_FASTAPI:  # pragma: no cover
    app = make_app()
# end of app.py

