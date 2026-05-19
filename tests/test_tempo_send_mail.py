"""Tests for Tempo.send_mail recipient resolution against the contact graph.

W4.2 — send_mail's authority contract is untouched (needs_confirm=True),
but it now resolves bare names through ``jarvis.state.contacts`` before
staging. Bare emails pass through unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.agents.providers import MockOutlook
from jarvis.agents.tempo.agent import Tempo
from jarvis.state import contacts as contacts_mod


@pytest.fixture(autouse=True)
def _redirect_contacts_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contacts_mod, "_path", lambda: tmp_path / "contacts.jsonl"
    )


def _tempo() -> Tempo:
    return Tempo(MockOutlook(seed_mail=[]))


def test_resolve_recipient_passthrough_email() -> None:
    """A literal email address is returned unchanged."""
    assert _tempo().resolve_recipient("a@b.com") == "a@b.com"


def test_resolve_recipient_alias_to_email() -> None:
    """A nickname resolves to the contact's primary email."""
    contacts_mod.create_contact(
        "Pepper Potts",
        relation="colleague",
        aliases=["Pepper"],
        email="pepper@stark.com",
    )
    assert _tempo().resolve_recipient("Pepper") == "pepper@stark.com"


def test_resolve_recipient_unknown_raises() -> None:
    with pytest.raises(ValueError):
        _tempo().resolve_recipient("Bruce Banner")


def test_resolve_recipient_contact_without_email_raises() -> None:
    """Resolving a contact who has no email is a hard error, not silent."""
    contacts_mod.create_contact("Dr. Patel", relation="advisor")
    with pytest.raises(ValueError):
        _tempo().resolve_recipient("Dr. Patel")


def test_send_mail_resolves_alias_and_keeps_needs_confirm() -> None:
    """send_mail resolves "Pepper" → email and still gates via needs_confirm."""
    contacts_mod.create_contact(
        "Pepper Potts",
        relation="colleague",
        aliases=["Pepper"],
        email="pepper@stark.com",
    )

    resp = _tempo().send_mail(to="Pepper", subject="hi", body="ping")

    assert resp.agent == "tempo"
    assert resp.intent == "send_mail"
    assert resp.action == "proposed"
    assert resp.needs_confirm is True
    assert resp.result["to"] == "pepper@stark.com"
    assert resp.result["subject"] == "hi"
    assert resp.result["body"] == "ping"


def test_send_mail_passthrough_email_still_gated() -> None:
    """A literal email recipient still needs_confirm."""
    resp = _tempo().send_mail(
        to="x@example.com", subject="hi", body="hello"
    )
    assert resp.needs_confirm is True
    assert resp.result["to"] == "x@example.com"
