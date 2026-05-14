"""Tests for jarvis/exports.py — daily and weekly digest generation."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from jarvis.contract import AgentLogEntry, Confirmation, InboxEvent, Task
from jarvis.state import (
    add_confirmation,
    add_task,
    append_agent_log,
    append_inbox,
    update_confirmation,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _seed_agent_log(state_dir: Path, date_iso: str, count: int = 3) -> None:
    """Write agent_log entries timestamped on ``date_iso``."""
    for i in range(count):
        ts = f"{date_iso}T10:0{i}:00+00:00"
        entry = AgentLogEntry(
            ts=ts,
            request_id=f"req{i:04d}",
            agent="tempo" if i % 2 == 0 else "scholar",
            action="triage" if i % 2 == 0 else "plan",
            status="ok" if i < 2 else "error",
            duration_ms=100 + i * 10,
        )
        append_agent_log(entry)


def _seed_inbox(state_dir: Path, date_iso: str, count: int = 2) -> None:
    for i in range(count):
        ts = f"{date_iso}T09:0{i}:00+00:00"
        append_inbox(
            InboxEvent(
                ts=ts,
                agent="tempo" if i == 0 else "sentinel",
                severity="info",
                summary=f"inbox event {i}",
            )
        )


def _seed_confirmations(state_dir: Path, date_iso: str) -> None:
    c = add_confirmation(
        Confirmation(
            ts=f"{date_iso}T08:00:00+00:00",
            agent="atlas",
            intent="trigger_strategy",
            request="run strategy alpha-1",
            summary="confirm to run strategy alpha-1",
        )
    )
    update_confirmation(c.id, status="approved")
    add_confirmation(
        Confirmation(
            ts=f"{date_iso}T08:30:00+00:00",
            agent="forge",
            intent="open_pr",
            request="ship dashboard",
            summary="open PR for dashboard redesign",
        )
    )


def _seed_tasks(state_dir: Path, date_iso: str) -> None:
    add_task(
        Task(
            title="Ship dashboard redesign",
            tags=["forge"],
            status="done",
            created=f"{date_iso}T07:00:00+00:00",
            updated=f"{date_iso}T11:00:00+00:00",
        )
    )
    add_task(
        Task(
            title="Linalg practice — eigenvalues",
            tags=["scholar"],
            status="open",
            created=f"{date_iso}T07:00:00+00:00",
            updated=f"{date_iso}T07:00:00+00:00",
        )
    )


def _seed_scholar(state_dir: Path, date_iso: str) -> None:
    problems_path = state_dir / "scholar_problems.jsonl"
    problems_path.write_text(
        json.dumps(
            {
                "id": "abc123",
                "ts": f"{date_iso}T10:00:00+00:00",
                "course": "Linear Algebra",
                "problem": "Find eigenvalues of [[2,1],[1,2]]",
                "response": {
                    "steps": ["step1"],
                    "final_answer": "3 and 1",
                    "concepts_used": ["eigenvalue"],
                    "weak_topic_candidates": ["rank-nullity"],
                },
                "rated_correct": True,
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "def456",
                "ts": f"{date_iso}T11:00:00+00:00",
                "course": "Linear Algebra",
                "problem": "Is [[1,1],[1,1]] invertible?",
                "response": {
                    "steps": ["step1"],
                    "final_answer": "No",
                    "concepts_used": ["determinant"],
                    "weak_topic_candidates": [],
                },
                "rated_correct": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    exams_path = state_dir / "scholar_exams.jsonl"
    exams_path.write_text(
        json.dumps(
            {
                "session_id": "sess1",
                "started_iso": f"{date_iso}T09:00:00+00:00",
                "ends_iso": f"{date_iso}T09:30:00+00:00",
                "course": "Linear Algebra",
                "duration_min": 30,
                "problems": [{"id": "p1", "prompt": "q1", "expected_concepts": []}],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _seed_turn_log(state_dir: Path) -> None:
    turn_log_path = state_dir / "jarvis_turn_log.json"
    turns = [
        {"role": "user", "text": "What's on my plate today?"},
        {"role": "assistant", "text": "You have 2 open tasks and 1 exam tomorrow."},
        {"role": "user", "text": "What are the eigenvalues of the identity matrix?"},
        {"role": "assistant", "text": "All eigenvalues are 1 for the identity matrix."},
        {"role": "user", "text": "Remind me about the Linear Algebra test."},
        {
            "role": "assistant",
            "text": "Linear Algebra test opens in 30 minutes at 3:30 PM.",
        },
    ]
    turn_log_path.write_text(json.dumps(turns), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDailyDigest:
    def test_empty_state_returns_valid_markdown(self, isolated_state):
        """Digest with no data must still return a valid markdown string with a date header."""
        import re

        from jarvis.state.exports import daily_digest

        today = datetime.date(2026, 4, 29)
        result = daily_digest(today)

        assert isinstance(result, str)
        assert result.startswith("# Daily Digest")
        assert "2026-04-29" in result
        assert re.search(r"^##\s+", result, re.MULTILINE), "must have at least one ## section"

    def test_mixed_data_all_sections_render(self, isolated_state):
        """With seeded data every main section should appear."""
        from jarvis.state.exports import daily_digest

        date_iso = "2026-04-29"
        target = datetime.date(2026, 4, 29)

        _seed_agent_log(isolated_state, date_iso)
        _seed_inbox(isolated_state, date_iso)
        _seed_confirmations(isolated_state, date_iso)
        _seed_tasks(isolated_state, date_iso)
        _seed_scholar(isolated_state, date_iso)
        _seed_turn_log(isolated_state)

        result = daily_digest(target)

        assert "## Activity" in result
        assert "## Tasks" in result
        assert "## Scholar" in result
        assert "## Conversations with Jarvis" in result
        assert "## Notable Inbox Events" in result

    def test_dispatches_count_and_status(self, isolated_state):
        """Activity section must report correct ok/error counts."""
        from jarvis.state.exports import daily_digest

        date_iso = "2026-04-29"
        target = datetime.date(2026, 4, 29)
        _seed_agent_log(isolated_state, date_iso, count=3)

        result = daily_digest(target)

        assert "3 agent dispatches" in result
        assert "2 ok" in result
        assert "1 errored" in result

    def test_confirmations_count(self, isolated_state):
        """Activity section must count approved + pending confirmations."""
        from jarvis.state.exports import daily_digest

        date_iso = "2026-04-29"
        target = datetime.date(2026, 4, 29)
        _seed_confirmations(isolated_state, date_iso)

        result = daily_digest(target)

        assert "1 approved" in result
        assert "1 pending" in result

    def test_scholar_section_course_and_problems(self, isolated_state):
        """Scholar section includes course name and problem stats."""
        from jarvis.state.exports import daily_digest

        date_iso = "2026-04-29"
        target = datetime.date(2026, 4, 29)
        _seed_scholar(isolated_state, date_iso)

        result = daily_digest(target)

        assert "Linear Algebra" in result
        assert "2 problems" in result

    def test_task_completed_and_open(self, isolated_state):
        """Tasks section lists both completed and open tasks."""
        from jarvis.state.exports import daily_digest

        date_iso = "2026-04-29"
        target = datetime.date(2026, 4, 29)
        _seed_tasks(isolated_state, date_iso)

        result = daily_digest(target)

        assert "Ship dashboard redesign" in result
        assert "Linalg practice" in result
        assert "**Completed:**" in result or "Completed" in result
        assert "**Open:**" in result or "Open" in result

    def test_conversation_excerpts_render(self, isolated_state):
        """Conversations section shows excerpts from turn log."""
        from jarvis.state.exports import daily_digest

        _seed_turn_log(isolated_state)
        result = daily_digest(datetime.date(2026, 4, 29))

        assert "Conversations with Jarvis" in result
        assert "> User:" in result or "> **User**:" in result

    def test_skips_scholar_section_when_no_data(self, isolated_state):
        """Scholar section is omitted when no problems or exams exist."""
        from jarvis.state.exports import daily_digest

        result = daily_digest(datetime.date(2026, 4, 29))

        # Scholar section should be absent with empty state
        assert "## Scholar" not in result

    def test_default_date_is_today(self, isolated_state):
        """Calling daily_digest() with no args uses today's UTC date."""
        from jarvis.state.exports import daily_digest

        today = datetime.datetime.now(datetime.UTC).date()
        result = daily_digest()

        assert today.isoformat() in result


class TestWeeklyDigest:
    def test_spans_seven_day_window(self, isolated_state):
        """Weekly digest header must include start and end dates 6 days apart."""
        from jarvis.state.exports import weekly_digest

        end = datetime.date(2026, 4, 29)
        start = end - datetime.timedelta(days=6)
        result = weekly_digest(end)

        assert start.isoformat() in result
        assert end.isoformat() in result

    def test_date_range_filter(self, isolated_state):
        """Entries outside the 7-day window must NOT appear in the digest."""
        from jarvis.state.exports import weekly_digest

        # Seed entries outside the window (8 days before end)
        outside_date = "2026-04-21"  # 8 days before 2026-04-29
        _seed_agent_log(isolated_state, outside_date, count=5)

        end = datetime.date(2026, 4, 29)
        result = weekly_digest(end)

        # 5 outside + 0 inside = 0 total dispatches
        assert "0 agent dispatches" in result

    def test_date_range_includes_boundary(self, isolated_state):
        """Entries ON the end_date are included."""
        from jarvis.state.exports import weekly_digest

        end = datetime.date(2026, 4, 29)
        _seed_agent_log(isolated_state, "2026-04-29", count=2)

        result = weekly_digest(end)
        assert "2 agent dispatches" in result

    def test_weekly_digest_well_formed_markdown(self, isolated_state):
        """Weekly digest must start with # and have at least one ## section."""
        import re

        from jarvis.state.exports import weekly_digest

        result = weekly_digest(datetime.date(2026, 4, 29))

        assert result.startswith("# ")
        assert re.search(r"^##\s+", result, re.MULTILINE)

    def test_default_end_date_is_today(self, isolated_state):
        """weekly_digest() with no args ends today."""
        from jarvis.state.exports import weekly_digest

        today = datetime.datetime.now(datetime.UTC).date()
        result = weekly_digest()

        assert today.isoformat() in result
