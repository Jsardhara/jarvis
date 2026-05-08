"""Tests for ``jarvis/voice/context_cache.py``."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from pathlib import Path


from jarvis.voice import context_cache


def test_load_returns_empty_when_file_missing(tmp_path: Path):
    p = tmp_path / "voice_context.json"
    assert context_cache.load_voice_context(p) == {}


def test_load_returns_data_when_fresh(tmp_path: Path):
    p = tmp_path / "voice_context.json"
    p.write_text(
        json.dumps(
            {
                "pnl_today_pct": 0.012,
                "open_positions": 2,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ),
    )
    out = context_cache.load_voice_context(p)
    assert out["pnl_today_pct"] == 0.012
    assert out["open_positions"] == 2


def test_load_returns_empty_when_stale(tmp_path: Path):
    p = tmp_path / "voice_context.json"
    stale_ts = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
    p.write_text(json.dumps({"pnl_today_pct": 0.01, "updated_at": stale_ts}))
    assert context_cache.load_voice_context(p) == {}


def test_write_voice_context_is_atomic(tmp_path: Path):
    p = tmp_path / "voice_context.json"
    out = context_cache.write_voice_context({"pnl_today_pct": 0.005}, p)
    assert out == p
    data = json.loads(p.read_text())
    assert data["pnl_today_pct"] == 0.005
    assert "updated_at" in data
    # No leftover .tmp file.
    leftovers = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
    assert leftovers == []


def test_render_for_prompt_compact():
    rendered = context_cache.render_for_prompt(
        {
            "pnl_today_pct": 0.012,
            "open_positions": 3,
            "unread_mail": 5,
            "next_event": "Standup at 10:00",
            "atlas_health": "healthy",
        },
    )
    assert "pnl_today: +1.20%" in rendered
    assert "open_positions: 3" in rendered
    assert "next_event: Standup at 10:00" in rendered


def test_render_for_prompt_handles_empty_dict():
    rendered = context_cache.render_for_prompt({})
    assert "context unavailable" in rendered
