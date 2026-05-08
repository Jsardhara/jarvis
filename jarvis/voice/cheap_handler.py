"""Voice query handler with three-tier routing.

Replaces the orchestrator-fanout that the voice loop used to invoke. Same
Jarvis brain — just routed through the cheapest tier that can answer:

  Tier 0 (free)            local regex match → instant response
  Tier 1 (~150 tokens)     Haiku 4.5 + cached fact sheet → status replies
  Tier 2 (~400 tokens)     Sonnet 4.6 → explain/why/code/refactor escalation
  Tier 3 (full dispatch)   Orchestrator.dispatch → state-changing tasks
                           (draft mail, schedule, execute, merge, …)

Heavy keywords (explain, why, code, refactor) → Sonnet.
Dispatch keywords (draft, send, schedule, execute, …) → full orchestrator.
Everything else → Haiku.

Returns the dict shape the existing voice loop expects (matching
:class:`jarvis.orchestrator.Orchestrator.dispatch`'s output) so
``_voice_summary`` can compress for TTS without changes.
"""

from __future__ import annotations

import logging
from typing import Any

from .cheap_patterns import has_dispatch_keyword, has_heavy_keyword, match
from .context_cache import load_voice_context, render_for_prompt

logger = logging.getLogger(__name__)

VOICE_SYSTEM_PROMPT = """You are Jarvis voice. Reply in 1-2 sentences, max 30 words.
Pull facts from CONTEXT below; never invent numbers.
If something isn't in CONTEXT, say "I'd need to check the dashboard for that."

CONTEXT
{context_block}
"""

DEFAULT_HAIKU_MODEL = "claude-haiku-4-5"
DEFAULT_SONNET_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 120

# Module-level cache so "repeat" can replay the last reply.
_LAST_REPLY: dict[str, str] = {"text": ""}


def _wrap(reply: str, *, source: str) -> dict[str, Any]:
    """Match Orchestrator.dispatch shape so _voice_summary works unchanged."""
    return {
        "responses": {
            "voice": {
                "agent": "voice",
                "action": reply,
                "result": {"source": source, "text": reply},
            },
        },
        "needs_confirm": False,
        "source": source,
    }


def _local_response(text: str) -> dict[str, Any] | None:
    local = match(text)
    if local is None:
        return None
    if local == "__REPEAT_LAST__":
        return _wrap(_LAST_REPLY["text"] or "Nothing to repeat.", source="local")
    _LAST_REPLY["text"] = local
    return _wrap(local, source="local")


async def _ask_claude(text: str, model: str) -> dict[str, Any]:
    """Single Claude call routed through claude_queue.submit."""
    from ..claude_queue import submit  # type: ignore[import-not-found]

    context = load_voice_context()
    system = VOICE_SYSTEM_PROMPT.format(context_block=render_for_prompt(context))
    try:
        reply = submit(
            model=model,
            system=system,
            messages=[{"role": "user", "content": text}],
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        if isinstance(reply, dict):  # some queue paths return dict
            reply = reply.get("text", "")
    except Exception as exc:  # noqa: BLE001 — voice should never crash on LLM fail
        logger.warning("[voice] %s call failed: %s", model, exc)
        reply = "Sorry, I had trouble with that."
    reply = (reply or "").strip()
    if reply:
        _LAST_REPLY["text"] = reply
    return _wrap(reply, source=model)


async def _full_dispatch(text: str) -> dict[str, Any]:
    """Fall through to the standard Orchestrator for state-changing tasks.

    Voice is just an input channel here — Jarvis behaves identically to
    a typed dashboard request. Same agents, same confirmation gates,
    same cost.
    """
    try:
        from ..orchestrator import Orchestrator  # type: ignore[import-not-found]
        from ..subsystems.registry import build_default_registry  # type: ignore[import-not-found]

        reg = build_default_registry()
        orch = Orchestrator(reg)
        result = await orch.dispatch(text)
        # Stash the most-relevant action string for "repeat".
        responses = result.get("responses", {})
        if responses:
            first = next(iter(responses.values()), {})
            _LAST_REPLY["text"] = first.get("action") or _LAST_REPLY["text"]
        result.setdefault("source", "orchestrator")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("[voice] orchestrator dispatch failed: %s", exc)
        return _wrap(
            "I had trouble routing that. Try again or use the dashboard.",
            source="orchestrator-error",
        )


async def handle(text: str) -> dict[str, Any]:
    """Route a voice query to the cheapest tier that can answer.

    Matches the ``HandleFn`` signature the voice loop expects.
    """
    text = (text or "").strip()
    if not text:
        return _wrap("", source="empty")

    # Tier 0 — local pattern match, no LLM.
    local = _local_response(text)
    if local is not None:
        return local

    # Tier 3 — state-changing tasks always go through the full orchestrator
    # so the existing tier/authority gates and subsystem dispatches run.
    if has_dispatch_keyword(text):
        logger.info("[voice] tier=orchestrator (dispatch keyword)")
        return await _full_dispatch(text)

    # Tier 2 — heavy reasoning keywords escalate to Sonnet.
    if has_heavy_keyword(text):
        logger.info("[voice] tier=sonnet (heavy keyword)")
        return await _ask_claude(text, DEFAULT_SONNET_MODEL)

    # Tier 1 — default. Haiku + cached context.
    logger.info("[voice] tier=haiku")
    return await _ask_claude(text, DEFAULT_HAIKU_MODEL)


__all__ = [
    "handle",
    "VOICE_SYSTEM_PROMPT",
    "DEFAULT_HAIKU_MODEL",
    "DEFAULT_SONNET_MODEL",
    "DEFAULT_MAX_TOKENS",
]
