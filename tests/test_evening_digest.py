"""Tests for jarvis.state.briefing.evening_digest."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from jarvis.contract import AgentResponse, Task
from jarvis.state import add_task, read_inbox
from jarvis.state.briefing import evening_digest


class _MockDesc:
    """Minimal AgentDescriptor stand-in — ``call`` returns the mapped response."""

    def __init__(self, responses: dict[str, AgentResponse], instance=None) -> None:
        self._responses = responses
        self.instance = instance

    def call(self, action: str, _args: dict | None = None) -> AgentResponse:
        if action not in self._responses:
            raise ValueError(f"unknown action {action!r}")
        return self._responses[action]


class _TempoInstance:
    """Stub tempo instance exposing ``today_first_tomorrow``."""

    def __init__(self, first_event: dict | None) -> None:
        self._first = first_event

    def today_first_tomorrow(self) -> AgentResponse:
        return AgentResponse(
            agent="tempo",
            intent="today_first_tomorrow",
            action="ok",
            result=self._first or {},
        )


def test_evening_digest_renders_closed_tasks(isolated_state: Path) -> None:
    """A task done today appears under 'Today's closes'."""
    today_iso = datetime.now(UTC).isoformat()
    add_task(
        Task(
            title="Ship the patch",
            status="done",
            created=today_iso,
            updated=today_iso,
        )
    )
    notifier = MagicMock()
    out = evening_digest({}, notifier)

    assert "digest" in out
    assert "Ship the patch" in out["digest"]
    assert "Today's closes" in out["digest"]


def test_evening_digest_includes_tomorrow_first_event(isolated_state: Path) -> None:
    """Tomorrow's first calendar event title appears in the digest."""
    tomorrow_start = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    first = {"subject": "Standup with team", "start": tomorrow_start.isoformat()}
    reg = {"tempo": _MockDesc({}, instance=_TempoInstance(first))}

    notifier = MagicMock()
    out = evening_digest(reg, notifier)

    assert "Standup with team" in out["digest"]
    assert "Tomorrow's first event" in out["digest"]


def test_evening_digest_pushes_at_p1(isolated_state: Path) -> None:
    """The digest is pushed at priority=1 with title 'Evening recap'."""
    notifier = MagicMock()
    evening_digest({}, notifier)

    notifier.push.assert_called_once()
    args, kwargs = notifier.push.call_args
    assert args[0] == "Evening recap"
    priority = kwargs.get("priority", args[2] if len(args) >= 3 else None)
    assert priority == 1


def test_evening_digest_appends_inbox_event(isolated_state: Path) -> None:
    """The digest appends a single info-severity sentinel inbox event."""
    notifier = MagicMock()
    evening_digest({}, notifier)

    inbox = read_inbox(limit=5)
    assert any(
        ev.agent == "sentinel" and ev.severity == "info" and "Evening digest" in ev.summary
        for ev in inbox
    )
