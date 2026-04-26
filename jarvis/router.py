"""Intent classifier + routing table for the orchestrator."""
from __future__ import annotations

import re

from .contract import IntentClassification

# Pattern → primary agent. Order matters: more-specific surfaces first so
# "reply to slack DM" routes to echo (not aide), "fix bug in atlas" to forge
# (not ledger). Generic comms/finance words are last.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(slack|discord|sms|dm|whatsapp|imessage)\b", re.I), "echo"),
    (re.compile(r"\b(repo|pr|pull request|build|ship|bug|refactor|implement|deploy|commit|merge|\.py|\.ts|\.tsx|\.js)\b", re.I), "forge"),
    (re.compile(r"\b(portfolio|position|p&?l|holdings|drawdown|atlas strategy|paper trade|live trade)\b", re.I), "ledger"),
    (re.compile(r"\b(email|inbox|reply|draft|mail|gmail)\b", re.I), "aide"),
    (re.compile(r"\b(calendar|schedule|meeting|free time|todo|task|remind|appointment)\b", re.I), "chronos"),
    (re.compile(r"\b(research|look up|summari[sz]e|find out|news on|investigate)\b", re.I), "sherlock"),
    (re.compile(r"\b(market|trade|btc|eth|atlas)\b", re.I), "ledger"),
    (re.compile(r"\b(code)\b", re.I), "forge"),
    (re.compile(r"\b(message|text)\b", re.I), "echo"),
]

# Multi-domain triggers — orchestrator dispatches to multiple
_MULTI: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\b(briefing|morning|daily summary|catch me up|what'?s on my plate)\b", re.I),
     ["aide", "chronos", "ledger"]),
    (re.compile(r"\b(end of day|wrap up|evening summary)\b", re.I),
     ["aide", "chronos", "ledger"]),
]


def classify(request: str) -> IntentClassification:
    """Rule-first classifier. LLM fallback handled by orchestrator agent prompt."""
    if not request or not request.strip():
        return IntentClassification(
            primary="jarvis",
            confidence=0.0,
            rationale="empty request",
            raw_request=request,
        )

    # Multi-domain first
    for pat, agents in _MULTI:
        if pat.search(request):
            primary = agents[0]
            return IntentClassification(
                primary=primary,
                confidence=0.85,
                rationale=f"multi-domain briefing matched: {pat.pattern}",
                parallel=agents[1:],
                raw_request=request,
            )

    # Single-agent rules
    matches: list[tuple[str, re.Match]] = []
    for pat, agent in _RULES:
        m = pat.search(request)
        if m:
            matches.append((agent, m))

    if not matches:
        return IntentClassification(
            primary="jarvis",
            confidence=0.3,
            rationale="no rule matched — orchestrator self-handles or asks LLM",
            raw_request=request,
        )

    if len(matches) == 1:
        agent, m = matches[0]
        return IntentClassification(
            primary=agent,
            confidence=0.9,
            rationale=f"matched '{m.group(0)}' → {agent}",
            raw_request=request,
        )

    # Multiple single-agent rules hit — first wins as primary, rest parallel
    primary = matches[0][0]
    parallel = [a for a, _ in matches[1:] if a != primary]
    return IntentClassification(
        primary=primary,
        confidence=0.7,
        rationale=f"multi-rule match; primary={primary}, parallel={parallel}",
        parallel=parallel,
        raw_request=request,
    )
