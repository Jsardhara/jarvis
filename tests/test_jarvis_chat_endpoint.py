"""Tests: POST /api/jarvis/terminal routes through JarvisChat (Atlas reverse path)."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.apps.api.app import make_app


def _make_client_with_mock_chat():
    """Build a TestClient with JarvisChat stubbed out."""
    from unittest.mock import MagicMock

    from jarvis.contract import TraceEvent

    async def _fake_stream(message: str):
        yield TraceEvent(
            type="text",
            request_id="r1",
            agent="jarvis",
            payload={"delta": f"echo:{message}"},
        )
        yield TraceEvent(
            type="done",
            request_id="r1",
            agent="jarvis",
            payload={"duration_ms": 10},
        )

    mock_chat = MagicMock()
    mock_chat.stream = _fake_stream

    app = make_app()
    # Inject mock via app.state.jarvis_chat (the shared dict inside make_app closure)
    app.state.jarvis_chat["instance"] = mock_chat
    return TestClient(app)


def test_terminal_endpoint_returns_response():
    """POST /api/jarvis/terminal returns {response, session_id}."""
    client = _make_client_with_mock_chat()
    r = client.post(
        "/api/jarvis/terminal",
        json={"message": "hello", "session_id": "sess-001"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "session_id" in body
    assert body["session_id"] == "sess-001"
    assert "echo:hello" in body["response"]


def test_terminal_endpoint_empty_message():
    """POST /api/jarvis/terminal with empty message returns 400."""
    client = _make_client_with_mock_chat()
    r = client.post(
        "/api/jarvis/terminal",
        json={"message": "", "session_id": "sess-001"},
    )
    assert r.status_code == 400


def test_terminal_endpoint_missing_session_id():
    """POST /api/jarvis/terminal without session_id still works — defaults to empty string."""
    client = _make_client_with_mock_chat()
    r = client.post("/api/jarvis/terminal", json={"message": "ping"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == ""


def test_streaming_chat_still_works():
    """Original POST /api/jarvis/chat (streaming SSE) remains functional."""
    from unittest.mock import MagicMock

    from jarvis.contract import TraceEvent

    async def _fake_stream(message: str):
        yield TraceEvent(
            type="text",
            request_id="r2",
            agent="jarvis",
            payload={"delta": "pong"},
        )

    mock_chat = MagicMock()
    mock_chat.stream = _fake_stream

    app = make_app()
    app.state.jarvis_chat["instance"] = mock_chat
    client = TestClient(app)

    with client.stream("POST", "/api/jarvis/chat", json={"message": "ping"}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
