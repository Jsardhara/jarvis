"""Unit tests for MockOutlook and MockSearch providers."""
from __future__ import annotations

from jarvis.subsystems.providers import MockOutlook, MockSearch

# --- MockOutlook: mail ---


def test_get_message_returns_seeded_mail():
    p = MockOutlook()
    msg = p.get_message("m1")
    assert msg["id"] == "m1"
    assert "from" in msg


def test_draft_reply_returns_draft_id():
    p = MockOutlook()
    d = p.draft_reply("m1", "Thanks!")
    assert "draft_id" in d
    assert d["in_reply_to"] == "m1"
    assert d["body"] == "Thanks!"


def test_send_records_and_returns_sent_message():
    p = MockOutlook()
    rec = p.send("bob@example.com", "Hi", "Body text")
    assert rec["to"] == "bob@example.com"
    assert rec["subject"] == "Hi"
    assert "ts" in rec


def test_sent_property_grows_with_sends():
    p = MockOutlook()
    assert p.sent == []
    p.send("a@b.com", "s1", "b1")
    p.send("c@d.com", "s2", "b2")
    assert len(p.sent) == 2


# --- MockOutlook: calendar ---


def test_create_event_adds_to_internal_store():
    p = MockOutlook()
    before = len(p.list_events("2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))
    evt = p.create_event("Team sync", "2026-06-01T10:00:00+00:00", "2026-06-01T11:00:00+00:00", ["x@y.com"])
    assert "id" in evt
    after = len(p.list_events("2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))
    assert after == before + 1


def test_find_free_returns_slot():
    p = MockOutlook()
    slots = p.find_free(30, "2026-06-01T09:00:00+00:00", "2026-06-01T17:00:00+00:00")
    assert len(slots) == 1
    assert slots[0]["duration_min"] == 30


def test_cancel_event_removes_it():
    p = MockOutlook()
    evt = p.create_event("To cancel", "2026-07-01T10:00:00+00:00", "2026-07-01T11:00:00+00:00", [])
    eid = evt["id"]
    result = p.cancel_event(eid)
    assert result["cancelled"] == eid
    assert result["found"] is True


def test_cancel_missing_event_returns_not_found():
    p = MockOutlook()
    result = p.cancel_event("nonexistent")
    assert result["found"] is False


# --- MockOutlook: tasks ---


def test_list_tasks_returns_seeded_tasks():
    p = MockOutlook()
    tasks = p.list_tasks()
    assert len(tasks) >= 1
    assert all("id" in t for t in tasks)


def test_add_task_remote_creates_task():
    p = MockOutlook()
    before = len(p.list_tasks())
    t = p.add_task_remote("New task", "2026-12-01")
    assert t["title"] == "New task"
    assert t["due"] == "2026-12-01"
    assert len(p.list_tasks()) == before + 1


def test_complete_task_remote_marks_done():
    p = MockOutlook()
    t = p.add_task_remote("Finish report", None)
    result = p.complete_task_remote(t["id"])
    assert result["status"] == "done"


def test_complete_task_remote_missing_returns_not_found():
    p = MockOutlook()
    result = p.complete_task_remote("ghost-id")
    assert result["status"] == "not_found"


# --- MockSearch ---


def test_mock_search_fetch_returns_body():
    s = MockSearch()
    result = s.fetch("https://example.com/page")
    assert result["url"] == "https://example.com/page"
    assert "text" in result
    assert "title" in result
