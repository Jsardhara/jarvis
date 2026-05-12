"""Tests: Atlas pipeline envelope parsing — status/correlation_id/result/job_id."""
from __future__ import annotations

import httpx
import respx

from jarvis.agents.atlas.agent import AtlasBridge, AtlasOrchestrator, _parse_pipeline_envelope


def test_parse_envelope_ok_status():
    """status='ok' envelope returns action with payload."""
    raw = {
        "status": "ok",
        "correlation_id": "corr-abc",
        "result": {"regime": "risk_on"},
    }
    resp = _parse_pipeline_envelope(
        raw, "atlas.oracle", "market_scan", "scanned", {}, base_confidence=0.8
    )
    assert resp.action == "scanned"
    assert resp.result["correlation_id"] == "corr-abc"
    assert resp.result["payload"]["regime"] == "risk_on"
    assert resp.confidence == 0.8


def test_parse_envelope_timeout_status():
    """status='timeout' lowers confidence and adds poll follow_up."""
    raw = {
        "status": "timeout",
        "correlation_id": "corr-xyz",
        "result": {},
        "job_id": "job-999",
    }
    resp = _parse_pipeline_envelope(
        raw, "atlas.oracle", "market_scan", "scanned", {}, base_confidence=0.8
    )
    assert resp.action == "pending"
    assert resp.confidence < 0.8
    assert any("job_id=job-999" in fu for fu in resp.follow_ups)


def test_parse_envelope_202_job_id():
    """HTTP 202 with job_id triggers pending action."""
    raw = {
        "status": "ok",
        "correlation_id": "corr-202",
        "result": {},
        "job_id": "job-202",
    }
    resp = _parse_pipeline_envelope(
        raw, "atlas.trader", "execute_strategy", "proposed", {}, base_confidence=0.9
    )
    assert resp.action == "pending"
    assert resp.result["job_id"] == "job-202"


def test_parse_envelope_none_input():
    """None input returns unavailable AgentResponse."""
    resp = _parse_pipeline_envelope(
        None, "atlas.oracle", "market_scan", "scanned", {}, base_confidence=0.8
    )
    assert resp.action == "unavailable"
    assert resp.confidence == 0.0
    assert len(resp.follow_ups) > 0


def test_oracle_scan_parses_live_envelope(monkeypatch):
    """oracle_scan calls /pipeline/oracle-scan and parses the envelope."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    envelope = {
        "status": "ok",
        "correlation_id": "c1",
        "result": {"regime": "risk_on", "top_movers": []},
    }

    with respx.mock(base_url="http://atlas-envelope:8000", assert_all_called=False) as mock:
        mock.get("/api/health").mock(return_value=httpx.Response(200))
        mock.post("/pipeline/oracle-scan").mock(
            return_value=httpx.Response(200, json=envelope)
        )
        bridge = AtlasBridge(base_url="http://atlas-envelope:8000")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=False, mode="live")
        orch._health_cache = (True, float("inf"))
        resp = orch.oracle_scan()

    assert resp.agent == "atlas.oracle"
    assert resp.result["correlation_id"] == "c1"


def test_trader_execute_202_surfaces_follow_up(monkeypatch):
    """HTTP 202 from trader-execute surfaces poll follow_up in AgentResponse."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    envelope_202 = {
        "status": "timeout",
        "correlation_id": "c-trade",
        "result": {},
        "job_id": "job-trade-42",
    }

    with respx.mock(base_url="http://atlas-202:8000", assert_all_called=False) as mock:
        mock.post("/pipeline/trader-execute").mock(
            return_value=httpx.Response(202, json=envelope_202)
        )
        bridge = AtlasBridge(base_url="http://atlas-202:8000")
        orch = AtlasOrchestrator(bridge=bridge, allow_mock=False, mode="live")
        orch._health_cache = (True, float("inf"))
        resp = orch.trader_execute("strat-1", mode="paper")

    assert resp.action == "pending"
    assert any("job-trade-42" in fu for fu in resp.follow_ups)
    assert resp.confidence < 0.9
