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
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

from ..contract import AgentLogEntry, Confirmation, Task, TraceEvent
from ..orchestrator import Orchestrator
from ..state import (
    add_confirmation,
    add_task,
    append_agent_log,
    load_tasks,
    read_agent_log,
    read_confirmations,
    read_inbox,
    update_confirmation,
    update_task,
)
from ..subsystems.registry import AgentDescriptor, build_default_registry

log = logging.getLogger(__name__)


def _build_orchestrator(registry: dict[str, AgentDescriptor]) -> Orchestrator:
    o = Orchestrator()
    for name, desc in registry.items():
        async def _handler(req: str, _desc: AgentDescriptor = desc) -> Any:
            return _desc.call_text(req)
        o.register(name, _handler)
    return o


class _Broadcaster:
    """Tiny WebSocket fan-out for live agent activity."""

    def __init__(self):
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
            append_agent_log(AgentLogEntry(
                ts=event.ts,
                request_id=event.request_id,
                agent=event.agent,
                action="?",
                status="error",
                duration_ms=int(payload.get("duration_ms", 0)),
                error=str(payload.get("error", "")),
            ))
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
    return {"portfolio": portfolio, "pnl": pnl, "positions": positions, "degraded": degraded, "ts": ts}


def make_app(orchestrator: Orchestrator | None = None,
             registry: dict[str, AgentDescriptor] | None = None) -> FastAPI:
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi not installed — pip install jarvis[web]")
    reg = registry or build_default_registry()
    o = orchestrator or _build_orchestrator(reg)
    bus = _Broadcaster()
    o.set_event_sink(_make_event_sink(bus))

    app = FastAPI(title="Jarvis API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        t = add_task(Task(title=payload["title"], due=payload.get("due"),
                          tags=payload.get("tags", [])))
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
        # Auto-capture confirmations from any agent that needs_confirm
        for agent_name, resp in result.get("responses", {}).items():
            if resp.get("needs_confirm"):
                conf = add_confirmation(Confirmation(
                    agent=agent_name,
                    intent=resp.get("intent", ""),
                    args=resp.get("result", {}),
                    summary=", ".join(resp.get("follow_ups", []))[:160],
                ))
                await bus.broadcast({
                    "type": "confirmation.created",
                    **TraceEvent(
                        type="confirmation.created",
                        request_id=result.get("request_id", ""),
                        agent=agent_name,
                        payload={"confirmation": conf.model_dump()},
                    ).model_dump(),
                })
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

        await bus.broadcast({"type": "agent.start",
                             **TraceEvent(type="agent.start", request_id=request_id,
                                          agent=name, payload={"text": text, "action": action}
                                          ).model_dump()})
        started = time.perf_counter()
        try:
            resp = desc.call(action, payload.get("args", {})) if action else desc.call_text(text)
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            append_agent_log(AgentLogEntry(
                request_id=request_id, agent=name, action=action or "text",
                status="error", duration_ms=duration, error=str(exc),
            ))
            await bus.broadcast({"type": "agent.error",
                                 **TraceEvent(type="agent.error", request_id=request_id,
                                              agent=name,
                                              payload={"error": str(exc), "duration_ms": duration}
                                              ).model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        duration = int((time.perf_counter() - started) * 1000)
        append_agent_log(AgentLogEntry(
            request_id=request_id, agent=name, action=resp.action,
            status="proposed" if resp.needs_confirm else "ok",
            duration_ms=duration, confidence=resp.confidence,
            needs_confirm=resp.needs_confirm,
        ))
        await bus.broadcast({"type": "agent.done",
                             **TraceEvent(type="agent.done", request_id=request_id, agent=name,
                                          payload={"duration_ms": duration, "action": resp.action,
                                                   "confidence": resp.confidence,
                                                   "needs_confirm": resp.needs_confirm}
                                          ).model_dump()})
        if resp.needs_confirm:
            conf = add_confirmation(Confirmation(
                agent=name, intent=resp.intent, args=resp.result,
                summary=", ".join(resp.follow_ups)[:160],
            ))
            await bus.broadcast({"type": "confirmation.created",
                                 **TraceEvent(type="confirmation.created", request_id=request_id,
                                              agent=name,
                                              payload={"confirmation": conf.model_dump()}
                                              ).model_dump()})
        return resp.model_dump()

    @app.get("/api/agents/{name}/history")
    async def agent_history(name: str, limit: int = 50) -> dict[str, Any]:
        if name not in reg:
            raise HTTPException(status_code=404, detail=f"unknown agent '{name}'")
        entries = read_agent_log(agent=name, limit=limit)
        return {"entries": [e.model_dump() for e in entries]}

    @app.get("/api/confirmations")
    async def list_confirmations(status: str | None = None, limit: int = 100) -> dict[str, Any]:
        items = read_confirmations(status=status, limit=limit)
        return {"confirmations": [c.model_dump() for c in items]}

    @app.post("/api/confirmations/{confirmation_id}/approve")
    async def approve_confirmation(confirmation_id: str) -> dict[str, Any]:
        updated = update_confirmation(confirmation_id, status="approved")
        if updated is None:
            raise HTTPException(status_code=404, detail="confirmation not found")
        await bus.broadcast({"type": "confirmation.resolved",
                             **TraceEvent(type="confirmation.resolved",
                                          request_id=confirmation_id, agent=updated.agent,
                                          payload={"confirmation": updated.model_dump()}
                                          ).model_dump()})
        return updated.model_dump()

    @app.post("/api/confirmations/{confirmation_id}/reject")
    async def reject_confirmation(confirmation_id: str) -> dict[str, Any]:
        updated = update_confirmation(confirmation_id, status="rejected")
        if updated is None:
            raise HTTPException(status_code=404, detail="confirmation not found")
        await bus.broadcast({"type": "confirmation.resolved",
                             **TraceEvent(type="confirmation.resolved",
                                          request_id=confirmation_id, agent=updated.agent,
                                          payload={"confirmation": updated.model_dump()}
                                          ).model_dump()})
        return updated.model_dump()

    # ─── Jarvis chatbot (Claude Opus 4.7 + OpenClaw soul) ─────────────────────

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

        return StreamingResponse(gen(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):  # pragma: no cover - websocket runtime
        await websocket.accept()
        await bus.add(websocket)
        try:
            while True:
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            await bus.remove(websocket)

    # Test helper: surface bus + registry as app.state so tests can inspect
    app.state.broadcaster = bus
    app.state.registry = reg
    return app


app = None
if HAS_FASTAPI:  # pragma: no cover
    app = make_app()
