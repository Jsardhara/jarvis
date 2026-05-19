"""Stream-event generators extracted from ``jarvis.agent``.

These are the short-circuit branches of :meth:`JarvisChat.stream` that
do NOT use the persistent SDK client — they each run a one-shot model
call and synthesize the model→text→done event sequence the dashboard
expects.

Moved here from ``agent.py`` to keep that file under the 800-line cap
from CLAUDE.md. Each helper takes the :class:`JarvisChat` instance as
its first arg and reads the same attributes the methods formerly read
on ``self`` (``_sonnet_model``, ``_last_lane``).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

from jarvis.state.recap import record_turn, record_unified_turn

if TYPE_CHECKING:  # pragma: no cover — avoid runtime circular import
    from jarvis.agent import JarvisChat, StreamEvent

logger = logging.getLogger(__name__)


async def stream_via_link_handler(
    chat: "JarvisChat",
    message: str,
    *,
    surface: Literal["voice", "chat", "api"] = "api",
    session_id: str = "default",
) -> AsyncIterator["StreamEvent"]:
    """Run link_handler in a thread, synthesize stream events from result."""
    # Local imports to avoid a circular at module-load time.
    from jarvis.agent import StreamEvent
    from jarvis.agents.lens import link_handler

    cleaned = message.strip()
    # Sonnet handles link summaries — emit decision badge first.
    decision_model = chat._sonnet_model
    yield StreamEvent(
        "model",
        {
            "model": decision_model,
            "reason": "link_handler — multimodal URL ingestion",
            "tier": 2,
            "manual": False,
            "length_chars": len(cleaned),
        },
    )

    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, link_handler.handle, cleaned)
    except Exception as exc:  # pragma: no cover — already caught inside handle
        yield StreamEvent("error", {"message": f"link_handler failed: {exc}"})
        return

    if resp.action == "no_url":
        yield StreamEvent("text", {"delta": "No URL found in your message."})
        yield StreamEvent("done", {"total_cost_usd": 0.0})
        return

    if resp.action == "failed":
        err = resp.result.get("error", "unknown")
        yield StreamEvent(
            "text",
            {
                "delta": (
                    f"Couldn't process that link — {err}. "
                    "Try a different URL or a public one."
                )
            },
        )
        yield StreamEvent("done", {"total_cost_usd": 0.0})
        return

    summary = str(resp.result.get("summary", "")).strip() or "Nothing useful."
    # Surface the summary in one text event so the UI streams it as a
    # single delta — consistent with the rest of the pipeline.
    yield StreamEvent("text", {"delta": summary})
    yield StreamEvent("done", {"total_cost_usd": 0.0})

    chat._last_lane = decision_model
    record_turn(chat, "user", cleaned, lane=decision_model)
    record_turn(chat, "assistant", summary, lane=decision_model)
    if surface != "chat":
        record_unified_turn(
            user_text=cleaned,
            assistant_text=summary,
            lane=decision_model,
            surface=surface,
            session_id=session_id,
        )


async def stream_via_skill(
    chat: "JarvisChat",
    skill: Any,
    user_text: str,
    *,
    surface: Literal["voice", "chat", "api"] = "api",
    session_id: str = "default",
) -> AsyncIterator["StreamEvent"]:
    """Run a named skill — one-shot Claude call using skill.prompt as system.

    Mirrors :func:`stream_via_link_handler`: emits a model badge, runs the
    skill via the global claude queue in a thread, then synthesizes
    text + done events. Records the turn through the standard pathways
    so it lands in turn-log + unified store like any other reply.
    """
    from jarvis.agent import StreamEvent

    cleaned = (user_text or "").strip()
    decision_model = skill.model or chat._sonnet_model

    yield StreamEvent(
        "model",
        {
            "model": decision_model,
            "reason": f"skill — {skill.slug}",
            "tier": 2,
            "manual": True,
            "length_chars": len(cleaned),
        },
    )

    def _run_skill() -> str:
        from jarvis.llm.queue import submit

        try:
            return submit(
                system=skill.prompt,
                user=cleaned
                or f"(no input — run the {skill.slug} skill with whatever defaults make sense.)",
                model=decision_model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[chat] skill %s failed: %s", skill.slug, exc)
            return f"Sorry, the {skill.slug} skill hit an error."

    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, _run_skill)
    except Exception as exc:  # pragma: no cover — inner already caught
        yield StreamEvent("error", {"message": f"skill failed: {exc}"})
        return

    reply = (reply or "").strip() or "Nothing useful."

    # Cross-skill orchestration (W3.2): append a "try /next-slug" footer
    # when the skill manifest declares ``chains_to``. Operator stays in
    # the driver's seat — the next skill is suggested, not auto-run.
    try:
        from jarvis.skills import render_chain_suggestion

        chain_footer = render_chain_suggestion(skill)
    except Exception as exc:  # noqa: BLE001 — chaining must never break a reply
        logger.debug("[chat] chain suggestion skipped: %s", exc)
        chain_footer = ""
    if chain_footer:
        reply = f"{reply}{chain_footer}"

    yield StreamEvent("text", {"delta": reply})
    yield StreamEvent("done", {"total_cost_usd": 0.0})

    chat._last_lane = decision_model
    # Log with the slash prefix so the turn-log reflects what the
    # operator actually typed.
    logged_user = f"/{skill.slug}"
    if cleaned:
        logged_user = f"{logged_user} {cleaned}"
    record_turn(chat, "user", logged_user, lane=decision_model)
    record_turn(chat, "assistant", reply, lane=decision_model)
    if surface != "chat":
        record_unified_turn(
            user_text=logged_user,
            assistant_text=reply,
            lane=decision_model,
            surface=surface,
            session_id=session_id,
        )


async def stream_with_image(
    chat: "JarvisChat",
    message: str,
    image_b64: str,
    media_type: str = "image/png",
    *,
    surface: Literal["voice", "chat", "api"] = "api",
    session_id: str = "default",
) -> AsyncIterator["StreamEvent"]:
    """Run a multimodal turn with an operator-supplied image.

    Used by the dashboard image-upload path: the user drags or pastes
    an image into the chat panel; the API endpoint receives base64 and
    forwards here. Distinct from :func:`stream_via_screen_vision` which
    captures the operator's own screen.
    """
    from jarvis.agent import StreamEvent

    cleaned = (message or "").strip() or "What's in this image?"
    decision_model = chat._sonnet_model

    yield StreamEvent(
        "model",
        {
            "model": decision_model,
            "reason": "image-attached — multimodal vision",
            "tier": 2,
            "manual": False,
            "length_chars": len(cleaned),
        },
    )

    def _do_vision() -> str:
        from jarvis.llm.queue import submit_multimodal

        block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_b64,
            },
        }
        system = (
            "You are Jarvis. Look at this image Jyot shared and answer "
            "the question grounded in what's visible. Stay terse — "
            "2-3 sentences. Markdown is fine for code or lists."
        )
        try:
            return submit_multimodal(
                system=system,
                content=[
                    block,
                    {"type": "text", "text": cleaned},
                ],
                model=decision_model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[chat] image-attached vision call failed: %s", exc)
            return "Sorry, I had trouble reading that image."

    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, _do_vision)
    except Exception as exc:  # pragma: no cover
        yield StreamEvent("error", {"message": f"image vision failed: {exc}"})
        return

    reply = (reply or "").strip() or "Nothing useful."
    yield StreamEvent("text", {"delta": reply})
    yield StreamEvent("done", {"total_cost_usd": 0.0})

    chat._last_lane = decision_model
    record_turn(chat, "user", cleaned, lane=decision_model)
    record_turn(chat, "assistant", reply, lane=decision_model)
    if surface != "chat":
        record_unified_turn(
            user_text=cleaned,
            assistant_text=reply,
            lane=decision_model,
            surface=surface,
            session_id=session_id,
        )


async def stream_via_screen_vision(
    chat: "JarvisChat",
    message: str,
    *,
    surface: Literal["voice", "chat", "api"] = "api",
    session_id: str = "default",
) -> AsyncIterator["StreamEvent"]:
    """Capture the operator's screen and run a multimodal Sonnet call.

    Synthesizes stream events from the single-shot multimodal reply so the
    dashboard UI receives the same model→text→done sequence it expects
    from a normal SDK turn. Mirrors :func:`stream_via_link_handler`.
    """
    from jarvis.agent import StreamEvent

    cleaned = (message or "").strip() or "What's on my screen right now?"
    decision_model = chat._sonnet_model

    yield StreamEvent(
        "model",
        {
            "model": decision_model,
            "reason": "screen-vision — desktop capture + multimodal",
            "tier": 2,
            "manual": False,
            "length_chars": len(cleaned),
        },
    )

    # Run the blocking screenshot + LLM call in a thread so we don't
    # stall the event loop. Both are inherently synchronous.
    def _do_vision() -> str:
        from jarvis.llm.queue import submit_multimodal
        from jarvis.tools.screen import (
            ScreenCaptureError,
            capture_and_block,
        )

        try:
            block = capture_and_block()
        except ScreenCaptureError as exc:
            logger.warning("[chat] screen capture failed: %s", exc)
            return (
                "I can't see your screen right now — screen capture isn't available."
            )

        system = (
            "You are Jarvis. Look at this screenshot of Jyot's screen and "
            "answer the question grounded in what's actually visible. Stay "
            "terse — 2-3 sentences. Markdown is fine for code or lists."
        )
        try:
            return submit_multimodal(
                system=system,
                content=[
                    block,
                    {"type": "text", "text": cleaned},
                ],
                model=decision_model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[chat] screen vision call failed: %s", exc)
            return "Sorry, I had trouble reading your screen."

    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, _do_vision)
    except Exception as exc:  # pragma: no cover — inner already caught
        yield StreamEvent("error", {"message": f"screen vision failed: {exc}"})
        return

    reply = (reply or "").strip() or "Nothing useful."
    yield StreamEvent("text", {"delta": reply})
    yield StreamEvent("done", {"total_cost_usd": 0.0})

    chat._last_lane = decision_model
    record_turn(chat, "user", cleaned, lane=decision_model)
    record_turn(chat, "assistant", reply, lane=decision_model)
    if surface != "chat":
        record_unified_turn(
            user_text=cleaned,
            assistant_text=reply,
            lane=decision_model,
            surface=surface,
            session_id=session_id,
        )
