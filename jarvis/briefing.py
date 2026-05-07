"""Smart morning briefing — aggregates real state, returns markdown + structured.

Pulls from every subsystem via the registry and state files.
No LLM in the hot path — all sections are deterministic.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import get_settings
from .cost import daily_rollup
from .state import load_tasks, read_agent_log

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _dead_letter_path() -> Path:
    return get_settings().state_dir / "dead_letter.jsonl"


def _exams_path() -> Path:
    return get_settings().state_dir / "scholar_exams.jsonl"


def _weak_topics_path() -> Path:
    return get_settings().state_dir / "scholar_weak_topics.json"


def _problems_path() -> Path:
    return get_settings().state_dir / "scholar_problems.jsonl"


# ── Section builders ──────────────────────────────────────────────────────────


def _build_tempo_section(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Pull triage_status from tempo; return None on failure."""
    tempo_desc = reg.get("tempo")
    if tempo_desc is None:
        return None
    try:
        resp = tempo_desc.call("triage_status")
    except Exception:
        log.warning("briefing: tempo.triage_status failed", exc_info=True)
        return None

    result = resp.result
    # triage_status uses "counts" for bucket totals, "top_action_required" for items
    bucket_counts: dict[str, int] = result.get("counts", result.get("bucket_counts", {}))
    top_raw: list[dict[str, Any]] = result.get(
        "top_action_required", result.get("top_action", [])
    )

    action_count = bucket_counts.get("action_required", 0)
    info_count = bucket_counts.get("info_only", 0)
    noise_count = bucket_counts.get("noise", 0)

    top = [
        {"subject": r.get("subject", ""), "from": r.get("from_addr", r.get("from", ""))}
        for r in top_raw[:3]
    ]

    tasks = load_tasks()
    today_str = datetime.now(UTC).date().isoformat()
    due_today = sum(
        1 for t in tasks if t.status == "open" and t.due and t.due.startswith(today_str)
    )
    overdue = sum(
        1
        for t in tasks
        if t.status == "open" and t.due and t.due < today_str
    )

    return {
        "unread_action": action_count,
        "unread_info": info_count,
        "unread_noise": noise_count,
        "top": top,
        "due_today": due_today,
        "overdue": overdue,
    }


def _build_scholar_section(now: datetime) -> dict[str, Any] | None:
    """Read scholar state files directly; return None if nothing notable."""
    next_exam = _next_exam_within_days(now, days=7)
    weak = _top_weak_topics(top_n=3)
    review_depth = _review_queue_depth(now)

    if next_exam is None and not weak and review_depth == 0:
        return None

    return {
        "next_exam": next_exam,
        "weak_top3": weak,
        "review_depth": review_depth,
    }


def _next_exam_within_days(
    now: datetime, days: int
) -> dict[str, Any] | None:
    """Return {course, in_hours} for the soonest exam in next `days` days."""
    path = _exams_path()
    if not path.exists():
        return None

    cutoff = now + timedelta(days=days)
    soonest: dict[str, Any] | None = None
    soonest_dt: datetime | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        start_str = rec.get("start_iso") or rec.get("start")
        if not start_str:
            continue
        try:
            start_dt = datetime.fromisoformat(start_str)
        except (ValueError, TypeError):
            continue
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
        if now <= start_dt <= cutoff and (soonest_dt is None or start_dt < soonest_dt):
            soonest_dt = start_dt
            soonest = {
                "course": rec.get("course", "Unknown"),
                "in_hours": round((start_dt - now).total_seconds() / 3600, 1),
            }

    return soonest


def _top_weak_topics(top_n: int = 3) -> list[dict[str, Any]]:
    """Return top-N weak topics across all courses as [{topic, course, miss_count}]."""
    path = _weak_topics_path()
    if not path.exists():
        return []
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    # Detect flat (legacy) vs nested-by-course
    is_flat = any(isinstance(v, dict) and "miss_count" in v for v in raw.values())
    if is_flat:
        raw = {"_global": raw}

    entries: list[tuple[int, str, str]] = []  # (miss_count, topic, course)
    for course, topics in raw.items():
        if not isinstance(topics, dict):
            continue
        for topic, stats in topics.items():
            if not isinstance(stats, dict):
                continue
            miss = int(stats.get("miss_count", 0))
            entries.append((miss, topic, course))

    entries.sort(key=lambda x: x[0], reverse=True)
    return [
        {"topic": t, "course": c, "miss_count": m}
        for m, t, c in entries[:top_n]
        if m > 0
    ]


def _review_queue_depth(now: datetime) -> int:
    """Count problems where next_review_iso <= now (due for review)."""
    path = _problems_path()
    if not path.exists():
        return 0

    now_iso = now.isoformat()
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        next_rev = rec.get("next_review_iso", "")
        if next_rev and next_rev <= now_iso:
            count += 1
    return count


def _build_atlas_section(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Call atlas.pnl(); return None on total failure."""
    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return None
    try:
        pnl_resp = atlas_desc.call("pnl")
        port_resp = atlas_desc.call("portfolio")
    except Exception:
        log.warning("briefing: atlas calls failed", exc_info=True)
        return None

    pnl = pnl_resp.result.get("pnl", {})
    is_mock = bool(pnl_resp.result.get("mock") or port_resp.result.get("mock"))

    pnl_usd = float(pnl.get("pnl_usd", pnl.get("pnl_pct", 0.0) * 10_000))

    positions_raw = port_resp.result.get("positions", [])
    if isinstance(positions_raw, list):
        position_count = len(positions_raw)
    else:
        position_count = int(port_resp.result.get("position_count", 0))

    return {
        "pnl_today_usd": round(pnl_usd, 2),
        "positions": position_count,
        "mock": is_mock,
    }


def _build_system_section(now: datetime) -> dict[str, Any]:
    """Read dead-letter + agent-log + cost rollup."""
    cutoff = now - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()

    # Dead-letter count last 24h
    dl_count = 0
    dl_path = _dead_letter_path()
    if dl_path.exists():
        for raw in dl_path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
                ts = rec.get("ts", "")
                if ts >= cutoff_iso:
                    dl_count += 1
            except json.JSONDecodeError:
                continue

    # Agent dispatch count last 24h
    entries = read_agent_log(limit=0)
    dispatch_count = sum(
        1 for e in entries if e.ts >= cutoff_iso
    )

    # Cost today
    rollup = daily_rollup()
    cost_today = float(rollup.get("total_usd", 0.0))

    return {
        "dead_letters_24h": dl_count,
        "dispatches_24h": dispatch_count,
        "cost_today": cost_today,
    }


# ── Markdown rendering ────────────────────────────────────────────────────────


def _glance_line(
    tempo: dict[str, Any] | None,
    scholar: dict[str, Any] | None,
    atlas: dict[str, Any] | None,
    _now: datetime,
) -> str:
    parts: list[str] = []
    if tempo:
        a = tempo["unread_action"]
        if a:
            parts.append(f"{a} important email{'s' if a != 1 else ''}")
        due = tempo["due_today"] + tempo["overdue"]
        if due:
            parts.append(f"{due} deadline{'s' if due != 1 else ''}")
    if scholar and scholar.get("next_exam"):
        hours = scholar["next_exam"]["in_hours"]
        parts.append(f"exam in {hours:.0f}h")
    if atlas:
        pnl = atlas["pnl_today_usd"]
        pct = (pnl / 10_000) * 100  # rough pct of $10k base
        sign = "+" if pnl >= 0 else ""
        suffix = " (mock)" if atlas["mock"] else ""
        parts.append(f"atlas {sign}{pct:.1f}%{suffix}")
    return " · ".join(parts) if parts else "nothing urgent"


def _render_markdown(
    date_str: str,
    glance: str,
    tempo: dict[str, Any] | None,
    scholar: dict[str, Any] | None,
    atlas: dict[str, Any] | None,
    system: dict[str, Any],
) -> str:
    lines: list[str] = [
        f"# Morning Briefing · {date_str}",
        "",
        f"**Today at a glance:** {glance}",
        "",
    ]

    if tempo:
        lines.append("## Tempo")
        a, i, n = tempo["unread_action"], tempo["unread_info"], tempo["unread_noise"]
        lines.append(
            f"- {a} action-required email{'s' if a != 1 else ''}"
            f" ({i} info, {n} noise filtered)"
        )
        top = tempo.get("top", [])
        if top:
            subjects = ", ".join(
                f"*{r['subject']}*" if r["subject"] else f"*{r['from']}*"
                for r in top
            )
            lines.append(f"- Top: {subjects}")
        due = tempo["due_today"]
        over = tempo["overdue"]
        task_parts = []
        if due:
            task_parts.append(f"{due} task{'s' if due != 1 else ''} due today")
        if over:
            task_parts.append(f"{over} overdue")
        if task_parts:
            lines.append(f"- {', '.join(task_parts)}")
        lines.append("")

    if scholar:
        lines.append("## Scholar")
        exam = scholar.get("next_exam")
        if exam:
            hours = exam["in_hours"]
            course = exam["course"]
            lines.append(f"- ⚠ Exam in {hours:.0f}h: {course}")
        weak = scholar.get("weak_top3", [])
        if weak:
            weak_str = ", ".join(
                f"{w['topic']} ({w['miss_count']})" for w in weak
            )
            lines.append(f"- Weak topics: {weak_str}")
        depth = scholar.get("review_depth", 0)
        if depth:
            lines.append(f"- {depth} card{'s' if depth != 1 else ''} in review queue")
        lines.append("")

    if atlas:
        lines.append("## Atlas")
        pnl = atlas["pnl_today_usd"]
        sign = "+" if pnl >= 0 else ""
        mock_tag = " (mock)" if atlas["mock"] else ""
        lines.append(f"- P&L today: {sign}${pnl:.2f}{mock_tag}")
        pos = atlas["positions"]
        lines.append(f"- {pos} position{'s' if pos != 1 else ''}")
        lines.append("")

    lines.append("## System")
    dl = system["dead_letters_24h"]
    disp = system["dispatches_24h"]
    cost = system["cost_today"]
    lines.append(f"- {dl} dead-letter{'s' if dl != 1 else ''} · {disp} dispatches · ${cost:.2f} today")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────


def build_briefing(
    reg: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    """Return {markdown, sections: {tempo, scholar, atlas, system}, metadata}.

    All subsystem calls are defensive — a failed subsystem yields an absent
    section rather than a blown-up briefing.
    """
    t0 = time.perf_counter()
    current = _now(now)
    date_str = current.strftime("%Y-%m-%d %H:%M")

    tempo_sec = _build_tempo_section(reg)
    scholar_sec = _build_scholar_section(current)
    atlas_sec = _build_atlas_section(reg)
    system_sec = _build_system_section(current)

    glance = _glance_line(tempo_sec, scholar_sec, atlas_sec, current)

    md = _render_markdown(date_str, glance, tempo_sec, scholar_sec, atlas_sec, system_sec)

    duration_ms = int((time.perf_counter() - t0) * 1000)

    sections: dict[str, Any] = {"system": system_sec}
    if tempo_sec is not None:
        sections["tempo"] = tempo_sec
    if scholar_sec is not None:
        sections["scholar"] = scholar_sec
    if atlas_sec is not None:
        sections["atlas"] = atlas_sec

    return {
        "markdown": md,
        "sections": sections,
        "metadata": {
            "generated_iso": current.isoformat(),
            "duration_ms": duration_ms,
        },
    }
