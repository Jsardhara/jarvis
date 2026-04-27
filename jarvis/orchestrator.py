"""Orchestrator core — context aggregation + dispatch.

Full pipeline per dispatch:
    classify_request → classify_tier → check_authority → run handlers
    → verify_response → record_dispatch → aggregate

Raises AuthorityError if tier requires confirmation but confirmed=False.
Atlas pipeline emits per-stage trace events for sub-flow swimlane rendering.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from .authority import AuthorityError, check_authority
from .classify import classify_tier
from .contract import AgentResponse, IntentClassification, TraceEvent
from .memory import record_dispatch
from .router import classify
from .state import load_tasks, read_inbox
from .verify import verify_response

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
        self._session: dict[str, Any] = {}

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

    async def _run_one(
        self,
        agent_name: str,
        request: str,
        request_id: str,
        tier: int,
    ) -> AgentResponse | None:
        handler = self._handlers.get(agent_name)
        if handler is None:
            return None
        await self._on_event(TraceEvent(
            type="agent.start", request_id=request_id, agent=agent_name,
            payload={"request": request, "tier": tier},
        ))
        started = time.perf_counter()
        try:
            resp = await handler(request)
        except Exception as exc:
            await self._on_event(TraceEvent(
                type="agent.error", request_id=request_id, agent=agent_name,
                payload={"error": str(exc),
                         "duration_ms": int((time.perf_counter() - started) * 1000)},
            ))
            raise
        resp = resp.model_copy(update={"tier": tier})
        resp = verify_response(resp)
        await self._on_event(TraceEvent(
            type="agent.done", request_id=request_id, agent=agent_name,
            payload={
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "action": resp.action,
                "confidence": resp.confidence,
                "needs_confirm": resp.needs_confirm,
                "tier": tier,
                "verification_status": resp.verification.get("status"),
            },
        ))
        return resp

    async def dispatch(self, request: str, confirmed: bool = False) -> dict[str, Any]:
        """Classify → authority gate → dispatch → verify → memory → aggregate."""
        request_id = uuid4().hex[:12]
        intent = classify(request)
        tier_result = classify_tier(request, agent=intent.primary)
        tier = tier_result.tier

        await self._on_event(TraceEvent(
            type="router.classified", request_id=request_id,
            payload={"intent": intent.model_dump(), "tier": tier},
        ))

        try:
            check_authority(
                agent=intent.primary,
                action="dispatch",
                tier=tier,
                confirmed=confirmed,
            )
        except AuthorityError as exc:
            return {
                "request_id": request_id,
                "intent": intent.model_dump(),
                "tier": tier,
                "needs_confirm": True,
                "confirmation_required": True,
                "authority_error": str(exc),
                "responses": {},
            }

        targets = [intent.primary, *intent.parallel]
        seen: set[str] = set()
        ordered: list[str] = []
        for n in targets:
            if n in self._handlers and n not in seen:
                seen.add(n)
                ordered.append(n)

        results = await asyncio.gather(
            *(self._run_one(name, request, request_id, tier) for name in ordered),
            return_exceptions=False,
        )
        responses: dict[str, AgentResponse] = {
            name: resp
            for name, resp in zip(ordered, results, strict=False)
            if resp is not None
        }

        for agent_name, resp in responses.items():
            self._session = record_dispatch(
                session=self._session,
                agent=agent_name,
                action=resp.action,
                tier=tier,
                summary=resp.intent,
            )

        return {
            "request_id": request_id,
            "intent": intent.model_dump(),
            "tier": tier,
            "context": self.gather_context(),
            "responses": {k: v.model_dump() for k, v in responses.items()},
            "needs_confirm": any(r.needs_confirm for r in responses.values()),
        }
