"""Smoke test for ``python -m jarvis.voice``.

End-to-end mocks: wake fires once, STT returns a canned utterance,
orchestrator stub echoes, TTS captures bytes. Asserts the full pipeline
runs cleanly through one cycle.
"""

from __future__ import annotations

from typing import Any

import pytest


class _OneShotWake:
    def __init__(self) -> None:
        self.fired = False

    def listen(self, audio_chunks: Any) -> bool:
        # First call: wake. Second call: don't (so cycle ends).
        if not self.fired:
            self.fired = True
            return True
        return False


class _CannedSTT:
    def transcribe(self, audio: bytes | Any) -> str:
        return "what is on my plate today"


class _CapturingTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return b"\x00" * 32  # any non-empty bytes


@pytest.mark.asyncio
async def test_one_cycle_full_pipeline(monkeypatch):
    """One cycle: wake → collect → STT → handle → summary → TTS → play."""
    from jarvis.voice import __main__ as voice_main
    from jarvis.voice import audio_io

    # Stub mic_chunks to yield finite frames so collect_until_silence terminates.
    def _mic():
        for _ in range(50):
            yield b"x" * audio_io.FRAME_BYTES

    monkeypatch.setattr(voice_main, "mic_chunks", _mic)

    # collect_until_silence — return canned PCM, skip the real VAD path.
    monkeypatch.setattr(
        voice_main,
        "collect_until_silence",
        lambda chunks: b"\x01\x02\x03",
    )

    # play_audio — record bytes instead of speaker.
    played: list[int] = []
    monkeypatch.setattr(
        voice_main,
        "play_audio",
        lambda audio: played.append(len(audio)),
    )

    wake = _OneShotWake()
    stt = _CannedSTT()
    tts = _CapturingTTS()

    received: dict[str, Any] = {}

    async def _handle(text: str) -> dict[str, Any]:
        received["text"] = text
        return {"responses": {"echo": {"action": text}}}

    await voice_main._one_cycle(wake, stt, tts, _handle)

    assert received["text"] == "what is on my plate today"
    assert tts.spoken, "TTS was never invoked"
    assert "what is on my plate today" in tts.spoken[0]
    assert played, "play_audio was never invoked"


@pytest.mark.asyncio
async def test_one_cycle_skips_when_no_wake(monkeypatch):
    """When wake.listen() returns False, the cycle is a no-op."""
    from jarvis.voice import __main__ as voice_main

    monkeypatch.setattr(voice_main, "mic_chunks", lambda: iter(()))

    class _NoWake:
        def listen(self, audio_chunks: Any) -> bool:
            return False

    tts = _CapturingTTS()

    async def _handle(text: str) -> dict[str, Any]:
        raise AssertionError("handle should NOT be called without wake")

    await voice_main._one_cycle(_NoWake(), _CannedSTT(), tts, _handle)
    assert tts.spoken == []


@pytest.mark.asyncio
async def test_one_cycle_skips_empty_transcription(monkeypatch):
    """Empty STT result must not invoke the orchestrator."""
    from jarvis.voice import __main__ as voice_main

    def _mic():
        for _ in range(5):
            yield b"x" * 32

    monkeypatch.setattr(voice_main, "mic_chunks", _mic)
    monkeypatch.setattr(voice_main, "collect_until_silence", lambda chunks: b"abc")

    class _EmptySTT:
        def transcribe(self, audio: bytes | Any) -> str:
            return "   "

    tts = _CapturingTTS()
    handle_calls: list[str] = []

    async def _handle(text: str) -> dict[str, Any]:
        handle_calls.append(text)
        return {}

    await voice_main._one_cycle(_OneShotWake(), _EmptySTT(), tts, _handle)
    assert handle_calls == []
    assert tts.spoken == []


def test_build_tts_falls_back_to_edge_when_elevenlabs_missing_creds(monkeypatch):
    """ElevenLabs requested but no creds → fall back to edge-tts cleanly."""
    from jarvis.voice import __main__ as voice_main

    class _Settings:
        voice_engine_tts = "elevenlabs"
        elevenlabs_api_key = None
        elevenlabs_voice_id = None
        voice_name = "en-US-AndrewMultilingualNeural"

    # Stub edge_tts module so EdgeTTSProvider construction doesn't fail.
    import sys
    import types

    fake = types.ModuleType("edge_tts")

    class _C:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            if False:
                yield None

    fake.Communicate = _C  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)

    tts = voice_main._build_tts(_Settings())
    assert tts.__class__.__name__ == "EdgeTTSProvider"


def test_build_stt_falls_back_to_mock_when_deepgram_key_missing():
    from jarvis.voice import __main__ as voice_main

    class _Settings:
        voice_engine_stt = "deepgram"
        deepgram_api_key = None
        voice_whisper_model = "base.en"

    stt = voice_main._build_stt(_Settings())
    assert stt.__class__.__name__ == "MockSTT"
