"""Tests for jarvis.state.facts — declarative-fact capture."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.state import facts as facts_mod
from jarvis.state.facts import (
    KeyValueFact,
    append_fact,
    extract_facts,
    read_facts,
    render_facts_for_prompt,
)


@pytest.fixture(autouse=True)
def _redirect_facts_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect state/facts.jsonl to a per-test tmp file."""
    target = tmp_path / "facts.jsonl"
    monkeypatch.setattr(facts_mod, "_facts_path", lambda: target)
    return target


def test_extract_i_prefer() -> None:
    out = extract_facts("i prefer dark roast coffee", turn_id="t1")
    assert out, "expected at least one fact"
    pref = next((f for f in out if f.key == "preference"), None)
    assert pref is not None
    assert pref.value == "dark roast coffee"
    assert pref.extracted_from_turn_id == "t1"


def test_extract_call_me() -> None:
    out = extract_facts("call me J", turn_id="t2")
    name = next((f for f in out if f.key == "name"), None)
    assert name is not None
    assert name.value == "J"


def test_extract_remember_that() -> None:
    out = extract_facts(
        "remember that my flight is at 6am", turn_id="t3"
    )
    reminder = next((f for f in out if f.key == "reminder"), None)
    assert reminder is not None
    assert reminder.value == "my flight is at 6am"


def test_extract_my_x_is() -> None:
    """Multi-word field — "my favorite color is blue" captures the full field."""
    out = extract_facts("my favorite color is blue", turn_id="t4")
    color = next((f for f in out if f.key == "favorite color"), None)
    assert color is not None
    assert color.value == "blue"


def test_extract_my_x_is_single_word() -> None:
    """Single-word field still works after the multi-word relaxation."""
    out = extract_facts("my doctor is Dr Patel", turn_id="t4b")
    fact = next((f for f in out if f.key == "doctor"), None)
    assert fact is not None
    assert "Patel" in fact.value


def test_dedup_latest_value_per_key(_redirect_facts_path: Path) -> None:
    older = KeyValueFact(
        key="preference",
        value="tea",
        extracted_from_turn_id="t_old",
        ts="2026-05-01T00:00:00+00:00",
    )
    newer = KeyValueFact(
        key="preference",
        value="coffee",
        extracted_from_turn_id="t_new",
        ts="2026-05-13T00:00:00+00:00",
    )
    append_fact(older)
    append_fact(newer)

    facts = read_facts()
    prefs = [f for f in facts if f.key == "preference"]
    assert len(prefs) == 1
    assert prefs[0].value == "coffee"


def test_render_for_prompt_empty() -> None:
    assert render_facts_for_prompt([]) == ""


def test_render_for_prompt_formats_lines() -> None:
    block = render_facts_for_prompt(
        [
            KeyValueFact(
                key="name",
                value="J",
                extracted_from_turn_id="t1",
                ts="2026-05-13T00:00:00+00:00",
            ),
            KeyValueFact(
                key="preference",
                value="dark roast coffee",
                extracted_from_turn_id="t2",
                ts="2026-05-13T00:00:01+00:00",
            ),
        ]
    )
    assert "Known facts about the operator" in block
    assert "- name: J" in block
    assert "- preference: dark roast coffee" in block


def test_persist_round_trip(_redirect_facts_path: Path) -> None:
    fact = KeyValueFact(
        key="name",
        value="J",
        extracted_from_turn_id="t1",
        ts="2026-05-13T00:00:00+00:00",
    )
    append_fact(fact)
    out = read_facts()
    assert len(out) == 1
    assert out[0] == fact


def test_extract_empty_text_returns_empty() -> None:
    assert extract_facts("", turn_id="t0") == []
    assert extract_facts("   ", turn_id="t0") == []


# ── Extended pattern coverage (post-J2 polish) ────────────────────────────────


def test_extract_location() -> None:
    out = extract_facts("i'm in Brooklyn this week", turn_id="t-loc")
    loc = next((f for f in out if f.key == "location"), None)
    assert loc is not None
    assert "Brooklyn" in loc.value


def test_extract_location_live_in() -> None:
    out = extract_facts("i live in Philadelphia", turn_id="t-loc2")
    loc = next((f for f in out if f.key == "location"), None)
    assert loc is not None
    assert "Philadelphia" in loc.value


def test_extract_hours() -> None:
    out = extract_facts("i work from 9 to 6", turn_id="t-h")
    hrs = next((f for f in out if f.key == "hours"), None)
    assert hrs is not None
    assert "9" in hrs.value


def test_extract_routine_named_key() -> None:
    out = extract_facts("i meditate every morning", turn_id="t-r")
    routine = next((f for f in out if f.key.startswith("routine:")), None)
    assert routine is not None
    assert routine.key == "routine:meditate"
    assert "morning" in routine.value


def test_extract_avoid_dont() -> None:
    out = extract_facts("don't call me after 10pm.", turn_id="t-a")
    avoid = next((f for f in out if f.key == "avoid"), None)
    assert avoid is not None
    assert "call me after 10pm" in avoid.value


def test_extract_avoid_never() -> None:
    out = extract_facts("never schedule meetings before 10am", turn_id="t-a2")
    avoid = next((f for f in out if f.key == "avoid"), None)
    assert avoid is not None
    assert "schedule meetings" in avoid.value


def test_extract_multiple_facts_one_sentence() -> None:
    """One sentence with two declarative shapes should yield both facts."""
    out = extract_facts(
        "call me J and remember that my flight is at six am",
        turn_id="t-multi",
    )
    keys = {f.key for f in out}
    assert "name" in keys
    assert "reminder" in keys
