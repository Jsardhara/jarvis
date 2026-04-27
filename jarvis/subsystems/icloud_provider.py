"""iCloud calendar + reminders provider via CalDAV.

Implements the calendar + tasks subset of the OutlookProvider Protocol.
Mail is delegated to a separate provider (Gmail / Drexel) via composition.

Auth: Apple ID + app-specific password (https://appleid.apple.com → App-Specific Passwords).
Endpoint: https://caldav.icloud.com (iCloud follows RFC 4791 CalDAV).

Apple Reminders are stored as CalDAV todos in a calendar collection whose
``supported-calendar-component-set`` includes ``VTODO``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import Iterable


logger = logging.getLogger(__name__)


class ICloudCalDAVError(RuntimeError):
    """Raised when CalDAV operations fail."""


@dataclass(frozen=True)
class ICloudConfig:
    apple_id: str
    app_password: str
    caldav_url: str = "https://caldav.icloud.com"


def _parse_iso(value: str) -> datetime:
    """Parse ISO-8601 → aware datetime (UTC if naive)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


class ICloudProvider:
    """CalDAV-backed calendar + reminders provider.

    Implements 7 of the 11 OutlookProvider Protocol methods (calendar + tasks).
    Mail methods are intentionally absent — wire via composition with a mail
    provider in MultiMailProvider / TempoStack.
    """

    def __init__(
        self,
        config: ICloudConfig | None = None,
        client: Any | None = None,  # injection seam for tests
    ):
        self._config = config
        self._client = client
        self._principal: Any | None = None
        self._cal: Any | None = None
        self._reminders: Any | None = None

    # ---------- internals ----------

    def _build_client(self) -> Any:
        """Lazy-construct caldav.DAVClient."""
        if self._client is not None:
            return self._client
        if self._config is None:
            raise ICloudCalDAVError("ICloudProvider missing config")
        import caldav  # lazy import keeps test scaffolding cheap

        self._client = caldav.DAVClient(
            url=self._config.caldav_url,
            username=self._config.apple_id,
            password=self._config.app_password,
        )
        return self._client

    def _get_principal(self) -> Any:
        if self._principal is None:
            self._principal = self._build_client().principal()
        return self._principal

    def _get_calendar(self) -> Any:
        """Return primary VEVENT calendar, lazy-resolved."""
        if self._cal is None:
            for cal in self._get_principal().calendars():
                comps = _supported_components(cal)
                if "VEVENT" in comps:
                    self._cal = cal
                    break
            if self._cal is None:
                raise ICloudCalDAVError("no VEVENT calendar found on principal")
        return self._cal

    def _get_reminders(self) -> Any:
        """Return primary VTODO calendar (Apple Reminders), lazy-resolved."""
        if self._reminders is None:
            for cal in self._get_principal().calendars():
                comps = _supported_components(cal)
                if "VTODO" in comps:
                    self._reminders = cal
                    break
            if self._reminders is None:
                raise ICloudCalDAVError("no VTODO calendar (Reminders) found")
        return self._reminders

    # ---------- calendar ----------

    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        cal = self._get_calendar()
        start, end = _parse_iso(start_iso), _parse_iso(end_iso)
        events = cal.search(start=start, end=end, event=True, expand=True)
        return [_map_event(e) for e in events]

    def create_event(
        self,
        summary: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
    ) -> dict:
        cal = self._get_calendar()
        start, end = _parse_iso(start_iso), _parse_iso(end_iso)
        uid = f"jarvis-{uuid4().hex[:12]}@icloud"
        ical = _build_event_ical(uid=uid, summary=summary, start=start, end=end, attendees=attendees)
        cal.save_event(ical)
        return {
            "id": uid,
            "summary": summary,
            "start": _iso(start),
            "end": _iso(end),
            "attendees": list(attendees),
        }

    def find_free(
        self,
        duration_min: int,
        window_start_iso: str,
        window_end_iso: str,
    ) -> list[dict]:
        """Compute free slots by subtracting busy events from window.

        Simple greedy walk; returns all free intervals ≥ duration_min.
        """
        window_start = _parse_iso(window_start_iso)
        window_end = _parse_iso(window_end_iso)
        events = self.list_events(window_start_iso, window_end_iso)
        busy = sorted(
            ((_parse_iso(e["start"]), _parse_iso(e["end"])) for e in events),
            key=lambda p: p[0],
        )
        free: list[dict] = []
        cursor = window_start
        for b_start, b_end in busy:
            if cursor < b_start and (b_start - cursor) >= timedelta(minutes=duration_min):
                free.append(
                    {"start": _iso(cursor), "end": _iso(b_start), "duration_min": duration_min}
                )
            cursor = max(cursor, b_end)
        if cursor < window_end and (window_end - cursor) >= timedelta(minutes=duration_min):
            free.append(
                {"start": _iso(cursor), "end": _iso(window_end), "duration_min": duration_min}
            )
        return free

    def cancel_event(self, event_id: str) -> dict:
        cal = self._get_calendar()
        try:
            evt = cal.event_by_uid(event_id)
        except Exception:
            return {"cancelled": event_id, "found": False}
        evt.delete()
        return {"cancelled": event_id, "found": True}

    # ---------- tasks (Reminders) ----------

    def list_tasks(self) -> list[dict]:
        rem = self._get_reminders()
        return [_map_todo(t) for t in rem.todos()]

    def add_task_remote(self, title: str, due: str | None) -> dict:
        rem = self._get_reminders()
        uid = f"jarvis-{uuid4().hex[:12]}@icloud"
        due_dt = _parse_iso(due) if due else None
        ical = _build_todo_ical(uid=uid, summary=title, due=due_dt)
        rem.save_todo(ical)
        return {"id": uid, "title": title, "due": due, "status": "open"}

    def complete_task_remote(self, task_id: str) -> dict:
        rem = self._get_reminders()
        try:
            todo = rem.todo_by_uid(task_id)
        except Exception:
            return {"id": task_id, "status": "not_found"}
        todo.complete()
        return {"id": task_id, "status": "done"}


# ---------- helpers ----------


def _supported_components(cal: Any) -> Iterable[str]:
    """Read the supported-calendar-component-set property (caldav exposes it)."""
    try:
        comps = cal.get_supported_components()
        return list(comps)
    except Exception:
        return ()


def _map_event(evt: Any) -> dict:
    """caldav.Event → provider dict."""
    vobj = evt.icalendar_component
    summary = str(vobj.get("summary", ""))
    start = vobj.get("dtstart").dt
    end = vobj.get("dtend").dt if vobj.get("dtend") else start
    uid = str(vobj.get("uid", ""))
    attendees: list[str] = []
    raw_attendees = vobj.get("attendee")
    if raw_attendees is not None:
        items = raw_attendees if isinstance(raw_attendees, list) else [raw_attendees]
        for a in items:
            email = str(a).replace("mailto:", "").replace("MAILTO:", "")
            attendees.append(email)
    return {
        "id": uid,
        "summary": summary,
        "start": _iso(_to_dt(start)),
        "end": _iso(_to_dt(end)),
        "attendees": attendees,
    }


def _map_todo(todo: Any) -> dict:
    vobj = todo.icalendar_component
    uid = str(vobj.get("uid", ""))
    summary = str(vobj.get("summary", ""))
    due_raw = vobj.get("due")
    due = _iso(_to_dt(due_raw.dt)) if due_raw else None
    status_raw = str(vobj.get("status", "")).lower()
    status = "done" if status_raw == "completed" else "open"
    return {"id": uid, "title": summary, "due": due, "status": status}


def _to_dt(value: Any) -> datetime:
    """Coerce a date | datetime to aware datetime in UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.combine(value, datetime.min.time(), tzinfo=UTC)


def _build_event_ical(
    *,
    uid: str,
    summary: str,
    start: datetime,
    end: datetime,
    attendees: list[str],
) -> str:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    s = start.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    e = end.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jarvis//icloud-provider//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"DTSTART:{s}",
        f"DTEND:{e}",
        f"SUMMARY:{_escape(summary)}",
    ]
    for a in attendees:
        lines.append(f"ATTENDEE:mailto:{a}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(lines)


def _build_todo_ical(*, uid: str, summary: str, due: datetime | None) -> str:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jarvis//icloud-provider//EN",
        "BEGIN:VTODO",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"SUMMARY:{_escape(summary)}",
        "STATUS:NEEDS-ACTION",
    ]
    if due is not None:
        d = due.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        lines.append(f"DUE:{d}")
    lines.extend(["END:VTODO", "END:VCALENDAR"])
    return "\r\n".join(lines)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
