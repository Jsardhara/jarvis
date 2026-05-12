"""Tests for ``jarvis/voice/persona.py``.

The PERSONA string is the single source of truth for Jarvis' voice +
chat personality. These tests pin the character markers so future
edits don't accidentally drift back to a sycophantic / screen-reader
voice.
"""
from __future__ import annotations

import pytest

from jarvis.apps.voice import persona


@pytest.mark.parametrize(
    "marker",
    [
        "chief of staff",          # back-compat with existing cheap_handler tests
        "1-2 sentences",           # cadence cap
        "composed",                # butler half
        "dry",                     # observational tone
        "contractions",            # spoken cadence cue
        "no markdown",             # strip-for-voice cue
        "speak, don't recite",     # primary directive
        "operator",                # name of person being talked to
    ],
)
def test_persona_contains_character_marker(marker: str) -> None:
    assert marker.lower() in persona.PERSONA.lower(), (
        f"PERSONA missing character marker: {marker!r}"
    )


@pytest.mark.parametrize(
    "banned",
    [
        "certainly",
        "happy to help",
        "of course",
        "as an ai",
    ],
)
def test_persona_does_not_invite_sycophancy(banned: str) -> None:
    # Persona explicitly forbids these phrases — they should appear only
    # inside a forbid-list construct, never as part of the persona itself.
    text = persona.PERSONA.lower()
    if banned in text:
        # allowed only when wrapped in a "no X" / "never X" instruction
        idx = text.index(banned)
        window = text[max(0, idx - 30):idx]
        assert any(
            tok in window for tok in ("no ", "never", "skip", "don't", "without")
        ), f"PERSONA includes {banned!r} without forbidding context"


def test_persona_is_nonempty_string() -> None:
    assert isinstance(persona.PERSONA, str)
    assert len(persona.PERSONA) > 200
