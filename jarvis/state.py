"""State persistence — tasks.json + inbox.jsonl + agent_log.jsonl + confirmations.jsonl."""
from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from .config import get_settings
from .contract import (
    AgentLogEntry,
    Confirmation,
    InboxEvent,
    SentinelHealthEvent,
    Task,
)

log = logging.getLogger(__name__)

_WATCHLIST_DEFAULT = ["BTC", "ETH", "SOL"]
_ROTATE_KEEP_UNCOMPRESSED_DAYS = 7

# ── Inbox listeners — notified synchronously after each append_inbox call ──

_inbox_listeners: list[Callable[[InboxEvent], None]] = []


def register_inbox_listener(fn: Callable[[InboxEvent], None]) -> None:
    """Register a callback to be called after each append_inbox.

    Duplicate registrations are silently ignored.
    """
    if fn not in _inbox_listeners:
        _inbox_listeners.append(fn)


def unregister_inbox_listener(fn: Callable[[InboxEvent], None]) -> None:
    """Remove a previously registered inbox listener (no-op if absent)."""
    if fn in _inbox_listeners:
        _inbox_listeners.remove(fn)

TASKS_SCHEMA_VERSION = 1


def _tasks_path() -> Path:
    return get_settings().state_dir / "tasks.json"


def _inbox_path() -> Path:
    return get_settings().state_dir / "inbox.jsonl"


def _agent_log_path() -> Path:
    return get_settings().state_dir / "agent_log.jsonl"


def _confirmations_path() -> Path:
    return get_settings().state_dir / "confirmations.jsonl"


def _sentinel_health_path() -> Path:
    return get_settings().state_dir / "sentinel_health.jsonl"


def _watchlist_path() -> Path:
    return get_settings().state_dir / "watchlist.json"


def _inbox_archive_dir(state_dir: Path | None = None) -> Path:
    base = state_dir if state_dir is not None else get_settings().state_dir
    return base / "inbox"


def load_tasks() -> list[Task]:
    p = _tasks_path()
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [Task(**t) for t in raw.get("tasks", [])]


def save_tasks(tasks: Iterable[Task]) -> None:
    p = _tasks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": TASKS_SCHEMA_VERSION,
        "tasks": [t.model_dump() for t in tasks],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_task(task: Task) -> Task:
    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)
    return task


def update_task(task_id: str, **fields) -> Task | None:
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id == task_id:
            updated = t.model_copy(update=fields)
            tasks[i] = updated
            save_tasks(tasks)
            return updated
    return None


def append_inbox(event: InboxEvent) -> None:
    p = _inbox_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")
    for fn in list(_inbox_listeners):
        try:
            fn(event)
        except Exception:
            log.warning("inbox listener %r raised", fn, exc_info=True)


def read_inbox(limit: int = 20) -> list[InboxEvent]:
    p = _inbox_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    return [InboxEvent(**json.loads(line)) for line in tail if line.strip()]


def read_daily_forge(limit: int = 30) -> list[dict[str, Any]]:
    """Tail state/daily_projects.jsonl; each line = autonomous forge run record."""
    p = get_settings().state_dir / "daily_projects.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    out: list[dict[str, Any]] = []
    for line in tail:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --- Mission control: agent_log + confirmations ---


def append_agent_log(entry: AgentLogEntry) -> None:
    p = _agent_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def read_agent_log(agent: str | None = None, limit: int = 50) -> list[AgentLogEntry]:
    p = _agent_log_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    entries = [AgentLogEntry(**json.loads(line)) for line in lines if line.strip()]
    if agent is not None:
        entries = [e for e in entries if e.agent == agent]
    return entries[-limit:] if limit else entries


def add_confirmation(confirmation: Confirmation) -> Confirmation:
    p = _confirmations_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(confirmation.model_dump_json() + "\n")
    return confirmation


def read_confirmations(status: str | None = None, limit: int = 100) -> list[Confirmation]:
    p = _confirmations_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    by_id: dict[str, Confirmation] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        c = Confirmation(**json.loads(line))
        # later writes for same id win (status updates)
        by_id[c.id] = c
    items = list(by_id.values())
    if status is not None:
        items = [c for c in items if c.status == status]
    return items[-limit:] if limit else items


def update_confirmation(confirmation_id: str, **fields) -> Confirmation | None:
    items = read_confirmations(status=None, limit=0)
    for c in items:
        if c.id == confirmation_id:
            updated = c.model_copy(update=fields)
            # append updated record (read_confirmations dedupes by id)
            with _confirmations_path().open("a", encoding="utf-8") as f:
                f.write(updated.model_dump_json() + "\n")
            return updated
    return None


# --- Sentinel infrastructure health (not operator inbox) ---


def append_sentinel_health(event: SentinelHealthEvent) -> None:
    """Write a heartbeat tick to sentinel_health.jsonl — NOT inbox.jsonl."""
    p = _sentinel_health_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")


def read_sentinel_health(limit: int = 100) -> list[SentinelHealthEvent]:
    """Return recent sentinel health ticks (newest last)."""
    p = _sentinel_health_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    return [SentinelHealthEvent(**json.loads(line)) for line in tail if line.strip()]


# --- Watchlist ---


def load_watchlist() -> list[str]:
    """Return watchlist items.  Creates watchlist.json with defaults if absent."""
    p = _watchlist_path()
    if not p.exists():
        save_watchlist(list(_WATCHLIST_DEFAULT))
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data.get("items", _WATCHLIST_DEFAULT))


def save_watchlist(items: list[str]) -> None:
    """Persist watchlist items to state/watchlist.json."""
    p = _watchlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"items": list(items)}, indent=2), encoding="utf-8")


# --- Inbox rotation ---


def _parse_entry_date(raw: str) -> date | None:
    """Extract the calendar date from a JSONL inbox entry, or None on failure."""
    try:
        entry = json.loads(raw)
        ts_str = entry.get("ts", "")
        if not ts_str:
            return None
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).date()
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def rotate_inbox(state_dir: Path | None = None) -> int:
    """Move non-today entries from inbox.jsonl into per-day archive files.

    Rules:
    - Today's entries stay in inbox.jsonl uncompressed.
    - Entries from 1–7 days ago go to state/inbox/YYYY-MM-DD.jsonl (plain).
    - Entries 8+ days old go to state/inbox/YYYY-MM-DD.jsonl.gz (gzipped).

    Returns the count of entries moved out of inbox.jsonl.
    """
    base = state_dir if state_dir is not None else get_settings().state_dir
    archive_dir = base / "inbox"
    archive_dir.mkdir(parents=True, exist_ok=True)

    inbox = base / "inbox.jsonl"
    if not inbox.exists():
        return 0

    today = date.today()

    lines = inbox.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    by_date: dict[date, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        entry_date = _parse_entry_date(stripped)
        if entry_date is None or entry_date >= today:
            keep.append(stripped)
        else:
            by_date.setdefault(entry_date, []).append(stripped)

    rotated = sum(len(v) for v in by_date.values())
    if rotated == 0:
        return 0

    # Write today's entries back
    inbox.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")

    # Archive each date
    for entry_date, entry_lines in by_date.items():
        age_days = (today - entry_date).days
        content = "\n".join(entry_lines) + "\n"
        if age_days <= _ROTATE_KEEP_UNCOMPRESSED_DAYS:
            dest = archive_dir / f"{entry_date.isoformat()}.jsonl"
            _append_to_archive_plain(dest, content)
        else:
            dest_gz = archive_dir / f"{entry_date.isoformat()}.jsonl.gz"
            _append_to_archive_gz(dest_gz, content)

    return rotated


def _append_to_archive_plain(path: Path, content: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


def _append_to_archive_gz(path: Path, content: str) -> None:
    existing = b""
    if path.exists():
        with gzip.open(path, "rb") as fh:
            existing = fh.read()
    with gzip.open(path, "wb") as fh:
        fh.write(existing + content.encode("utf-8"))
