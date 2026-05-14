"""Tests for jarvis.core.triggers.scan_meeting_imminent."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from jarvis.contract import AgentResponse

from jarvis.core import triggers as triggers_mod


def _seed_voice_context(state_dir: Path, start_dt: datetime, event_id: str = "evt_1") -> None:
    """Drop a voice_context.json with a next_event so scan_meeting_imminent picks it up."""
    ctx = {
        "updated_at": datetime.now(UTC).isoformat(),
        "next_event": {
            "event_id": event_id,
            "subject": "Sync with Sarah",
            "start": start_dt.isoformat(),
        },
    }
    (state_dir / "voice_context.json").write_text(
        json.dumps(ctx), encoding="utf-8"
    )


def test_emits_event_at_5min_window(isolated_state: Path, monkeypatch) -> None:
    """An event 4 minutes out fires a warn InboxEvent in the 5min bucket."""
    monkeypatch.setattr(
        triggers_mod, "_fired_path", lambda: isolated_state / "triggers_fired.jsonl"
    )
    start = datetime.now(UTC) + timedelta(minutes=4)
    _seed_voice_context(isolated_state, start, event_id="evt_5min")

    events = triggers_mod.scan_meeting_imminent({})

    assert len(events) == 1
    ev = events[0]
    assert ev.severity == "warn"
    assert ev.ref["bucket"] == "5min"
    assert ev.ref["event_id"] == "evt_5min"


def test_dedup_same_bucket_same_event(isolated_state: Path, monkeypatch) -> None:
    """A second scan in the same minute returns no new events for the same bucket."""
    monkeypatch.setattr(
        triggers_mod, "_fired_path", lambda: isolated_state / "triggers_fired.jsonl"
    )
    start = datetime.now(UTC) + timedelta(minutes=4)
    _seed_voice_context(isolated_state, start, event_id="evt_dup")

    first = triggers_mod.scan_meeting_imminent({})
    second = triggers_mod.scan_meeting_imminent({})

    assert len(first) == 1
    assert second == []


def test_no_event_when_more_than_15min_away(isolated_state: Path, monkeypatch) -> None:
    """An event 20 minutes out is too far away — no warning yet."""
    monkeypatch.setattr(
        triggers_mod, "_fired_path", lambda: isolated_state / "triggers_fired.jsonl"
    )
    start = datetime.now(UTC) + timedelta(minutes=20)
    _seed_voice_context(isolated_state, start, event_id="evt_far")

    events = triggers_mod.scan_meeting_imminent({})

    assert events == []


def test_falls_back_to_tempo_today_when_no_voice_context(
    isolated_state: Path, monkeypatch
) -> None:
    """When voice_context is absent, scan_meeting_imminent uses tempo.today()."""
    monkeypatch.setattr(
        triggers_mod, "_fired_path", lambda: isolated_state / "triggers_fired.jsonl"
    )

    start = datetime.now(UTC) + timedelta(minutes=8)
    tempo = MagicMock()
    tempo.call.return_value = AgentResponse(
        agent="tempo",
        intent="list_today",
        action="listed",
        result={
            "events": [
                {
                    "event_id": "fallback_evt",
                    "subject": "Fallback meeting",
                    "start": start.isoformat(),
                }
            ],
            "count": 1,
        },
    )
    reg = {"tempo": tempo}

    events = triggers_mod.scan_meeting_imminent(reg)

    assert len(events) == 1
    assert events[0].ref["bucket"] == "10min"
