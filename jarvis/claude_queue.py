"""Pro/Max-routed Claude queue.

Single global FIFO funnel for every LLM call in Jarvis. All subsystems use
``query_claude_sync`` from ``jarvis.llm``, which authenticates through the
local ``claude-agent-sdk`` (Pro/Max session token) — no Anthropic API key.

Why a queue:

* Pro/Max uses one shared 5h rolling rate-limit bucket per machine.
* Parallel ``claude`` invocations from sentinel + chat + scholar + forge can
  saturate that bucket and trigger 429 rate-limit errors.
* This module serialises all calls and adds exponential backoff retry on
  transient failures.

Public surface:

    submit(system, user, *, model="claude-sonnet-4-6") -> str
        Synchronous. Acquires the global lock, calls
        ``jarvis.llm.query_claude_sync``, retries on rate-limit/overload.
"""

from __future__ import annotations

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

_LOCK = threading.Lock()

# Match Anthropic SDK + CLI rate-limit / overload signals.
_RETRY_PATTERNS = (
    re.compile(r"rate[_ ]?limit", re.I),
    re.compile(r"\b429\b"),
    re.compile(r"overloaded", re.I),
    re.compile(r"\b529\b"),
)

_DEFAULT_BACKOFF_SEC = (60.0, 180.0, 600.0)


def _is_retryable(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(p.search(text) for p in _RETRY_PATTERNS)


def submit(
    system: str,
    user: str,
    *,
    model: str = "claude-sonnet-4-6",
    backoff_sec: tuple[float, ...] = _DEFAULT_BACKOFF_SEC,
) -> str:
    """Run a single Claude turn through the global queue.

    Serialises all callers via ``_LOCK`` so only one ``claude`` invocation
    runs at a time. Retries on rate-limit/overload signals using
    ``backoff_sec`` delays between attempts.

    Raises the final exception if every attempt fails.
    """
    from .llm import query_claude_sync

    attempts = len(backoff_sec) + 1
    last_exc: BaseException | None = None

    with _LOCK:
        for i in range(attempts):
            try:
                return query_claude_sync(system=system, user=user, model=model)
            except BaseException as exc:  # noqa: BLE001 — surface after retries
                last_exc = exc
                if i >= attempts - 1 or not _is_retryable(exc):
                    raise
                delay = backoff_sec[i]
                log.warning(
                    "claude_queue: retryable error (%s) — backoff %.0fs (attempt %d/%d)",
                    type(exc).__name__,
                    delay,
                    i + 1,
                    attempts,
                )
                time.sleep(delay)

    # Unreachable — loop either returns or raises. Belt-and-braces.
    assert last_exc is not None
    raise last_exc
