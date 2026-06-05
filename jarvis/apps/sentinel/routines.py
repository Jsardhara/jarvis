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

from jarvis.agents.atlas.agent import AtlasOrchestrator, AtlasUnavailableError
from jarvis.agents.lens.agent import Lens
from jarvis.agents.scholar.agent import Scholar
from jarvis.agents.tempo.agent import TIER_ACTION, Tempo
from jarvis.config import get_settings
from jarvis.contract import InboxEvent, SentinelHealthEvent
from jarvis.state import append_inbox, append_sentinel_health, read_agent_log, read_inbox
from jarvis.state.agency import (
    Goal,
    list_goals,
    update_goal_check,
)
from jarvis.state.memory import append_daily, remember_session

from .atlas_decision import AtlasSnapshot, DecisionAction, Policy, decide
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


def draft_replies_tick(tempo: Tempo, notifier: Notifier) -> dict[str, Any]:
    """Nightly: draft replies for action-required mail (J9).

    Calls ``tempo.draft_replies(limit=5)``, which scans recent unread mail,
    classifies via ``classify_message``, and persists candidate drafts to
    ``state/drafted_replies.jsonl`` with status="drafted". The operator
    reviews/approves in the morning; sending still requires confirmation
    via ``tempo.send_mail`` per the Jarvis authority matrix.
    """
    resp = tempo.draft_replies(limit=5)
    count = int(resp.result.get("count", 0))
    draft_ids = list(resp.result.get("draft_ids", []))
    if count > 0:
        summary = f"Drafted {count} reply candidates overnight"
        append_inbox(
            InboxEvent(
                agent="tempo",
                severity="info",
                summary=summary,
                ref={"draft_ids": draft_ids},
            )
        )
        notifier.push("Tempo - drafts ready", summary, priority=0)
    return {"count": count, "draft_ids": draft_ids}


def calendar_tick(tempo: Tempo, notifier: Notifier) -> dict[str, Any]:
    resp = tempo.today()
    count = resp.result["count"]
    summary = f"{count} events today"
    append_inbox(InboxEvent(agent="tempo", severity="info", summary=summary,
                            ref={"events": resp.result["events"]}))
    return {"count": count}


def _build_atlas_snapshot(atlas: AtlasOrchestrator) -> AtlasSnapshot:
    """Pull live ATLAS state into a snapshot the decision engine can consume."""
    pnl_resp = atlas.pnl(window="1d")
    pnl_data = pnl_resp.result.get("pnl", {})
    pnl_pct = float(pnl_data.get("pnl_pct", 0) or 0)
    is_mock = bool(pnl_resp.result.get("mock", False))

    positions_count = 0
    try:
        pos_resp = atlas.positions()
        positions_count = int(pos_resp.result.get("count", 0) or 0)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        log.warning("atlas snapshot positions failed: %s", exc)

    agent_states: dict[str, str] = {}
    agent_last_hb: dict[str, datetime | None] = {}
    if not is_mock:
        try:
            state_resp = atlas.agent_state()
            for entry in state_resp.result.get("agents", []):
                aid = entry.get("id")
                if not aid:
                    continue
                agent_states[aid] = str(entry.get("state") or "")
                hb_raw = entry.get("last_heartbeat")
                hb: datetime | None = None
                if isinstance(hb_raw, str) and hb_raw:
                    try:
                        hb = datetime.fromisoformat(hb_raw.replace("Z", "+00:00"))
                    except ValueError:
                        hb = None
                agent_last_hb[aid] = hb
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            log.warning("atlas snapshot agent_state failed: %s", exc)

    return AtlasSnapshot(
        pnl_pct=pnl_pct,
        open_positions_count=positions_count,
        agent_states=agent_states,
        agent_last_heartbeat=agent_last_hb,
        is_mock=is_mock,
    )


def _execute_atlas_action(
    atlas: AtlasOrchestrator,
    notifier: Notifier,
    action: DecisionAction,
) -> str:
    """Run one decision action. Returns a short status string for inbox."""
    if action.type == "noop":
        return f"noop: {action.reason}"
    if action.type == "alert":
        title = f"Atlas — {action.agent_id or 'system'}"
        notifier.push(title, action.reason, priority=action.priority)
        return f"alert: {action.reason}"
    if action.type == "pause_agent" and action.agent_id:
        try:
            atlas.pause_agent(action.agent_id)
        except AtlasUnavailableError as exc:
            log.warning("pause_agent(%s) failed: %s", action.agent_id, exc)
            return f"pause_failed: {action.agent_id}"
        if action.priority >= 2:
            notifier.push(
                f"Atlas — paused {action.agent_id}",
                action.reason,
                priority=action.priority,
            )
        return f"paused: {action.agent_id} ({action.reason})"
    if action.type == "resume_agent" and action.agent_id:
        try:
            atlas.resume_agent(action.agent_id)
        except AtlasUnavailableError as exc:
            log.warning("resume_agent(%s) failed: %s", action.agent_id, exc)
            return f"resume_failed: {action.agent_id}"
        return f"resumed: {action.agent_id} ({action.reason})"
    if action.type == "oracle_scan":
        try:
            atlas.trigger_oracle_scan(reason=action.reason)
        except AtlasUnavailableError as exc:
            log.warning("trigger_oracle_scan failed: %s", exc)
            return f"scan_failed: {action.reason}"
        return f"scan_triggered: {action.reason}"
    return f"unknown_action: {action.type}"


def atlas_tick(
    atlas: AtlasOrchestrator,
    notifier: Notifier,
    drawdown_alert_pct: float = DRAWDOWN_ALERT_PCT,
    policy: Policy | None = None,
) -> dict[str, Any]:
    """Decision-layer tick.

    Pulls a state snapshot, runs the policy engine, executes each
    recommended action (pause/resume/scan/alert), and writes one inbox
    event per cycle summarizing the outcome.
    """
    pol = policy or Policy(
        drawdown_pause_pct=drawdown_alert_pct,
        drawdown_alert_pct=drawdown_alert_pct,
    )
    snapshot = _build_atlas_snapshot(atlas)
    actions = decide(snapshot, pol)
    statuses = [_execute_atlas_action(atlas, notifier, a) for a in actions]

    severity = "info"
    if any(a.severity == "crit" for a in actions):
        severity = "crit"
    elif any(a.severity == "alert" for a in actions):
        severity = "alert"
    elif any(a.severity == "warn" for a in actions):
        severity = "warn"

    summary = (
        f"ATLAS pnl={snapshot.pnl_pct:+.2%} pos={snapshot.open_positions_count} "
        f"actions={len(actions)}"
    )
    if snapshot.is_mock:
        summary += " (mock)"

    append_inbox(
        InboxEvent(
            agent="atlas",
            severity=severity,
            summary=summary,
            ref={
                "pnl_pct": snapshot.pnl_pct,
                "open_positions": snapshot.open_positions_count,
                "agent_states": snapshot.agent_states,
                "actions": [
                    {"type": a.type, "agent_id": a.agent_id, "reason": a.reason}
                    for a in actions
                ],
                "statuses": statuses,
                "mock": snapshot.is_mock,
            },
        )
    )
    return {
        "pnl_pct": snapshot.pnl_pct,
        "severity": severity,
        "actions": [a.type for a in actions],
        "statuses": statuses,
    }


def atlas_daily_rollup(
    atlas: AtlasOrchestrator,
    notifier: Notifier,
) -> dict[str, Any]:
    """End-of-day ATLAS digest. Push priority matches what happened today.

    Aggregates the day's atlas inbox events and emits one rollup notification:

      priority=2  if any "alert" tier event landed today (drawdown, pause)
      priority=1  if only "warn" tier events landed (stale heartbeats, caps)
      priority=0  pure info day (default — quiet rollup)

    The rollup never re-fires the original alerts; those went out as they
    happened. This is a once-per-day "here's what ATLAS did" line.
    """
    # Read today's atlas-tagged inbox events. read_inbox tails the file so
    # we look at the last 500 lines and filter — cheap.

    today = datetime.now(UTC).date()
    events = read_inbox(limit=500)
    today_atlas = [
        e for e in events
        if e.agent == "atlas"
        and getattr(e, "ts", None)
        and _ts_date(e.ts) == today
    ]

    severities = {e.severity for e in today_atlas}
    counts = {
        "alert": sum(1 for e in today_atlas if e.severity == "alert"),
        "warn": sum(1 for e in today_atlas if e.severity == "warn"),
        "info": sum(1 for e in today_atlas if e.severity == "info"),
    }
    action_total = 0
    pnl_pct_last: float | None = None
    pos_last: int | None = None
    for e in today_atlas:
        ref = getattr(e, "ref", {}) or {}
        action_total += len(ref.get("actions", []) or [])
        if "pnl_pct" in ref:
            pnl_pct_last = float(ref.get("pnl_pct") or 0.0)
        if "open_positions" in ref:
            pos_last = int(ref.get("open_positions") or 0)

    if "alert" in severities:
        priority = 2
        title = "Atlas — daily rollup (ALERT)"
    elif "warn" in severities:
        priority = 1
        title = "Atlas — daily rollup (warn)"
    else:
        priority = 0
        title = "Atlas — daily rollup"

    summary_parts = [
        f"events={len(today_atlas)}",
        f"alert={counts['alert']}",
        f"warn={counts['warn']}",
        f"actions={action_total}",
    ]
    if pnl_pct_last is not None:
        summary_parts.append(f"pnl={pnl_pct_last:+.2%}")
    if pos_last is not None:
        summary_parts.append(f"pos={pos_last}")
    summary = " ".join(summary_parts)

    notifier.push(title, summary, priority=priority)
    append_inbox(
        InboxEvent(
            agent="atlas",
            severity="info",
            summary=f"daily rollup: {summary}",
            ref={
                "rollup": True,
                "counts": counts,
                "pnl_pct": pnl_pct_last,
                "open_positions": pos_last,
                "actions_total": action_total,
                "priority": priority,
            },
        )
    )
    return {
        "priority": priority,
        "events": len(today_atlas),
        "counts": counts,
        "actions_total": action_total,
    }


def _ts_date(ts: Any) -> Any:
    """Coerce an InboxEvent timestamp (str or datetime) to a date object."""
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


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


def proactive_intelligence_tick(notifier: Notifier) -> dict[str, Any]:
    """Daily: LLM scans recent activity, emits non-obvious observations."""
    from .proactive_intelligence import run_proactive_pass

    events = run_proactive_pass()
    summaries: list[str] = []
    for event in events:
        summaries.append(event.summary)
        notifier.push("Jarvis — observed", event.summary, priority=0)
    return {"observation_count": len(events), "summaries": summaries}


def morning_digest(reg: dict[str, Any], notifier: Notifier) -> dict[str, Any]:
    """Build and push the smart morning briefing, replacing the old static stub."""
    from jarvis.state.briefing import build_briefing

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
    from jarvis.agents.atlas import budget

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
                agent="forge", severity="crit", summary=f"daily forge pick failed: {err}",
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
                agent="forge", severity="crit", summary=summary, ref=full_rec
            ))
            notifier.push("Daily Forge failed", err[:200], priority=1)
        return {"status": run.get("status"), "rec": full_rec}

    except Exception as exc:
        log.exception("daily_forge_tick crashed")
        err = f"{type(exc).__name__}: {exc}"
        append_inbox(InboxEvent(
            agent="forge", severity="crit",
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


# ---------------------------------------------------------------------------
# W4.1 — Persistent agency: long-running goals advanced by sentinel each tick
# ---------------------------------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _agency_watch_price(
    goal: Goal,
    reg: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Read latest atlas snapshot; complete when delta crosses threshold.

    Returns ``(observation, result_or_None, status_or_None)``. The handler is
    intentionally tolerant: a missing ticker quote yields a "no quote" obs
    rather than a hard error. The baseline is anchored on first observation
    and stored on the goal's ``result`` field; subsequent ticks compare the
    fresh price against that anchor.
    """
    ticker = str(goal.params.get("ticker", "")).upper()
    delta_pct = float(goal.params.get("delta_pct", 0.05) or 0.05)
    prior = goal.result or {}
    baseline = prior.get("baseline") if isinstance(prior, dict) else None
    if not ticker:
        return ("watch_price: missing ticker param", None, "failed")
    if reg is None:
        return (f"watch_price: no registry; ticker={ticker}", None, None)
    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return (f"watch_price: atlas unavailable; ticker={ticker}", None, None)

    try:
        atlas = getattr(atlas_desc, "instance", atlas_desc)
        price: float | None = None
        try:
            pos_resp = atlas.positions()
            for row in pos_resp.result.get("positions", []) or []:
                sym = str(row.get("symbol") or row.get("ticker") or "").upper()
                if sym == ticker:
                    raw_price = row.get("price") or row.get("mark") or row.get("last")
                    if raw_price is not None:
                        price = float(raw_price)
                        break
        except Exception as exc:  # noqa: BLE001 — degrade
            log.debug("watch_price positions read failed: %s", exc)
        if price is None:
            return (f"watch_price: no quote for {ticker}", None, None)
    except Exception as exc:  # noqa: BLE001 — degrade
        return (f"watch_price: error {type(exc).__name__}", None, None)

    if baseline is None:
        return (
            f"watch_price: baseline set @ {price:.4f} for {ticker}",
            {"baseline": price, "ticker": ticker, "last_price": price},
            None,
        )

    try:
        base = float(baseline)
    except (TypeError, ValueError):
        return (f"watch_price: bad baseline {baseline!r}", None, "failed")
    if base == 0:
        return ("watch_price: baseline zero", None, "failed")
    change = (price - base) / base
    obs = f"watch_price: {ticker} {price:.4f} ({change:+.2%}) vs {base:.4f}"
    if abs(change) >= delta_pct:
        result = {
            "ticker": ticker,
            "baseline": base,
            "price": price,
            "delta_pct": change,
            "threshold": delta_pct,
        }
        return (obs + " — threshold crossed", result, "completed")
    # Track last price without changing baseline.
    return (
        obs,
        {"baseline": base, "ticker": ticker, "last_price": price},
        None,
    )


def _agency_watch_mail(
    goal: Goal,
    reg: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Scan recent inbox events for a sender; complete on first match."""
    sender = str(goal.params.get("sender", "")).lower()
    if not sender:
        return ("watch_mail: missing sender param", None, "failed")

    # Look at recent inbox events for a tempo triage with a hit on sender.
    # We avoid hitting the live mail API every tick — the tempo email_tick
    # already pulls action items and writes them to the inbox feed.
    try:
        events = read_inbox(limit=200)
    except Exception as exc:  # noqa: BLE001 — degrade
        return (f"watch_mail: inbox read failed {exc}", None, None)
    for ev in events:
        if ev.agent != "tempo":
            continue
        ref = ev.ref or {}
        # action items list of dicts with 'from' or 'sender' keys
        for key in ("action_items", "messages", "items", "hits"):
            for msg in ref.get(key, []) or []:
                from_field = str(
                    msg.get("from") or msg.get("sender") or ""
                ).lower()
                if sender in from_field:
                    result = {
                        "sender": sender,
                        "matched_from": from_field,
                        "subject": msg.get("subject", ""),
                        "msg_id": msg.get("id"),
                    }
                    return (
                        f"watch_mail: matched sender '{sender}'",
                        result,
                        "completed",
                    )
    return (f"watch_mail: no match yet for '{sender}'", None, None)


def _agency_periodic_check(
    goal: Goal,
    reg: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    return (f"periodic: still watching '{goal.title}'", None, None)


def _agency_freeform(
    goal: Goal,
    reg: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    return (f"freeform: noted '{goal.title}'", None, None)


_AGENCY_HANDLERS = {
    "watch_price": _agency_watch_price,
    "watch_mail": _agency_watch_mail,
    "periodic_check": _agency_periodic_check,
    "freeform": _agency_freeform,
}


def agency_tick(
    reg: dict[str, Any] | None,
    notifier: Notifier,
) -> dict[str, Any]:
    """Advance each active goal one step.

    For every goal returned by ``list_goals(status="active")``:
      * Deadline reached → mark "completed" with a deadline result.
      * check_count >= max_checks → mark "failed" with overflow result.
      * Otherwise dispatch to the handler matching ``goal.kind``. The
        handler returns (observation, optional_result, optional_new_status).
    Each handler is wrapped in try/except so one bad goal cannot crash the
    tick. A priority-1 push is emitted for every goal that transitions to
    "completed" or "failed" on this tick.
    """
    active = list_goals(status="active")
    now = datetime.now(UTC)
    completed: list[str] = []
    failed: list[str] = []

    for goal in active:
        try:
            deadline = _parse_iso(goal.deadline)
            if deadline is not None and now >= deadline:
                updated = update_goal_check(
                    goal.id,
                    "deadline reached",
                    result={"reason": "deadline_reached", "deadline": goal.deadline},
                    status="completed",
                )
                if updated is not None:
                    completed.append(updated.id)
                    notifier.push(
                        f"Jarvis — goal complete: {goal.title}",
                        "Deadline reached",
                        priority=1,
                    )
                continue

            if goal.check_count >= goal.max_checks:
                updated = update_goal_check(
                    goal.id,
                    "max checks reached",
                    result={"reason": "max_checks_reached", "max_checks": goal.max_checks},
                    status="failed",
                )
                if updated is not None:
                    failed.append(updated.id)
                    notifier.push(
                        f"Jarvis — goal failed: {goal.title}",
                        f"Hit max_checks ({goal.max_checks})",
                        priority=1,
                    )
                continue

            handler = _AGENCY_HANDLERS.get(goal.kind)
            if handler is None:
                update_goal_check(
                    goal.id,
                    f"unknown kind '{goal.kind}'",
                    status="failed",
                )
                failed.append(goal.id)
                notifier.push(
                    f"Jarvis — goal failed: {goal.title}",
                    f"Unknown goal kind: {goal.kind}",
                    priority=1,
                )
                continue

            try:
                observation, result, new_status = handler(goal, reg)
            except Exception as exc:  # noqa: BLE001 — never crash the tick
                log.warning(
                    "agency_tick handler %s raised on goal %s",
                    goal.kind, goal.id, exc_info=True,
                )
                observation = f"handler error: {type(exc).__name__}: {exc}"
                result = None
                new_status = None

            updated = update_goal_check(
                goal.id,
                observation,
                result=result,
                status=new_status,
            )
            if updated is None:
                continue
            if new_status == "completed":
                completed.append(updated.id)
                notifier.push(
                    f"Jarvis — goal complete: {goal.title}",
                    observation,
                    priority=1,
                )
            elif new_status == "failed":
                failed.append(updated.id)
                notifier.push(
                    f"Jarvis — goal failed: {goal.title}",
                    observation,
                    priority=1,
                )
        except Exception:  # noqa: BLE001 — outer guard, never crash tick
            log.warning("agency_tick: goal %s crashed loop", goal.id, exc_info=True)

    return {
        "active_count": len(active),
        "completed": completed,
        "failed": failed,
    }



def training_extract_tick(notifier: Notifier) -> dict[str, Any]:
    """Nightly: refresh training datasets under ``state/training/``.

    Calls :func:`jarvis.training.extract.extract_all` which appends new
    ShareGPT-format examples from ``chat_turns.jsonl`` (orchestrator
    persona) and approved/sent ``drafted_replies.jsonl`` (email voice).
    Idempotent -- re-running over the same source produces no duplicates.

    Pushes a notification only when fresh examples land, so quiet days
    don't spam the inbox. By the time the local PC arrives, months of
    personalised data are ready for Unsloth / Axolotl LoRA fine-tunes.
    """
    from jarvis.training import extract

    results = extract.extract_all()
    written_by_source = {r.source: r.written for r in results}
    total_written = sum(written_by_source.values())

    if total_written > 0:
        summary = ", ".join(
            f"{src}: {count}" for src, count in written_by_source.items() if count
        )
        notifier.push(
            "Training data refreshed",
            f"{total_written} new examples ({summary})",
            priority=0,
        )

    return {
        "total_written": total_written,
        "by_source": written_by_source,
        "targets": [str(r.target) for r in results],
    }
