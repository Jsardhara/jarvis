"""Tests: SSE pass-through for GET /api/atlas/agents/{id}/chat/stream."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.apps.api.app import make_app  # noqa: E402


def _make_app_with_bridge(bridge: MagicMock, mode: str = "live") -> TestClient:
    from jarvis.agents.atlas.agent import AtlasOrchestrator

    orchestrator = AtlasOrchestrator(bridge=bridge, mode=mode)
    app = make_app()
    atlas_desc = app.state.registry.get("atlas")
    if atlas_desc is not None:
        atlas_desc.instance = orchestrator
    return TestClient(app)


def _make_sse_mocks(sse_chunks: list[bytes]) -> tuple[Any, MagicMock]:
    """Build the two-level async context manager mock for httpx.AsyncClient.

    The production code does:
        async with httpx.AsyncClient() as client:          # level 1
            async with client.stream(...) as upstream:     # level 2
                async for chunk in upstream.aiter_bytes(): ...

    Returns (mock_client_cls_to_patch, upstream_fake).
    """

    class _FakeUpstream:
        async def __aenter__(self) -> _FakeUpstream:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aiter_bytes(self):  # type: ignore[override]
            for chunk in sse_chunks:
                yield chunk

    fake_upstream = _FakeUpstream()

    # Level-1 mock: the AsyncClient instance returned by AsyncClient()
    mock_async_client = MagicMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=False)
    mock_async_client.stream.return_value = fake_upstream

    # Level-0 mock: the AsyncClient class itself (called as a constructor)
    mock_cls = MagicMock(return_value=mock_async_client)

    return mock_cls, mock_async_client


def _inject_atlas_live(app: Any, bridge: MagicMock) -> None:
    from jarvis.agents.atlas.agent import AtlasOrchestrator

    atlas_desc = app.state.registry.get("atlas")
    if atlas_desc is not None:
        atlas_desc.instance = AtlasOrchestrator(bridge=bridge, mode="live")


def test_sse_stream_chunks_forwarded_in_order() -> None:
    """SSE chunks from Atlas arrive in order and content-type is text/event-stream."""
    sse_chunks = [
        b'data: {"type": "text", "delta": "chunk1"}\n\n',
        b'data: {"type": "text", "delta": "chunk2"}\n\n',
        b'data: {"type": "done"}\n\n',
    ]

    bridge = MagicMock()
    bridge._token = "test-bearer"
    bridge.base_url = "http://atlas-test:8000"

    mock_cls, _ = _make_sse_mocks(sse_chunks)

    with patch("jarvis.apps.api.atlas_proxy.httpx.AsyncClient", mock_cls):
        app = make_app()
        _inject_atlas_live(app, bridge)
        client = TestClient(app)
        with client.stream("GET", "/api/atlas/agents/oracle/chat/stream") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = b"".join(resp.iter_bytes())

    assert b"chunk1" in body
    assert b"chunk2" in body
    assert b"done" in body
    # Chunks must appear in order
    idx1 = body.index(b"chunk1")
    idx2 = body.index(b"chunk2")
    assert idx1 < idx2


def test_sse_503_when_mock_mode() -> None:
    """SSE endpoint returns 503 when atlas is in mock mode."""
    bridge = MagicMock()
    bridge._token = "tok"
    bridge.base_url = "http://atlas-test:8000"

    client = _make_app_with_bridge(bridge, mode="mock")
    r = client.get("/api/atlas/agents/oracle/chat/stream")
    assert r.status_code == 503
    assert "mock" in r.json()["detail"].lower()


def test_sse_bearer_not_exposed_in_response() -> None:
    """Bearer token used to reach Atlas is never echoed to the SSE client."""
    sse_chunks = [b'data: {"type": "text", "delta": "safe"}\n\n']

    bridge = MagicMock()
    bridge._token = "super-secret-bearer"
    bridge.base_url = "http://atlas-test:8000"

    mock_cls, _ = _make_sse_mocks(sse_chunks)

    with patch("jarvis.apps.api.atlas_proxy.httpx.AsyncClient", mock_cls):
        app = make_app()
        _inject_atlas_live(app, bridge)
        client = TestClient(app)
        with client.stream("GET", "/api/atlas/agents/oracle/chat/stream") as resp:
            body = b"".join(resp.iter_bytes())
            assert b"super-secret-bearer" not in body
            for header_val in resp.headers.values():
                assert "super-secret-bearer" not in header_val
