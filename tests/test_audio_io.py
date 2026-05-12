"""Tests for ``jarvis/voice/audio_io.py``.

Stubs ``sounddevice`` + ``webrtcvad`` so the helpers are exercised
without real hardware or PortAudio.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from jarvis.apps.voice import audio_io


def test_collect_until_silence_stops_after_silence_threshold(monkeypatch):
    """First 10 frames voiced, rest silent — collector stops after silence hangover."""
    counter = {"calls": 0}

    def _fake_is_voiced(frame: bytes, threshold: float = 500.0) -> bool:  # noqa: ARG001
        counter["calls"] += 1
        return counter["calls"] <= 10

    monkeypatch.setattr("jarvis.apps.voice.silence.is_voiced", _fake_is_voiced)
    chunks = (b"x" * audio_io.FRAME_BYTES for _ in range(200))
    out = audio_io.collect_until_silence(
        chunks, silence_ms=120, frame_ms=30, max_ms=15_000,
    )
    # 10 voiced + 4 trailing silence frames (120ms / 30ms) → 14 frames.
    assert len(out) == audio_io.FRAME_BYTES * 14


def test_collect_until_silence_stops_at_max_ms_safety(monkeypatch):
    """Always-voiced input — collector stops when max_ms reached, not before."""
    monkeypatch.setattr(
        "jarvis.apps.voice.silence.is_voiced", lambda frame, threshold=500.0: True,
    )
    chunks = (b"x" * audio_io.FRAME_BYTES for _ in range(10_000))
    out = audio_io.collect_until_silence(
        chunks, silence_ms=700, frame_ms=30, max_ms=300,
    )
    # max_ms=300, frame_ms=30 → 10 frames cap.
    assert len(out) == audio_io.FRAME_BYTES * 10


def test_play_audio_no_op_on_empty_bytes():
    # Should not raise even without sounddevice installed in test env.
    audio_io.play_audio(b"")


def test_play_audio_calls_sounddevice_play(monkeypatch):
    captured: dict[str, Any] = {}

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.play = lambda samples, rate, blocking=True: captured.update(  # type: ignore[attr-defined]
        {"samples_len": len(samples), "rate": rate, "blocking": blocking},
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    # Stub soundfile so _decode succeeds.
    fake_sf = types.ModuleType("soundfile")

    import numpy as np

    def _read(buf, dtype="float32"):  # noqa: ARG001
        return np.zeros(1024, dtype=np.float32), 16_000

    fake_sf.read = _read  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundfile", fake_sf)

    audio_io.play_audio(b"\x00" * 4096)
    assert captured["rate"] == 16_000
    assert captured["samples_len"] == 1024
    assert captured["blocking"] is True


def test_play_audio_falls_back_to_raw_int16_when_decode_fails(monkeypatch):
    """If soundfile can't parse, should still play as raw int16 PCM."""
    captured: dict[str, Any] = {}

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.play = lambda samples, rate, blocking=True: captured.update(  # type: ignore[attr-defined]
        {"rate": rate, "len": len(samples)},
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    fake_sf = types.ModuleType("soundfile")

    def _read(buf, dtype="float32"):  # noqa: ARG001
        raise ValueError("not a real audio container")

    fake_sf.read = _read  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundfile", fake_sf)

    raw_pcm = b"\x01\x00" * 1000  # 1000 int16 samples
    audio_io.play_audio(raw_pcm)
    # Fallback rate is 22050 (Piper default).
    assert captured["rate"] == 22_050
    assert captured["len"] == 1000


def test_mic_chunks_raises_helpful_error_when_sounddevice_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    with pytest.raises(RuntimeError, match="sounddevice not installed"):
        next(audio_io.mic_chunks())
