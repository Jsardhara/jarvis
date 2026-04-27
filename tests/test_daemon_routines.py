"""Sentinel daemon routines — driven by injected agents + noop notifier."""
from __future__ import annotations

import httpx

from jarvis.daemon.notifier import NoopNotifier
from jarvis.daemon.routines import (
    DRAWDOWN_ALERT_PCT,
    atlas_tick,
    calendar_tick,
    email_tick,
    morning_digest,
    news_tick,
    scholar_tick,
)
from jarvis.state import read_inbox
from jarvis.subsystems.atlas import AtlasBridge, AtlasOrchestrator
from jarvis.subsystems.lens import Lens
from jarvis.subsystems.providers import MockOutlook, MockSearch
from jarvis.subsystems.scholar import Scholar
from jarvis.subsystems.tempo import Tempo


def _silent_atlas() -> AtlasBridge:
    return AtlasBridge("http://t", transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={})
    ))


def test_email_tick_writes_inbox_and_pushes_when_action():
    # Inject one explicit action email so the tick has something to push
    seed = [{
        "id": "m99", "from": "boss@x.com", "subject": "Action required",
        "snippet": "Please review and approve ASAP", "labels": ["UNREAD", "INBOX", "IMPORTANT"],
    }]
    notifier = NoopNotifier()
    email_tick(Tempo(MockOutlook(seed_mail=seed)), notifier)
    events = read_inbox()
    assert any(e.agent == "tempo" for e in events)
    assert len(notifier.calls) == 1


def test_email_tick_no_push_when_no_action():
    notifier = NoopNotifier()
    tempo = Tempo(MockOutlook(seed_mail=[]))
    out = email_tick(tempo, notifier)
    assert out["action_count"] == 0
    assert notifier.calls == []


def test_calendar_tick_records_events():
    notifier = NoopNotifier()
    out = calendar_tick(Tempo(MockOutlook()), notifier)
    assert "count" in out
    events = read_inbox()
    assert any(e.agent == "tempo" for e in events)


def test_atlas_tick_alerts_on_drawdown():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"pnl_pct": -0.10}))
    atlas = AtlasOrchestrator(bridge=AtlasBridge("http://t", transport=transport),
                              allow_mock=False)
    notifier = NoopNotifier()
    out = atlas_tick(atlas, notifier, drawdown_alert_pct=DRAWDOWN_ALERT_PCT)
    assert out["severity"] == "alert"
    assert len(notifier.calls) == 1
    assert "drawdown" in notifier.calls[0][0].lower()


def test_atlas_tick_no_alert_for_mock_pnl():
    atlas = AtlasOrchestrator(bridge=_silent_atlas(), allow_mock=True)
    notifier = NoopNotifier()
    out = atlas_tick(atlas, notifier, drawdown_alert_pct=DRAWDOWN_ALERT_PCT)
    assert out["severity"] == "info"
    assert notifier.calls == []


def test_news_tick_with_watchlist():
    notifier = NoopNotifier()
    out = news_tick(Lens(MockSearch()), ["BTC", "ETH"], notifier)
    assert out["hits"] == 6  # 3 results × 2 terms


def test_news_tick_skips_when_empty_watchlist():
    notifier = NoopNotifier()
    out = news_tick(Lens(MockSearch()), [], notifier)
    assert out["skipped"] is True


def test_scholar_tick_records_count():
    notifier = NoopNotifier()
    out = scholar_tick(Scholar(), notifier)
    assert "count" in out
    events = read_inbox()
    assert any(e.agent == "scholar" for e in events)


def test_morning_digest_pushes_summary():
    notifier = NoopNotifier()
    atlas = AtlasOrchestrator(bridge=_silent_atlas(), allow_mock=True)
    out = morning_digest(Tempo(MockOutlook()), atlas, Scholar(), notifier)
    assert "body" in out
    assert len(notifier.calls) == 1
    assert "briefing" in notifier.calls[0][0].lower()


# --- heartbeat_tick tests ---

def test_heartbeat_tick_writes_inbox():
    from apscheduler.schedulers.background import BackgroundScheduler

    from jarvis.daemon.routines import heartbeat_tick
    from jarvis.daemon.sentinel import build_scheduler

    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    notifier = NoopNotifier()
    out = heartbeat_tick(sched, notifier)

    events = read_inbox()
    heartbeat_events = [e for e in events if e.agent == "sentinel" and e.summary == "heartbeat"]
    assert heartbeat_events, "expected a heartbeat InboxEvent from sentinel"
    assert "jobs" in heartbeat_events[-1].ref
    assert notifier.calls == [], "heartbeat should not push a notification"
    assert "job_count" in out


def test_heartbeat_tick_ref_contains_known_job_ids():
    from apscheduler.schedulers.background import BackgroundScheduler

    from jarvis.daemon.routines import heartbeat_tick
    from jarvis.daemon.sentinel import build_scheduler

    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    heartbeat_tick(sched, NoopNotifier())

    events = read_inbox()
    ref = next(e.ref for e in reversed(events) if e.summary == "heartbeat")
    job_ids = set(ref["jobs"].keys())
    assert {"email", "atlas", "news"} <= job_ids


# --- inspect_agent_log tests ---

def test_inspect_agent_log_returns_entries():
    from jarvis.contract import AgentLogEntry
    from jarvis.daemon.routines import inspect_agent_log
    from jarvis.state import append_agent_log

    append_agent_log(AgentLogEntry(request_id="r1", agent="tempo", action="triage", status="ok"))
    append_agent_log(AgentLogEntry(request_id="r2", agent="atlas", action="pnl", status="ok"))

    entries = inspect_agent_log()
    assert len(entries) >= 2
    keys = set(entries[0].keys())
    assert {"agent", "action", "status"} <= keys


def test_inspect_agent_log_filters_by_agent():
    from jarvis.contract import AgentLogEntry
    from jarvis.daemon.routines import inspect_agent_log
    from jarvis.state import append_agent_log

    append_agent_log(AgentLogEntry(request_id="r3", agent="tempo", action="triage", status="ok"))
    append_agent_log(AgentLogEntry(request_id="r4", agent="atlas", action="pnl", status="ok"))

    entries = inspect_agent_log(agent="tempo")
    assert all(e["agent"] == "tempo" for e in entries)
