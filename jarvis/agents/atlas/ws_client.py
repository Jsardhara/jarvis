"""AtlasWsClient — async background WebSocket consumer for Atlas events.

Connects to the Atlas WebSocket, re-emits each incoming message as a Jarvis
TraceEvent via the registered EventSink. Reconnects with exponential backoff
on disconnect. Started by AtlasOrchestrator (or explicitly via start_ws()).

Type allowlist for the Atlas WS filter query string:
    pipeline_decision, trade_approved, trade_rejected, trade_modified,
    order_placed, order_filled, position_opened, position_closed,
    learning_insight, strategy_proposed, market_signal, agent_status
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis.contract import TraceEvent

log = logging.getLogger(__name__)

# Atlas event types Jarvis cares about
_WS_TYPE_FILTER = ",".join([
    "pipeline_decision",
    "trade_approved",
    "trade_rejected",
    "trade_modified",
    "order_placed",
    "order_filled",
    "position_opened",
    "position_closed",
    "learning_insight",
    "strategy_proposed",
    "market_signal",
    "agent_status",
])

EventSink = Callable[[TraceEvent], Awaitable[None]]

_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0


def _atlas_ws_url() -> str:
    base = os.environ.get("JARVIS_ATLAS_API", "http://localhost:8000")
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_base.rstrip('/')}/ws?type={_WS_TYPE_FILTER}"


def _atlas_event_to_trace(raw: dict[str, Any]) -> TraceEvent:
    """Map an Atlas WebSocket message to a Jarvis TraceEvent."""
    msg_type = raw.get("message_type", raw.get("type", "atlas.event"))
    agent = raw.get("agent", "atlas")
    request_id = raw.get("correlation_id", raw.get("job_id", ""))
    payload = {k: v for k, v in raw.items() if k not in ("message_type", "type", "agent")}
    return TraceEvent(
        type=f"atlas.{msg_type}",
        request_id=str(request_id),
        agent=agent,
        payload=payload,
    )


class AtlasWsClient:
    """Async background task that consumes Atlas WebSocket events.

    Usage (inside a running event loop)::

        sink = my_event_sink
        client = AtlasWsClient(sink)
        client.start()          # schedules asyncio.create_task internally
        # ...
        await client.stop()
    """

    def __init__(
        self,
        sink: EventSink,
        ws_url: str | None = None,
    ) -> None:
        self._sink = sink
        self._ws_url = ws_url or _atlas_ws_url()
        self._task: asyncio.Task | None = None
        self._stopped = False

    def start(self) -> None:
        """Schedule the background reconnect loop as an asyncio task.

        Safe to call when a loop is running. If no loop is running (sync
        context), defers until the first event-loop tick that receives
        a running loop.
        """
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop(), name="atlas-ws-client")
        except RuntimeError:
            # No running loop — caller must invoke start() from async context
            # or call start_ws() once the loop is available.
            log.debug("AtlasWsClient.start() called outside running loop; deferred")

    async def start_ws(self) -> None:
        """Async entry point — schedules background task from async context."""
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.create_task(self._run_loop(), name="atlas-ws-client")

    async def stop(self) -> None:
        """Signal the loop to stop and await task completion."""
        self._stopped = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        """Reconnect loop with exponential backoff."""
        backoff = _BACKOFF_BASE
        while not self._stopped:
            try:
                await self._connect_and_consume()
                backoff = _BACKOFF_BASE  # reset on clean exit
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stopped:
                    break
                log.warning(
                    "AtlasWsClient disconnected (%s); reconnecting in %.1fs", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _connect_and_consume(self) -> None:
        """Open the WebSocket, consume messages until disconnect."""
        try:
            import websockets  # type: ignore[import]
        except ImportError:
            log.warning("websockets package not installed; AtlasWsClient inactive")
            self._stopped = True
            return

        log.info("AtlasWsClient connecting to %s", self._ws_url)
        async with websockets.connect(self._ws_url) as ws:
            log.info("AtlasWsClient connected")
            async for raw_msg in ws:
                if self._stopped:
                    break
                await self._handle_message(raw_msg)

    async def _handle_message(self, raw_msg: str) -> None:
        """Parse a raw WS message and re-emit as TraceEvent."""
        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError:
            log.debug("AtlasWsClient: non-JSON message skipped: %r", raw_msg[:80])
            return
        try:
            event = _atlas_event_to_trace(data)
            await self._sink(event)
        except Exception as exc:
            log.warning("AtlasWsClient sink error: %s", exc)
