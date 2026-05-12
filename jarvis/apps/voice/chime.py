"""Synth a 150 ms wake chime once, cache to ``state/voice_samples/chime.wav``.

Pure stdlib + numpy. No internet, no LLM, no third-party audio assets.
The chime is a two-tone bell (440 Hz + 660 Hz) with a quick exponential
fade-out so it doesn't bleed into the STT capture.

Plays the moment wake word fires, before STT starts. Operator hears
acknowledgement within 200 ms so they know Jarvis is listening, instead
of waiting through 3-5 seconds of dead air.
"""

from __future__ import annotations

import logging
import wave
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

CHIME_FILENAME = "chime.wav"
SAMPLE_RATE = 16_000
DURATION_S = 0.15  # 150 ms
TONE_A_HZ = 440.0
TONE_B_HZ = 660.0
PEAK_AMPLITUDE = 0.35  # gentle, not jarring

DEFAULT_CACHE_DIR = Path("state/voice_samples")


def synth_chime() -> bytes:
    """Return the chime as a complete WAV byte string (header + PCM)."""
    import numpy as np

    n_samples = int(SAMPLE_RATE * DURATION_S)
    t = np.linspace(0.0, DURATION_S, n_samples, endpoint=False)
    blend = 0.5 * np.sin(2 * np.pi * TONE_A_HZ * t) + 0.5 * np.sin(
        2 * np.pi * TONE_B_HZ * t
    )
    # Exponential fade-out so the chime doesn't ring into the STT window.
    envelope = np.exp(-3.0 * t / DURATION_S)
    samples = (blend * envelope * PEAK_AMPLITUDE * 32767).astype(np.int16)

    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # int16
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())
    return buf.getvalue()


def chime_path(cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / CHIME_FILENAME


def ensure_chime(cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Generate the chime once and cache it. Returns the file path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = chime_path(cache_dir)
    if not path.exists():
        path.write_bytes(synth_chime())
        logger.info("[voice] chime cached at %s", path)
    return path


def load_chime(cache_dir: Path = DEFAULT_CACHE_DIR) -> bytes:
    """Return chime WAV bytes; synthesize on first call."""
    path = ensure_chime(cache_dir)
    return path.read_bytes()


__all__ = [
    "synth_chime",
    "chime_path",
    "ensure_chime",
    "load_chime",
    "CHIME_FILENAME",
    "SAMPLE_RATE",
    "DURATION_S",
]
