"""Tests: merged cost rollup flattens Atlas nested by_agent + unions with Jarvis costs."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.config import Settings
from jarvis.web.api import _merge_cost_rollups

# ---------------------------------------------------------------------------
# Unit tests for _merge_cost_rollups
# ---------------------------------------------------------------------------


def test_merge_flattens_atlas_nested_by_agent():
    """Atlas by_agent with nested {cost_usd, calls} objects are flattened to floats."""
    jarvis = {
        "date": "2026-04-30",
        "total_usd": 1.0,
        "by_agent": {"tempo": 0.5, "scholar": 0.5},
        "by_model": {"claude-sonnet-4-6": 1.0},
        "call_count": 2,
    }
    atlas = {
        "date": "2026-04-30",
        "total_usd": 2.5,
        "by_agent": {
            "atlas.oracle": {"calls": 3, "input_tokens": 1000, "output_tokens": 500, "cost_usd": 1.5},
            "atlas.trader": {"calls": 1, "input_tokens": 200, "output_tokens": 100, "cost_usd": 1.0},
        },
        "by_model": {"claude-opus-4-7": 2.5},
        "call_count": 4,
    }
    merged = _merge_cost_rollups(jarvis, atlas)

    assert isinstance(merged["by_agent"]["atlas.oracle"], float)
    assert isinstance(merged["by_agent"]["atlas.trader"], float)
    assert merged["by_agent"]["atlas.oracle"] == pytest.approx(1.5)
    assert merged["by_agent"]["atlas.trader"] == pytest.approx(1.0)


def test_merge_unions_agents():
    """Jarvis and Atlas agents are unioned — no key dropped."""
    jarvis = {
        "date": "2026-04-30",
        "total_usd": 1.0,
        "by_agent": {"tempo": 0.4, "scholar": 0.6},
        "by_model": {},
        "call_count": 2,
    }
    atlas = {
        "date": "2026-04-30",
        "total_usd": 0.8,
        "by_agent": {"atlas.oracle": 0.5, "atlas.sage": 0.3},
        "by_model": {},
        "call_count": 2,
    }
    merged = _merge_cost_rollups(jarvis, atlas)

    assert "tempo" in merged["by_agent"]
    assert "scholar" in merged["by_agent"]
    assert "atlas.oracle" in merged["by_agent"]
    assert "atlas.sage" in merged["by_agent"]


def test_merge_sums_overlapping_agents():
    """If an agent appears in both Jarvis and Atlas, costs are summed."""
    jarvis = {
        "date": "2026-04-30",
        "total_usd": 0.5,
        "by_agent": {"atlas": 0.5},
        "by_model": {},
        "call_count": 1,
    }
    atlas = {
        "date": "2026-04-30",
        "total_usd": 0.3,
        "by_agent": {"atlas": 0.3},
        "by_model": {},
        "call_count": 1,
    }
    merged = _merge_cost_rollups(jarvis, atlas)
    assert merged["by_agent"]["atlas"] == pytest.approx(0.8)


def test_merge_totals_sum():
    """total_usd in merged equals sum of both inputs."""
    jarvis = {
        "date": "2026-04-30",
        "total_usd": 1.23,
        "by_agent": {},
        "by_model": {},
        "call_count": 3,
    }
    atlas = {
        "date": "2026-04-30",
        "total_usd": 4.56,
        "by_agent": {},
        "by_model": {},
        "call_count": 7,
    }
    merged = _merge_cost_rollups(jarvis, atlas)
    assert merged["total_usd"] == pytest.approx(5.79)
    assert merged["call_count"] == 10


def test_merge_call_count_sums():
    """call_count in merged equals sum of both inputs."""
    jarvis = {
        "date": "2026-04-30",
        "total_usd": 0.0,
        "by_agent": {},
        "by_model": {},
        "call_count": 5,
    }
    atlas = {
        "date": "2026-04-30",
        "total_usd": 0.0,
        "by_agent": {},
        "by_model": {},
        "call_count": 12,
    }
    merged = _merge_cost_rollups(jarvis, atlas)
    assert merged["call_count"] == 17


# ---------------------------------------------------------------------------
# Integration: /api/cost/rollup endpoint returns merged shape
# ---------------------------------------------------------------------------


def test_cost_rollup_endpoint_returns_flat_by_agent(tmp_path: Path, monkeypatch):
    """GET /api/cost/rollup returns RawRollup-compatible flat by_agent."""
    import json

    from jarvis.config import get_settings

    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://localhost:8000")
    monkeypatch.setattr("jarvis.cost.get_settings", lambda: fake)
    get_settings.cache_clear()

    # Write one Jarvis cost entry
    ts_today = datetime(2026, 4, 30, 10, 0, 0, tzinfo=UTC).isoformat()
    log_path = tmp_path / "cost_log.jsonl"
    entry = {
        "ts": ts_today,
        "agent": "tempo",
        "model": "claude-sonnet-4-6",
        "in_tokens": 1000,
        "out_tokens": 500,
        "cost_usd": 0.01,
    }
    log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    from jarvis.web.api import make_app

    app = make_app()
    client = TestClient(app)
    r = client.get("/api/cost/rollup?date_str=2026-04-30")
    assert r.status_code == 200
    body = r.json()
    # by_agent values must be floats (RawRollup shape)
    for _agent, val in body.get("by_agent", {}).items():
        assert isinstance(val, (int, float)), f"by_agent[{_agent}] not a float: {val!r}"
