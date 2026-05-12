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
from datetime import datetime, timedelta

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


_DURATION_MULTIPLIER = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}

_WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60,
    "a": 1, "an": 1,
}

_QUIET_DURATION_RE = re.compile(
    r"\b(?:quiet|mute|stand\s+down|silence)"
    r"(?:\s+(?:for|me|me\s+for))?"
    r"\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|sixty|a|an)\s+"
    r"(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)\b",
    re.I,
)
_QUIET_BARE_RE = re.compile(
    r"^(?:quiet|stand\s+down|silence|hush)(?:\s+jarvis)?[.!?]?$", re.I,
)
_SPEAK_UP_RE = re.compile(
    r"^(?:speak\s+up|come\s+back|wake\s+up|unmute|listen\s+up)(?:\s+jarvis)?[.!?]?$",
    re.I,
)
_START_FRESH_RE = re.compile(
    r"^(?:start\s+fresh|forget\s+(?:that|it|everything)|new\s+conversation|reset\s+memory)[.!?]?$",
    re.I,
)


def _parse_duration(amount: str, unit: str) -> timedelta:
    amount_lower = amount.lower()
    if amount_lower.isdigit():
        n = int(amount_lower)
    else:
        n = _WORD_TO_NUM.get(amount_lower, 1)
    mult = _DURATION_MULTIPLIER.get(unit.lower(), 60)
    return timedelta(seconds=n * mult)


def _format_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total >= 3600:
        h = total // 3600
        return f"{h} hour" if h == 1 else f"{h} hours"
    if total >= 60:
        m = total // 60
        return f"{m} minute" if m == 1 else f"{m} minutes"
    return f"{total} seconds"


def _quiet_for(text: str) -> str | None:
    m = _QUIET_DURATION_RE.search(text)
    if not m:
        return None
    duration = _parse_duration(m.group(1), m.group(2))
    from . import proactive
    proactive.mute_for(duration)
    return f"Quiet for {_format_duration(duration)}."


def _quiet_bare(_text: str) -> str:
    from . import proactive
    proactive.mute_for(timedelta(minutes=10))
    return "Quiet for 10 minutes."


def _speak_up(_text: str) -> str:
    from . import proactive
    proactive.clear_mute()
    return "Back."


def _start_fresh(_text: str) -> str:
    from . import conversation_memory
    conversation_memory.clear()
    return "Fresh slate."


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
    (_QUIET_DURATION_RE, _quiet_for),
    (_SPEAK_UP_RE, _speak_up),
    (_START_FRESH_RE, _start_fresh),
    (_QUIET_BARE_RE, _quiet_bare),
    (
        re.compile(r"^(?:stop|cancel|never\s+mind|nevermind|abort|mute)[.!?]?$", re.I),
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

# Read-only queries that nonetheless require *tools* (screenshot, file
# read, window listing, etc.). Routing these to Haiku/Sonnet without
# tools causes hallucinated answers. Route to agent_brain instead so
# the SDK loop has access to MCP + Read/Bash/Grep/Glob.
TOOL_KEYWORDS: frozenset[str] = frozenset(
    {
        "screen", "screenshot", "window", "windows open", "what's open",
        "click", "type into", "press key", "scroll",
        "look at", "show me", "see your screen", "see the screen",
        "focus on", "drag",
        "read file", "open file", "what's in", "list files",
        "run command", "in terminal", "in cmd",
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


def has_tool_keyword(text: str) -> bool:
    """True if the query needs tools (screenshot, file read, etc.)."""
    lowered = text.lower()
    return any(kw in lowered for kw in TOOL_KEYWORDS)


__all__ = [
    "match",
    "has_heavy_keyword",
    "has_dispatch_keyword",
    "has_tool_keyword",
    "RULES",
    "HEAVY_KEYWORDS",
    "DISPATCH_KEYWORDS",
    "TOOL_KEYWORDS",
]
