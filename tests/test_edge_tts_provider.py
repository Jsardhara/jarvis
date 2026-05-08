"""Tests for ``jarvis/voice/edge_tts_provider.py``.

Mocks the ``edge_tts`` library so we don't hit Microsoft's endpoint
during CI. Verifies bytes flow through, voice/rate/volume params hit
the right place, and empty input is handled cleanly.
"""

from __future__ import annotations

import sys
import types
from collections.abc import AsyncIterator
from typing import Any

import pytest


@pytest.fixture
def fake_edge_tts(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Insert a fake ``edge_tts`` module into sys.modules."""
    captured: dict[str, Any] = {"calls": []}

    class _Communicate:
        def __init__(self, text: str, **kwargs: Any) -> None:
            captured["calls"].append({"text": text, **kwargs})
            self._text = text

        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            # Two audio events + one end event.
            yield {"type": "audio", "data": b"AA"}
            yield {"type": "audio", "data": b"BB"}
            yield {"type": "WordBoundary", "offset": 0}

    fake = types.ModuleType("edge_tts")
    fake.Communicate = _Communicate  # type: ignore[attr-defined]

    async def _fake_list_voices() -> list[dict[str, str]]:
        return [
            {"ShortName": "en-US-AndrewMultilingualNeural", "Locale": "en-US"},
            {"ShortName": "en-GB-RyanNeural", "Locale": "en-GB"},
            {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR"},
        ]

    fake.list_voices = _fake_list_voices  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    return captured


def test_synthesize_returns_concatenated_audio_bytes(fake_edge_tts):
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider(voice="en-US-AndrewMultilingualNeural")
    out = provider.synthesize("hello world")
    assert out == b"AABB"
    assert fake_edge_tts["calls"][0]["text"] == "hello world"
    assert fake_edge_tts["calls"][0]["voice"] == "en-US-AndrewMultilingualNeural"


def test_synthesize_empty_input_returns_empty_bytes(fake_edge_tts):
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider()
    assert provider.synthesize("") == b""
    assert provider.synthesize("   ") == b""
    assert fake_edge_tts["calls"] == []


def test_voice_rate_volume_pitch_pass_through(fake_edge_tts):
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider(
        voice="en-GB-RyanNeural", rate="+10%", volume="-5%", pitch="+2Hz",
    )
    provider.synthesize("custom params")
    call = fake_edge_tts["calls"][0]
    assert call["voice"] == "en-GB-RyanNeural"
    assert call["rate"] == "+10%"
    assert call["volume"] == "-5%"
    assert call["pitch"] == "+2Hz"


def test_synthesize_skips_non_audio_events(fake_edge_tts):
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider

    out = EdgeTTSProvider().synthesize("ignore boundaries")
    # Fake yielded WordBoundary too; it should not be in output bytes.
    assert b"WordBoundary" not in out
    assert b"offset" not in out


@pytest.mark.asyncio
async def test_list_voices_filters_by_language(fake_edge_tts):
    from jarvis.voice.edge_tts_provider import list_voices

    en_voices = await list_voices(language="en")
    assert len(en_voices) == 2
    assert all(v["Locale"].startswith("en") for v in en_voices)


def test_synthesize_raises_helpful_error_when_lib_missing(monkeypatch):
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider

    monkeypatch.setitem(sys.modules, "edge_tts", None)
    with pytest.raises(RuntimeError, match="edge-tts not installed"):
        EdgeTTSProvider().synthesize("anything")
