"""Agent contract envelope shape tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.contract import AgentResponse, InboxEvent, IntentClassification, Task


def test_agent_response_minimal():
    r = AgentResponse(agent="aide", intent="triage", action="done")
    assert r.confidence == 1.0
    assert r.needs_confirm is False
    assert r.follow_ups == []
    assert r.result == {}
    assert len(r.request_id) == 12
    assert r.ts.endswith("+00:00")


def test_agent_response_confidence_bounds():
    with pytest.raises(ValidationError):
        AgentResponse(agent="x", intent="y", action="z", confidence=1.5)
    with pytest.raises(ValidationError):
        AgentResponse(agent="x", intent="y", action="z", confidence=-0.1)


def test_task_default_status():
    t = Task(title="ship phase 1")
    assert t.status == "open"
    assert t.tags == []


def test_task_status_validation():
    with pytest.raises(ValidationError):
        Task(title="x", status="weird")


def test_inbox_event_serializes():
    e = InboxEvent(agent="sentinel", severity="alert", summary="atlas drawdown")
    payload = e.model_dump_json()
    assert "alert" in payload
    assert "atlas drawdown" in payload


def test_intent_classification_shape():
    c = IntentClassification(
        primary="aide", confidence=0.9, rationale="email keyword", raw_request="check inbox"
    )
    assert c.parallel == []
