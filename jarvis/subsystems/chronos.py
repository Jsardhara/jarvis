"""Chronos — calendar + tasks."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..contract import AgentResponse, Task
from ..state import add_task, load_tasks, update_task
from .providers import CalendarProvider


def _today_window() -> tuple[str, str]:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


class Chronos:
    def __init__(self, calendar: CalendarProvider):
        self.calendar = calendar

    # ---------- Calendar ----------

    def today(self) -> AgentResponse:
        start, end = _today_window()
        events = self.calendar.list_events(start, end)
        return AgentResponse(
            agent="chronos",
            intent="list_today",
            action="listed",
            result={"events": events, "count": len(events)},
            confidence=1.0,
        )

    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> AgentResponse:
        slots = self.calendar.find_free(duration_min, window_start_iso, window_end_iso)
        return AgentResponse(
            agent="chronos",
            intent="find_free_time",
            action="proposed",
            result={"slots": slots, "duration_min": duration_min},
            follow_ups=["create event in slot"],
            confidence=0.85,
        )

    def schedule(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> AgentResponse:
        evt = self.calendar.create_event(summary, start_iso, end_iso, attendees)
        return AgentResponse(
            agent="chronos",
            intent="create_event",
            action="created",
            result={"event": evt},
            needs_confirm=False,  # Already confirmed by user before invocation
            confidence=1.0,
        )

    def cancel(self, event_id: str) -> AgentResponse:
        out = self.calendar.cancel_event(event_id)
        return AgentResponse(
            agent="chronos",
            intent="cancel_event",
            action="cancelled" if out["found"] else "not_found",
            result=out,
            confidence=1.0 if out["found"] else 0.0,
        )

    # ---------- Tasks ----------

    def add(self, title: str, due: str | None = None, tags: list[str] | None = None) -> AgentResponse:
        t = Task(title=title, due=due, tags=tags or [])
        add_task(t)
        return AgentResponse(
            agent="chronos",
            intent="add_task",
            action="created",
            result={"task": t.model_dump()},
            confidence=1.0,
        )

    def list_open(self) -> AgentResponse:
        tasks = [t for t in load_tasks() if t.status == "open"]
        return AgentResponse(
            agent="chronos",
            intent="list_tasks",
            action="listed",
            result={"tasks": [t.model_dump() for t in tasks], "count": len(tasks)},
            confidence=1.0,
        )

    def complete(self, task_id: str) -> AgentResponse:
        updated = update_task(task_id, status="done", updated=datetime.now(UTC).isoformat())
        return AgentResponse(
            agent="chronos",
            intent="complete_task",
            action="updated" if updated else "not_found",
            result={"task": updated.model_dump() if updated else None},
            confidence=1.0 if updated else 0.0,
        )
