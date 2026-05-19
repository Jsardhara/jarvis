"""Tests for W4.1 persistent agency — goal store + sentinel agency_tick."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.apps.sentinel.notifier import NoopNotifier
from jarvis.apps.sentinel.routines import agency_tick
from jarvis.state import agency as agency_mod
from jarvis.state.agency import (
    cancel_goal,
    create_goal,
    get_goal,
    list_goals,
    render_active_goals_for_prompt,
    update_goal_check,
)


@pytest.fixture(autouse=True)
def _redirect_agency_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Pin the goals.jsonl path to a clean tmp file per test."""
    target = tmp_path / "goals.jsonl"
    monkeypatch.setattr(agency_mod, "_path", lambda: target)
    return target


def test_create_goal_returns_active() -> None:
    goal = create_goal(
        "Watch BTC for 5% delta",
        kind="watch_price",
        params={"ticker": "BTC", "delta_pct": 0.05},
    )
    assert goal.id
    assert goal.title == "Watch BTC for 5% delta"
    assert goal.kind == "watch_price"
    assert goal.status == "active"
    assert goal.check_count == 0
    assert goal.last_check is None
    assert goal.observations == []
    assert get_goal(goal.id) == goal


def test_list_goals_filters_by_status() -> None:
    a = create_goal("A", kind="periodic_check", params={})
    b = create_goal("B", kind="periodic_check", params={})
    # Complete goal b via update.
    update_goal_check(b.id, "done", status="completed")
    active = list_goals(status="active")
    completed = list_goals(status="completed")
    assert any(g.id == a.id for g in active)
    assert not any(g.id == b.id for g in active)
    assert any(g.id == b.id for g in completed)


def test_update_goal_check_appends_observation() -> None:
    goal = create_goal("Tick me", kind="periodic_check", params={})
    bumped = update_goal_check(goal.id, "observation 1")
    assert bumped is not None
    assert bumped.observations == ["observation 1"]
    assert bumped.check_count == 1
    assert bumped.last_check is not None

    bumped = update_goal_check(goal.id, "observation 2")
    assert bumped is not None
    assert bumped.observations == ["observation 1", "observation 2"]
    assert bumped.check_count == 2


def test_update_goal_check_caps_observations_at_50() -> None:
    goal = create_goal("Cap test", kind="periodic_check", params={})
    latest = None
    for i in range(60):
        latest = update_goal_check(goal.id, f"obs-{i}")
    assert latest is not None
    assert len(latest.observations) == 50
    # Newest entries retained; oldest dropped.
    assert latest.observations[0] == "obs-10"
    assert latest.observations[-1] == "obs-59"


def test_deadline_auto_completion() -> None:
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    goal = create_goal(
        "Watch BTC briefly",
        kind="watch_price",
        params={"ticker": "BTC", "delta_pct": 0.05},
        deadline=past,
    )
    notifier = NoopNotifier()
    result = agency_tick(reg=None, notifier=notifier)
    assert goal.id in result["completed"]
    fresh = get_goal(goal.id)
    assert fresh is not None
    assert fresh.status == "completed"
    assert fresh.result is not None
    assert fresh.result.get("reason") == "deadline_reached"
    assert any("goal complete" in c[0] for c in notifier.calls)


def test_max_checks_auto_fail() -> None:
    goal = create_goal(
        "Stop after one",
        kind="periodic_check",
        params={},
        max_checks=1,
    )
    notifier = NoopNotifier()
    # First tick: handler runs and bumps check_count to 1.
    first = agency_tick(reg=None, notifier=notifier)
    assert goal.id not in first["failed"]
    # Second tick: check_count(1) >= max_checks(1) → fail before handler.
    second = agency_tick(reg=None, notifier=notifier)
    assert goal.id in second["failed"]
    fresh = get_goal(goal.id)
    assert fresh is not None
    assert fresh.status == "failed"


def test_render_active_goals_for_prompt_empty() -> None:
    assert render_active_goals_for_prompt() == ""


def test_render_active_goals_for_prompt_with_data() -> None:
    create_goal("Watch BTC", kind="watch_price", params={"ticker": "BTC"})
    create_goal("Watch inbox for Patel", kind="watch_mail",
                params={"sender": "patel@example.com"})
    rendered = render_active_goals_for_prompt()
    assert rendered.startswith("Active goals:")
    assert "Watch BTC" in rendered
    assert "watch_price" in rendered
    assert "Watch inbox for Patel" in rendered
    assert "watch_mail" in rendered


def test_cancel_goal() -> None:
    goal = create_goal("Nope", kind="periodic_check", params={})
    cancelled = cancel_goal(goal.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    fresh = get_goal(goal.id)
    assert fresh is not None
    assert fresh.status == "cancelled"
    assert not any(g.id == goal.id for g in list_goals(status="active"))


def test_periodic_check_increments_via_tick() -> None:
    """periodic_check kind logs 'still watching' each tick."""
    goal = create_goal("Periodic", kind="periodic_check", params={})
    notifier = NoopNotifier()
    agency_tick(reg=None, notifier=notifier)
    fresh = get_goal(goal.id)
    assert fresh is not None
    assert fresh.status == "active"
    assert fresh.check_count == 1
    assert "still watching" in fresh.observations[-1]


def test_watch_price_baseline_then_completion() -> None:
    """First tick anchors baseline, second crosses threshold → completed."""

    class _FakeAtlas:
        def __init__(self) -> None:
            self.calls = 0

        def positions(self):
            self.calls += 1
            price = 100.0 if self.calls == 1 else 110.0  # +10% on 2nd read

            class _Resp:
                def __init__(self, p: float) -> None:
                    self.result = {
                        "positions": [{"symbol": "BTC", "price": p}],
                        "count": 1,
                    }

            return _Resp(price)

    class _Desc:
        def __init__(self, inst):  # noqa: ANN001 — test stub
            self.instance = inst

    fake = _FakeAtlas()
    reg = {"atlas": _Desc(fake)}
    notifier = NoopNotifier()
    goal = create_goal(
        "Watch BTC 5%",
        kind="watch_price",
        params={"ticker": "BTC", "delta_pct": 0.05},
    )
    # First tick: anchors baseline.
    agency_tick(reg=reg, notifier=notifier)
    mid = get_goal(goal.id)
    assert mid is not None
    assert mid.status == "active"
    assert mid.result is not None
    assert mid.result.get("baseline") == 100.0
    # Second tick: 10% jump → completed.
    out = agency_tick(reg=reg, notifier=notifier)
    assert goal.id in out["completed"]
    final = get_goal(goal.id)
    assert final is not None
    assert final.status == "completed"
    assert final.result is not None
    assert final.result.get("delta_pct") == pytest.approx(0.10)


def test_handler_exception_does_not_crash_tick() -> None:
    """A bad goal kind logs a 'failed' but other goals still advance."""
    bad = create_goal("Bad kind", kind="not_a_real_kind", params={})
    good = create_goal("Good", kind="periodic_check", params={})
    notifier = NoopNotifier()
    out = agency_tick(reg=None, notifier=notifier)
    assert bad.id in out["failed"]
    good_fresh = get_goal(good.id)
    assert good_fresh is not None
    assert good_fresh.check_count == 1
    assert good_fresh.status == "active"
