"""Aide — email triage + draft replies."""
from __future__ import annotations

from ..contract import AgentResponse
from .providers import GmailProvider

# Triage tiers — informed by chief-of-staff skill
TIER_SKIP = "skip"
TIER_INFO = "info_only"
TIER_MEETING = "meeting_info"
TIER_ACTION = "action_required"

_PROMO_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
_MEETING_KEYWORDS = ("meet", "sync", "call", "calendar", "invite", "schedule")
_ACTION_KEYWORDS = ("action", "due", "asap", "urgent", "review", "approve", "respond")


def classify_message(msg: dict) -> str:
    """Bucket one Gmail message into one of four tiers."""
    labels = set(msg.get("labels", []))
    snippet = (msg.get("snippet", "") + " " + msg.get("subject", "")).lower()

    if labels & _PROMO_LABELS:
        return TIER_SKIP
    if any(k in snippet for k in _MEETING_KEYWORDS):
        return TIER_MEETING
    if any(k in snippet for k in _ACTION_KEYWORDS):
        return TIER_ACTION
    if "IMPORTANT" in labels:
        return TIER_ACTION
    return TIER_INFO


class Aide:
    def __init__(self, gmail: GmailProvider):
        self.gmail = gmail

    def triage(self, max_results: int = 25) -> AgentResponse:
        msgs = self.gmail.list_unread(max_results=max_results)
        buckets: dict[str, list[dict]] = {
            TIER_SKIP: [],
            TIER_INFO: [],
            TIER_MEETING: [],
            TIER_ACTION: [],
        }
        for m in msgs:
            tier = classify_message(m)
            buckets[tier].append(
                {"id": m["id"], "from": m.get("from"), "subject": m.get("subject"),
                 "snippet": m.get("snippet")}
            )

        action_count = len(buckets[TIER_ACTION])
        meeting_count = len(buckets[TIER_MEETING])
        return AgentResponse(
            agent="aide",
            intent="triage_inbox",
            action="triaged",
            result={
                "counts": {k: len(v) for k, v in buckets.items()},
                "buckets": buckets,
                "total": len(msgs),
            },
            follow_ups=(
                ["draft replies for action_required"] if action_count else []
            ) + (
                ["accept/decline meeting requests"] if meeting_count else []
            ),
            confidence=0.95,
        )

    def draft_reply(self, msg_id: str, body: str) -> AgentResponse:
        draft = self.gmail.draft_reply(msg_id, body)
        return AgentResponse(
            agent="aide",
            intent="draft_reply",
            action="proposed",
            result={"draft": draft},
            follow_ups=["confirm to send"],
            needs_confirm=True,
            confidence=0.9,
        )

    def send(self, to: str, subject: str, body: str) -> AgentResponse:
        sent = self.gmail.send(to, subject, body)
        return AgentResponse(
            agent="aide",
            intent="send_email",
            action="sent",
            result={"sent": sent},
            confidence=1.0,
        )
