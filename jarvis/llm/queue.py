"""Pro/Max-routed Claude queue.

Known bypass sites (call query_claude_sync directly, skipping this queue):
    * jarvis/agents/scholar/agent.py:42 — direct call for fast study tasks
    * jarvis/agents/tempo/agent.py:131 — direct call (being fixed by parallel agent)

Every other subsystem must route through :func:`submit` / :func:`submit_multimodal`
so the shared 5h Pro/Max rate-limit bucket stays under one global lock.

Single global FIFO funnel for every LLM call in Jarvis. All subsystems use
``query_claude_sync`` from ``jarvis.llm.client``, which authenticates through the
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
    from jarvis.llm.client import query_claude_sync

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
# Multimodal — claude-agent-sdk stream-input path (Pro/Max OAuth)
# ---------------------------------------------------------------------------


def _multimodal_once(
    system: str,
    content: list[dict],
    model: str,
) -> str:
    """One multimodal turn via claude-agent-sdk. Sync wrapper around async query.

    Uses the SDK's stream-input form — ``prompt=AsyncIterable[dict]`` — which
    forwards Anthropic-format content blocks (text/image/document) straight
    through the Claude Code CLI session. Authenticates with the Pro/Max
    OAuth token, never the API key.
    """
    import asyncio
    import threading
    from typing import Any as _Any

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    async def _stream_in():
        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
        }

    async def _run() -> str:
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            permission_mode="bypassPermissions",
        )
        chunks: list[str] = []
        async for msg in query(prompt=_stream_in(), options=opts):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        chunks.append(block.text)
        return "".join(chunks)

    box: dict[str, _Any] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["result"] = loop.run_until_complete(_run())
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout=180)
    if "error" in box:
        raise box["error"]
    return str(box.get("result", "")).strip()


def submit_multimodal(
    system: str,
    content: list[dict],
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 1024,  # kept for API compat; SDK manages tokens
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

    Authenticates through the local Claude Code session (Pro/Max plan),
    not via ANTHROPIC_API_KEY. Same global lock + retry as ``submit``.
    """
    del max_tokens  # SDK path manages output tokens internally
    attempts = len(backoff_sec) + 1
    last_exc: BaseException | None = None

    with _LOCK:
        for i in range(attempts):
            try:
                return _multimodal_once(system, content, model)
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
