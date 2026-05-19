"""Tests for jarvis.state.contacts — multi-user contact graph."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.state import contacts as contacts_mod
from jarvis.state.contacts import (
    create_contact,
    get_contact,
    list_contacts,
    render_contacts_for_prompt,
    resolve_name,
    update_contact,
)


@pytest.fixture(autouse=True)
def _redirect_contacts_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    target = tmp_path / "contacts.jsonl"
    monkeypatch.setattr(contacts_mod, "_path", lambda: target)
    return target


def test_create_contact_round_trip() -> None:
    c = create_contact(
        "Pepper Potts",
        relation="colleague",
        aliases=["Pepper", "Pep"],
        email="pepper@stark.com",
        notes="CEO of Stark Industries",
    )
    assert c.id
    assert c.display_name == "Pepper Potts"
    assert c.aliases == ["Pepper", "Pep"]
    assert c.email == "pepper@stark.com"
    assert c.relation == "colleague"
    assert c.created
    assert c.updated == c.created

    fetched = get_contact(c.id)
    assert fetched is not None
    assert fetched.display_name == "Pepper Potts"
    assert fetched.aliases == ["Pepper", "Pep"]
    assert fetched.email == "pepper@stark.com"


def test_list_contacts_filters_by_relation() -> None:
    create_contact("Dr. Patel", relation="advisor")
    create_contact("Pepper", relation="colleague")
    create_contact("Tony Stark", relation="colleague")

    advisors = list_contacts(relation="advisor")
    colleagues = list_contacts(relation="colleague")

    assert [c.display_name for c in advisors] == ["Dr. Patel"]
    assert sorted(c.display_name for c in colleagues) == ["Pepper", "Tony Stark"]


def test_list_contacts_sorted_by_display_name() -> None:
    create_contact("Zelda", relation="friend")
    create_contact("alpha", relation="friend")
    create_contact("Mike", relation="friend")

    names = [c.display_name for c in list_contacts()]
    assert names == ["alpha", "Mike", "Zelda"]


def test_get_contact_unknown_returns_none() -> None:
    assert get_contact("does-not-exist") is None


def test_resolve_name_case_insensitive_display_name() -> None:
    create_contact("Pepper Potts", relation="colleague", email="p@stark.com")
    hit = resolve_name("pepper potts")
    assert hit is not None
    assert hit.display_name == "Pepper Potts"


def test_resolve_name_matches_alias() -> None:
    create_contact(
        "Pepper Potts",
        relation="colleague",
        aliases=["Pepper", "Ms. Potts"],
        email="p@stark.com",
    )
    hit = resolve_name("PEPPER")
    assert hit is not None
    assert hit.display_name == "Pepper Potts"

    hit2 = resolve_name("Ms. Potts")
    assert hit2 is not None
    assert hit2.display_name == "Pepper Potts"


def test_resolve_name_unknown_returns_none() -> None:
    create_contact("Pepper", relation="colleague")
    assert resolve_name("Bruce Banner") is None
    assert resolve_name("") is None


def test_update_contact_patches_fields() -> None:
    c = create_contact("Pepper", relation="colleague")
    bumped = update_contact(
        c.id,
        display_name="Pepper Potts",
        aliases=["Pep"],
        email="pepper@stark.com",
        relation="friend",
        notes="became friend",
    )
    assert bumped is not None
    assert bumped.display_name == "Pepper Potts"
    assert bumped.aliases == ["Pep"]
    assert bumped.email == "pepper@stark.com"
    assert bumped.relation == "friend"
    assert bumped.notes == "became friend"
    assert bumped.updated >= c.updated

    refetch = get_contact(c.id)
    assert refetch is not None
    assert refetch.display_name == "Pepper Potts"
    assert refetch.email == "pepper@stark.com"


def test_update_contact_unknown_returns_none() -> None:
    assert update_contact("nope", display_name="Foo") is None


def test_update_contact_ignores_unknown_keys() -> None:
    c = create_contact("Pepper", relation="colleague")
    bumped = update_contact(c.id, display_name="Pepper Potts", bogus="x")
    assert bumped is not None
    assert bumped.display_name == "Pepper Potts"
    assert not hasattr(bumped, "bogus")


def test_render_contacts_for_prompt_empty() -> None:
    assert render_contacts_for_prompt() == ""


def test_render_contacts_for_prompt_populated() -> None:
    create_contact(
        "Pepper Potts",
        relation="colleague",
        email="pepper@stark.com",
    )
    create_contact("Dr. Patel", relation="advisor")
    block = render_contacts_for_prompt()
    assert "Known contacts:" in block
    assert "Pepper Potts" in block
    assert "(colleague)" in block
    assert "<pepper@stark.com>" in block
    assert "Dr. Patel" in block
    assert "(advisor)" in block
