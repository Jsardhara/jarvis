"""Tests for ``jarvis/voice/conversation_memory.py`` — in-process ring buffer."""
from __future__ import annotations

import pytest

from jarvis.voice import conversation_memory as cm


@pytest.fixture(autouse=True)
def _reset():
    cm.clear()
    yield
    cm.clear()


def test_remember_then_recent_returns_tuple() -> None:
    cm.remember("hi", "hey")
    out = cm.recent()
    assert isinstance(out, tuple)
    assert len(out) == 1
    assert out[0].user == "hi"
    assert out[0].jarvis == "hey"


def test_ring_buffer_evicts_oldest_first() -> None:
    for i in range(10):
        cm.remember(f"u{i}", f"j{i}")
    out = cm.recent()
    assert len(out) == cm.MAX_TURNS
    # Oldest evicted, newest retained
    assert out[0].user == f"u{10 - cm.MAX_TURNS}"
    assert out[-1].user == "u9"


def test_recent_with_smaller_n() -> None:
    for i in range(4):
        cm.remember(f"u{i}", f"j{i}")
    out = cm.recent(n=2)
    assert len(out) == 2
    assert out[-1].user == "u3"


def test_render_for_prompt_formats_turns() -> None:
    cm.remember("what's my pnl", "two grand up")
    cm.remember("and yesterday", "down four hundred")
    rendered = cm.render_for_prompt()
    assert "what's my pnl" in rendered
    assert "two grand up" in rendered
    assert "down four hundred" in rendered
    # Operator + Jarvis labels present
    assert "operator" in rendered.lower() or "user" in rendered.lower()
    assert "jarvis" in rendered.lower()


def test_render_for_prompt_empty_returns_empty_string() -> None:
    assert cm.render_for_prompt() == ""


def test_clear_drops_all() -> None:
    cm.remember("a", "b")
    cm.remember("c", "d")
    cm.clear()
    assert cm.recent() == ()


def test_exchange_is_frozen() -> None:
    cm.remember("a", "b")
    ex = cm.recent()[0]
    with pytest.raises((AttributeError, Exception)):
        ex.user = "mutated"  # type: ignore[misc]


def test_remember_ignores_empty_pair() -> None:
    cm.remember("", "")
    assert cm.recent() == ()
    cm.remember("question", "")
    # Empty reply should not be stored either
    assert cm.recent() == ()
