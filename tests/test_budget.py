"""Tests for jarvis.agents.atlas.budget."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.agents.atlas import budget


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirect budget.jsonl to a temp dir."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    from jarvis.config import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_today_spent_zero_when_no_file(isolated_state):
    assert budget.today_spent() == 0.0


def test_record_and_read_today(isolated_state):
    budget.record_spend(0.50, tag="t1")
    budget.record_spend(1.25, tag="t2")
    assert budget.today_spent() == pytest.approx(1.75)


def test_record_ignores_zero_or_negative(isolated_state):
    budget.record_spend(0.0)
    budget.record_spend(-1.0)
    assert budget.today_spent() == 0.0


def test_can_afford_under_cap(isolated_state):
    budget.record_spend(2.0, tag="x")
    assert budget.can_afford(2.5) is True
    assert budget.can_afford(3.0) is True
    assert budget.can_afford(3.01) is False


def test_can_afford_at_cap_boundary(isolated_state):
    budget.record_spend(5.0, tag="x")
    assert budget.can_afford(0.0) is True
    assert budget.can_afford(0.01) is False


def test_today_spent_ignores_other_days(isolated_state, tmp_path):
    """Old-day records are excluded from today_spent."""
    path = tmp_path / "budget.jsonl"
    yesterday = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with path.open("w") as f:
        f.write(json.dumps({"date": yesterday, "ts": "x", "usd": 4.99}) + "\n")
        f.write(json.dumps({"date": today, "ts": "x", "usd": 1.0}) + "\n")
    assert budget.today_spent() == pytest.approx(1.0)


def test_snapshot(isolated_state):
    budget.record_spend(1.50, tag="x")
    snap = budget.snapshot()
    assert snap.spent_usd == pytest.approx(1.50)
    assert snap.cap_usd == budget.DAILY_CAP_USD
    assert snap.remaining_usd == pytest.approx(budget.DAILY_CAP_USD - 1.50)


def test_corrupt_lines_are_skipped(isolated_state, tmp_path):
    path = tmp_path / "budget.jsonl"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with path.open("w") as f:
        f.write("not json\n")
        f.write(json.dumps({"date": today, "usd": 2.0}) + "\n")
        f.write(json.dumps({"date": today, "usd": "bad"}) + "\n")
    assert budget.today_spent() == pytest.approx(2.0)
