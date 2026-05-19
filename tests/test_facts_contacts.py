"""Tests for the contact-graph hook in jarvis.state.facts.extract_facts.

These exercise the W4.2 "X is my Y" opportunistic learning pass — when a
matching sentence is captured we both create a Contact AND yield a
KeyValueFact so the existing facts.jsonl-driven prompt injection still
works.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.state import contacts as contacts_mod
from jarvis.state import facts as facts_mod
from jarvis.state.facts import extract_facts


@pytest.fixture(autouse=True)
def _redirect_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect both facts.jsonl and contacts.jsonl into the per-test tmp."""
    monkeypatch.setattr(
        facts_mod, "_facts_path", lambda: tmp_path / "facts.jsonl"
    )
    monkeypatch.setattr(
        contacts_mod, "_path", lambda: tmp_path / "contacts.jsonl"
    )


def test_contact_pattern_creates_contact_and_fact() -> None:
    """Dr. Patel is my advisor → Contact + KeyValueFact key="advisor"."""
    out = extract_facts("Dr. Patel is my advisor", turn_id="t1")

    fact = next((f for f in out if f.key == "advisor"), None)
    assert fact is not None
    assert "Patel" in fact.value
    assert fact.extracted_from_turn_id == "t1"

    contact = contacts_mod.resolve_name("Dr. Patel")
    assert contact is not None
    assert contact.relation == "advisor"


def test_contact_pattern_colleague() -> None:
    """Pepper is my colleague → contact with relation=colleague."""
    out = extract_facts("Pepper is my colleague", turn_id="t2")

    assert any(f.key == "colleague" and "Pepper" in f.value for f in out)
    contact = contacts_mod.resolve_name("Pepper")
    assert contact is not None
    assert contact.display_name == "Pepper"
    assert contact.relation == "colleague"


def test_contact_pattern_skips_false_positives() -> None:
    """Common idioms must not create phantom contacts."""
    # "this is my idea" — "idea" isn't in the relation whitelist.
    out = extract_facts("this is my idea", turn_id="t3a")
    assert not any(f.key in {"advisor", "colleague", "friend"} for f in out)
    assert contacts_mod.list_contacts() == []

    # "today is my birthday" — lowercase "today" wouldn't pass the
    # leading-capital guard even if "birthday" were a relation; doubly safe.
    out2 = extract_facts("today is my birthday", turn_id="t3b")
    assert not any(f.key == "birthday" for f in out2)
    assert contacts_mod.list_contacts() == []


def test_extract_facts_still_returns_legacy_facts() -> None:
    """Adding the contact pass must not regress existing fact patterns."""
    out = extract_facts(
        "call me J. Dr. Patel is my advisor.", turn_id="t4"
    )
    keys = {f.key for f in out}
    assert "name" in keys  # legacy "call me" pattern
    assert "advisor" in keys  # new contact pattern


def test_contact_pattern_idempotent_on_repeat() -> None:
    """Saying the same sentence twice should not create two contacts."""
    extract_facts("Pepper is my colleague", turn_id="t5a")
    extract_facts("Pepper is my colleague", turn_id="t5b")

    matches = [
        c for c in contacts_mod.list_contacts() if c.display_name == "Pepper"
    ]
    assert len(matches) == 1


def test_contact_failure_does_not_break_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the contact-side write blows up, fact extraction still proceeds."""

    def boom(*_a, **_kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(contacts_mod, "create_contact", boom)
    monkeypatch.setattr(contacts_mod, "resolve_name", lambda _n: None)

    # Should not raise even though the contact side blows up.
    out = extract_facts("call me J. Pepper is my colleague.", turn_id="t6")
    keys = {f.key for f in out}
    assert "name" in keys
