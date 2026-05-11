"""Tests for ``jarvis/voice/proactive.py`` — daemon-driven voice alerts.

The proactive channel tails ``state/inbox.jsonl``, filters for
``severity=='alert'``, respects the mute window, defers when voice is
busy speaking/listening, and never crashes the voice loop on errors.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from jarvis.voice import proactive


class _StubTTS:
    """Minimal TTS double — records what gets spoken."""
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return b""


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    # Redirect inbox + voice_actions to tmp
    inbox = tmp_path / "inbox.jsonl"
    actions = tmp_path / "voice_actions.jsonl"
    monkeypatch.setattr(proactive, "_inbox_path", lambda: inbox)
    monkeypatch.setattr(proactive, "_actions_path", lambda: actions)
    # Reset module-level state between tests
    proactive.clear_mute()
    proactive._OFFSET = 0
    yield


def _write_event(path: Path, *, severity: str, summary: str, agent: str = "atlas") -> None:
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "agent": agent,
        "severity": severity,
        "summary": summary,
        "ref": {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def test_speaks_on_alert_event(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line",
                        lambda summary: f"Heads up: {summary}.")
    tts = _StubTTS()
    _write_event(proactive._inbox_path(), severity="alert", summary="Drawdown -8%")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == ["Heads up: Drawdown -8%."]
    # Audit log written
    audit = proactive._actions_path().read_text(encoding="utf-8").strip().splitlines()
    assert len(audit) == 1
    rec = json.loads(audit[0])
    assert rec["severity"] == "alert"
    assert rec["summary"] == "Drawdown -8%"


def test_skips_info_severity(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"alert: {s}")
    tts = _StubTTS()
    _write_event(proactive._inbox_path(), severity="info", summary="heartbeat")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == []


def test_skips_warn_severity(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"alert: {s}")
    tts = _StubTTS()
    _write_event(proactive._inbox_path(), severity="warn", summary="rate limit close")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == []


def test_mute_window_suppresses_alert(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"alert: {s}")
    tts = _StubTTS()
    proactive.mute_for(timedelta(minutes=10))
    _write_event(proactive._inbox_path(), severity="alert", summary="big move")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == []


def test_clear_mute_re_enables(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"alert: {s}")
    tts = _StubTTS()
    proactive.mute_for(timedelta(minutes=10))
    proactive.clear_mute()
    _write_event(proactive._inbox_path(), severity="alert", summary="back")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == ["alert: back"]


def test_defers_while_voice_busy(monkeypatch):
    """When voice_state mode is 'stt' or 'tts', proactive must not interrupt."""
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"alert: {s}")
    monkeypatch.setattr(proactive, "_voice_busy", lambda: True)
    tts = _StubTTS()
    _write_event(proactive._inbox_path(), severity="alert", summary="big move")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == []
    # Event NOT consumed — offset shouldn't advance past it.
    monkeypatch.setattr(proactive, "_voice_busy", lambda: False)
    asyncio.run(proactive.tick(tts))
    assert tts.spoken == ["alert: big move"]


def test_offset_advances_after_processing(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"a: {s}")
    tts = _StubTTS()
    _write_event(proactive._inbox_path(), severity="alert", summary="one")
    asyncio.run(proactive.tick(tts))
    _write_event(proactive._inbox_path(), severity="alert", summary="two")
    asyncio.run(proactive.tick(tts))

    assert tts.spoken == ["a: one", "a: two"]


def test_tick_survives_malformed_line(monkeypatch):
    monkeypatch.setattr(proactive, "_build_spoken_line", lambda s: f"a: {s}")
    tts = _StubTTS()
    p = proactive._inbox_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json\n", encoding="utf-8")
    _write_event(p, severity="alert", summary="after garbage")

    asyncio.run(proactive.tick(tts))

    assert tts.spoken == ["a: after garbage"]


def test_mute_for_accepts_seconds():
    proactive.mute_for(timedelta(seconds=30))
    assert proactive.is_muted()
