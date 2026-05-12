"""Tests for jarvis.llm.cost — log_cost + daily_rollup."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from jarvis.config import Settings


def _fake_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        state_dir=tmp_path,
        atlas_api="http://localhost:8000",
    )


def test_log_cost_appends_entry(tmp_path: Path, monkeypatch) -> None:
    """log_cost writes one JSON line to state/cost_log.jsonl."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("tempo", "claude-sonnet-4-6", in_tokens=1000, out_tokens=500)

    log_path = tmp_path / "cost_log.jsonl"
    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["agent"] == "tempo"
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["in_tokens"] == 1000
    assert entry["out_tokens"] == 500
    assert "ts" in entry
    assert "cost_usd" in entry


def test_log_cost_appends_multiple(tmp_path: Path, monkeypatch) -> None:
    """Successive calls append lines, not overwrite."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("tempo", "claude-sonnet-4-6", 100, 50)
    log_cost("atlas", "claude-opus-4-7", 200, 100)

    lines = [
        line for line in (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2


def test_log_cost_sonnet_rate(tmp_path: Path, monkeypatch) -> None:
    """Sonnet cost: $3/Mtok in, $15/Mtok out."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    # 1M in + 1M out at $3/$15 = $18
    log_cost("tempo", "claude-sonnet-4-6", in_tokens=1_000_000, out_tokens=1_000_000)
    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert abs(entry["cost_usd"] - 18.0) < 0.01


def test_log_cost_opus_rate(tmp_path: Path, monkeypatch) -> None:
    """Opus cost: $15/Mtok in, $75/Mtok out."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    # 1M in + 1M out at $15/$75 = $90
    log_cost("atlas", "claude-opus-4-7", in_tokens=1_000_000, out_tokens=1_000_000)
    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert abs(entry["cost_usd"] - 90.0) < 0.01


def test_log_cost_haiku_rate(tmp_path: Path, monkeypatch) -> None:
    """Haiku cost: $1/Mtok in, $5/Mtok out."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    # 1M in + 1M out at $1/$5 = $6
    log_cost("sentinel", "claude-haiku-4-5", in_tokens=1_000_000, out_tokens=1_000_000)
    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert abs(entry["cost_usd"] - 6.0) < 0.01


def test_daily_rollup_empty(tmp_path: Path, monkeypatch) -> None:
    """daily_rollup returns zeroed dict when no entries exist."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup

    result = daily_rollup(date(2026, 4, 28))
    assert result["date"] == "2026-04-28"
    assert result["total_usd"] == 0.0
    assert result["call_count"] == 0
    assert result["by_agent"] == {}
    assert result["by_model"] == {}


def test_daily_rollup_sums_by_agent_and_model(tmp_path: Path, monkeypatch) -> None:
    """daily_rollup aggregates costs correctly."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup

    today = date(2026, 4, 28)
    ts_today = datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC).isoformat()
    ts_yesterday = datetime(2026, 4, 27, 10, 0, 0, tzinfo=UTC).isoformat()

    # Two today, one yesterday
    log_path = tmp_path / "cost_log.jsonl"
    from jarvis.llm.cost import MODEL_RATES
    sonnet_in, sonnet_out = MODEL_RATES.get("claude-sonnet-4-6", (3.0, 15.0))
    opus_in, opus_out = MODEL_RATES.get("claude-opus-4-7", (15.0, 75.0))

    def _cost(model_in: float, model_out: float, in_tok: int, out_tok: int) -> float:
        return (in_tok / 1_000_000) * model_in + (out_tok / 1_000_000) * model_out

    entry1 = {
        "ts": ts_today, "agent": "tempo", "model": "claude-sonnet-4-6",
        "in_tokens": 1000, "out_tokens": 500,
        "cost_usd": _cost(sonnet_in, sonnet_out, 1000, 500),
    }
    entry2 = {
        "ts": ts_today, "agent": "atlas", "model": "claude-opus-4-7",
        "in_tokens": 2000, "out_tokens": 800,
        "cost_usd": _cost(opus_in, opus_out, 2000, 800),
    }
    entry_old = {
        "ts": ts_yesterday, "agent": "tempo", "model": "claude-sonnet-4-6",
        "in_tokens": 999, "out_tokens": 999,
        "cost_usd": 99.0,
    }
    with log_path.open("w", encoding="utf-8") as f:
        for e in (entry1, entry2, entry_old):
            f.write(json.dumps(e) + "\n")

    result = daily_rollup(today)
    assert result["call_count"] == 2  # only today's entries
    assert "tempo" in result["by_agent"]
    assert "atlas" in result["by_agent"]
    assert "claude-sonnet-4-6" in result["by_model"]
    assert "claude-opus-4-7" in result["by_model"]
    expected_total = entry1["cost_usd"] + entry2["cost_usd"]
    assert abs(result["total_usd"] - expected_total) < 0.001


def test_daily_rollup_defaults_to_today(tmp_path: Path, monkeypatch) -> None:
    """daily_rollup(None) uses today's date."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup

    result = daily_rollup()
    today_str = date.today().isoformat()
    assert result["date"] == today_str
