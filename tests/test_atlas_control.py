"""Tests for the ATLAS control surface added in Phase 2 (Jarvis decision layer).

Exercises the new ``AtlasBridge.control_*`` methods, the orchestrator
wrappers, and the paper-vs-live behavior of ``trader_execute``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from jarvis.agents.atlas.agent import (
    AtlasBridge,
    AtlasOrchestrator,
    AtlasUnavailableError,
)


def _route(handler):
    return httpx.MockTransport(handler)


def _bridge(handler) -> AtlasBridge:
    return AtlasBridge(
        "http://t", transport=_route(handler), timeout=1.0
    )


def _make_orch(handler, *, allow_mock: bool = False) -> AtlasOrchestrator:
    bridge = _bridge(handler)
    return AtlasOrchestrator(
        bridge=bridge,
        allow_mock=allow_mock,
        auto_mock_on_offline=False,
        mode="live",
    )


# ── pipeline_trader_execute auto flag ────────────────────────────────────


def test_pipeline_trader_execute_includes_auto():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(200, json={"status": "ok", "correlation_id": "c"})

    bridge = _bridge(handler)
    bridge.pipeline_trader_execute(signal_id="s", mode="paper", auto=True)
    assert captured["body"]["auto"] is True
    assert captured["body"]["mode"] == "paper"
    assert captured["body"]["signal_id"] == "s"


def test_pipeline_trader_execute_default_auto_false():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(200, json={"status": "ok", "correlation_id": "c"})

    bridge = _bridge(handler)
    bridge.pipeline_trader_execute(signal_id="s", mode="live")
    assert captured["body"]["auto"] is False


# ── trader_execute orchestrator: paper auto, live confirms ───────────────


def test_trader_execute_paper_returns_executed_no_confirm():
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        assert body["auto"] is True
        return httpx.Response(
            200, json={"status": "ok", "correlation_id": "c1", "result": {}}
        )

    orch = _make_orch(handler)
    resp = orch.trader_execute("strategy-x", mode="paper")
    assert resp.action == "executed"
    assert resp.needs_confirm is False
    assert resp.result["auto"] is True


def test_trader_execute_paper_raises_when_bridge_unreachable():
    """Silent-failure guard: if ATLAS is online-but-broken, paper auto must
    NOT return action='executed' with synthetic data. Surface the failure."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="bridge boom")

    orch = _make_orch(handler)
    with pytest.raises(AtlasUnavailableError):
        orch.trader_execute("strategy-fail", mode="paper")


def test_trader_execute_live_keeps_confirm_gate():
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        assert body["auto"] is False
        return httpx.Response(
            200, json={"status": "ok", "correlation_id": "c2", "result": {}}
        )

    orch = _make_orch(handler)
    resp = orch.trader_execute("strategy-y", mode="live")
    assert resp.action == "proposed"
    assert resp.needs_confirm is True
    assert resp.follow_ups
    assert resp.result["auto"] is False


# ── pause / resume ───────────────────────────────────────────────────────


def test_pause_agent_calls_control_endpoint():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"agent_id": "trader", "state": "paused", "command_id": "abc"},
        )

    orch = _make_orch(handler)
    resp = orch.pause_agent("trader")
    assert resp.action == "paused"
    assert resp.result["state"] == "paused"
    assert "/control/pause-agent" in captured["url"]
    assert captured["body"] == {"agent_id": "trader"}


def test_resume_agent_calls_control_endpoint():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={"agent_id": "oracle", "state": "running", "command_id": "xyz"},
        )

    orch = _make_orch(handler)
    resp = orch.resume_agent("oracle")
    assert resp.action == "resumed"
    assert resp.result["state"] == "running"
    assert "/control/resume-agent" in captured["url"]


def test_pause_agent_raises_on_endpoint_failure():
    orch = _make_orch(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(AtlasUnavailableError):
        orch.pause_agent("trader")


# ── agent_state ──────────────────────────────────────────────────────────


def test_agent_state_returns_list():
    body = {
        "agents": [
            {"id": "oracle", "state": "running", "last_heartbeat": None},
            {"id": "trader", "state": "paused", "last_heartbeat": None},
        ]
    }

    def handler(req: httpx.Request) -> httpx.Response:
        assert "/control/agent-state" in str(req.url)
        return httpx.Response(200, json=body)

    orch = _make_orch(handler)
    resp = orch.agent_state()
    assert resp.action == "fetched"
    assert len(resp.result["agents"]) == 2


# ── strategy weights ─────────────────────────────────────────────────────


def test_set_strategy_weights_posts_dict():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(200, json={"weights": {"a": 1.5}, "count": 1})

    orch = _make_orch(handler)
    resp = orch.set_strategy_weights({"a": 1.5})
    assert resp.action == "set"
    assert captured["body"]["weights"] == {"a": 1.5}


# ── oracle scan trigger ──────────────────────────────────────────────────


def test_trigger_oracle_scan_posts_reason():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(
            200, json={"command_id": "c", "reason": "vix-spike"}
        )

    orch = _make_orch(handler)
    resp = orch.trigger_oracle_scan(reason="vix-spike", universe=["AAPL"])
    assert resp.action == "triggered"
    assert captured["body"]["reason"] == "vix-spike"
    assert captured["body"]["universe"] == ["AAPL"]


# ── mock mode bypasses bridge ────────────────────────────────────────────


def test_mock_mode_skips_bridge_calls_for_pause():
    """In mock mode every control op short-circuits to a synthetic AgentResponse."""
    bridge_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        bridge_calls.append(str(req.url))
        return httpx.Response(500)

    orch = AtlasOrchestrator(
        bridge=_bridge(handler),
        allow_mock=True,
        auto_mock_on_offline=False,
        mode="mock",
    )
    resp = orch.pause_agent("trader")
    assert resp.action == "paused"
    assert resp.result["mock"] is True
    # Bridge was NOT called.
    assert bridge_calls == []
