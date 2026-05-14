"""Text-to-speech — ElevenLabs (paid, best) or Piper (local, free).

J10 - every concrete provider grows an ``interrupt()`` method. The
synthesize/playback path is synchronous today (each provider returns the
full byte blob before the caller plays it), so the safe minimum is a
cooperative cancel flag the playback loop can poll. Hot-mic mode calls
:meth:`TTSProvider.interrupt` when the VAD fires mid-reply.

Returns:

* ``True`` if there was an in-progress synthesis/playback that was
  cancelled.
* ``False`` if nothing was playing.

Provider notes:

* **MockTTS** - synthesis is instant; we flip a flag so tests can assert.
* **ElevenLabsTTS / EdgeTTSProvider** - synthesis is one HTTP round-trip;
  there's nothing to cancel mid-call today. We still expose the flag so
  the caller can avoid playing audio that arrived after the user spoke.
* **PiperTTS** - runs a subprocess; ``interrupt()`` terminates the live
  process if one is registered.
"""
from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...
    def interrupt(self) -> bool: ...


class _BaseInterruptible:
    """Mixin: cheap cooperative-cancel flag shared across providers."""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._in_flight: bool = False

    def interrupt(self) -> bool:
        """Mark any in-flight synthesis/playback as cancelled.

        Returns True if something was actually running; False otherwise.
        Idempotent - calling twice on a quiet provider stays False.
        """
        if not self._in_flight:
            return False
        self._cancelled = True
        self._in_flight = False
        return True


class MockTTS(_BaseInterruptible):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self._cancelled = False
        self._in_flight = True
        try:
            self.calls.append(text)
            return b"<mock-audio:" + text.encode() + b">"
        finally:
            self._in_flight = False


class ElevenLabsTTS(_BaseInterruptible):
    """ElevenLabs REST."""

    URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, api_key: str, voice_id: str,
                 transport: httpx.BaseTransport | None = None):
        super().__init__()
        self.api_key = api_key
        self.voice_id = voice_id
        self._client = httpx.Client(timeout=30.0, transport=transport)

    def synthesize(self, text: str) -> bytes:
        self._cancelled = False
        self._in_flight = True
        try:
            r = self._client.post(
                self.URL_TEMPLATE.format(voice_id=self.voice_id),
                json={"text": text, "model_id": "eleven_multilingual_v2"},
                headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
            )
            if self._cancelled:
                return b""
            return r.content if r.status_code == 200 else b""
        finally:
            self._in_flight = False


class PiperTTS(_BaseInterruptible):  # pragma: no cover - requires local binary
    """Local Piper."""

    def __init__(self, model_path: str):
        super().__init__()
        self.model_path = model_path
        self._proc = None

    def synthesize(self, text: str) -> bytes:
        import subprocess
        self._cancelled = False
        self._in_flight = True
        try:
            self._proc = subprocess.Popen(  # noqa: S603
                ["piper", "--model", self.model_path, "--output_raw"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            out, _err = self._proc.communicate(input=text.encode())
            return b"" if self._cancelled else out
        finally:
            self._in_flight = False
            self._proc = None

    def interrupt(self) -> bool:
        was_running = super().interrupt()
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception as exc:  # noqa: BLE001
                logger.warning("piper interrupt failed: %s", exc)
        return was_running
