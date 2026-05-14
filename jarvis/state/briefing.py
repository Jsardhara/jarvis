"""Smart morning briefing — aggregates real state, returns markdown + structured.

Pulls from every subsystem via the registry and state files.
No LLM in the hot path — all sections are deterministic.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.config import get_settings
from jarvis.llm.cost import daily_rollup
from jarvis.state import load_tasks, read_agent_log

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


# ── Evening digest ────────────────────────────────────────────────────────────


def _closes_today(now: datetime) -> list[Any]:
    """Tasks whose status==done AND updated >= start-of-today (UTC)."""
    today_start_iso = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return [
        t
        for t in load_tasks()
        if t.status == "done" and (t.updated or "") >= today_start_iso
    ]


def _open_loops_at_eod(now: datetime) -> list[Any]:
    """Open tasks that are either high-priority or due tomorrow.

    "High priority" is tag-based: any of {priority:high, p1, urgent}.
    """
    tomorrow_str = (now + timedelta(days=1)).date().isoformat()
    high_tags = {"priority:high", "p1", "urgent"}
    out: list[Any] = []
    for t in load_tasks():
        if t.status != "open":
            continue
        tags_lower = {str(tag).lower() for tag in (t.tags or [])}
        is_high = bool(tags_lower & high_tags)
        is_due_tomorrow = bool(t.due and t.due.startswith(tomorrow_str))
        if is_high or is_due_tomorrow:
            out.append(t)
    return out


def _today_cost_rollup() -> dict[str, float]:
    """Today's cost-log spend grouped by agent (empty when cost_log missing)."""
    rollup = daily_rollup()
    by_agent = rollup.get("by_agent") or {}
    if not isinstance(by_agent, dict):
        return {}
    return {str(k): float(v) for k, v in by_agent.items()}


def _tomorrow_first_event(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Return the next-day's first calendar event as a dict, or None.

    Tries ``tempo.today_first_tomorrow()`` first (preferred); falls back to
    filtering ``tempo.today()`` events for ones starting tomorrow.
    """
    tempo_desc = reg.get("tempo")
    if tempo_desc is None:
        return None
    tempo_inst = getattr(tempo_desc, "instance", None)
    if tempo_inst is not None:
        fn = getattr(tempo_inst, "today_first_tomorrow", None)
        if callable(fn):
            try:
                resp = fn()
                first = resp.result if hasattr(resp, "result") else resp
                if isinstance(first, dict) and first:
                    return first
            except Exception:
                log.warning("evening_digest: today_first_tomorrow failed", exc_info=True)
    # Fallback — best effort via today()
    try:
        resp = tempo_desc.call("today")
        events = resp.result.get("events", []) if hasattr(resp, "result") else []
    except Exception:
        log.warning("evening_digest: tempo.today fallback failed", exc_info=True)
        return None
    tomorrow_str = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        start = str(ev.get("start") or ev.get("when") or "")
        if start.startswith(tomorrow_str):
            return ev
    return None


def _atlas_pnl_close(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Return today's realized P&L close for atlas, or None when unavailable."""
    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return None
    try:
        pnl_resp = atlas_desc.call("pnl")
    except Exception:
        log.warning("evening_digest: atlas.pnl failed", exc_info=True)
        return None
    pnl = pnl_resp.result.get("pnl", {}) if hasattr(pnl_resp, "result") else {}
    if not pnl:
        return None
    pnl_usd_raw = pnl.get("pnl_usd")
    pnl_pct_raw = pnl.get("pnl_pct")
    if pnl_usd_raw is None and pnl_pct_raw is None:
        return None
    return {
        "pnl_usd": float(pnl_usd_raw if pnl_usd_raw is not None else 0.0),
        "pnl_pct": float(pnl_pct_raw if pnl_pct_raw is not None else 0.0),
        "mock": bool(pnl_resp.result.get("mock", False)) if hasattr(pnl_resp, "result") else False,
    }


def _render_evening_markdown(
    date_str: str,
    closes: list[Any],
    open_loops: list[Any],
    cost_by_agent: dict[str, float],
    tomorrow_first: dict[str, Any] | None,
    atlas_close: dict[str, Any] | None,
) -> str:
    """Render evening digest markdown — each section conditional on content."""
    lines: list[str] = [f"# Evening Recap · {date_str}", ""]

    if closes:
        lines.append("## Today's closes")
        for t in closes:
            lines.append(f"- {t.title}")
        lines.append("")

    if open_loops:
        lines.append("## Open loops")
        for t in open_loops:
            tail = f" (due {t.due})" if t.due else ""
            lines.append(f"- {t.title}{tail}")
        lines.append("")

    if cost_by_agent:
        lines.append("## Cost rollup")
        total = sum(cost_by_agent.values())
        lines.append(f"- Total today: ${total:.4f}")
        for agent, cost in sorted(cost_by_agent.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {agent}: ${cost:.4f}")
        lines.append("")

    if tomorrow_first:
        title = (
            tomorrow_first.get("subject")
            or tomorrow_first.get("title")
            or "Untitled"
        )
        start = tomorrow_first.get("start") or tomorrow_first.get("when") or ""
        lines.append("## Tomorrow's first event")
        lines.append(f"- {title} @ {start}".rstrip(" @"))
        lines.append("")

    if atlas_close:
        sign = "+" if atlas_close["pnl_usd"] >= 0 else ""
        mock_tag = " (mock)" if atlas_close.get("mock") else ""
        lines.append("## Atlas close")
        lines.append(
            f"- P&L: {sign}${atlas_close['pnl_usd']:.2f} "
            f"({atlas_close['pnl_pct']:+.2%}){mock_tag}"
        )
        lines.append("")

    # If everything is empty, still emit a tombstone so the operator sees the cron ran.
    if len(lines) == 2:
        lines.append("_Nothing notable today._")

    return "\n".join(lines).rstrip() + "\n"


def evening_digest(reg: dict[str, Any], notifier: Any) -> dict[str, Any]:
    """End-of-day recap — distinct from morning_digest.

    Aggregates closed tasks, open loops, today's spend, tomorrow's first event,
    and atlas P&L close. Pushes a priority-1 notification ("Evening recap") and
    appends a single info-severity inbox event. Returns ``{"digest", "severity"}``.
    """
    from jarvis.contract import InboxEvent
    from jarvis.state import append_inbox

    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")

    closes = _closes_today(now)
    open_loops = _open_loops_at_eod(now)
    cost_by_agent = _today_cost_rollup()
    tomorrow_first = _tomorrow_first_event(reg)
    atlas_close = _atlas_pnl_close(reg)
    memory_section = _build_memory_section(now.date())

    digest_md = _render_evening_markdown(
        date_str, closes, open_loops, cost_by_agent, tomorrow_first, atlas_close
    )
    if memory_section:
        digest_md = f"{digest_md}\n\n{memory_section}"

    try:
        notifier.push("Evening recap", digest_md[:300] + "...", priority=1)
    except Exception:
        log.warning("evening_digest: notifier push failed", exc_info=True)

    append_inbox(
        InboxEvent(
            agent="sentinel",
            severity="info",
            summary="Evening digest fired",
            ref={
                "closes": [t.title for t in closes],
                "open_loops": [t.title for t in open_loops],
                "cost_by_agent": cost_by_agent,
                "tomorrow_first": tomorrow_first,
                "atlas_close": atlas_close,
            },
        )
    )

    return {"digest": digest_md, "severity": "info"}


# ── Memory section (J2) ───────────────────────────────────────────────────────


_MEMORY_DAILY_CAP_CHARS = 200
_MEMORY_RECENT_TURN_LIMIT = 10
_MEMORY_TURN_TRUNC_CHARS = 160


def _build_memory_section(today: date) -> str:
    """Render a ``## Memory`` markdown section, or empty string if no content.

    Pulls:
      * Yesterday's daily file (``memory.read_daily``) — capped at 200 chars.
      * Recent chat_turns — last 10 turns, oldest-first, each truncated.

    Defensive against every read failure (filesystem, import) — a broken
    memory store must never crash a briefing.
    """
    yesterday = today - timedelta(days=1)

    daily_excerpt = ""
    try:
        from jarvis.state import memory as _memory

        body = _memory.read_daily(yesterday.isoformat())
        if body:
            daily_excerpt = body.strip()[:_MEMORY_DAILY_CAP_CHARS]
    except Exception:  # noqa: BLE001 — never crash on memory read
        log.debug("memory section: read_daily failed", exc_info=True)

    recent_lines: list[str] = []
    try:
        from jarvis.state.chat_turns import read_recent

        records = read_recent(user_id="default", limit=_MEMORY_RECENT_TURN_LIMIT)
        for rec in records:
            user_text = (rec.user_text or "").strip()
            asst_text = (rec.assistant_text or "").strip()
            if user_text:
                recent_lines.append(
                    f"- user: {user_text[:_MEMORY_TURN_TRUNC_CHARS]}"
                )
            if asst_text:
                recent_lines.append(
                    f"- jarvis: {asst_text[:_MEMORY_TURN_TRUNC_CHARS]}"
                )
    except Exception:  # noqa: BLE001 — never crash on memory read
        log.debug("memory section: chat_turns read failed", exc_info=True)

    if not daily_excerpt and not recent_lines:
        return ""

    lines: list[str] = ["## Memory"]
    if daily_excerpt:
        lines.append(f"**Yesterday ({yesterday.isoformat()}):** {daily_excerpt}")
    if recent_lines:
        lines.append("")
        lines.append("Recent context:")
        lines.extend(recent_lines)
    return "\n".join(lines)
