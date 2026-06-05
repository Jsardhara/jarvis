"""Tests for the nightly training_extract_tick sentinel routine."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.apps.sentinel.routines import training_extract_tick
from jarvis.training.extract import ExtractResult


def _stub_results(written_by_source: dict[str, int]) -> list[ExtractResult]:
    """Build a list of fake ExtractResult rows for monkeypatching."""
    return [
        ExtractResult(
            source=source,
            target=Path(f"/tmp/{source}.jsonl"),
            written=written,
            skipped=0,
            deduped=0,
        )
        for source, written in written_by_source.items()
    ]


def test_tick_calls_extract_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tick delegates to extract_all and returns its summary."""
    called = {"n": 0}

    def fake_extract_all() -> list[ExtractResult]:
        called["n"] += 1
        return _stub_results({"chat_turns": 3, "drafted_replies": 1})

    monkeypatch.setattr(
        "jarvis.training.extract.extract_all", fake_extract_all
    )

    notifier = MagicMock()
    result = training_extract_tick(notifier)

    assert called["n"] == 1
    assert result["total_written"] == 4
    assert result["by_source"] == {"chat_turns": 3, "drafted_replies": 1}


def test_tick_pushes_notifier_on_new_examples(monkeypatch: pytest.MonkeyPatch) -> None:
    """When fresh examples land, the operator gets a low-priority notification."""
    monkeypatch.setattr(
        "jarvis.training.extract.extract_all",
        lambda: _stub_results({"chat_turns": 5, "drafted_replies": 0}),
    )

    notifier = MagicMock()
    training_extract_tick(notifier)

    assert notifier.push.call_count == 1
    title, body = notifier.push.call_args.args[:2]
    assert "Training data" in title
    assert "5" in body  # total_written count
    assert "chat_turns: 5" in body  # per-source breakdown
    assert notifier.push.call_args.kwargs.get("priority") == 0


def test_tick_quiet_on_empty_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero new examples -> no notification (don't spam the operator)."""
    monkeypatch.setattr(
        "jarvis.training.extract.extract_all",
        lambda: _stub_results({"chat_turns": 0, "drafted_replies": 0}),
    )

    notifier = MagicMock()
    result = training_extract_tick(notifier)

    notifier.push.assert_not_called()
    assert result["total_written"] == 0


def test_tick_returns_target_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """The result includes target paths so the dashboard can link them."""
    monkeypatch.setattr(
        "jarvis.training.extract.extract_all",
        lambda: _stub_results({"chat_turns": 1, "drafted_replies": 0}),
    )

    notifier = MagicMock()
    result = training_extract_tick(notifier)

    assert "targets" in result
    assert len(result["targets"]) == 2
    assert all(isinstance(t, str) for t in result["targets"])
