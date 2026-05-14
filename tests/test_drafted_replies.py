"""Tests for the drafted-reply JSONL store (J9)."""
from __future__ import annotations

from datetime import UTC, datetime

from jarvis.config import get_settings
from jarvis.state.drafted_replies import (
    STATUS_APPROVED,
    STATUS_DRAFTED,
    STATUS_REJECTED,
    STATUS_SENT,
    DraftedReply,
    _path,
    append_draft,
    read_drafts,
    update_status,
)


def _make_draft(
    draft_id: str = "d1",
    inbox_event_id: str = "m1",
    status: str = STATUS_DRAFTED,
) -> DraftedReply:
    return DraftedReply(
        id=draft_id,
        inbox_event_id=inbox_event_id,
        to="boss@example.com",
        subject="Re: status",
        body="Thanks — will follow up.",
        drafted_at=datetime.now(UTC).isoformat(),
        status=status,
    )


def test_append_and_read_round_trip():
    draft = _make_draft()
    append_draft(draft)

    all_drafts = read_drafts()
    assert len(all_drafts) == 1
    got = all_drafts[0]
    assert got.id == "d1"
    assert got.inbox_event_id == "m1"
    assert got.to == "boss@example.com"
    assert got.subject == "Re: status"
    assert got.body == "Thanks — will follow up."
    assert got.status == STATUS_DRAFTED
    assert got.sent_at is None


def test_read_drafts_filter_by_status():
    append_draft(_make_draft("d1", "m1", STATUS_DRAFTED))
    append_draft(_make_draft("d2", "m2", STATUS_APPROVED))
    append_draft(_make_draft("d3", "m3", STATUS_REJECTED))

    drafted = read_drafts(status=STATUS_DRAFTED)
    approved = read_drafts(status=STATUS_APPROVED)
    rejected = read_drafts(status=STATUS_REJECTED)

    assert [d.id for d in drafted] == ["d1"]
    assert [d.id for d in approved] == ["d2"]
    assert [d.id for d in rejected] == ["d3"]
    assert len(read_drafts()) == 3


def test_update_status_transitions():
    append_draft(_make_draft("d1", "m1", STATUS_DRAFTED))

    after_approve = update_status("d1", STATUS_APPROVED)
    assert after_approve is not None
    assert after_approve.status == STATUS_APPROVED
    assert read_drafts(status=STATUS_APPROVED)[0].id == "d1"

    after_send = update_status("d1", STATUS_SENT)
    assert after_send is not None
    assert after_send.status == STATUS_SENT
    assert after_send.sent_at is not None

    sent_drafts = read_drafts(status=STATUS_SENT)
    assert len(sent_drafts) == 1
    assert sent_drafts[0].id == "d1"
    assert sent_drafts[0].sent_at is not None

    # Other statuses must be empty after the transition
    assert read_drafts(status=STATUS_DRAFTED) == []
    assert read_drafts(status=STATUS_APPROVED) == []


def test_path_resolves_under_state_dir():
    path = _path()
    assert path == get_settings().state_dir / "drafted_replies.jsonl"
    assert path.parent == get_settings().state_dir
    assert path.name == "drafted_replies.jsonl"
