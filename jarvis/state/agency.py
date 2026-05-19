"""Persistent agency — long-running goals Jarvis pursues over hours.

W4.1: JARVIS in the films runs experiments in the background ("the encryption
is at 89%, sir"). Until now Jarvis has been purely reactive — operator asks a
question, Jarvis answers. This module ships the substrate that lets sentinel
advance a goal step by step across many ticks, then surface completion as an
inbox event.

Schema:
    Goal
      id            uuid hex prefix
      title         human-readable description
      kind          "watch_price" | "watch_mail" | "periodic_check" | "freeform"
      params        kind-specific config (ticker, threshold, sender, period_sec, ...)
      status        "active" | "completed" | "failed" | "cancelled"
      created       ISO UTC
      updated       ISO UTC
      last_check    ISO UTC of last tick advance (None until first tick)
      check_count   how many times tick advanced this goal
      max_checks    auto-fail-safe; defaults to 100
      deadline      ISO UTC; goal auto-completes/fails after this
      observations  what tick discovered each step (capped at 50)
      result        final findings on completion

Storage:
    state/goals.jsonl — one Goal per line, append-on-create. Updates are
    full-record rewrites (load all → latest ts wins per id), same pattern as
    ``projects.py`` / ``drafted_replies.py``. ``rotate_if_large`` on append.

Reads:
    ``list_goals`` returns the latest record per id, optionally filtered by
    status. ``get_goal`` returns the single most-recent record for an id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)

GoalStatus = Literal["active", "completed", "failed", "cancelled"]
GoalKind = Literal["watch_price", "watch_mail", "periodic_check", "freeform"]

_OBSERVATION_CAP = 50
_DEFAULT_MAX_CHECKS = 100


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    kind: str
    params: dict[str, Any]
    status: str
    created: str
    updated: str
    last_check: str | None = None
    check_count: int = 0
    max_checks: int = _DEFAULT_MAX_CHECKS
    deadline: str | None = None
    observations: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None


def _path() -> Path:
    return get_settings().state_dir / "goals.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _from_dict(raw: dict[str, Any]) -> Goal | None:
    """Hydrate a Goal from a JSON line. Returns None on schema mismatch."""
    try:
        return Goal(
            id=str(raw["id"]),
            title=str(raw["title"]),
            kind=str(raw["kind"]),
            params=dict(raw.get("params") or {}),
            status=str(raw.get("status", "active")),
            created=str(raw.get("created", "")),
            updated=str(raw.get("updated", "")),
            last_check=raw.get("last_check"),
            check_count=int(raw.get("check_count", 0) or 0),
            max_checks=int(raw.get("max_checks", _DEFAULT_MAX_CHECKS) or _DEFAULT_MAX_CHECKS),
            deadline=raw.get("deadline"),
            observations=list(raw.get("observations") or []),
            result=raw.get("result"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("agency: skipping malformed goal record: %s", exc)
        return None


def _read_all_lines() -> list[Goal]:
    """Read every line; latest-ts wins per id."""
    target = _path()
    if not target.exists():
        return []
    by_id: dict[str, Goal] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        goal = _from_dict(data)
        if goal is None:
            continue
        prior = by_id.get(goal.id)
        if prior is None or goal.updated >= prior.updated:
            by_id[goal.id] = goal
    return list(by_id.values())


def _append_record(goal: Goal) -> None:
    """Append one JSON line. The caller-supplied goal is the new truth."""
    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(target)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(goal), ensure_ascii=False) + "\n")


def create_goal(
    title: str,
    kind: str,
    params: dict[str, Any] | None = None,
    *,
    deadline: str | None = None,
    max_checks: int = _DEFAULT_MAX_CHECKS,
) -> Goal:
    """Create a new active goal. Returns the persisted Goal."""
    now = _now_iso()
    goal = Goal(
        id=uuid4().hex[:12],
        title=title,
        kind=kind,
        params=dict(params or {}),
        status="active",
        created=now,
        updated=now,
        last_check=None,
        check_count=0,
        max_checks=max_checks,
        deadline=deadline,
        observations=[],
        result=None,
    )
    _append_record(goal)
    return goal


def list_goals(status: GoalStatus | None = None) -> list[Goal]:
    """All goals, optionally filtered by status. Sorted by updated desc."""
    items = _read_all_lines()
    if status is not None:
        items = [g for g in items if g.status == status]
    return sorted(items, key=lambda g: g.updated, reverse=True)


def get_goal(goal_id: str) -> Goal | None:
    return next((g for g in _read_all_lines() if g.id == goal_id), None)


def update_goal_check(
    goal_id: str,
    observation: str,
    *,
    result: dict[str, Any] | None = None,
    status: str | None = None,
) -> Goal | None:
    """Append observation, optionally set result/status, bump counters.

    The observation list is capped at ``_OBSERVATION_CAP`` (drops oldest) so
    long-running goals don't grow unbounded.
    """
    goals = {g.id: g for g in _read_all_lines()}
    cur = goals.get(goal_id)
    if cur is None:
        return None
    now = _now_iso()
    new_obs = list(cur.observations) + [observation]
    if len(new_obs) > _OBSERVATION_CAP:
        new_obs = new_obs[-_OBSERVATION_CAP:]
    updated = replace(
        cur,
        observations=new_obs,
        result=result if result is not None else cur.result,
        status=status if status is not None else cur.status,
        last_check=now,
        check_count=cur.check_count + 1,
        updated=now,
    )
    _append_record(updated)
    return updated


def cancel_goal(goal_id: str) -> Goal | None:
    """Mark a goal cancelled. Returns the patched record, or None if unknown."""
    goals = {g.id: g for g in _read_all_lines()}
    cur = goals.get(goal_id)
    if cur is None:
        return None
    now = _now_iso()
    updated = replace(cur, status="cancelled", updated=now)
    _append_record(updated)
    return updated


def render_active_goals_for_prompt(limit: int = 5) -> str:
    """Compact "Active goals:" block. Returns "" when no active goals."""
    active = list_goals(status="active")[:limit]
    if not active:
        return ""
    lines = ["Active goals:"]
    for g in active:
        kind = g.kind
        checks = f"{g.check_count}/{g.max_checks}"
        lines.append(f"- {g.title} [{kind}] ({checks} checks)")
    return "\n".join(lines)


__all__ = [
    "Goal",
    "GoalKind",
    "GoalStatus",
    "cancel_goal",
    "create_goal",
    "get_goal",
    "list_goals",
    "render_active_goals_for_prompt",
    "update_goal_check",
]
