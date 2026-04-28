"""Intent classifier + routing table for the orchestrator.

Six agents only:

    tempo    — Outlook (mail + calendar + tasks)
    scholar  — academics + study planning
    lens     — research + monitoring
    forge    — code-work delegation
    atlas    — trading orchestrator
    jarvis   — self-handled / fallback

LLM-based classifier (Haiku) is tried first when ANTHROPIC_API_KEY is set
and JARVIS_LLM_ROUTER != "false".  Regex rules serve as fallback.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

from .contract import IntentClassification
from .cost import log_cost

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level switch — set JARVIS_LLM_ROUTER=false to force regex only.
# ---------------------------------------------------------------------------

USE_LLM_ROUTER: bool = os.environ.get("JARVIS_LLM_ROUTER", "true").lower() == "true"

_LLM_MODEL = "claude-haiku-4-5-20251001"
_KNOWN_AGENTS = {"tempo", "scholar", "lens", "forge", "atlas", "jarvis"}

_LLM_SYSTEM = (
    "Classify this request into ONE of: tempo, scholar, lens, forge, atlas, jarvis. "
    "Return JSON only: "
    '{"primary": str, "parallel": list[str], "rationale": str, "confidence": float}. '
    "Use parallel for multi-domain briefings (e.g. morning_briefing → tempo+scholar+atlas). "
    "Confidence must be 0.0–1.0. No extra text."
)

# ---------------------------------------------------------------------------
# Regex rules (fallback)
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
            r"\b(class|lecture|professor|course|assignment|homework|exam|study|midterm|final|gpa|syllabus|paper|essay)\b",
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


# ---------------------------------------------------------------------------
# Regex-only classifier
# ---------------------------------------------------------------------------


def _classify_regex(request: str) -> IntentClassification:
    """Pure-regex classifier — always available, no API key required."""
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


# ---------------------------------------------------------------------------
# LLM classifier (Haiku) with LRU cache
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=512)
def classify_llm(request: str) -> IntentClassification:
    """Classify intent via Haiku LLM.  Falls back to regex on any failure.

    The cache key is the normalised (stripped, lowercased) request.  Callers
    should pass ``request.lower().strip()`` for maximum cache hit rate.
    """
    if anthropic is None:
        log.warning("anthropic package not installed — falling back to regex")
        return _classify_regex(request)

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=_LLM_MODEL,
            max_tokens=128,
            system=_LLM_SYSTEM,
            messages=[{"role": "user", "content": request}],
        )
        raw_text: str = msg.content[0].text
        log_cost(
            agent="jarvis-router",
            model=_LLM_MODEL,
            in_tokens=msg.usage.input_tokens,
            out_tokens=msg.usage.output_tokens,
        )
    except Exception as exc:
        log.warning("LLM classify failed (%s) — falling back to regex", exc)
        return _classify_regex(request)

    try:
        data = json.loads(raw_text)
        primary = str(data["primary"])
        parallel = [str(a) for a in data.get("parallel", [])]
        rationale = str(data["rationale"])
        confidence = float(data["confidence"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        log.warning("LLM response parse error (%s) — falling back to regex", exc)
        return _classify_regex(request)

    if primary not in _KNOWN_AGENTS:
        log.warning("LLM returned unknown agent '%s' — falling back to regex", primary)
        return _classify_regex(request)

    return IntentClassification(
        primary=primary,
        confidence=max(0.0, min(1.0, confidence)),
        rationale=rationale,
        parallel=[a for a in parallel if a in _KNOWN_AGENTS],
        raw_request=request,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify(request: str) -> IntentClassification:
    """Route *request* to the best agent.

    Uses LLM classifier (Haiku) when:
    - USE_LLM_ROUTER is True, AND
    - ANTHROPIC_API_KEY env var is set.

    Falls back to regex otherwise.
    """
    normalised = (request or "").lower().strip()

    if USE_LLM_ROUTER and os.environ.get("ANTHROPIC_API_KEY"):
        return classify_llm(normalised)

    return _classify_regex(request)
