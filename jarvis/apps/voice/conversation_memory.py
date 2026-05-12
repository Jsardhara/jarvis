"""In-process short-term conversation memory for voice.

Ring buffer of the last few (user, jarvis) exchanges. Process-lifetime only —
persistent memory is a separate concern (claude-mem integration).

Used by ``cheap_handler._ask_claude`` to inject prior turns into the system
context block, and reset by the local ``start fresh`` / ``forget that``
patterns in ``cheap_patterns``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

MAX_TURNS = 6


@dataclass(frozen=True)
class Exchange:
    """One (operator, jarvis) turn pair."""
    ts: datetime
    user: str
    jarvis: str


_BUFFER: deque[Exchange] = deque(maxlen=MAX_TURNS)
_LOCK = Lock()


def remember(user: str, jarvis: str) -> None:
    """Append one turn. Skip if either side is empty."""
    if not user or not jarvis:
        return
    if not user.strip() or not jarvis.strip():
        return
    with _LOCK:
        _BUFFER.append(Exchange(
            ts=datetime.now(UTC),
            user=user.strip(),
            jarvis=jarvis.strip(),
        ))


def recent(n: int = MAX_TURNS) -> tuple[Exchange, ...]:
    """Last ``n`` exchanges in chronological order. Returns immutable tuple."""
    with _LOCK:
        items = list(_BUFFER)
    if n >= len(items):
        return tuple(items)
    return tuple(items[-n:])


def render_for_prompt(n: int = MAX_TURNS) -> str:
    """Format recent turns as system-prompt context. Empty string if no history."""
    turns = recent(n)
    if not turns:
        return ""
    lines = []
    for ex in turns:
        lines.append(f"Operator: {ex.user}")
        lines.append(f"Jarvis: {ex.jarvis}")
    return "\n".join(lines)


def clear() -> None:
    """Drop all stored exchanges."""
    with _LOCK:
        _BUFFER.clear()
