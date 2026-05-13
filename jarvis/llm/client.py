"""Shared LLM helper — one-shot Claude queries for any subsystem.

Provides a synchronous wrapper around the claude-agent-sdk async query so
both sync callers (Tempo, Scholar) and thread contexts (FastAPI) work without
holding a live event loop.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)


# Rough char-to-token heuristic when the SDK does not surface usage counts.
# Claude's tokenizer averages ~3.8 chars/token in English; use 4 for safety.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _record_cost(
    agent: str,
    model: str,
    system: str,
    user: str,
    output_text: str,
    usage: dict[str, int] | None = None,
) -> None:
    """Append a cost row for this Claude call.

    Prefers real usage numbers when the SDK exposes them on a ResultMessage;
    falls back to a character-count heuristic so headless dashboards still
    chart non-zero spend.
    """
    if usage is not None:
        in_tokens = int(usage.get("input_tokens", 0) or 0)
        out_tokens = int(usage.get("output_tokens", 0) or 0)
    else:
        in_tokens = _estimate_tokens(system) + _estimate_tokens(user)
        out_tokens = _estimate_tokens(output_text)
    with contextlib.suppress(Exception):
        # Late import so test fixtures can monkeypatch jarvis.llm.cost.log_cost
        # and so a missing state_dir on cold startup never breaks an LLM call.
        from jarvis.llm.cost import log_cost

        log_cost(agent=agent, model=model, in_tokens=in_tokens, out_tokens=out_tokens)


def query_claude_sync(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    agent: str = "jarvis",
) -> str:
    """One-shot Claude query — sync wrapper that runs an isolated event loop in a thread.

    Uses Claude Code's OAuth (no ANTHROPIC_API_KEY required). Returns the
    assembled text response. Strips leading/trailing markdown fences when
    Claude adds them despite a system-prompt request to omit them.

    Every call records a row in ``state/cost_log.jsonl`` via
    :func:`jarvis.llm.cost.log_cost` so the dashboard's daily rollup is
    accurate. ``agent`` lets the caller attribute the spend (tempo/scholar/…)
    rather than a generic bucket.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    usage_box: dict[str, int] = {}

    async def _run() -> str:
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            permission_mode="bypassPermissions",
        )
        chunks: list[str] = []
        async for msg in query(prompt=user, options=opts):
            # ResultMessage / message_delta may carry usage; capture if present
            maybe_usage = getattr(msg, "usage", None)
            if isinstance(maybe_usage, dict):
                usage_box.update(
                    {
                        k: int(v)
                        for k, v in maybe_usage.items()
                        if isinstance(v, (int, float))
                    }
                )
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        chunks.append(block.text)
        return "".join(chunks)

    box: dict[str, Any] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["result"] = loop.run_until_complete(_run())
        except Exception as exc:  # surface to caller
            box["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout=120)
    if "error" in box:
        raise box["error"]
    raw = str(box.get("result", "")).strip()
    # Tolerate code fences if Claude adds them despite the system prompt
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    cleaned = raw.strip()
    _record_cost(
        agent=agent,
        model=model,
        system=system,
        user=user,
        output_text=cleaned,
        usage=usage_box or None,
    )
    return cleaned


async def query_claude_async(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    agent: str = "jarvis",
) -> str:
    """Async sibling of :func:`query_claude_sync`.

    Kept narrow on purpose — most subsystems share the sync wrapper through
    the global queue. Exposed so async-native callers (FastAPI streaming
    handlers) can avoid the thread hop while still recording cost.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    usage_box: dict[str, int] = {}
    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=system,
        permission_mode="bypassPermissions",
    )
    chunks: list[str] = []
    async for msg in query(prompt=user, options=opts):
        maybe_usage = getattr(msg, "usage", None)
        if isinstance(maybe_usage, dict):
            usage_box.update(
                {
                    k: int(v)
                    for k, v in maybe_usage.items()
                    if isinstance(v, (int, float))
                }
            )
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    raw = "".join(chunks).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    cleaned = raw.strip()
    _record_cost(
        agent=agent,
        model=model,
        system=system,
        user=user,
        output_text=cleaned,
        usage=usage_box or None,
    )
    return cleaned
