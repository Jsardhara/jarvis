"""Three-tier memory for Jarvis.

Tier 1 — session:    in-memory dict, caller-owned, immutable operations
Tier 2 — daily:      state/memory/daily/YYYY-MM-DD.md, markdown append
Tier 3 — long-term:  state/memory/MEMORY.md, append-only index
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import config as _config


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


# --- Tier 1: session (in-memory, immutable) ---


def remember_session(session: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """Return a new session dict with key=value added."""
    return {**session, key: value}


def session_get(session: dict[str, Any], key: str, default: Any = None) -> Any:
    return session.get(key, default)


# --- Tier 2: daily file ---


def _daily_path(state_dir: Path, date_str: str) -> Path:
    return state_dir / "memory" / "daily" / f"{date_str}.md"


def append_daily(entry: str, ts: str | None = None, date_str: str | None = None) -> Path:
    """Append a markdown bullet to today's daily file. Returns the file path."""
    settings = _config.get_settings()
    stamp = ts or _now_iso()
    day = date_str or _today_str()
    path = _daily_path(settings.state_dir, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Jarvis Daily — {day}\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] {entry}\n")
    return path


def read_daily(date_str: str | None = None) -> str:
    """Return contents of a daily file (empty string if missing)."""
    settings = _config.get_settings()
    day = date_str or _today_str()
    path = _daily_path(settings.state_dir, day)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# --- Tier 3: long-term index ---


def _longterm_path() -> Path:
    return _config.get_settings().state_dir / "memory" / "MEMORY.md"


def append_longterm(summary: str, agent: str, ts: str | None = None) -> None:
    """Append one line to the long-term MEMORY.md index."""
    stamp = ts or _now_iso()
    path = _longterm_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Jarvis Long-Term Memory\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] [{agent}] {summary}\n")


def read_longterm(limit: int = 100) -> list[str]:
    """Return last N lines from MEMORY.md (excluding header)."""
    path = _longterm_path()
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]
    return lines[-limit:] if limit else lines


# --- Convenience: record a dispatch across tiers ---


def record_dispatch(
    session: dict[str, Any],
    agent: str,
    action: str,
    tier: int,
    summary: str,
    ts: str | None = None,
) -> dict[str, Any]:
    """Write dispatch to daily + session. Write to longterm only for tier <= 2."""
    stamp = ts or _now_iso()
    entry = f"[{agent}] {action} — {summary}"
    append_daily(entry, ts=stamp)
    new_session = remember_session(
        session, f"{agent}.last_action", {"action": action, "ts": stamp, "summary": summary}
    )
    if tier <= 2:
        append_longterm(summary=entry, agent=agent, ts=stamp)
    return new_session
