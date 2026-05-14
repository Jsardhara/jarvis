"""Voice state singleton + WS broadcast helpers."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

VoiceMode = Literal["idle", "wake", "stt", "routing", "tts", "offline"]
VoiceTier = Literal["local", "haiku", "sonnet", "orchestrator"] | None

_STATE_PATH = Path("state") / "voice_state.json"

BroadcastFn = Callable[[dict[str, Any]], None]
_broadcaster: BroadcastFn | None = None

_DEFAULT_STATE: dict[str, Any] = {
    "mode": "idle",
    "tier": None,
    "last_text": "",
    "last_reply_source": None,
    "latency_ms": 0,
    "cost_usd": 0.0,
    "hot_mic_enabled": False,
    "updated_at": None,
}


def set_hot_mic_enabled(enabled: bool) -> dict[str, Any]:
    """Toggle the persisted ``hot_mic_enabled`` flag (J10)."""
    state = read_state()
    state["hot_mic_enabled"] = bool(enabled)
    state["updated_at"] = _now_iso()
    write_state(state)
    if _broadcaster is not None:
        try:
            _broadcaster({"type": "voice.state", "state": state})
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice.state broadcast failed: %s", exc)
    return state


def register_broadcaster(fn: BroadcastFn) -> None:
    """API server registers its push helper here at startup."""
    global _broadcaster
    _broadcaster = fn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def read_state() -> dict[str, Any]:
    """Read the singleton; create with defaults if missing."""
    if not _STATE_PATH.exists():
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_state(_DEFAULT_STATE.copy())
        return _DEFAULT_STATE.copy()
    try:
        state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("voice_state read failed (%s); resetting", exc)
        write_state(_DEFAULT_STATE.copy())
        return _DEFAULT_STATE.copy()
    # Backfill any new fields onto state files written by older versions.
    for key, default in _DEFAULT_STATE.items():
        state.setdefault(key, default)
    return state


def write_state(state: dict[str, Any]) -> None:
    """Atomic write of the singleton."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_STATE_PATH)


def set_state(
    mode: VoiceMode,
    *,
    tier: VoiceTier = None,
    last_text: str | None = None,
    last_reply_source: str | None = None,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """Update + persist + broadcast the singleton."""
    state = read_state()
    state["mode"] = mode
    if tier is not None:
        state["tier"] = tier
    if last_text is not None:
        state["last_text"] = last_text
    if last_reply_source is not None:
        state["last_reply_source"] = last_reply_source
    if latency_ms is not None:
        state["latency_ms"] = int(latency_ms)
    if cost_usd is not None:
        state["cost_usd"] = float(cost_usd)
    state["updated_at"] = _now_iso()
    write_state(state)
    if _broadcaster is not None:
        try:
            _broadcaster({"type": "voice.state", "state": state})
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice.state broadcast failed: %s", exc)
    return state


def push_level(rms_db: float) -> None:
    """Broadcast a single voice.level frame (no file write)."""
    if _broadcaster is None:
        return
    payload = {
        "type": "voice.level",
        "rms_db": float(rms_db),
        "ts": _now_iso(),
    }
    try:
        _broadcaster(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("voice.level broadcast failed: %s", exc)


__all__ = [
    "VoiceMode",
    "VoiceTier",
    "register_broadcaster",
    "read_state",
    "write_state",
    "set_state",
    "set_hot_mic_enabled",
    "push_level",
]
