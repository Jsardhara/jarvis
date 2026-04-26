"""Ledger ATLAS-bridge tests — uses httpx MockTransport for deterministic HTTP."""
from __future__ import annotations

import httpx
import pytest

from jarvis.subsystems.ledger import AtlasClient, AtlasUnavailable, Ledger


def _transport(responses: dict[str, httpx.Response]):
    """Build a transport that returns a canned response per (METHOD, path)."""
    def handler(req: httpx.Request) -> httpx.Response:
        key = f"{req.method} {req.url.path}"
        if key in responses:
            return responses[key]
        # query string variant
        key_with_q = f"{req.method} {req.url.path}?{req.url.query.decode() if req.url.query else ''}"
        if key_with_q in responses:
            return responses[key_with_q]
        return httpx.Response(404, json={"error": "not found"})
    return httpx.MockTransport(handler)


def test_portfolio_real_response():
    transport = _transport({
        "GET /portfolio": httpx.Response(200, json={"total_value_usd": 12345.0}),
    })
    client = AtlasClient(base_url="http://test", transport=transport)
    led = Ledger(client=client)
    resp = led.portfolio()
    assert resp.result["mock"] is False
    assert resp.result["portfolio"]["total_value_usd"] == 12345.0
    assert resp.confidence == 1.0


def test_portfolio_falls_back_to_mock():
    transport = _transport({})  # everything 404s
    client = AtlasClient(base_url="http://test", transport=transport)
    led = Ledger(client=client, allow_mock=True)
    resp = led.portfolio()
    assert resp.result["mock"] is True
    assert resp.confidence < 1.0
    assert "start ATLAS API" in resp.follow_ups


def test_portfolio_raises_when_mock_disabled():
    transport = _transport({})
    client = AtlasClient(base_url="http://test", transport=transport)
    led = Ledger(client=client, allow_mock=False)
    with pytest.raises(AtlasUnavailable):
        led.portfolio()


def test_positions_normalizes_list_response():
    transport = _transport({
        "GET /trades/open": httpx.Response(200, json=[
            {"id": "p1", "symbol": "BTC", "side": "long"}
        ]),
    })
    led = Ledger(client=AtlasClient("http://t", transport=transport))
    resp = led.positions()
    assert resp.result["count"] == 1
    assert resp.result["positions"][0]["symbol"] == "BTC"


def test_positions_normalizes_dict_response():
    transport = _transport({
        "GET /trades/open": httpx.Response(200, json={"trades": [{"symbol": "ETH"}]}),
    })
    led = Ledger(client=AtlasClient("http://t", transport=transport))
    resp = led.positions()
    assert resp.result["count"] == 1


def test_pnl_real():
    transport = _transport({
        "GET /trades/stats": httpx.Response(200, json={"pnl_usd": 50}),
    })
    led = Ledger(client=AtlasClient("http://t", transport=transport))
    resp = led.pnl()
    assert resp.result["mock"] is False
    assert resp.result["pnl"]["pnl_usd"] == 50
    assert resp.result["pnl"]["window"] == "1d"


def test_trigger_strategy_proposes_with_confirm():
    led = Ledger(client=AtlasClient("http://t", transport=_transport({})))
    resp = led.trigger_strategy("alpha-1", mode="paper")
    assert resp.needs_confirm is True
    assert resp.action == "proposed"


def test_trigger_strategy_confirmed_calls_post():
    transport = _transport({
        "POST /strategies/alpha-1/activate": httpx.Response(200, json={"id": "alpha-1", "status": "queued"}),
    })
    led = Ledger(client=AtlasClient("http://t", transport=transport))
    resp = led.trigger_strategy_confirmed("alpha-1", mode="paper")
    assert resp.action == "triggered"
    assert resp.result["mock"] is False


def test_health_returns_true_when_endpoint_ok():
    transport = _transport({
        "GET /system/health": httpx.Response(200, json={"ok": True}),
    })
    client = AtlasClient("http://t", transport=transport)
    assert client.health() is True


def test_health_returns_false_when_unreachable():
    client = AtlasClient("http://t", transport=_transport({}))
    assert client.health() is False
