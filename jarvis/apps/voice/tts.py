"""Text-to-speech — ElevenLabs (paid, best) or Piper (local, free)."""
from __future__ import annotations

from typing import Protocol

import httpx


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class MockTTS:
    def __init__(self):
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return b"<mock-audio:" + text.encode() + b">"


class ElevenLabsTTS:
    """ElevenLabs REST. https://elevenlabs.io/docs/api-reference/text-to-speech"""

    URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, api_key: str, voice_id: str,
                 transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self._client = httpx.Client(timeout=30.0, transport=transport)

    def synthesize(self, text: str) -> bytes:
        r = self._client.post(
            self.URL_TEMPLATE.format(voice_id=self.voice_id),
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
        )
        return r.content if r.status_code == 200 else b""


class PiperTTS:  # pragma: no cover - requires local binary
    """Local Piper. https://github.com/rhasspy/piper"""

    def __init__(self, model_path: str):
        self.model_path = model_path

    def synthesize(self, text: str) -> bytes:
        import subprocess
        proc = subprocess.run(
            ["piper", "--model", self.model_path, "--output_raw"],
            input=text.encode(), capture_output=True, check=False,
        )
        return proc.stdout
