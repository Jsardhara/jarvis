"""Atlas degraded-mode tests.

Tests the health-check gate, degraded flag propagation, caching, and
pipeline-level degradation when ATLAS is offline.
"""
from __future__ import annotations

import time

import httpx
import respx

from jarvis.subsystems.atlas import AtlasBridge, AtlasOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_online_orchestrator(base_url: str = "http://atlas-test:8000") -> AtlasOrchestrator:
    bridge = AtlasBridge(base_url=base_url)
    return AtlasOrchestrator(bridge=bridge, allow_mock=True, auto_mock_on_offline=True)


def _make_offline_orchestrator(base_url: str = "http://atlas-offline:9999") -> AtlasOrchestrator:
    bridge = AtlasBridge(base_url=base_url)
    return AtlasOrchestrator(bridge=bridge, allow_mock=True, auto_mock_on_offline=True)


# ---------------------------------------------------------------------------
# test_atlas_returns_mock_with_degraded_flag_when_offline
# ---------------------------------------------------------------------------


def test_atlas_returns_mock_with_degraded_flag_when_offline():
    """When ATLAS is unreachable, portfolio returns mock data with meta.degraded=True."""
    with respx.mock(base_url="http://atlas-offline:9999", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        orch = _make_offline_orchestrator()
        resp = orch.portfolio()
    assert resp.action == "fetched"
    assert resp.result.get("mock") is True
    assert resp.result.get("meta", {}).get("degraded") is True


def test_atlas_returns_mock_pnl_with_degraded_flag_when_offline():
    """When ATLAS is unreachable, pnl returns mock data with meta.degraded=True."""
    with respx.mock(base_url="http://atlas-offline:9999", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        orch = _make_offline_orchestrator()
        resp = orch.pnl("7d")
    assert resp.result.get("mock") is True
    assert resp.result.get("meta", {}).get("degraded") is True


def test_atlas_returns_mock_positions_with_degraded_flag_when_offline():
    """When ATLAS is unreachable, positions returns mock data with meta.degraded=True."""
    with respx.mock(base_url="http://atlas-offline:9999", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        orch = _make_offline_orchestrator()
        resp = orch.positions()
    assert resp.result.get("mock") is True
    assert resp.result.get("meta", {}).get("degraded") is True


def test_atlas_oracle_scan_degraded_when_offline():
    """oracle_scan falls to mock with degraded flag when ATLAS offline."""
    with respx.mock(base_url="http://atlas-offline:9999", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        orch = _make_offline_orchestrator()
        resp = orch.oracle_scan()
    assert resp.result.get("meta", {}).get("degraded") is True


# ---------------------------------------------------------------------------
# test_atlas_returns_real_data_when_online
# ---------------------------------------------------------------------------


def test_atlas_returns_real_data_when_online():
    """When ATLAS responds 200, portfolio uses live data and degraded is absent/False."""
    portfolio_data = {
        "total_value_usd": 50000.0,
        "cash": 10000.0,
        "holdings": [{"symbol": "BTC", "qty": 0.5, "value_usd": 40000.0}],
    }
    with respx.mock(base_url="http://atlas-test:8000", assert_all_called=False) as mock:
        mock.get("/api/health").mock(return_value=httpx.Response(200, json={"ok": True}))
        mock.get("/portfolio").mock(return_value=httpx.Response(200, json=portfolio_data))
        orch = _make_online_orchestrator()
        resp = orch.portfolio()
    assert resp.result.get("mock") is False
    assert resp.result.get("meta", {}).get("degraded") is not True
    assert resp.result["portfolio"]["total_value_usd"] == 50000.0


# ---------------------------------------------------------------------------
# test_health_check_caches_result
# ---------------------------------------------------------------------------


def test_health_check_caches_result():
    """_health_check result is cached; only one HTTP hit within the TTL window."""
    call_count = 0

    def _count_and_fail(request):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("refused")

    with respx.mock(base_url="http://atlas-cached:9998", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=_count_and_fail)
        bridge = AtlasBridge(base_url="http://atlas-cached:9998")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=True, auto_mock_on_offline=True)
        # Force cache miss first, then second call within TTL should reuse cache
        orch._health_check()
        orch._health_check()
    assert call_count == 1, f"Expected 1 HTTP call (cached), got {call_count}"


def test_health_check_cache_expires():
    """After TTL seconds, _health_check re-probes the server."""
    call_count = 0

    def _count_and_fail(request):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("refused")

    with respx.mock(base_url="http://atlas-expire:9997", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=_count_and_fail)
        bridge = AtlasBridge(base_url="http://atlas-expire:9997")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=True, auto_mock_on_offline=True)
        orch._health_check()
        # Force expiry by backdating the cache
        orch._health_cache = (False, time.monotonic() - orch._health_ttl_seconds - 1)
        orch._health_check()
    assert call_count == 2, f"Expected 2 HTTP calls (TTL expired), got {call_count}"


# ---------------------------------------------------------------------------
# test_pipeline_propagates_degraded
# ---------------------------------------------------------------------------


def test_pipeline_propagates_degraded():
    """pipeline() in offline mode still completes and carries degraded flag in result."""
    with respx.mock(base_url="http://atlas-offline:9999", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        orch = _make_offline_orchestrator()
        resp = orch.pipeline()
    # Pipeline completes (proposed or vetoed) — degraded propagated
    assert resp.result.get("meta", {}).get("degraded") is True
    assert resp.action in ("proposed", "vetoed", "halted")


def test_auto_mock_disabled_does_not_check_health():
    """When auto_mock_on_offline=False, health check is never called; exceptions propagate."""
    bridge = AtlasBridge(base_url="http://atlas-no-check:9996")
    orch = AtlasOrchestrator(bridge=bridge, allow_mock=True, auto_mock_on_offline=False)
    # Without auto_mock_on_offline, portfolio still falls back via allow_mock
    resp = orch.portfolio()
    assert resp.result.get("mock") is True
    # No degraded flag since health gate was not consulted
    assert resp.result.get("meta", {}).get("degraded") is not True


# ---------- Live HTTP tests with respx ----------


def test_atlas_bridge_portfolio_timeout():
    """AtlasBridge.portfolio() handles timeout gracefully."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/portfolio").mock(side_effect=httpx.TimeoutException("timeout"))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.portfolio()
    assert result is None


def test_atlas_bridge_positions_http_error():
    """AtlasBridge.open_positions() handles 4xx/5xx gracefully."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/trades/open").mock(return_value=httpx.Response(500))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.open_positions()
    assert result is None


def test_atlas_bridge_pnl_success_with_window():
    """AtlasBridge.pnl() sets default window if missing."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/trades/stats").mock(return_value=httpx.Response(200, json={
            "pnl_usd": 100.0,
            "pnl_pct": 0.01,
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.pnl(window="30d")
    assert result["window"] == "30d"


def test_atlas_bridge_strategies_extracts_from_dict():
    """AtlasBridge.strategies() extracts from dict with 'strategies' key."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/strategies").mock(return_value=httpx.Response(200, json={
            "strategies": [
                {"id": "s1", "score": 0.9},
                {"id": "s2", "score": 0.7},
            ],
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.strategies()
    assert len(result) == 2
    assert result[0]["id"] == "s1"


def test_atlas_bridge_run_strategy_success():
    """AtlasBridge.run_strategy() POSTs with mode parameter."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        route = mock.post("/strategies/test_strat/activate")
        route.mock(return_value=httpx.Response(200, json={
            "run_id": "r123",
            "status": "queued",
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.run_strategy("test_strat", mode="live")
    assert result["run_id"] == "r123"


def test_atlas_orchestrator_positions_count():
    """AtlasOrchestrator.positions() includes position count."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/api/health").mock(return_value=httpx.Response(200))
        mock.get("/trades/open").mock(return_value=httpx.Response(200, json=[
            {"id": "p1"},
            {"id": "p2"},
            {"id": "p3"},
        ]))
        bridge = AtlasBridge(base_url="http://test")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=False, auto_mock_on_offline=True)
        resp = orch.positions()
    assert resp.result["count"] == 3


def test_atlas_orchestrator_architect_rank_with_regime():
    """AtlasOrchestrator.architect_rank() filters by regime."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/api/health").mock(return_value=httpx.Response(200))
        mock.get("/strategies").mock(return_value=httpx.Response(200, json=[
            {"id": "risk_on_strat", "score": 0.9, "regime_fit": "risk_on"},
            {"id": "risk_off_strat", "score": 0.8, "regime_fit": "risk_off"},
            {"id": "neutral_strat", "score": 0.7, "regime_fit": "neutral"},
        ]))
        bridge = AtlasBridge(base_url="http://test")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=False, auto_mock_on_offline=True)
        resp = orch.architect_rank(regime="risk_on")
    ranked = resp.result["ranked"]
    assert ranked[0]["id"] == "risk_on_strat"


def test_atlas_bridge_market_scan_fallback():
    """AtlasBridge.market_scan() falls back from /market/scan to /oracle/scan."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/market/scan").mock(side_effect=httpx.ConnectError("refused"))
        mock.get("/oracle/scan").mock(return_value=httpx.Response(200, json={
            "regime": "neutral",
            "top_movers": [],
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.market_scan()
    assert result is not None
    assert result["regime"] == "neutral"


def test_atlas_bridge_health_fallback():
    """AtlasBridge.health() falls back from /system/health to /health."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/system/health").mock(side_effect=httpx.ConnectError("refused"))
        mock.get("/health").mock(return_value=httpx.Response(200, json={}))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.health()
    assert result is True


def test_atlas_bridge_open_positions_dict_with_trades_key():
    """AtlasBridge.open_positions() extracts from dict with 'trades' key."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/trades/open").mock(return_value=httpx.Response(200, json={
            "trades": [
                {"id": "t1", "symbol": "BTC/USD"},
            ],
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.open_positions()
    assert len(result) == 1


def test_atlas_bridge_open_positions_dict_with_positions_key():
    """AtlasBridge.open_positions() extracts from dict with 'positions' key."""
    with respx.mock(base_url="http://test", assert_all_called=False) as mock:
        mock.get("/trades/open").mock(return_value=httpx.Response(200, json={
            "positions": [
                {"id": "p1", "symbol": "ETH/USD"},
            ],
        }))
        bridge = AtlasBridge(base_url="http://test")
        result = bridge.open_positions()
    assert len(result) == 1
