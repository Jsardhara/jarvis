"""Orchestrator core — context aggregation + dispatch.

Full pipeline per dispatch:
    classify_request → classify_tier → check_authority → run handlers
    → verify_response → record_dispatch → aggregate

Raises AuthorityError if tier requires confirmation but confirmed=False.
Atlas pipeline emits per-stage trace events for sub-flow swimlane rendering.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from .authority import AuthorityError, check_authority
from .classify import classify_tier
from .contract import AgentResponse, InboxEvent, IntentClassification, TraceEvent
from .memory import record_dispatch
from .router import classify
from .state import append_inbox, load_tasks, read_inbox
from .verify import verify_response

SubsystemHandler = Callable[[str], Awaitable[AgentResponse]]
EventSink = Callable[[TraceEvent], Awaitable[None]]


async def _noop_sink(_event: TraceEvent) -> None:
    return None


def _push_crit_inbox(event: InboxEvent) -> None:
    """Persist a crit inbox event from the supervisor directly to state."""
    with contextlib.suppress(Exception):  # pragma: no cover — belt-and-suspenders
        append_inbox(event)


class Orchestrator:
    def __init__(
        self,
        handlers: dict[str, SubsystemHandler] | None = None,
        on_event: EventSink | None = None,
    ):
        self._handlers: dict[str, SubsystemHandler] = handlers or {}
        self._on_event: EventSink = on_event or _noop_sink
        self._session: dict[str, Any] = {}

    # ── public surface ──────────────────────────────────────────────────

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

    async def dispatch(self, request: str, confirmed: bool = False) -> dict[str, Any]:
        """Classify → authority gate → dispatch → verify → memory → aggregate."""
        request_id = uuid4().hex[:12]
        intent = classify(request)
        tier = classify_tier(request, agent=intent.primary).tier

        await self._emit("router.classified", request_id,
                         intent=intent.model_dump(), tier=tier)

        try:
            check_authority(agent=intent.primary, action="dispatch",
                            tier=tier, confirmed=confirmed)
        except AuthorityError as exc:
            return self._authority_block_payload(request_id, intent, tier, exc)

        ordered = self._resolve_targets(intent)
        responses = await self._run_fanout(ordered, request, request_id, tier)
        self._record_responses(responses, tier)

        return {
            "request_id": request_id,
            "intent": intent.model_dump(),
            "tier": tier,
            "context": self.gather_context(),
            "responses": {k: v.model_dump() for k, v in responses.items()},
            "needs_confirm": any(r.needs_confirm for r in responses.values()),
        }

    # ── internals ───────────────────────────────────────────────────────

    async def _emit(self, event_type: str, request_id: str,
                    agent: str | None = None, **payload: Any) -> None:
        await self._on_event(TraceEvent(
            type=event_type, request_id=request_id, agent=agent, payload=payload,
        ))

    def _resolve_targets(self, intent: IntentClassification) -> list[str]:
        """Dedupe targets, preserve order, drop unregistered handlers."""
        seen: set[str] = set()
        ordered: list[str] = []
        for name in (intent.primary, *intent.parallel):
            if name in self._handlers and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def _authority_block_payload(
        self,
        request_id: str,
        intent: IntentClassification,
        tier: int,
        exc: AuthorityError,
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "intent": intent.model_dump(),
            "tier": tier,
            "needs_confirm": True,
            "confirmation_required": True,
            "authority_error": str(exc),
            "responses": {},
        }

    async def _run_fanout(
        self,
        ordered: list[str],
        request: str,
        request_id: str,
        tier: int,
    ) -> dict[str, AgentResponse]:
        results = await asyncio.gather(
            *(self._run_one(name, request, request_id, tier) for name in ordered),
            return_exceptions=False,
        )
        return {
            name: resp
            for name, resp in zip(ordered, results, strict=False)
            if resp is not None
        }

    def _record_responses(
        self,
        responses: dict[str, AgentResponse],
        tier: int,
    ) -> None:
        for agent_name, resp in responses.items():
            self._session = record_dispatch(
                session=self._session,
                agent=agent_name,
                action=resp.action,
                tier=tier,
                summary=resp.intent,
            )

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
        await self._emit("agent.start", request_id, agent=agent_name,
                         request=request, tier=tier)
        started = time.perf_counter()
        try:
            resp = await handler(request)
        except Exception as exc:
            await self._emit("agent.error", request_id, agent=agent_name,
                             error=str(exc),
                             duration_ms=int((time.perf_counter() - started) * 1000))
            raise
        resp = verify_response(resp.model_copy(update={"tier": tier}))
        await self._emit(
            "agent.done", request_id, agent=agent_name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            action=resp.action,
            confidence=resp.confidence,
            needs_confirm=resp.needs_confirm,
            tier=tier,
            verification_status=resp.verification.get("status"),
        )
        return resp
