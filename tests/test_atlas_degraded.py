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
