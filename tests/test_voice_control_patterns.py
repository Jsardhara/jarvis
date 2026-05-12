"""Tests for the voice control patterns added for proactive mute / memory reset.

Quiet-for-duration, bare-quiet, speak-up, start-fresh patterns short-circuit
the LLM and mutate proactive/conversation_memory module state.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis.apps.voice import conversation_memory, proactive
from jarvis.apps.voice.cheap_patterns import match


@pytest.fixture(autouse=True)
def _reset():
    proactive.clear_mute()
    conversation_memory.clear()
    yield
    proactive.clear_mute()
    conversation_memory.clear()


@pytest.mark.parametrize(
    "utterance,expected_seconds",
    [
        ("quiet for 5 minutes", 300),
        ("quiet for ten minutes", 600),
        ("stand down for 30 seconds", 30),
        ("silence for 2 hours", 7200),
        ("mute for fifteen mins", 900),
        ("quiet me for one hour", 3600),
    ],
)
def test_quiet_duration_parses_and_mutes(utterance: str, expected_seconds: int) -> None:
    reply = match(utterance)
    assert reply is not None
    assert "quiet" in reply.lower() or "minute" in reply.lower() or "hour" in reply.lower()
    assert proactive.is_muted()


def test_bare_quiet_defaults_to_ten_minutes() -> None:
    reply = match("stand down")
    assert reply is not None
    assert proactive.is_muted()


def test_speak_up_clears_mute() -> None:
    proactive.mute_for(timedelta(minutes=30))
    assert proactive.is_muted()
    reply = match("speak up")
    assert reply is not None
    assert not proactive.is_muted()


def test_wake_up_also_clears_mute() -> None:
    proactive.mute_for(timedelta(minutes=30))
    reply = match("wake up jarvis")
    assert reply is not None
    assert not proactive.is_muted()


def test_start_fresh_clears_conversation_memory() -> None:
    conversation_memory.remember("a", "b")
    conversation_memory.remember("c", "d")
    assert len(conversation_memory.recent()) == 2
    reply = match("start fresh")
    assert reply is not None
    assert conversation_memory.recent() == ()


def test_forget_that_clears_conversation_memory() -> None:
    conversation_memory.remember("a", "b")
    reply = match("forget that")
    assert reply is not None
    assert conversation_memory.recent() == ()


def test_existing_patterns_still_work() -> None:
    # Sanity — pre-existing rules aren't shadowed.
    assert match("hello") is not None
    assert match("thanks") == ""  # silent ack
    assert match("repeat") == "__REPEAT_LAST__"
    assert "It's" in (match("what time is it") or "")
