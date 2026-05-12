"""Tests for the Pro/Max-routed Claude queue."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from jarvis.llm import queue as claude_queue


def test_submit_returns_query_result():
    with patch("jarvis.llm.client.query_claude_sync", return_value="hello") as mock_q:
        out = claude_queue.submit("sys", "user", model="claude-sonnet-4-6")
    assert out == "hello"
    mock_q.assert_called_once_with(system="sys", user="user", model="claude-sonnet-4-6")


def test_submit_retries_on_rate_limit():
    calls: list[int] = []

    def fake_query(*, system: str, user: str, model: str) -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("Error code: 429 - rate_limit_error")
        return "ok"

    with patch("jarvis.llm.client.query_claude_sync", side_effect=fake_query):
        with patch("jarvis.llm.queue.time.sleep") as mock_sleep:
            out = claude_queue.submit(
                "s",
                "u",
                backoff_sec=(0.0, 0.0, 0.0),
            )
    assert out == "ok"
    assert len(calls) == 3
    assert mock_sleep.call_count == 2  # slept between failed attempts


def test_submit_does_not_retry_on_unknown_error():
    def fake_query(*, system: str, user: str, model: str) -> str:
        raise ValueError("bad json")

    with patch("jarvis.llm.client.query_claude_sync", side_effect=fake_query):
        with pytest.raises(ValueError, match="bad json"):
            claude_queue.submit("s", "u", backoff_sec=(0.0, 0.0))


def test_submit_raises_after_exhausting_retries():
    def fake_query(*, system: str, user: str, model: str) -> str:
        raise RuntimeError("overloaded — try again")

    with patch("jarvis.llm.client.query_claude_sync", side_effect=fake_query):
        with patch("jarvis.llm.queue.time.sleep"):
            with pytest.raises(RuntimeError, match="overloaded"):
                claude_queue.submit("s", "u", backoff_sec=(0.0,))


def test_is_retryable_matches_known_signals():
    assert claude_queue._is_retryable(RuntimeError("rate_limit_error"))
    assert claude_queue._is_retryable(RuntimeError("Error 429: too many requests"))
    assert claude_queue._is_retryable(RuntimeError("server overloaded"))
    assert claude_queue._is_retryable(RuntimeError("got 529 from upstream"))
    assert not claude_queue._is_retryable(ValueError("bad json"))
    assert not claude_queue._is_retryable(KeyError("missing"))
