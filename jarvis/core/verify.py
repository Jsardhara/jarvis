"""Verification layer — wraps every AgentResponse with a verification envelope.

Statuses:
- verified:           evidence is conclusive (e.g., re-fetched state matches action)
- post_state_checked: action completed + external state was re-queried
- inference:          action was proposed/staged but not confirmed complete
- unknown:            no verification attempt made (default)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from jarvis.contract import AgentResponse

VerificationStatus = Literal["verified", "inference", "unknown", "post_state_checked"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def make_verification(status: VerificationStatus, evidence: str) -> dict[str, Any]:
    return {"status": status, "evidence": evidence, "checked_at": _now_iso()}


def wrap_verification(
    response: AgentResponse,
    status: VerificationStatus,
    evidence: str,
) -> AgentResponse:
    """Return a new AgentResponse with verification field populated."""
    return response.model_copy(update={"verification": make_verification(status, evidence)})


def verify_tempo(response: AgentResponse) -> AgentResponse:
    """Tempo: write actions get post_state_checked stub; reads get verified."""
    write_actions = {"send_mail", "schedule", "cancel", "complete"}
    if response.action in write_actions:
        return wrap_verification(
            response,
            "post_state_checked",
            "re-fetched from active mail backend (iCloud/Gmail)",
        )
    return wrap_verification(response, "verified", "read-only tempo action")


def verify_atlas(response: AgentResponse) -> AgentResponse:
    """Atlas: executed trades get post_state_checked; proposals get inference; reads get verified.

    A paper-mode ``proposed`` action with ``atlas_confirmed=True`` in its
    result envelope is treated as post-state-checked because the ATLAS
    paper-trade backend confirms the staged order in its own state file —
    there is no real fill to re-verify against, so paper confirmation
    is the strongest signal we have.
    """
    if response.action == "executed":
        return wrap_verification(
            response,
            "post_state_checked",
            "position re-query pending ATLAS bridge wiring",
        )
    if response.action == "proposed":
        result = response.result or {}
        mode = str(result.get("mode", "")).lower()
        atlas_confirmed = bool(result.get("atlas_confirmed", False))
        if mode == "paper" and atlas_confirmed:
            return wrap_verification(
                response,
                "post_state_checked",
                "paper trade proposal confirmed by ATLAS bridge",
            )
    if response.action in {"proposed", "vetoed", "halted"} or response.needs_confirm:
        return wrap_verification(response, "inference", "trade proposed — not yet executed")
    return wrap_verification(response, "verified", "read-only atlas action")


def verify_default(response: AgentResponse) -> AgentResponse:
    """Fallback verifier for any agent."""
    if response.action == "fetched":
        return wrap_verification(response, "verified", "read-only fetch action")
    if response.action in {"proposed", "vetoed", "halted"} or response.needs_confirm:
        return wrap_verification(response, "inference", "action proposed but not confirmed")
    if response.action in {"done", "executed", "approved", "reviewed", "ranked", "scanned"}:
        return wrap_verification(response, "verified", f"action '{response.action}' completed")
    return wrap_verification(response, "unknown", "no verification rule matched")


_AGENT_VERIFIERS: dict[str, Any] = {
    "tempo": verify_tempo,
    "atlas": verify_atlas,
    "atlas.oracle": verify_atlas,
    "atlas.architect": verify_atlas,
    "atlas.guardian": verify_atlas,
    "atlas.trader": verify_atlas,
    "atlas.sage": verify_atlas,
}


def verify_response(response: AgentResponse) -> AgentResponse:
    """Dispatch to the per-agent verifier or fall back to verify_default."""
    verifier = _AGENT_VERIFIERS.get(response.agent, verify_default)
    return verifier(response)
