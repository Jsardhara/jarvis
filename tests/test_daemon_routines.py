"""Sentinel daemon routines — driven by injected providers + noop notifier."""
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
)
from jarvis.state import read_inbox
from jarvis.subsystems.aide import Aide
from jarvis.subsystems.chronos import Chronos
from jarvis.subsystems.ledger import AtlasClient, Ledger
from jarvis.subsystems.providers import MockCalendar, MockGmail
from jarvis.subsystems.sherlock import MockSearch, Sherlock


def _silent_atlas() -> AtlasClient:
    return AtlasClient("http://t", transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={})
    ))


def test_email_tick_writes_inbox_and_pushes_when_action():
    notifier = NoopNotifier()
    email_tick(Aide(MockGmail()), notifier)
    events = read_inbox()
    assert any(e.agent == "aide" for e in events)
    # Seed contains 1 action email → push should fire
    assert len(notifier.calls) == 1


def test_email_tick_no_push_when_no_action():
    # Empty inbox → no action emails
    notifier = NoopNotifier()
    aide = Aide(MockGmail(seed=[]))
    out = email_tick(aide, notifier)
    assert out["action_count"] == 0
    assert notifier.calls == []


def test_calendar_tick_records_events():
    notifier = NoopNotifier()
    out = calendar_tick(Chronos(MockCalendar()), notifier)
    assert "count" in out
    events = read_inbox()
    assert any(e.agent == "chronos" for e in events)


def test_atlas_tick_alerts_on_drawdown():
    """Real (non-mock) ATLAS reporting drawdown beyond threshold → alert."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"pnl_pct": -0.10}))
    led = Ledger(client=AtlasClient("http://t", transport=transport), allow_mock=False)
    notifier = NoopNotifier()
    out = atlas_tick(led, notifier, drawdown_alert_pct=DRAWDOWN_ALERT_PCT)
    assert out["severity"] == "alert"
    assert len(notifier.calls) == 1
    assert "drawdown" in notifier.calls[0][0].lower()


def test_atlas_tick_no_alert_for_mock_pnl():
    """Mock fallback should not trigger drawdown alerts even if pct looks bad."""
    led = Ledger(client=_silent_atlas(), allow_mock=True)
    notifier = NoopNotifier()
    out = atlas_tick(led, notifier, drawdown_alert_pct=DRAWDOWN_ALERT_PCT)
    assert out["severity"] == "info"
    assert notifier.calls == []


def test_news_tick_with_watchlist():
    notifier = NoopNotifier()
    out = news_tick(Sherlock(MockSearch()), ["BTC", "ETH"], notifier)
    assert out["hits"] == 2


def test_news_tick_skips_when_empty_watchlist():
    notifier = NoopNotifier()
    out = news_tick(Sherlock(MockSearch()), [], notifier)
    assert out["skipped"] is True


def test_morning_digest_pushes_summary():
    notifier = NoopNotifier()
    led = Ledger(client=_silent_atlas(), allow_mock=True)
    out = morning_digest(Aide(MockGmail()), Chronos(MockCalendar()), led, notifier)
    assert "body" in out
    assert len(notifier.calls) == 1
    assert "briefing" in notifier.calls[0][0].lower()
