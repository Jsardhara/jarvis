"""Agent contract — every subsystem agent returns this envelope."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentResponse(BaseModel):
    """Standard envelope for all subsystem agent responses."""

    intent: str = Field(description="What the request was understood as")
    action: str = Field(description="What was done, or 'proposed' if awaiting confirm")
    result: dict[str, Any] = Field(default_factory=dict)
    follow_ups: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    needs_confirm: bool = False
    agent: str = Field(description="Subsystem agent name")
    request_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    ts: str = Field(default_factory=_now_iso)


class InboxEvent(BaseModel):
    """One line in state/inbox.jsonl — daemon→interactive queue."""

    ts: str = Field(default_factory=_now_iso)
    agent: str
    severity: str = Field(description="info | warn | alert")
    summary: str
    ref: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Todo entry persisted in state/tasks.json."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str
    due: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: str = Field(default="open", pattern="^(open|done|cancelled)$")
    created: str = Field(default_factory=_now_iso)
    updated: str = Field(default_factory=_now_iso)


class IntentClassification(BaseModel):
    """Output of orchestrator's intent classifier."""

    primary: str = Field(description="Subsystem agent name to route to")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    parallel: list[str] = Field(default_factory=list, description="Other agents to run in parallel")
    raw_request: str


# --- Mission control: trace events, agent log entries, confirmations ---


TRACE_TYPES = (
    "router.classified",
    "agent.start",
    "agent.done",
    "agent.error",
    "confirmation.created",
    "confirmation.resolved",
)


class TraceEvent(BaseModel):
    """Lifecycle event broadcast over the WebSocket bus."""

    type: str = Field(description="One of TRACE_TYPES")
    request_id: str
    ts: str = Field(default_factory=_now_iso)
    agent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentLogEntry(BaseModel):
    """One line in state/agent_log.jsonl — every agent invocation."""

    ts: str = Field(default_factory=_now_iso)
    request_id: str
    agent: str
    action: str
    status: str = Field(description="ok | error | proposed")
    duration_ms: int = 0
    confidence: float = 1.0
    needs_confirm: bool = False
    summary: str = ""
    error: str | None = None


class Confirmation(BaseModel):
    """Persisted in state/confirmations.jsonl. Survives reload."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    ts: str = Field(default_factory=_now_iso)
    agent: str
    intent: str
    args: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    status: str = Field(default="pending", pattern="^(pending|approved|rejected)$")
    resolved_ts: str | None = None
    resolved_result: dict[str, Any] | None = None
