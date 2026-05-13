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

from jarvis.contract import (
    AgentLogEntry,
    AgentResponse,
    InboxEvent,
    IntentClassification,
    TraceEvent,
)
from jarvis.state import append_agent_log, append_inbox, load_tasks, read_inbox
from jarvis.state.memory import record_dispatch

from .authority import AuthorityError, check_authority
from .classify import classify_tier
from .router import classify
from .verify import verify_response

SubsystemHandler = Callable[[Any], Awaitable[AgentResponse]]
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
        action = intent.action or "dispatch"
        tier = classify_tier(request, agent=intent.primary, action=action).tier

        await self._emit("router.classified", request_id,
                         intent=intent.model_dump(), tier=tier)

        try:
            check_authority(agent=intent.primary, action=action,
                            tier=tier, confirmed=confirmed)
        except AuthorityError as exc:
            return self._authority_block_payload(request_id, intent, tier, exc)

        ordered = self._resolve_targets(intent)
        responses = await self._run_fanout(
            ordered, request, request_id, tier, action=action,
        )
        self._record_responses(responses, tier)
        self._persist_agent_log(request_id, responses, tier)

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
        action: str = "dispatch",
    ) -> dict[str, AgentResponse]:
        # ``return_exceptions=True`` so one misbehaving agent cannot kill the
        # entire fan-out — partial results still bubble back to the caller.
        results = await asyncio.gather(
            *(
                self._run_one(name, request, request_id, tier, action=action)
                for name in ordered
            ),
            return_exceptions=True,
        )
        merged: dict[str, AgentResponse] = {}
        for name, resp in zip(ordered, results, strict=False):
            if isinstance(resp, BaseException):
                merged[name] = self._degraded_response(name, resp, tier)
            elif resp is not None:
                merged[name] = resp
        return merged

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
        action: str = "dispatch",
    ) -> AgentResponse | None:
        handler = self._handlers.get(agent_name)
        if handler is None:
            return None
        await self._emit("agent.start", request_id, agent=agent_name,
                         request=request, tier=tier, action=action)
        started = time.perf_counter()
        # Pass the action through when the handler accepts it; the
        # API-layer factory wraps handlers to detect a dict envelope.
        payload: Any = {"text": request, "action": action} if action and action != "dispatch" else request
        try:
            resp = await handler(payload)
        except Exception as exc:
            # Do NOT re-raise — the fan-out caller relies on partial
            # results. Emit the error event and let the caller wrap it
            # into a degraded AgentResponse.
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

    def _degraded_response(
        self,
        agent_name: str,
        exc: BaseException,
        tier: int,
    ) -> AgentResponse:
        """Wrap a handler exception as a degraded AgentResponse.

        Keeps the orchestrator's caller able to render partial results when
        one agent in a fan-out crashes — failure no longer bubbles up as
        a 500.
        """
        return AgentResponse(
            agent=agent_name,
            intent="error",
            action="error",
            result={"error": str(exc), "error_class": type(exc).__name__},
            follow_ups=[],
            confidence=0.0,
            needs_confirm=False,
            tier=tier,
            verification={
                "status": "errored",
                "evidence": f"{type(exc).__name__}: {exc}",
            },
        )

    def _persist_agent_log(
        self,
        request_id: str,
        responses: dict[str, AgentResponse],
        tier: int,
    ) -> None:
        """Append one AgentLogEntry per successful dispatch response.

        Belt-and-braces: even when the API-layer event sink also writes
        agent_log.jsonl on ``agent.done``, headless callers (CLI, tests)
        still get a complete dispatch trail.
        """
        for agent_name, resp in responses.items():
            status = (
                "error" if resp.action == "error"
                else "proposed" if resp.needs_confirm
                else "ok"
            )
            entry = AgentLogEntry(
                request_id=request_id,
                agent=agent_name,
                action=resp.action,
                status=status,
                confidence=resp.confidence,
                needs_confirm=resp.needs_confirm,
                summary=resp.intent,
                error=resp.result.get("error") if status == "error" else None,
            )
            with contextlib.suppress(Exception):
                append_agent_log(entry)
        del tier  # tier is recorded via record_dispatch on the session
