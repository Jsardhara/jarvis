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

    submit_multimodal(system, content, *, model="claude-sonnet-4-6",
                       max_tokens=1024) -> str
        Multimodal turn — ``content`` is a list of Anthropic content blocks
        (text/image/document). Uses the raw anthropic SDK because the
        claude-agent-sdk only carries plain text. Same global lock + retry.
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


# ---------------------------------------------------------------------------
# Multimodal — raw anthropic SDK (vision / PDF / document blocks)
# ---------------------------------------------------------------------------


def _resolve_anthropic_key() -> str:
    """Return ANTHROPIC_API_KEY env var.

    Multimodal calls go to api.anthropic.com directly, which requires a
    real Anthropic API key (Console billing). The Claude Code Pro/Max
    OAuth token used elsewhere is *not* accepted here.
    """
    import os

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    raise RuntimeError(
        "ANTHROPIC_API_KEY not set. Multimodal (vision/PDF/audio) calls go "
        "through api.anthropic.com and need a real API key — Pro/Max OAuth "
        "won't work here. Get one at https://console.anthropic.com/settings/keys "
        "and add ANTHROPIC_API_KEY=... to your environment."
    )


def submit_multimodal(
    system: str,
    content: list[dict],
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 1024,
    backoff_sec: tuple[float, ...] = _DEFAULT_BACKOFF_SEC,
) -> str:
    """Run a multimodal Claude turn through the global queue.

    ``content`` is a list of Anthropic content blocks — typical shapes:

        {"type": "text", "text": "describe what you see"}
        {"type": "image", "source": {"type": "base64",
                                       "media_type": "image/png",
                                       "data": "<b64>"}}
        {"type": "document", "source": {"type": "base64",
                                          "media_type": "application/pdf",
                                          "data": "<b64>"}}

    Returns the assembled assistant text. Raises after all retries on
    persistent failure.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=_resolve_anthropic_key())
    attempts = len(backoff_sec) + 1
    last_exc: BaseException | None = None

    with _LOCK:
        for i in range(attempts):
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": content}],
                )
                parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
                return "".join(parts).strip()
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                if i >= attempts - 1 or not _is_retryable(exc):
                    raise
                delay = backoff_sec[i]
                log.warning(
                    "claude_queue.multimodal: retryable (%s) — backoff %.0fs (%d/%d)",
                    type(exc).__name__,
                    delay,
                    i + 1,
                    attempts,
                )
                time.sleep(delay)

    assert last_exc is not None
    raise last_exc
