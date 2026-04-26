"""Agent contract — every subsystem agent returns this envelope."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
