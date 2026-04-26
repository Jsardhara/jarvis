"""FastAPI dashboard API smoke tests."""
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
    append_inbox(InboxEvent(agent="aide", severity="info", summary="3 unread"))
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
    # 'plate' triggers briefing → aide + chronos + ledger
    assert "aide" in body["responses"]
    assert "chronos" in body["responses"]
    assert "request_id" in body


def test_list_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    names = {a["name"] for a in r.json()["agents"]}
    assert {"aide", "chronos", "sherlock", "forge", "ledger", "echo", "hearth"} <= names


def test_agent_dispatch_explicit_action(client):
    r = client.post("/api/agents/aide/dispatch", json={"action": "triage"})
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "aide"
    assert body["action"] == "triaged"


def test_agent_dispatch_text_falls_back_to_default(client):
    r = client.post("/api/agents/chronos/dispatch", json={"text": "anything"})
    assert r.status_code == 200
    assert r.json()["agent"] == "chronos"


def test_agent_dispatch_unknown_agent(client):
    r = client.post("/api/agents/ghost/dispatch", json={"text": "hi"})
    assert r.status_code == 404


def test_agent_dispatch_unknown_action(client):
    r = client.post("/api/agents/aide/dispatch", json={"action": "nope"})
    assert r.status_code == 400


def test_agent_history_after_dispatch(client):
    client.post("/api/agents/aide/dispatch", json={"action": "triage"})
    r = client.get("/api/agents/aide/history?limit=10")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["agent"] == "aide" and e["action"] == "triaged" for e in entries)


def test_confirmations_lifecycle(client):
    # Trigger a needs_confirm action via per-agent dispatch
    r = client.post("/api/agents/ledger/dispatch",
                    json={"action": "trigger_strategy",
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
    client.post("/api/agents/ledger/dispatch",
                json={"action": "trigger_strategy",
                      "args": {"strategy_id": "alpha-2", "mode": "paper"}})
    cid = client.get("/api/confirmations?status=pending").json()["confirmations"][-1]["id"]
    rejected = client.post(f"/api/confirmations/{cid}/reject").json()
    assert rejected["status"] == "rejected"


def test_reject_unknown_confirmation(client):
    r = client.post("/api/confirmations/missing/reject")
    assert r.status_code == 404
