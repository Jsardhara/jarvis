"""Tests for ``jarvis/voice/speech.py`` — clean_for_speech + rewrite_for_speech.

clean_for_speech is pure-string: idempotent, no LLM. It MUST strip markdown,
code fences, JSON-looking blobs, and bullet markers so TTS never reads
them aloud. rewrite_for_speech is the Haiku fallback when cleaning alone
isn't enough.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from jarvis.voice import speech


@pytest.mark.parametrize(
    "raw,must_not_contain",
    [
        ("**bold** text", "*"),
        ("_italic_ here", "_"),
        ("# Heading", "#"),
        ("`code` inline", "`"),
        ("- item one\n- item two", "-"),
        ("* bullet\n* bullet", "*"),
        ("```python\nprint('x')\n```", "```"),
    ],
)
def test_clean_strips_markdown(raw: str, must_not_contain: str) -> None:
    out = speech.clean_for_speech(raw)
    assert must_not_contain not in out, f"clean_for_speech left {must_not_contain!r} in: {out!r}"


def test_clean_strips_json_blob() -> None:
    raw = 'Result: {"agent": "atlas", "pnl": 1.2, "actions": 1}'
    out = speech.clean_for_speech(raw)
    assert "{" not in out
    assert "}" not in out
    assert '"agent"' not in out


def test_clean_is_idempotent() -> None:
    raw = "**bold** and _italic_ with `code` and a {json: blob}"
    once = speech.clean_for_speech(raw)
    twice = speech.clean_for_speech(once)
    assert once == twice


def test_clean_preserves_apostrophes_and_quotes() -> None:
    raw = "I'm here — don't worry, \"all good\""
    out = speech.clean_for_speech(raw)
    assert "'" in out  # apostrophe survived
    assert "don't" in out


def test_clean_collapses_newlines_to_space() -> None:
    raw = "first line\n\n\nsecond line"
    out = speech.clean_for_speech(raw)
    assert "\n\n" not in out


def test_clean_empty_string_returns_empty() -> None:
    assert speech.clean_for_speech("") == ""
    assert speech.clean_for_speech(None) == ""  # type: ignore[arg-type]


def test_rewrite_for_speech_calls_haiku() -> None:
    with patch.object(speech, "_submit", return_value="Two grand up today.") as mock:
        out = speech.rewrite_for_speech("P&L: +$2,000 today.")
    assert out == "Two grand up today."
    mock.assert_called_once()
    # PERSONA must be in system prompt
    kwargs = mock.call_args.kwargs
    assert "operator" in kwargs["system"].lower()


def test_rewrite_for_speech_falls_back_on_error() -> None:
    with patch.object(speech, "_submit", side_effect=RuntimeError("boom")):
        out = speech.rewrite_for_speech("anything")
    # On failure, return the original cleaned text — never crash voice loop.
    assert out == "anything"
