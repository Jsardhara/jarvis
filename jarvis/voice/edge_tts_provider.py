"""Free TTS provider using Microsoft's Edge cloud Neural voices via ``edge-tts``.

No API key required — Microsoft serves the same TTS endpoint Edge browser
uses for the read-aloud feature. Voice quality is comparable to ElevenLabs'
free tier on most voices and is **completely free** under reasonable use.

Implements :class:`jarvis.voice.tts.TTSProvider` (sync ``synthesize``)
even though the underlying library is async — we run a fresh event loop
internally so callers can stay sync.

Voice names follow Microsoft's catalog (``en-US-AndrewMultilingualNeural``,
``en-GB-RyanNeural``, etc). Full list:

    edge-tts --list-voices

Default voice is locked after Phase B's blind A/B (operator selects via
``scripts/voice_sample.py --select <voice>`` which writes ``VOICE_NAME``
to ``.env``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"


class EdgeTTSProvider:
    """Microsoft Edge cloud Neural TTS — free, no key.

    Returns MP3 bytes. Pair with :func:`jarvis.voice.audio_io.play_audio`
    which decodes via the standard library only.
    """

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch

    def synthesize(self, text: str) -> bytes:
        """Block until the full clip is synthesized; return MP3 bytes."""
        if not text or not text.strip():
            return b""
        try:
            return asyncio.run(self._synthesize_async(text))
        except RuntimeError as exc:
            # Already inside an event loop — synthesize on a worker thread.
            if "asyncio.run() cannot be called" in str(exc):
                import threading

                buf: dict[str, bytes] = {"data": b""}

                def _runner() -> None:
                    buf["data"] = asyncio.run(self._synthesize_async(text))

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                t.join()
                return buf["data"]
            raise

    async def _synthesize_async(self, text: str) -> bytes:
        try:
            import edge_tts  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts not installed — pip install -e '.[voice]'"
            ) from exc

        communicate = edge_tts.Communicate(
            text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
        )
        chunks: list[bytes] = []
        async for event in communicate.stream():
            if event.get("type") == "audio":
                chunks.append(event.get("data", b""))
        return b"".join(chunks)


async def list_voices(language: str | None = None) -> list[dict[str, Any]]:
    """Return the Edge voice catalog. Useful for the Phase B A/B script.

    Pass e.g. ``language='en'`` to filter to English voices.
    """
    try:
        import edge_tts  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("edge-tts not installed") from exc
    voices = await edge_tts.list_voices()
    if language:
        voices = [v for v in voices if v.get("Locale", "").startswith(language)]
    return voices


__all__ = ["EdgeTTSProvider", "DEFAULT_VOICE", "list_voices"]
