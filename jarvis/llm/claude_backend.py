"""Claude backend — wraps the claude-agent-sdk (Pro/Max OAuth path).

Implements the :class:`jarvis.llm.backend.Backend` Protocol over the existing
``claude_agent_sdk`` calls that ``jarvis.llm.client`` and ``jarvis.llm.queue``
have used since the start of the project. Code logic is preserved 1:1 — the
sync thread-hop pattern, the markdown-fence stripping, the multimodal
stream-input shape — only repackaged behind the Protocol.

This backend is the default until the local vLLM/Ollama backends come online
on the new PC.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

from jarvis.llm.backend import BackendResult, TokenUsage

_QUERY_TIMEOUT_SEC = 120.0
_MULTIMODAL_TIMEOUT_SEC = 180.0


def _extract_usage(msg: Any) -> dict[str, int]:
    """Pull a ``{input_tokens, output_tokens}`` dict off a result message.

    The SDK sometimes carries usage on ``ResultMessage`` / message_delta and
    sometimes does not; callers tolerate the empty case.
    """
    raw = getattr(msg, "usage", None)
    if not isinstance(raw, dict):
        return {}
    return {k: int(v) for k, v in raw.items() if isinstance(v, (int, float))}


def _strip_fences(raw: str) -> str:
    """Tolerate code fences when Claude adds them despite a system prompt request."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: s.rfind("```")]
    return s.strip()


class ClaudeBackend:
    """Backend implementation using ``claude_agent_sdk`` (Pro/Max OAuth)."""

    name = "claude"

    def query(
        self,
        system: str,
        user: str,
        *,
        model: str,
    ) -> BackendResult:
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
                usage_box.update(_extract_usage(msg))
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text:
                            chunks.append(block.text)
            return "".join(chunks)

        text = self._run_in_thread(_run, timeout=_QUERY_TIMEOUT_SEC)
        cleaned = _strip_fences(text)
        usage = (
            TokenUsage(
                input_tokens=usage_box.get("input_tokens", 0),
                output_tokens=usage_box.get("output_tokens", 0),
            )
            if usage_box
            else None
        )
        return BackendResult(text=cleaned, usage=usage, model_id=model)

    def query_multimodal(
        self,
        system: str,
        content: list[dict],
        *,
        model: str,
    ) -> BackendResult:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )

        usage_box: dict[str, int] = {}

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
                usage_box.update(_extract_usage(msg))
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text:
                            chunks.append(block.text)
            return "".join(chunks)

        text = self._run_in_thread(_run, timeout=_MULTIMODAL_TIMEOUT_SEC).strip()
        usage = (
            TokenUsage(
                input_tokens=usage_box.get("input_tokens", 0),
                output_tokens=usage_box.get("output_tokens", 0),
            )
            if usage_box
            else None
        )
        return BackendResult(text=text, usage=usage, model_id=model)

    def is_available(self) -> bool:
        """Importability of ``claude_agent_sdk`` is the cheapest available signal."""
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _run_in_thread(coro_factory, *, timeout: float) -> str:
        """Run ``coro_factory()`` in a fresh thread + event loop.

        Mirrors the existing sync-wrapper pattern so FastAPI threads and
        async callers do not collide on the running loop.
        """
        box: dict[str, Any] = {}

        def runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                box["result"] = loop.run_until_complete(coro_factory())
            except BaseException as exc:  # noqa: BLE001 — surface after join
                box["error"] = exc
            finally:
                loop.close()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if "error" in box:
            raise box["error"]
        return str(box.get("result", ""))


async def query_async(
    system: str,
    user: str,
    *,
    model: str,
) -> BackendResult:
    """Async sibling for callers already running in an event loop.

    Kept narrow because the queue path is sync-first; FastAPI streaming
    handlers can skip the thread hop with this entry point.
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
        usage_box.update(_extract_usage(msg))
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text:
                    chunks.append(block.text)
    cleaned = _strip_fences("".join(chunks))
    usage = (
        TokenUsage(
            input_tokens=usage_box.get("input_tokens", 0),
            output_tokens=usage_box.get("output_tokens", 0),
        )
        if usage_box
        else None
    )
    return BackendResult(text=cleaned, usage=usage, model_id=model)
