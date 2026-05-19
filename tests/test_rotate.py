"""Tests for jarvis.state.rotate — size-based JSONL rotation."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.state.rotate import rotate_if_large


def test_no_rotate_when_path_missing(tmp_path: Path) -> None:
    """Missing source returns False without raising."""
    target = tmp_path / "absent.jsonl"
    assert rotate_if_large(target) is False


def test_no_rotate_below_max(tmp_path: Path) -> None:
    """File under the threshold is left in place."""
    target = tmp_path / "small.jsonl"
    target.write_bytes(b"line\n" * 100)
    assert rotate_if_large(target, max_bytes=10_000) is False
    assert target.exists(), "small file should not be rotated"
    # No rotation copies should appear.
    assert not (tmp_path / "small.jsonl.1").exists()


def test_rotate_when_over_max(tmp_path: Path) -> None:
    """File over the threshold rotates to .1 and source is gone."""
    target = tmp_path / "big.jsonl"
    target.write_bytes(b"x" * 2_048)
    assert rotate_if_large(target, max_bytes=1_024) is True
    assert not target.exists(), "source should have moved to .1"
    rotated = tmp_path / "big.jsonl.1"
    assert rotated.exists()
    assert rotated.stat().st_size == 2_048


def test_rotate_shifts_existing_copies(tmp_path: Path) -> None:
    """An existing .1 shifts to .2; .2 shifts to .3 on a fresh rotate."""
    target = tmp_path / "log.jsonl"
    prior_one = tmp_path / "log.jsonl.1"
    prior_two = tmp_path / "log.jsonl.2"
    target.write_bytes(b"new" * 1_024)  # ~3 KB, over threshold
    prior_one.write_bytes(b"older")
    prior_two.write_bytes(b"oldest")
    assert rotate_if_large(target, max_bytes=1_024) is True
    # source → .1
    assert (tmp_path / "log.jsonl.1").read_bytes().startswith(b"new")
    # .1 → .2
    assert (tmp_path / "log.jsonl.2").read_bytes() == b"older"
    # .2 → .3
    assert (tmp_path / "log.jsonl.3").read_bytes() == b"oldest"


def test_rotate_drops_oldest_beyond_keep(tmp_path: Path) -> None:
    """With keep=3 and an existing .3, the .3 is unlinked before shifts."""
    target = tmp_path / "log.jsonl"
    target.write_bytes(b"new" * 1_024)
    (tmp_path / "log.jsonl.1").write_bytes(b"a")
    (tmp_path / "log.jsonl.2").write_bytes(b"b")
    (tmp_path / "log.jsonl.3").write_bytes(b"c")
    assert rotate_if_large(target, max_bytes=1_024, keep=3) is True
    # .3 now holds what used to be in .2 (b"b"), not the old .3 (b"c").
    assert (tmp_path / "log.jsonl.3").read_bytes() == b"b"


def test_rotate_with_custom_keep(tmp_path: Path) -> None:
    """A custom keep value controls how many rotations are retained."""
    target = tmp_path / "log.jsonl"
    target.write_bytes(b"x" * 2_000)
    assert rotate_if_large(target, max_bytes=1_000, keep=2) is True
    assert (tmp_path / "log.jsonl.1").exists()
    # No .3 should have been created since keep=2.
    assert not (tmp_path / "log.jsonl.3").exists()


def test_rotate_silently_returns_false_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem failure during shift is logged but does not raise."""
    target = tmp_path / "log.jsonl"
    target.write_bytes(b"x" * 2_000)
    # Patch Path.replace to raise — simulates a perm issue mid-rotate.
    original_replace = Path.replace

    def boom(self: Path, *args: object, **kwargs: object) -> Path:
        if self == target:
            raise OSError("simulated")
        return original_replace(self, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", boom)
    # Should not raise.
    result = rotate_if_large(target, max_bytes=1_000)
    assert result is False
