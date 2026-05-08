"""Microphone capture + speaker playback for the voice loop.

* :func:`mic_chunks` — generator yielding raw PCM frames (16 kHz mono, 30 ms)
  pulled from the default input device via ``sounddevice``. The frame size
  matches openWakeWord + webrtcvad expectations.
* :func:`play_audio` — accepts MP3 *or* WAV bytes (TTS providers vary)
  and plays them on the default output device.

Both helpers degrade gracefully when ``sounddevice`` / ``numpy`` /
``soundfile`` are missing — they raise a clear ``RuntimeError`` that the
``__main__`` entrypoint catches at startup and prints an install hint.

The default frame layout (16 kHz mono int16, 30 ms = 480 samples = 960
bytes) is chosen to satisfy:

* webrtcvad — accepts only 10/20/30 ms frames at 8/16/32/48 kHz
* openWakeWord — feature pipeline is tuned for 16 kHz mono
* faster-whisper — accepts arbitrary 16 kHz mono PCM
"""

from __future__ import annotations

import logging
import queue
from collections.abc import Iterable, Iterator
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_FRAME_MS = 30
DEFAULT_CHANNELS = 1
DEFAULT_DTYPE = "int16"

# 30 ms × 16 kHz = 480 samples × 2 bytes (int16) = 960 bytes per frame.
FRAME_BYTES = (DEFAULT_SAMPLE_RATE * DEFAULT_FRAME_MS // 1000) * 2


def mic_chunks(
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    frame_ms: int = DEFAULT_FRAME_MS,
    channels: int = DEFAULT_CHANNELS,
    device: int | str | None = None,
) -> Iterator[bytes]:
    """Yield raw PCM frames from the default microphone forever.

    The caller stops by breaking out of the for-loop.

    Raises ``RuntimeError`` with an install hint if ``sounddevice`` is
    missing.
    """
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice not installed — pip install -e '.[voice]'"
        ) from exc

    blocksize = int(sample_rate * frame_ms / 1000)
    q: queue.Queue[bytes] = queue.Queue()

    def _callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:  # noqa: ARG001
        if status:
            logger.warning("mic stream status: %s", status)
        # indata is a contiguous numpy array of shape (frames, channels);
        # tobytes() gives raw int16 PCM in little-endian.
        q.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=blocksize,
        device=device,
        dtype=DEFAULT_DTYPE,
        channels=channels,
        callback=_callback,
    ):
        while True:
            yield q.get()


def play_audio(audio_bytes: bytes, *, blocking: bool = True) -> None:
    """Play TTS audio bytes (MP3 or WAV) on the default output device.

    Requires ``soundfile`` + ``sounddevice`` from the voice extra. If
    decoding fails (e.g. operator passed raw int16 PCM), falls back to
    playing the bytes as 22 kHz mono int16 — a reasonable default for
    Piper local TTS output.
    """
    if not audio_bytes:
        return
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice not installed — pip install -e '.[voice]'"
        ) from exc

    samples, sample_rate = _decode(audio_bytes)
    sd.play(samples, sample_rate, blocking=blocking)


def _decode(audio_bytes: bytes) -> tuple[Any, int]:
    """Try MP3/WAV decoding via ``soundfile``; fall back to raw int16."""
    try:
        import io as _io

        import numpy as np
        import soundfile as sf  # type: ignore[import-not-found]
    except ImportError:
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "numpy + soundfile required to decode audio — pip install -e '.[voice]'"
            ) from exc
        # Last-ditch: treat as raw int16 mono at 22 kHz (Piper default).
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype("float32") / 32768.0
        return samples, 22_050
    try:
        samples, sr = sf.read(_io.BytesIO(audio_bytes), dtype="float32")
        return samples, int(sr)
    except Exception as exc:  # noqa: BLE001 — decoder is best-effort
        logger.warning(
            "soundfile failed to decode (%s); falling back to raw int16 22kHz", exc,
        )
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype("float32") / 32768.0
        return samples, 22_050


def collect_until_silence(
    chunks: Iterable[bytes],
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,  # noqa: ARG001 — kept for API compat
    frame_ms: int = DEFAULT_FRAME_MS,
    silence_ms: int = 700,
    max_ms: int = 15_000,
    threshold: float | None = None,
) -> bytes:
    """Pull frames from ``chunks`` until ``silence_ms`` of silence
    (energy VAD) or ``max_ms`` of audio has accumulated. Returns the
    concatenated PCM.

    Defaults are tuned for short utterances ("what's the time", "summarize
    today"). Bump ``silence_ms`` or ``max_ms`` for longer monologues.

    Replaced webrtcvad with energy-based VAD because Python 3.14 has no
    prebuilt webrtcvad wheel. See :mod:`jarvis.voice.silence`.
    """
    from .silence import DEFAULT_THRESHOLD, is_voiced

    thresh = threshold if threshold is not None else DEFAULT_THRESHOLD
    voiced: list[bytes] = []
    silence_count = 0
    silence_frames_threshold = silence_ms // frame_ms
    max_frames = max_ms // frame_ms
    for total, frame in enumerate(chunks, start=1):
        if total > max_frames:
            break
        is_speech = is_voiced(frame, threshold=thresh)
        if is_speech:
            voiced.append(frame)
            silence_count = 0
        elif voiced:
            voiced.append(frame)
            silence_count += 1
            if silence_count >= silence_frames_threshold:
                break
    return b"".join(voiced)


__all__ = [
    "mic_chunks",
    "play_audio",
    "collect_until_silence",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_FRAME_MS",
    "DEFAULT_CHANNELS",
    "DEFAULT_DTYPE",
    "FRAME_BYTES",
]
