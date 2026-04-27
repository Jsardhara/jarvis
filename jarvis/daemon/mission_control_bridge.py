"""Mission Control bridge — mirrors Jarvis state into web/data/*.json.

Mission Control (web/) is a self-contained Next.js dashboard that reads
its own JSON files. Rather than rewrite its data layer to call our
FastAPI, we mirror our state files into the shape it expects on a
short interval.

Mapping
-------
Jarvis state                   →  Mission Control file
state/inbox.jsonl              →  web/data/inbox.json       (InboxMessage[])
state/agent_log.jsonl          →  web/data/activity-log.json (ActivityEvent[])
state/tasks.jsonl              →  web/data/tasks.json       (Task[] w/ Eisenhower mapping)
state/confirmations.jsonl      →  web/data/decisions.json   (DecisionItem[])
registry agents (5 subsystems) →  web/data/agents.json      (AgentDefinition[])
"""
from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.config import get_settings
from jarvis.contract import AgentLogEntry, Confirmation, InboxEvent, Task
from jarvis.state import load_tasks

logger = logging.getLogger(__name__)


# ---------- public entrypoint ----------


def sync_tick(web_data_dir: Path | None = None) -> dict[str, int]:
    """One-shot mirror of state/* into mission-control's data/*.json.

    Returns counts per surface so the daemon can log a heartbeat.
    """
    settings = get_settings()
    state_dir = Path(settings.state_dir)
    out = web_data_dir or _default_web_data()
    out.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}

    counts["agents"] = _write_agents(out / "agents.json")
    counts["inbox"] = _mirror_inbox(state_dir / "inbox.jsonl", out / "inbox.json")
    counts["activity"] = _mirror_activity(state_dir / "agent_log.jsonl", out / "activity-log.json")
    counts["tasks"] = _mirror_tasks(out / "tasks.json")
    counts["decisions"] = _mirror_decisions(
        state_dir / "confirmations.jsonl",
        out / "decisions.json",
    )

    return counts


# ---------- writers ----------


def _write_agents(path: Path) -> int:
    agents = [
        _agent_def("tempo", "Tempo", "Mail",
                   "Outlook + iCloud — mail, calendar, tasks",
                   ["mail", "calendar", "tasks", "scheduling"]),
        _agent_def("scholar", "Scholar", "GraduationCap",
                   "Academics + study planning",
                   ["assignments", "study-plans", "summarization"]),
        _agent_def("lens", "Lens", "Search",
                   "Web research + monitoring",
                   ["search", "monitor", "synthesize"]),
        _agent_def("forge", "Forge", "Code",
                   "Code-work delegation",
                   ["code-changes", "PRs", "refactoring"]),
        _agent_def("atlas", "Atlas", "BarChart3",
                   "Trading orchestrator (Oracle/Architect/Guardian/Trader/Sage)",
                   ["scan-markets", "rank-trades", "risk-check", "execute"]),
        _agent_def("me", "Me", "User",
                   "Tasks I do myself — decisions, approvals, creative direction",
                   ["decision-making", "approvals", "creative-direction"]),
    ]
    _atomic_json_write(path, {"agents": agents})
    return len(agents)


def _agent_def(
    agent_id: str,
    name: str,
    icon: str,
    description: str,
    capabilities: list[str],
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": agent_id,
        "name": name,
        "icon": icon,
        "description": description,
        "instructions": description,
        "capabilities": capabilities,
        "skillIds": [],
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }


def _mirror_inbox(jsonl_path: Path, out: Path) -> int:
    events = list(_read_jsonl(jsonl_path, InboxEvent))
    messages = [_inbox_to_message(e) for e in events]
    _atomic_json_write(out, {"messages": messages})
    return len(messages)


def _inbox_to_message(e: InboxEvent) -> dict[str, Any]:
    msg_type = {
        "alert": "approval",
        "warn": "question",
        "info": "update",
    }.get(e.severity, "update")
    return {
        "id": _stable_id(e.ts, e.agent, e.summary),
        "from": e.agent,
        "to": "me",
        "type": msg_type,
        "taskId": None,
        "subject": e.summary[:120],
        "body": json.dumps(e.ref, indent=2) if e.ref else e.summary,
        "status": "unread",
        "createdAt": e.ts,
        "readAt": None,
    }


def _mirror_activity(jsonl_path: Path, out: Path) -> int:
    entries = list(_read_jsonl(jsonl_path, AgentLogEntry))
    events = [_log_to_event(x) for x in entries]
    _atomic_json_write(out, {"events": events})
    return len(events)


def _log_to_event(x: AgentLogEntry) -> dict[str, Any]:
    event_type = {
        "ok": "task_completed",
        "error": "task_failed",
        "proposed": "task_started",
    }.get(x.status, "comment_added")
    duration = f" ({x.duration_ms} ms)" if x.duration_ms else ""
    return {
        "id": _stable_id(x.ts, x.agent, x.action, x.request_id),
        "type": event_type,
        "actor": x.agent,
        "taskId": None,
        "summary": f"{x.agent}.{x.action}{duration}",
        "details": x.error or "",
        "timestamp": x.ts,
    }


def _mirror_tasks(out: Path) -> int:
    tasks = load_tasks()
    mapped = [_task_to_mission(t) for t in tasks]
    _atomic_json_write(out, {"tasks": mapped})
    return len(mapped)


def _task_to_mission(t: Task) -> dict[str, Any]:
    importance, urgency = _eisenhower(t)
    kanban = {
        "open": "todo",
        "done": "done",
        "cancelled": "cancelled",
    }.get(t.status, "todo")
    return {
        "id": t.id,
        "title": t.title,
        "description": "",
        "importance": importance,
        "urgency": urgency,
        "kanban": kanban,
        "projectId": None,
        "milestoneId": None,
        "assignedTo": "me",
        "collaborators": [],
        "dailyActions": [],
        "subtasks": [],
        "blockedBy": [],
        "estimatedMinutes": None,
        "actualMinutes": None,
        "acceptanceCriteria": [],
        "comments": [],
        "tags": list(t.tags),
        "notes": "",
        "dueDate": t.due,
        "createdAt": t.created,
        "updatedAt": t.updated,
    }


def _eisenhower(t: Task) -> tuple[str, str]:
    """Bucket a Jarvis Task into Eisenhower importance/urgency.

    Heuristic — without explicit tier on legacy local tasks, use due-date proximity.
    Tasks tagged with a known tier (`tier:1` … `tier:5`) override.
    """
    tier = _tier_from_tags(t.tags)
    if tier == 1 or tier == 2:
        return ("important", "urgent")
    if tier == 3:
        return ("important", "not_urgent")
    if tier == 4:
        return ("not_important", "urgent")
    if tier == 5:
        return ("not_important", "not_urgent")

    if not t.due:
        return ("important", "not_urgent")
    try:
        due = datetime.fromisoformat(t.due.replace("Z", "+00:00"))
    except ValueError:
        return ("important", "not_urgent")
    if not due.tzinfo:
        due = due.replace(tzinfo=UTC)
    delta_days = (due - datetime.now(UTC)).total_seconds() / 86400
    return ("important", "urgent" if delta_days <= 2 else "not_urgent")


def _tier_from_tags(tags: Iterable[str]) -> int | None:
    for tag in tags:
        if tag.lower().startswith("tier:"):
            try:
                return int(tag.split(":", 1)[1])
            except ValueError:
                continue
    return None


def _mirror_decisions(jsonl_path: Path, out: Path) -> int:
    confs = list(_read_jsonl(jsonl_path, Confirmation))
    items = [_conf_to_decision(c) for c in confs if c.status == "pending"]
    _atomic_json_write(out, {"decisions": items})
    return len(items)


def _conf_to_decision(c: Confirmation) -> dict[str, Any]:
    return {
        "id": c.id,
        "requestedBy": c.agent,
        "taskId": None,
        "question": c.summary or f"{c.agent} requests confirmation for {c.intent}",
        "options": ["approve", "reject"],
        "context": json.dumps(c.args, indent=2) if c.args else "",
        "status": "pending",
        "answer": None,
        "answeredAt": None,
        "createdAt": c.ts,
    }


# ---------- helpers ----------


def _read_jsonl(path: Path, model: Any) -> Iterable[Any]:
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield model.model_validate_json(line)
            except Exception as exc:
                logger.debug("skipping malformed line in %s: %s", path.name, exc)
    except Exception as exc:
        logger.warning("could not read %s: %s", path, exc)


def _atomic_json_write(path: Path, data: Any) -> None:
    """Write JSON atomically (rename) so concurrent reads never see partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        import os
        os.close(fd)
        tmp.replace(path)
    except Exception:
        try:
            import os
            os.close(fd)
        except OSError:
            pass
        if tmp.exists():
            tmp.unlink()
        raise


def _stable_id(*parts: str) -> str:
    """Deterministic short id so re-syncs don't generate new ids each tick."""
    import hashlib
    h = hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()
    return h[:16]


def _default_web_data() -> Path:
    """Project-relative default: <repo>/web/data/."""
    here = Path(__file__).resolve()
    return here.parents[2] / "web" / "data"
