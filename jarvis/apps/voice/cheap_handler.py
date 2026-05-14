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

Returns the dict shape the voice loop expects (matching
:class:`jarvis.core.orchestrator.Orchestrator.dispatch`'s output) — Tier 0/1/2
populate ``responses.voice`` with spoken-ready text, Tier 3 leaves raw
agent artifacts for ``_spoken_text`` to humanize.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from . import conversation_memory
from .cheap_patterns import (
    has_dispatch_keyword,
    has_heavy_keyword,
    has_tool_keyword,
    match,
)
from .context_cache import load_voice_context, render_for_prompt
from .persona import PERSONA
from .voice_state import set_state as _set_voice_state

logger = logging.getLogger(__name__)

# Stable per-process session_id so turns from one voice run can be grouped
# in the dashboard. Falls back to a fresh UUID per process start.
_VOICE_SESSION_ID = os.environ.get("JARVIS_VOICE_SESSION_ID") or uuid4().hex

VOICE_SYSTEM_PROMPT = (
    PERSONA
    + "\n\nCONTEXT\n{context_block}\n\nRECENT EXCHANGES\n{memory_block}\n"
    + "\n{cross_surface_block}{semantic_block}"
)

_VOICE_CHAT_TURN_LIMIT = 20
_VOICE_CHAT_TURN_TRUNC = 200
_VOICE_SEMANTIC_TOP_K = 3

DEFAULT_HAIKU_MODEL = "claude-haiku-4-5"
DEFAULT_SONNET_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 120

# Module-level cache so "repeat" can replay the last reply.
_LAST_REPLY: dict[str, str] = {"text": ""}


def _persist_voice_turn(user_text: str, assistant_text: str, *, source: str) -> None:
    """Append a voice turn to the unified ``chat_turns.jsonl`` store.

    Called once per voice utterance regardless of tier (local / haiku /
    sonnet / link). Tier 3 (agent-brain) writes its own unified record
    through ``JarvisChat`` so we skip it here to avoid double-writing.
    Best-effort: any failure is logged and swallowed — voice must never
    crash on persistence.
    """
    if not user_text or not assistant_text:
        return
    try:
        from jarvis.state.chat_turns import ChatTurnRecord, append_turn

        rec = ChatTurnRecord(
            user_id="default",
            turn_id=uuid4().hex,
            user_text=user_text,
            assistant_text=assistant_text,
            model=source,
            ts=datetime.now(UTC).isoformat(),
            session_id=_VOICE_SESSION_ID,
            surface="voice",
        )
        append_turn(rec)
    except Exception as exc:  # noqa: BLE001 — voice never crashes on persistence
        logger.warning("[voice] chat_turns append failed: %s", exc)


def _wrap(reply: str, *, source: str) -> dict[str, Any]:
    """Match Orchestrator.dispatch shape; voice tier carries spoken-ready text."""
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
        reply = _LAST_REPLY["text"] or "Nothing to repeat."
        _persist_voice_turn(text, reply, source="local-repeat")
        return _wrap(reply, source="local")
    _LAST_REPLY["text"] = local
    _persist_voice_turn(text, local, source="local")
    return _wrap(local, source="local")


def _render_recent_chat_turns(records: list[Any]) -> str:
    """Render unified chat_turns records as a compact prompt block.

    Truncates each user/assistant payload to ``_VOICE_CHAT_TURN_TRUNC``
    chars so even a long history doesn't blow the prompt budget. Returns
    an empty string when *records* is empty so the caller can drop the
    section cleanly.
    """
    if not records:
        return ""
    lines = [
        f"Recent conversation (last {_VOICE_CHAT_TURN_LIMIT} turns, mixed voice + chat):"
    ]
    for rec in records:
        surface = getattr(rec, "surface", "chat") or "chat"
        user_text = (getattr(rec, "user_text", "") or "")[:_VOICE_CHAT_TURN_TRUNC]
        asst_text = (getattr(rec, "assistant_text", "") or "")[:_VOICE_CHAT_TURN_TRUNC]
        if user_text:
            lines.append(f"[{surface}] user: {user_text}")
        if asst_text:
            lines.append(f"[{surface}] you: {asst_text}")
    return "\n".join(lines)


def _render_semantic_hits(text: str) -> str:
    """Return top-K semantic hits as a prompt block, or empty string.

    Wrapped in try/except so a missing ``sentence-transformers`` or any
    other failure inside ``memory_index.search`` doesn't crash the voice
    path. Short-circuits when the index file is absent so we don't pay
    the embedding cost on an empty store.
    """
    try:
        from jarvis.state.memory_index import (  # type: ignore[import-not-found]
            _get_index_path,
            search,
        )

        if not _get_index_path().exists():
            return ""
        hits = search(text, top_k=_VOICE_SEMANTIC_TOP_K)
    except Exception as exc:  # noqa: BLE001 — voice never crashes on memory fail
        logger.debug("[voice] semantic search skipped: %s", exc)
        return ""
    if not hits:
        return ""
    lines = ["Possibly relevant past turns:"]
    for score, turn in hits:
        snippet = (turn.text or "").strip().replace("\n", " ")[:_VOICE_CHAT_TURN_TRUNC]
        lines.append(f"- [{turn.role} @ {score:.2f}] {snippet}")
    return "\n".join(lines)


def _load_cross_surface_records() -> list[Any]:
    """Read recent chat_turns; return empty list on any failure."""
    try:
        from jarvis.state.chat_turns import read_recent  # type: ignore[import-not-found]

        return read_recent(user_id="default", limit=_VOICE_CHAT_TURN_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[voice] chat_turns read skipped: %s", exc)
        return []


async def _ask_claude(text: str, model: str) -> dict[str, Any]:
    """Single Claude call routed through claude_queue.submit."""
    from jarvis.llm.queue import submit  # type: ignore[import-not-found]

    context = load_voice_context()
    memory_block = conversation_memory.render_for_prompt() or "(none)"
    cross_surface = _render_recent_chat_turns(_load_cross_surface_records())
    semantic = _render_semantic_hits(text)
    cross_surface_block = f"\n{cross_surface}\n" if cross_surface else ""
    semantic_block = f"\n{semantic}\n" if semantic else ""
    system = VOICE_SYSTEM_PROMPT.format(
        context_block=render_for_prompt(context),
        memory_block=memory_block,
        cross_surface_block=cross_surface_block,
        semantic_block=semantic_block,
    )
    try:
        reply = submit(system=system, user=text, model=model)
        if isinstance(reply, dict):  # some queue paths return dict
            reply = reply.get("text", "")
    except Exception as exc:  # noqa: BLE001 — voice should never crash on LLM fail
        logger.warning("[voice] %s call failed: %s", model, exc)
        reply = "Sorry, I had trouble with that."
    reply = (reply or "").strip()
    if reply:
        _LAST_REPLY["text"] = reply
        conversation_memory.remember(text, reply)
        _persist_voice_turn(text, reply, source=model)
    return _wrap(reply, source=model)


async def _orchestrator_fallback(text: str) -> dict[str, Any]:
    """Legacy orchestrator-only path. Used if the Agent SDK brain fails."""
    try:
        from jarvis.agents.registry import build_default_registry  # type: ignore[import-not-found]
        from jarvis.core.orchestrator import Orchestrator  # type: ignore[import-not-found]

        reg = build_default_registry()
        orch = Orchestrator(reg)
        result = await orch.dispatch(text)
        responses = result.get("responses", {})
        spoken_for_persist = ""
        if responses:
            first = next(iter(responses.values()), {})
            spoken_for_persist = first.get("action") or ""
            _LAST_REPLY["text"] = spoken_for_persist or _LAST_REPLY["text"]
        result.setdefault("source", "orchestrator")
        if spoken_for_persist:
            _persist_voice_turn(text, spoken_for_persist, source="orchestrator")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("[voice] orchestrator dispatch failed: %s", exc)
        return _wrap(
            "I had trouble routing that. Try again or use the dashboard.",
            source="orchestrator-error",
        )


_JARVIS_CHAT_SINGLETON: dict[str, Any] = {"instance": None}


def _shared_jarvis_chat():
    """Lazily build and cache the unified JarvisChat instance.

    Voice and dashboard chat share this single brain so memory, tools, and
    persona stay in sync across surfaces.
    """
    inst = _JARVIS_CHAT_SINGLETON.get("instance")
    if inst is not None:
        return inst
    from jarvis.agent import JarvisChat  # type: ignore[import-not-found]
    from jarvis.agents.registry import build_default_registry  # type: ignore[import-not-found]

    inst = JarvisChat(registry=build_default_registry())
    _JARVIS_CHAT_SINGLETON["instance"] = inst
    return inst


async def _full_dispatch(text: str) -> dict[str, Any]:
    """Tier-3 — route voice through the shared JarvisChat brain.

    Falls back to the legacy Orchestrator path only if JarvisChat itself
    raises or can't be imported in this environment.
    """
    try:
        chat = _shared_jarvis_chat()
        # surface="voice" + session_id flow into JarvisChat.stream and on to
        # the unified chat_turns.jsonl writer so the dashboard sees this
        # voice utterance. JarvisChat does the write itself — do NOT call
        # _persist_voice_turn here (would double-write).
        result = await chat.respond_single(
            text, surface="voice", session_id=_VOICE_SESSION_ID
        )
        responses = result.get("responses", {})
        block = responses.get("agent_brain") or responses.get("voice") or {}
        spoken = (block.get("result") or {}).get("text") or block.get("action")
        if spoken:
            _LAST_REPLY["text"] = spoken
        result.setdefault("source", "jarvis-chat")
        return result
    except Exception as exc:  # noqa: BLE001 — voice never crashes on brain fail
        logger.warning("[voice] JarvisChat unavailable (%s) — falling back", exc)
        return await _orchestrator_fallback(text)


async def _link_response(text: str) -> dict[str, Any]:
    """Run multimodal link_handler in a thread, wrap result for voice."""
    import asyncio

    from jarvis.agents.lens import link_handler

    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(None, link_handler.handle, text)
    summary = ""
    if resp.action == "summarized":
        summary = str(resp.result.get("summary", "")).strip()
    elif resp.action == "failed":
        summary = "Couldn't process that link. Try a different one."
    else:
        summary = "No URL found."
    if summary:
        _LAST_REPLY["text"] = summary
        conversation_memory.remember(text, summary)
        _persist_voice_turn(text, summary, source="link_handler")
    return _wrap(summary or "Nothing useful.", source="link_handler")


async def handle(text: str) -> dict[str, Any]:
    """Route a voice query to the cheapest tier that can answer.

    Matches the ``HandleFn`` signature the voice loop expects.
    """
    text = (text or "").strip()
    if not text:
        return _wrap("", source="empty")

    # Operator-presence mark: every non-empty voice turn counts as activity.
    # Best-effort; never lets the presence hook break voice routing.
    try:
        from jarvis.state.operator_presence import mark_present

        mark_present("voice")
    except Exception as exc:  # noqa: BLE001
        logger.debug("operator_presence mark skipped: %s", exc)

    # URL detected → multimodal link_handler runs before any tier routing.
    from jarvis.agents.lens import link_handler

    if link_handler.extract_urls(text):
        logger.info("[voice] tier=link_handler (URL detected)")
        _set_voice_state("routing", tier="link_handler", last_text=text)
        return await _link_response(text)

    # Tier 0 — local pattern match, no LLM.
    local = _local_response(text)
    if local is not None:
        _set_voice_state("routing", tier="local", last_text=text)
        return local

    # Tier 3 — state-changing or tool-needing utterances route to the
    # Claude Agent SDK brain (file ops, GUI control, sub-agent dispatch).
    if has_dispatch_keyword(text) or has_tool_keyword(text):
        logger.info("[voice] tier=agent-brain (dispatch/tool keyword)")
        _set_voice_state("routing", tier="agent-brain", last_text=text)
        return await _full_dispatch(text)

    # Tier 2 — heavy reasoning keywords escalate to Sonnet.
    if has_heavy_keyword(text):
        logger.info("[voice] tier=sonnet (heavy keyword)")
        _set_voice_state("routing", tier="sonnet", last_text=text)
        return await _ask_claude(text, DEFAULT_SONNET_MODEL)

    # Tier 1 — default. Haiku + cached context.
    logger.info("[voice] tier=haiku")
    _set_voice_state("routing", tier="haiku", last_text=text)
    return await _ask_claude(text, DEFAULT_HAIKU_MODEL)


__all__ = [
    "handle",
    "VOICE_SYSTEM_PROMPT",
    "DEFAULT_HAIKU_MODEL",
    "DEFAULT_SONNET_MODEL",
    "DEFAULT_MAX_TOKENS",
]
