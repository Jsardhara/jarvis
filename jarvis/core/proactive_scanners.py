"""Proactivity scanners — R6/R7/R8.

Periodic polling rules that emit warn-severity InboxEvents when something
in the operator's world starts to need attention but no other subsystem
would have spoken up on its own:

* ``scan_meeting_imminent``  — calendar event 5/10/15 min away
* ``scan_assignments_due_soon`` — scholar assignment due in <24h
* ``scan_stale_tasks`` — open task untouched for >7 days

The companion module ``jarvis.core.triggers`` owns the fired-ledger and
the periodic-scan dispatcher; we reuse its dedup helpers so the operator
isn't paged twice for the same condition.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from jarvis.contract import InboxEvent

log = logging.getLogger(__name__)


class _NotifierProto(Protocol):
    """Minimal push interface — duck-typed against apps.sentinel.notifier."""

    def push(self, title: str, body: str, priority: int = 0) -> None: ...


_MEETING_BUCKETS_MIN = (5, 10, 15)


def _parse_iso(raw: str | None) -> datetime | None:
    """Parse a possibly-tz-naive ISO string into an aware UTC datetime."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _voice_context_next_event() -> dict[str, Any] | None:
    """Return cached next_event dict, or None when missing / not a dict."""
    try:
        from jarvis.apps.voice.context_cache import load_voice_context
    except Exception:
        return None
    ctx = load_voice_context()
    nxt = ctx.get("next_event") if isinstance(ctx, dict) else None
    return nxt if isinstance(nxt, dict) else None


def _tempo_next_event_today(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Fallback: ask tempo for today's events; return the first dict event."""
    tempo_desc = reg.get("tempo")
    if tempo_desc is None:
        return None
    try:
        resp = tempo_desc.call("today")
    except Exception:
        log.warning("scan_meeting_imminent: tempo.today fallback failed", exc_info=True)
        return None
    result = getattr(resp, "result", None)
    if not isinstance(result, dict):
        return None
    events = result.get("events", [])
    if not isinstance(events, list):
        return None
    for ev in events:
        if isinstance(ev, dict):
            return ev
    return None


def scan_meeting_imminent(
    reg: dict[str, Any],
    notifier: _NotifierProto | None = None,  # noqa: ARG001 — parity with scan_periodic
) -> list[InboxEvent]:
    """Emit warn events when the next event is 5/10/15 min away.

    Dedup is per (event_id, bucket) — the operator sees one 15-min warning,
    then a 10-min, then a 5-min — not three of each.
    """
    from jarvis.core.triggers import FiredTrigger, _record_fired, _was_fired_recently

    nxt = _voice_context_next_event() or _tempo_next_event_today(reg)
    if not nxt or not isinstance(nxt, dict):
        return []

    start_raw = nxt.get("start") or nxt.get("when") or nxt.get("start_time")
    start_dt = _parse_iso(start_raw if isinstance(start_raw, str) else None)
    if start_dt is None:
        return []

    now = datetime.now(UTC)
    minutes_away = (start_dt - now).total_seconds() / 60.0
    if minutes_away < 0 or minutes_away > _MEETING_BUCKETS_MIN[-1]:
        return []

    bucket: int | None = None
    for limit in _MEETING_BUCKETS_MIN:
        if minutes_away <= limit:
            bucket = limit
            break
    if bucket is None:
        return []

    event_id = str(
        nxt.get("event_id")
        or nxt.get("id")
        or nxt.get("subject")
        or nxt.get("title")
        or start_raw
        or "unknown"
    )
    source_key = f"meeting:{event_id}:{bucket}min"
    if _was_fired_recently("meeting_imminent", source_key):
        return []

    title = str(nxt.get("subject") or nxt.get("title") or "Untitled event")
    summary = f"{title} in {bucket} min"
    event = InboxEvent(
        agent="tempo",
        severity="warn",
        summary=summary,
        ref={"event_id": event_id, "bucket": f"{bucket}min", "starts_at": start_raw},
    )
    _record_fired(
        FiredTrigger(
            rule_name="meeting_imminent",
            source_key=source_key,
            action_summary=summary,
            outcome="ok",
        )
    )
    return [event]


def _assignment_due_dt(due: str) -> datetime | None:
    """Parse an assignment ``due`` string — supports ISO or date-only formats."""
    dt = _parse_iso(due)
    if dt is not None:
        return dt
    try:
        return datetime.fromisoformat(due + "T23:59:59+00:00")
    except ValueError:
        return None


def _assignment_fields(a: Any) -> tuple[str, str, str]:
    """Extract (id, due, title) from a dict or Task-like assignment."""
    if isinstance(a, dict):
        aid = str(a.get("id") or a.get("assignment_id") or "")
        due = str(a.get("due") or "")
        title = str(a.get("title") or "Untitled")
    else:
        aid = str(getattr(a, "id", "") or "")
        due = str(getattr(a, "due", "") or "")
        title = str(getattr(a, "title", "") or "Untitled")
    return aid, due, title


def scan_assignments_due_soon(reg: dict[str, Any]) -> list[InboxEvent]:
    """Emit warn events for scholar assignments due within 24h.

    Dedup is per ``assignment_id`` over the standard 24h window.
    """
    from jarvis.core.triggers import FiredTrigger, _record_fired, _was_fired_recently

    scholar_desc = reg.get("scholar")
    if scholar_desc is None:
        return []
    scholar_inst = getattr(scholar_desc, "instance", None)
    if scholar_inst is None:
        return []
    fn = getattr(scholar_inst, "list_assignments", None)
    if not callable(fn):
        return []

    try:
        resp = fn()
    except Exception:
        log.warning("scan_assignments_due_soon: list_assignments failed", exc_info=True)
        return []

    result = getattr(resp, "result", None)
    if not isinstance(result, dict):
        return []
    raw = result.get("assignments", []) or result.get("tasks", []) or []
    if not isinstance(raw, list):
        return []

    now = datetime.now(UTC)
    window_end = now + timedelta(hours=24)
    events: list[InboxEvent] = []

    for a in raw:
        aid, due, title = _assignment_fields(a)
        if not due:
            continue
        due_dt = _assignment_due_dt(due)
        if due_dt is None or not (now <= due_dt <= window_end):
            continue

        source_key = f"assignment_due:{aid}"
        if _was_fired_recently("assignment_due_soon", source_key):
            continue

        hours = max(0, int((due_dt - now).total_seconds() / 3600))
        summary = f"Due in {hours}h: {title}"
        events.append(
            InboxEvent(
                agent="scholar",
                severity="warn",
                summary=summary,
                ref={"assignment_id": aid, "due": due, "title": title},
            )
        )
        _record_fired(
            FiredTrigger(
                rule_name="assignment_due_soon",
                source_key=source_key,
                action_summary=summary,
                outcome="ok",
            )
        )

    return events


def scan_stale_tasks() -> list[InboxEvent]:
    """Emit warn events for open tasks created >7 days ago.

    Dedup key is per (task_id, ISO week) — each stale task triggers at most
    once per week.
    """
    from jarvis.core.triggers import (
        FiredTrigger,
        _load_tasks_raw,
        _record_fired,
        _was_fired_recently,
    )

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=7)
    events: list[InboxEvent] = []

    for task in _load_tasks_raw():
        if task.get("status", "open") != "open":
            continue
        created_dt = _parse_iso(task.get("created", ""))
        if created_dt is None or created_dt > cutoff:
            continue

        task_id = str(task.get("id", ""))
        iso_year, iso_week, _ = now.isocalendar()
        source_key = f"stale_task:{task_id}:{iso_year}W{iso_week:02d}"
        if _was_fired_recently("stale_task", source_key):
            continue

        days_old = int((now - created_dt).total_seconds() / 86400)
        title = str(task.get("title", "Untitled"))
        summary = f"Stale {days_old}d: {title}"
        events.append(
            InboxEvent(
                agent="tempo",
                severity="warn",
                summary=summary,
                ref={"task_id": task_id, "days_old": days_old, "title": title},
            )
        )
        _record_fired(
            FiredTrigger(
                rule_name="stale_task",
                source_key=source_key,
                action_summary=summary,
                outcome="ok",
            )
        )

    return events


__all__ = [
    "scan_meeting_imminent",
    "scan_assignments_due_soon",
    "scan_stale_tasks",
]
