"""FastAPI dashboard API smoke tests — six-agent registry."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.contract import InboxEvent, Task
from jarvis.state import add_task, append_inbox
from jarvis.web.api import make_app


@pytest.fixture
def client():
    return TestClient(make_app())


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_inbox_returns_events(client):
    append_inbox(InboxEvent(agent="tempo", severity="info", summary="3 unread"))
    r = client.get("/api/inbox")
    assert r.status_code == 200
    assert any(e["summary"] == "3 unread" for e in r.json()["events"])


def test_tasks_list(client):
    add_task(Task(title="ship phase 6"))
    r = client.get("/api/tasks")
    titles = [t["title"] for t in r.json()["tasks"]]
    assert "ship phase 6" in titles


def test_create_task(client):
    r = client.post("/api/tasks", json={"title": "new task", "tags": ["work"]})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "new task"
    assert body["tags"] == ["work"]


def test_patch_task_status(client):
    create = client.post("/api/tasks", json={"title": "to be done"})
    tid = create.json()["id"]
    r = client.patch(f"/api/tasks/{tid}", json={"status": "done"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_patch_missing_task(client):
    r = client.patch("/api/tasks/ghost", json={"status": "done"})
    assert r.json() == {"error": "not_found"}


def test_dispatch_routes_request(client):
    r = client.post("/api/dispatch", json={"request": "what's on my plate today"})
    assert r.status_code == 200
    body = r.json()
    assert "intent" in body
    assert "responses" in body
    assert "tempo" in body["responses"]
    assert "scholar" in body["responses"] or "atlas" in body["responses"]
    assert "request_id" in body


def test_list_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    names = {a["name"] for a in r.json()["agents"]}
    assert {"tempo", "scholar", "lens", "forge", "atlas"} <= names


def test_agent_dispatch_explicit_action(client):
    r = client.post("/api/agents/tempo/dispatch", json={"action": "triage"})
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "tempo"
    assert body["action"] == "triaged"


def test_agent_dispatch_text_falls_back_to_default(client):
    r = client.post("/api/agents/tempo/dispatch", json={"text": "anything"})
    assert r.status_code == 200
    assert r.json()["agent"] == "tempo"


def test_agent_dispatch_unknown_agent(client):
    r = client.post("/api/agents/ghost/dispatch", json={"text": "hi"})
    assert r.status_code == 404


def test_agent_dispatch_unknown_action(client):
    r = client.post("/api/agents/tempo/dispatch", json={"action": "nope"})
    assert r.status_code == 400


def test_agent_history_after_dispatch(client):
    client.post("/api/agents/tempo/dispatch", json={"action": "triage"})
    r = client.get("/api/agents/tempo/history?limit=10")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["agent"] == "tempo" and e["action"] == "triaged" for e in entries)


def test_confirmations_lifecycle(client):
    r = client.post("/api/agents/atlas/dispatch",
                    json={"action": "trader_execute",
                          "args": {"strategy_id": "alpha-1", "mode": "paper"}})
    assert r.status_code == 200
    assert r.json()["needs_confirm"] is True

    pending = client.get("/api/confirmations?status=pending").json()["confirmations"]
    assert len(pending) >= 1
    cid = pending[-1]["id"]

    approved = client.post(f"/api/confirmations/{cid}/approve").json()
    assert approved["status"] == "approved"

    pending_after = client.get("/api/confirmations?status=pending").json()["confirmations"]
    assert all(c["id"] != cid for c in pending_after)


def test_reject_confirmation(client):
    client.post("/api/agents/atlas/dispatch",
                json={"action": "trader_execute",
                      "args": {"strategy_id": "alpha-2", "mode": "paper"}})
    cid = client.get("/api/confirmations?status=pending").json()["confirmations"][-1]["id"]
    rejected = client.post(f"/api/confirmations/{cid}/reject").json()
    assert rejected["status"] == "rejected"


def test_reject_unknown_confirmation(client):
    r = client.post("/api/confirmations/missing/reject")
    assert r.status_code == 404


# --- /api/activity ---


def test_activity_returns_200_with_entries_key(client):
    r = client.get("/api/activity")
    assert r.status_code == 200
    assert "entries" in r.json()


def test_activity_returns_agent_log_entries(client):
    client.post("/api/agents/tempo/dispatch", json={"action": "triage"})
    r = client.get("/api/activity?limit=10")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["agent"] == "tempo" for e in entries)


def test_activity_empty_when_no_log(client):
    r = client.get("/api/activity")
    assert r.status_code == 200
    assert isinstance(r.json()["entries"], list)


# --- /api/atlas/snapshot ---


def test_atlas_snapshot_returns_200(client):
    r = client.get("/api/atlas/snapshot")
    assert r.status_code == 200


def test_atlas_snapshot_shape(client):
    body = client.get("/api/atlas/snapshot").json()
    assert "portfolio" in body
    assert "pnl" in body
    assert "positions" in body
    assert "degraded" in body
    assert "ts" in body


def test_atlas_snapshot_degraded_is_bool(client):
    body = client.get("/api/atlas/snapshot").json()
    assert isinstance(body["degraded"], bool)


def test_atlas_snapshot_positions_is_list(client):
    body = client.get("/api/atlas/snapshot").json()
    assert isinstance(body["positions"], list)


def test_atlas_snapshot_degraded_true_when_atlas_raises():
    """If atlas.call raises inside _atlas_snapshot_data, degraded=True is returned."""
    from jarvis.subsystems.registry import AgentDescriptor, build_default_registry
    from jarvis.web.api import make_app

    class _RaisingDescriptor(AgentDescriptor):
        def call(self, action, args=None):
            raise RuntimeError("atlas offline")

    reg = build_default_registry()
    orig = reg["atlas"]
    reg["atlas"] = _RaisingDescriptor(
        name=orig.name,
        instance=orig.instance,
        actions=orig.actions,
        description=orig.description,
    )
    c = TestClient(make_app(registry=reg))
    body = c.get("/api/atlas/snapshot").json()
    assert body["degraded"] is True
    assert body["portfolio"] == {}


def test_atlas_snapshot_no_atlas_in_registry():
    """When atlas is absent from registry the snapshot still returns 200 degraded."""
    from jarvis.subsystems.registry import build_default_registry
    from jarvis.web.api import make_app

    reg = {k: v for k, v in build_default_registry().items() if k != "atlas"}
    c = TestClient(make_app(registry=reg))
    body = c.get("/api/atlas/snapshot").json()
    assert body["degraded"] is True
    assert body["positions"] == []


# --- _summarize_result helper ---


def test_summarize_result_count_key():
    from jarvis.web.api import _summarize_result

    assert _summarize_result({"count": 7}) == "count=7"


def test_summarize_result_total_key():
    from jarvis.web.api import _summarize_result

    assert _summarize_result({"total": 3}) == "total=3"


def test_summarize_result_portfolio_value():
    from jarvis.web.api import _summarize_result

    assert _summarize_result({"portfolio": {"total_value_usd": 10000.0}}) == "value=$10000"


def test_summarize_result_empty():
    from jarvis.web.api import _summarize_result

    assert _summarize_result({}) == ""


# --- agent_history 404 ---


def test_agent_history_unknown_agent_returns_404(client):
    r = client.get("/api/agents/nonexistent/history")
    assert r.status_code == 404


# --- event sink error path ---


def test_agent_dispatch_error_is_logged_and_returns_400(client):
    """An unknown action triggers an error response + agent_log error entry."""
    r = client.post("/api/agents/tempo/dispatch", json={"action": "does_not_exist"})
    assert r.status_code == 400


# --- confirmations list with status filter ---


def test_list_confirmations_status_filter(client):
    """Filtering by status returns only matching items."""
    client.post("/api/agents/atlas/dispatch",
                json={"action": "trader_execute",
                      "args": {"strategy_id": "s-filter", "mode": "paper"}})
    pending = client.get("/api/confirmations?status=pending").json()["confirmations"]
    assert all(c["status"] == "pending" for c in pending)
    approved = client.get("/api/confirmations?status=approved").json()["confirmations"]
    assert all(c["status"] == "approved" for c in approved)


# --- dispatch confirmation auto-capture ---


def test_dispatch_captures_confirmation_when_response_needs_confirm():
    """POST /api/dispatch auto-creates a Confirmation when a response has needs_confirm=True.

    Injects a mock orchestrator whose dispatch result carries needs_confirm so the
    auto-capture branch in api.py:207-213 is exercised.
    """
    from unittest.mock import AsyncMock

    from jarvis.orchestrator import Orchestrator
    from jarvis.state import read_confirmations
    from jarvis.web.api import make_app

    mock_dispatch_result = {
        "request_id": "testid",
        "intent": {"primary": "atlas", "confidence": 0.9, "rationale": "", "parallel": [], "raw_request": "trade"},
        "tier": 4,
        "needs_confirm": True,
        "responses": {
            "atlas": {
                "agent": "atlas",
                "intent": "execute trade",
                "action": "proposed",
                "result": {},
                "follow_ups": ["confirm?"],
                "confidence": 0.9,
                "needs_confirm": True,
                "request_id": "testid",
                "ts": "2026-01-01T00:00:00+00:00",
                "tier": 4,
                "verification": {"status": "unknown"},
            }
        },
    }
    orch = Orchestrator()
    orch.dispatch = AsyncMock(return_value=mock_dispatch_result)

    c = TestClient(make_app(orchestrator=orch))
    r = c.post("/api/dispatch", json={"request": "trade something"})
    assert r.status_code == 200
    # Confirmation should have been auto-captured
    pending = read_confirmations(status="pending")
    assert any(conf.agent == "atlas" for conf in pending)


# --- read_confirmations blank-line skip (state.py:130) ---


def test_read_confirmations_handles_blank_lines(tmp_path, monkeypatch):
    """read_confirmations skips blank lines in the JSONL file gracefully."""
    import json as _json

    from jarvis.config import Settings
    from jarvis.contract import Confirmation
    from jarvis.state import read_confirmations

    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)
    c = Confirmation(agent="tempo", intent="send mail", summary="test")
    path = tmp_path / "confirmations.jsonl"
    path.write_text("\n" + _json.dumps(c.model_dump()) + "\n\n", encoding="utf-8")
    result = read_confirmations()
    assert len(result) == 1
    assert result[0].agent == "tempo"
