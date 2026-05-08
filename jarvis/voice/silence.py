"""Energy-based voice-activity detector.

Replaces ``webrtcvad`` for the voice loop on Python versions where
no prebuilt wheel exists (e.g. 3.14 at time of writing). Pure stdlib
+ numpy. RMS over a single frame; voiced if above the threshold.

The default threshold (500.0 on int16 samples) suits a typical
desktop microphone in a quiet room. Tune via env::

    VOICE_SILENCE_THRESHOLD=300   # quieter mic / soft-spoken
    VOICE_SILENCE_THRESHOLD=800   # noisier room

Pair with :func:`jarvis.voice.audio_io.collect_until_silence` which
calls :func:`is_voiced` on each 30 ms frame.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 500.0


def is_voiced(frame: bytes, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Return True if the frame's RMS amplitude exceeds ``threshold``.

    Frame is expected to be raw int16 mono PCM at any sample rate
    (the threshold is amplitude-based, not rate-based).
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "numpy required for silence detection — pip install -e '.[voice]'"
        ) from exc
    if not frame:
        return False
    arr = np.frombuffer(frame, dtype=np.int16).astype("float32")
    if arr.size == 0:
        return False
    rms = float(np.sqrt(np.mean(arr * arr)))
    return rms > threshold


def rms(frame: bytes) -> float:
    """Return the RMS amplitude of a frame (debug + threshold tuning)."""
    try:
        import numpy as np
    except ImportError:
        return 0.0
    if not frame:
        return 0.0
    arr = np.frombuffer(frame, dtype=np.int16).astype("float32")
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


__all__ = ["is_voiced", "rms", "DEFAULT_THRESHOLD"]
