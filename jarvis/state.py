"""State persistence — tasks.json + inbox.jsonl + agent_log.jsonl + confirmations.jsonl."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .config import get_settings
from .contract import (
    AgentLogEntry,
    Confirmation,
    InboxEvent,
    SentinelHealthEvent,
    Task,
)

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


def read_inbox(limit: int = 20) -> list[InboxEvent]:
    p = _inbox_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    return [InboxEvent(**json.loads(line)) for line in tail if line.strip()]


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
