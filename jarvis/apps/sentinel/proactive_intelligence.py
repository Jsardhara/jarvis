"""J8 — Active proactive intelligence (LLM-driven pattern detection).

Daily pass that submits the operator's recent activity (chat turns, open tasks,
known facts, active projects) to Sonnet and asks for up to N non-obvious
observations. Each observation lands in ``state/inbox.jsonl`` as an
``InboxEvent`` so the morning digest surfaces it.

This is intentionally distinct from rule-based proactivity (J3):

* J3 reacts to events with deterministic rules.
* J8 asks an LLM to *find* patterns no rule would catch — multi-task themes,
  stalled projects, watchlist/news overlap.

Dedup: observations fire at most once per 7-day window per summary string. The
fire log lives at ``state/_proactive_fired.jsonl``.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.config import get_settings
from jarvis.contract import InboxEvent
from jarvis.llm.queue import submit
from jarvis.state import append_inbox, load_tasks
from jarvis.state.chat_turns import read_recent
from jarvis.state.facts import read_facts
from jarvis.state.projects import list_projects

log = logging.getLogger(__name__)

_DEDUP_WINDOW_DAYS = 7
_FIRED_LOG_NAME = "_proactive_fired.jsonl"
_DEFAULT_USER_ID = "default"
_MAX_CHAT_TURNS = 50
_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)

_SYSTEM_PROMPT = (
    "You are Jarvis's pattern-detector. Look at the operator's recent activity "
    "and surface up to 3 non-obvious connections worth their attention. Each "
    "observation should be specific (cite a task title, a person's name, a "
    "project), actionable (suggest a next step in 5 words or less), and NOT "
    "something a simple keyword rule would catch. Output as JSON array: "
    '[{"observation": "...", "suggestion": "...", "severity": "info|warn"}]. '
    "Empty array if nothing worth flagging."
)


def _fired_path() -> Path:
    return get_settings().state_dir / _FIRED_LOG_NAME


def _load_recent_fired(now: datetime | None = None) -> set[str]:
    """Return the set of summaries fired in the last ``_DEDUP_WINDOW_DAYS``."""
    p = _fired_path()
    if not p.exists():
        return set()
    cutoff = (now or datetime.now(UTC)) - timedelta(days=_DEDUP_WINDOW_DAYS)
    out: set[str] = set()
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts_str = rec.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            summary = rec.get("summary")
            if isinstance(summary, str) and summary:
                out.add(summary)
    except OSError as exc:
        log.warning("proactive_intelligence: fired log read failed: %s", exc)
    return out


def _record_fired(summary: str) -> None:
    """Append a fired observation to the dedup log."""
    p = _fired_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(UTC).isoformat(), "summary": summary}
    try:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError as exc:
        log.warning("proactive_intelligence: fired log write failed: %s", exc)


def _strip_fence(text: str) -> str:
    """Remove a surrounding ```json … ``` markdown fence if present."""
    m = _FENCE_RE.match(text.strip())
    if m:
        return m.group(1).strip()
    return text.strip()


def _parse_observations(reply: str) -> list[dict[str, Any]]:
    """Parse the LLM reply into a list of observation dicts.

    Tolerates a markdown fence wrapper. Returns ``[]`` on any parse failure
    rather than raising so a flaky LLM reply does not crash the daily cron.
    """
    if not reply:
        return []
    cleaned = _strip_fence(reply)
    if not cleaned:
        return []
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("proactive_intelligence: parse failed: %s", exc)
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        observation = str(item.get("observation", "")).strip()
        if not observation:
            continue
        suggestion = str(item.get("suggestion", "")).strip()
        severity = str(item.get("severity", "info")).strip().lower()
        if severity not in {"info", "warn"}:
            severity = "info"
        out.append(
            {
                "observation": observation,
                "suggestion": suggestion,
                "severity": severity,
            }
        )
    return out


def _build_context() -> str:
    """Assemble the user-prompt context block from recent activity."""
    parts: list[str] = []

    # Recent chat turns — compact, user side only is enough signal.
    turns = read_recent(_DEFAULT_USER_ID, limit=_MAX_CHAT_TURNS)
    if turns:
        parts.append("Recent chat turns (oldest first):")
        for t in turns:
            user_line = (t.user_text or "").strip().replace("\n", " ")[:200]
            if user_line:
                parts.append(f"- {user_line}")
    else:
        parts.append("Recent chat turns: (none)")

    # Open tasks
    tasks = [t for t in load_tasks() if t.status == "open"]
    if tasks:
        parts.append("")
        parts.append("Open task titles:")
        for t in tasks:
            parts.append(f"- {t.title}")
    else:
        parts.append("")
        parts.append("Open task titles: (none)")

    # Facts
    facts = read_facts(limit=30)
    if facts:
        parts.append("")
        parts.append("Known facts:")
        for f in facts:
            parts.append(f"- {f.key}: {f.value}")
    else:
        parts.append("")
        parts.append("Known facts: (none)")

    # Active projects
    projects = list_projects(status="active")
    if projects:
        parts.append("")
        parts.append("Active project titles:")
        for p in projects:
            parts.append(f"- {p.title}")
    else:
        parts.append("")
        parts.append("Active project titles: (none)")

    return "\n".join(parts)


def run_proactive_pass(*, max_observations: int = 3) -> list[InboxEvent]:
    """Daily LLM analysis — surface non-obvious connections.

    Reads: last 50 chat_turns, open tasks (state/tasks.json),
    facts (state/facts.jsonl), active projects (state/projects.jsonl).
    Submits to Sonnet via jarvis.llm.queue.submit with a structured
    prompt; parses the reply for observations; emits one InboxEvent
    per observation (capped at max_observations).
    """
    user_prompt = _build_context()
    try:
        reply = submit(_SYSTEM_PROMPT, user_prompt)
    except BaseException as exc:  # noqa: BLE001 — never crash daily cron
        log.warning("proactive_intelligence: LLM submit failed: %s", exc)
        return []

    observations = _parse_observations(reply)
    if not observations:
        return []

    recent_fired = _load_recent_fired()
    emitted: list[InboxEvent] = []

    for obs in observations:
        if len(emitted) >= max_observations:
            break
        summary = obs["observation"]
        if summary in recent_fired:
            continue
        event = InboxEvent(
            agent="jarvis",
            severity=obs["severity"],
            summary=summary,
            ref={
                "suggestion": obs["suggestion"],
                "kind": "proactive_intelligence",
            },
        )
        append_inbox(event)
        _record_fired(summary)
        recent_fired.add(summary)
        emitted.append(event)

    return emitted


__all__ = ["run_proactive_pass"]
