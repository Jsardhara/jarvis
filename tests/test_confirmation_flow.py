"""TDD tests for the confirmation token flow.

Covers:
- dispatch with needs_confirm auto-creates Confirmation and returns confirmation_id
- approve replays original request via orchestrator (confirmed=True)
- reject sets status=rejected and returns {ok, id, status}
- approve/reject on unknown id returns 404
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from unittest.mock import AsyncMock  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from jarvis.orchestrator import Orchestrator  # noqa: E402
from jarvis.state import read_confirmations  # noqa: E402
from jarvis.web.api import make_app  # noqa: E402

# ── helpers ────────────────────────────────────────────────────────────────

_NEEDS_CONFIRM_RESULT = {
    "request_id": "aaa111",
    "intent": {
        "primary": "atlas",
        "confidence": 0.9,
        "rationale": "",
        "parallel": [],
        "raw_request": "send mail to bob",
    },
    "tier": 4,
    "needs_confirm": True,
    "responses": {
        "atlas": {
            "agent": "atlas",
            "intent": "send mail",
            "action": "proposed",
            "result": {},
            "follow_ups": ["confirm the send?"],
            "confidence": 0.9,
            "needs_confirm": True,
            "request_id": "aaa111",
            "ts": "2026-01-01T00:00:00+00:00",
            "tier": 4,
            "verification": {"status": "unknown"},
        }
    },
}

_OK_RESULT = {
    "request_id": "bbb222",
    "intent": {
        "primary": "atlas",
        "confidence": 0.9,
        "rationale": "",
        "parallel": [],
        "raw_request": "send mail to bob",
    },
    "tier": 4,
    "needs_confirm": False,
    "responses": {
        "atlas": {
            "agent": "atlas",
            "intent": "send mail",
            "action": "sent",
            "result": {"ok": True},
            "follow_ups": [],
            "confidence": 0.9,
            "needs_confirm": False,
            "request_id": "bbb222",
            "ts": "2026-01-01T00:00:00+00:00",
            "tier": 4,
            "verification": {"status": "ok"},
        }
    },
}


@pytest.fixture
def client_and_orch():
    """TestClient wired to a mock orchestrator."""
    orch = Orchestrator()
    orch.dispatch = AsyncMock(return_value=_NEEDS_CONFIRM_RESULT)
    c = TestClient(make_app(orchestrator=orch))
    return c, orch


# ── tests ──────────────────────────────────────────────────────────────────


def test_dispatch_returns_confirmation_id_when_needs_confirm(client_and_orch):
    """dispatch result must include confirmation_id when needs_confirm=True."""
    client, _ = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_confirm"] is True
    assert "confirmation_id" in body
    assert body["confirmation_id"] is not None


def test_dispatch_creates_confirmation_record(client_and_orch):
    """dispatch must persist a Confirmation entry with the original request text."""
    client, _ = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    assert r.status_code == 200
    cid = r.json()["confirmation_id"]
    pending = read_confirmations(status="pending")
    matching = [c for c in pending if c.id == cid]
    assert len(matching) == 1
    conf = matching[0]
    assert conf.agent == "atlas"
    assert conf.request == "send mail to bob"


def test_dispatch_no_confirmation_id_when_ok():
    """When no agent needs_confirm, confirmation_id should NOT appear in response."""
    orch = Orchestrator()
    orch.dispatch = AsyncMock(return_value=_OK_RESULT)
    c = TestClient(make_app(orchestrator=orch))
    r = c.post("/api/dispatch", json={"request": "morning briefing"})
    assert r.status_code == 200
    assert "confirmation_id" not in r.json() or r.json().get("confirmation_id") is None


def test_approve_replays_request_via_orchestrator(client_and_orch):
    """Approve must call orchestrator.dispatch(request, confirmed=True)."""
    client, orch = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    cid = r.json()["confirmation_id"]

    # Second dispatch (replay) returns an OK result
    orch.dispatch = AsyncMock(return_value=_OK_RESULT)
    resp = client.post(f"/api/confirmations/{cid}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert "dispatch_result" in body
    # The orchestrator was called with confirmed=True
    orch.dispatch.assert_called_once_with("send mail to bob", confirmed=True)


def test_approve_updates_confirmation_status(client_and_orch):
    """Confirmation status must be 'approved' in persistent store after approve."""
    client, orch = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    cid = r.json()["confirmation_id"]

    orch.dispatch = AsyncMock(return_value=_OK_RESULT)
    client.post(f"/api/confirmations/{cid}/approve")

    all_confs = read_confirmations(status=None, limit=0)
    matching = [c for c in all_confs if c.id == cid]
    assert matching[-1].status == "approved"


def test_reject_returns_ok_status(client_and_orch):
    """Reject must return {ok, id, status} envelope."""
    client, _ = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    cid = r.json()["confirmation_id"]

    resp = client.post(f"/api/confirmations/{cid}/reject")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["id"] == cid
    assert body["status"] == "rejected"


def test_reject_updates_confirmation_status(client_and_orch):
    """Rejection must be persisted."""
    client, _ = client_and_orch
    r = client.post("/api/dispatch", json={"request": "send mail to bob"})
    cid = r.json()["confirmation_id"]

    client.post(f"/api/confirmations/{cid}/reject")

    all_confs = read_confirmations(status=None, limit=0)
    matching = [c for c in all_confs if c.id == cid]
    assert matching[-1].status == "rejected"


def test_approve_unknown_id_returns_404(client_and_orch):
    client, _ = client_and_orch
    r = client.post("/api/confirmations/doesnotexist/approve")
    assert r.status_code == 404


def test_reject_unknown_id_returns_404(client_and_orch):
    client, _ = client_and_orch
    r = client.post("/api/confirmations/doesnotexist/reject")
    assert r.status_code == 404
