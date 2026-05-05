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
from ..contract import InboxEvent, SentinelHealthEvent
from ..memory import append_daily, remember_session
from ..state import append_inbox, append_sentinel_health, read_agent_log
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


def morning_digest(reg: dict[str, Any], notifier: Notifier) -> dict[str, Any]:
    """Build and push the smart morning briefing, replacing the old static stub."""
    from ..briefing import build_briefing

    brief = build_briefing(reg)
    notifier.push("Morning Briefing", brief["markdown"][:300] + "...", priority=1)
    append_inbox(
        InboxEvent(
            agent="sentinel",
            severity="info",
            summary="Morning briefing fired",
            ref={"sections": brief["sections"]},
        )
    )
    return {"sections": brief["sections"]}


def heartbeat_tick(sched: BaseScheduler, notifier: Notifier) -> dict[str, Any]:
    """Write an infra health tick.

    Mirrors to sentinel_health.jsonl (clean infra file) and keeps a slim
    entry in inbox.jsonl so existing monitors stay compatible.
    """
    jobs = {j.id: "scheduled" if not j.pending else "paused" for j in sched.get_jobs()}
    append_sentinel_health(SentinelHealthEvent(job_count=len(jobs), jobs=jobs))
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


def _append_daily_project(rec: dict[str, Any]) -> None:
    path = get_settings().state_dir / "daily_projects.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def daily_forge_tick(reg: dict[str, Any], notifier: Notifier) -> dict[str, Any]:
    """Daily autonomous loop: world news → Forge → GitHub.

    Steps:
      1. lens.world_brief() — last 18h of unbiased wire-service news.
      2. budget.can_afford(0.50) for pick.
      3. forge.pick_project(stories) — Opus picks 1 + writes spec.
      4. budget.can_afford(4.00) for scaffold.
      5. forge.scaffold_daily(spec) — claude CLI builds + git push.
      6. log + notify.
    """
    from ..subsystems import budget

    started = datetime.now(UTC)
    rec_base = {"ts": started.isoformat(), "date": started.strftime("%Y-%m-%d")}

    try:
        lens_desc = reg.get("lens")
        forge_desc = reg.get("forge")
        if lens_desc is None or forge_desc is None:
            raise RuntimeError("registry missing lens or forge")

        # Step 1 — fetch unbiased world brief
        brief_resp = lens_desc.call("world_brief", {"window_hours": 18})
        stories = brief_resp.result.get("stories", [])
        if not stories:
            summary = "no fresh news in 18h window — daily forge skipped"
            append_inbox(InboxEvent(
                agent="forge", severity="warn", summary=summary, ref=rec_base
            ))
            _append_daily_project({**rec_base, "status": "skipped_no_news"})
            return {"status": "skipped_no_news"}

        # Step 2 — budget pre-check (rough estimate for pick)
        if not budget.can_afford(0.50):
            summary = "daily forge skipped — budget exhausted"
            append_inbox(InboxEvent(
                agent="forge", severity="warn", summary=summary, ref=rec_base
            ))
            notifier.push("Daily Forge skipped", summary, priority=0)
            _append_daily_project({**rec_base, "status": "skipped_budget"})
            return {"status": "skipped_budget"}

        # Step 3 — pick project
        pick_resp = forge_desc.call("pick_project", {"brief": stories})
        if pick_resp.action != "picked":
            err = pick_resp.result.get("error", "pick failed")
            append_inbox(InboxEvent(
                agent="forge", severity="alert", summary=f"daily forge pick failed: {err}",
                ref=rec_base,
            ))
            notifier.push("Daily Forge failed", err[:200], priority=1)
            _append_daily_project({**rec_base, "status": "failed", "error": err})
            return {"status": "failed", "error": err}
        spec = pick_resp.result

        # Step 4 — budget check before expensive scaffold
        if not budget.can_afford(2.50):
            summary = f"daily forge skipped post-pick — budget exhausted (picked: {spec.get('title', '')})"
            append_inbox(InboxEvent(
                agent="forge", severity="warn", summary=summary, ref={**rec_base, "spec": spec},
            ))
            notifier.push("Daily Forge skipped", summary[:200], priority=0)
            _append_daily_project({**rec_base, "status": "skipped_budget", "spec": spec})
            return {"status": "skipped_budget"}

        # Step 5 — build + push
        scaffold_resp = forge_desc.call("scaffold_daily", {"spec": spec})
        run = scaffold_resp.result

        # Step 6 — log + notify
        full_rec = {**rec_base, **run, "spec": {
            k: spec.get(k) for k in ("slug", "title", "news_url", "news_source")
        }}
        _append_daily_project(full_rec)

        if run.get("status") == "success":
            project_url = (
                f"{run.get('repo_url', '')}/tree/main/{run.get('folder', '')}"
            )
            summary = f"Today's project: {spec.get('title', 'untitled')} — {project_url}"
            append_inbox(InboxEvent(
                agent="forge", severity="info", summary=summary, ref=full_rec
            ))
            notifier.push(
                f"Daily Forge: {spec.get('title', 'project')[:60]}",
                f"{spec.get('news_source', '')} → {project_url}",
                priority=0,
            )
        else:
            err = run.get("error") or "scaffold failed"
            summary = f"daily forge failed: {err}"
            append_inbox(InboxEvent(
                agent="forge", severity="alert", summary=summary, ref=full_rec
            ))
            notifier.push("Daily Forge failed", err[:200], priority=1)
        return {"status": run.get("status"), "rec": full_rec}

    except Exception as exc:
        log.exception("daily_forge_tick crashed")
        err = f"{type(exc).__name__}: {exc}"
        append_inbox(InboxEvent(
            agent="forge", severity="alert",
            summary=f"daily forge crashed: {err}", ref=rec_base,
        ))
        notifier.push("Daily Forge crashed", err[:200], priority=1)
        _append_daily_project({**rec_base, "status": "crashed", "error": err})
        return {"status": "crashed", "error": err}


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
