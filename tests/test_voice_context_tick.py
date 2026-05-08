"""Tests for ``jarvis/daemon/voice_context_tick.py``."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


from jarvis.daemon import voice_context_tick as tick_mod


def _ev(agent: str, ref: dict) -> SimpleNamespace:
    return SimpleNamespace(agent=agent, ref=ref)


def test_voice_context_tick_writes_fact_sheet(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    fixture_events = [
        _ev("atlas", {"pnl_pct": 0.012, "open_positions": 3,
                       "agent_states": {"oracle": "running", "trader": "running"}}),
        _ev("tempo", {"counts": {"action_required": 4, "info_only": 6},
                       "events": [{"subject": "Standup", "start": "10:00"}]}),
    ]
    monkeypatch.setattr(
        "jarvis.daemon.voice_context_tick.read_inbox",
        lambda limit=200: fixture_events,
        raising=False,
    )
    # Patch via module path used inside tick (deferred import).
    import jarvis.state as _state

    monkeypatch.setattr(_state, "read_inbox", lambda limit=200: fixture_events)

    payload = tick_mod.voice_context_tick()
    assert payload["pnl_today_pct"] == 0.012
    assert payload["open_positions"] == 3
    assert payload["unread_mail"] == 10  # 4 + 6
    assert "Standup" in payload["next_event"]
    assert payload["atlas_health"] == "healthy"

    written = tmp_path / "voice_context.json"
    assert written.exists()
    data = json.loads(written.read_text())
    assert data["pnl_today_pct"] == 0.012
    assert "updated_at" in data


def test_voice_context_tick_handles_empty_inbox(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    import jarvis.state as _state

    monkeypatch.setattr(_state, "read_inbox", lambda limit=200: [])
    payload = tick_mod.voice_context_tick()
    assert payload["pnl_today_pct"] == 0.0
    assert payload["open_positions"] == 0
    assert payload["unread_mail"] == 0
    assert payload["next_event"] == ""
    assert payload["atlas_health"] == "unknown"


def test_voice_context_tick_marks_degraded_when_agent_down(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    import jarvis.state as _state

    monkeypatch.setattr(
        _state,
        "read_inbox",
        lambda limit=200: [
            _ev("atlas", {"agent_states": {"oracle": "running", "trader": "paused"}}),
        ],
    )
    payload = tick_mod.voice_context_tick()
    assert payload["atlas_health"] == "degraded"
