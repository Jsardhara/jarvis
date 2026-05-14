"""Tests for jarvis.state.operator_presence — presence tracking + stale scan."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jarvis.state import operator_presence


def test_mark_present_then_seconds_since(isolated_state: Path) -> None:
    """After mark_present, seconds_since_last_seen should be a small float."""
    operator_presence.mark_present("voice", user_id="default")

    elapsed = operator_presence.seconds_since_last_seen()

    assert elapsed != float("inf")
    assert 0.0 <= elapsed < 60.0  # well under a minute


def test_seconds_since_returns_inf_when_no_marks(isolated_state: Path) -> None:
    """With no presence file, seconds_since_last_seen returns inf."""
    elapsed = operator_presence.seconds_since_last_seen()
    assert elapsed == float("inf")


def test_last_seen_reads_most_recent(isolated_state: Path) -> None:
    """last_seen returns the latest PresenceMark."""
    operator_presence.mark_present("chat")
    operator_presence.mark_present("voice")

    mark = operator_presence.last_seen()
    assert mark is not None
    assert mark.surface == "voice"
    assert mark.user_id == "default"


def test_scan_presence_stale_emits_when_stale(isolated_state: Path) -> None:
    """When the operator has been silent >6h, scan_presence_stale emits a warn event."""
    operator_presence.mark_present("voice")

    with patch.object(operator_presence, "seconds_since_last_seen", return_value=7 * 3600):
        events = operator_presence.scan_presence_stale(threshold_hours=6)

    assert len(events) == 1
    ev = events[0]
    assert ev.agent == "sentinel"
    assert ev.severity == "warn"
    assert "silent" in ev.summary.lower()


def test_scan_presence_stale_no_event_when_fresh(isolated_state: Path) -> None:
    """When the operator was recently seen, no warn event fires."""
    operator_presence.mark_present("voice")

    with patch.object(operator_presence, "seconds_since_last_seen", return_value=60.0):
        events = operator_presence.scan_presence_stale(threshold_hours=6)

    assert events == []


def test_scan_presence_stale_no_event_when_cold(isolated_state: Path) -> None:
    """With no marks at all, no warn event fires (cold start ≠ stale)."""
    events = operator_presence.scan_presence_stale(threshold_hours=6)
    assert events == []


def test_scan_presence_stale_dedup(isolated_state: Path) -> None:
    """A second scan within the dedup window does not re-emit."""
    operator_presence.mark_present("voice")

    with patch.object(operator_presence, "seconds_since_last_seen", return_value=7 * 3600):
        first = operator_presence.scan_presence_stale(threshold_hours=6)
        second = operator_presence.scan_presence_stale(threshold_hours=6)

    assert len(first) == 1
    assert second == []
