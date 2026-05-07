"""Tests for ``atlas_daily_rollup`` — Phase 4 reporting matrix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from jarvis.contract import InboxEvent
from jarvis.daemon import routines
from jarvis.daemon.notifier import NoopNotifier
from jarvis.daemon.routines import atlas_daily_rollup
from jarvis.subsystems.atlas import AtlasBridge, AtlasOrchestrator


def _silent_atlas() -> AtlasBridge:
    return AtlasBridge(
        "http://t",
        transport=httpx.MockTransport(lambda r: httpx.Response(404, json={})),
    )


def _orch() -> AtlasOrchestrator:
    return AtlasOrchestrator(bridge=_silent_atlas(), allow_mock=True, mode="mock")


def _seed_inbox(monkeypatch: pytest.MonkeyPatch, events: list[InboxEvent]) -> None:
    monkeypatch.setattr(
        "jarvis.daemon.routines.read_inbox",
        lambda limit=500: events,
    )


def _ev(severity: str, ref: dict[str, Any] | None = None, *, today: bool = True) -> InboxEvent:
    ts = datetime.now(UTC) if today else datetime.now(UTC) - timedelta(days=2)
    return InboxEvent(
        agent="atlas",
        severity=severity,
        summary="x",
        ref=ref or {},
        ts=ts.isoformat(),
    )


def test_rollup_priority_2_when_any_alert_today(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [
            _ev("info", {"pnl_pct": 0.0, "actions": []}),
            _ev("alert", {"pnl_pct": -0.07, "actions": [{"type": "pause_agent"}]}),
        ],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["priority"] == 2
    assert out["counts"]["alert"] == 1
    assert any("ALERT" in title for title, *_ in notifier.calls)


def test_rollup_priority_1_when_only_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [
            _ev("info", {"pnl_pct": 0.005, "actions": []}),
            _ev("warn", {"pnl_pct": 0.0, "actions": [{"type": "alert"}]}),
        ],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["priority"] == 1


def test_rollup_priority_0_for_pure_info_day(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [
            _ev("info", {"pnl_pct": 0.012, "open_positions": 1, "actions": []}),
            _ev("info", {"pnl_pct": 0.013, "open_positions": 1, "actions": []}),
        ],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["priority"] == 0
    title, _body, *_ = notifier.calls[0]
    assert "ALERT" not in title and "warn" not in title


def test_rollup_ignores_yesterdays_events(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [
            _ev("alert", {"pnl_pct": -0.10, "actions": []}, today=False),
            _ev("info", {"pnl_pct": 0.0, "actions": []}, today=True),
        ],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["priority"] == 0  # yesterday's alert excluded
    assert out["events"] == 1


def test_rollup_aggregates_action_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [
            _ev("warn", {"actions": [{"type": "alert"}, {"type": "pause_agent"}]}),
            _ev("info", {"actions": [{"type": "noop"}]}),
        ],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["actions_total"] == 3


def test_rollup_pushes_exactly_once_per_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_inbox(monkeypatch, [_ev("info", {"actions": []})])
    notifier = NoopNotifier()
    atlas_daily_rollup(_orch(), notifier)
    assert len(notifier.calls) == 1


def test_rollup_handles_missing_ref_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_inbox(
        monkeypatch,
        [InboxEvent(agent="atlas", severity="info", summary="bare", ref={})],
    )
    notifier = NoopNotifier()
    out = atlas_daily_rollup(_orch(), notifier)
    assert out["priority"] == 0
    assert out["events"] == 1


def test_ts_date_handles_str_and_datetime() -> None:
    now = datetime.now(UTC)
    assert routines._ts_date(now) == now.date()
    assert routines._ts_date(now.isoformat()) == now.date()
    assert routines._ts_date("not-a-date") is None
    assert routines._ts_date(None) is None
