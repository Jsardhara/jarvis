"""Tests for jarvis.state.rotate_inbox — gzip rotation of old inbox entries."""
from __future__ import annotations

import gzip
import json
from datetime import date, timedelta
from pathlib import Path

from jarvis.config import Settings


def _fake_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        state_dir=tmp_path,
        atlas_api="http://localhost:8000",
    )


def _write_inbox_entry(inbox_path: Path, ts: str, agent: str = "tempo") -> None:
    """Append a minimal InboxEvent line to inbox.jsonl."""
    from jarvis.contract import InboxEvent

    event = InboxEvent(agent=agent, severity="info", summary="test", ref={})
    raw = json.loads(event.model_dump_json())
    raw["ts"] = ts
    with inbox_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(raw) + "\n")


def test_rotate_inbox_creates_inbox_dir(tmp_path: Path, monkeypatch) -> None:
    """rotate_inbox ensures state/inbox/ directory exists."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import rotate_inbox

    rotate_inbox(state_dir=tmp_path)
    assert (tmp_path / "inbox").is_dir()


def test_rotate_inbox_returns_zero_when_empty(tmp_path: Path, monkeypatch) -> None:
    """No inbox.jsonl → returns 0."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import rotate_inbox

    count = rotate_inbox(state_dir=tmp_path)
    assert count == 0


def test_rotate_inbox_today_entries_stay(tmp_path: Path, monkeypatch) -> None:
    """Entries timestamped today remain in inbox.jsonl uncompressed."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    today = date.today().isoformat()
    inbox_path = tmp_path / "inbox.jsonl"
    _write_inbox_entry(inbox_path, ts=f"{today}T12:00:00+00:00")

    from jarvis.state import rotate_inbox

    count = rotate_inbox(state_dir=tmp_path)
    assert count == 0
    assert inbox_path.exists()
    lines = [line for line in inbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_rotate_inbox_yesterday_moved_to_archive(tmp_path: Path, monkeypatch) -> None:
    """Yesterday's entries move to state/inbox/YYYY-MM-DD.jsonl (uncompressed — within 7d)."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    inbox_path = tmp_path / "inbox.jsonl"
    _write_inbox_entry(inbox_path, ts=f"{yesterday}T09:00:00+00:00")
    _write_inbox_entry(inbox_path, ts=f"{today}T09:00:00+00:00")

    from jarvis.state import rotate_inbox

    count = rotate_inbox(state_dir=tmp_path)
    assert count == 1

    # Today's entry stays in inbox.jsonl
    remaining = [
        line for line in inbox_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(remaining) == 1

    # Yesterday's entry in archive dir (uncompressed since within 7d)
    archive_dir = tmp_path / "inbox"
    archive_file = archive_dir / f"{yesterday}.jsonl"
    assert archive_file.exists()
    archived = [
        line for line in archive_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(archived) == 1


def test_rotate_inbox_old_entries_gzipped(tmp_path: Path, monkeypatch) -> None:
    """Entries older than 7 days are stored as .jsonl.gz."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    old_date = (date.today() - timedelta(days=8)).isoformat()
    inbox_path = tmp_path / "inbox.jsonl"
    _write_inbox_entry(inbox_path, ts=f"{old_date}T08:00:00+00:00")

    from jarvis.state import rotate_inbox

    count = rotate_inbox(state_dir=tmp_path)
    assert count == 1

    archive_dir = tmp_path / "inbox"
    gz_file = archive_dir / f"{old_date}.jsonl.gz"
    assert gz_file.exists()

    # Ensure it's valid gzip with the entry inside
    with gzip.open(gz_file, "rt", encoding="utf-8") as fh:
        lines = [line for line in fh.read().splitlines() if line.strip()]
    assert len(lines) == 1


def test_rotate_inbox_mixed_dates(tmp_path: Path, monkeypatch) -> None:
    """Mixed-date inbox: today stays, yesterday uncompressed, 8d-ago gzipped."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    today = date.today()
    yesterday = today - timedelta(days=1)
    old = today - timedelta(days=8)

    inbox_path = tmp_path / "inbox.jsonl"
    for ts_date in (today, yesterday, old):
        _write_inbox_entry(inbox_path, ts=f"{ts_date.isoformat()}T10:00:00+00:00")

    from jarvis.state import rotate_inbox

    count = rotate_inbox(state_dir=tmp_path)
    assert count == 2  # yesterday + old moved

    # Today's entry remains
    lines = [
        line for line in inbox_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(lines) == 1

    archive_dir = tmp_path / "inbox"
    # Yesterday uncompressed
    assert (archive_dir / f"{yesterday.isoformat()}.jsonl").exists()
    # Old gzipped
    assert (archive_dir / f"{old.isoformat()}.jsonl.gz").exists()
