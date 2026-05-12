"""Memory tier tests."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from jarvis.state.memory import (
    append_daily,
    append_longterm,
    read_daily,
    read_longterm,
    record_dispatch,
    remember_session,
    session_get,
)


def test_remember_session_creates_new_dict():
    session = {}
    new_session = remember_session(session, "key1", "value1")
    assert new_session["key1"] == "value1"
    assert session == {}, "original session should not be mutated"


def test_session_get_returns_value():
    session = {"key1": "value1"}
    assert session_get(session, "key1") == "value1"


def test_session_get_returns_default():
    session = {}
    assert session_get(session, "missing", "default") == "default"


def test_append_daily_creates_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        path = append_daily("test entry", date_str="2026-04-27")
        assert path.exists()
        assert "test entry" in path.read_text()


def test_append_daily_appends_to_existing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        append_daily("first", date_str="2026-04-27")
        append_daily("second", date_str="2026-04-27")
        content = read_daily(date_str="2026-04-27")
        assert "first" in content
        assert "second" in content


def test_read_daily_missing_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        content = read_daily(date_str="2026-01-01")
        assert content == ""


def test_append_longterm_creates_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        append_longterm("test summary", "test_agent")
        path = tmpdir / "memory" / "MEMORY.md"
        assert path.exists(), f"Expected {path} to exist"
        assert "test summary" in path.read_text()


def test_read_longterm_missing_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        entries = read_longterm()
        assert entries == []


def test_record_dispatch_writes_to_daily_and_session(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        session = {}
        new_session = record_dispatch(session, "test_agent", "read", tier=3, summary="test dispatch")
        assert "test_agent.last_action" in new_session
        assert new_session["test_agent.last_action"]["action"] == "read"


def test_record_dispatch_tier_1_writes_longterm(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from jarvis import config

        mock_settings = MagicMock()
        mock_settings.state_dir = tmpdir
        monkeypatch.setattr(config, "get_settings", lambda: mock_settings)

        session = {}
        record_dispatch(session, "test_agent", "execute", tier=1, summary="important action")
        longterm = read_longterm()
        assert len(longterm) > 0
        assert "important action" in longterm[0]
