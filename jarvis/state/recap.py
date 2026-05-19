"""Recap + turn-log persistence helpers extracted from ``jarvis.agent``.

These are pure helpers that operate on a ``JarvisChat`` instance's mutable
state (``_turn_log``, ``_last_lane``). They were pulled out of
``agent.py`` to keep that file under the 800-line cap from CLAUDE.md.

Public surface kept identical so monkey-patching by tests via
``jarvis.agent.<name>`` continues to work — ``agent.py`` re-exports each
function it formerly owned.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover — avoid runtime circular import
    from jarvis.agent import JarvisChat

logger = logging.getLogger(__name__)

# Constants — mirrored from the original agent.py so recap behavior is identical.
RECAP_TURN_PAIRS = 3
RECAP_SAME_LANE_PAIRS = 2  # briefer recap when staying on the same lane
RECAP_MAX_CHARS = 800
TURN_LOG_MAX = 100  # bumped from 12 so hydration from chat_turns.jsonl fits
# Anchor at the project root so the file resolves the same whether the
# importer is uvicorn (started from the repo root), the voice daemon
# (started from any cwd), or a test runner from `tests/`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TURN_LOG_PATH = _PROJECT_ROOT / "state" / "jarvis_turn_log.json"
SEMANTIC_RECAP_TOP_K = 3
SEMANTIC_MIN_SCORE = 0.4
SEMANTIC_MAX_CHARS = 120  # per hit in recap


# ---------- Turn-log persistence ----------


def load_turn_log() -> list[dict[str, str]]:
    """Restore prior conversation turns from disk so memory survives restarts."""
    if not TURN_LOG_PATH.exists():
        return []
    try:
        raw = json.loads(TURN_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("turn-log read failed (%s); starting empty", exc)
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw[-TURN_LOG_MAX:]:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("role"), str)
            and isinstance(entry.get("text"), str)
        ):
            out.append({"role": entry["role"], "text": entry["text"]})
    return out


def save_turn_log(turns: list[dict[str, str]]) -> None:
    """Persist the rolling turn log to disk (atomic write).

    Runs the disk write on a background thread so the chat hot path
    doesn't block on fsync.
    """
    snapshot = list(turns)

    def _write() -> None:
        try:
            TURN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = TURN_LOG_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            tmp.replace(TURN_LOG_PATH)
        except OSError as exc:
            logger.warning("turn-log write failed: %s", exc)

    threading.Thread(target=_write, daemon=True).start()


# ---------- Hydration from unified store ----------


def hydrate_from_unified_store(chat: "JarvisChat", limit: int = 50) -> None:
    """Merge recent ChatTurnRecord entries into ``chat._turn_log``.

    Dedupes against existing entries by ``(role, text)`` so a record
    already on disk in ``jarvis_turn_log.json`` isn't double-counted.
    Ordered oldest-first to match the rolling-log convention.
    """
    try:
        from jarvis.state.chat_turns import read_recent

        records = read_recent(user_id="default", limit=limit)
    except Exception as exc:  # noqa: BLE001 — never block init on memory read
        logger.debug("unified-store hydrate skipped: %s", exc)
        return
    if not records:
        return
    existing: set[tuple[str, str]] = {
        (e.get("role", ""), e.get("text", "")) for e in chat._turn_log
    }
    hydrated: list[dict[str, str]] = []
    # ``read_recent`` returns chronological order (oldest-first).
    for rec in records:
        user_text = (rec.user_text or "").strip()
        asst_text = (rec.assistant_text or "").strip()
        if user_text and ("user", user_text) not in existing:
            hydrated.append({"role": "user", "text": user_text})
            existing.add(("user", user_text))
        if asst_text and ("assistant", asst_text) not in existing:
            hydrated.append({"role": "assistant", "text": asst_text})
            existing.add(("assistant", asst_text))
    if not hydrated:
        return
    merged = hydrated + chat._turn_log
    if len(merged) > TURN_LOG_MAX:
        merged = merged[-TURN_LOG_MAX:]
    chat._turn_log = merged


# ---------- Recap formatting ----------


def build_recap(
    chat: "JarvisChat",
    upcoming_message: str | None = None,
    *,
    lane_switch: bool = True,
) -> str | None:
    """Return a short context recap of the last few turn pairs, or None.

    ``lane_switch=True`` → full recap (last 3 pairs + top-3 semantic).
    ``lane_switch=False`` → brief recap (last 2 pairs + top-1 semantic),
    used when the same model lane carries forward so the model still
    sees rolling context on the first turn of a new session.
    """
    if not chat._turn_log:
        return None
    # Take the last N user/assistant pairs
    pairs: list[tuple[str, str]] = []
    user_buf: str | None = None
    for entry in chat._turn_log:
        if entry["role"] == "user":
            user_buf = entry["text"]
        elif entry["role"] == "assistant" and user_buf is not None:
            pairs.append((user_buf, entry["text"]))
            user_buf = None
    if not pairs:
        return None
    pair_cap = RECAP_TURN_PAIRS if lane_switch else RECAP_SAME_LANE_PAIRS
    recent = pairs[-pair_cap:]
    header = (
        "[Earlier in this thread, on a different model:]"
        if lane_switch
        else "[Rolling thread context:]"
    )
    lines = [header]
    for u, a in recent:
        lines.append(f"- You said: {u.strip()[:200]}")
        lines.append(f"- I responded: {a.strip()[:200]}")
    recap = "\n".join(lines)
    recap = recap[:RECAP_MAX_CHARS]

    # Augment with semantic hits when an upcoming message is known.
    if upcoming_message:
        top_k = SEMANTIC_RECAP_TOP_K if lane_switch else 1
        semantic_lines = semantic_recap_lines(upcoming_message, top_k=top_k)
        if semantic_lines:
            budget = RECAP_MAX_CHARS - len(recap)
            if budget > 40:
                block = "\n".join(semantic_lines)
                recap += "\n" + block[:budget]
    return recap


def semantic_recap_lines(
    query: str, *, top_k: int = SEMANTIC_RECAP_TOP_K
) -> list[str]:
    """Return formatted lines for semantic recall to embed in recap."""
    try:
        from jarvis.state.memory_index import search as _search

        hits = _search(query, top_k=top_k)
    except Exception as exc:
        logger.debug("semantic recap search failed: %s", exc)
        return []
    if not hits:
        return []
    lines = ["[Possibly relevant from earlier:]"]
    for score, turn in hits:
        if score < SEMANTIC_MIN_SCORE:
            continue
        snippet = turn.text.strip().replace("\n", " ")[:SEMANTIC_MAX_CHARS]
        lines.append(f"- [{turn.role}] {snippet}")
    return lines if len(lines) > 1 else []


# ---------- Turn recording ----------


def record_turn(
    chat: "JarvisChat", role: str, text: str, lane: str | None = None
) -> None:
    if not text:
        return
    chat._turn_log.append({"role": role, "text": text})
    if len(chat._turn_log) > TURN_LOG_MAX:
        chat._turn_log = chat._turn_log[-TURN_LOG_MAX:]
    # Route through ``jarvis.agent`` so tests that monkey-patch
    # ``jarvis.agent._save_turn_log`` still intercept the write.
    from jarvis import agent as _agent

    _agent._save_turn_log(chat._turn_log)
    index_turn(role=role, text=text, lane=lane)
    if role == "user":
        extract_and_persist_facts(text)
        mark_operator_present("chat")


def mark_operator_present(surface: str) -> None:
    """Record an operator-presence mark so sentinel can detect inactivity.

    Best-effort: failures are logged at debug and swallowed. Never let the
    presence hook break the chat hot path.
    """
    try:
        from jarvis.state.operator_presence import mark_present

        mark_present(surface)
    except Exception as exc:  # noqa: BLE001
        logger.debug("operator_presence mark skipped: %s", exc)


def extract_and_persist_facts(text: str) -> None:
    """Regex-extract declarative facts from a user turn; append to disk.

    Best-effort: any failure is logged at debug level and swallowed.
    Never lets fact capture break the chat hot path.
    """
    try:
        from jarvis.state.facts import append_fact, extract_facts
        from jarvis.state.memory_index import turn_id_from_dict

        tid = turn_id_from_dict({"role": "user", "text": text})
        for fact in extract_facts(text, turn_id=tid):
            append_fact(fact)
    except Exception as exc:  # noqa: BLE001 — facts must never break chat
        logger.debug("facts extract skipped: %s", exc)


def record_unified_turn(
    *,
    user_text: str,
    assistant_text: str,
    lane: str | None,
    surface: Literal["voice", "chat", "api"],
    session_id: str = "default",
    user_id: str = "default",
    turn_id: str | None = None,
    cost_usd: float = 0.0,
) -> None:
    """Append a turn pair to the unified ``chat_turns.jsonl`` store.

    Called from voice paths (cheap_handler) AND from JarvisChat itself
    when invoked outside the HTTP layer, so the dashboard sees every
    turn regardless of surface. Best-effort: failures are warnings.
    """
    if not user_text and not assistant_text:
        return
    try:
        from datetime import UTC, datetime
        from uuid import uuid4

        from jarvis.state.chat_turns import ChatTurnRecord, append_turn

        rec = ChatTurnRecord(
            user_id=user_id,
            turn_id=turn_id or uuid4().hex,
            user_text=user_text,
            assistant_text=assistant_text,
            model=lane or "",
            cost_usd=cost_usd,
            ts=datetime.now(UTC).isoformat(),
            session_id=session_id,
            surface=surface,
        )
        append_turn(rec)
    except Exception as exc:  # noqa: BLE001
        logger.warning("unified turn write failed: %s", exc)


def index_turn(role: str, text: str, lane: str | None) -> None:
    """Persist turn to semantic index. Never raises — failures are warnings.

    Embedding is dispatched to a background thread so the chat hot path
    is never blocked on the model call or disk write.
    """

    def _run() -> None:
        try:
            from datetime import UTC, datetime

            from jarvis.state.memory_index import (
                IndexedTurn,
                append_turn,
                embed,
                turn_id_from_dict,
            )

            ts = datetime.now(UTC).isoformat()
            raw = {"role": role, "text": text, "ts": ts}
            tid = turn_id_from_dict(raw)
            vec = embed(text)
            turn = IndexedTurn(
                turn_id=tid,
                ts=ts,
                role=role,
                text=text,
                lane=lane,
                embedding=vec,
            )
            append_turn(turn)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory index write failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
