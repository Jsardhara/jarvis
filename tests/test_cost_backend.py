"""Tests for the P2 backend-tagging additions in jarvis.llm.cost.

P1 added the Backend abstraction; P2 threads the backend name into cost-log
entries so the dashboard can break costs out per engine once subsystems flip
to vLLM or Ollama. Pre-P2 entries (no ``backend`` field) bucket under
"claude" so historical aggregates stay accurate.
"""
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


def test_log_cost_defaults_backend_to_claude(tmp_path: Path, monkeypatch) -> None:
    """No backend kwarg -> entry tagged as 'claude'. Back-compat for old callers."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("tempo", "claude-sonnet-4-6", in_tokens=100, out_tokens=50)

    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["backend"] == "claude"


def test_log_cost_records_explicit_backend(tmp_path: Path, monkeypatch) -> None:
    """Explicit backend kwarg lands in the JSONL entry."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("sentinel", "qwen2.5:7b", 200, 80, backend="ollama")

    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["backend"] == "ollama"
    assert entry["agent"] == "sentinel"
    assert entry["model"] == "qwen2.5:7b"


def test_log_cost_vllm_is_free(tmp_path: Path, monkeypatch) -> None:
    """Local backends override pricing to $0."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("jarvis", "Qwen/Qwen2.5-72B-Instruct-AWQ", 1_000_000, 1_000_000, backend="vllm")

    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["backend"] == "vllm"
    assert entry["cost_usd"] == 0.0


def test_log_cost_ollama_is_free(tmp_path: Path, monkeypatch) -> None:
    """Same zero-rate for Ollama."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    log_cost("sentinel", "qwen2.5:7b", 5000, 2500, backend="ollama")

    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["cost_usd"] == 0.0


def test_log_cost_claude_still_priced(tmp_path: Path, monkeypatch) -> None:
    """Claude calls keep their real per-million-token rates."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import log_cost

    # Sonnet: $3 in + $15 out per Mtok -> 1M+1M = $18
    log_cost("tempo", "claude-sonnet-4-6", 1_000_000, 1_000_000, backend="claude")

    entry = json.loads(
        (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert abs(entry["cost_usd"] - 18.0) < 0.01


def test_daily_rollup_includes_by_backend(tmp_path: Path, monkeypatch) -> None:
    """daily_rollup surfaces a by_backend aggregate alongside by_agent/by_model."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup, log_cost

    log_cost("tempo", "claude-sonnet-4-6", 1_000_000, 1_000_000, backend="claude")
    log_cost("sentinel", "qwen2.5:7b", 1_000_000, 1_000_000, backend="ollama")
    log_cost("jarvis", "Qwen/Qwen2.5-72B-Instruct-AWQ", 1_000_000, 1_000_000, backend="vllm")

    result = daily_rollup(date.today())
    assert "by_backend" in result
    assert set(result["by_backend"].keys()) == {"claude", "ollama", "vllm"}
    # Claude entry has cost; locals are zero.
    assert result["by_backend"]["claude"] > 0
    assert result["by_backend"]["ollama"] == 0.0
    assert result["by_backend"]["vllm"] == 0.0


def test_daily_rollup_legacy_entry_buckets_as_claude(
    tmp_path: Path, monkeypatch
) -> None:
    """Pre-P2 rows have no ``backend`` field -> they roll up under 'claude'."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup

    today_ts = datetime.now(UTC).isoformat()
    log_path = tmp_path / "cost_log.jsonl"
    legacy_entry = {
        "ts": today_ts,
        "agent": "tempo",
        "model": "claude-sonnet-4-6",
        "in_tokens": 1000,
        "out_tokens": 500,
        "cost_usd": 0.005,
        # NOTE: no ``backend`` key -- this is the pre-P2 shape.
    }
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(legacy_entry) + "\n")

    result = daily_rollup(date.today())
    assert "claude" in result["by_backend"]
    assert result["by_backend"]["claude"] > 0


def test_empty_rollup_has_by_backend_field(tmp_path: Path, monkeypatch) -> None:
    """Empty-state shape includes by_backend so the dashboard can render uniformly."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.llm.cost.get_settings", lambda: fake)

    from jarvis.llm.cost import daily_rollup

    result = daily_rollup(date(2026, 1, 1))
    assert result["by_backend"] == {}
    assert result["call_count"] == 0
