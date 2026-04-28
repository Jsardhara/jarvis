"""Provider protocols and mock implementations.

Tempo owns Outlook (mail + calendar + tasks) via Microsoft Graph.
Real OutlookProvider lands once Azure app registration is supplied.
Until then MockOutlook gives deterministic fixtures so the rest of the
stack runs end-to-end.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


class OutlookProvider(Protocol):
    # Mail
    def list_unread(self, max_results: int = 25) -> list[dict]: ...
    def get_message(self, msg_id: str) -> dict: ...
    def draft_reply(self, msg_id: str, body: str) -> dict: ...
    def send(self, to: str, subject: str, body: str) -> dict: ...

    # Calendar
    def list_events(self, start_iso: str, end_iso: str) -> list[dict]: ...
    def create_event(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> dict: ...
    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> list[dict]: ...
    def cancel_event(self, event_id: str) -> dict: ...

    # Tasks (Microsoft To Do)
    def list_tasks(self) -> list[dict]: ...
    def add_task_remote(self, title: str, due: str | None) -> dict: ...
    def complete_task_remote(self, task_id: str) -> dict: ...


class SearchProvider(Protocol):
    def search(self, query: str, num_results: int = 5) -> list[dict]: ...
    def fetch(self, url: str) -> dict: ...


# ---------- Mocks (default until creds wired) ----------


class MockOutlook:
    """Single mock that fakes mail + calendar + tasks behind the OutlookProvider Protocol."""

    def __init__(
        self,
        seed_mail: list[dict] | None = None,
        seed_events: list[dict] | None = None,
        seed_tasks: list[dict] | None = None,
    ):
        self._mail: dict[str, dict] = {m["id"]: m for m in (seed_mail if seed_mail is not None else _seed_mail())}
        self._events: dict[str, dict] = {e["id"]: e for e in (seed_events if seed_events is not None else _seed_events())}
        self._tasks: dict[str, dict] = {t["id"]: t for t in (seed_tasks if seed_tasks is not None else _seed_tasks())}
        self._sent: list[dict] = []

    # Mail
    def list_unread(self, max_results: int = 25) -> list[dict]:
        unread = [m for m in self._mail.values() if "UNREAD" in m.get("labels", [])]
        return unread[:max_results]

    def get_message(self, msg_id: str) -> dict:
        return self._mail[msg_id]

    def draft_reply(self, msg_id: str, body: str) -> dict:
        return {"draft_id": f"draft-{uuid4().hex[:8]}", "in_reply_to": msg_id, "body": body}

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

    # Calendar
    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return [e for e in self._events.values() if start_iso <= e["start"] <= end_iso]

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
        return [{"start": window_start_iso, "end": window_end_iso, "duration_min": duration_min}]

    def cancel_event(self, event_id: str) -> dict:
        evt = self._events.pop(event_id, None)
        return {"cancelled": event_id, "found": evt is not None}

    # Tasks
    def list_tasks(self) -> list[dict]:
        return list(self._tasks.values())

    def add_task_remote(self, title: str, due: str | None) -> dict:
        tid = f"todo-{uuid4().hex[:8]}"
        task = {"id": tid, "title": title, "due": due, "status": "open"}
        self._tasks[tid] = task
        return task

    def complete_task_remote(self, task_id: str) -> dict:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "done"
            return self._tasks[task_id]
        return {"id": task_id, "status": "not_found"}


def _seed_mail() -> list[dict]:
    return [
        {
            "id": "m1",
            "from": "professor@university.edu",
            "subject": "Office hours moved to Thursday",
            "snippet": "Hi class — moving Thursday OH to 2pm.",
            "labels": ["UNREAD", "INBOX"],
        },
        {
            "id": "m2",
            "from": "manager@work.com",
            "subject": "Friday review",
            "snippet": "Can we sync at 3pm Friday on the Q2 plan?",
            "labels": ["UNREAD", "INBOX", "IMPORTANT"],
        },
        {
            "id": "m3",
            "from": "newsletter@medium.com",
            "subject": "Top stories this week",
            "snippet": "The 10 best engineering reads…",
            "labels": ["UNREAD", "INBOX", "CATEGORY_PROMOTIONS"],
        },
    ]


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


def _seed_tasks() -> list[dict]:
    return [
        {"id": "todo-1", "title": "Submit CS401 problem set", "due": None, "status": "open"},
    ]


class MockSearch:
    def __init__(self, fixtures: dict[str, list[dict]] | None = None):
        self._fixtures = fixtures or {}

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        return self._fixtures.get(query, [
            {
                "title": f"Result {i + 1} for '{query}'",
                "url": f"https://example.com/{query.replace(' ', '-')}/{i + 1}",
                "snippet": f"Mock snippet {i + 1}",
                "score": 1.0 - i * 0.1,
            }
            for i in range(num_results)
        ])

    def fetch(self, url: str) -> dict:
        return {"url": url, "text": f"Mock body for {url}", "title": "Mock"}


class ExaSearch:
    """Exa search provider stub. Wired to real Exa MCP in Plan B2.

    Instantiated when EXA_API_KEY is present in env. search() and fetch()
    raise NotImplementedError until B2 wires the real Exa MCP transport.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        # TODO(B2): wire to real Exa MCP search tool
        raise NotImplementedError("ExaSearch.search wired in B2")

    def fetch(self, url: str) -> dict:
        # TODO(B2): wire to real Exa MCP fetch tool
        raise NotImplementedError("ExaSearch.fetch wired in B2")
