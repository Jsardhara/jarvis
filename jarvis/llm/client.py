"""Shared LLM helper — one-shot Claude queries for any subsystem.

Provides a synchronous wrapper around the claude-agent-sdk async query so
both sync callers (Tempo, Scholar) and thread contexts (FastAPI) work without
holding a live event loop.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any


def query_claude_sync(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """One-shot Claude query — sync wrapper that runs an isolated event loop in a thread.

    Uses Claude Code's OAuth (no ANTHROPIC_API_KEY required). Returns the
    assembled text response. Strips leading/trailing markdown fences when
    Claude adds them despite a system-prompt request to omit them.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    async def _run() -> str:
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            permission_mode="bypassPermissions",
        )
        chunks: list[str] = []
        async for msg in query(prompt=user, options=opts):
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
    return raw.strip()
