"""Training-dataset extractor — turn live state into fine-tune-ready JSONL.

Reads from the JSONL stores Jarvis is already writing every day and emits
ShareGPT-format training examples into ``state/training/``. By the time the
local PC arrives, months of personalised data are ready for Unsloth /
Axolotl LoRA fine-tunes — the orchestrator's chat persona, tempo's email
voice, and forge's code style.

ShareGPT was chosen over Alpaca because:

* Multi-turn conversations map naturally (Jarvis chat is multi-turn).
* Unsloth and Axolotl both accept it out of the box.
* Easier to add tool-call traces later as additional ``conversations``
  entries.

Output shape (one JSON object per line)::

    {
        "source": "chat_turns",
        "turn_id": "...",
        "ts": "2026-05-19T...",
        "conversations": [
            {"from": "human", "value": "<user_text>"},
            {"from": "gpt",   "value": "<assistant_text>"}
        ]
    }

Each extractor is idempotent — re-running over the same source produces the
same output file with no duplicates. ``turn_id`` (or the equivalent stable
key) is the dedup token.

The extractors are sentinel-driven later — a daily cron will call
:func:`extract_all` so the training corpus stays current without operator
intervention. The cron wiring lives in ``apps/sentinel/scheduler.py``; this
module just exposes the pure functions.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from jarvis import paths

log = logging.getLogger(__name__)

_MIN_TEXT_LEN = 2  # skip turns shorter than this (whitespace, punctuation only)


@dataclass(frozen=True)
class ExtractResult:
    """Summary of one extractor run."""

    source: str
    target: Path
    written: int
    skipped: int
    deduped: int


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _default_chat_turns_source() -> Path:
    """Where chat_turns.jsonl lives in this install."""
    return paths.state_dir() / "chat_turns.jsonl"


def _default_drafted_replies_source() -> Path:
    return paths.state_dir() / "drafted_replies.jsonl"


def _chat_persona_target() -> Path:
    return paths.training_dir() / "chat_persona.jsonl"


def _email_voice_target() -> Path:
    return paths.training_dir() / "email_voice.jsonl"


# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file. Skips malformed lines with a warning."""
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            log.warning("training.extract: skipping malformed line in %s", path)
    return rows


def _existing_ids(target: Path, key: str) -> set[str]:
    """Read ``target`` and return the set of ``key`` values already written.

    Used for idempotent re-runs — extractors append only new examples.
    """
    seen: set[str] = set()
    if not target.exists():
        return seen
    for raw in target.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        val = entry.get(key)
        if isinstance(val, str):
            seen.add(val)
    return seen


def _append_jsonl(target: Path, rows: list[dict]) -> None:
    if not rows:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def extract_chat_persona(
    source: Path | None = None,
    target: Path | None = None,
) -> ExtractResult:
    """Pair user + assistant turns from chat_turns.jsonl into ShareGPT examples.

    Each ChatTurnRecord already carries both sides of a turn, so the pairing
    is direct — no sliding window needed. Skips turns with empty text on
    either side and turns whose ``turn_id`` is already in the target file.
    """
    src = source or _default_chat_turns_source()
    tgt = target or _chat_persona_target()

    rows = _read_jsonl(src)
    seen = _existing_ids(tgt, key="turn_id")

    new_examples: list[dict] = []
    skipped = 0
    deduped = 0
    for row in rows:
        turn_id = str(row.get("turn_id") or "")
        user_text = str(row.get("user_text") or "").strip()
        assistant_text = str(row.get("assistant_text") or "").strip()

        if not turn_id or not user_text or not assistant_text:
            skipped += 1
            continue
        if len(user_text) < _MIN_TEXT_LEN or len(assistant_text) < _MIN_TEXT_LEN:
            skipped += 1
            continue
        if turn_id in seen:
            deduped += 1
            continue

        new_examples.append(
            {
                "source": "chat_turns",
                "turn_id": turn_id,
                "ts": row.get("ts", ""),
                "conversations": [
                    {"from": "human", "value": user_text},
                    {"from": "gpt", "value": assistant_text},
                ],
            }
        )
        seen.add(turn_id)

    _append_jsonl(tgt, new_examples)
    return ExtractResult(
        source="chat_turns",
        target=tgt,
        written=len(new_examples),
        skipped=skipped,
        deduped=deduped,
    )


def extract_email_voice(
    source: Path | None = None,
    target: Path | None = None,
) -> ExtractResult:
    """Emit reply-body training examples from drafted_replies.jsonl.

    Only ``approved`` or ``sent`` drafts are included — these are the ones
    the operator vetted as "this sounds like me". Drafts in ``drafted`` or
    ``rejected`` status are excluded.

    Without the original incoming message body in the same store we can't
    build a true (incoming -> reply) pair yet; this v1 extractor records the
    subject + recipient as the human turn and the reply body as the gpt
    turn, which still captures voice/tone. A future pass can join against
    ``state/inbox.jsonl`` for the original body.
    """
    src = source or _default_drafted_replies_source()
    tgt = target or _email_voice_target()

    rows = _read_jsonl(src)
    seen = _existing_ids(tgt, key="draft_id")

    new_examples: list[dict] = []
    skipped = 0
    deduped = 0
    for row in rows:
        status = str(row.get("status") or "")
        if status not in ("approved", "sent"):
            skipped += 1
            continue

        draft_id = str(row.get("id") or "")
        subject = str(row.get("subject") or "").strip()
        recipient = str(row.get("to") or "").strip()
        body = str(row.get("body") or "").strip()

        if not draft_id or not body:
            skipped += 1
            continue
        if len(body) < _MIN_TEXT_LEN:
            skipped += 1
            continue
        if draft_id in seen:
            deduped += 1
            continue

        prompt = f"Draft a reply to {recipient}. Subject: {subject}".strip()

        new_examples.append(
            {
                "source": "drafted_replies",
                "draft_id": draft_id,
                "ts": row.get("drafted_at", ""),
                "conversations": [
                    {"from": "human", "value": prompt},
                    {"from": "gpt", "value": body},
                ],
            }
        )
        seen.add(draft_id)

    _append_jsonl(tgt, new_examples)
    return ExtractResult(
        source="drafted_replies",
        target=tgt,
        written=len(new_examples),
        skipped=skipped,
        deduped=deduped,
    )


def extract_all() -> list[ExtractResult]:
    """Run every extractor in sequence. Returns one result per source.

    Called nightly by the sentinel scheduler once wired up. Safe to call
    from a CLI for ad-hoc dataset refreshes -- idempotent.
    """
    return [
        extract_chat_persona(),
        extract_email_voice(),
    ]
