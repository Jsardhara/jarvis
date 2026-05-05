"""Persistent chat-turn store (cross-device sync layer for /api/jarvis/chat).

Each turn = one user message + assistant response + tool-call trace + metadata.
Written to JSONL append-only at `state/chat_turns.jsonl` once the SSE stream
for that turn closes. Read at frontend mount to hydrate the chat from any
device.

`user_id` is baked in from day one. Today derived from the bearer token via
SHA-256 truncation (one token = one stable user_id). When real signup/auth
lands, the same field maps to a real user UUID without a schema migration.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import get_settings

log = logging.getLogger(__name__)


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


def _default_path() -> Path:
    return get_settings().state_dir / "chat_turns.jsonl"


def append_turn(record: ChatTurnRecord, *, path: Path | None = None) -> None:
    """Append a single turn record to the JSONL store."""
    target = path or _default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


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
                matches.append(ChatTurnRecord(**raw))
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
