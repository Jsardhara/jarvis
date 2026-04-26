"""Orchestrator core — context aggregation + dispatch.

Phase 1 scope: routing logic + envelope wrapping. Actual subsystem agents
are invoked from CC via the Agent tool against `.claude/agents/*.md`. This
module exposes the same logic to the daemon and tests via plain functions.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .contract import AgentResponse, IntentClassification
from .router import classify
from .state import load_tasks, read_inbox

SubsystemHandler = Callable[[str], Awaitable[AgentResponse]]


class Orchestrator:
    def __init__(self, handlers: dict[str, SubsystemHandler] | None = None):
        self._handlers: dict[str, SubsystemHandler] = handlers or {}

    def register(self, name: str, handler: SubsystemHandler) -> None:
        self._handlers[name] = handler

    def gather_context(self, inbox_limit: int = 20) -> dict[str, Any]:
        return {
            "inbox": [e.model_dump() for e in read_inbox(limit=inbox_limit)],
            "tasks": [t.model_dump() for t in load_tasks() if t.status == "open"],
        }

    def route(self, request: str) -> IntentClassification:
        return classify(request)

    async def dispatch(self, request: str) -> dict[str, Any]:
        """Classify, dispatch to primary + parallel handlers, aggregate."""
        intent = classify(request)
        primary = intent.primary
        responses: dict[str, AgentResponse] = {}

        # Primary
        if primary in self._handlers:
            responses[primary] = await self._handlers[primary](request)

        # Parallel
        for agent_name in intent.parallel:
            if agent_name in self._handlers:
                responses[agent_name] = await self._handlers[agent_name](request)

        return {
            "intent": intent.model_dump(),
            "context": self.gather_context(),
            "responses": {k: v.model_dump() for k, v in responses.items()},
            "needs_confirm": any(r.needs_confirm for r in responses.values()),
        }
