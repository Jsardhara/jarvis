"""Tests for Tempo.draft_replies (J9 autonomous email drafting)."""
from __future__ import annotations

import pytest

from jarvis.agents.providers import MockOutlook
from jarvis.agents.tempo.agent import Tempo
from jarvis.state.drafted_replies import read_drafts

# Mail seeds: m1 + m2 hit action keywords ("review", "urgent"); m3 is a
# promo so the classifier maps it to skip, never to action_required.
_ACTION_MAIL = [
    {
        "id": "m1",
        "from": "boss@company.com",
        "subject": "Please review the proposal urgently",
        "snippet": "Can you review by EOD?",
        "body_preview": "Can you review by EOD?",
        "labels": ["UNREAD", "INBOX"],
    },
    {
        "id": "m2",
        "from": "ops@vendor.com",
        "subject": "Action required: approve invoice",
        "snippet": "Please approve before Friday.",
        "body_preview": "Please approve before Friday.",
        "labels": ["UNREAD", "INBOX"],
    },
]

_NON_ACTION_MAIL = [
    {
        "id": "m3",
        "from": "newsletter@medium.com",
        "subject": "Top stories this week",
        "snippet": "Best engineering reads",
        "body_preview": "Best engineering reads",
        "labels": ["UNREAD", "INBOX", "CATEGORY_PROMOTIONS"],
    },
    {
        "id": "m4",
        "from": "friend@example.com",
        "subject": "Lunch sometime?",
        "snippet": "Wondering if you're around.",
        "body_preview": "Wondering if you're around.",
        "labels": ["UNREAD", "INBOX"],
    },
]


@pytest.fixture
def patch_llm(monkeypatch):
    """Replace query_claude_sync (looked up dynamically inside _draft_one)."""
    import jarvis.llm.client as client

    monkeypatch.setattr(
        client, "query_claude_sync", lambda *_a, **_kw: "draft body"
    )


def test_draft_replies_skips_when_no_action_required(patch_llm):
    outlook = MockOutlook(seed_mail=list(_NON_ACTION_MAIL))
    tempo = Tempo(outlook)

    resp = tempo.draft_replies(limit=5)

    assert resp.result["count"] == 0
    assert resp.result["draft_ids"] == []
    assert read_drafts() == []


def test_draft_replies_persists_drafts(patch_llm):
    outlook = MockOutlook(seed_mail=list(_ACTION_MAIL))
    tempo = Tempo(outlook)

    resp = tempo.draft_replies(limit=5)

    assert resp.result["count"] == 2
    draft_ids = resp.result["draft_ids"]
    assert len(draft_ids) == 2

    stored = read_drafts()
    assert len(stored) == 2
    stored_ids = {d.id for d in stored}
    assert stored_ids == set(draft_ids)

    inbox_ids = {d.inbox_event_id for d in stored}
    assert inbox_ids == {"m1", "m2"}
    for d in stored:
        assert d.body == "draft body"
        assert d.status == "drafted"
        assert d.subject.lower().startswith("re:")
        assert d.sent_at is None


def test_draft_replies_response_shape(patch_llm):
    outlook = MockOutlook(seed_mail=list(_ACTION_MAIL))
    tempo = Tempo(outlook)

    resp = tempo.draft_replies(limit=5)

    assert resp.agent == "tempo"
    assert resp.intent == "draft_replies"
    assert resp.action == "drafted"
    assert resp.needs_confirm is False
    assert resp.confidence == pytest.approx(0.9)
    assert set(resp.result.keys()) >= {"count", "draft_ids"}
    assert resp.result["count"] == len(resp.result["draft_ids"])
