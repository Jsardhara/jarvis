"""Free wake-word detector using openWakeWord (community-trained models).

No paid Picovoice account required. Uses the community-released
``hey_jarvis_v0.1`` model which ships with the openWakeWord PyPI
package. Latency on CPU: ~50-100 ms per 30 ms frame.

Implements :class:`jarvis.voice.wake.WakeDetector` Protocol.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "hey_jarvis_v0.1"
DEFAULT_THRESHOLD = 0.5


class OpenWakeWordDetector:
    """openWakeWord wrapper with the pretrained 'hey jarvis' model.

    The model + dependencies are downloaded on first instantiation
    (cached at ``~/.cache/openwakeword/``).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        try:
            from openwakeword.model import Model  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword not installed — pip install -e '.[voice]'"
            ) from exc
        self.keyword = model_name.replace("_v0.1", "").replace("_", " ")
        self.threshold = threshold
        # Download stock models if missing; cheap on subsequent runs.
        try:
            import openwakeword.utils  # type: ignore[import-not-found]

            openwakeword.utils.download_models([model_name])
        except Exception as exc:  # noqa: BLE001 — best-effort first-run fetch
            logger.warning(
                "openWakeWord model download skipped (%s); assuming cached", exc,
            )
        self._model = Model(wakeword_models=[model_name])

    def listen(self, audio_chunks: Iterable[bytes]) -> bool:
        """Block on each frame; return True the first time wake-prob ≥ threshold."""
        for chunk in audio_chunks:
            arr = np.frombuffer(chunk, dtype=np.int16)
            if arr.size == 0:
                continue
            scores = self._model.predict(arr)
            for score in scores.values():
                if score >= self.threshold:
                    return True
        return False


__all__ = ["OpenWakeWordDetector", "DEFAULT_MODEL", "DEFAULT_THRESHOLD"]
