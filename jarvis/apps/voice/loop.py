"""Voice loop — wake → STT → handler → spoken reply → TTS.

Voice is a *conversation* channel. Background work happens silently;
the spoken reply is one natural acknowledgement, not a recital of what
the agents did.

- Tier 0/1/2 (cheap_handler local/Haiku/Sonnet) already produce
  spoken-ready text in ``responses.voice.action`` — used as-is.
- Tier 3 (orchestrator dispatch) returns raw work artifacts. Those go
  through ``_humanize_dispatch`` — a single Haiku call that turns the
  dispatch result into one conversational sentence.

J10 — when ``settings.voice_hot_mic`` is set, :func:`run_hot_mic_loop`
replaces the wake-word gate with a continuous-listening + barge-in
loop. The wake-word path stays the default; hot-mic is additive.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterable

from .persona import PERSONA, VOICE_WORD_CAP
from .silence import BargeinDetector
from .speech import clean_for_speech, rewrite_for_speech
from .stt import STTProvider
from .tts import TTSProvider
from .voice_state import set_hot_mic_enabled as _set_hot_mic_enabled
from .voice_state import set_state as _set_voice_state
from .wake import WakeDetector

logger = logging.getLogger(__name__)

HandleFn = Callable[[str], Awaitable[dict]]

HUMANIZER_MODEL = "claude-haiku-4-5"
HUMANIZER_SYSTEM = (
    PERSONA
    + f"\n\nThe operator just gave a voice command. Background agents already ran.\n"
    f"Your only job: acknowledge in ONE spoken sentence ({VOICE_WORD_CAP} words max).\n"
    f"Don't recite the work. Don't list agent names or fields.\n"
    f"If something needs operator review/confirm, say so plainly.\n"
    f"If everything ran clean, confirm + offer one short nudge."
)


def _humanize_dispatch(response: dict) -> str:
    """Turn raw orchestrator dispatch result into one spoken-ready sentence."""
    from jarvis.llm.queue import submit  # type: ignore[import-not-found]

    try:
        artifact = json.dumps(response.get("responses", {}), default=str)[:1500]
    except (TypeError, ValueError):
        artifact = str(response.get("responses", {}))[:1500]

    user_msg = f"Background work output:\n{artifact}\n\nReply in one spoken sentence."

    try:
        reply = submit(system=HUMANIZER_SYSTEM, user=user_msg, model=HUMANIZER_MODEL)
        if isinstance(reply, dict):
            reply = reply.get("text", "")
        reply = (reply or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[voice] humanizer failed: %s", exc)
        reply = ""
    return reply or "Handled. Anything else?"


_STRUCTURAL_HINTS = ("{", "}", "[", "]", "  - ", "  * ")
_MAX_SPOKEN_WORDS = 50


def _talk_pass(text: str, *, source: str | None) -> str:
    """Last-mile spoken pass."""
    cleaned = clean_for_speech(text)
    if not cleaned:
        return ""
    if source == "local":
        return cleaned

    word_count = len(cleaned.split())
    looks_structural = any(h in cleaned for h in _STRUCTURAL_HINTS)
    too_long = word_count > _MAX_SPOKEN_WORDS

    if not looks_structural and not too_long:
        return cleaned

    return rewrite_for_speech(cleaned)


def _spoken_text(response: dict) -> str:
    """Extract or synthesize the spoken-ready line for TTS."""
    if response.get("needs_confirm"):
        return "Need your okay before I run that."

    source = response.get("source")
    responses = response.get("responses") or {}
    voice = responses.get("voice")
    if voice is not None:
        text = (voice.get("result") or {}).get("text") or voice.get("action") or ""
        text = (text or "").strip()
        if text:
            return _talk_pass(text, source=source)
        return "Got it."

    if not responses:
        return "Nothing on that — want me to dig deeper?"

    return _talk_pass(_humanize_dispatch(response), source=source)


async def process_utterance(text: str, handle: HandleFn,
                            tts: TTSProvider) -> tuple[dict, bytes]:
    """Pipeline: text → handler → spoken reply → TTS bytes."""
    response = await handle(text)
    spoken = _spoken_text(response)
    _set_voice_state(
        "tts",
        last_text=text,
        last_reply_source=response.get("source"),
    )
    audio = tts.synthesize(spoken)
    _set_voice_state("idle")
    return response, audio


async def run_voice_loop(detector: WakeDetector, stt: STTProvider, tts: TTSProvider,
                         handle: HandleFn,
                         audio_source: Callable[[], Iterable[bytes]] | None = None):  # pragma: no cover
    """One-shot voice cycle. Real loop wraps this in `while True`."""
    if audio_source is None:
        raise RuntimeError("audio_source required (sounddevice or fixture)")
    _set_voice_state("wake")
    chunks = audio_source()
    if not detector.listen(chunks):
        _set_voice_state("idle")
        return None
    _set_voice_state("stt")
    audio = b"".join(audio_source())
    text = stt.transcribe(audio)
    response, spoken = await process_utterance(text, handle, tts)
    return {"text": text, "response": response, "audio_bytes": len(spoken)}


def _safe_interrupt(tts: TTSProvider) -> bool:
    """Call ``tts.interrupt()`` defensively (providers may lack it)."""
    fn = getattr(tts, "interrupt", None)
    if not callable(fn):
        return False
    try:
        return bool(fn())
    except Exception as exc:  # noqa: BLE001
        logger.warning("[voice] tts.interrupt() failed: %s", exc)
        return False


async def run_hot_mic_loop(
    stt: STTProvider,
    tts: TTSProvider,
    handle: HandleFn,
    audio_source: Callable[[], Iterable[bytes]],
    *,
    detector: BargeinDetector | None = None,
    silence_frames_to_end: int = 24,  # ~720 ms at 30 ms frames
    max_frames: int = 500,            # safety cap (~15 s)
    is_tts_playing: Callable[[], bool] | None = None,
) -> dict | None:
    """One hot-mic cycle: continuously listen, barge-in on speech, send to handle.

    Mirrors :func:`run_voice_loop`'s output shape. Wraps in a ``while True``
    upstream. Safe to call repeatedly - each invocation processes one
    end-to-end utterance and returns.
    """
    det = detector or BargeinDetector()
    _set_hot_mic_enabled(True)
    _set_voice_state("wake")

    frames: list[bytes] = []
    voice_started = False
    silence_count = 0
    interrupted = False

    for total, frame in enumerate(audio_source(), start=1):
        if total > max_frames:
            break
        speech = det.feed(frame)

        if speech and not interrupted and is_tts_playing and is_tts_playing():
            if _safe_interrupt(tts):
                interrupted = True
                logger.info("[voice] hot-mic barge-in - interrupted TTS")

        if speech:
            frames.append(frame)
            voice_started = True
            silence_count = 0
            continue

        if voice_started:
            frames.append(frame)
            silence_count += 1
            if silence_count >= silence_frames_to_end:
                break

    if not frames:
        _set_voice_state("idle")
        return None

    pcm = b"".join(frames)
    _set_voice_state("stt")
    text = stt.transcribe(pcm) if hasattr(stt, "transcribe") else ""
    text = (text or "").strip()
    if not text:
        _set_voice_state("idle")
        return None

    response, audio = await process_utterance(text, handle, tts)
    return {
        "text": text,
        "response": response,
        "audio_bytes": len(audio) if audio else 0,
        "interrupted": interrupted,
    }
