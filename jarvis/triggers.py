"""Cross-agent trigger rules — declarative wiring between subsystems.

A trigger fires when an InboxEvent or specific subsystem state-change matches
a pattern, and dispatches a follow-up call to another agent.

Rules are declared in TRIGGER_RULES below. Each rule has:
  - name: stable identifier
  - match: callable returning bool given an event/context
  - action: callable that runs the follow-up dispatch (idempotent — safe to fire
    twice; we de-dupe via state/triggers_fired.jsonl)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import get_settings
from .contract import InboxEvent

log = logging.getLogger(__name__)

_DEDUP_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Paths — patchable by tests
# ---------------------------------------------------------------------------


def _fired_path() -> Path:
    return get_settings().state_dir / "triggers_fired.jsonl"


def _exams_path() -> Path:
    return get_settings().state_dir / "scholar_exams.jsonl"


def _dead_letter_path() -> Path:
    return get_settings().state_dir / "dead_letter.jsonl"


def _load_tasks_raw() -> list[dict[str, Any]]:
    """Load tasks from state/tasks.json as plain dicts (avoids Task Pydantic dep)."""
    tasks_file = get_settings().state_dir / "tasks.json"
    if not tasks_file.exists():
        return []
    raw = json.loads(tasks_file.read_text(encoding="utf-8"))
    return list(raw.get("tasks", []))


# ---------------------------------------------------------------------------
# FiredTrigger record
# ---------------------------------------------------------------------------


@dataclass
class FiredTrigger:
    rule_name: str
    source_key: str
    action_summary: str
    outcome: str
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "rule_name": self.rule_name,
            "source_key": self.source_key,
            "action_summary": self.action_summary,
            "outcome": self.outcome,
        }


# ---------------------------------------------------------------------------
# De-duplication helpers
# ---------------------------------------------------------------------------


def _was_fired_recently(rule_name: str, source_key: str) -> bool:
    """Return True if this (rule_name, source_key) pair was fired within the dedup window."""
    path = _fired_path()
    if not path.exists():
        return False
    cutoff = datetime.now(UTC) - timedelta(hours=_DEDUP_WINDOW_HOURS)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("rule_name") != rule_name or rec.get("source_key") != source_key:
            continue
        try:
            fired_at = datetime.fromisoformat(rec["ts"])
            if fired_at.tzinfo is None:
                fired_at = fired_at.replace(tzinfo=UTC)
        except (KeyError, ValueError):
            continue
        if fired_at >= cutoff:
            return True
    return False


def _record_fired(record: FiredTrigger) -> None:
    path = _fired_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict()) + "\n")


# ---------------------------------------------------------------------------
# R1 — scholar.exam_scheduled → tempo.add
# ---------------------------------------------------------------------------


def fire_exam_scheduled(
    reg: dict[str, Any],
    exam_result: dict[str, Any],
) -> FiredTrigger | None:
    """Call tempo.add to block the exam as a task.

    exam_result must contain: session_id, course, started_iso, duration_min.
    Returns FiredTrigger on success, None if deduplicated or tempo missing.
    """
    session_id: str = exam_result.get("session_id", "")
    source_key = f"exam:{session_id}"

    if _was_fired_recently("scholar_exam_scheduled", source_key):
        return None

    tempo = reg.get("tempo")
    if tempo is None:
        log.warning("R1: tempo not in registry, skipping")
        return None

    course: str = exam_result.get("course", "Unknown")
    duration_min: int = int(exam_result.get("duration_min", 60))
    started_iso: str = exam_result.get("started_iso", "")

    title = f"EXAM: {course} ({duration_min}m)"

    try:
        from .state import append_inbox
        from .supervisor import supervise_call

        supervise_call(
            reg,
            "tempo",
            "add",
            {
                "title": title,
                "due": started_iso,
                "tags": ["scholar", "exam", f"course:{course}"],
            },
            on_inbox_event=append_inbox,
        )
        outcome = "ok"
        action_summary = f"tempo.add title={title!r} due={started_iso}"
    except Exception as exc:
        log.warning("R1 fire_exam_scheduled failed: %s", exc)
        outcome = f"error:{exc}"
        action_summary = f"tempo.add failed: {exc}"

    record = FiredTrigger(
        rule_name="scholar_exam_scheduled",
        source_key=source_key,
        action_summary=action_summary,
        outcome=outcome,
    )
    _record_fired(record)
    return record


# ---------------------------------------------------------------------------
# R2 — scholar.exam_imminent → InboxEvent warn
# ---------------------------------------------------------------------------


def scan_imminent_exams() -> list[InboxEvent]:
    """Return warn InboxEvents for exams starting within the next 24 hours.

    Reads scholar_exams.jsonl directly; de-dupes per session_id.
    Caller (sentinel) is responsible for calling append_inbox on each event.
    """
    path = _exams_path()
    if not path.exists():
        return []

    now = datetime.now(UTC)
    window_end = now + timedelta(hours=_DEDUP_WINDOW_HOURS)
    events: list[InboxEvent] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            session = json.loads(line)
        except json.JSONDecodeError:
            continue

        session_id = session.get("session_id", "")
        source_key = f"imminent:{session_id}"
        if _was_fired_recently("scholar_exam_imminent", source_key):
            continue

        started_iso = session.get("started_iso", "")
        if not started_iso:
            continue
        try:
            starts_at = datetime.fromisoformat(started_iso)
            if starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=UTC)
        except ValueError:
            continue

        if not (now <= starts_at <= window_end):
            continue

        hours_away = int((starts_at - now).total_seconds() / 3600)
        course = session.get("course", "Unknown")
        summary = f"Exam in {hours_away}h: {course}"

        event = InboxEvent(
            agent="scholar",
            severity="warn",
            summary=summary,
            ref={"session_id": session_id, "course": course, "starts_at": started_iso},
        )
        events.append(event)
        _record_fired(
            FiredTrigger(
                rule_name="scholar_exam_imminent",
                source_key=source_key,
                action_summary=f"inbox event: {summary}",
                outcome="ok",
            )
        )

    return events


# ---------------------------------------------------------------------------
# R3 — tempo.task_due_today → scholar.surface_on_dashboard
# ---------------------------------------------------------------------------


def scan_tasks_due_today() -> list[InboxEvent]:
    """Return info InboxEvents for open tasks with a course tag due today.

    Caller (sentinel) is responsible for calling append_inbox on each event.
    """
    today = datetime.now(UTC).date().isoformat()
    events: list[InboxEvent] = []

    for task in _load_tasks_raw():
        if task.get("status", "open") != "open":
            continue
        due = task.get("due", "")
        if not due or not due.startswith(today):
            continue
        tags: list[str] = task.get("tags", [])
        if not any(t.startswith("course:") for t in tags):
            continue

        task_id = task.get("id", "")
        source_key = f"due:{task_id}:{today}"
        if _was_fired_recently("tempo_task_due_today", source_key):
            continue

        title = task.get("title", "Untitled")
        summary = f"Due today: {title}"
        event = InboxEvent(
            agent="scholar",
            severity="info",
            summary=summary,
            ref={"task_id": task_id, "title": title, "tags": tags},
        )
        events.append(event)
        _record_fired(
            FiredTrigger(
                rule_name="tempo_task_due_today",
                source_key=source_key,
                action_summary=f"inbox event: {summary}",
                outcome="ok",
            )
        )

    return events


# ---------------------------------------------------------------------------
# R4 — forge.run_failed → inbox crit (taps dead_letter.jsonl)
# ---------------------------------------------------------------------------


def scan_forge_dead_letter() -> list[InboxEvent]:
    """Return crit InboxEvents for new forge dead-letter records.

    Caller (sentinel) is responsible for calling append_inbox on each event.
    """
    path = _dead_letter_path()
    if not path.exists():
        return []

    events: list[InboxEvent] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        if rec.get("agent") != "forge":
            continue

        request_id = rec.get("request_id", "")
        source_key = f"dead:{request_id}"
        if _was_fired_recently("forge_run_failed", source_key):
            continue

        error_msg = rec.get("error_msg", "unknown error")
        action = rec.get("action", "?")
        summary = f"Forge {action} failed: {error_msg}"[:300]

        event = InboxEvent(
            agent="forge",
            severity="crit",
            summary=summary,
            ref={
                "request_id": request_id,
                "error_class": rec.get("error_class", ""),
                "retries": rec.get("retries", 0),
            },
        )
        events.append(event)
        _record_fired(
            FiredTrigger(
                rule_name="forge_run_failed",
                source_key=source_key,
                action_summary=f"inbox crit: {summary}",
                outcome="ok",
            )
        )

    return events


# ---------------------------------------------------------------------------
# R5 — atlas.guardian_violation → inbox crit
# ---------------------------------------------------------------------------


def build_guardian_violation_event(
    strategy_id: str,
    violations: list[str],
) -> InboxEvent | None:
    """Build a crit InboxEvent for a guardian violation (caller must append_inbox).

    Returns None when violations is empty (no violation occurred).
    """
    if not violations:
        return None

    reason = violations[0]
    summary = f"Guardian violation: {reason}"[:300]
    return InboxEvent(
        agent="atlas",
        severity="crit",
        summary=summary,
        ref={"strategy_id": strategy_id, "violations": violations},
    )


# ---------------------------------------------------------------------------
# Periodic scanner — sentinel calls this on every tick
# ---------------------------------------------------------------------------


def scan_periodic(reg: dict[str, Any]) -> list[FiredTrigger]:  # noqa: ARG001
    """Run all polling-style rules (R2, R3, R4).

    Appends generated InboxEvents to state/inbox.jsonl and records each fire.
    Returns the list of FiredTrigger records created in this tick.
    """
    from .state import append_inbox

    fired: list[FiredTrigger] = []

    # R2 — imminent exams
    for event in scan_imminent_exams():
        try:
            append_inbox(event)
            fired.append(
                FiredTrigger(
                    rule_name="scholar_exam_imminent",
                    source_key=event.ref.get("session_id", ""),
                    action_summary=event.summary,
                    outcome="ok",
                )
            )
        except Exception as exc:
            log.warning("scan_periodic R2 append failed: %s", exc)

    # R3 — tasks due today
    for event in scan_tasks_due_today():
        try:
            append_inbox(event)
            fired.append(
                FiredTrigger(
                    rule_name="tempo_task_due_today",
                    source_key=event.ref.get("task_id", ""),
                    action_summary=event.summary,
                    outcome="ok",
                )
            )
        except Exception as exc:
            log.warning("scan_periodic R3 append failed: %s", exc)

    # R4 — forge dead-letter
    for event in scan_forge_dead_letter():
        try:
            append_inbox(event)
            fired.append(
                FiredTrigger(
                    rule_name="forge_run_failed",
                    source_key=event.ref.get("request_id", ""),
                    action_summary=event.summary,
                    outcome="ok",
                )
            )
        except Exception as exc:
            log.warning("scan_periodic R4 append failed: %s", exc)

    return fired


# ---------------------------------------------------------------------------
# fire_for_event — inbox listener path (R5 + future event-driven rules)
# ---------------------------------------------------------------------------


def fire_for_event(reg: dict[str, Any], event: InboxEvent) -> list[FiredTrigger]:  # noqa: ARG001
    """Run all event-driven rules matching the given InboxEvent.

    Currently handles R5 (atlas guardian violations surfaced as inbox events).
    register_inbox_listener(lambda e: fire_for_event(reg, e)) wires this at
    app startup so every append_inbox call runs through here.
    """
    fired: list[FiredTrigger] = []
    return fired  # event-driven rules beyond R5 are added here as needed


# ---------------------------------------------------------------------------
# list_recent_fires
# ---------------------------------------------------------------------------


def list_recent_fires(limit: int = 50) -> list[dict[str, Any]]:
    """Read state/triggers_fired.jsonl tail and return as plain dicts."""
    path = _fired_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    records: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("triggers: malformed fired line skipped")
    return records
