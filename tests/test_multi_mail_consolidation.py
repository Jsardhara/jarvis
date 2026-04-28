"""Consolidation tests — MultiMailProvider promoted to registry default.

Covers the full unified-inbox surface: fan-out merging, sort-by-date,
recipient-domain routing for send, calendar aggregation through
TempoStack, and per-provider failure isolation. The integration test is
gated behind APPLE/GMAIL env vars so CI without secrets stays green.
"""
from __future__ import annotations

import os

import pytest

from jarvis.subsystems.multi_mail_provider import MailAccount, MultiMailProvider
from jarvis.subsystems.tempo_stack import TempoStack, build_default_tempo_stack

# ---------- fakes ----------


class _FakeMailBackend:
    """Mail backend fixture — implements the 4 mail Protocol methods."""

    def __init__(self, label: str, unread: list[dict] | None = None):
        self.label = label
        self._unread = unread or []
        self.calls: list[tuple] = []

    def list_unread(self, max_results: int = 25) -> list[dict]:
        self.calls.append(("list_unread", max_results))
        return [dict(item) for item in self._unread[:max_results]]

    def get_message(self, msg_id: str) -> dict:
        self.calls.append(("get_message", msg_id))
        return {"id": msg_id, "from": f"x@{self.label.lower()}.test", "subject": "s", "labels": []}

    def draft_reply(self, msg_id: str, body: str) -> dict:
        self.calls.append(("draft_reply", msg_id, body))
        return {"draft_id": "d", "in_reply_to": msg_id, "body": body, "label": self.label}

    def send(self, to: str, subject: str, body: str) -> dict:
        self.calls.append(("send", to, subject, body))
        return {"id": f"sent-{self.label}", "to": to, "subject": subject, "body": body, "label": self.label}


class _FakeCalendarBackend:
    """Calendar+tasks backend fixture — 7 Protocol methods."""

    def __init__(self, events: list[dict] | None = None, tasks: list[dict] | None = None):
        self._events = events or []
        self._tasks = tasks or []
        self.calls: list[tuple] = []

    def list_events(self, start, end):
        self.calls.append(("list_events", start, end))
        return [dict(e) for e in self._events]

    def create_event(self, summary, start, end, attendees):
        self.calls.append(("create_event", summary, start, end, list(attendees)))
        return {"id": "ev-new", "summary": summary, "start": start, "end": end}

    def find_free(self, duration_min, ws, we):
        self.calls.append(("find_free", duration_min, ws, we))
        return [{"start": ws, "end": we, "duration_min": duration_min}]

    def cancel_event(self, event_id):
        self.calls.append(("cancel_event", event_id))
        return {"cancelled": event_id, "found": True}

    def list_tasks(self):
        self.calls.append(("list_tasks",))
        return [dict(t) for t in self._tasks]

    def add_task_remote(self, title, due):
        self.calls.append(("add_task_remote", title, due))
        return {"id": "t-new", "title": title, "due": due, "status": "open"}

    def complete_task_remote(self, task_id):
        self.calls.append(("complete_task_remote", task_id))
        return {"id": task_id, "status": "done"}


# ---------- list_unread merging + sorting ----------


def test_list_unread_merges_from_all_providers():
    g = _FakeMailBackend("GMAIL", [
        {"id": "1", "subject": "g1", "date": "2026-04-28T10:00:00+00:00"},
        {"id": "2", "subject": "g2", "date": "2026-04-27T10:00:00+00:00"},
    ])
    d = _FakeMailBackend("DREXEL", [
        {"id": "9", "subject": "d1", "date": "2026-04-28T11:00:00+00:00"},
    ])
    multi = MultiMailProvider.from_backends(gmail=g, drexel=d, default="GMAIL")
    items = multi.list_unread(max_results=10)
    assert len(items) == 3
    accounts = {item["account"] for item in items}
    assert accounts == {"GMAIL", "DREXEL"}


def test_list_unread_sorted_by_date_desc():
    g = _FakeMailBackend("GMAIL", [
        {"id": "old", "date": "2026-04-20T10:00:00+00:00"},
        {"id": "new", "date": "2026-04-28T10:00:00+00:00"},
    ])
    d = _FakeMailBackend("DREXEL", [
        {"id": "mid", "date": "2026-04-25T10:00:00+00:00"},
    ])
    multi = MultiMailProvider.from_backends(gmail=g, drexel=d, default="GMAIL")
    items = multi.list_unread(max_results=10)
    ordered = [item["id"] for item in items]
    assert ordered == ["GMAIL:new", "DREXEL:mid", "GMAIL:old"]


def test_list_unread_missing_dates_sink_to_bottom():
    g = _FakeMailBackend("GMAIL", [
        {"id": "dated", "date": "2026-04-28T10:00:00+00:00"},
        {"id": "nodate"},  # no date field at all
    ])
    multi = MultiMailProvider.from_backends(gmail=g, drexel=None, default="GMAIL")
    items = multi.list_unread(max_results=10)
    assert items[0]["id"] == "GMAIL:dated"
    assert items[-1]["id"] == "GMAIL:nodate"


# ---------- send routing by recipient ----------


def test_send_mail_routes_to_correct_provider_by_from_address():
    g = _FakeMailBackend("GMAIL")
    d = _FakeMailBackend("DREXEL")
    multi = MultiMailProvider.from_backends(gmail=g, drexel=d, default="GMAIL")

    res = multi.send("prof@drexel.edu", "subj", "body")
    assert res["account"] == "DREXEL"
    assert d.calls and g.calls == []

    g.calls.clear()
    d.calls.clear()
    res = multi.send("buddy@gmail.com", "subj", "body")
    assert res["account"] == "GMAIL"
    assert g.calls and d.calls == []


# ---------- calendar aggregation through TempoStack ----------


def test_calendar_aggregates_today_events():
    cal = _FakeCalendarBackend(events=[
        {"id": "ev1", "summary": "Standup", "start": "2026-04-28T14:00:00+00:00"},
        {"id": "ev2", "summary": "Review", "start": "2026-04-28T16:00:00+00:00"},
    ])
    mail = _FakeMailBackend("GMAIL")
    multi = MultiMailProvider.from_backends(gmail=mail, drexel=None, default="GMAIL")
    stack = TempoStack(calendar=cal, mail=multi)
    events = stack.list_events("2026-04-28T00:00:00+00:00", "2026-04-28T23:59:59+00:00")
    assert len(events) == 2
    assert {e["id"] for e in events} == {"ev1", "ev2"}
    assert ("list_events", "2026-04-28T00:00:00+00:00", "2026-04-28T23:59:59+00:00") in cal.calls


# ---------- failure isolation ----------


def test_provider_failure_isolated(caplog):
    class _Broken(_FakeMailBackend):
        def list_unread(self, max_results: int = 25):
            raise RuntimeError("imap connection lost")

    g = _FakeMailBackend("GMAIL", [{"id": "1", "subject": "ok", "date": "2026-04-28T10:00:00+00:00"}])
    broken = _Broken("DREXEL")
    multi = MultiMailProvider(
        accounts=[MailAccount("GMAIL", g, "gmail.com"), MailAccount("DREXEL", broken, "drexel.edu")],
        default_label="GMAIL",
    )

    import logging

    with caplog.at_level(logging.WARNING, logger="jarvis.subsystems.multi_mail_provider"):
        items = multi.list_unread(max_results=10)

    assert len(items) == 1
    assert items[0]["account"] == "GMAIL"
    # Failure was logged (by name) but did not propagate
    assert any("DREXEL" in rec.message for rec in caplog.records)
    assert any("imap connection lost" in rec.message for rec in caplog.records)


def test_failure_in_one_provider_does_not_break_send_to_other():
    """If one backend's send fails, the other backend remains usable."""
    class _BrokenSend(_FakeMailBackend):
        def send(self, to, subject, body):
            raise RuntimeError("smtp down")

    g = _FakeMailBackend("GMAIL")
    broken_drexel = _BrokenSend("DREXEL")
    multi = MultiMailProvider(
        accounts=[MailAccount("GMAIL", g, "gmail.com"), MailAccount("DREXEL", broken_drexel, "drexel.edu")],
        default_label="GMAIL",
    )

    # Drexel send raises (synchronous, no retry magic)
    with pytest.raises(RuntimeError, match="smtp down"):
        multi.send("anyone@drexel.edu", "S", "B")

    # Gmail send still works
    res = multi.send("friend@gmail.com", "S", "B")
    assert res["account"] == "GMAIL"


# ---------- integration: real stack assembly when env present ----------


_have_apple = bool(os.getenv("APPLE_ID") and os.getenv("APPLE_APP_PASSWORD"))
_have_gmail = bool(os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD"))


@pytest.mark.skipif(
    not (_have_apple and _have_gmail),
    reason="requires APPLE_* and GMAIL_* env vars",
)
def test_real_stack_builds_when_apple_and_gmail_env_set():
    """Smoke test — TempoStack assembles without network calls.

    No actual IMAP/CalDAV connection is opened; constructors are lazy.
    """
    stack = build_default_tempo_stack()
    assert isinstance(stack, TempoStack)
    # Mail surface is MultiMailProvider; calendar is ICloudProvider.
    from jarvis.subsystems.icloud_provider import ICloudProvider
    from jarvis.subsystems.multi_mail_provider import MultiMailProvider as MMP

    assert isinstance(stack.mail, MMP)
    assert isinstance(stack.calendar, ICloudProvider)
    assert "GMAIL" in stack.mail.labels
