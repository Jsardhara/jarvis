"""Long-term semantic chat memory.

Every turn -> embedding -> appended JSONL. Cosine search returns top K hits.
Falls back gracefully if sentence-transformers is not installed.

CLI backfill:
    python -m jarvis.state.memory_index --backfill
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

EMBED_DIM = 384  # all-MiniLM-L6-v2

# Module-level cache so the model is loaded once per process.
_ST_MODEL: Any = None
_ST_AVAILABLE: bool | None = None  # None = not yet checked


def _get_index_path() -> Path:
    from jarvis.config import get_settings

    return get_settings().state_dir / "jarvis_chat_index.jsonl"


# ── Model ────────────────────────────────────────────────────────────────────


class IndexedTurn(BaseModel):
    turn_id: str
    ts: str  # ISO-8601
    role: str  # "user" | "assistant"
    text: str
    lane: str | None = None  # model id (opus / sonnet)
    embedding: list[float] | None = None
    session_id: str | None = None


# ── Embedding ────────────────────────────────────────────────────────────────


def _check_st_available() -> bool:
    global _ST_AVAILABLE
    if _ST_AVAILABLE is not None:
        return _ST_AVAILABLE
    try:
        import sentence_transformers  # noqa: F401

        _ST_AVAILABLE = True
    except ImportError:
        logger.warning(
            "sentence-transformers not installed — semantic recall disabled. "
            "Install with: pip install 'sentence-transformers>=2.7,<3'"
        )
        _ST_AVAILABLE = False
    return _ST_AVAILABLE


def _load_st_model() -> Any:
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    from sentence_transformers import SentenceTransformer

    _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _ST_MODEL


def embed(text: str) -> list[float] | None:
    """Return a 384-dim embedding for *text*, or None if the package is missing."""
    if not _check_st_available():
        return None
    try:
        model = _load_st_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:
        logger.warning("embed failed: %s", exc)
        return None


# ── Cosine similarity ─────────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    try:
        import numpy as np

        va = np.array(a, dtype=float)
        vb = np.array(b, dtype=float)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0.0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    except ImportError:
        # Pure-Python fallback (rare — numpy is a transitive dep via ST)
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)


# ── Persistence ───────────────────────────────────────────────────────────────


def append_turn(turn: IndexedTurn) -> None:
    """Atomically append one JSON line to the chat index."""
    path = _get_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = turn.model_dump_json() + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _load_all_turns() -> list[IndexedTurn]:
    """Read all indexed turns from disk. Returns [] on any I/O error."""
    path = _get_index_path()
    if not path.exists():
        return []
    turns: list[IndexedTurn] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                turns.append(IndexedTurn.model_validate_json(raw_line))
            except Exception as exc:
                logger.debug("skip malformed index line: %s", exc)
    except OSError as exc:
        logger.warning("chat index read failed: %s", exc)
    return turns


# ── Search ────────────────────────────────────────────────────────────────────


def search(
    query: str,
    top_k: int = 5,
) -> list[tuple[float, IndexedTurn]]:
    """Embed *query* and return the top K turns by cosine similarity.

    Returns an empty list if embedding is unavailable or the index is empty.
    """
    q_vec = embed(query)
    if q_vec is None:
        return []
    turns = _load_all_turns()
    if not turns:
        return []
    scored = _rank_turns(q_vec, turns)
    return scored[:top_k]


def search_window(
    query: str,
    top_k: int = 5,
    days: int = 90,
) -> list[tuple[float, IndexedTurn]]:
    """Like :func:`search` but only considers turns within the last *days* days."""
    q_vec = embed(query)
    if q_vec is None:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    turns = [t for t in _load_all_turns() if _parse_ts(t.ts) >= cutoff]
    if not turns:
        return []
    scored = _rank_turns(q_vec, turns)
    return scored[:top_k]


def _rank_turns(
    q_vec: list[float], turns: list[IndexedTurn]
) -> list[tuple[float, IndexedTurn]]:
    """Score each turn by cosine similarity; skip turns with no embedding."""
    scored: list[tuple[float, IndexedTurn]] = []
    for t in turns:
        if t.embedding is None:
            continue
        sim = _cosine(q_vec, t.embedding)
        scored.append((sim, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO timestamp to aware datetime; return epoch on failure."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=UTC)


# ── Stable turn-ID from raw turn dict ────────────────────────────────────────


def turn_id_from_dict(entry: dict[str, str]) -> str:
    """Derive a stable turn_id from role+text (and optionally ts)."""
    raw = (entry.get("role", "") + entry.get("text", "") + entry.get("ts", "")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


# ── Backfill CLI ─────────────────────────────────────────────────────────────


def _backfill(turn_log_path: Path) -> None:
    """Embed existing turns from the rolling turn log and add to the index.

    Idempotent — turns whose turn_id already appears in the index are skipped.
    """
    if not turn_log_path.exists():
        logger.info("turn log not found at %s — nothing to backfill", turn_log_path)
        return

    try:
        raw: list[dict[str, Any]] = json.loads(turn_log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to read turn log: %s", exc)
        return

    # Build set of already-indexed turn_ids
    existing: set[str] = {t.turn_id for t in _load_all_turns()}

    added = 0
    ts_now = datetime.now(UTC).isoformat()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", ""))
        text = str(entry.get("text", ""))
        if not role or not text:
            continue
        tid = turn_id_from_dict({"role": role, "text": text, "ts": entry.get("ts", ts_now)})
        if tid in existing:
            continue
        vec = embed(text)
        turn = IndexedTurn(
            turn_id=tid,
            ts=entry.get("ts", ts_now),
            role=role,
            text=text,
            embedding=vec,
        )
        append_turn(turn)
        existing.add(tid)
        added += 1
        logger.info("backfill: indexed turn %s (%s, %d chars)", tid, role, len(text))

    logger.info("backfill complete — %d turns added", added)


# ── __main__ ─────────────────────────────────────────────────────────────────


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m jarvis.state.memory_index")
    parser.add_argument("--backfill", action="store_true", help="Backfill from turn log")
    parser.add_argument(
        "--turn-log",
        default=None,
        help="Path to jarvis_turn_log.json (default: state/jarvis_turn_log.json)",
    )
    args = parser.parse_args()

    if args.backfill:
        from jarvis.config import get_settings

        default_path = get_settings().state_dir / "jarvis_turn_log.json"
        turn_log_path = Path(args.turn_log) if args.turn_log else default_path
        _backfill(turn_log_path)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    _main()
