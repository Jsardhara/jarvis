"""Pre-cached filler MP3s played while Jarvis is thinking.

Six short phrases generated once via :class:`EdgeTTSProvider`, cached
under ``state/voice_samples/fillers/``. Random pick on each query so
operator doesn't hear the same filler back-to-back.

Zero LLM cost ever. One-time edge-tts synthesis (free) on first run.
After that, fillers play instantly off disk.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("state/voice_samples/fillers")

# (id, phrase). MP3s named ``<id>.mp3``.
FILLERS: tuple[tuple[str, str], ...] = (
    ("01-one-moment", "One moment."),
    ("02-let-me-check", "Let me check."),
    ("03-looking", "Looking into it."),
    ("04-working", "Working on it."),
    ("05-just-a-sec", "Just a second."),
    ("06-checking", "Checking now."),
)


def _gen_one(phrase: str, voice: str, rate: str, out_path: Path) -> None:
    """Synthesize one filler via edge-tts and write to disk."""
    import asyncio

    from .edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider(voice=voice, rate=rate)
    audio = asyncio.run(provider._synthesize_async(phrase))
    out_path.write_bytes(audio)


def ensure_fillers(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    voice: str = "en-US-AndrewMultilingualNeural",
    rate: str = "+15%",
) -> list[Path]:
    """Generate every filler once and cache. Returns the list of MP3 paths.

    ``voice`` and ``rate`` should match the operator's selected production
    voice (default Andrew at +15%) so fillers don't sound like a different
    speaker than the rest of the reply.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filler_id, phrase in FILLERS:
        out = cache_dir / f"{filler_id}.mp3"
        if not out.exists():
            try:
                _gen_one(phrase, voice, rate, out)
                logger.info("[voice] filler cached at %s", out)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[voice] filler %s synthesis failed: %s", filler_id, exc)
                continue
        paths.append(out)
    return paths


def pick_filler(cache_dir: Path = DEFAULT_CACHE_DIR) -> Path | None:
    """Return a random cached filler path, or None if cache empty."""
    if not cache_dir.exists():
        return None
    candidates = sorted(cache_dir.glob("*.mp3"))
    if not candidates:
        return None
    return random.choice(candidates)


def load_filler_bytes(cache_dir: Path = DEFAULT_CACHE_DIR) -> bytes:
    """Pick a random filler and return its raw bytes; empty if none cached."""
    path = pick_filler(cache_dir)
    if path is None:
        return b""
    return path.read_bytes()


__all__ = [
    "FILLERS",
    "ensure_fillers",
    "pick_filler",
    "load_filler_bytes",
    "DEFAULT_CACHE_DIR",
]
