"""Orchestrator dispatch + context aggregation."""
from __future__ import annotations

import asyncio

from jarvis.contract import AgentResponse, InboxEvent, Task
from jarvis.orchestrator import Orchestrator
from jarvis.state import add_task, append_inbox


def _stub_handler(name: str):
    async def _h(req: str) -> AgentResponse:
        return AgentResponse(agent=name, intent="stub", action="done", result={"echo": req})
    return _h


def test_route_classifies_into_intent():
    o = Orchestrator()
    intent = o.route("check inbox")
    assert intent.primary == "tempo"


def test_dispatch_invokes_primary():
    o = Orchestrator({"tempo": _stub_handler("tempo")})
    out = asyncio.run(o.dispatch("check inbox"))
    assert "tempo" in out["responses"]
    assert out["responses"]["tempo"]["result"]["echo"] == "check inbox"


def test_dispatch_invokes_parallel_for_briefing():
    o = Orchestrator({
        "tempo": _stub_handler("tempo"),
        "scholar": _stub_handler("scholar"),
        "atlas": _stub_handler("atlas"),
    })
    out = asyncio.run(o.dispatch("morning briefing please"))
    assert {"tempo", "scholar", "atlas"} <= set(out["responses"].keys())


def test_gather_context_includes_inbox_and_tasks():
    add_task(Task(title="open one"))
    append_inbox(InboxEvent(agent="tempo", severity="info", summary="3 unread"))
    o = Orchestrator()
    ctx = o.gather_context()
    assert any(t["title"] == "open one" for t in ctx["tasks"])
    assert any(e["summary"] == "3 unread" for e in ctx["inbox"])


def test_dispatch_skips_unregistered_handlers():
    o = Orchestrator({"tempo": _stub_handler("tempo")})
    out = asyncio.run(o.dispatch("morning briefing"))
    assert "tempo" in out["responses"]
    assert "atlas" not in out["responses"]


def test_register_adds_handler():
    o = Orchestrator()
    o.register("tempo", _stub_handler("tempo"))
    out = asyncio.run(o.dispatch("inbox"))
    assert "tempo" in out["responses"]
