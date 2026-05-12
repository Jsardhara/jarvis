"""Wake-word detector — Picovoice Porcupine in prod, mock in tests.

Phase 5 ships the WakeDetector Protocol + a deterministic mock detector
keyed off a sentinel string. Real Porcupine integration lands when
PICOVOICE_ACCESS_KEY is in env.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class WakeDetector(Protocol):
    keyword: str
    def listen(self, audio_chunks: Iterable[bytes]) -> bool: ...


class MockWakeDetector:
    """Detects when an audio chunk equals the keyword bytes (string→utf8)."""

    def __init__(self, keyword: str = "hey jarvis"):
        self.keyword = keyword
        self._kw_bytes = keyword.lower().encode()

    def listen(self, audio_chunks: Iterable[bytes]) -> bool:
        for chunk in audio_chunks:
            if self._kw_bytes in chunk.lower():
                return True
        return False


class PorcupineDetector:  # pragma: no cover - requires hardware audio
    """Real Porcupine wrapper. Not exercised in unit tests."""

    def __init__(self, access_key: str, keyword_paths: list[str] | None = None,
                 keywords: list[str] | None = None):
        try:
            import pvporcupine  # noqa: F401
        except ImportError as e:
            raise RuntimeError("pip install jarvis[voice]") from e
        self.access_key = access_key
        self.keyword_paths = keyword_paths
        self.keywords = keywords or ["jarvis"]
        self.keyword = self.keywords[0]

    def listen(self, audio_chunks):
        import pvporcupine
        handle = pvporcupine.create(access_key=self.access_key,
                                    keyword_paths=self.keyword_paths,
                                    keywords=self.keywords)
        try:
            for chunk in audio_chunks:
                idx = handle.process(chunk)
                if idx >= 0:
                    return True
            return False
        finally:
            handle.delete()
