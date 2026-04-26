"""State persistence — tasks.json + inbox.jsonl."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .config import get_settings
from .contract import InboxEvent, Task

TASKS_SCHEMA_VERSION = 1


def _tasks_path() -> Path:
    return get_settings().state_dir / "tasks.json"


def _inbox_path() -> Path:
    return get_settings().state_dir / "inbox.jsonl"


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
