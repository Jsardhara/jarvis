"""Tests for ``jarvis/daemon/atlas_decision.py`` — pure policy engine."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

from jarvis.daemon.atlas_decision import (
    AtlasSnapshot,
    Policy,
    decide,
)


def test_mock_snapshot_returns_single_noop():
    snap = AtlasSnapshot(pnl_pct=-0.10, is_mock=True)
    actions = decide(snap)
    assert len(actions) == 1
    assert actions[0].type == "noop"
    assert actions[0].reason == "mock_snapshot"


def test_drawdown_breach_triggers_pause_and_alert():
    snap = AtlasSnapshot(pnl_pct=-0.06, agent_states={"trader": "running"})
    actions = decide(snap, Policy(drawdown_pause_pct=-0.05))
    types = [a.type for a in actions]
    assert "pause_agent" in types
    assert "alert" in types
    pause = next(a for a in actions if a.type == "pause_agent")
    assert pause.agent_id == "trader"
    assert pause.priority == 2


def test_drawdown_no_double_pause_when_already_paused():
    """Trader already paused → only the alert fires, not another pause."""
    snap = AtlasSnapshot(pnl_pct=-0.08, agent_states={"trader": "paused"})
    actions = decide(snap, Policy(drawdown_pause_pct=-0.05))
    types = [a.type for a in actions]
    assert "pause_agent" not in types
    assert "alert" in types


def test_open_position_cap_pauses_oracle():
    snap = AtlasSnapshot(
        pnl_pct=0.0, open_positions_count=5, agent_states={"oracle": "running"}
    )
    actions = decide(snap, Policy(max_open_positions=5))
    pause = [a for a in actions if a.type == "pause_agent"]
    assert pause and pause[0].agent_id == "oracle"


def test_stale_heartbeat_emits_alert():
    now = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    stale = now - timedelta(seconds=600)
    snap = AtlasSnapshot(
        pnl_pct=0.0,
        agent_last_heartbeat={"sage": stale, "trader": now - timedelta(seconds=10)},
        now=now,
    )
    actions = decide(snap, Policy(stale_heartbeat_sec=300))
    alerts = [a for a in actions if a.type == "alert"]
    assert any(a.agent_id == "sage" for a in alerts)
    assert all(a.agent_id != "trader" for a in alerts)


def test_recovery_proposes_resume_when_pnl_back_above_threshold():
    snap = AtlasSnapshot(
        pnl_pct=0.01, agent_states={"trader": "paused"}
    )
    actions = decide(snap, Policy(drawdown_pause_pct=-0.05))
    types = [a.type for a in actions]
    assert "resume_agent" in types
    resume = next(a for a in actions if a.type == "resume_agent")
    assert resume.agent_id == "trader"


def test_no_actions_yields_single_noop():
    snap = AtlasSnapshot(pnl_pct=0.005, open_positions_count=2)
    actions = decide(snap)
    assert len(actions) == 1
    assert actions[0].type == "noop"
    assert actions[0].reason == "no_policy_match"


def test_policy_thresholds_are_configurable():
    snap = AtlasSnapshot(pnl_pct=-0.03, agent_states={"trader": "running"})
    # Default policy (-5%) — no breach.
    assert all(a.type != "pause_agent" for a in decide(snap, Policy()))
    # Tighter policy (-2%) — breach triggers pause.
    tight = decide(snap, Policy(drawdown_pause_pct=-0.02))
    assert any(a.type == "pause_agent" for a in tight)


def test_mock_snapshot_ignores_other_thresholds():
    """Even with a synthetic drawdown, mock data must NOT push real alerts."""
    snap = AtlasSnapshot(pnl_pct=-0.50, open_positions_count=99, is_mock=True)
    actions = decide(snap)
    assert len(actions) == 1
    assert actions[0].type == "noop"


def test_decision_action_immutable():
    """Frozen dataclass — defends against accidental in-place mutation."""
    import dataclasses

    snap = AtlasSnapshot(pnl_pct=-0.10)
    actions = decide(snap, Policy(drawdown_pause_pct=-0.05))
    for a in actions:
        assert dataclasses.is_dataclass(a)
        # frozen=True → reassigning a field raises FrozenInstanceError
        try:
            a.reason = "tampered"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            continue
        else:
            raise AssertionError("DecisionAction should be frozen")
