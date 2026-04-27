"""Tests for TempoStack — composes calendar + mail behind OutlookProvider Protocol."""
from __future__ import annotations

import pytest

from jarvis.subsystems.tempo_stack import TempoStack, build_default_tempo_stack


class _FakeCalendar:
    def __init__(self):
        self.calls: list[tuple] = []

    def list_events(self, start, end):
        self.calls.append(("list_events", start, end))
        return [{"id": "ev1"}]

    def create_event(self, summary, start, end, attendees):
        self.calls.append(("create_event", summary, start, end, attendees))
        return {"id": "ev2", "summary": summary}

    def find_free(self, duration_min, ws, we):
        self.calls.append(("find_free", duration_min, ws, we))
        return [{"start": ws, "end": we, "duration_min": duration_min}]

    def cancel_event(self, event_id):
        self.calls.append(("cancel_event", event_id))
        return {"cancelled": event_id, "found": True}

    def list_tasks(self):
        self.calls.append(("list_tasks",))
        return [{"id": "t1", "status": "open"}]

    def add_task_remote(self, title, due):
        self.calls.append(("add_task_remote", title, due))
        return {"id": "t2", "title": title, "due": due, "status": "open"}

    def complete_task_remote(self, task_id):
        self.calls.append(("complete_task_remote", task_id))
        return {"id": task_id, "status": "done"}


class _FakeMail:
    def __init__(self):
        self.calls: list[tuple] = []

    def list_unread(self, max_results=25):
        self.calls.append(("list_unread", max_results))
        return [{"id": "GMAIL:1"}]

    def get_message(self, msg_id):
        self.calls.append(("get_message", msg_id))
        return {"id": msg_id}

    def draft_reply(self, msg_id, body):
        self.calls.append(("draft_reply", msg_id, body))
        return {"draft_id": "d", "in_reply_to": msg_id, "body": body}

    def send(self, to, subject, body):
        self.calls.append(("send", to, subject, body))
        return {"id": "sent", "to": to}


def test_stack_proxies_calendar_methods():
    cal = _FakeCalendar()
    mail = _FakeMail()
    s = TempoStack(calendar=cal, mail=mail)
    assert s.list_events("a", "b") == [{"id": "ev1"}]
    assert s.create_event("S", "a", "b", ["x@y"])["summary"] == "S"
    assert s.find_free(30, "a", "b")[0]["duration_min"] == 30
    assert s.cancel_event("ev1")["found"] is True
    assert s.list_tasks() == [{"id": "t1", "status": "open"}]
    assert s.add_task_remote("Read", None)["title"] == "Read"
    assert s.complete_task_remote("t1") == {"id": "t1", "status": "done"}
    assert ("list_events", "a", "b") in cal.calls


def test_stack_proxies_mail_methods():
    cal = _FakeCalendar()
    mail = _FakeMail()
    s = TempoStack(calendar=cal, mail=mail)
    assert s.list_unread(5)[0]["id"] == "GMAIL:1"
    assert s.get_message("GMAIL:1")["id"] == "GMAIL:1"
    assert s.draft_reply("GMAIL:1", "hi")["body"] == "hi"
    assert s.send("a@b.com", "S", "B")["to"] == "a@b.com"
    assert ("send", "a@b.com", "S", "B") in mail.calls


def test_build_default_raises_when_apple_missing(monkeypatch):
    monkeypatch.delenv("APPLE_ID", raising=False)
    monkeypatch.delenv("APPLE_APP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        build_default_tempo_stack()


def test_build_default_raises_when_gmail_missing(monkeypatch):
    monkeypatch.setenv("APPLE_ID", "x@icloud.com")
    monkeypatch.setenv("APPLE_APP_PASSWORD", "pw")
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        build_default_tempo_stack()


def test_build_default_succeeds_without_drexel(monkeypatch):
    monkeypatch.setenv("APPLE_ID", "x@icloud.com")
    monkeypatch.setenv("APPLE_APP_PASSWORD", "pw")
    monkeypatch.setenv("GMAIL_ADDRESS", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.delenv("DREXEL_ADDRESS", raising=False)
    monkeypatch.delenv("DREXEL_CLIENT_ID", raising=False)
    stack = build_default_tempo_stack()
    assert stack.mail.labels == ["GMAIL"]


def test_build_default_includes_drexel_when_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ID", "x@icloud.com")
    monkeypatch.setenv("APPLE_APP_PASSWORD", "pw")
    monkeypatch.setenv("GMAIL_ADDRESS", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setenv("DREXEL_ADDRESS", "u@drexel.edu")
    monkeypatch.setenv("DREXEL_CLIENT_ID", "fake-id")
    monkeypatch.setenv("DREXEL_TOKEN_CACHE", str(tmp_path / "cache.json"))
    stack = build_default_tempo_stack()
    assert sorted(stack.mail.labels) == ["DREXEL", "GMAIL"]
