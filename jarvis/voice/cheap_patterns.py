"""Local regex matchers for voice queries that don't need an LLM.

Match before Claude is invoked. Returns a short voice response or None.
Adds zero token cost for the most common short queries (time, date,
greetings, acks, control words).

Order matters: check specific patterns before generic. ``match()``
returns the first hit's response.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

# Each rule = (compiled-regex, builder-function-returning-str-or-None)
# Builder takes the original text; returns the response or None to fall
# through to the next rule.
RuleBuilder = Callable[[str], str | None]
Rule = tuple[re.Pattern[str], RuleBuilder]


def _now_time(_text: str) -> str:
    return datetime.now().strftime("It's %-I:%M %p.") if hasattr(
        datetime.now(), "strftime"
    ) else "Time unavailable."


def _now_time_safe(_text: str) -> str:
    # %-I is POSIX; fallback for Windows.
    now = datetime.now()
    h12 = now.hour % 12 or 12
    return f"It's {h12}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}."


def _today_date(_text: str) -> str:
    return datetime.now().strftime("Today is %A, %B %d.")


def _greeting(_text: str) -> str:
    return "Hi."


def _thanks(_text: str) -> str:
    # Empty string = silent ack — TTS skips, just plays nothing back.
    return ""


def _stop(_text: str) -> str:
    return "Stopped."


def _repeat(_text: str) -> str:
    # cheap_handler will replay the last response cached in memory.
    return "__REPEAT_LAST__"


RULES: tuple[Rule, ...] = (
    (
        re.compile(r"\bwhat\s+(?:time|hour)\s+(?:is\s+it|now)\b", re.I),
        _now_time_safe,
    ),
    (re.compile(r"\b(?:current\s+)?time\b", re.I), _now_time_safe),
    (re.compile(r"\bwhat\s+(?:day|date)\s+is\s+it\b", re.I), _today_date),
    (re.compile(r"\b(?:today's|todays)\s+date\b", re.I), _today_date),
    (
        re.compile(
            r"^(?:hi|hello|hey|yo|sup)(?:\s+jarvis)?[.!?]?$", re.I,
        ),
        _greeting,
    ),
    (
        re.compile(r"^(?:thanks|thank\s+you|thx|ty|cheers|appreciated)[.!?]?$", re.I),
        _thanks,
    ),
    (
        re.compile(r"^(?:stop|cancel|never\s+mind|nevermind|abort|quiet|mute)[.!?]?$", re.I),
        _stop,
    ),
    (
        re.compile(r"^(?:repeat|say\s+(?:that|it)\s+again|what)[.!?]?$", re.I),
        _repeat,
    ),
)

# Heavy keywords that should escalate from Haiku to Sonnet for better
# multi-step reasoning. Operator selected: explain/why and code/refactor.
HEAVY_KEYWORDS: frozenset[str] = frozenset(
    {"explain", "why", "because", "reason", "code", "refactor", "review"},
)

# Keywords that signal full agent dispatch needed — voice falls back to
# the Orchestrator instead of cheap_handler. These are tasks that
# *change* state across subsystems (drafting mail, scheduling, executing
# trades, kicking off forge work). Read-only queries stay cheap.
DISPATCH_KEYWORDS: frozenset[str] = frozenset(
    {
        "draft", "send", "schedule", "remind", "create", "delete",
        "execute", "run strategy", "open pr", "merge", "deploy",
        "atlas pipeline", "run forge", "build me",
    },
)


def match(text: str) -> str | None:
    """Return a local response, or None if no rule matches."""
    cleaned = text.strip().rstrip(".!?")
    for pattern, builder in RULES:
        if pattern.search(cleaned):
            return builder(cleaned)
    return None


def has_heavy_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in HEAVY_KEYWORDS)


def has_dispatch_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in DISPATCH_KEYWORDS)


__all__ = [
    "match",
    "has_heavy_keyword",
    "has_dispatch_keyword",
    "RULES",
    "HEAVY_KEYWORDS",
    "DISPATCH_KEYWORDS",
]
