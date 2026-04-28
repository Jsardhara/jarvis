"""FastAPI bridge for the web dashboard.

Exposes orchestrator functionality over HTTP for the Next.js front-end and
streams agent activity over WebSocket. Run alongside webhooks:

    uvicorn jarvis.web.api:app --reload --port 8765
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

from ..contract import AgentLogEntry, Confirmation, InboxEvent, Task, TraceEvent
from ..cost import daily_rollup
from ..memory import OperatorPreferences, load_preferences, save_preferences
from ..orchestrator import Orchestrator
from ..state import (
    add_confirmation,
    add_task,
    append_agent_log,
    load_tasks,
    load_watchlist,
    read_agent_log,
    read_confirmations,
    read_inbox,
    register_inbox_listener,
    save_watchlist,
    unregister_inbox_listener,
    update_confirmation,
    update_task,
)
from ..subsystems.registry import AgentDescriptor, build_default_registry

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


def _build_orchestrator(registry: dict[str, AgentDescriptor]) -> Orchestrator:
    o = Orchestrator()
    for name, desc in registry.items():

        async def _handler(req: str, _desc: AgentDescriptor = desc) -> Any:
            return _desc.call_text(req)

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

    app = FastAPI(title="Jarvis API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("shutdown")
    async def _cleanup() -> None:
        unregister_inbox_listener(_push_inbox_event)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "jarvis-api"}

    @app.get("/api/inbox")
    async def inbox(limit: int = 50) -> dict[str, Any]:
        return {"events": [e.model_dump() for e in read_inbox(limit=limit)]}

    @app.get("/api/activity")
    async def activity(limit: int = 100) -> dict[str, Any]:
        """Return recent agent_log entries — mirrors /api/inbox shape."""
        return {"entries": [e.model_dump() for e in read_agent_log(limit=limit)]}

    @app.get("/api/atlas/snapshot")
    async def atlas_snapshot() -> dict[str, Any]:
        """Combine portfolio + pnl + positions; set degraded=True when ATLAS is offline."""
        return _atlas_snapshot_data(reg)

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

        # Replay the original request with confirmed=True
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

    # ─── Cost telemetry ───────────────────────────────────────────────────────

    @app.get("/api/cost/rollup")
    async def cost_rollup(date_str: str | None = None) -> dict[str, Any]:
        """Return daily cost rollup.  Query param ``date`` accepts YYYY-MM-DD."""
        target: date | None = None
        if date_str is not None:
            try:
                target = date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="date must be YYYY-MM-DD"
                ) from None
        return daily_rollup(target)

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

    # ─── Jarvis chatbot (Claude Opus 4.7 + OpenClaw soul) ────────────────────

    _jarvis_chat: dict[str, Any] = {"instance": None}

    def _get_jarvis():
        if _jarvis_chat["instance"] is None:
            from ..jarvis_agent import JarvisChat

            _jarvis_chat["instance"] = JarvisChat(registry=reg)
        return _jarvis_chat["instance"]

    @app.post("/api/jarvis/chat")
    async def jarvis_chat(payload: dict[str, Any]) -> StreamingResponse:
        message = str(payload.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="message required")
        chat = _get_jarvis()

        async def gen():
            try:
                async for ev in chat.stream(message):
                    line = json.dumps({"type": ev.type, **ev.payload}, default=str)
                    yield f"data: {line}\n\n"
            except Exception as exc:  # pragma: no cover
                log.exception("jarvis chat stream failed")
                err = json.dumps({"type": "error", "message": str(exc)})
                yield f"data: {err}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

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

    @app.on_event("startup")
    async def _capture_loop() -> None:
        global _active_loop
        _active_loop = asyncio.get_running_loop()

    # Test helper: surface bus + registry as app.state so tests can inspect
    app.state.broadcaster = bus
    app.state.registry = reg
    return app


app = None
if HAS_FASTAPI:  # pragma: no cover
    app = make_app()
