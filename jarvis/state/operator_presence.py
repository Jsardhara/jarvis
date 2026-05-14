"""Operator presence — track when the human last interacted with Jarvis.

Presence marks land in ``state/operator_presence.jsonl`` as the operator
talks to Jarvis through voice / chat / API. A sentinel scanner later checks
how long the operator has been silent and fires a warn-severity InboxEvent
when the gap crosses a threshold (default 6h) — Jarvis should notice you
disappeared without forcing you to ping it first.

Single-operator system; ``user_id`` exists for future multi-user expansion
but defaults to "default" so the dataclass stays stable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from jarvis.config import get_settings
from jarvis.contract import InboxEvent
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)

_DEFAULT_STALE_THRESHOLD_HOURS = 6
_DEDUP_WINDOW_HOURS = 12  # don't fire the stale-warn more than 2x/day


@dataclass(frozen=True)
class PresenceMark:
    """One presence mark — operator was seen on ``surface`` at ``ts``."""

    ts: str  # ISO UTC
    surface: str  # voice / chat / api
    user_id: str


def _presence_path() -> Path:
    return get_settings().state_dir / "operator_presence.jsonl"


def _fired_path() -> Path:
    return get_settings().state_dir / "triggers_fired.jsonl"


def mark_present(surface: str, user_id: str = "default") -> None:
    """Append a PresenceMark for ``surface`` at the current UTC moment."""
    mark = PresenceMark(
        ts=datetime.now(UTC).isoformat(),
        surface=surface,
        user_id=user_id,
    )
    path = _presence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(mark)) + "\n")


def last_seen() -> PresenceMark | None:
    """Return the most-recent PresenceMark, or None when no marks exist."""
    path = _presence_path()
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        try:
            return PresenceMark(
                ts=str(rec.get("ts", "")),
                surface=str(rec.get("surface", "")),
                user_id=str(rec.get("user_id", "default")),
            )
        except (TypeError, ValueError):
            continue
    return None


def seconds_since_last_seen() -> float:
    """Seconds since the most-recent mark; ``inf`` when no marks exist."""
    mark = last_seen()
    if mark is None or not mark.ts:
        return float("inf")
    try:
        when = datetime.fromisoformat(mark.ts)
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - when
    return max(0.0, delta.total_seconds())


def _was_stale_warn_fired_recently(window_hours: int) -> bool:
    """Check ``triggers_fired.jsonl`` for a recent presence-stale fire."""
    path = _fired_path()
    if not path.exists():
        return False
    cutoff = datetime.now(UTC).timestamp() - window_hours * 3600
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if rec.get("rule_name") != "operator_presence_stale":
            continue
        ts_str = rec.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts.timestamp() >= cutoff:
                return True
        except ValueError:
            continue
    return False


def _record_fired(summary: str) -> None:
    """Append a fired-trigger record for dedup tracking."""
    path = _fired_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(UTC).isoformat(),
        "rule_name": "operator_presence_stale",
        "source_key": "presence",
        "action_summary": summary,
        "outcome": "ok",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def scan_presence_stale(
    threshold_hours: int = _DEFAULT_STALE_THRESHOLD_HOURS,
) -> list[InboxEvent]:
    """Emit a warn InboxEvent if the operator has been silent > threshold.

    Dedup is per ~12h window so we don't spam the inbox when the operator
    stays away all day. Returns an empty list when fresh, when stale-but-
    already-fired, or when there are no marks at all (cold start is not
    a "stale" condition — we only warn after we've seen them once).
    """
    if last_seen() is None:
        return []
    elapsed = seconds_since_last_seen()
    if elapsed < threshold_hours * 3600:
        return []
    if _was_stale_warn_fired_recently(_DEDUP_WINDOW_HOURS):
        return []

    hours = int(elapsed / 3600)
    summary = f"Operator silent for {hours}h — check in?"
    event = InboxEvent(
        agent="sentinel",
        severity="warn",
        summary=summary,
        ref={"hours_silent": hours, "threshold_hours": threshold_hours},
    )
    _record_fired(summary)
    return [event]


__all__ = [
    "PresenceMark",
    "mark_present",
    "last_seen",
    "seconds_since_last_seen",
    "scan_presence_stale",
]
