"""Authority gate — enforces confirmation rules before any agent action runs.

Rules (derived from CLAUDE.md confirmation table):
- Tier 1: ALWAYS requires confirmation.
- Tier 2 + external-effect action: requires confirmation.
- Tier 3-5: most actions pass; explicit send/execute/mutate actions still require confirmation.
"""
from __future__ import annotations

# Actions that mutate external state and always need confirmation regardless of tier.
# Confirmation matrix (CLAUDE.md): send_mail, calendar mutations, code merge/push,
# Atlas strategy triggers, sentinel control, agent pause, mass delete.
_ALWAYS_CONFIRM_ACTIONS: frozenset[str] = frozenset({
    "send_mail",
    "trader_execute",
    "trader_execute_confirmed",
    "merge",
    "push",
    "commit",
    "cancel",
    "stop_sentinel",
    "restart_sentinel",
    "pause_agent",
    "mass_delete",
    # Response-side action verbs — agents emit these on completion. Including
    # them here lets ``check_response_authority`` catch mutations that the
    # pre-dispatch gate could not see (e.g. agent decided to merge even
    # though the request text only said "ship it").
    "paused",
    "halted",
    "merged",
    "pushed",
    "committed",
})

# External-effect actions that trigger confirmation at tier 2 but not at tier 3-5.
_TIER2_EXTERNAL_ACTIONS: frozenset[str] = frozenset({
    "send_mail",
    "cancel",
    "schedule",
    "trader_execute",
    "trader_execute_confirmed",
    "merge",
    "push",
    "commit",
})


class AuthorityError(Exception):
    def __init__(self, action: str, reason: str) -> None:
        self.action = action
        self.reason = reason
        super().__init__(f"authority check failed for '{action}': {reason}")


def requires_confirm(agent: str, action: str, tier: int) -> bool:  # noqa: ARG001
    """Return True if this agent/action/tier combination requires operator confirmation."""
    if tier == 1:
        return True
    if tier == 2 and action in _TIER2_EXTERNAL_ACTIONS:
        return True
    return action in _ALWAYS_CONFIRM_ACTIONS


def check_authority(agent: str, action: str, tier: int, confirmed: bool = False) -> None:
    """Raise AuthorityError if confirmation is required but not given."""
    if not requires_confirm(agent, action, tier):
        return
    if confirmed:
        return
    if tier == 1:
        raise AuthorityError(action, f"tier-1 action '{action}' always requires confirmation")
    if tier == 2 and action in _TIER2_EXTERNAL_ACTIONS:
        raise AuthorityError(
            action,
            f"tier-2 external-effect action '{action}' requires confirmation",
        )
    raise AuthorityError(action, f"action '{action}' requires confirmation")


def check_response_authority(
    agent: str,  # noqa: ARG001
    response_action: str,
    confirmed: bool = False,
) -> None:
    """Post-dispatch authority gate.

    The pre-dispatch ``check_authority`` runs against an action *inferred*
    from request text. After a handler returns, the agent may have emitted
    a response-side action (e.g. ``paused`` or ``merged``) that should also
    have required confirmation but bypassed the up-front gate. Re-check
    against ``_ALWAYS_CONFIRM_ACTIONS`` here so the orchestrator can
    transform the response into a proposal instead of letting it land.
    """
    if response_action in _ALWAYS_CONFIRM_ACTIONS and not confirmed:
        raise AuthorityError(
            response_action,
            f"response-side action '{response_action}' requires confirmation",
        )
