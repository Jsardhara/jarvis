"""Long-running project memory — goals tracked across days/weeks.

Distinct from ``tasks.json`` (per-action TODOs) and ``state/memory/daily``
(per-day summaries). A Project is a multi-day objective with milestones,
blockers, and a status that the operator and Jarvis both track over time.

JARVIS in the films keeps state on Tony's projects across days ("the
encryption is at 89%, sir"). That requires durable, structured state. This
module is the foundation.

Schema:
    Project
      id            uuid hex prefix
      title         human-readable label
      goal          one-sentence objective
      status        "active" | "paused" | "complete" | "archived"
      created       ISO UTC
      updated       ISO UTC
      milestones    list[Milestone]
      blockers      list[Blocker]
      last_activity ISO UTC — bumped on every milestone/blocker change

Storage:
    state/projects.jsonl — one Project per line, append-on-create. Updates
    are full-record rewrites (load all → mutate → atomic temp+replace),
    same pattern as ``drafted_replies.py``.

Reads:
    ``list_projects`` returns the most recent record per id (latest ts
    wins per id) so a stale earlier line is masked by the rewrite.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)

ProjectStatus = Literal["active", "paused", "complete", "archived"]


@dataclass(frozen=True)
class Milestone:
    title: str
    done: bool = False
    due: str | None = None  # ISO date, optional
    notes: str = ""


@dataclass(frozen=True)
class Blocker:
    description: str
    raised: str  # ISO UTC
    resolved: str | None = None  # ISO UTC, None until cleared


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    goal: str
    status: ProjectStatus
    created: str
    updated: str
    last_activity: str
    milestones: list[Milestone] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)


def _path() -> Path:
    return get_settings().state_dir / "projects.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _from_dict(raw: dict[str, Any]) -> Project | None:
    """Hydrate a Project from a JSON line. Returns None on schema mismatch."""
    try:
        ms = [Milestone(**m) for m in raw.get("milestones", [])]
        bs = [Blocker(**b) for b in raw.get("blockers", [])]
        return Project(
            id=str(raw["id"]),
            title=str(raw["title"]),
            goal=str(raw.get("goal", "")),
            status=str(raw.get("status", "active")),  # type: ignore[arg-type]
            created=str(raw.get("created", "")),
            updated=str(raw.get("updated", "")),
            last_activity=str(raw.get("last_activity", "")),
            milestones=ms,
            blockers=bs,
        )
    except (KeyError, TypeError) as exc:
        log.warning("projects: skipping malformed record: %s", exc)
        return None


def _read_all_lines() -> list[Project]:
    """Read every line; latest-ts wins per id."""
    target = _path()
    if not target.exists():
        return []
    by_id: dict[str, Project] = {}
    for raw in target.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        proj = _from_dict(data)
        if proj is None:
            continue
        prior = by_id.get(proj.id)
        if prior is None or proj.updated >= prior.updated:
            by_id[proj.id] = proj
    return list(by_id.values())


def _append_record(project: Project) -> None:
    """Append one JSON line. Caller-supplied project is the new truth."""
    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(target)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(project), ensure_ascii=False) + "\n")


def create_project(title: str, goal: str = "") -> Project:
    """Create a new active project. Returns the persisted Project."""
    now = _now_iso()
    project = Project(
        id=uuid4().hex[:12],
        title=title,
        goal=goal,
        status="active",
        created=now,
        updated=now,
        last_activity=now,
    )
    _append_record(project)
    return project


def update_project(
    project_id: str,
    *,
    title: str | None = None,
    goal: str | None = None,
    status: ProjectStatus | None = None,
) -> Project | None:
    """Patch fields on a project. Bumps ``updated`` and ``last_activity``."""
    projects = {p.id: p for p in _read_all_lines()}
    cur = projects.get(project_id)
    if cur is None:
        return None
    now = _now_iso()
    updated = Project(
        id=cur.id,
        title=title if title is not None else cur.title,
        goal=goal if goal is not None else cur.goal,
        status=status if status is not None else cur.status,
        created=cur.created,
        updated=now,
        last_activity=now,
        milestones=list(cur.milestones),
        blockers=list(cur.blockers),
    )
    _append_record(updated)
    return updated


def add_milestone(project_id: str, title: str, due: str | None = None) -> Project | None:
    """Append a milestone to an existing project."""
    projects = {p.id: p for p in _read_all_lines()}
    cur = projects.get(project_id)
    if cur is None:
        return None
    now = _now_iso()
    new_ms = list(cur.milestones) + [Milestone(title=title, due=due)]
    updated = Project(
        id=cur.id,
        title=cur.title,
        goal=cur.goal,
        status=cur.status,
        created=cur.created,
        updated=now,
        last_activity=now,
        milestones=new_ms,
        blockers=list(cur.blockers),
    )
    _append_record(updated)
    return updated


def complete_milestone(project_id: str, milestone_title: str) -> Project | None:
    """Mark a milestone done by title match (first match wins)."""
    projects = {p.id: p for p in _read_all_lines()}
    cur = projects.get(project_id)
    if cur is None:
        return None
    matched = False
    new_ms: list[Milestone] = []
    for m in cur.milestones:
        if not matched and m.title == milestone_title and not m.done:
            new_ms.append(Milestone(title=m.title, done=True, due=m.due, notes=m.notes))
            matched = True
        else:
            new_ms.append(m)
    if not matched:
        return cur
    now = _now_iso()
    updated = Project(
        id=cur.id,
        title=cur.title,
        goal=cur.goal,
        status=cur.status,
        created=cur.created,
        updated=now,
        last_activity=now,
        milestones=new_ms,
        blockers=list(cur.blockers),
    )
    _append_record(updated)
    return updated


def add_blocker(project_id: str, description: str) -> Project | None:
    projects = {p.id: p for p in _read_all_lines()}
    cur = projects.get(project_id)
    if cur is None:
        return None
    now = _now_iso()
    new_bs = list(cur.blockers) + [Blocker(description=description, raised=now)]
    updated = Project(
        id=cur.id,
        title=cur.title,
        goal=cur.goal,
        status=cur.status,
        created=cur.created,
        updated=now,
        last_activity=now,
        milestones=list(cur.milestones),
        blockers=new_bs,
    )
    _append_record(updated)
    return updated


def list_projects(status: ProjectStatus | None = None) -> list[Project]:
    """All projects, optionally filtered by status. Sorted by updated desc."""
    items = _read_all_lines()
    if status is not None:
        items = [p for p in items if p.status == status]
    return sorted(items, key=lambda p: p.updated, reverse=True)


def get_project(project_id: str) -> Project | None:
    return next((p for p in _read_all_lines() if p.id == project_id), None)


def render_active_projects_for_prompt(limit: int = 5) -> str:
    """Compact render for injection into the chat prompt.

    Returns an empty string when there are no active projects so the live
    state block stays trim.
    """
    active = list_projects(status="active")[:limit]
    if not active:
        return ""
    lines = ["Active projects:"]
    for p in active:
        done = sum(1 for m in p.milestones if m.done)
        total = len(p.milestones)
        open_blockers = sum(1 for b in p.blockers if b.resolved is None)
        progress = f"{done}/{total} milestones" if total else "no milestones"
        blocker_note = f"; {open_blockers} blocker(s)" if open_blockers else ""
        lines.append(f"- {p.title} ({progress}{blocker_note})")
    return "\n".join(lines)


__all__ = [
    "Blocker",
    "Milestone",
    "Project",
    "ProjectStatus",
    "add_blocker",
    "add_milestone",
    "complete_milestone",
    "create_project",
    "get_project",
    "list_projects",
    "render_active_projects_for_prompt",
    "update_project",
]
