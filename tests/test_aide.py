"""Aide email triage tests."""
from __future__ import annotations

from jarvis.subsystems.aide import (
    TIER_ACTION,
    TIER_INFO,
    TIER_MEETING,
    TIER_SKIP,
    Aide,
    classify_message,
)
from jarvis.subsystems.providers import MockGmail


def test_classify_promo_to_skip():
    msg = {"subject": "Sale!", "snippet": "buy now", "labels": ["UNREAD", "CATEGORY_PROMOTIONS"]}
    assert classify_message(msg) == TIER_SKIP


def test_classify_meeting():
    msg = {"subject": "Sync Friday", "snippet": "let's meet at 3pm", "labels": ["UNREAD"]}
    assert classify_message(msg) == TIER_MEETING


def test_classify_action_keyword():
    msg = {"subject": "Invoice due", "snippet": "please review and approve", "labels": ["UNREAD"]}
    assert classify_message(msg) == TIER_ACTION


def test_classify_important_label():
    msg = {"subject": "FYI", "snippet": "heads up", "labels": ["UNREAD", "IMPORTANT"]}
    assert classify_message(msg) == TIER_ACTION


def test_classify_default_info():
    msg = {"subject": "Hello", "snippet": "just saying hi", "labels": ["UNREAD"]}
    assert classify_message(msg) == TIER_INFO


def test_aide_triage_with_seed():
    aide = Aide(MockGmail())
    resp = aide.triage()
    assert resp.agent == "aide"
    assert resp.action == "triaged"
    counts = resp.result["counts"]
    assert counts[TIER_ACTION] >= 1  # invoice
    assert counts[TIER_MEETING] >= 1  # Friday review (matches 'sync')
    assert counts[TIER_SKIP] >= 1  # newsletter promotion


def test_aide_draft_needs_confirm():
    aide = Aide(MockGmail())
    resp = aide.draft_reply("m1", "Sounds good, see you Friday.")
    assert resp.needs_confirm is True
    assert resp.action == "proposed"
    assert "draft_id" in resp.result["draft"]


def test_aide_send_records():
    g = MockGmail()
    aide = Aide(g)
    resp = aide.send("a@b.com", "subj", "body")
    assert resp.action == "sent"
    assert len(g.sent) == 1
