"""Digest exports — daily and weekly markdown summaries of Jarvis activity.

Public API:
    daily_digest(date)    -> str   markdown for one day
    weekly_digest(end)    -> str   markdown for the 7-day window ending on end

Both functions read from state/* files using the configured state_dir.
They never write state and never call external services except atlas
(optional, skipped on failure).
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.config import get_settings
from jarvis.contract import AgentLogEntry, Confirmation, InboxEvent, Task
from jarvis.state import load_tasks, read_agent_log, read_confirmations, read_inbox

log = logging.getLogger(__name__)

# ── Date range type alias ─────────────────────────────────────────────────────

DateRange = tuple[datetime.date, datetime.date]  # (start_inclusive, end_inclusive)

# ── Private helpers ───────────────────────────────────────────────────────────


def _load_jsonl(
    path: Path,
    predicate: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    """Read a JSONL file line-by-line, returning only lines that pass predicate.

    Silently skips malformed lines.
    """
    if not path.exists():
        return []
    results: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if predicate(obj):
                results.append(obj)
        except (json.JSONDecodeError, TypeError):
            log.debug("skipping malformed jsonl line in %s", path)
    return results


def _ts_in_range(ts_str: str, date_range: DateRange) -> bool:
    """Return True if ISO-8601 ts_str falls within date_range (inclusive)."""
    try:
        dt = datetime.datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.UTC)
        d = dt.astimezone(datetime.UTC).date()
        return date_range[0] <= d <= date_range[1]
    except (ValueError, TypeError):
        return False


def _entries_in_range(
    entries: list[AgentLogEntry], date_range: DateRange
) -> list[AgentLogEntry]:
    return [e for e in entries if _ts_in_range(e.ts, date_range)]


def _confirmations_in_range(
    items: list[Confirmation], date_range: DateRange
) -> list[Confirmation]:
    return [c for c in items if _ts_in_range(c.ts, date_range)]


def _inbox_in_range(
    events: list[InboxEvent], date_range: DateRange
) -> list[InboxEvent]:
    return [e for e in events if _ts_in_range(e.ts, date_range)]


# ── Section formatters ────────────────────────────────────────────────────────


def _format_agent_summary(entries: list[AgentLogEntry]) -> str:
    """Return the ## Activity markdown section."""
    ok = sum(1 for e in entries if e.status == "ok")
    errored = sum(1 for e in entries if e.status == "error")
    proposed = sum(1 for e in entries if e.status == "proposed")
    total = len(entries)
    lines = [
        "## Activity",
        f"- {total} agent dispatches ({ok} ok, {errored} errored"
        + (f", {proposed} proposed" if proposed else "")
        + ")",
    ]
    return "\n".join(lines)


def _format_confirmations(items: list[Confirmation]) -> str:
    """Return confirmation bullet for the ## Activity section."""
    if not items:
        return "- 0 confirmations"
    approved = sum(1 for c in items if c.status == "approved")
    pending = sum(1 for c in items if c.status == "pending")
    rejected = sum(1 for c in items if c.status == "rejected")
    parts = []
    if approved:
        parts.append(f"{approved} approved")
    if pending:
        parts.append(f"{pending} pending")
    if rejected:
        parts.append(f"{rejected} rejected")
    return f"- {len(items)} confirmations ({', '.join(parts)})"


def _format_tasks(tasks: list[Task]) -> str | None:
    """Return the ## Tasks markdown section, or None if no tasks."""
    if not tasks:
        return None
    done = [t for t in tasks if t.status == "done"]
    open_ = [t for t in tasks if t.status == "open"]
    lines = ["## Tasks"]
    if done:
        lines.append("**Completed:**")
        for t in done:
            tag_prefix = f"[{t.tags[0]}] " if t.tags else ""
            lines.append(f"- {tag_prefix}{t.title}")
    if open_:
        lines.append("**Open:**")
        for t in open_:
            tag_prefix = f"[{t.tags[0]}] " if t.tags else ""
            due_str = f" (due {t.due})" if t.due else ""
            lines.append(f"- {tag_prefix}{t.title}{due_str}")
    return "\n".join(lines)


def _scholar_stats(
    problems: list[dict[str, Any]],
    exams: list[dict[str, Any]],
    date_range: DateRange,
) -> dict[str, Any] | None:
    """Compute scholar stats for date_range. Returns None when no data."""
    filtered_problems = [
        p for p in problems if _ts_in_range(p.get("ts", ""), date_range)
    ]
    filtered_exams = [
        e for e in exams if _ts_in_range(e.get("started_iso", ""), date_range)
    ]
    if not filtered_problems and not filtered_exams:
        return None

    # Group problems by course
    by_course: dict[str, list[dict[str, Any]]] = {}
    for p in filtered_problems:
        course = p.get("course", "Unknown")
        by_course.setdefault(course, []).append(p)

    correct = sum(1 for p in filtered_problems if p.get("rated_correct") is True)
    missed = sum(1 for p in filtered_problems if p.get("rated_correct") is False)

    # Collect weak topic candidates
    weak: list[str] = []
    for p in filtered_problems:
        resp = p.get("response", {})
        for wt in resp.get("weak_topic_candidates", []):
            if wt not in weak:
                weak.append(wt)

    return {
        "by_course": by_course,
        "total_problems": len(filtered_problems),
        "correct": correct,
        "missed": missed,
        "weak_topics": weak,
        "exam_count": len(filtered_exams),
    }


def _format_scholar(stats: dict[str, Any] | None) -> str | None:
    """Return the ## Scholar markdown section or None."""
    if stats is None:
        return None
    lines = ["## Scholar"]
    for course, problems in stats["by_course"].items():
        correct = sum(1 for p in problems if p.get("rated_correct") is True)
        missed = sum(1 for p in problems if p.get("rated_correct") is False)
        lines.append(
            f"- {course}: {len(problems)} problems ({correct} correct, {missed} missed)"
        )
    if stats["exam_count"]:
        lines.append(f"- Exam sessions: {stats['exam_count']}")
    if stats["weak_topics"]:
        weak_str = ", ".join(stats["weak_topics"][:3])
        lines.append(f"- Weak topics flagged: {weak_str}")
    return "\n".join(lines)


def _atlas_summary() -> str | None:
    """Fetch live atlas snapshot; return ## Atlas section or None on failure."""
    try:
        from jarvis.agents.registry import build_default_registry

        reg = build_default_registry()
        atlas_desc = reg.get("atlas")
        if atlas_desc is None:
            return None
        pnl_resp = atlas_desc.call("pnl")
        pnl = pnl_resp.result
        pos_resp = atlas_desc.call("positions")
        positions = pos_resp.result
        is_mock = bool(pnl.get("mock"))
        label = " (mock)" if is_mock else ""
        pnl_pct = pnl.get("pnl_pct", 0.0)
        pnl_display = f"{pnl_pct:+.2%}"
        n_pos = (
            len(positions)
            if isinstance(positions, list)
            else len(positions.get("positions", []))
        )
        lines = [
            "## Atlas",
            f"- Day P&L: {pnl_display}{label}",
            f"- {n_pos} positions",
        ]
        return "\n".join(lines)
    except Exception:
        log.debug("atlas summary unavailable", exc_info=True)
        return None


def _conversation_excerpts(state_dir: Path) -> str | None:
    """Return ## Conversations section from jarvis_turn_log.json or None."""
    turn_log_path = state_dir / "jarvis_turn_log.json"
    if not turn_log_path.exists():
        return None
    try:
        turns: list[dict[str, Any]] = json.loads(
            turn_log_path.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        log.debug("could not read jarvis_turn_log.json")
        return None

    if not turns:
        return None

    # Pick at most 5 pairs (user + assistant), evenly spaced
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    i = 0
    while i < len(turns) - 1:
        if turns[i].get("role") == "user" and turns[i + 1].get("role") == "assistant":
            pairs.append((turns[i], turns[i + 1]))
            i += 2
        else:
            i += 1

    if not pairs:
        return None

    # Pick at most 5 representative pairs (head, tail, spread)
    selected = _pick_representative(pairs, max_count=5)

    lines = [
        "## Conversations with Jarvis",
        f"*Excerpts from last {len(turns)} turns:*",
    ]
    for user_turn, asst_turn in selected:
        u_text = user_turn.get("text", "")[:200]
        a_text = asst_turn.get("text", "")[:200]
        lines.append(f"> User: {u_text}")
        lines.append(f"> Jarvis: {a_text}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _pick_representative(
    pairs: list[tuple[Any, Any]], max_count: int
) -> list[tuple[Any, Any]]:
    """Select up to max_count evenly-spread pairs from a list."""
    if len(pairs) <= max_count:
        return pairs
    step = len(pairs) / max_count
    return [pairs[round(i * step)] for i in range(max_count)]


def _format_inbox_summary(events: list[InboxEvent]) -> str | None:
    """Return ## Notable Inbox Events section or None."""
    if not events:
        return None
    # Summarise by agent
    by_agent: dict[str, int] = {}
    for e in events:
        by_agent[e.agent] = by_agent.get(e.agent, 0) + 1
    lines = ["## Notable Inbox Events"]
    for agent, count in sorted(by_agent.items()):
        lines.append(f"- [{agent}] {count} event{'s' if count != 1 else ''}")
    return "\n".join(lines)


# ── Core functions ────────────────────────────────────────────────────────────


def daily_digest(date: datetime.date | None = None) -> str:
    """Return a markdown digest for a single day (default = today UTC)."""
    target = date or datetime.datetime.now(datetime.UTC).date()
    date_range: DateRange = (target, target)
    return _build_digest(
        title=f"# Daily Digest · {target.isoformat()}",
        date_range=date_range,
    )


def weekly_digest(end_date: datetime.date | None = None) -> str:
    """Return a markdown digest for the 7-day window ending on end_date (default today UTC)."""
    end = end_date or datetime.datetime.now(datetime.UTC).date()
    start = end - datetime.timedelta(days=6)
    date_range: DateRange = (start, end)
    return _build_digest(
        title=f"# Weekly Digest · {start.isoformat()} — {end.isoformat()}",
        date_range=date_range,
    )


def _build_digest(title: str, date_range: DateRange) -> str:
    """Assemble all sections into a single markdown string."""
    state_dir = get_settings().state_dir

    # ── Activity ──────────────────────────────────────────────────────────────
    all_entries = read_agent_log(limit=0)
    entries = _entries_in_range(all_entries, date_range)
    all_confs = read_confirmations(status=None, limit=0)
    confs = _confirmations_in_range(all_confs, date_range)
    all_inbox = read_inbox(limit=500)
    inbox_events = _inbox_in_range(all_inbox, date_range)

    activity_section = _format_agent_summary(entries)
    activity_section += "\n" + _format_confirmations(confs)
    # Dead-letters: inbox events with severity == "alert" not actioned
    dead_letters = [e for e in inbox_events if e.severity == "alert"]
    activity_section += f"\n- {len(dead_letters)} dead-letters"

    # ── Tasks ─────────────────────────────────────────────────────────────────
    all_tasks = load_tasks()
    tasks_section = _format_tasks(all_tasks)

    # ── Scholar ───────────────────────────────────────────────────────────────
    problems = _load_jsonl(
        state_dir / "scholar_problems.jsonl",
        lambda _: True,
    )
    exams = _load_jsonl(
        state_dir / "scholar_exams.jsonl",
        lambda _: True,
    )
    scholar_stats = _scholar_stats(problems, exams, date_range)
    scholar_section = _format_scholar(scholar_stats)

    # ── Atlas ─────────────────────────────────────────────────────────────────
    atlas_section = _atlas_summary()

    # ── Conversations ─────────────────────────────────────────────────────────
    conv_section = _conversation_excerpts(state_dir)

    # ── Inbox events ─────────────────────────────────────────────────────────
    inbox_section = _format_inbox_summary(inbox_events)

    # ── Assemble ──────────────────────────────────────────────────────────────
    parts = [title, ""]
    parts.append(activity_section)

    for section in (
        tasks_section,
        scholar_section,
        atlas_section,
        conv_section,
        inbox_section,
    ):
        if section:
            parts.append("")
            parts.append(section)

    return "\n".join(parts)
