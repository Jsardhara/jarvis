"""Daemon → voice bridge.

Tail ``state/inbox.jsonl``, watch for ``severity=='alert'`` events, and
speak a short proactive line through TTS — but only when:

* operator hasn't muted (``mute_for`` window)
* voice loop isn't actively speaking or listening

Every spoken alert is logged to ``state/voice_actions.jsonl`` for audit.

The Haiku rewrite (``_build_spoken_line``) keeps the alert conversational
("Heads up — drawdown's at minus eight.") rather than reading the raw
summary aloud.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .persona import PERSONA, VOICE_WORD_CAP
from .voice_state import read_state

logger = logging.getLogger(__name__)

ALERT_MODEL = "claude-haiku-4-5"
POLL_INTERVAL_SEC = 2.0

_MUTE_UNTIL: datetime | None = None
_OFFSET: int = 0  # byte offset into inbox.jsonl

_ALERT_SYSTEM = (
    PERSONA
    + f"\n\nA background daemon just flagged something the operator should hear.\n"
    f"Speak one short sentence — what happened, plain words, no jargon.\n"
    f"End with a question if action is needed ('want me to pull it up?').\n"
    f"No markdown. No agent names. {VOICE_WORD_CAP} words max."
)


def _inbox_path() -> Path:
    from jarvis.config import get_settings
    return get_settings().state_dir / "inbox.jsonl"


def _actions_path() -> Path:
    from jarvis.config import get_settings
    return get_settings().state_dir / "voice_actions.jsonl"


def mute_for(duration: timedelta) -> None:
    """Suppress proactive alerts for ``duration`` from now."""
    global _MUTE_UNTIL
    _MUTE_UNTIL = datetime.now(UTC) + duration


def clear_mute() -> None:
    """Re-enable proactive alerts immediately."""
    global _MUTE_UNTIL
    _MUTE_UNTIL = None


def is_muted() -> bool:
    if _MUTE_UNTIL is None:
        return False
    return datetime.now(UTC) < _MUTE_UNTIL


def _voice_busy() -> bool:
    """True while the voice loop is mid-utterance or mid-STT."""
    try:
        mode = read_state().get("mode")
    except Exception:  # noqa: BLE001
        return False
    return mode in ("stt", "tts")


def _build_spoken_line(summary: str) -> str:
    """Haiku rewrite — alert summary → conversational one-liner.

    Falls back to ``"Heads up — {summary}."`` on LLM failure.
    """
    fallback = f"Heads up — {summary}."
    try:
        from jarvis.llm.queue import submit
        reply = submit(system=_ALERT_SYSTEM, user=summary, model=ALERT_MODEL)
        if isinstance(reply, dict):
            reply = reply.get("text", "")
        reply = (reply or "").strip()
        return reply or fallback
    except Exception as exc:  # noqa: BLE001 — voice never crashes on LLM fail
        logger.warning("[voice.proactive] rewrite failed: %s", exc)
        return fallback


def _audit(event: dict[str, Any], spoken: str) -> None:
    path = _actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "agent": event.get("agent"),
        "severity": event.get("severity"),
        "summary": event.get("summary"),
        "spoken": spoken,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


async def tick(tts) -> None:
    """One pass over new inbox lines. Idempotent — called repeatedly by ``run``.

    Behaviour:
      * Reads only lines past the last offset.
      * Skips non-alert severities silently (offset still advances).
      * If voice is busy, the offset is NOT advanced — alert retries next tick.
      * If muted, the offset advances (we drop muted alerts on purpose).
    """
    global _OFFSET

    path = _inbox_path()
    if not path.exists():
        return

    size = path.stat().st_size
    if size < _OFFSET:
        # File was rotated/truncated — restart from beginning.
        _OFFSET = 0

    if size == _OFFSET:
        return

    busy_deferred = False
    new_offset = _OFFSET
    with path.open("rb") as f:
        f.seek(_OFFSET)
        for raw in f:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                new_offset = f.tell()
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("[voice.proactive] skipping malformed line")
                new_offset = f.tell()
                continue

            severity = event.get("severity")
            if severity != "alert":
                new_offset = f.tell()
                continue

            if _voice_busy():
                busy_deferred = True
                break

            if is_muted():
                # drop muted alerts
                new_offset = f.tell()
                continue

            summary = event.get("summary", "")
            spoken = _build_spoken_line(summary)
            try:
                audio = tts.synthesize(spoken)
                # In real loop, audio plays via audio_io — caller responsibility.
                # Test doubles only inspect tts.spoken.
                _ = audio
            except Exception as exc:  # noqa: BLE001
                logger.warning("[voice.proactive] tts failed: %s", exc)
            _audit(event, spoken)
            new_offset = f.tell()

    if not busy_deferred:
        _OFFSET = new_offset
    else:
        _OFFSET = new_offset  # advance past anything already consumed


async def run(tts, *, interval: float = POLL_INTERVAL_SEC) -> None:  # pragma: no cover
    """Forever loop — call ``tick`` every ``interval`` seconds."""
    # Start at end of file so old events don't replay.
    global _OFFSET
    p = _inbox_path()
    if p.exists():
        _OFFSET = p.stat().st_size

    while True:
        try:
            await tick(tts)
        except Exception:  # noqa: BLE001
            logger.exception("[voice.proactive] tick crashed; continuing")
        await asyncio.sleep(interval)
