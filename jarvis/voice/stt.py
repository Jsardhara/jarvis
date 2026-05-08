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
    """Local Whisper STT.

    Prefers ``faster-whisper`` (CTranslate2-optimised, ~4x faster on CPU);
    falls back to ``openai-whisper`` if the former is missing.

    Accepts raw 16 kHz mono int16 PCM bytes (the layout produced by
    :func:`jarvis.voice.audio_io.mic_chunks`) OR a Path to an existing
    audio file. Bytes are routed through ``faster-whisper`` directly via
    a numpy array; Paths use either backend's file API.
    """

    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None
        self._backend: str | None = None  # "faster" | "openai"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]

            self._model = WhisperModel(self.model_name, device="auto", compute_type="auto")
            self._backend = "faster"
            return
        except ImportError:
            pass
        import whisper  # type: ignore[import-not-found]

        self._model = whisper.load_model(self.model_name)
        self._backend = "openai"

    def transcribe(self, audio: bytes | Path) -> str:
        self._ensure_loaded()
        if self._backend == "faster":
            return self._transcribe_faster(audio)
        return self._transcribe_openai(audio)

    def _transcribe_faster(self, audio: bytes | Path) -> str:
        import numpy as np

        if isinstance(audio, Path):
            segments, _info = self._model.transcribe(str(audio))  # type: ignore[union-attr]
        else:
            arr = np.frombuffer(audio, dtype=np.int16).astype("float32") / 32768.0
            segments, _info = self._model.transcribe(arr)  # type: ignore[union-attr]
        return " ".join(seg.text.strip() for seg in segments).strip()

    def _transcribe_openai(self, audio: bytes | Path) -> str:
        path = audio if isinstance(audio, Path) else Path(audio.decode("latin-1"))
        result = self._model.transcribe(str(path))  # type: ignore[union-attr]
        return result.get("text", "")
