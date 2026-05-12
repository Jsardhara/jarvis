"""Tests for jarvis.state.briefing — morning briefing aggregator."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.state.briefing import (
    _build_system_section,
    _next_exam_within_days,
    _top_weak_topics,
    build_briefing,
)
from jarvis.contract import AgentLogEntry, AgentResponse, Task
from jarvis.state import add_task, append_agent_log

# ── Mock descriptors ──────────────────────────────────────────────────────────


class MockDesc:
    """Minimal AgentDescriptor stand-in with configurable call() responses."""

    def __init__(self, responses: dict[str, AgentResponse]) -> None:
        self._responses = responses

    def call(self, action: str, _args: dict | None = None) -> AgentResponse:
        if action not in self._responses:
            raise ValueError(f"unknown action {action!r}")
        return self._responses[action]


def _tempo_desc(
    action_count: int = 4,
    info_count: int = 12,
    noise_count: int = 8,
    top: list[dict] | None = None,
) -> MockDesc:
    top = top or [
        {"subject": "Sarah re Q3 plan", "from_addr": "sarah@example.com"},
        {"subject": "Stripe invoice", "from_addr": "billing@stripe.com"},
        {"subject": "Apartment lease renewal", "from_addr": "landlord@example.com"},
    ]
    return MockDesc(
        {
            "triage_status": AgentResponse(
                agent="tempo",
                intent="triage_status",
                action="summarised",
                result={
                    "counts": {
                        "action_required": action_count,
                        "info_only": info_count,
                        "noise": noise_count,
                    },
                    "total_classified": action_count + info_count + noise_count,
                    "snoozed_count": 0,
                    "top_action_required": top,
                },
            )
        }
    )


def _atlas_desc(pnl_usd: float = 12.34, mock: bool = True) -> MockDesc:
    return MockDesc(
        {
            "pnl": AgentResponse(
                agent="atlas",
                intent="pnl",
                action="ok",
                result={"pnl": {"pnl_usd": pnl_usd, "pnl_pct": pnl_usd / 10_000}, "mock": mock},
            ),
            "portfolio": AgentResponse(
                agent="atlas",
                intent="portfolio",
                action="ok",
                result={"positions": [{"sym": "BTC"}, {"sym": "ETH"}, {"sym": "SOL"}, {"sym": "AAPL"}], "mock": mock},
            ),
        }
    )


def _full_reg() -> dict:
    return {"tempo": _tempo_desc(), "atlas": _atlas_desc()}


# ── Test: empty state still returns valid briefing ────────────────────────────


def test_empty_state_returns_valid_briefing(isolated_state: Path) -> None:
    """Empty state dir — no crash, valid shape with zero counts."""
    brief = build_briefing({})

    assert "markdown" in brief
    assert "sections" in brief
    assert "metadata" in brief
    assert "system" in brief["sections"]

    system = brief["sections"]["system"]
    assert system["dead_letters_24h"] == 0
    assert system["dispatches_24h"] == 0
    # tempo / scholar / atlas absent when no registry entries
    assert "tempo" not in brief["sections"]
    assert "scholar" not in brief["sections"]
    assert "atlas" not in brief["sections"]


def test_empty_state_markdown_has_header(isolated_state: Path) -> None:
    brief = build_briefing({})
    assert brief["markdown"].startswith("# Morning Briefing")
    assert "**Today at a glance:**" in brief["markdown"]
    assert "## System" in brief["markdown"]


# ── Test: seeded fixtures produce expected sections ───────────────────────────


def test_tempo_section_present_with_counts(isolated_state: Path) -> None:
    reg = {"tempo": _tempo_desc(action_count=4, info_count=12, noise_count=8)}
    brief = build_briefing(reg)

    assert "tempo" in brief["sections"]
    sec = brief["sections"]["tempo"]
    assert sec["unread_action"] == 4
    assert sec["unread_info"] == 12
    assert sec["unread_noise"] == 8
    assert len(sec["top"]) == 3


def test_tempo_subjects_in_markdown(isolated_state: Path) -> None:
    reg = {"tempo": _tempo_desc()}
    brief = build_briefing(reg)
    assert "## Tempo" in brief["markdown"]
    assert "Sarah re Q3 plan" in brief["markdown"]
    assert "Stripe invoice" in brief["markdown"]


def test_atlas_section_pnl_and_positions(isolated_state: Path) -> None:
    reg = {"atlas": _atlas_desc(pnl_usd=12.34, mock=True)}
    brief = build_briefing(reg)

    assert "atlas" in brief["sections"]
    sec = brief["sections"]["atlas"]
    assert sec["pnl_today_usd"] == 12.34
    assert sec["positions"] == 4
    assert sec["mock"] is True


def test_atlas_mock_label_in_markdown(isolated_state: Path) -> None:
    reg = {"atlas": _atlas_desc(mock=True)}
    brief = build_briefing(reg)
    assert "(mock)" in brief["markdown"]


def test_all_sections_in_markdown(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    # Seed an exam 18h in the future
    exams_path = isolated_state / "scholar_exams.jsonl"
    exam_dt = now + timedelta(hours=18)
    exams_path.write_text(
        json.dumps({"course": "Linear Algebra", "start_iso": exam_dt.isoformat()}) + "\n",
        encoding="utf-8",
    )

    reg = _full_reg()
    brief = build_briefing(reg, now=now)
    md = brief["markdown"]

    assert "## Tempo" in md
    assert "## Scholar" in md
    assert "## Atlas" in md
    assert "## System" in md


# ── Test: next_exam math ──────────────────────────────────────────────────────


def test_next_exam_12h_in_future(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    exam_dt = now + timedelta(hours=12)
    exams_path = isolated_state / "scholar_exams.jsonl"
    exams_path.write_text(
        json.dumps({"course": "Calculus", "start_iso": exam_dt.isoformat()}) + "\n",
        encoding="utf-8",
    )

    result = _next_exam_within_days(now, days=7)
    assert result is not None
    assert result["course"] == "Calculus"
    assert result["in_hours"] == 12.0


def test_next_exam_outside_window_ignored(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    far_dt = now + timedelta(days=10)
    exams_path = isolated_state / "scholar_exams.jsonl"
    exams_path.write_text(
        json.dumps({"course": "Physics", "start_iso": far_dt.isoformat()}) + "\n",
        encoding="utf-8",
    )

    result = _next_exam_within_days(now, days=7)
    assert result is None


def test_next_exam_picks_soonest(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    near = now + timedelta(hours=6)
    far = now + timedelta(hours=48)
    exams_path = isolated_state / "scholar_exams.jsonl"
    lines = "\n".join(
        [
            json.dumps({"course": "Far Course", "start_iso": far.isoformat()}),
            json.dumps({"course": "Near Course", "start_iso": near.isoformat()}),
        ]
    )
    exams_path.write_text(lines + "\n", encoding="utf-8")

    result = _next_exam_within_days(now, days=7)
    assert result is not None
    assert result["course"] == "Near Course"
    assert result["in_hours"] == 6.0


def test_exam_in_past_not_returned(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    past_dt = now - timedelta(hours=2)
    exams_path = isolated_state / "scholar_exams.jsonl"
    exams_path.write_text(
        json.dumps({"course": "Past Course", "start_iso": past_dt.isoformat()}) + "\n",
        encoding="utf-8",
    )
    result = _next_exam_within_days(now, days=7)
    assert result is None


# ── Test: dead-letter count surfaces in System section ────────────────────────


def test_dead_letter_count_in_system_section(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    dl_path = isolated_state / "dead_letter.jsonl"
    recent = (now - timedelta(hours=1)).isoformat()
    old = (now - timedelta(hours=30)).isoformat()
    dl_path.write_text(
        json.dumps({"ts": recent, "agent": "tempo", "action": "triage", "error_msg": "boom",
                    "request_id": "abc", "args_summary": "", "error_class": "RuntimeError",
                    "retries": 1, "traceback": ""}) + "\n"
        + json.dumps({"ts": old, "agent": "atlas", "action": "pnl", "error_msg": "timeout",
                      "request_id": "def", "args_summary": "", "error_class": "TimeoutError",
                      "retries": 2, "traceback": ""}) + "\n",
        encoding="utf-8",
    )

    system = _build_system_section(now)
    assert system["dead_letters_24h"] == 1  # only the recent one


def test_dead_letter_zero_when_no_file(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    system = _build_system_section(now)
    assert system["dead_letters_24h"] == 0


def test_dead_letters_in_markdown(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)
    dl_path = isolated_state / "dead_letter.jsonl"
    dl_path.write_text(
        json.dumps({"ts": now.isoformat(), "agent": "tempo", "action": "triage",
                    "error_msg": "x", "request_id": "r1", "args_summary": "",
                    "error_class": "RuntimeError", "retries": 0, "traceback": ""}) + "\n",
        encoding="utf-8",
    )
    brief = build_briefing({}, now=now)
    assert "1 dead-letter" in brief["markdown"]


# ── Test: dispatch count in system section ────────────────────────────────────


def test_dispatch_count_last_24h(isolated_state: Path) -> None:
    now = datetime(2026, 4, 29, 8, 0, 0, tzinfo=UTC)

    recent_ts = (now - timedelta(hours=1)).isoformat()
    old_ts = (now - timedelta(hours=25)).isoformat()

    append_agent_log(AgentLogEntry(ts=recent_ts, request_id="r1", agent="tempo", action="triage", status="ok"))
    append_agent_log(AgentLogEntry(ts=recent_ts, request_id="r2", agent="atlas", action="pnl", status="ok"))
    append_agent_log(AgentLogEntry(ts=old_ts, request_id="r3", agent="scholar", action="list_assignments", status="ok"))

    system = _build_system_section(now)
    assert system["dispatches_24h"] == 2


# ── Test: API endpoint ────────────────────────────────────────────────────────


def test_api_briefing_endpoint(isolated_state: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    client = TestClient(make_app())
    r = client.get("/api/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    data = body["data"]
    assert "markdown" in data
    assert "sections" in data
    assert "metadata" in data
    assert "# Morning Briefing" in data["markdown"]


def test_api_briefing_envelope_shape(isolated_state: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    client = TestClient(make_app())
    r = client.get("/api/briefing")
    body = r.json()
    assert set(body.keys()) == {"data", "error"}
    sections = body["data"]["sections"]
    assert "system" in sections


# ── Test: scholar weak topics ─────────────────────────────────────────────────


def test_weak_topics_returned(isolated_state: Path) -> None:
    wt_path = isolated_state / "scholar_weak_topics.json"
    wt_path.write_text(
        json.dumps({
            "Linear Algebra": {
                "rank-nullity": {"miss_count": 3, "total": 5},
                "eigenvectors": {"miss_count": 2, "total": 4},
                "Gram-Schmidt": {"miss_count": 1, "total": 3},
            }
        }),
        encoding="utf-8",
    )

    weak = _top_weak_topics(top_n=3)
    assert len(weak) == 3
    assert weak[0]["topic"] == "rank-nullity"
    assert weak[0]["miss_count"] == 3


def test_scholar_section_includes_weak_topics_in_markdown(isolated_state: Path) -> None:
    wt_path = isolated_state / "scholar_weak_topics.json"
    wt_path.write_text(
        json.dumps({
            "Linear Algebra": {
                "rank-nullity": {"miss_count": 3},
                "eigenvectors": {"miss_count": 2},
            }
        }),
        encoding="utf-8",
    )
    brief = build_briefing({})
    assert "rank-nullity" in brief["markdown"]


# ── Test: due-today tasks reflected in tempo section ─────────────────────────


def test_due_today_task_count(isolated_state: Path) -> None:
    today = datetime.now(UTC).date().isoformat()
    add_task(Task(title="submit report", due=today, status="open"))
    add_task(Task(title="old task", due="2020-01-01", status="open"))  # overdue

    reg = {"tempo": _tempo_desc()}
    brief = build_briefing(reg)

    sec = brief["sections"]["tempo"]
    assert sec["due_today"] == 1
    assert sec["overdue"] == 1


# ── Test: metadata fields ─────────────────────────────────────────────────────


def test_metadata_has_required_keys(isolated_state: Path) -> None:
    brief = build_briefing({})
    meta = brief["metadata"]
    assert "generated_iso" in meta
    assert "duration_ms" in meta
    assert isinstance(meta["duration_ms"], int)
