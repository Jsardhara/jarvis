"""Tests for ``jarvis/voice/fillers.py``."""

from __future__ import annotations

from pathlib import Path


from jarvis.voice import fillers


def test_pick_filler_returns_none_when_cache_empty(tmp_path: Path):
    assert fillers.pick_filler(tmp_path) is None


def test_pick_filler_returns_path_when_cache_populated(tmp_path: Path):
    (tmp_path / "01-foo.mp3").write_bytes(b"fake-mp3")
    (tmp_path / "02-bar.mp3").write_bytes(b"fake-mp3-2")
    pick = fillers.pick_filler(tmp_path)
    assert pick is not None
    assert pick.parent == tmp_path
    assert pick.name in {"01-foo.mp3", "02-bar.mp3"}


def test_load_filler_bytes_returns_empty_when_cache_missing(tmp_path: Path):
    assert fillers.load_filler_bytes(tmp_path / "missing") == b""


def test_load_filler_bytes_reads_picked_file(tmp_path: Path):
    payload = b"actual-filler-bytes"
    (tmp_path / "01-one.mp3").write_bytes(payload)
    out = fillers.load_filler_bytes(tmp_path)
    assert out == payload


def test_filler_catalog_has_six_entries():
    assert len(fillers.FILLERS) == 6
    ids = [f[0] for f in fillers.FILLERS]
    # All ids are unique and prefixed numerically.
    assert len(set(ids)) == 6
    assert all(fid[0].isdigit() for fid in ids)


def test_ensure_fillers_skips_existing(tmp_path: Path, monkeypatch):
    """If files already exist on disk, no synthesis should happen."""
    for filler_id, _ in fillers.FILLERS:
        (tmp_path / f"{filler_id}.mp3").write_bytes(b"prebuilt")

    called = []

    def _no_synth(*a, **kw):
        called.append(a)

    monkeypatch.setattr(fillers, "_gen_one", _no_synth)
    paths = fillers.ensure_fillers(tmp_path)
    assert len(paths) == 6
    assert called == []  # synthesis skipped because files exist
