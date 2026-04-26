"""Provider protocols — Gmail, Calendar, etc. behind small interfaces.

Phase 1 ships in-memory mock implementations. Phase 1.5 swaps to MCP
(claude.ai Gmail/Calendar/Drive) once OAuth is wired by the operator.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


class GmailProvider(Protocol):
    def list_unread(self, max_results: int = 25) -> list[dict]: ...
    def get_message(self, msg_id: str) -> dict: ...
    def draft_reply(self, msg_id: str, body: str) -> dict: ...
    def send(self, to: str, subject: str, body: str) -> dict: ...


class CalendarProvider(Protocol):
    def list_events(self, start_iso: str, end_iso: str) -> list[dict]: ...
    def create_event(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> dict: ...
    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> list[dict]: ...
    def cancel_event(self, event_id: str) -> dict: ...


# ---------- Mocks (Phase 1 default) ----------


class MockGmail:
    def __init__(self, seed: list[dict] | None = None):
        # Empty list must NOT trigger fallback — only None does
        msgs = _seed_emails() if seed is None else seed
        self._messages: dict[str, dict] = {m["id"]: m for m in msgs}
        self._sent: list[dict] = []

    def list_unread(self, max_results: int = 25) -> list[dict]:
        unread = [m for m in self._messages.values() if "UNREAD" in m.get("labels", [])]
        return unread[:max_results]

    def get_message(self, msg_id: str) -> dict:
        return self._messages[msg_id]

    def draft_reply(self, msg_id: str, body: str) -> dict:
        return {
            "draft_id": f"draft-{uuid4().hex[:8]}",
            "in_reply_to": msg_id,
            "body": body,
        }

    def send(self, to: str, subject: str, body: str) -> dict:
        rec = {
            "id": f"sent-{uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "ts": datetime.now(UTC).isoformat(),
        }
        self._sent.append(rec)
        return rec

    @property
    def sent(self) -> list[dict]:
        return list(self._sent)


def _seed_emails() -> list[dict]:
    return [
        {
            "id": "m1",
            "from": "boss@example.com",
            "subject": "Friday review",
            "snippet": "Can we sync at 3pm Friday on the Q2 plan?",
            "labels": ["UNREAD", "INBOX", "IMPORTANT"],
        },
        {
            "id": "m2",
            "from": "newsletter@medium.com",
            "subject": "Top stories this week",
            "snippet": "The 10 best engineering reads…",
            "labels": ["UNREAD", "INBOX", "CATEGORY_PROMOTIONS"],
        },
        {
            "id": "m3",
            "from": "ops@vendor.io",
            "subject": "Invoice #4421 due",
            "snippet": "Reminder: invoice payable by EOM.",
            "labels": ["UNREAD", "INBOX"],
        },
    ]


class MockCalendar:
    def __init__(self, seed: list[dict] | None = None):
        evts = _seed_events() if seed is None else seed
        self._events: dict[str, dict] = {e["id"]: e for e in evts}

    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return [
            e for e in self._events.values()
            if start_iso <= e["start"] <= end_iso
        ]

    def create_event(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> dict:
        eid = f"ev-{uuid4().hex[:8]}"
        evt = {
            "id": eid,
            "summary": summary,
            "start": start_iso,
            "end": end_iso,
            "attendees": attendees,
        }
        self._events[eid] = evt
        return evt

    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> list[dict]:
        # Naive mock: returns single slot at window_start
        return [
            {
                "start": window_start_iso,
                "end": window_end_iso,
                "duration_min": duration_min,
            }
        ]

    def cancel_event(self, event_id: str) -> dict:
        evt = self._events.pop(event_id, None)
        return {"cancelled": event_id, "found": evt is not None}


def _seed_events() -> list[dict]:
    today = datetime.now(UTC).date().isoformat()
    return [
        {
            "id": "ev1",
            "summary": "Standup",
            "start": f"{today}T14:00:00+00:00",
            "end": f"{today}T14:30:00+00:00",
            "attendees": ["team@example.com"],
        },
    ]
