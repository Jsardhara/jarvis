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
