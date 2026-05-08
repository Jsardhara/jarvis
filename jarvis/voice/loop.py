"""Voice loop — wake → STT → orchestrator → TTS.

The audio I/O loop (microphone in, speaker out) lives in run_voice_loop()
and requires sounddevice; it's stubbed in tests. The pure-Python orchestration
in process_utterance is fully testable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from .stt import STTProvider
from .tts import TTSProvider
from .voice_state import set_state as _set_voice_state
from .wake import WakeDetector

HandleFn = Callable[[str], Awaitable[dict]]


async def process_utterance(text: str, handle: HandleFn,
                            tts: TTSProvider) -> tuple[dict, bytes]:
    """Pipeline: text → orchestrator handle → response → TTS bytes.

    `handle` mirrors `Orchestrator.dispatch` but is decoupled so tests
    can pass a stub.
    """
    response = await handle(text)
    spoken = _voice_summary(response)
    _set_voice_state(
        "tts",
        last_text=text,
        last_reply_source=response.get("source"),
    )
    audio = tts.synthesize(spoken)
    _set_voice_state("idle")
    return response, audio


def _voice_summary(response: dict) -> str:
    """Compress orchestrator output to one terse sentence for voice."""
    if response.get("needs_confirm"):
        return "Confirm needed before acting."
    responses = response.get("responses", {})
    if not responses:
        return "Nothing to report."
    parts = []
    for agent, body in responses.items():
        action = body.get("action", "")
        if agent == "aide":
            counts = body.get("result", {}).get("counts", {})
            parts.append(f"{counts.get('action_required', 0)} action emails")
        elif agent == "chronos":
            count = body.get("result", {}).get("count", 0)
            parts.append(f"{count} events today")
        elif agent == "ledger":
            pnl = body.get("result", {}).get("pnl", {}).get("pnl_pct", 0)
            parts.append(f"PnL {pnl:.1%}")
        else:
            parts.append(f"{agent}: {action}")
    return ", ".join(parts) + "."


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
