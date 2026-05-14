"""Energy-based voice-activity detector.

Replaces ``webrtcvad`` for the voice loop on Python versions where
no prebuilt wheel exists (e.g. 3.14 at time of writing). Pure stdlib
+ numpy. RMS over a single frame; voiced if above the threshold.

The default threshold (500.0 on int16 samples) suits a typical
desktop microphone in a quiet room. Tune via env::

    VOICE_SILENCE_THRESHOLD=300   # quieter mic / soft-spoken
    VOICE_SILENCE_THRESHOLD=800   # noisier room

Pair with :func:`jarvis.apps.voice.audio_io.collect_until_silence` which
calls :func:`is_voiced` on each 30 ms frame.

J10 — :class:`BargeinDetector` adds an OO entry-point for hot-mic mode,
using webrtcvad when available (better SNR) and falling back to the same
energy VAD when it isn't.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 500.0


def is_voiced(frame: bytes, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Return True if the frame's RMS amplitude exceeds ``threshold``."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "numpy required for silence detection - pip install -e '.[voice]'"
        ) from exc
    if not frame:
        return False
    arr = np.frombuffer(frame, dtype=np.int16).astype("float32")
    if arr.size == 0:
        return False
    rms_val = float(np.sqrt(np.mean(arr * arr)))
    return rms_val > threshold


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


class BargeinDetector:
    """VAD-based barge-in detector for hot-mic mode (J10).

    Streams microphone frames through a voice-activity decision and fires
    True as soon as speech is detected. The hot-mic loop uses this to
    interrupt in-progress TTS playback when the operator starts talking.

    Backend resolution:

    * If ``webrtcvad`` is importable, it's used (better SNR rejection on
      typical desktop mics). The detector enforces webrtcvad's frame-size
      contract (10/20/30 ms at 8/16/32/48 kHz). Off-size frames degrade
      to the energy fallback for that frame only.
    * Otherwise an energy-RMS threshold is used - same algorithm as
      :func:`is_voiced` so behaviour is consistent with the rest of the
      voice stack on Python builds without prebuilt webrtcvad wheels
      (e.g. 3.14).

    ``vad_threshold`` maps to webrtcvad's aggressiveness when in webrtc
    mode (0-3, rescaled from 0.0-1.0). In energy mode it's an RMS cutoff
    scaled against :data:`DEFAULT_THRESHOLD`.
    """

    def __init__(
        self,
        vad_threshold: float = 0.5,
        frame_ms: int = 30,
        sample_rate: int = 16_000,
    ) -> None:
        self.vad_threshold = float(vad_threshold)
        self.frame_ms = int(frame_ms)
        self.sample_rate = int(sample_rate)
        self._expected_bytes = (sample_rate * frame_ms // 1000) * 2
        self._webrtc_vad = self._try_load_webrtc()

    @staticmethod
    def _try_load_webrtc() -> object | None:
        try:
            import webrtcvad  # type: ignore[import-not-found]
        except ImportError:
            return None
        try:
            return webrtcvad.Vad()
        except Exception as exc:  # noqa: BLE001
            logger.warning("webrtcvad init failed (%s); using energy VAD", exc)
            return None

    def _aggressiveness(self) -> int:
        raw = round(self.vad_threshold * 3)
        return max(0, min(3, int(raw)))

    def feed(self, audio_chunk: bytes) -> bool:
        """Return True if the chunk contains speech."""
        if not audio_chunk:
            return False
        vad = self._webrtc_vad
        if vad is not None and len(audio_chunk) == self._expected_bytes:
            try:
                vad.set_mode(self._aggressiveness())
                return bool(vad.is_speech(audio_chunk, self.sample_rate))
            except Exception as exc:  # noqa: BLE001
                logger.warning("webrtcvad.is_speech failed (%s); falling back", exc)
        thresh = max(50.0, DEFAULT_THRESHOLD * self.vad_threshold)
        return is_voiced(audio_chunk, threshold=thresh)


__all__ = ["is_voiced", "rms", "DEFAULT_THRESHOLD", "BargeinDetector"]
