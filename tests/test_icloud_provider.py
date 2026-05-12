"""Tests for ICloudProvider — mock caldav layer."""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from jarvis.agents.tempo.providers.icloud import (
    ICloudCalDAVError,
    ICloudConfig,
    ICloudProvider,
    _build_event_ical,
    _build_todo_ical,
    _escape,
    _parse_iso,
    _to_dt,
)


def _make_event_obj(uid: str, summary: str, start: datetime, end: datetime, attendees=None):
    obj = MagicMock()
    comp = {
        "uid": uid,
        "summary": summary,
        "dtstart": MagicMock(dt=start),
        "dtend": MagicMock(dt=end),
    }
    if attendees:
        comp["attendee"] = [f"mailto:{a}" for a in attendees]
    obj.icalendar_component = comp
    return obj


def _make_todo_obj(uid: str, summary: str, due: datetime | None, status: str = ""):
    obj = MagicMock()
    comp = {"uid": uid, "summary": summary, "status": status}
    if due:
        comp["due"] = MagicMock(dt=due)
    obj.icalendar_component = comp
    return obj


class _FakeCalendar:
    def __init__(self, components: list[str], events=(), todos=()):
        self._components = components
        self._events = list(events)
        self._todos = list(todos)
        self.saved_events: list[str] = []
        self.saved_todos: list[str] = []

    def get_supported_components(self):
        return self._components

    def search(self, start, end, event=False, expand=False):
        return self._events

    def todos(self):
        return self._todos

    def save_event(self, ical):
        self.saved_events.append(ical)

    def save_todo(self, ical):
        self.saved_todos.append(ical)

    def event_by_uid(self, uid: str):
        for e in self._events:
            if str(e.icalendar_component.get("uid")) == uid:
                return e
        raise KeyError(uid)

    def todo_by_uid(self, uid: str):
        for t in self._todos:
            if str(t.icalendar_component.get("uid")) == uid:
                return t
        raise KeyError(uid)


class _FakePrincipal:
    def __init__(self, calendars):
        self._cals = calendars

    def calendars(self):
        return self._cals


class _FakeClient:
    def __init__(self, principal):
        self._principal = principal

    def principal(self):
        return self._principal


@pytest.fixture
def cfg():
    return ICloudConfig(apple_id="x@icloud.com", app_password="aaaa-bbbb")


def test_parse_iso_handles_z_and_offset():
    dt = _parse_iso("2026-01-01T10:00:00Z")
    assert dt.tzinfo is not None
    dt2 = _parse_iso("2026-01-01T10:00:00+00:00")
    assert dt == dt2


def test_to_dt_promotes_date_to_aware_datetime():
    d = date(2026, 1, 1)
    dt = _to_dt(d)
    assert dt.tzinfo == UTC
    assert dt.year == 2026


def test_escape_handles_special_chars():
    assert _escape("a, b; c\nd") == "a\\, b\\; c\\nd"


def test_build_event_ical_contains_required_fields():
    s = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    e = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    ical = _build_event_ical(uid="uid1", summary="Meet", start=s, end=e, attendees=["a@b.com"])
    assert "UID:uid1" in ical
    assert "SUMMARY:Meet" in ical
    assert "DTSTART:20260101T100000Z" in ical
    assert "ATTENDEE:mailto:a@b.com" in ical


def test_build_todo_ical_with_due():
    due = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    ical = _build_todo_ical(uid="t1", summary="Pay rent", due=due)
    assert "BEGIN:VTODO" in ical
    assert "DUE:20260201T120000Z" in ical
    assert "SUMMARY:Pay rent" in ical


def test_build_todo_ical_without_due():
    ical = _build_todo_ical(uid="t1", summary="Read", due=None)
    assert "DUE:" not in ical


def test_list_events_maps_attendees(cfg):
    s = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    e = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    ev = _make_event_obj("ev1", "Standup", s, e, attendees=["team@x.com"])
    cal = _FakeCalendar(["VEVENT"], events=[ev])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    out = p.list_events("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
    assert len(out) == 1
    assert out[0]["id"] == "ev1"
    assert out[0]["summary"] == "Standup"
    assert out[0]["attendees"] == ["team@x.com"]


def test_create_event_saves_ical_and_returns_envelope(cfg):
    cal = _FakeCalendar(["VEVENT"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.create_event("Sync", "2026-03-01T10:00:00Z", "2026-03-01T11:00:00Z", ["a@b.com"])
    assert res["summary"] == "Sync"
    assert res["attendees"] == ["a@b.com"]
    assert len(cal.saved_events) == 1
    assert "BEGIN:VEVENT" in cal.saved_events[0]


def test_cancel_event_returns_found_true_when_present(cfg):
    s = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    e = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    evt = _make_event_obj("ev1", "X", s, e)
    cal = _FakeCalendar(["VEVENT"], events=[evt])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.cancel_event("ev1")
    assert res == {"cancelled": "ev1", "found": True}


def test_cancel_event_returns_found_false_when_missing(cfg):
    cal = _FakeCalendar(["VEVENT"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.cancel_event("missing")
    assert res == {"cancelled": "missing", "found": False}


def test_find_free_returns_window_when_no_events(cfg):
    cal = _FakeCalendar(["VEVENT"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    free = p.find_free(30, "2026-01-01T09:00:00Z", "2026-01-01T17:00:00Z")
    assert len(free) == 1
    assert free[0]["duration_min"] == 30


def test_find_free_subtracts_busy_intervals(cfg):
    s = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    e = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
    ev = _make_event_obj("ev1", "Lunch", s, e)
    cal = _FakeCalendar(["VEVENT"], events=[ev])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    free = p.find_free(30, "2026-01-01T09:00:00Z", "2026-01-01T17:00:00Z")
    # Should produce two slots: 9-12 and 13-17, both ≥30min
    assert len(free) == 2


def test_list_tasks_maps_status(cfg):
    due = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    open_t = _make_todo_obj("t1", "Read", due, status="NEEDS-ACTION")
    done_t = _make_todo_obj("t2", "Done", None, status="COMPLETED")
    cal = _FakeCalendar(["VTODO"], todos=[open_t, done_t])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    items = p.list_tasks()
    statuses = {t["id"]: t["status"] for t in items}
    assert statuses == {"t1": "open", "t2": "done"}


def test_add_task_remote_saves_todo(cfg):
    cal = _FakeCalendar(["VTODO"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.add_task_remote("Submit assignment", "2026-04-30T23:59:00Z")
    assert res["status"] == "open"
    assert len(cal.saved_todos) == 1
    assert "SUMMARY:Submit assignment" in cal.saved_todos[0]


def test_complete_task_remote_returns_done(cfg):
    todo = _make_todo_obj("t1", "Read", None)
    cal = _FakeCalendar(["VTODO"], todos=[todo])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.complete_task_remote("t1")
    assert res == {"id": "t1", "status": "done"}
    todo.complete.assert_called_once()


def test_complete_task_remote_not_found(cfg):
    cal = _FakeCalendar(["VTODO"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    res = p.complete_task_remote("missing")
    assert res == {"id": "missing", "status": "not_found"}


def test_no_vevent_calendar_raises(cfg):
    cal = _FakeCalendar(["VTODO"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    with pytest.raises(ICloudCalDAVError):
        p.list_events("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")


def test_no_vtodo_calendar_raises(cfg):
    cal = _FakeCalendar(["VEVENT"])
    client = _FakeClient(_FakePrincipal([cal]))
    p = ICloudProvider(cfg, client=client)
    with pytest.raises(ICloudCalDAVError):
        p.list_tasks()


def test_missing_config_raises_on_build(cfg):
    p = ICloudProvider(config=None, client=None)
    with pytest.raises(ICloudCalDAVError):
        p._build_client()
