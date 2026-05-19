"""Free TTS provider using Microsoft's Edge cloud Neural voices via ``edge-tts``.

No API key required — Microsoft serves the same TTS endpoint Edge browser
uses for the read-aloud feature. Voice quality is comparable to ElevenLabs'
free tier on most voices and is **completely free** under reasonable use.

Implements :class:`jarvis.apps.voice.tts.TTSProvider` (sync ``synthesize``)
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
import threading
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"


class EdgeTTSProvider:
    """Microsoft Edge cloud Neural TTS — free, no key.

    Returns MP3 bytes. Pair with :func:`jarvis.apps.voice.audio_io.play_audio`
    which decodes via the standard library only.

    Supports cooperative cancellation via :meth:`interrupt` so the J10
    hot-mic barge-in can cut the bot off mid-reply. Cancellation covers
    both legs of the trip:

    * The async ``edge_tts.Communicate.stream()`` task is cancelled, which
      tears down the in-flight HTTP fetch.
    * ``sounddevice.stop()`` is called to abort speaker playback (the
      audio is played by :func:`jarvis.apps.voice.audio_io.play_audio`,
      so we reach into the same module).
    * A cooperative ``_cancelled`` flag is set so the next ``synthesize``
      starts clean and so callers that finished synthesis before the
      interrupt fired can drop the buffered audio.
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
        # Barge-in state. Mutated from the playback thread via
        # ``interrupt()``; read from ``synthesize`` / ``_synthesize_async``.
        self._lock = threading.Lock()
        self._cancelled: bool = False
        self._in_flight: bool = False
        self._active_task: asyncio.Task[Any] | None = None
        self._active_loop: asyncio.AbstractEventLoop | None = None

    def synthesize(self, text: str) -> bytes:
        """Block until the full clip is synthesized; return MP3 bytes.

        Returns ``b""`` if :meth:`interrupt` is called mid-fetch (or was
        called before the call started and not cleared by a subsequent
        speak — the very next ``synthesize`` always clears the flag).
        """
        if not text or not text.strip():
            return b""
        with self._lock:
            self._cancelled = False
            self._in_flight = True
        try:
            try:
                return asyncio.run(self._synthesize_async(text))
            except RuntimeError as exc:
                # Already inside an event loop — synthesize on a worker thread.
                if "asyncio.run() cannot be called" in str(exc):
                    buf: dict[str, bytes] = {"data": b""}

                    def _runner() -> None:
                        try:
                            buf["data"] = asyncio.run(self._synthesize_async(text))
                        except asyncio.CancelledError:
                            buf["data"] = b""

                    t = threading.Thread(target=_runner, daemon=True)
                    t.start()
                    t.join()
                    return buf["data"]
                raise
            except asyncio.CancelledError:
                # Barge-in raced in while we were streaming — drop the buffer.
                return b""
        finally:
            with self._lock:
                self._in_flight = False
                self._active_task = None
                self._active_loop = None

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

        async def _stream() -> bytes:
            chunks: list[bytes] = []
            async for event in communicate.stream():
                if self._cancelled:
                    break
                if event.get("type") == "audio":
                    chunks.append(event.get("data", b""))
            return b"".join(chunks)

        # Register the task so ``interrupt()`` can cancel it from any thread.
        task = asyncio.ensure_future(_stream())
        with self._lock:
            self._active_task = task
            self._active_loop = asyncio.get_running_loop()
            # If interrupt() fired before the task was registered, honour it.
            already_cancelled = self._cancelled
        if already_cancelled:
            task.cancel()
        try:
            return await task
        except asyncio.CancelledError:
            return b""

    def interrupt(self) -> bool:
        """Cancel any in-flight Edge TTS synthesis and stop playback.

        Idempotent. Safe to call from any thread and safe to call when
        nothing is playing — returns ``False`` in that case. Never
        raises: every backend touch is wrapped and logged at warning.

        Returns ``True`` if there was an in-flight synthesis or active
        playback that we attempted to stop, ``False`` otherwise.
        """
        with self._lock:
            was_running = self._in_flight
            self._cancelled = True
            task = self._active_task
            loop = self._active_loop

        # 1. Cancel the asyncio Communicate stream if one is in flight.
        if task is not None and loop is not None and not task.done():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError as exc:
                # Loop already closed — task is effectively dead.
                logger.warning("[edge-tts] task cancel skipped: %s", exc)
            except Exception as exc:  # noqa: BLE001 — defensive: never raise
                logger.warning("[edge-tts] task cancel failed: %s", exc)

        # 2. Stop the speaker. ``audio_io.play_audio`` uses sounddevice,
        # so ``sd.stop()`` aborts whatever clip is currently playing.
        # sounddevice may not be installed in headless test envs — that's
        # fine, the play path would also have failed earlier.
        try:
            import sounddevice as sd  # type: ignore[import-not-found]

            sd.stop()
            was_running = True
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 — defensive: never raise
            logger.warning("[edge-tts] sounddevice stop failed: %s", exc)

        return was_running


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
