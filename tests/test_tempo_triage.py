"""Tests for Tempo smart-triage: triage_smart, snooze_mail, triage_status."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.subsystems.providers import MockOutlook
from jarvis.subsystems.tempo import (
    Tempo,
    _active_snoozes,
    _load_snoozes,
    _load_triage_cache,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MAIL_SEED = [
    {
        "id": "m1",
        "from": "boss@company.com",
        "subject": "Urgent: please review the proposal",
        "body_preview": "Can you approve by EOD?",
        "snippet": "Can you approve by EOD?",
        "labels": ["UNREAD", "INBOX"],
        "unread": True,
    },
    {
        "id": "m2",
        "from": "newsletter@digest.io",
        "subject": "Top stories this week",
        "body_preview": "Here are this week's highlights…",
        "snippet": "Here are this week's highlights…",
        "labels": ["UNREAD", "INBOX"],
        "unread": True,
    },
    {
        "id": "m3",
        "from": "noreply@spamco.com",
        "subject": "You've won a prize!",
        "body_preview": "Click here to claim your reward",
        "snippet": "Click here to claim your reward",
        "labels": ["UNREAD", "INBOX"],
        "unread": True,
    },
]

# Canned LLM response covering all three items
_LLM_RESPONSE = json.dumps([
    {"id": "m1", "bucket": "action_required", "reason": "explicit ask with deadline"},
    {"id": "m2", "bucket": "info_only", "reason": "newsletter digest"},
    {"id": "m3", "bucket": "noise", "reason": "bulk marketing no-reply"},
])


@pytest.fixture()
def outlook():
    return MockOutlook(seed_mail=list(_MAIL_SEED))


@pytest.fixture()
def tempo(outlook):
    return Tempo(outlook)


def _patch_llm(monkeypatch, response: str = _LLM_RESPONSE):
    monkeypatch.setattr("jarvis.llm.query_claude_sync", lambda *_a, **_kw: response)


# ── triage_smart — basic bucketing ───────────────────────────────────────────


def test_triage_smart_sorts_into_buckets(monkeypatch, tempo):
    _patch_llm(monkeypatch)
    resp = tempo.triage_smart()

    assert resp.agent == "tempo"
    assert resp.intent == "triage_smart"

    result = resp.result
    action_ids = [m["id"] for m in result["action_required"]]
    info_ids = [m["id"] for m in result["info_only"]]
    noise_ids = [m["id"] for m in result["noise"]]

    assert "m1" in action_ids
    assert "m2" in info_ids
    assert "m3" in noise_ids
    assert result["counts"]["action_required"] == 1
    assert result["counts"]["info_only"] == 1
    assert result["counts"]["noise"] == 1


def test_triage_smart_persists_to_jsonl(monkeypatch, tempo, isolated_state):
    _patch_llm(monkeypatch)
    tempo.triage_smart()

    cache = _load_triage_cache()
    assert set(cache.keys()) == {"m1", "m2", "m3"}
    assert cache["m1"]["bucket"] == "action_required"
    assert cache["m1"]["classified_by"] == "claude"


def test_triage_smart_idempotent_no_reclassify(monkeypatch, tempo, isolated_state):
    """Second call should not invoke the LLM for already-cached IDs."""
    call_count = {"n": 0}

    def counting_llm(*args, **kwargs):
        call_count["n"] += 1
        return _LLM_RESPONSE

    monkeypatch.setattr("jarvis.llm.query_claude_sync", counting_llm)

    tempo.triage_smart()
    assert call_count["n"] == 1

    tempo.triage_smart()
    # Second call — all IDs cached, no new LLM call
    assert call_count["n"] == 1


# ── important sender override ─────────────────────────────────────────────────


def test_important_sender_forces_action_required(monkeypatch, tempo, isolated_state):
    # LLM would classify m2 as info_only, but boss@company.com is important
    monkeypatch.setattr("jarvis.llm.query_claude_sync", lambda *a, **k: _LLM_RESPONSE)

    # Patch load_preferences to return newsletter sender as important
    from jarvis.memory import OperatorPreferences

    monkeypatch.setattr(
        "jarvis.subsystems.tempo.load_preferences",
        lambda: OperatorPreferences(important_senders=("digest.io",)),
    )

    resp = tempo.triage_smart()
    result = resp.result

    # m2 is from newsletter@digest.io — should be overridden to action_required
    action_ids = [m["id"] for m in result["action_required"]]
    assert "m2" in action_ids

    # Verify persisted record shows override
    cache = _load_triage_cache()
    assert cache["m2"]["classified_by"] == "override"
    assert cache["m2"]["bucket"] == "action_required"


def test_important_sender_no_false_overrides(monkeypatch, tempo, isolated_state):
    """Non-matching senders should not be overridden."""
    monkeypatch.setattr("jarvis.llm.query_claude_sync", lambda *a, **k: _LLM_RESPONSE)

    from jarvis.memory import OperatorPreferences

    monkeypatch.setattr(
        "jarvis.subsystems.tempo.load_preferences",
        lambda: OperatorPreferences(important_senders=("vip@example.com",)),
    )

    resp = tempo.triage_smart()
    result = resp.result

    # m3 (noise) should remain noise — spamco.com doesn't match vip@example.com
    noise_ids = [m["id"] for m in result["noise"]]
    assert "m3" in noise_ids


# ── snooze_mail ───────────────────────────────────────────────────────────────


def test_snooze_mail_persists(tempo, isolated_state):
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    resp = tempo.snooze_mail("m2", future)

    assert resp.action == "snoozed"
    assert resp.result["msg_id"] == "m2"
    assert resp.result["until_iso"] == future

    snoozes = _load_snoozes()
    assert snoozes["m2"] == future


def test_snooze_mail_filters_from_triage_smart(monkeypatch, tempo, isolated_state):
    """Snoozed message should not appear in triage_smart output."""
    _patch_llm(monkeypatch)

    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    tempo.snooze_mail("m2", future)

    resp = tempo.triage_smart()
    result = resp.result

    all_ids = (
        [m["id"] for m in result["action_required"]]
        + [m["id"] for m in result["info_only"]]
        + [m["id"] for m in result["noise"]]
    )
    assert "m2" not in all_ids


def test_snooze_expires_and_message_reappears(monkeypatch, tempo, isolated_state):
    """After snooze expiry the message should reappear in triage_smart."""
    _patch_llm(monkeypatch)

    # Snooze already expired (1 hour ago)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    tempo.snooze_mail("m2", past)

    resp = tempo.triage_smart()
    result = resp.result

    all_ids = (
        [m["id"] for m in result["action_required"]]
        + [m["id"] for m in result["info_only"]]
        + [m["id"] for m in result["noise"]]
    )
    assert "m2" in all_ids


def test_snooze_overwrite_existing(tempo, isolated_state):
    """Re-snoozing a message replaces the existing entry."""
    t1 = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    t2 = (datetime.now(UTC) + timedelta(hours=4)).isoformat()

    tempo.snooze_mail("m1", t1)
    tempo.snooze_mail("m1", t2)

    snoozes = _load_snoozes()
    assert snoozes["m1"] == t2


# ── triage_status ─────────────────────────────────────────────────────────────


def test_triage_status_returns_correct_counts(monkeypatch, tempo, isolated_state):
    _patch_llm(monkeypatch)
    tempo.triage_smart()  # populate cache

    status_resp = tempo.triage_status()
    result = status_resp.result

    assert result["counts"]["action_required"] == 1
    assert result["counts"]["info_only"] == 1
    assert result["counts"]["noise"] == 1
    assert result["total_classified"] == 3


def test_triage_status_counts_active_snoozes(monkeypatch, tempo, isolated_state):
    _patch_llm(monkeypatch)
    tempo.triage_smart()

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    tempo.snooze_mail("m1", future)
    tempo.snooze_mail("m2", past)  # expired — should not count

    status_resp = tempo.triage_status()
    assert status_resp.result["snoozed_count"] == 1


def test_triage_status_top_action_required(monkeypatch, tempo, isolated_state):
    _patch_llm(monkeypatch)
    tempo.triage_smart()

    status_resp = tempo.triage_status()
    top = status_resp.result["top_action_required"]
    assert len(top) <= 5
    assert top[0]["bucket"] == "action_required"


def test_triage_status_empty_before_any_classification(tempo, isolated_state):
    """Status when cache is empty should return zero counts without errors."""
    status_resp = tempo.triage_status()
    result = status_resp.result

    assert result["total_classified"] == 0
    assert result["counts"]["action_required"] == 0
    assert result["snoozed_count"] == 0
    assert result["top_action_required"] == []


# ── active_snoozes helper ─────────────────────────────────────────────────────


def test_active_snoozes_excludes_expired():
    now = datetime.now(UTC).isoformat()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    snoozes = {"m1": future, "m2": past, "m3": future}
    active = _active_snoozes(snoozes, now)

    assert "m1" in active
    assert "m3" in active
    assert "m2" not in active


# ── LLM parse failure graceful degradation ────────────────────────────────────


def test_triage_smart_handles_bad_llm_response(monkeypatch, tempo, isolated_state):
    """When LLM returns unparseable content all items fall back to info_only."""
    monkeypatch.setattr(
        "jarvis.llm.query_claude_sync",
        lambda *a, **k: "this is not json",
    )

    resp = tempo.triage_smart()
    result = resp.result

    # All should land in info_only (parse_error fallback)
    info_ids = [m["id"] for m in result["info_only"]]
    assert "m1" in info_ids
    assert "m2" in info_ids
    assert "m3" in info_ids
