"""Cron routines — pure functions, easily testable.

Each routine takes injected agents + notifier, runs one tick, writes
inbox events, pushes alerts. Schedules wired in sentinel.py.

Six top-level agents drive the recurring layer:
    tempo (mail+calendar) → email + calendar ticks
    atlas              → portfolio drawdown + pipeline tick
    lens               → news/watchlist tick
    scholar            → assignment due-soon tick
    forge              → no recurring tick (on-demand only)
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import get_settings
from ..contract import InboxEvent
from ..memory import append_daily, remember_session
from ..state import append_inbox, read_agent_log
from ..subsystems.atlas import AtlasOrchestrator
from ..subsystems.lens import Lens
from ..subsystems.scholar import Scholar
from ..subsystems.tempo import TIER_ACTION, Tempo
from .notifier import Notifier

if TYPE_CHECKING:
    from apscheduler.schedulers.base import BaseScheduler

log = logging.getLogger(__name__)

DRAWDOWN_ALERT_PCT = -0.05  # alert if window pnl < -5%


def email_tick(tempo: Tempo, notifier: Notifier) -> dict[str, Any]:
    resp = tempo.triage()
    counts = resp.result["counts"]
    action_count = counts.get(TIER_ACTION, 0)
    severity = "alert" if action_count >= 3 else ("warn" if action_count else "info")
    summary = f"{action_count} action emails, {counts.get('meeting_info', 0)} meetings"
    append_inbox(InboxEvent(agent="tempo", severity=severity, summary=summary,
                            ref={"counts": counts}))
    if action_count > 0:
        notifier.push("Tempo — inbox", summary, priority=1 if action_count >= 3 else 0)
    return {"action_count": action_count, "severity": severity}


def calendar_tick(tempo: Tempo, notifier: Notifier) -> dict[str, Any]:
    resp = tempo.today()
    count = resp.result["count"]
    summary = f"{count} events today"
    append_inbox(InboxEvent(agent="tempo", severity="info", summary=summary,
                            ref={"events": resp.result["events"]}))
    return {"count": count}


def atlas_tick(atlas: AtlasOrchestrator, notifier: Notifier,
               drawdown_alert_pct: float = DRAWDOWN_ALERT_PCT) -> dict[str, Any]:
    pnl_resp = atlas.pnl(window="1d")
    pnl_pct = pnl_resp.result["pnl"].get("pnl_pct", 0)
    is_mock = pnl_resp.result.get("mock", False)
    if pnl_pct <= drawdown_alert_pct and not is_mock:
        severity = "alert"
        summary = f"ATLAS drawdown: {pnl_pct:.2%}"
        notifier.push("Atlas — drawdown alert", summary, priority=2)
    else:
        severity = "info"
        summary = f"ATLAS 1d pnl: {pnl_pct:.2%}{' (mock)' if is_mock else ''}"
    append_inbox(InboxEvent(agent="atlas", severity=severity, summary=summary,
                            ref={"pnl_pct": pnl_pct, "mock": is_mock}))
    return {"pnl_pct": pnl_pct, "severity": severity}


def news_tick(lens: Lens, watchlist: list[str], notifier: Notifier) -> dict[str, Any]:
    if not watchlist:
        return {"skipped": True}
    resp = lens.monitor(watchlist)
    hits = resp.result["count"]
    summary = f"news: {hits} hits across {len(watchlist)} terms"
    append_inbox(InboxEvent(agent="lens", severity="info", summary=summary,
                            ref={"hits": resp.result["hits"]}))
    return {"hits": hits}


def scholar_tick(scholar: Scholar, notifier: Notifier) -> dict[str, Any]:
    resp = scholar.list_assignments()
    count = resp.result["count"]
    severity = "warn" if count >= 5 else "info"
    summary = f"{count} open assignments"
    append_inbox(InboxEvent(agent="scholar", severity=severity, summary=summary,
                            ref={"count": count}))
    if count >= 5:
        notifier.push("Scholar — workload high", summary, priority=0)
    return {"count": count, "severity": severity}


def morning_digest(tempo: Tempo, atlas: AtlasOrchestrator, scholar: Scholar,
                   notifier: Notifier) -> dict[str, Any]:
    em = tempo.triage()
    cal = tempo.today()
    pnl = atlas.pnl()
    sch = scholar.list_assignments()
    health = _verification_health(hours=24)
    parts = [
        f"Inbox: {em.result['counts'].get(TIER_ACTION, 0)} action",
        f"Calendar: {cal.result['count']} events",
        f"School: {sch.result['count']} open",
        f"PnL 1d: {pnl.result['pnl'].get('pnl_pct', 0):.2%}",
        (
            f"Verification: {health['verified']:.0%} verified"
            f" | {health['inference']:.0%} inference"
            f" | {health['unknown']:.0%} unknown"
        ),
    ]
    body = " | ".join(parts)
    append_inbox(InboxEvent(agent="sentinel", severity="info", summary="morning digest",
                            ref={"body": body, "verification_health": health}))
    notifier.push("Morning briefing", body, priority=0)
    return {"body": body}


def heartbeat_tick(sched: BaseScheduler, notifier: Notifier) -> dict[str, Any]:
    """Write a silent health tick to inbox.jsonl with current APScheduler job states."""
    jobs = {j.id: "scheduled" if not j.pending else "paused"
            for j in sched.get_jobs()}
    append_inbox(InboxEvent(
        agent="sentinel",
        severity="info",
        summary="heartbeat",
        ref={"jobs": jobs},
    ))
    return {"job_count": len(jobs)}


def inspect_agent_log(agent: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent agent_log entries as plain dicts — usable when live tooling hangs."""
    entries = read_agent_log(agent=agent, limit=limit)
    return [e.model_dump() for e in entries]


def announce_agent(agent_name: str, session: dict[str, Any]) -> dict[str, Any]:
    """Record first-dispatch announcement for an agent in the session tier.

    Idempotent: if agent already in session["announced_agents"], returns session unchanged.
    Also appends a bullet to today's daily memory file.
    """
    announced: set[str] = session.get("announced_agents", set())
    if agent_name in announced:
        return session
    append_daily(f"{agent_name} online")
    new_announced = announced | {agent_name}
    return remember_session(
        remember_session(session, "announced_agents", new_announced),
        f"{agent_name}.online",
        True,
    )


def _verification_health(hours: int = 24) -> dict[str, float]:
    """Return fraction of agent_log entries in last N hours by verification status.

    Reads raw JSONL to pick up the verification field even when AgentLogEntry
    does not yet model it. Entries missing the field count as 'unknown'.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    log_path: Path = get_settings().state_dir / "agent_log.jsonl"
    if not log_path.exists():
        return {"verified": 0.0, "inference": 0.0, "unknown": 0.0}

    counts: dict[str, int] = {"verified": 0, "inference": 0, "unknown": 0}
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        try:
            ts = datetime.fromisoformat(entry.get("ts", ""))
            if ts < cutoff:
                continue
        except (ValueError, TypeError):
            continue
        status = entry.get("verification", {}).get("status", "unknown")
        bucket = status if status in counts else "unknown"
        counts[bucket] += 1

    total = sum(counts.values())
    if total == 0:
        return {"verified": 0.0, "inference": 0.0, "unknown": 0.0}
    return {k: v / total for k, v in counts.items()}
