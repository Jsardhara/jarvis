"""ATLAS decision layer — pure-Python policy engine.

Sentinel calls :func:`decide` once per ``atlas_tick`` with a snapshot of the
current ATLAS state. The function returns a list of :class:`DecisionAction`
records. Each action is one of:

* ``pause_agent`` / ``resume_agent`` — mutate ATLAS agent state via the
  ``/control/*`` surface.
* ``oracle_scan`` — fire an ad-hoc Oracle scan outside the 15-min cycle.
* ``alert`` — push a Pushover notification (severity decides priority).
* ``noop`` — log the snapshot, no action.

Design constraints:

* No LLM calls — fully deterministic so every cycle is auditable.
* Pure function — same input → same output. Side effects happen in
  ``routines.atlas_tick`` after this returns.
* Safe defaults — when fields are missing or malformed, prefer ``noop``
  over a bad mutation.
* Live trades are NEVER auto-decided. Only paper-mode + read-only ops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

DecisionType = Literal[
    "pause_agent",
    "resume_agent",
    "oracle_scan",
    "alert",
    "noop",
]

# Default policy thresholds. Override via Sentinel config / env.
DEFAULT_DRAWDOWN_PAUSE_PCT: float = -0.05  # pause trader if 1d PnL ≤ -5%
DEFAULT_DRAWDOWN_ALERT_PCT: float = -0.05  # push alert at same threshold
DEFAULT_MAX_OPEN_POSITIONS: int = 5
DEFAULT_STALE_HEARTBEAT_SEC: int = 300  # 5 min


@dataclass(frozen=True)
class AtlasSnapshot:
    """Immutable view of ATLAS state at one tick."""

    pnl_pct: float = 0.0
    open_positions_count: int = 0
    agent_states: dict[str, str] = field(default_factory=dict)
    agent_last_heartbeat: dict[str, datetime | None] = field(default_factory=dict)
    is_mock: bool = False
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DecisionAction:
    """One recommendation from the policy engine."""

    type: DecisionType
    agent_id: str | None = None
    reason: str = ""
    severity: Literal["info", "warn", "alert"] = "info"
    priority: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Policy:
    """Policy thresholds. Frozen so a Sentinel cycle uses one snapshot."""

    drawdown_pause_pct: float = DEFAULT_DRAWDOWN_PAUSE_PCT
    drawdown_alert_pct: float = DEFAULT_DRAWDOWN_ALERT_PCT
    max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS
    stale_heartbeat_sec: int = DEFAULT_STALE_HEARTBEAT_SEC


def decide(snapshot: AtlasSnapshot, policy: Policy | None = None) -> list[DecisionAction]:
    """Apply policy rules to ``snapshot``. Returns ordered actions.

    Mock snapshots short-circuit to a single noop — we never push real
    alerts based on synthetic data.
    """
    pol = policy or Policy()

    if snapshot.is_mock:
        return [
            DecisionAction(
                type="noop",
                reason="mock_snapshot",
                payload={"pnl_pct": snapshot.pnl_pct},
            )
        ]

    actions: list[DecisionAction] = []

    # Rule 1 — drawdown breach. Pause trader + push high-priority alert.
    if snapshot.pnl_pct <= pol.drawdown_pause_pct:
        if snapshot.agent_states.get("trader") != "paused":
            actions.append(
                DecisionAction(
                    type="pause_agent",
                    agent_id="trader",
                    reason=f"drawdown_breach: {snapshot.pnl_pct:.2%} ≤ {pol.drawdown_pause_pct:.2%}",
                    severity="alert",
                    priority=2,
                    payload={"pnl_pct": snapshot.pnl_pct},
                )
            )
        actions.append(
            DecisionAction(
                type="alert",
                reason=f"ATLAS drawdown {snapshot.pnl_pct:.2%}",
                severity="alert",
                priority=2,
                payload={"pnl_pct": snapshot.pnl_pct},
            )
        )

    # Rule 2 — open-position cap. Pause oracle so no fresh signals stack up.
    if (
        snapshot.open_positions_count >= pol.max_open_positions
        and snapshot.agent_states.get("oracle") != "paused"
    ):
        actions.append(
            DecisionAction(
                type="pause_agent",
                agent_id="oracle",
                reason=(
                    f"open_position_cap: {snapshot.open_positions_count} ≥ "
                    f"{pol.max_open_positions}"
                ),
                severity="warn",
                priority=1,
                payload={"open_positions": snapshot.open_positions_count},
            )
        )

    # Rule 3 — stale heartbeats. Alert per stale agent.
    for agent_id, last_hb in snapshot.agent_last_heartbeat.items():
        if last_hb is None:
            continue
        delta = (snapshot.now - last_hb).total_seconds()
        if delta > pol.stale_heartbeat_sec:
            actions.append(
                DecisionAction(
                    type="alert",
                    agent_id=agent_id,
                    reason=f"stale_heartbeat: {agent_id} last seen {int(delta)}s ago",
                    severity="warn",
                    priority=1,
                    payload={"stale_sec": int(delta)},
                )
            )

    # Rule 4 — recovery. If pnl rebounded above the alert threshold and an
    # agent was previously paused due to drawdown, propose resume.
    if (
        snapshot.pnl_pct > pol.drawdown_pause_pct
        and snapshot.agent_states.get("trader") == "paused"
    ):
        actions.append(
            DecisionAction(
                type="resume_agent",
                agent_id="trader",
                reason=f"drawdown_recovered: {snapshot.pnl_pct:.2%} > {pol.drawdown_pause_pct:.2%}",
                severity="info",
                priority=0,
                payload={"pnl_pct": snapshot.pnl_pct},
            )
        )

    if not actions:
        actions.append(
            DecisionAction(
                type="noop",
                reason="no_policy_match",
                payload={
                    "pnl_pct": snapshot.pnl_pct,
                    "open_positions": snapshot.open_positions_count,
                },
            )
        )

    return actions


__all__ = [
    "AtlasSnapshot",
    "DecisionAction",
    "Policy",
    "decide",
    "DEFAULT_DRAWDOWN_PAUSE_PCT",
    "DEFAULT_DRAWDOWN_ALERT_PCT",
    "DEFAULT_MAX_OPEN_POSITIONS",
    "DEFAULT_STALE_HEARTBEAT_SEC",
]
