"""Shared LLM helper — one-shot queries routed through the backend abstraction.

Public API is unchanged from the pre-abstraction version: ``query_claude_sync``
and ``query_claude_async`` keep their signatures so every caller in
``jarvis.agents.*``, ``jarvis.apps.*`` and ``jarvis.llm.queue`` keeps working.

Internally each call now goes through
:func:`jarvis.llm.backend_router.get_backend_for_agent` — by default that
returns :class:`jarvis.llm.claude_backend.ClaudeBackend` (today's behaviour),
but flipping ``JARVIS_LLM_BACKEND`` or ``JARVIS_LLM_BACKEND_<agent>``
re-routes to vLLM or Ollama without code changes at the call site.

The function names retain the ``_claude`` suffix for backwards compatibility
with the existing codebase. The name is now misleading-on-purpose: a call to
``query_claude_sync`` with ``JARVIS_LLM_BACKEND=vllm`` set targets vLLM. Rename
to ``query_sync`` / ``query_async`` lands in a future cleanup pass — not in P1
because that would touch every call site.
"""
from __future__ import annotations

import contextlib
import logging

from jarvis.llm.backend import BackendResult, TokenUsage

log = logging.getLogger(__name__)


# Rough char-to-token heuristic for backends that don't surface usage.
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
    usage: TokenUsage | None,
) -> None:
    """Append a cost row for this call.

    Prefers real token counts from the backend when available; falls back
    to a char-count heuristic so the dashboard's daily rollup is never
    empty just because a local backend doesn't surface usage.
    """
    if usage is not None:
        in_tokens = int(usage.input_tokens)
        out_tokens = int(usage.output_tokens)
    else:
        in_tokens = _estimate_tokens(system) + _estimate_tokens(user)
        out_tokens = _estimate_tokens(output_text)
    with contextlib.suppress(Exception):
        # Late import so test fixtures can monkeypatch jarvis.llm.cost.log_cost
        # and so a missing state_dir on cold startup never breaks an LLM call.
        from jarvis.llm.cost import log_cost

        log_cost(agent=agent, model=model, in_tokens=in_tokens, out_tokens=out_tokens)


def _record_result(
    *,
    agent: str,
    model: str,
    system: str,
    user_text: str,
    result: BackendResult,
) -> str:
    """Common post-processing: cost logging + unwrap to ``str``."""
    _record_cost(
        agent=agent,
        model=model,
        system=system,
        user=user_text,
        output_text=result.text,
        usage=result.usage,
    )
    return result.text


def query_claude_sync(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    agent: str = "jarvis",
) -> str:
    """One-shot LLM query — sync entry point.

    Picks a backend via :func:`backend_router.get_backend_for_agent` based on
    env-var configuration. Default backend is Claude (Pro/Max OAuth via
    ``claude-agent-sdk``). Other supported backends today: vLLM, Ollama —
    both stubs until the local PC is online.

    Every call records a row in ``state/cost_log.jsonl`` via
    :func:`jarvis.llm.cost.log_cost`. ``agent`` attributes the spend so the
    dashboard can break costs out per subsystem.
    """
    from jarvis.llm.backend_router import get_backend_for_agent

    backend = get_backend_for_agent(agent)
    result = backend.query(system=system, user=user, model=model)
    return _record_result(
        agent=agent,
        model=model,
        system=system,
        user_text=user,
        result=result,
    )


async def query_claude_async(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    agent: str = "jarvis",
) -> str:
    """One-shot LLM query — async entry point.

    For Claude this avoids the sync-wrapper thread hop by calling the async
    sibling directly. For other backends today, no async path is implemented
    yet — calls fall back to running the sync method (acceptable because
    those backends are stubs that immediately raise ``NotImplementedError``).
    """
    from jarvis.llm.backend_router import get_backend_for_agent
    from jarvis.llm.claude_backend import ClaudeBackend, query_async

    backend = get_backend_for_agent(agent)
    if isinstance(backend, ClaudeBackend):
        result = await query_async(system=system, user=user, model=model)
    else:
        result = backend.query(system=system, user=user, model=model)
    return _record_result(
        agent=agent,
        model=model,
        system=system,
        user_text=user,
        result=result,
    )


def query_multimodal_sync(
    system: str,
    content: list[dict],
    model: str = "claude-sonnet-4-6",
    agent: str = "jarvis",
) -> str:
    """One-shot multimodal query — sync entry point.

    Used by the queue's ``submit_multimodal`` and bypassing callers in the
    lens link-handler. Same backend routing as :func:`query_claude_sync`.
    """
    from jarvis.llm.backend_router import get_backend_for_agent

    backend = get_backend_for_agent(agent)
    result = backend.query_multimodal(system=system, content=content, model=model)
    # User-text proxy for cost heuristic: first text block, if any.
    user_text = _first_text_block(content)
    return _record_result(
        agent=agent,
        model=model,
        system=system,
        user_text=user_text,
        result=result,
    )


def _first_text_block(content: list[dict]) -> str:
    """Pull the first ``text`` block out of a content list for cost-estimation."""
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                return text
    return ""


