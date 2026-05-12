"""Tests for the Mission Control bridge."""
from __future__ import annotations

import json
from pathlib import Path

from jarvis.contract import AgentLogEntry, Confirmation, InboxEvent, Task
from jarvis.apps.sentinel.mission_control_bridge import (
    _eisenhower,
    _inbox_to_message,
    _log_to_event,
    _stable_id,
    _task_to_mission,
    sync_tick,
)


def _write_jsonl(path: Path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(i.model_dump_json() for i in items), encoding="utf-8")


def test_stable_id_is_deterministic():
    a = _stable_id("x", "y", "z")
    b = _stable_id("x", "y", "z")
    assert a == b
    assert len(a) == 16
    assert a != _stable_id("x", "y", "zz")


def test_inbox_to_message_maps_severity_to_type():
    e = InboxEvent(agent="atlas", severity="alert", summary="drawdown", ref={"pnl": -0.05})
    msg = _inbox_to_message(e)
    assert msg["from"] == "atlas"
    assert msg["to"] == "me"
    assert msg["type"] == "approval"
    assert msg["status"] == "unread"
    assert "drawdown" in msg["subject"]
    assert json.loads(msg["body"]) == {"pnl": -0.05}


def test_inbox_to_message_info_severity_maps_to_update():
    e = InboxEvent(agent="tempo", severity="info", summary="0 unread")
    assert _inbox_to_message(e)["type"] == "update"


def test_log_to_event_status_mapping():
    a = AgentLogEntry(request_id="r1", agent="tempo", action="today", status="ok", duration_ms=42)
    assert _log_to_event(a)["type"] == "task_completed"
    b = AgentLogEntry(request_id="r2", agent="atlas", action="trader", status="error",
                      error="boom")
    assert _log_to_event(b)["type"] == "task_failed"
    c = AgentLogEntry(request_id="r3", agent="atlas", action="trader", status="proposed")
    assert _log_to_event(c)["type"] == "task_started"


def test_eisenhower_explicit_tier_overrides_due():
    t = Task(title="x", tags=["tier:1"])
    assert _eisenhower(t) == ("important", "urgent")
    t2 = Task(title="x", tags=["tier:5"])
    assert _eisenhower(t2) == ("not_important", "not_urgent")


def test_eisenhower_due_today_is_urgent():
    from datetime import UTC, datetime, timedelta
    soon = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    t = Task(title="x", due=soon)
    assert _eisenhower(t) == ("important", "urgent")


def test_eisenhower_due_far_is_not_urgent():
    from datetime import UTC, datetime, timedelta
    later = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    t = Task(title="x", due=later)
    assert _eisenhower(t) == ("important", "not_urgent")


def test_task_to_mission_carries_due_and_tags():
    t = Task(title="Submit report", due="2026-05-01T10:00:00+00:00", tags=["work", "tier:3"])
    m = _task_to_mission(t)
    assert m["title"] == "Submit report"
    assert m["dueDate"] == "2026-05-01T10:00:00+00:00"
    assert "work" in m["tags"]
    assert m["importance"] == "important"
    assert m["urgency"] == "not_urgent"
    assert m["assignedTo"] == "me"
    assert m["kanban"] == "todo"


def test_sync_tick_writes_all_files(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    web_data = tmp_path / "web" / "data"
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state_dir))
    # reset cached settings
    from jarvis import config
    config.get_settings.cache_clear()

    _write_jsonl(state_dir / "inbox.jsonl",
                 [InboxEvent(agent="atlas", severity="info", summary="ping")])
    _write_jsonl(state_dir / "agent_log.jsonl",
                 [AgentLogEntry(request_id="r1", agent="tempo", action="today", status="ok")])
    _write_jsonl(state_dir / "confirmations.jsonl",
                 [Confirmation(agent="atlas", intent="trader_execute", summary="confirm trade")])

    counts = sync_tick(web_data_dir=web_data)
    assert counts == {"agents": 6, "inbox": 1, "activity": 1, "tasks": 0, "decisions": 1}

    agents = json.loads((web_data / "agents.json").read_text(encoding="utf-8"))
    assert {a["id"] for a in agents["agents"]} == {"tempo", "scholar", "lens", "forge", "atlas", "me"}

    inbox = json.loads((web_data / "inbox.json").read_text(encoding="utf-8"))
    assert inbox["messages"][0]["from"] == "atlas"

    activity = json.loads((web_data / "activity-log.json").read_text(encoding="utf-8"))
    assert activity["events"][0]["actor"] == "tempo"

    decisions = json.loads((web_data / "decisions.json").read_text(encoding="utf-8"))
    assert decisions["decisions"][0]["requestedBy"] == "atlas"


def test_sync_tick_handles_missing_state_files(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state_dir))
    from jarvis import config
    config.get_settings.cache_clear()

    counts = sync_tick(web_data_dir=tmp_path / "web" / "data")
    assert counts["inbox"] == 0
    assert counts["activity"] == 0
    assert counts["decisions"] == 0


def test_only_pending_confirmations_become_decisions(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state_dir))
    from jarvis import config
    config.get_settings.cache_clear()

    _write_jsonl(state_dir / "confirmations.jsonl", [
        Confirmation(agent="atlas", intent="trader_execute", status="pending"),
        Confirmation(agent="atlas", intent="trader_execute", status="approved"),
        Confirmation(agent="atlas", intent="trader_execute", status="rejected"),
    ])

    counts = sync_tick(web_data_dir=tmp_path / "web" / "data")
    assert counts["decisions"] == 1
