"""Drafted-reply store — JSONL persistence for J9 autonomous email drafting.

Sentinel calls ``tempo.draft_replies()`` overnight; each generated draft lands
in ``state/drafted_replies.jsonl`` with status="drafted". The operator reviews
in the morning, flips status to "approved" or "rejected", and the eventual
send still goes through ``tempo.send_mail`` (needs_confirm=True per the
Jarvis confirmation matrix — drafting is non-destructive, sending is not).

Status transitions:
    drafted → approved → sent
    drafted → rejected
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)

STATUS_DRAFTED = "drafted"
STATUS_APPROVED = "approved"
STATUS_SENT = "sent"
STATUS_REJECTED = "rejected"

_ALLOWED_STATUSES = {STATUS_DRAFTED, STATUS_APPROVED, STATUS_SENT, STATUS_REJECTED}


@dataclass(frozen=True)
class DraftedReply:
    """One generated draft awaiting operator review."""

    id: str
    inbox_event_id: str
    to: str
    subject: str
    body: str
    drafted_at: str
    status: str
    sent_at: str | None = None


def _path() -> Path:
    return get_settings().state_dir / "drafted_replies.jsonl"


def append_draft(reply: DraftedReply) -> None:
    """Append a draft record to the JSONL store."""
    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(target)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(reply), ensure_ascii=False) + "\n")


def _load_all() -> list[DraftedReply]:
    """Load every draft (most recent write wins per id)."""
    target = _path()
    if not target.exists():
        return []
    by_id: dict[str, DraftedReply] = {}
    order: list[str] = []
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                log.warning("skipping corrupt drafted_replies line")
                continue
            try:
                rec = DraftedReply(**raw)
            except TypeError:
                log.warning("skipping drafted_replies record with bad schema")
                continue
            if rec.id not in by_id:
                order.append(rec.id)
            by_id[rec.id] = rec
    return [by_id[i] for i in order]


def read_drafts(
    status: str | None = None, limit: int = 50
) -> list[DraftedReply]:
    """Return drafts, newest-last. Filter by ``status`` when supplied."""
    items = _load_all()
    if status is not None:
        items = [r for r in items if r.status == status]
    if limit and limit > 0:
        return items[-limit:]
    return items


def update_status(draft_id: str, new_status: str) -> DraftedReply | None:
    """Transition a draft's status. Rewrites the file (low write rate)."""
    if new_status not in _ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {new_status}")

    items = _load_all()
    found: DraftedReply | None = None
    updated_items: list[DraftedReply] = []
    for rec in items:
        if rec.id == draft_id:
            from dataclasses import replace

            sent_at = rec.sent_at
            if new_status == STATUS_SENT and sent_at is None:
                from datetime import UTC, datetime

                sent_at = datetime.now(UTC).isoformat()
            updated = replace(rec, status=new_status, sent_at=sent_at)
            found = updated
            updated_items.append(updated)
        else:
            updated_items.append(rec)

    if found is None:
        return None

    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in updated_items:
            fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    tmp.replace(target)
    return found
