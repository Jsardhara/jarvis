"""Tests for jarvis.state.projects — long-running project memory."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.state import projects as projects_mod
from jarvis.state.projects import (
    Project,
    add_blocker,
    add_milestone,
    complete_milestone,
    create_project,
    get_project,
    list_projects,
    render_active_projects_for_prompt,
    update_project,
)


@pytest.fixture(autouse=True)
def _redirect_projects_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    target = tmp_path / "projects.jsonl"
    monkeypatch.setattr(projects_mod, "_path", lambda: target)
    return target


def test_create_project_persists_and_returns() -> None:
    proj = create_project("Encryption refactor", goal="Replace AES-128 with AES-256")
    assert proj.id
    assert proj.title == "Encryption refactor"
    assert proj.status == "active"
    assert get_project(proj.id) == proj


def test_list_projects_filters_by_status() -> None:
    a = create_project("Project A")
    b = create_project("Project B")
    update_project(b.id, status="complete")
    active = list_projects(status="active")
    complete = list_projects(status="complete")
    assert any(p.id == a.id for p in active)
    assert not any(p.id == b.id for p in active)
    assert any(p.id == b.id for p in complete)


def test_update_project_bumps_timestamps() -> None:
    proj = create_project("Iterate")
    bumped = update_project(proj.id, goal="new goal")
    assert bumped is not None
    assert bumped.goal == "new goal"
    assert bumped.updated >= proj.updated


def test_add_milestone_then_complete() -> None:
    proj = create_project("Ship vision pass")
    with_ms = add_milestone(proj.id, "Wire voice")
    assert with_ms is not None
    assert len(with_ms.milestones) == 1
    completed = complete_milestone(proj.id, "Wire voice")
    assert completed is not None
    assert completed.milestones[0].done is True


def test_add_blocker_records_with_raised_ts() -> None:
    proj = create_project("Hot mic")
    blocked = add_blocker(proj.id, "VAD false-triggering on keyboard noise")
    assert blocked is not None
    assert len(blocked.blockers) == 1
    assert blocked.blockers[0].description.startswith("VAD")
    assert blocked.blockers[0].resolved is None


def test_render_active_projects_for_prompt_empty() -> None:
    assert render_active_projects_for_prompt() == ""


def test_render_active_projects_for_prompt_with_data() -> None:
    proj = create_project("Vision integration", goal="See what Jyot sees")
    add_milestone(proj.id, "Wire voice")
    add_milestone(proj.id, "Wire chat")
    complete_milestone(proj.id, "Wire voice")
    add_blocker(proj.id, "Browser paste flaky")
    rendered = render_active_projects_for_prompt()
    assert "Vision integration" in rendered
    assert "1/2 milestones" in rendered
    assert "1 blocker" in rendered


def test_get_project_unknown_returns_none() -> None:
    assert get_project("does-not-exist") is None


def test_latest_record_per_id_wins_after_updates() -> None:
    """Multiple rewrites for one id collapse to the latest line on read."""
    proj = create_project("Iterations")
    update_project(proj.id, title="Pass 1")
    update_project(proj.id, title="Pass 2")
    update_project(proj.id, title="Pass 3")
    items = list_projects()
    matches = [p for p in items if p.id == proj.id]
    assert len(matches) == 1
    assert matches[0].title == "Pass 3"
