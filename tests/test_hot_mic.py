"""J10 — hot-mic voice mode tests.

Covers:

* ``voice_hot_mic`` setting wiring (env var → Settings).
* :class:`BargeinDetector` — fires on synthetic speech, ignores silence.

Audio + TTS are mocked. We don't exercise the live hot-mic loop here
(that path touches sounddevice). Coverage of ``run_hot_mic_loop`` is left
to integration testing on a machine with a real mic.
"""
from __future__ import annotations

import struct
from math import pi, sin

import pytest

from jarvis.apps.voice.silence import BargeinDetector
from jarvis.config import get_settings


def _silence_frame(frame_ms: int = 30, sample_rate: int = 16_000) -> bytes:
    """Return a frame of pure zeros — guaranteed non-speech."""
    samples = sample_rate * frame_ms // 1000
    return b"\x00\x00" * samples


def _speech_frame(
    frame_ms: int = 30,
    sample_rate: int = 16_000,
    freq: int = 220,
    amplitude: int = 12_000,
) -> bytes:
    """Return a high-energy sine wave — energy VAD treats as speech."""
    samples = sample_rate * frame_ms // 1000
    out = bytearray()
    for i in range(samples):
        v = int(amplitude * sin(2 * pi * freq * i / sample_rate))
        out += struct.pack("<h", v)
    return bytes(out)


def test_settings_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOICE_HOT_MIC", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().voice_hot_mic is False
    finally:
        get_settings.cache_clear()


def test_settings_on_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_HOT_MIC", "1")
    get_settings.cache_clear()
    try:
        assert get_settings().voice_hot_mic is True
    finally:
        get_settings.cache_clear()


def test_bargein_detector_fires_on_speech_chunk() -> None:
    det = BargeinDetector(vad_threshold=0.5, frame_ms=30)
    assert det.feed(_speech_frame()) is True


def test_bargein_detector_ignores_silence() -> None:
    det = BargeinDetector(vad_threshold=0.5, frame_ms=30)
    assert det.feed(_silence_frame()) is False
