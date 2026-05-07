"""Tests: Atlas proxy routes in /api/atlas/* forward to Atlas via AtlasBridge.

These tests use httpx.MockTransport / respx to intercept Atlas-bound requests
without starting a real Atlas server.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.web.api import make_app  # noqa: E402

# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_bridge(responses: dict[str, Any]) -> MagicMock:
    """Build a fake AtlasBridge whose _client.get/post return canned JSON."""
    bridge = MagicMock()
    bridge._token = "test-bearer-token"

    def _fake_get(path: str, **kwargs: Any) -> httpx.Response:
        data = responses.get(path, {"ok": True})
        return httpx.Response(200, json=data)

    bridge._client.get = _fake_get
    return bridge


def _make_app_with_bridge(bridge: MagicMock, mode: str = "live") -> TestClient:
    """Build TestClient with a patched AtlasOrchestrator.bridge."""
    from jarvis.subsystems.atlas import AtlasOrchestrator

    orchestrator = AtlasOrchestrator(bridge=bridge, mode=mode)
    app = make_app()
    # Inject into the registry that make_app built
    atlas_desc = app.state.registry.get("atlas")
    if atlas_desc is not None:
        atlas_desc.instance = orchestrator
    return TestClient(app)


# ── Mock-mode guard ───────────────────────────────────────────────────────────


def test_proxy_503_when_atlas_mode_mock() -> None:
    """All proxy routes return 503 when AtlasOrchestrator.mode == 'mock'."""
    bridge = _mock_bridge({})
    client = _make_app_with_bridge(bridge, mode="mock")

    r = client.get("/api/atlas/portfolio")
    assert r.status_code == 503
    assert "mock" in r.json()["detail"].lower()


# ── Unreachable guard ─────────────────────────────────────────────────────────


def test_proxy_503_when_atlas_unreachable() -> None:
    """ConnectError after retries → 503 atlas unreachable."""
    bridge = MagicMock()
    bridge._token = "tok"
    bridge._client.get.side_effect = httpx.ConnectError("refused")

    client = _make_app_with_bridge(bridge, mode="live")
    r = client.get("/api/atlas/portfolio")
    assert r.status_code == 503
    assert "unreachable" in r.json()["detail"].lower()


# ── Route: GET /api/atlas/portfolio ──────────────────────────────────────────


def test_portfolio_forwards_path() -> None:
    """GET /api/atlas/portfolio → Atlas GET /portfolio, returns body unchanged."""
    bridge = _mock_bridge({"/portfolio": {"total_value_usd": 9999.0}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/portfolio")
    assert r.status_code == 200
    assert r.json()["total_value_usd"] == 9999.0


def test_portfolio_bearer_not_leaked_in_response() -> None:
    """Bearer token must not appear in any response header or body."""
    bridge = _mock_bridge({"/portfolio": {"data": "safe"}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/portfolio")
    assert "test-bearer-token" not in r.text
    assert "authorization" not in {k.lower() for k in r.headers}


# ── Route: GET /api/atlas/portfolio/history ──────────────────────────────────


def test_portfolio_history_forwards_path() -> None:
    """GET /api/atlas/portfolio/history → Atlas GET /portfolio/history."""
    bridge = _mock_bridge({"/portfolio/history": [{"ts": "2026-01-01", "value": 5000}]})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/portfolio/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Route: GET /api/atlas/trades ─────────────────────────────────────────────


def test_trades_passthrough_query_params() -> None:
    """Query params status, limit, offset, pair are forwarded to Atlas."""
    captured: dict[str, Any] = {}

    bridge = MagicMock()
    bridge._token = "tok"

    def _fake_get(path: str, params: dict | None = None, **kwargs: Any) -> httpx.Response:
        captured["path"] = path
        captured["params"] = params or {}
        return httpx.Response(200, json={"trades": []})

    bridge._client.get = _fake_get

    client = _make_app_with_bridge(bridge, mode="live")
    r = client.get("/api/atlas/trades?status=open&limit=50&offset=10&pair=BTC/USD")

    assert r.status_code == 200
    assert captured["path"] == "/trades"
    assert captured["params"].get("status") == "open"
    assert str(captured["params"].get("limit")) == "50"
    assert str(captured["params"].get("offset")) == "10"
    assert captured["params"].get("pair") == "BTC/USD"


def test_trades_open_endpoint() -> None:
    """GET /api/atlas/trades/open → Atlas GET /trades/open."""
    captured: dict[str, Any] = {}

    bridge = MagicMock()
    bridge._token = "tok"

    def _fake_get(path: str, **kwargs: Any) -> httpx.Response:
        captured["path"] = path
        return httpx.Response(200, json=[])

    bridge._client.get = _fake_get
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/trades/open")
    assert r.status_code == 200
    assert captured["path"] == "/trades/open"


def test_trades_stats_endpoint() -> None:
    """GET /api/atlas/trades/stats → Atlas GET /trades/stats."""
    bridge = _mock_bridge({"/trades/stats": {"pnl_usd": 42.0}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/trades/stats")
    assert r.status_code == 200
    assert r.json()["pnl_usd"] == 42.0


def test_trade_by_id_endpoint() -> None:
    """GET /api/atlas/trades/{trade_id} → Atlas GET /trades/{trade_id}."""
    bridge = _mock_bridge({"/trades/t123": {"id": "t123", "pair": "ETH/USD"}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/trades/t123")
    assert r.status_code == 200
    assert r.json()["id"] == "t123"


# ── Route: GET /api/atlas/signals ────────────────────────────────────────────


def test_signals_with_limit() -> None:
    """GET /api/atlas/signals?limit=10 → Atlas GET /signals with limit param."""
    captured: dict[str, Any] = {}

    bridge = MagicMock()
    bridge._token = "tok"

    def _fake_get(path: str, params: dict | None = None, **kwargs: Any) -> httpx.Response:
        captured["path"] = path
        captured["params"] = params or {}
        return httpx.Response(200, json={"signals": []})

    bridge._client.get = _fake_get
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/signals?limit=10")
    assert r.status_code == 200
    assert captured["path"] == "/signals"
    assert str(captured["params"].get("limit")) == "10"


def test_signals_active_endpoint() -> None:
    """GET /api/atlas/signals/active → Atlas GET /signals/active."""
    bridge = _mock_bridge({"/signals/active": {"signals": [{"id": "s1"}]}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/signals/active")
    assert r.status_code == 200


# ── Route: GET /api/atlas/strategies ────────────────────────────────────────


def test_strategies_list() -> None:
    """GET /api/atlas/strategies → Atlas GET /strategies."""
    bridge = _mock_bridge({"/strategies": [{"id": "trend_v1"}]})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/strategies")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "trend_v1"


def test_strategy_by_id() -> None:
    """GET /api/atlas/strategies/{id} → Atlas GET /strategies/{id}."""
    bridge = _mock_bridge({"/strategies/trend_v1": {"id": "trend_v1", "score": 0.9}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/strategies/trend_v1")
    assert r.status_code == 200
    assert r.json()["score"] == 0.9


# ── Route: GET /api/atlas/agents ────────────────────────────────────────────


def test_agents_list() -> None:
    """GET /api/atlas/agents → Atlas GET /agents."""
    bridge = _mock_bridge({"/agents": [{"id": "oracle"}]})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/agents")
    assert r.status_code == 200
    assert r.json()[0]["id"] == "oracle"


def test_agent_by_id() -> None:
    """GET /api/atlas/agents/{id} → Atlas GET /agents/{id}."""
    bridge = _mock_bridge({"/agents/oracle": {"id": "oracle", "status": "idle"}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/agents/oracle")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"


def test_agent_memory() -> None:
    """GET /api/atlas/agents/{id}/memory → Atlas GET /agents/{id}/memory."""
    bridge = _mock_bridge({"/agents/oracle/memory": {"entries": []}})
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.get("/api/atlas/agents/oracle/memory")
    assert r.status_code == 200


# ── Route: POST /api/atlas/agents/{id}/chat ──────────────────────────────────


def test_agent_chat_post_body_passthrough() -> None:
    """POST /api/atlas/agents/{id}/chat forwards body to Atlas POST /agents/{id}/chat."""
    captured: dict[str, Any] = {}

    bridge = MagicMock()
    bridge._token = "tok"

    def _fake_post(
        path: str, json: dict | None = None, **kwargs: Any
    ) -> httpx.Response:
        captured["path"] = path
        captured["body"] = json or {}
        return httpx.Response(200, json={"reply": "hello"})

    bridge._client.post = _fake_post
    client = _make_app_with_bridge(bridge, mode="live")

    r = client.post(
        "/api/atlas/agents/oracle/chat",
        json={"message": "scan the market", "session_id": "s1"},
    )
    assert r.status_code == 200
    assert captured["path"] == "/agents/oracle/chat"
    assert captured["body"]["message"] == "scan the market"
    assert r.json()["reply"] == "hello"


# ── Route: Atlas 4xx/5xx forwarded unchanged ─────────────────────────────────


def test_atlas_404_forwarded() -> None:
    """Atlas 404 is forwarded with same status code."""
    bridge = MagicMock()
    bridge._token = "tok"
    bridge._client.get.return_value = httpx.Response(404, json={"detail": "not found"})

    client = _make_app_with_bridge(bridge, mode="live")
    r = client.get("/api/atlas/trades/nonexistent")
    assert r.status_code == 404


def test_atlas_401_returns_502() -> None:
    """Atlas 401 (bearer rejected) → Jarvis returns 502, not 401 (don't leak auth info)."""
    bridge = MagicMock()
    bridge._token = "tok"
    bridge._client.get.return_value = httpx.Response(
        401, json={"detail": "unauthorized"}
    )

    client = _make_app_with_bridge(bridge, mode="live")
    r = client.get("/api/atlas/portfolio")
    assert r.status_code == 502
    # Bearer token must not appear in response body
    assert "tok" not in r.text
    assert "unauthorized" not in r.text.lower()
