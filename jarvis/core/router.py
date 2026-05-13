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

# Action-keyword patterns per agent. First match wins.
# Used by ``infer_action`` so the orchestrator can pass real action names
# (send_mail, schedule, cancel, trader_execute, …) into the authority gate
# instead of the literal "dispatch".
_ACTION_RULES: dict[str, list[tuple[re.Pattern, str]]] = {
    "tempo": [
        (re.compile(r"\b(send mail|send email|send the (?:mail|email)|fire (?:it )?off)\b", re.I), "send_mail"),
        (re.compile(r"\b(cancel|drop|kill|remove)\b.*\b(meeting|event|invite)\b", re.I), "cancel"),
        (re.compile(r"\b(schedule|book|set up|arrange)\b.*\b(meeting|event|call|invite)\b", re.I), "schedule"),
        (re.compile(r"\b(draft|reply|respond)\b", re.I), "draft_reply"),
        (re.compile(r"\b(triage|inbox|action(?: items?)?)\b", re.I), "triage"),
        (re.compile(r"\b(search mail|find email|find mail)\b", re.I), "search_mail"),
        (re.compile(r"\b(today|calendar|schedule today)\b", re.I), "today"),
    ],
    "atlas": [
        (re.compile(r"\b(execute|place trade|fire trade|live trade|run trade)\b", re.I), "trader_execute"),
        (re.compile(r"\b(portfolio|holdings)\b", re.I), "portfolio"),
        (re.compile(r"\b(positions?)\b", re.I), "positions"),
        (re.compile(r"\b(p&?l|pnl)\b", re.I), "pnl"),
        (re.compile(r"\b(oracle scan|market scan)\b", re.I), "oracle_scan"),
        (re.compile(r"\b(architect rank|rank strateg)", re.I), "architect_rank"),
        (re.compile(r"\b(guardian check|risk check)\b", re.I), "guardian_check"),
        (re.compile(r"\b(pipeline|run pipeline)\b", re.I), "pipeline"),
    ],
    "forge": [
        (re.compile(r"\b(execute|build|implement|deploy|run)\b", re.I), "execute"),
        (re.compile(r"\b(push|merge|commit)\b", re.I), "execute"),
        (re.compile(r"\b(list runs|history|recent runs)\b", re.I), "list_runs"),
    ],
    "scholar": [
        (re.compile(r"\b(plan|study plan|schedule study)\b", re.I), "plan_week"),
        (re.compile(r"\b(assignments?|homework|due)\b", re.I), "list_assignments"),
        (re.compile(r"\b(summari[sz]e)\b", re.I), "summarize"),
    ],
    "lens": [
        (re.compile(r"\b(deep research|investigate)\b", re.I), "deep_research"),
        (re.compile(r"\b(monitor|watch|track)\b", re.I), "monitor"),
        (re.compile(r"\b(news|world brief)\b", re.I), "world_brief"),
        (re.compile(r"\b(research|look up|summari[sz]e|find out)\b", re.I), "quick_search"),
    ],
}


def infer_action(request: str, agent: str) -> str:
    """Best-effort action name for ``agent`` derived from request text.

    Returns ``"dispatch"`` when no agent-specific pattern matches, which
    preserves the legacy ``check_authority(action="dispatch", …)`` behaviour
    for unknown / ambiguous turns. Confirmation-gated actions like
    ``send_mail``, ``schedule``, ``cancel`` and ``trader_execute`` get
    detected here so the authority gate can fire correctly.
    """
    if not request:
        return "dispatch"
    rules = _ACTION_RULES.get(agent, [])
    for pat, action in rules:
        if pat.search(request):
            return action
    return "dispatch"


def _dedupe_preserve(items: list[str]) -> list[str]:
    """Return items with first-seen order preserved and duplicates removed."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _classify_regex(request: str) -> IntentClassification:
    """Pure-regex classifier."""
    if not request or not request.strip():
        return IntentClassification(
            primary="jarvis",
            confidence=0.0,
            rationale="empty request",
            raw_request=request,
            action="dispatch",
        )

    # Multi-domain triggers contribute to the parallel set instead of
    # short-circuiting — earlier behaviour silently dropped any single-rule
    # match when a briefing keyword fired, which left send_mail / schedule
    # signals stranded. Now we union both.
    multi_agents: list[str] = []
    multi_patterns: list[str] = []
    for pat, agents in _MULTI:
        if pat.search(request):
            multi_agents.extend(agents)
            multi_patterns.append(pat.pattern)

    matches: list[tuple[str, re.Match]] = []
    for pat, agent in _RULES:
        m = pat.search(request)
        if m:
            matches.append((agent, m))

    if not matches and not multi_agents:
        return IntentClassification(
            primary="jarvis",
            confidence=0.3,
            rationale="no rule matched — orchestrator self-handles",
            raw_request=request,
            action="dispatch",
        )

    if not matches and multi_agents:
        unioned = _dedupe_preserve(multi_agents)
        primary = unioned[0]
        return IntentClassification(
            primary=primary,
            confidence=0.85,
            rationale=f"multi-domain briefing matched: {','.join(multi_patterns)}",
            parallel=unioned[1:],
            raw_request=request,
            action=infer_action(request, primary),
        )

    if len(matches) == 1 and not multi_agents:
        agent, m = matches[0]
        return IntentClassification(
            primary=agent,
            confidence=0.9,
            rationale=f"matched '{m.group(0)}' → {agent}",
            raw_request=request,
            action=infer_action(request, agent),
        )

    rule_agents = [a for a, _ in matches]
    unioned = _dedupe_preserve(rule_agents + multi_agents)
    primary = unioned[0]
    parallel = unioned[1:]
    rationale_parts = []
    if matches:
        rationale_parts.append(f"multi-rule match; primary={primary}, parallel={parallel}")
    if multi_patterns:
        rationale_parts.append(f"multi-domain briefing: {','.join(multi_patterns)}")
    confidence = 0.85 if multi_patterns else 0.7
    return IntentClassification(
        primary=primary,
        confidence=confidence,
        rationale=" | ".join(rationale_parts),
        parallel=parallel,
        raw_request=request,
        action=infer_action(request, primary),
    )


def classify(request: str) -> IntentClassification:
    """Route *request* to the best agent via regex rules."""
    return _classify_regex(request)
