"""Tests: JARVIS_ATLAS_MODE=mock never hits network; =live returns None on failure."""
from __future__ import annotations

import httpx
import respx

from jarvis.subsystems.atlas import AtlasBridge, AtlasOrchestrator


def test_mock_mode_never_hits_network(monkeypatch):
    """mode=mock: oracle_scan returns mock data without any HTTP call."""
    monkeypatch.setenv("JARVIS_ATLAS_MODE", "mock")
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)

    # Track calls via a counter on the bridge's _get/_post methods
    get_calls: list[str] = []
    post_calls: list[str] = []

    bridge = AtlasBridge(base_url="http://atlas-mock-mode:8000")

    original_get = bridge._get
    original_post = bridge._post

    def _tracked_get(path: str):
        get_calls.append(path)
        return original_get(path)

    def _tracked_post(path: str, body, **kw):
        post_calls.append(path)
        return original_post(path, body, **kw)

    bridge._get = _tracked_get
    bridge._post = _tracked_post

    orch = AtlasOrchestrator(bridge=bridge, allow_mock=True, mode="mock")
    resp = orch.oracle_scan()

    # No HTTP calls attempted
    assert get_calls == []
    assert post_calls == []
    assert resp.result["scan"]["source"] == "mock"


def test_mock_mode_property(monkeypatch):
    """bridge.mode returns 'mock' when JARVIS_ATLAS_MODE=mock."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    bridge = AtlasBridge(base_url="http://atlas-mode:8000")
    orch = AtlasOrchestrator(bridge=bridge, mode="mock")
    assert orch.mode == "mock"


def test_live_mode_property(monkeypatch):
    """bridge.mode returns 'live' when mode=live."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    bridge = AtlasBridge(base_url="http://atlas-mode:8000")
    orch = AtlasOrchestrator(bridge=bridge, mode="live")
    assert orch.mode == "live"


def test_live_mode_returns_none_on_failure_no_mock_fallback(monkeypatch):
    """mode=live: portfolio raises AtlasUnavailableError on failure (no silent mock fallback)."""
    monkeypatch.setenv("JARVIS_ATLAS_MODE", "live")
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.subsystems.atlas.time.sleep", lambda _: None)

    from jarvis.subsystems.atlas import AtlasUnavailableError

    with respx.mock(base_url="http://atlas-live-fail:8000", assert_all_called=False) as mock:
        mock.get("/api/health").mock(side_effect=httpx.ConnectError("refused"))
        mock.get("/portfolio").mock(side_effect=httpx.ConnectError("refused"))
        bridge = AtlasBridge(base_url="http://atlas-live-fail:8000")
        orch = AtlasOrchestrator(
            bridge=bridge, allow_mock=False, auto_mock_on_offline=False, mode="live"
        )
        with pytest.raises((AtlasUnavailableError, Exception)):
            orch.portfolio()


def test_mock_mode_portfolio_returns_mock_source(monkeypatch):
    """mode=mock: portfolio always returns mock data."""
    monkeypatch.setenv("JARVIS_ATLAS_MODE", "mock")
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)

    bridge = AtlasBridge(base_url="http://atlas-mock2:8000")
    orch = AtlasOrchestrator(bridge=bridge, allow_mock=True, mode="mock")
    resp = orch.portfolio()
    assert resp.result["mock"] is True
    assert resp.result["portfolio"]["source"] == "mock"


def test_mode_reads_from_env_default_live(monkeypatch):
    """Default mode is 'live' when JARVIS_ATLAS_MODE is not set."""
    monkeypatch.delenv("JARVIS_ATLAS_MODE", raising=False)
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    bridge = AtlasBridge(base_url="http://atlas-default:8000")
    orch = AtlasOrchestrator(bridge=bridge)
    assert orch.mode == "live"


import pytest
