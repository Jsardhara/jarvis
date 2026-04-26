"""Orchestrator core — context aggregation + dispatch.

Phase 1 scope: routing logic + envelope wrapping. Actual subsystem agents
are invoked from CC via the Agent tool against `.claude/agents/*.md`. This
module exposes the same logic to the daemon and tests via plain functions.

Mission control phase: emit lifecycle events via on_event callback, run
parallel agents concurrently with asyncio.gather.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from .contract import AgentResponse, IntentClassification, TraceEvent
from .router import classify
from .state import load_tasks, read_inbox

SubsystemHandler = Callable[[str], Awaitable[AgentResponse]]
EventSink = Callable[[TraceEvent], Awaitable[None]]


async def _noop_sink(_event: TraceEvent) -> None:
    return None


class Orchestrator:
    def __init__(
        self,
        handlers: dict[str, SubsystemHandler] | None = None,
        on_event: EventSink | None = None,
    ):
        self._handlers: dict[str, SubsystemHandler] = handlers or {}
        self._on_event: EventSink = on_event or _noop_sink

    def register(self, name: str, handler: SubsystemHandler) -> None:
        self._handlers[name] = handler

    def set_event_sink(self, sink: EventSink) -> None:
        self._on_event = sink

    def gather_context(self, inbox_limit: int = 20) -> dict[str, Any]:
        return {
            "inbox": [e.model_dump() for e in read_inbox(limit=inbox_limit)],
            "tasks": [t.model_dump() for t in load_tasks() if t.status == "open"],
        }

    def route(self, request: str) -> IntentClassification:
        return classify(request)

    async def _run_one(self, agent_name: str, request: str, request_id: str) -> AgentResponse | None:
        handler = self._handlers.get(agent_name)
        if handler is None:
            return None
        await self._on_event(TraceEvent(
            type="agent.start", request_id=request_id, agent=agent_name,
            payload={"request": request},
        ))
        started = time.perf_counter()
        try:
            resp = await handler(request)
        except Exception as exc:  # surface as trace event, re-raise
            await self._on_event(TraceEvent(
                type="agent.error", request_id=request_id, agent=agent_name,
                payload={"error": str(exc),
                         "duration_ms": int((time.perf_counter() - started) * 1000)},
            ))
            raise
        await self._on_event(TraceEvent(
            type="agent.done", request_id=request_id, agent=agent_name,
            payload={
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "action": resp.action,
                "confidence": resp.confidence,
                "needs_confirm": resp.needs_confirm,
            },
        ))
        return resp

    async def dispatch(self, request: str) -> dict[str, Any]:
        """Classify, dispatch to primary + parallel handlers concurrently, aggregate."""
        request_id = uuid4().hex[:12]
        intent = classify(request)
        await self._on_event(TraceEvent(
            type="router.classified", request_id=request_id,
            payload={"intent": intent.model_dump()},
        ))

        targets = [intent.primary, *intent.parallel]
        # Dedupe while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for n in targets:
            if n in self._handlers and n not in seen:
                seen.add(n)
                ordered.append(n)

        results = await asyncio.gather(
            *(self._run_one(name, request, request_id) for name in ordered),
            return_exceptions=False,
        )
        responses: dict[str, AgentResponse] = {
            name: resp for name, resp in zip(ordered, results, strict=False) if resp is not None
        }

        return {
            "request_id": request_id,
            "intent": intent.model_dump(),
            "context": self.gather_context(),
            "responses": {k: v.model_dump() for k, v in responses.items()},
            "needs_confirm": any(r.needs_confirm for r in responses.values()),
        }
