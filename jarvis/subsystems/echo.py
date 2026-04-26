"""Echo — unified messaging triage across Slack/Discord/SMS."""
from __future__ import annotations

from typing import Protocol

from ..contract import AgentResponse


class MessageBridge(Protocol):
    """One per surface (slack/discord/sms). Send replies through the same bridge."""
    surface: str
    def send(self, channel: str, body: str) -> dict: ...


# Urgency tiers
URGENCY_NOW = "now"        # mention/DM, action keyword
URGENCY_TODAY = "today"    # direct message, no urgency keywords
URGENCY_FYI = "fyi"        # channel notification

_URGENCY_KEYWORDS = ("urgent", "asap", "now", "right away", "immediately", "blocker")


def classify_urgency(msg: dict) -> str:
    """msg has: surface, channel_type (dm|channel|mention), text, mentions."""
    text = (msg.get("text") or "").lower()
    if any(k in text for k in _URGENCY_KEYWORDS):
        return URGENCY_NOW
    ctype = msg.get("channel_type")
    if ctype in ("dm", "mention"):
        return URGENCY_NOW if ctype == "mention" else URGENCY_TODAY
    return URGENCY_FYI


class Echo:
    def __init__(self, bridges: dict[str, MessageBridge] | None = None):
        self.bridges = bridges or {}

    def register(self, bridge: MessageBridge) -> None:
        self.bridges[bridge.surface] = bridge

    def triage(self, messages: list[dict]) -> AgentResponse:
        buckets: dict[str, list[dict]] = {URGENCY_NOW: [], URGENCY_TODAY: [], URGENCY_FYI: []}
        for m in messages:
            buckets[classify_urgency(m)].append(m)
        return AgentResponse(
            agent="echo",
            intent="triage_messages",
            action="triaged",
            result={
                "counts": {k: len(v) for k, v in buckets.items()},
                "buckets": buckets,
                "total": len(messages),
            },
            follow_ups=["draft replies for now"] if buckets[URGENCY_NOW] else [],
            confidence=0.9,
        )

    def draft_reply(self, surface: str, channel: str, body: str) -> AgentResponse:
        return AgentResponse(
            agent="echo",
            intent="draft_reply",
            action="proposed",
            result={"surface": surface, "channel": channel, "body": body},
            needs_confirm=True,
            confidence=0.85,
        )

    def send(self, surface: str, channel: str, body: str) -> AgentResponse:
        if surface not in self.bridges:
            return AgentResponse(
                agent="echo",
                intent="send_message",
                action="failed",
                result={"error": f"no bridge for {surface}"},
                confidence=0.0,
            )
        out = self.bridges[surface].send(channel, body)
        return AgentResponse(
            agent="echo",
            intent="send_message",
            action="sent",
            result={"surface": surface, "channel": channel, "response": out},
            confidence=1.0,
        )
