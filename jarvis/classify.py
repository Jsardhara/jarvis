"""Tier classifier — assigns priority tier 1-5 to every request.

Tier 1: safety/risk (live trade, mass delete, security ops, sentinel control)
Tier 2: time-sensitive commitments (deadlines today, imminent meetings, drawdown)
Tier 3: trading + active research (paper trades, market scans, monitoring)
Tier 4: scheduling + correspondence (mail draft, calendar, study plan, tasks)
Tier 5: routine (status lookups, housekeeping, read-only queries)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TierClassification:
    tier: int
    rationale: str


_TIER_RULES: list[tuple[int, re.Pattern[str], str]] = [
    # Tier 1 — safety/risk
    (
        1,
        re.compile(
            r"\b(live trade|live mode|live execution|mass delete|wipe|drop table|"
            r"security ops|stop sentinel|restart sentinel|delete all|"
            r"purge|nuke|overwrite|force push|force-push)\b",
            re.I,
        ),
        "tier-1 safety/risk keyword",
    ),
    # Tier 2 — time-sensitive commitments
    (
        2,
        re.compile(
            r"\b(deadline\b.*\btoday|due today|meeting.*starting|starting.*meeting|"
            r"drawdown alert|drawdown.*critical|exam.*today|today.*exam|"
            r"starting soon|right now|urgent|asap|immediately)\b",
            re.I,
        ),
        "tier-2 time-sensitive keyword",
    ),
    # Tier 3 — trading + research
    (
        3,
        re.compile(
            r"\b(paper trade|backtest|market scan|oracle scan|architect rank|"
            r"guardian check|run strategy|research|look up|summari[sz]e|"
            r"find out|news on|investigate|monitor|watch|track|"
            r"portfolio|positions?|p&?l|holdings|drawdown|strateg(?:y|ies))\b",
            re.I,
        ),
        "tier-3 trading/research keyword",
    ),
    # Tier 4 — scheduling + correspondence
    (
        4,
        re.compile(
            r"\b(draft|repl(?:y|ies)|email|inbox|mail|outlook|calendar|schedule|meeting|"
            r"appointment|invite|todo|task|remind\w*|study plan|homework|assignment|"
            r"course|class|free time)\b",
            re.I,
        ),
        "tier-4 scheduling/correspondence keyword",
    ),
]


def classify_tier(request: str, agent: str = "", action: str = "") -> TierClassification:
    """Return the tier (1-5) for a request + optional agent/action context."""
    if not request or not request.strip():
        return TierClassification(tier=5, rationale="empty request defaults to tier-5")

    text = f"{request} {agent} {action}".strip()

    for tier, pattern, rationale in _TIER_RULES:
        if pattern.search(text):
            return TierClassification(tier=tier, rationale=rationale)

    return TierClassification(tier=5, rationale="no tier-1..4 keyword matched; defaulting to tier-5")
