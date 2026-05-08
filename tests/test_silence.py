"""Tests for the energy-based silence detector."""

from __future__ import annotations

import numpy as np

from jarvis.voice import silence


def _sine_frame(amplitude: float, freq_hz: float = 440.0, duration_s: float = 0.03,
                sample_rate: int = 16_000) -> bytes:
    n = int(sample_rate * duration_s)
    t = np.linspace(0.0, duration_s, n, endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq_hz * t) * 32767).astype(np.int16)
    return samples.tobytes()


def test_voiced_loud_sine_above_threshold():
    frame = _sine_frame(amplitude=0.5)  # ~16k peak
    assert silence.is_voiced(frame, threshold=500.0) is True


def test_silent_frame_below_threshold():
    frame = b"\x00" * 960
    assert silence.is_voiced(frame, threshold=500.0) is False


def test_quiet_sine_below_threshold():
    frame = _sine_frame(amplitude=0.005)  # very quiet
    assert silence.is_voiced(frame, threshold=500.0) is False


def test_threshold_tunable():
    frame = _sine_frame(amplitude=0.05)  # ~1640 RMS
    # A high threshold rejects it; a low one accepts it.
    assert silence.is_voiced(frame, threshold=5_000.0) is False
    assert silence.is_voiced(frame, threshold=100.0) is True


def test_empty_frame_not_voiced():
    assert silence.is_voiced(b"") is False


def test_rms_returns_zero_for_empty():
    assert silence.rms(b"") == 0.0


def test_rms_positive_for_loud_sine():
    frame = _sine_frame(amplitude=0.5)
    assert silence.rms(frame) > 1_000.0
