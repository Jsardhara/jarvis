"""Intent classifier + routing table for the orchestrator.

Six agents only:

    tempo    — Outlook (mail + calendar + tasks)
    scholar  — academics + study planning
    lens     — research + monitoring
    forge    — code-work delegation
    atlas    — trading orchestrator
    jarvis   — self-handled / fallback

Rules-only classifier. The LLM-backed Haiku classifier was removed in favour
of staying entirely on the local Pro/Max plan budget — running an LLM call
on every chat turn would compete with chat, scholar, and forge for the
shared 5h rate-limit bucket. Regex covers the routing table in CLAUDE.md.
"""
from __future__ import annotations

import logging
import re

from jarvis.contract import IntentClassification

log = logging.getLogger(__name__)

_KNOWN_AGENTS = {"tempo", "scholar", "lens", "forge", "atlas", "jarvis"}

# ---------------------------------------------------------------------------
# Regex rules
# Order matters: more-specific surfaces first.
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # Code-work signals
    (
        re.compile(
            r"\b(repo|pr|pull request|build|ship|bug|refactor|implement|deploy|commit|merge|\.py|\.ts|\.tsx|\.js)\b",
            re.I,
        ),
        "forge",
    ),
    # Trading / ATLAS
    (
        re.compile(
            r"\b(portfolio|positions?|p&?l|holdings|drawdown|atlas|paper trade|live trade|strateg(?:y|ies)|backtest)\b",
            re.I,
        ),
        "atlas",
    ),
    (re.compile(r"\b(market|trade|btc|eth|sol|crypto)\b", re.I), "atlas"),
    # School / academic
    (
        re.compile(
            r"\b(class(?:es)?|lectures?|professors?|courses?|assignments?|homework|exams?|stud(?:y|ies|ying)|midterms?|finals?|gpa|syllabus|papers?|essays?)\b",
            re.I,
        ),
        "scholar",
    ),
    # Mail / calendar / tasks → Tempo
    (re.compile(r"\b(email|inbox|reply|draft|mail|outlook)\b", re.I), "tempo"),
    (
        re.compile(
            r"\b(calendar|schedule|meeting|free time|todo|task|remind|appointment|invite)\b",
            re.I,
        ),
        "tempo",
    ),
    # Research / monitoring
    (
        re.compile(
            r"\b(research|look up|summari[sz]e|find out|news on|investigate|monitor|watch|track)\b",
            re.I,
        ),
        "lens",
    ),
    (re.compile(r"\b(code)\b", re.I), "forge"),
]

# Multi-domain triggers
_MULTI: list[tuple[re.Pattern, list[str]]] = [
    (
        re.compile(r"\b(briefing|morning|daily summary|catch me up|what'?s on my plate)\b", re.I),
        ["tempo", "scholar", "atlas"],
    ),
    (
        re.compile(r"\b(end of day|wrap up|evening summary)\b", re.I),
        ["tempo", "scholar", "atlas"],
    ),
]


def _classify_regex(request: str) -> IntentClassification:
    """Pure-regex classifier."""
    if not request or not request.strip():
        return IntentClassification(
            primary="jarvis",
            confidence=0.0,
            rationale="empty request",
            raw_request=request,
        )

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

    matches: list[tuple[str, re.Match]] = []
    for pat, agent in _RULES:
        m = pat.search(request)
        if m:
            matches.append((agent, m))

    if not matches:
        return IntentClassification(
            primary="jarvis",
            confidence=0.3,
            rationale="no rule matched — orchestrator self-handles",
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

    primary = matches[0][0]
    parallel = [a for a, _ in matches[1:] if a != primary]
    return IntentClassification(
        primary=primary,
        confidence=0.7,
        rationale=f"multi-rule match; primary={primary}, parallel={parallel}",
        parallel=parallel,
        raw_request=request,
    )


def classify(request: str) -> IntentClassification:
    """Route *request* to the best agent via regex rules."""
    return _classify_regex(request)
