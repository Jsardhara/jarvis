"""Cron routines — pure functions, easily testable.

Each routine takes injected providers + notifier, runs one tick, writes
inbox events, pushes alerts. Schedules wired in sentinel.py.
"""
from __future__ import annotations

import logging
from typing import Any

from ..contract import InboxEvent
from ..state import append_inbox
from ..subsystems.aide import TIER_ACTION, Aide
from ..subsystems.chronos import Chronos
from ..subsystems.ledger import Ledger
from ..subsystems.sherlock import Sherlock
from .notifier import Notifier

log = logging.getLogger(__name__)

# Default thresholds — overridden via env or config
DRAWDOWN_ALERT_PCT = -0.05  # alert if window pnl < -5%


def email_tick(aide: Aide, notifier: Notifier) -> dict[str, Any]:
    resp = aide.triage()
    counts = resp.result["counts"]
    action_count = counts.get(TIER_ACTION, 0)
    severity = "alert" if action_count >= 3 else ("warn" if action_count else "info")
    summary = f"{action_count} action emails, {counts.get('meeting_info', 0)} meetings"
    append_inbox(InboxEvent(agent="aide", severity=severity, summary=summary,
                            ref={"counts": counts}))
    if action_count > 0:
        notifier.push("Aide — inbox", summary, priority=1 if action_count >= 3 else 0)
    return {"action_count": action_count, "severity": severity}


def calendar_tick(chronos: Chronos, notifier: Notifier) -> dict[str, Any]:
    resp = chronos.today()
    count = resp.result["count"]
    severity = "info"
    summary = f"{count} events today"
    append_inbox(InboxEvent(agent="chronos", severity=severity, summary=summary,
                            ref={"events": resp.result["events"]}))
    return {"count": count}


def atlas_tick(ledger: Ledger, notifier: Notifier,
               drawdown_alert_pct: float = DRAWDOWN_ALERT_PCT) -> dict[str, Any]:
    pnl_resp = ledger.pnl(window="1d")
    pnl_pct = pnl_resp.result["pnl"].get("pnl_pct", 0)
    is_mock = pnl_resp.result.get("mock", False)
    if pnl_pct <= drawdown_alert_pct and not is_mock:
        severity = "alert"
        summary = f"ATLAS drawdown: {pnl_pct:.2%}"
        notifier.push("Ledger — drawdown alert", summary, priority=2)
    else:
        severity = "info"
        summary = f"ATLAS 1d pnl: {pnl_pct:.2%}{' (mock)' if is_mock else ''}"
    append_inbox(InboxEvent(agent="ledger", severity=severity, summary=summary,
                            ref={"pnl_pct": pnl_pct, "mock": is_mock}))
    return {"pnl_pct": pnl_pct, "severity": severity}


def news_tick(sherlock: Sherlock, watchlist: list[str], notifier: Notifier) -> dict[str, Any]:
    if not watchlist:
        return {"skipped": True}
    hits = []
    for ticker in watchlist:
        resp = sherlock.quick_search(f"{ticker} news today", num_results=3)
        if resp.result["count"]:
            hits.append({"ticker": ticker, "top": resp.result["results"][0]})
    summary = f"news: {len(hits)} hits across {len(watchlist)} tickers"
    append_inbox(InboxEvent(agent="sherlock", severity="info", summary=summary,
                            ref={"hits": hits}))
    return {"hits": len(hits)}


def morning_digest(aide: Aide, chronos: Chronos, ledger: Ledger,
                   notifier: Notifier) -> dict[str, Any]:
    em = aide.triage()
    cal = chronos.today()
    pnl = ledger.pnl()
    parts = [
        f"Inbox: {em.result['counts'].get(TIER_ACTION, 0)} action",
        f"Calendar: {cal.result['count']} events",
        f"PnL 1d: {pnl.result['pnl'].get('pnl_pct', 0):.2%}",
    ]
    body = " | ".join(parts)
    append_inbox(InboxEvent(agent="sentinel", severity="info", summary="morning digest",
                            ref={"body": body}))
    notifier.push("Morning briefing", body, priority=0)
    return {"body": body}
