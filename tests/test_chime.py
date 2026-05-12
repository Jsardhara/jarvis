"""Tests for ``jarvis/voice/chime.py``."""

from __future__ import annotations

import wave
from io import BytesIO
from pathlib import Path


from jarvis.apps.voice import chime


def test_synth_chime_returns_valid_wav_bytes():
    data = chime.synth_chime()
    assert len(data) > 0
    with wave.open(BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2  # int16
        assert wav.getframerate() == chime.SAMPLE_RATE
        # Frames roughly match the configured duration.
        n_frames = wav.getnframes()
        assert abs(n_frames - int(chime.SAMPLE_RATE * chime.DURATION_S)) < 5


def test_ensure_chime_creates_file_once(tmp_path: Path):
    out = chime.ensure_chime(tmp_path)
    assert out.exists()
    first_mtime = out.stat().st_mtime
    # Second call must NOT regenerate (idempotent).
    out2 = chime.ensure_chime(tmp_path)
    assert out2 == out
    assert out.stat().st_mtime == first_mtime


def test_load_chime_returns_bytes(tmp_path: Path):
    data = chime.load_chime(tmp_path)
    assert isinstance(data, bytes)
    assert len(data) > 100  # WAV header alone is 44 bytes


def test_chime_path_uses_provided_dir(tmp_path: Path):
    p = chime.chime_path(tmp_path)
    assert p.parent == tmp_path
    assert p.name == chime.CHIME_FILENAME
