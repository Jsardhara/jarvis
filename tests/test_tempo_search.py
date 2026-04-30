"""Tests for Tempo search_mail + list_recent_mail (read+unread coverage)."""
from __future__ import annotations

from jarvis.subsystems.providers import MockOutlook
from jarvis.subsystems.tempo import Tempo


def _seed() -> list[dict]:
    return [
        {
            "id": "m1",
            "from": "prof@uni.edu",
            "subject": "Test moved to Friday",
            "snippet": "Heads up — exam moved from Wednesday to Friday.",
            "labels": ["INBOX"],  # already read
        },
        {
            "id": "m2",
            "from": "boss@co.com",
            "subject": "Review",
            "snippet": "review the proposal",
            "labels": ["UNREAD", "INBOX"],
        },
        {
            "id": "m3",
            "from": "spam@noreply.io",
            "subject": "Win a prize",
            "snippet": "click to claim",
            "labels": ["INBOX"],  # read junk
        },
    ]


def _tempo() -> Tempo:
    return Tempo(MockOutlook(seed_mail=_seed()))


def test_search_mail_finds_read_message_by_subject() -> None:
    """Bug repro: a READ email about 'test moved' must be findable."""
    resp = _tempo().search_mail(query="test moved")
    assert resp.action == "searched"
    assert resp.result["count"] == 1
    hit = resp.result["hits"][0]
    assert hit["id"] == "m1"
    assert hit["is_unread"] is False


def test_search_mail_matches_subject_body_or_sender() -> None:
    t = _tempo()
    assert t.search_mail("proposal").result["count"] == 1
    assert t.search_mail("prof@uni.edu").result["count"] == 1
    assert t.search_mail("nonexistent-token").result["count"] == 0


def test_search_mail_empty_query_returns_no_hits() -> None:
    resp = _tempo().search_mail(query="   ")
    assert resp.result["count"] == 0
    assert resp.result["hits"] == []


def test_list_recent_mail_returns_read_and_unread() -> None:
    resp = _tempo().list_recent_mail(max_results=10)
    assert resp.action == "listed"
    ids = {m["id"] for m in resp.result["messages"]}
    assert ids == {"m1", "m2", "m3"}
    unread_flags = {m["id"]: m["is_unread"] for m in resp.result["messages"]}
    assert unread_flags["m1"] is False
    assert unread_flags["m2"] is True
    assert unread_flags["m3"] is False


def test_list_recent_mail_respects_max_results() -> None:
    resp = _tempo().list_recent_mail(max_results=2)
    assert resp.result["count"] == 2
