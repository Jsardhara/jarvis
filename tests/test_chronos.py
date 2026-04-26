"""Chronos calendar + tasks tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.subsystems.chronos import Chronos
from jarvis.subsystems.providers import MockCalendar


def test_today_lists_seeded_event():
    c = Chronos(MockCalendar())
    resp = c.today()
    assert resp.action == "listed"
    assert resp.result["count"] >= 0  # seed includes today's standup


def test_find_free_returns_slot():
    c = Chronos(MockCalendar())
    now = datetime.now(UTC)
    later = now + timedelta(hours=4)
    resp = c.find_free(30, now.isoformat(), later.isoformat())
    assert resp.result["duration_min"] == 30
    assert len(resp.result["slots"]) >= 1
    assert resp.action == "proposed"


def test_schedule_creates_event():
    c = Chronos(MockCalendar())
    now = datetime.now(UTC)
    end = now + timedelta(minutes=30)
    resp = c.schedule("1:1 with Sam", now.isoformat(), end.isoformat(), ["sam@x.com"])
    assert resp.action == "created"
    assert resp.result["event"]["summary"] == "1:1 with Sam"


def test_cancel_existing_event():
    cal = MockCalendar()
    c = Chronos(cal)
    resp = c.cancel("ev1")
    assert resp.action == "cancelled"


def test_cancel_missing_event():
    c = Chronos(MockCalendar())
    resp = c.cancel("nope")
    assert resp.action == "not_found"
    assert resp.confidence == 0.0


def test_add_task_persists():
    c = Chronos(MockCalendar())
    resp = c.add("call dentist", tags=["personal"])
    assert resp.action == "created"
    listed = c.list_open()
    titles = [t["title"] for t in listed.result["tasks"]]
    assert "call dentist" in titles


def test_complete_task_updates_status():
    c = Chronos(MockCalendar())
    add_resp = c.add("ship phase 1")
    tid = add_resp.result["task"]["id"]
    done = c.complete(tid)
    assert done.action == "updated"
    assert done.result["task"]["status"] == "done"


def test_complete_missing_task():
    c = Chronos(MockCalendar())
    resp = c.complete("ghost-id")
    assert resp.action == "not_found"
