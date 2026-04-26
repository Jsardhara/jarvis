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
    assert intent.primary == "aide"


def test_dispatch_invokes_primary():
    o = Orchestrator({"aide": _stub_handler("aide")})
    out = asyncio.run(o.dispatch("check inbox"))
    assert "aide" in out["responses"]
    assert out["responses"]["aide"]["result"]["echo"] == "check inbox"


def test_dispatch_invokes_parallel_for_briefing():
    o = Orchestrator({
        "aide": _stub_handler("aide"),
        "chronos": _stub_handler("chronos"),
        "ledger": _stub_handler("ledger"),
    })
    out = asyncio.run(o.dispatch("morning briefing please"))
    assert {"aide", "chronos", "ledger"} <= set(out["responses"].keys())


def test_gather_context_includes_inbox_and_tasks():
    add_task(Task(title="open one"))
    append_inbox(InboxEvent(agent="aide", severity="info", summary="3 unread"))
    o = Orchestrator()
    ctx = o.gather_context()
    assert any(t["title"] == "open one" for t in ctx["tasks"])
    assert any(e["summary"] == "3 unread" for e in ctx["inbox"])


def test_dispatch_skips_unregistered_handlers():
    o = Orchestrator({"aide": _stub_handler("aide")})  # no chronos/ledger
    out = asyncio.run(o.dispatch("morning briefing"))
    assert "aide" in out["responses"]
    assert "chronos" not in out["responses"]


def test_register_adds_handler():
    o = Orchestrator()
    o.register("aide", _stub_handler("aide"))
    out = asyncio.run(o.dispatch("inbox"))
    assert "aide" in out["responses"]
