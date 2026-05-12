"""Authority gate — enforces confirmation rules before any agent action runs.

Rules (derived from CLAUDE.md confirmation table):
- Tier 1: ALWAYS requires confirmation.
- Tier 2 + external-effect action: requires confirmation.
- Tier 3-5: most actions pass; explicit send/execute/mutate actions still require confirmation.
"""
from __future__ import annotations

# Actions that mutate external state and always need confirmation regardless of tier.
_ALWAYS_CONFIRM_ACTIONS: frozenset[str] = frozenset({
    "send_mail",
    "trader_execute",
    "trader_execute_confirmed",
    "merge",
    "push",
    "commit",
    "cancel",
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
