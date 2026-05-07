"""Tests: AtlasWsClient — connects, re-emits events, reconnects with backoff."""
from __future__ import annotations

import asyncio
import json

import pytest

from jarvis.contract import TraceEvent
from jarvis.subsystems.atlas_ws_client import AtlasWsClient, _atlas_event_to_trace

# ---------------------------------------------------------------------------
# Unit tests — no network
# ---------------------------------------------------------------------------


def test_atlas_event_to_trace_maps_message_type():
    """_atlas_event_to_trace converts message_type to atlas.<type> TraceEvent."""
    raw = {
        "message_type": "trade_approved",
        "agent": "atlas.trader",
        "correlation_id": "corr-1",
        "symbol": "BTC",
    }
    event = _atlas_event_to_trace(raw)
    assert event.type == "atlas.trade_approved"
    assert event.agent == "atlas.trader"
    assert event.request_id == "corr-1"
    assert event.payload["symbol"] == "BTC"


def test_atlas_event_to_trace_fallback_type():
    """Falls back to 'type' key when message_type absent."""
    raw = {"type": "market_signal", "agent": "atlas.oracle", "data": "x"}
    event = _atlas_event_to_trace(raw)
    assert event.type == "atlas.market_signal"


def test_atlas_event_to_trace_unknown_type():
    """Unknown message produces atlas.atlas.event type."""
    raw = {}
    event = _atlas_event_to_trace(raw)
    assert event.type == "atlas.atlas.event"


@pytest.mark.asyncio
async def test_handle_message_calls_sink():
    """_handle_message parses JSON and calls the sink with a TraceEvent."""
    received: list[TraceEvent] = []

    async def sink(ev: TraceEvent) -> None:
        received.append(ev)

    client = AtlasWsClient(sink, ws_url="ws://unused:8000/ws")
    raw_msg = json.dumps({"message_type": "order_filled", "agent": "atlas.trader", "qty": 1.0})
    await client._handle_message(raw_msg)

    assert len(received) == 1
    assert received[0].type == "atlas.order_filled"
    assert received[0].payload["qty"] == 1.0


@pytest.mark.asyncio
async def test_handle_message_skips_invalid_json():
    """_handle_message silently skips non-JSON without raising."""
    async def sink(ev: TraceEvent) -> None:
        raise AssertionError("should not be called")

    client = AtlasWsClient(sink, ws_url="ws://unused:8000/ws")
    await client._handle_message("not json {{")  # must not raise


@pytest.mark.asyncio
async def test_stop_cancels_task():
    """stop() cancels the background task."""
    received: list[TraceEvent] = []

    async def sink(ev: TraceEvent) -> None:
        received.append(ev)

    client = AtlasWsClient(sink, ws_url="ws://unused:8000/ws")

    async def _slow_loop() -> None:
        await asyncio.sleep(100)

    client._task = asyncio.create_task(_slow_loop())
    await client.stop()

    assert client._task.done()


@pytest.mark.asyncio
async def test_reconnects_with_backoff(monkeypatch):
    """_run_loop retries on disconnect, doubling backoff each time."""
    connect_count = 0
    slept: list[float] = []

    async def _mock_sleep(delay: float) -> None:
        slept.append(delay)
        if len(slept) >= 2:
            client._stopped = True

    monkeypatch.setattr("jarvis.subsystems.atlas_ws_client.asyncio.sleep", _mock_sleep)

    async def sink(ev: TraceEvent) -> None:
        pass

    client = AtlasWsClient(sink, ws_url="ws://unused:8000/ws")

    async def _failing_connect() -> None:
        nonlocal connect_count
        connect_count += 1
        raise ConnectionError("refused")

    client._connect_and_consume = _failing_connect
    client._stopped = False

    await client._run_loop()

    assert connect_count >= 2
    # Backoff doubles: second sleep >= first
    if len(slept) >= 2:
        assert slept[1] >= slept[0]


@pytest.mark.asyncio
async def test_start_ws_creates_task():
    """start_ws() creates a background asyncio task."""
    async def sink(ev: TraceEvent) -> None:
        pass

    client = AtlasWsClient(sink, ws_url="ws://unused:8000/ws")

    async def _noop_loop() -> None:
        pass

    client._run_loop = _noop_loop
    await client.start_ws()
    assert client._task is not None
    await client.stop()
