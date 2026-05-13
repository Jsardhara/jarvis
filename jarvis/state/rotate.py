"""Size-based JSONL rotation helper.

Used by append_inbox / append_turn / append_sentinel_health to keep
individual JSONL files bounded. When a file grows past ``max_bytes``
it is rotated:

    foo.jsonl     -> foo.jsonl.1
    foo.jsonl.1   -> foo.jsonl.2
    foo.jsonl.2   -> foo.jsonl.3  (oldest kept; .3 from before is dropped)

Three rotated copies are kept; older ones are discarded. Rotation is
best-effort — any OSError is logged and swallowed so a failed rotation
never blocks an append.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_KEEP_ROTATIONS = 3


def rotate_if_large(
    path: Path,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    keep: int = _KEEP_ROTATIONS,
) -> bool:
    """Rotate ``path`` when its size exceeds ``max_bytes``.

    Returns True iff a rotation actually happened. Best-effort: any
    filesystem error is swallowed and the function returns False.
    """
    try:
        if not path.exists():
            return False
        if path.stat().st_size <= max_bytes:
            return False
    except OSError as exc:
        log.warning("rotate stat failed for %s: %s", path, exc)
        return False

    try:
        # Drop the oldest rotation, shift each one up by 1.
        oldest = path.with_suffix(path.suffix + f".{keep}")
        if oldest.exists():
            oldest.unlink()
        for i in range(keep - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{i}")
            dst = path.with_suffix(path.suffix + f".{i + 1}")
            if src.exists():
                src.replace(dst)
        path.replace(path.with_suffix(path.suffix + ".1"))
        return True
    except OSError as exc:
        log.warning("rotate failed for %s: %s", path, exc)
        return False
