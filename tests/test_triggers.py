"""Tests for jarvis/triggers.py — cross-agent trigger rules.

Coverage:
- R1: scholar.exam_scheduled → tempo.add called with correct args
- R2: scan_imminent_exams returns InboxEvent when exam is within 24h
- R3: scan_tasks_due_today returns InboxEvent for task with course tag due today
- R4: forge_run_failed returns InboxEvent crit (taps dead_letter.jsonl)
- R5: atlas_guardian_violation returns InboxEvent crit
- Deduplication: second fire with same key is skipped
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from jarvis.contract import AgentResponse, InboxEvent

# ---------------------------------------------------------------------------
# Helpers — fake registry
# ---------------------------------------------------------------------------

def _make_registry(
    tempo_add_fn=None,
) -> dict[str, Any]:
    """Return a minimal stub registry with a mock tempo descriptor."""
    tempo = MagicMock()
    tempo.name = "tempo"
    if tempo_add_fn is not None:
        tempo.call.side_effect = tempo_add_fn
    else:
        tempo.call.return_value = AgentResponse(
            agent="tempo",
            intent="add_task",
            action="created",
            result={"task": {}},
        )
    return {"tempo": tempo}


# ---------------------------------------------------------------------------
# R1 — scholar.exam_scheduled → tempo.block_calendar
# ---------------------------------------------------------------------------

class TestR1ExamScheduled:
    def test_fires_tempo_add_with_correct_args(self, tmp_path, monkeypatch):
        """Synthesise an exam_session result and assert tempo.add is called."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        reg = _make_registry()
        course = "Linear Algebra"
        started_iso = (datetime.now(UTC) + timedelta(hours=48)).isoformat()
        duration_min = 90

        exam_result: dict[str, Any] = {
            "session_id": "abc123",
            "course": course,
            "started_iso": started_iso,
            "ends_iso": (
                datetime.fromisoformat(started_iso) + timedelta(minutes=duration_min)
            ).isoformat(),
            "duration_min": duration_min,
            "problems": [],
        }

        fired = triggers.fire_exam_scheduled(reg, exam_result)

        assert fired is not None
        assert fired.rule_name == "scholar_exam_scheduled"
        reg["tempo"].call.assert_called_once()
        call_args = reg["tempo"].call.call_args
        assert call_args[0][0] == "add"  # action name
        args_dict = call_args[0][1]
        assert course in args_dict["title"]
        assert "exam" in [t.lower() for t in args_dict.get("tags", [])]

    def test_deduplication_skips_second_fire(self, tmp_path, monkeypatch):
        """Firing the same (rule, source_key) twice within 24h skips the second."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        reg = _make_registry()
        started_iso = (datetime.now(UTC) + timedelta(hours=48)).isoformat()
        exam_result: dict[str, Any] = {
            "session_id": "dup_session",
            "course": "Physics",
            "started_iso": started_iso,
            "ends_iso": started_iso,
            "duration_min": 60,
            "problems": [],
        }

        first = triggers.fire_exam_scheduled(reg, exam_result)
        second = triggers.fire_exam_scheduled(reg, exam_result)

        assert first is not None
        assert second is None  # deduplicated
        assert reg["tempo"].call.call_count == 1


# ---------------------------------------------------------------------------
# R2 — scan_imminent_exams
# ---------------------------------------------------------------------------

class TestR2ImminentExam:
    def _write_exam(self, path: Path, session: dict[str, Any]) -> None:
        with path.open("a") as fh:
            fh.write(json.dumps(session) + "\n")

    def test_returns_event_when_exam_within_24h(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        exams_file = tmp_path / "scholar_exams.jsonl"
        started_iso = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
        session = {
            "session_id": "s1",
            "course": "Calculus",
            "started_iso": started_iso,
            "ends_iso": (datetime.fromisoformat(started_iso) + timedelta(minutes=60)).isoformat(),
            "duration_min": 60,
            "problems": [],
        }
        self._write_exam(exams_file, session)

        monkeypatch.setattr(triggers, "_exams_path", lambda: exams_file)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_imminent_exams()

        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, InboxEvent)
        assert ev.agent == "scholar"
        assert ev.severity == "warn"
        assert "Calculus" in ev.summary

    def test_no_event_when_exam_over_24h_away(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        exams_file = tmp_path / "scholar_exams.jsonl"
        started_iso = (datetime.now(UTC) + timedelta(hours=30)).isoformat()
        session = {
            "session_id": "s2",
            "course": "Thermodynamics",
            "started_iso": started_iso,
            "ends_iso": started_iso,
            "duration_min": 60,
            "problems": [],
        }
        self._write_exam(exams_file, session)

        monkeypatch.setattr(triggers, "_exams_path", lambda: exams_file)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_imminent_exams()

        assert events == []

    def test_dedup_skips_already_fired_exam(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        exams_file = tmp_path / "scholar_exams.jsonl"
        fired_file = tmp_path / "triggers_fired.jsonl"
        started_iso = (datetime.now(UTC) + timedelta(hours=6)).isoformat()
        session = {
            "session_id": "s3",
            "course": "Chemistry",
            "started_iso": started_iso,
            "ends_iso": started_iso,
            "duration_min": 60,
            "problems": [],
        }
        self._write_exam(exams_file, session)

        monkeypatch.setattr(triggers, "_exams_path", lambda: exams_file)
        monkeypatch.setattr(triggers, "_fired_path", lambda: fired_file)

        first = triggers.scan_imminent_exams()
        second = triggers.scan_imminent_exams()

        assert len(first) == 1
        assert second == []


# ---------------------------------------------------------------------------
# R3 — scan_tasks_due_today
# ---------------------------------------------------------------------------

class TestR3TasksDueToday:
    def test_returns_event_for_task_with_course_tag_due_today(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        today = datetime.now(UTC).date().isoformat()
        tasks = [
            {
                "id": "t1",
                "title": "Submit HW3",
                "due": today,
                "tags": ["school", "course:Linear Algebra"],
                "status": "open",
                "created": today,
                "updated": today,
            }
        ]

        monkeypatch.setattr(triggers, "_load_tasks_raw", lambda: tasks)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_tasks_due_today()

        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, InboxEvent)
        assert ev.agent == "scholar"
        assert ev.severity == "info"
        assert "Submit HW3" in ev.summary

    def test_ignores_task_without_course_tag(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        today = datetime.now(UTC).date().isoformat()
        tasks = [
            {
                "id": "t2",
                "title": "Buy groceries",
                "due": today,
                "tags": ["personal"],
                "status": "open",
                "created": today,
                "updated": today,
            }
        ]

        monkeypatch.setattr(triggers, "_load_tasks_raw", lambda: tasks)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_tasks_due_today()

        assert events == []

    def test_ignores_task_not_due_today(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
        tasks = [
            {
                "id": "t3",
                "title": "Essay",
                "due": tomorrow,
                "tags": ["course:English"],
                "status": "open",
                "created": tomorrow,
                "updated": tomorrow,
            }
        ]

        monkeypatch.setattr(triggers, "_load_tasks_raw", lambda: tasks)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_tasks_due_today()

        assert events == []


# ---------------------------------------------------------------------------
# R4 — forge_run_failed → inbox crit
# ---------------------------------------------------------------------------

class TestR4ForgeRunFailed:
    def test_returns_crit_event_when_dead_letter_present(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        dead_letter_file = tmp_path / "dead_letter.jsonl"
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "request_id": "req1",
            "agent": "forge",
            "action": "execute",
            "args_summary": "{}",
            "error_class": "RuntimeError",
            "error_msg": "build exploded",
            "retries": 2,
            "traceback": "...",
        }
        with dead_letter_file.open("w") as fh:
            fh.write(json.dumps(record) + "\n")

        monkeypatch.setattr(triggers, "_dead_letter_path", lambda: dead_letter_file)
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_forge_dead_letter()

        assert len(events) == 1
        ev = events[0]
        assert ev.severity == "crit"
        assert ev.agent == "forge"
        assert "build exploded" in ev.summary

    def test_returns_empty_when_no_dead_letter(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_dead_letter_path", lambda: tmp_path / "dead_letter.jsonl")
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        events = triggers.scan_forge_dead_letter()

        assert events == []


# ---------------------------------------------------------------------------
# R5 — atlas.guardian_violation → inbox crit
# ---------------------------------------------------------------------------

class TestR5GuardianViolation:
    def test_builds_crit_event_for_violation(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        violations = ["live mode requires explicit operator confirmation"]
        strategy_id = "strat_abc"

        event = triggers.build_guardian_violation_event(strategy_id, violations)

        assert event is not None
        assert isinstance(event, InboxEvent)
        assert event.severity == "crit"
        assert event.agent == "atlas"
        assert "live mode" in event.summary

    def test_returns_none_when_no_violations(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        event = triggers.build_guardian_violation_event("strat_xyz", [])

        assert event is None


# ---------------------------------------------------------------------------
# scan_periodic wiring
# ---------------------------------------------------------------------------

class TestScanPeriodic:
    def test_returns_list_of_fired_triggers(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        today = datetime.now(UTC).date().isoformat()
        tasks = [
            {
                "id": "t10",
                "title": "Lab Report",
                "due": today,
                "tags": ["course:Biology"],
                "status": "open",
                "created": today,
                "updated": today,
            }
        ]
        exams_file = tmp_path / "scholar_exams.jsonl"

        monkeypatch.setattr(triggers, "_load_tasks_raw", lambda: tasks)
        monkeypatch.setattr(triggers, "_exams_path", lambda: exams_file)
        monkeypatch.setattr(triggers, "_dead_letter_path", lambda: tmp_path / "dead_letter.jsonl")
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        reg = _make_registry()
        fired = triggers.scan_periodic(reg)

        assert isinstance(fired, list)
        # At minimum: one task due today event
        assert any(f.rule_name == "tempo_task_due_today" for f in fired)


# ---------------------------------------------------------------------------
# list_recent_fires
# ---------------------------------------------------------------------------

class TestListRecentFires:
    def test_reads_fired_jsonl(self, tmp_path, monkeypatch):
        from jarvis.core import triggers

        fired_file = tmp_path / "triggers_fired.jsonl"
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "rule_name": "scholar_exam_scheduled",
            "source_key": "abc123",
            "action_summary": "called tempo.add",
            "outcome": "ok",
        }
        with fired_file.open("w") as fh:
            fh.write(json.dumps(record) + "\n")

        monkeypatch.setattr(triggers, "_fired_path", lambda: fired_file)

        results = triggers.list_recent_fires(limit=10)

        assert len(results) == 1
        assert results[0]["rule_name"] == "scholar_exam_scheduled"


# ---------------------------------------------------------------------------
# Fix 2 — fire_for_event handler body
# ---------------------------------------------------------------------------

class TestFireForEventAtlasCrit:
    def test_atlas_crit_pushes_priority_2(self, tmp_path, monkeypatch):
        """An atlas+crit InboxEvent fires a priority-2 notifier push."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        notifier = MagicMock()
        event = InboxEvent(
            agent="atlas",
            severity="crit",
            summary="Guardian violation: position size exceeds cap",
            ref={"strategy_id": "strat_001", "violations": ["position size exceeds cap"]},
        )

        fired = triggers.fire_for_event({}, event, notifier=notifier)

        assert len(fired) == 1
        assert fired[0].rule_name == "atlas_crit_push"
        notifier.push.assert_called_once()
        args, kwargs = notifier.push.call_args
        assert kwargs.get("priority", args[2] if len(args) >= 3 else None) == 2

    def test_atlas_info_event_is_skipped(self, tmp_path, monkeypatch):
        """Non-crit atlas events do not push."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        notifier = MagicMock()
        event = InboxEvent(
            agent="atlas",
            severity="info",
            summary="ATLAS pnl=+0.42% pos=3 actions=0",
            ref={"pnl_pct": 0.0042, "open_positions": 3},
        )

        fired = triggers.fire_for_event({}, event, notifier=notifier)

        assert fired == []
        notifier.push.assert_not_called()

    def test_atlas_crit_dedup_skips_second_fire(self, tmp_path, monkeypatch):
        """Same (rule, source_key) within dedup window is skipped."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        notifier = MagicMock()
        event = InboxEvent(
            agent="atlas",
            severity="crit",
            summary="Guardian violation: stop loss missing",
            ref={"strategy_id": "strat_dup", "violations": ["stop loss missing"]},
        )

        first = triggers.fire_for_event({}, event, notifier=notifier)
        second = triggers.fire_for_event({}, event, notifier=notifier)

        assert len(first) == 1
        assert second == []
        assert notifier.push.call_count == 1


class TestFireForEventForgeCrit:
    def test_forge_crit_pushes_priority_2(self, tmp_path, monkeypatch):
        """A forge+crit InboxEvent (dead-letter) fires a priority-2 push."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        notifier = MagicMock()
        event = InboxEvent(
            agent="forge",
            severity="crit",
            summary="Forge execute failed: timeout after 3 retries",
            ref={"request_id": "req_xyz", "error_class": "TimeoutError", "retries": 3},
        )

        fired = triggers.fire_for_event({}, event, notifier=notifier)

        assert len(fired) == 1
        assert fired[0].rule_name == "forge_crit_push"
        notifier.push.assert_called_once()
        args, kwargs = notifier.push.call_args
        assert kwargs.get("priority", args[2] if len(args) >= 3 else None) == 2


class TestFireForEventScholarImminent:
    def test_scholar_warn_imminent_dispatches_tempo_add(self, tmp_path, monkeypatch):
        """scholar+warn with session_id ref → dispatch tempo.add to block the slot."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        reg = _make_registry()
        notifier = MagicMock()

        starts_at = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        event = InboxEvent(
            agent="scholar",
            severity="warn",
            summary="Exam in 3h: Linear Algebra",
            ref={"session_id": "sess_77", "course": "Linear Algebra", "starts_at": starts_at},
        )

        fired = triggers.fire_for_event(reg, event, notifier=notifier)

        assert len(fired) == 1
        assert fired[0].rule_name == "scholar_exam_imminent_block"
        # tempo.call was invoked with action "add"
        reg["tempo"].call.assert_called_once()
        call_args = reg["tempo"].call.call_args
        assert call_args[0][0] == "add"
        payload = call_args[0][1]
        assert "Linear Algebra" in payload["title"]
        assert payload["due"] == starts_at
        assert "scholar" in payload["tags"]
        assert "exam" in payload["tags"]

    def test_scholar_warn_without_session_id_is_skipped(self, tmp_path, monkeypatch):
        """scholar+warn without a session_id ref doesn't trigger the imminent-exam handler."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        reg = _make_registry()
        event = InboxEvent(
            agent="scholar",
            severity="warn",
            summary="Generic scholar warning",
            ref={"unrelated": "data"},
        )

        fired = triggers.fire_for_event(reg, event, notifier=MagicMock())

        assert fired == []
        reg["tempo"].call.assert_not_called()

    def test_scholar_imminent_missing_tempo_is_graceful(self, tmp_path, monkeypatch):
        """If tempo is not in the registry, the handler logs + skips without raising."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        event = InboxEvent(
            agent="scholar",
            severity="warn",
            summary="Exam in 2h: Statistics",
            ref={"session_id": "sess_88", "course": "Statistics", "starts_at": ""},
        )

        # No tempo in reg — handler should swallow and return empty
        fired = triggers.fire_for_event({}, event, notifier=MagicMock())

        assert fired == []


class TestFireForEventUnhandled:
    def test_lens_event_returns_empty(self, tmp_path, monkeypatch):
        """Events that don't match any rule pattern return [] cleanly."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")

        event = InboxEvent(
            agent="lens",
            severity="info",
            summary="3 new world brief items",
            ref={},
        )

        fired = triggers.fire_for_event({}, event, notifier=MagicMock())

        assert fired == []


# ---------------------------------------------------------------------------
# Fix 4 — scan_periodic pushes warn/crit through the injected notifier
# ---------------------------------------------------------------------------

class TestScanPeriodicNotifies:
    def test_crit_dead_letter_pushes_priority_2(self, tmp_path, monkeypatch):
        """R4 forge dead-letter → notifier push at priority=2."""
        from jarvis.core import triggers

        # Stub _fired_path + _dead_letter_path so we use isolated fixtures
        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")
        monkeypatch.setattr(triggers, "_dead_letter_path", lambda: tmp_path / "dead_letter.jsonl")
        monkeypatch.setattr(triggers, "_exams_path", lambda: tmp_path / "no_exams.jsonl")
        # Empty tasks file
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        dl_path = tmp_path / "dead_letter.jsonl"
        dl_path.write_text(
            json.dumps({
                "agent": "forge",
                "request_id": "req_dead_42",
                "action": "execute",
                "error_msg": "Claude SDK timeout",
                "error_class": "TimeoutError",
                "retries": 3,
                "ts": datetime.now(UTC).isoformat(),
            }) + "\n",
            encoding="utf-8",
        )

        # Patch append_inbox so we don't try to write to state.
        appended: list[InboxEvent] = []
        monkeypatch.setattr(
            "jarvis.state.append_inbox",
            lambda ev: appended.append(ev) or ev,
        )

        notifier = MagicMock()

        fired = triggers.scan_periodic({}, notifier=notifier)

        # At least one fire for R4 (crit)
        assert any(f.rule_name == "forge_run_failed" for f in fired)
        # Notifier was pushed at priority=2 for the crit event
        notifier.push.assert_called()
        # Inspect the call args for priority
        crit_calls = [
            c for c in notifier.push.call_args_list
            if (c.kwargs.get("priority") == 2 or (len(c.args) >= 3 and c.args[2] == 2))
        ]
        assert crit_calls, "expected at least one crit-priority push"

    def test_scan_periodic_without_notifier_is_quiet(self, tmp_path, monkeypatch):
        """If no notifier is passed, scan_periodic still works (back-compat)."""
        from jarvis.core import triggers

        monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")
        monkeypatch.setattr(triggers, "_dead_letter_path", lambda: tmp_path / "no_dl.jsonl")
        monkeypatch.setattr(triggers, "_exams_path", lambda: tmp_path / "no_exams.jsonl")
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        monkeypatch.setattr(
            "jarvis.state.append_inbox",
            lambda ev: ev,
        )

        # Old-style call without notifier kwarg must still work.
        fired = triggers.scan_periodic({})
        assert fired == []  # nothing in the fixture files
