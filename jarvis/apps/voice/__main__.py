"""Run the always-on voice loop.

Usage::

    python -m jarvis.apps.voice

Wires the existing :mod:`jarvis.apps.voice` scaffold (wake → STT → orchestrator
→ TTS) to real audio via :mod:`jarvis.apps.voice.audio_io`. Defaults are the
free stack: openWakeWord wake word, faster-whisper local STT, edge-tts
cloud TTS. Each is overridable via env (see :mod:`jarvis.config`).

The loop runs forever. Each iteration:

1. Block in :func:`mic_chunks` waiting for the wake word.
2. After wake, capture the next utterance until 700 ms of silence.
3. STT → text.
4. Forward text to :class:`jarvis.core.orchestrator.Orchestrator.dispatch`.
5. Render reply via ``_spoken_text`` (humanizes dispatch results) and TTS.
6. Play the audio back.

Designed to live as a Windows autostart background process. Logs to
stdout (the launcher pipes to ``%LOCALAPPDATA%\\Jarvis\\logs\\voice.log``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from jarvis.config import get_settings
from .audio_io import collect_until_silence, mic_chunks, play_audio
from .loop import _spoken_text
from .stt import DeepgramSTT, MockSTT, STTProvider, WhisperSTT
from .tts import ElevenLabsTTS, MockTTS, PiperTTS, TTSProvider
from .wake import MockWakeDetector, WakeDetector

logger = logging.getLogger("jarvis.apps.voice")


def _build_wake(settings: Any) -> WakeDetector:
    backend = (settings.voice_wake_backend or "openwakeword").lower()
    if backend == "openwakeword":
        try:
            from .openwakeword_detector import OpenWakeWordDetector

            logger.info("[voice] wake=openwakeword (hey jarvis)")
            return OpenWakeWordDetector()
        except RuntimeError as exc:
            logger.warning("[voice] openwakeword unavailable (%s); using mock", exc)
            return MockWakeDetector(settings.voice_wake_word or "hey jarvis")
    if backend == "porcupine":
        from .wake import PorcupineDetector

        if not settings.picovoice_access_key:
            logger.warning(
                "[voice] PICOVOICE_ACCESS_KEY missing; falling back to mock detector",
            )
            return MockWakeDetector(settings.voice_wake_word or "hey jarvis")
        logger.info("[voice] wake=porcupine")
        return PorcupineDetector(access_key=settings.picovoice_access_key)
    logger.info("[voice] wake=mock (%s)", settings.voice_wake_word)
    return MockWakeDetector(settings.voice_wake_word or "hey jarvis")


def _build_stt(settings: Any) -> STTProvider:
    engine = (settings.voice_engine_stt or "whisper-local").lower()
    if engine == "deepgram":
        if not settings.deepgram_api_key:
            logger.warning("[voice] DEEPGRAM_API_KEY missing; using mock STT")
            return MockSTT()
        logger.info("[voice] stt=deepgram nova-2")
        return DeepgramSTT(api_key=settings.deepgram_api_key)
    if engine == "mock":
        return MockSTT()
    logger.info("[voice] stt=whisper-local %s", settings.voice_whisper_model)
    return WhisperSTT(model_name=settings.voice_whisper_model)


def _build_tts(settings: Any) -> TTSProvider:
    engine = (settings.voice_engine_tts or "edge-tts").lower()
    if engine == "elevenlabs":
        if not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
            logger.warning("[voice] ElevenLabs creds missing; using edge-tts instead")
            engine = "edge-tts"
        else:
            logger.info("[voice] tts=elevenlabs voice=%s", settings.elevenlabs_voice_id)
            return ElevenLabsTTS(
                api_key=settings.elevenlabs_api_key,
                voice_id=settings.elevenlabs_voice_id,
            )
    if engine == "piper":
        from os import environ

        model = environ.get("PIPER_MODEL_PATH", "")
        logger.info("[voice] tts=piper model=%s", model)
        return PiperTTS(model_path=model)
    if engine == "mock":
        return MockTTS()
    from .edge_tts_provider import EdgeTTSProvider

    logger.info("[voice] tts=edge-tts voice=%s", settings.voice_name)
    return EdgeTTSProvider(voice=settings.voice_name)


async def _dispatch_factory():
    """Return the cheap-handler entrypoint.

    Voice queries are routed through :mod:`jarvis.apps.voice.cheap_handler`
    which itself escalates to the full ``Orchestrator.dispatch`` for
    state-changing requests. Same Jarvis brain, cheapest tier per query.
    """
    from .cheap_handler import handle as _handle

    return _handle


async def run_forever() -> None:
    settings = get_settings()
    if not settings.voice_enabled:
        logger.warning(
            "[voice] VOICE_ENABLED=false in env; exiting. Set VOICE_ENABLED=true to start.",
        )
        return
    wake = _build_wake(settings)
    stt = _build_stt(settings)
    tts = _build_tts(settings)
    try:
        handle = await _dispatch_factory()
    except Exception as exc:  # noqa: BLE001 — registry import optional in dev
        logger.warning(
            "[voice] orchestrator wiring failed (%s); replies will be terse echo",
            exc,
        )

        async def handle(text: str) -> dict[str, Any]:
            return {"responses": {"echo": {"action": text}}}

    logger.info(
        "[voice] loop started — say '%s' to talk", settings.voice_wake_word,
    )

    # Spawn proactive alert channel — daemon → voice bridge for severity=='alert'.
    from . import proactive

    proactive_task = asyncio.create_task(proactive.run(tts))
    logger.info("[voice] proactive alert channel spawned")

    while True:
        try:
            await _one_cycle(wake, stt, tts, handle)
        except KeyboardInterrupt:
            logger.info("[voice] stopped by user")
            proactive_task.cancel()
            break
        except Exception as exc:  # noqa: BLE001 — keep loop alive across faults
            logger.exception("[voice] cycle error: %s", exc)


async def _one_cycle(
    wake: WakeDetector,
    stt: STTProvider,
    tts: TTSProvider,
    handle: Any,
) -> None:
    from .chime import load_chime
    from .fillers import load_filler_bytes

    chunks = mic_chunks()
    if not wake.listen(chunks):
        return
    logger.info("[voice] wake detected — listening for utterance")

    # Phase 2 — instant chime so operator knows we heard the wake word.
    try:
        play_audio(load_chime(), blocking=False)
    except Exception as exc:  # noqa: BLE001 — chime is decorative
        logger.warning("[voice] chime play failed: %s", exc)

    pcm = collect_until_silence(mic_chunks())
    if not pcm:
        logger.info("[voice] silence — skipping")
        return
    text = stt.transcribe(pcm) if hasattr(stt, "transcribe") else ""
    text = text.strip()
    if not text:
        logger.info("[voice] empty transcription — skipping")
        return
    logger.info("[voice] heard: %s", text[:200])

    # Phase 2 — kick off filler in the background while the LLM runs.
    # Skip filler when the query will be answered by a local pattern
    # (those return in <50ms; the filler would arrive AFTER the reply).
    from .cheap_patterns import match as _local_match

    will_be_local = _local_match(text) is not None
    if not will_be_local:
        filler_bytes = load_filler_bytes()
        if filler_bytes:
            try:
                play_audio(filler_bytes, blocking=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[voice] filler play failed: %s", exc)

    response = await handle(text)
    spoken = _spoken_text(response)
    logger.info("[voice] reply: %s", spoken[:200])
    audio = tts.synthesize(spoken)
    if audio:
        play_audio(audio)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
