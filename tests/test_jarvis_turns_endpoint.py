"""Tests: /api/jarvis/turns persistence + chat handler append-on-done."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis import chat_turns  # noqa: E402
from jarvis.chat_turns import ChatTurnRecord, append_turn  # noqa: E402
from jarvis.contract import TraceEvent  # noqa: E402
from jarvis.web.api import make_app  # noqa: E402


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point chat_turns store at a tmp file and disable bearer auth."""
    target = tmp_path / "chat_turns.jsonl"
    monkeypatch.setattr(chat_turns, "_default_path", lambda: target)
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)
    return target


def _make_client(stream_events: list[TraceEvent]) -> TestClient:
    async def _fake_stream(message: str):
        for ev in stream_events:
            yield ev

    mock_chat = MagicMock()
    mock_chat.stream = _fake_stream

    app = make_app()
    app.state.jarvis_chat["instance"] = mock_chat
    return TestClient(app)


def test_turns_endpoint_returns_persisted_records(isolated_state: Path) -> None:
    append_turn(
        ChatTurnRecord(
            user_id="default",
            turn_id="t-stored",
            user_text="hi",
            assistant_text="hello",
            tool_calls=[],
            model="opus",
            cost_usd=0.0,
            duration_ms=42,
            ts="2026-05-05T12:00:00+00:00",
        )
    )

    client = _make_client([])
    res = client.get("/api/jarvis/turns?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["error"] is None
    assert len(body["data"]) == 1
    assert body["data"][0]["turn_id"] == "t-stored"


def test_chat_handler_persists_turn_on_done(isolated_state: Path) -> None:
    events = [
        TraceEvent(
            type="model",
            request_id="r1",
            agent="jarvis",
            payload={"model": "claude-opus-4-7"},
        ),
        TraceEvent(
            type="text", request_id="r1", agent="jarvis", payload={"delta": "hello "}
        ),
        TraceEvent(
            type="text", request_id="r1", agent="jarvis", payload={"delta": "world"}
        ),
        TraceEvent(
            type="tool_use",
            request_id="r1",
            agent="jarvis",
            payload={
                "tool_use_id": "tu-1",
                "name": "delegate",
                "agent": "tempo",
                "action": "read_inbox",
                "args": {},
            },
        ),
        TraceEvent(
            type="tool_result",
            request_id="r1",
            agent="jarvis",
            payload={"tool_use_id": "tu-1", "is_error": False, "text": "{}"},
        ),
        TraceEvent(
            type="done",
            request_id="r1",
            agent="jarvis",
            payload={"duration_ms": 123, "total_cost_usd": 0.001},
        ),
    ]
    client = _make_client(events)

    with client.stream("POST", "/api/jarvis/chat", json={"message": "ping"}) as resp:
        assert resp.status_code == 200
        # Drain the SSE stream so the generator's finally block runs.
        for _ in resp.iter_lines():
            pass

    res = client.get("/api/jarvis/turns?limit=10")
    body = res.json()
    assert len(body["data"]) == 1
    rec = body["data"][0]
    assert rec["user_text"] == "ping"
    assert rec["assistant_text"] == "hello world"
    assert rec["model"] == "claude-opus-4-7"
    assert rec["cost_usd"] == pytest.approx(0.001)
    assert rec["duration_ms"] == 123
    assert len(rec["tool_calls"]) == 1
    assert rec["tool_calls"][0]["agent"] == "tempo"
    assert rec["tool_calls"][0]["result"]["is_error"] is False


def test_turns_endpoint_rejects_bad_limit(isolated_state: Path) -> None:
    client = _make_client([])
    res = client.get("/api/jarvis/turns?limit=0")
    assert res.status_code == 422
    res = client.get("/api/jarvis/turns?limit=9999")
    assert res.status_code == 422


def test_turns_scoped_by_bearer_user_id(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two different bearer tokens = two different user_ids = isolated histories."""
    monkeypatch.setenv("JARVIS_API_TOKEN", "shared-token")

    # Store under the user_id derived from "shared-token"
    from jarvis.chat_turns import user_id_from_token

    uid = user_id_from_token("shared-token")
    append_turn(
        ChatTurnRecord(
            user_id=uid,
            turn_id="t-mine",
            user_text="hi",
            assistant_text="ok",
            tool_calls=[],
            model="",
            cost_usd=0.0,
            duration_ms=0,
            ts="2026-05-05T12:00:00+00:00",
        )
    )
    # And one under a different user
    append_turn(
        ChatTurnRecord(
            user_id="other-user",
            turn_id="t-other",
            user_text="hi",
            assistant_text="ok",
            tool_calls=[],
            model="",
            cost_usd=0.0,
            duration_ms=0,
            ts="2026-05-05T12:00:00+00:00",
        )
    )

    client = _make_client([])
    res = client.get(
        "/api/jarvis/turns?limit=10",
        headers={"Authorization": "Bearer shared-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert [r["turn_id"] for r in body["data"]] == ["t-mine"]

    # Ensure auth env doesn't leak to other tests.
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    if "JARVIS_API_TOKEN" in os.environ:
        del os.environ["JARVIS_API_TOKEN"]
