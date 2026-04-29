"""Tempo — Outlook agent. Owns mail + calendar + tasks (single MS Graph token).

Why one agent: Outlook mail, calendar, and Microsoft To Do all live behind
one OAuth scope. Splitting them creates fake boundaries. Tempo is the
single time-and-correspondence agent for the operator.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..contract import AgentResponse, Task
from ..state import add_task, load_tasks, update_task
from .providers import OutlookProvider

# Mail triage tiers
TIER_SKIP = "skip"
TIER_INFO = "info_only"
TIER_MEETING = "meeting_info"
TIER_ACTION = "action_required"

_PROMO_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
_MEETING_KEYWORDS = ("meet", "sync", "call", "calendar", "invite", "schedule")
_ACTION_KEYWORDS = ("action", "due", "asap", "urgent", "review", "approve", "respond")


def classify_message(msg: dict) -> str:
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


def _today_window() -> tuple[str, str]:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


class Tempo:
    def __init__(self, outlook: OutlookProvider):
        self.outlook = outlook

    # ---------- Mail ----------

    def triage(self, max_results: int = 25) -> AgentResponse:
        msgs = self.outlook.list_unread(max_results=max_results)
        buckets: dict[str, list[dict]] = {
            TIER_SKIP: [], TIER_INFO: [], TIER_MEETING: [], TIER_ACTION: [],
        }
        for m in msgs:
            tier = classify_message(m)
            buckets[tier].append({
                "id": m["id"], "from": m.get("from"),
                "subject": m.get("subject"), "snippet": m.get("snippet"),
            })
        return AgentResponse(
            agent="tempo",
            intent="triage_inbox",
            action="triaged",
            result={
                "counts": {k: len(v) for k, v in buckets.items()},
                "buckets": buckets,
                "total": len(msgs),
            },
            follow_ups=(
                ["draft replies for action_required"] if buckets[TIER_ACTION] else []
            ) + (
                ["accept/decline meeting requests"] if buckets[TIER_MEETING] else []
            ),
            confidence=0.95,
        )

    def draft_reply(self, msg_id: str, body: str) -> AgentResponse:
        draft = self.outlook.draft_reply(msg_id, body)
        return AgentResponse(
            agent="tempo",
            intent="draft_reply",
            action="proposed",
            result={"draft": draft},
            follow_ups=["confirm to send"],
            needs_confirm=True,
            confidence=0.9,
        )

    def send_mail(self, to: str, subject: str, body: str) -> AgentResponse:
        sent = self.outlook.send(to, subject, body)
        return AgentResponse(
            agent="tempo",
            intent="send_mail",
            action="sent",
            result={"sent": sent},
            confidence=1.0,
        )

    # ---------- Calendar ----------

    def today(self) -> AgentResponse:
        start, end = _today_window()
        events = self.outlook.list_events(start, end)
        return AgentResponse(
            agent="tempo",
            intent="list_today",
            action="listed",
            result={"events": events, "count": len(events)},
            confidence=1.0,
        )

    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> AgentResponse:
        slots = self.outlook.find_free(duration_min, window_start_iso, window_end_iso)
        return AgentResponse(
            agent="tempo",
            intent="find_free_time",
            action="proposed",
            result={"slots": slots, "duration_min": duration_min},
            follow_ups=["create event in slot"],
            confidence=0.85,
        )

    def schedule(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> AgentResponse:
        evt = self.outlook.create_event(summary, start_iso, end_iso, attendees)
        return AgentResponse(
            agent="tempo",
            intent="create_event",
            action="created",
            result={"event": evt},
            needs_confirm=False,
            confidence=1.0,
        )

    def cancel(self, event_id: str) -> AgentResponse:
        out = self.outlook.cancel_event(event_id)
        return AgentResponse(
            agent="tempo",
            intent="cancel_event",
            action="cancelled" if out["found"] else "not_found",
            result=out,
            confidence=1.0 if out["found"] else 0.0,
        )

    # ---------- Tasks (local + Microsoft To Do mirror) ----------

    def add(self, title: str, due: str | None = None, tags: list[str] | None = None) -> AgentResponse:
        t = Task(title=title, due=due, tags=tags or [])
        add_task(t)
        return AgentResponse(
            agent="tempo",
            intent="add_task",
            action="created",
            result={"task": t.model_dump()},
            confidence=1.0,
        )

    def list_open(self) -> AgentResponse:
        tasks = [t for t in load_tasks() if t.status == "open"]
        return AgentResponse(
            agent="tempo",
            intent="list_tasks",
            action="listed",
            result={"tasks": [t.model_dump() for t in tasks], "count": len(tasks)},
            confidence=1.0,
        )

    def complete(self, task_id: str) -> AgentResponse:
        updated = update_task(task_id, status="done", updated=datetime.now(UTC).isoformat())
        return AgentResponse(
            agent="tempo",
            intent="complete_task",
            action="updated" if updated else "not_found",
            result={"task": updated.model_dump() if updated else None},
            confidence=1.0 if updated else 0.0,
        )
