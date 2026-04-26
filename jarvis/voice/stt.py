"""Speech-to-text — Whisper local or Deepgram cloud."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx


class STTProvider(Protocol):
    def transcribe(self, audio: bytes | Path) -> str: ...


class MockSTT:
    """Returns the configured response. For tests + scripted demos."""

    def __init__(self, response: str = "what is on my plate today"):
        self.response = response

    def transcribe(self, audio: bytes | Path) -> str:
        return self.response


class DeepgramSTT:
    """Deepgram REST API. https://developers.deepgram.com/reference/listen-file"""

    URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str, model: str = "nova-2",
                 transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=30.0, transport=transport)

    def transcribe(self, audio: bytes | Path) -> str:
        if isinstance(audio, Path):
            audio = audio.read_bytes()
        r = self._client.post(
            f"{self.URL}?model={self.model}",
            content=audio,
            headers={"Authorization": f"Token {self.api_key}",
                     "Content-Type": "audio/wav"},
        )
        if r.status_code != 200:
            return ""
        results = r.json().get("results", {})
        channels = results.get("channels", [])
        if not channels:
            return ""
        alts = channels[0].get("alternatives", [])
        return alts[0].get("transcript", "") if alts else ""


class WhisperSTT:  # pragma: no cover - requires local model download
    """openai-whisper local. Lazy-load model."""

    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None

    def transcribe(self, audio: bytes | Path) -> str:
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self.model_name)
        path = audio if isinstance(audio, Path) else Path(audio.decode("latin-1"))
        result = self._model.transcribe(str(path))
        return result.get("text", "")
