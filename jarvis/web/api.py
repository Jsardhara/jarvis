"""FastAPI bridge for the web dashboard.

Exposes orchestrator functionality over HTTP for the Next.js front-end and
streams agent activity over WebSocket. Run alongside webhooks:

    uvicorn jarvis.web.api:app --reload --port 8765
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

from ..contract import AgentResponse, Task
from ..orchestrator import Orchestrator
from ..state import (
    add_task,
    append_inbox,
    load_tasks,
    read_inbox,
    update_task,
)
from ..subsystems.aide import Aide
from ..subsystems.chronos import Chronos
from ..subsystems.echo import Echo
from ..subsystems.forge import Forge, MockRunner
from ..subsystems.ledger import AtlasClient, Ledger
from ..subsystems.providers import MockCalendar, MockGmail
from ..subsystems.sherlock import MockSearch, Sherlock

log = logging.getLogger(__name__)


def _build_orchestrator() -> Orchestrator:
    aide = Aide(MockGmail())
    chronos = Chronos(MockCalendar())
    sherlock = Sherlock(MockSearch())
    forge = Forge(MockRunner())
    ledger = Ledger(client=AtlasClient(), allow_mock=True)
    echo = Echo()

    o = Orchestrator()
    async def _aide(req): return aide.triage()
    async def _chronos(req): return chronos.today()
    async def _sherlock(req): return sherlock.quick_search(req)
    async def _forge(req): return forge.execute(repo="?", task=req, push=False)
    async def _ledger(req): return ledger.portfolio()
    async def _echo(req): return echo.triage([])

    o.register("aide", _aide)
    o.register("chronos", _chronos)
    o.register("sherlock", _sherlock)
    o.register("forge", _forge)
    o.register("ledger", _ledger)
    o.register("echo", _echo)
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


def make_app(orchestrator: Orchestrator | None = None) -> "FastAPI":
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi not installed — pip install jarvis[web]")
    o = orchestrator or _build_orchestrator()
    bus = _Broadcaster()
    app = FastAPI(title="Jarvis API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "jarvis-api"}

    @app.get("/api/inbox")
    async def inbox(limit: int = 50) -> dict[str, Any]:
        return {"events": [e.model_dump() for e in read_inbox(limit=limit)]}

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
        return result

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):  # pragma: no cover - websocket runtime
        await websocket.accept()
        await bus.add(websocket)
        try:
            while True:
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            await bus.remove(websocket)

    # Test helper: surface bus as app.state so tests can broadcast/inspect
    app.state.broadcaster = bus
    return app


app = None
if HAS_FASTAPI:  # pragma: no cover
    app = make_app()
