"""tasks.json + inbox.jsonl persistence."""
from __future__ import annotations

from jarvis.contract import InboxEvent, Task
from jarvis.state import add_task, append_inbox, load_tasks, read_inbox, save_tasks, update_task


def test_save_load_tasks_roundtrip():
    t1 = Task(title="one")
    t2 = Task(title="two", tags=["work"])
    save_tasks([t1, t2])
    loaded = load_tasks()
    assert len(loaded) == 2
    assert {t.title for t in loaded} == {"one", "two"}


def test_add_task_appends():
    add_task(Task(title="a"))
    add_task(Task(title="b"))
    assert len(load_tasks()) == 2


def test_update_task_status():
    t = Task(title="ship")
    add_task(t)
    updated = update_task(t.id, status="done")
    assert updated is not None
    assert updated.status == "done"
    # Persisted
    again = [x for x in load_tasks() if x.id == t.id][0]
    assert again.status == "done"


def test_update_missing_task_returns_none():
    assert update_task("nope") is None


def test_inbox_append_and_read():
    append_inbox(InboxEvent(agent="aide", severity="info", summary="3 unread"))
    append_inbox(InboxEvent(agent="ledger", severity="alert", summary="drawdown"))
    events = read_inbox()
    assert len(events) == 2
    assert events[-1].severity == "alert"


def test_inbox_limit():
    for i in range(30):
        append_inbox(InboxEvent(agent="x", severity="info", summary=f"e{i}"))
    tail = read_inbox(limit=5)
    assert len(tail) == 5
    assert tail[-1].summary == "e29"


def test_inbox_empty_when_no_file():
    assert read_inbox() == []


def test_load_tasks_empty_when_no_file():
    assert load_tasks() == []
