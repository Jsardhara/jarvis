"""Hermes-native approval policy adapters.

This module centralizes the operator confirmation contract used by the Hermes
manifest, the FastAPI bridge, and Mission Control. It does not execute risky
actions; it only classifies them and normalizes existing Jarvis confirmations
into the dashboard approval shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis.contract import Confirmation
from jarvis.hermes.manifest import load_manifest

RISK_BY_GATE: dict[str, str] = {
    "send_mail": "external",
    "calendar_mutation": "external",
    "remote_code_push": "external",
    "open_pr": "external",
    "merge_pr": "external",
    "atlas_strategy_trigger": "financial",
    "atlas_execution": "financial",
    "atlas_live_mode_flip": "financial",
    "sentinel_stop": "system",
    "sentinel_restart": "system",
    "delete_memory": "system",
    "delete_state": "system",
    "install_service": "system",
}

ACTION_ALIASES: dict[str, str] = {
    # Tempo
    "send": "send_mail",
    "send_mail": "send_mail",
    "schedule": "calendar_mutation",
    "calendar_create": "calendar_mutation",
    "calendar_update": "calendar_mutation",
    "calendar_cancel": "calendar_mutation",
    "cancel": "calendar_mutation",
    # Forge
    "push": "remote_code_push",
    "remote_code_push": "remote_code_push",
    "open_pr": "open_pr",
    "merge": "merge_pr",
    "merge_pr": "merge_pr",
    # Atlas
    "atlas_strategy_trigger": "atlas_strategy_trigger",
    "trader_execute": "atlas_execution",
    "trader_execute_confirmed": "atlas_execution",
    "atlas_execution": "atlas_execution",
    "atlas_live_mode_flip": "atlas_live_mode_flip",
    # Sentinel
    "stop_sentinel": "sentinel_stop",
    "sentinel_stop": "sentinel_stop",
    "restart_sentinel": "sentinel_restart",
    "sentinel_restart": "sentinel_restart",
    # State/system
    "delete_memory": "delete_memory",
    "delete_state": "delete_state",
    "install_service": "install_service",
}

SAFE_READ_ACTIONS = frozenset(
    {
        "quick_search",
        "deep_research",
        "monitoring",
        "news_briefs",
        "evidence_synthesis",
        "document_summary",
        "assignments",
        "study_plans",
        "syllabus_ingest",
        "flashcards",
        "weak_topic_repair",
        "portfolio",
        "positions",
        "pnl",
        "health_checks",
        "cron",
    }
)


@dataclass(frozen=True)
class ActionPolicy:
    """Resolved confirmation policy for one agent/action pair."""

    agent: str
    action: str
    gate: str | None
    risk: str
    requires_confirmation: bool
    reason: str


def approval_policy() -> dict[str, Any]:
    """Return the public approval policy derived from the Hermes manifest."""

    manifest = load_manifest()
    gates: dict[str, dict[str, Any]] = {}

    for gate in manifest.approval_defaults.get("require_confirmation", []):
        gates[str(gate)] = {
            "risk": RISK_BY_GATE.get(str(gate), "mutate"),
            "agents": [],
            "requires_confirmation": True,
        }

    for agent_id, agent in manifest.agents.items():
        for gate in agent.get("confirmation_gates") or []:
            gate_id = str(gate)
            gates.setdefault(
                gate_id,
                {
                    "risk": RISK_BY_GATE.get(gate_id, "mutate"),
                    "agents": [],
                    "requires_confirmation": True,
                },
            )
            agents = gates[gate_id]["agents"]
            if agent_id not in agents:
                agents.append(agent_id)

    return {
        "mode": "approval_first",
        "default_safe_risk": "read",
        "gates": gates,
    }


def action_policy(agent: str, action: str) -> ActionPolicy:
    """Resolve whether an agent/action must stop for operator approval."""

    normalized_action = action.strip()
    gate = ACTION_ALIASES.get(normalized_action, normalized_action)
    policy = approval_policy()
    gate_policy = policy["gates"].get(gate)

    if gate_policy is not None:
        return ActionPolicy(
            agent=agent,
            action=normalized_action,
            gate=gate,
            risk=str(gate_policy["risk"]),
            requires_confirmation=True,
            reason=f"{gate} is listed in the Hermes approval policy",
        )

    if normalized_action in SAFE_READ_ACTIONS:
        return ActionPolicy(
            agent=agent,
            action=normalized_action,
            gate=None,
            risk="read",
            requires_confirmation=False,
            reason="read-only or draft-only action",
        )

    return ActionPolicy(
        agent=agent,
        action=normalized_action,
        gate=None,
        risk="draft",
        requires_confirmation=False,
        reason="not listed as a risky gate",
    )


def confirmation_to_approval(confirmation: Confirmation) -> dict[str, Any]:
    """Convert existing Jarvis Confirmation records to the Hermes approval shape."""

    action = confirmation.intent or confirmation.args.get("action") or "unknown"
    policy = _approval_policy_for_confirmation(confirmation, str(action))
    return {
        "id": confirmation.id,
        "created_at": confirmation.ts,
        "agent": confirmation.agent,
        "action": str(action),
        "gate": policy.gate,
        "risk": policy.risk,
        "summary": confirmation.summary or confirmation.request or str(action),
        "payload": confirmation.args,
        "status": confirmation.status,
        "resolved_at": confirmation.resolved_ts,
        "resolved_result": confirmation.resolved_result,
        "expires_at": None,
    }


def _approval_policy_for_confirmation(confirmation: Confirmation, action: str) -> ActionPolicy:
    direct = action_policy(confirmation.agent, action)
    if direct.requires_confirmation or direct.risk != "draft":
        return direct

    # Existing confirmations may store human-readable intents like
    # ``trade.execute`` rather than descriptor actions like ``trader_execute``.
    if confirmation.agent == "atlas":
        return ActionPolicy(
            agent=confirmation.agent,
            action=action,
            gate="atlas_execution",
            risk="financial",
            requires_confirmation=True,
            reason="Atlas confirmations are financial by default",
        )
    if confirmation.agent == "tempo" and ("mail" in action or "calendar" in action):
        gate = "send_mail" if "mail" in action else "calendar_mutation"
        return ActionPolicy(
            agent=confirmation.agent,
            action=action,
            gate=gate,
            risk="external",
            requires_confirmation=True,
            reason="Tempo mail/calendar confirmations affect external state",
        )
    if confirmation.agent == "sentinel":
        return ActionPolicy(
            agent=confirmation.agent,
            action=action,
            gate="sentinel_restart",
            risk="system",
            requires_confirmation=True,
            reason="Sentinel confirmations affect background automation",
        )
    if confirmation.agent == "forge":
        return ActionPolicy(
            agent=confirmation.agent,
            action=action,
            gate="remote_code_push",
            risk="external",
            requires_confirmation=True,
            reason="Forge confirmations may affect remote code state",
        )
    return direct
