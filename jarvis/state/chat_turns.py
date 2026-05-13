"""Persistent chat-turn store (cross-device sync layer for /api/jarvis/chat).

Each turn = one user message + assistant response + tool-call trace + metadata.
Written to JSONL append-only at `state/chat_turns.jsonl` once the SSE stream
for that turn closes. Read at frontend mount to hydrate the chat from any
device.

`user_id` is baked in from day one. Today derived from the bearer token via
SHA-256 truncation (one token = one stable user_id). When real signup/auth
lands, the same field maps to a real user UUID without a schema migration.

`session_id` + `surface` tag where each turn originated (chat HTTP, voice
daemon, etc.) so a single store can fan out to multiple frontends without
losing provenance.

Live pub/sub: callers (e.g. SSE endpoints) can ``subscribe()`` to receive
every new turn as it is appended. Used by the dashboard to flip from
poll-only hydration to real-time push when a voice turn lands.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)


Surface = Literal["voice", "chat", "api"]


@dataclass(frozen=True)
class ChatTurnRecord:
    user_id: str
    turn_id: str
    user_text: str
    assistant_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    ts: str = ""
    # New: provenance fields. Defaulted so legacy records still load.
    session_id: str = "default"
    surface: Surface = "chat"


def _default_path() -> Path:
    return get_settings().state_dir / "chat_turns.jsonl"


# Pub/sub for live turn pushes (SSE).

_subscribers: list[asyncio.Queue[dict[str, Any]]] = []
_subscribers_lock = threading.Lock()


def _publish(record: ChatTurnRecord) -> None:
    """Fan out a new turn to every active subscriber. Never raises."""
    payload = asdict(record)
    with _subscribers_lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            log.debug("turn subscriber queue full; dropping push")
        except Exception:  # noqa: BLE001 - never let pub/sub break appends
            log.warning("turn subscriber failed", exc_info=True)


async def subscribe() -> AsyncIterator[dict[str, Any]]:
    """Yield every new turn appended after ``subscribe`` is called.

    The caller is responsible for handling cancellation; the queue is
    unregistered automatically when the generator is closed.
    """
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
    with _subscribers_lock:
        _subscribers.append(queue)
    try:
        while True:
            payload = await queue.get()
            yield payload
    finally:
        with _subscribers_lock:
            if queue in _subscribers:
                _subscribers.remove(queue)


def append_turn(record: ChatTurnRecord, *, path: Path | None = None) -> None:
    """Append a single turn record to the JSONL store and notify subscribers."""
    target = path or _default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(target)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    _publish(record)


_ALLOWED_FIELDS = {
    "user_id", "turn_id", "user_text", "assistant_text",
    "tool_calls", "model", "cost_usd", "duration_ms", "ts",
    "session_id", "surface",
}


def read_recent(
    user_id: str, *, limit: int = 50, path: Path | None = None
) -> list[ChatTurnRecord]:
    """Return the most recent `limit` turns for the given user, oldest-first."""
    target = path or _default_path()
    if not target.exists():
        return []

    matches: list[ChatTurnRecord] = []
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                log.warning("skipping corrupt chat_turns line")
                continue
            if raw.get("user_id") != user_id:
                continue
            try:
                # Filter to known fields so a newer-written record with
                # extra keys still loads under an older code path.
                clean = {k: v for k, v in raw.items() if k in _ALLOWED_FIELDS}
                matches.append(ChatTurnRecord(**clean))
            except TypeError:
                log.warning("skipping chat_turns record with bad schema")

    return matches[-limit:] if limit > 0 else matches


def user_id_from_token(token: str | None) -> str:
    """Derive a stable user_id from a bearer token.

    Today: any non-empty token deterministically maps to a 16-char hex id.
    When signup ships, callers will supply a real user UUID instead.
    """
    if not token:
        return "default"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:16]
