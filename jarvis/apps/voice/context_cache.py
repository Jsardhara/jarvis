"""Read/write the voice fact-sheet at ``state/voice_context.json``.

Sentinel refreshes this file every 5 min by tailing existing inbox
events (no new LLM calls). The cheap voice handler reads it in to seed
its Haiku prompt with current pnl / mail counts / next event so quick
status queries don't need to fan out to subsystems.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("state/voice_context.json")
STALE_AFTER_MIN = 30


def voice_context_path() -> Path:
    """Resolve the voice context path, honoring JARVIS_STATE_DIR if set."""
    state_dir = os.environ.get("JARVIS_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "voice_context.json"
    return DEFAULT_PATH


def load_voice_context(path: Path | None = None) -> dict[str, Any]:
    """Return the cached fact sheet, or an empty dict if missing/stale.

    Stale = not refreshed in ``STALE_AFTER_MIN`` minutes. Stale dicts
    return empty so the handler doesn't quote outdated numbers.
    """
    p = path or voice_context_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("[voice] context load failed: %s", exc)
        return {}
    updated = data.get("updated_at")
    if updated:
        try:
            ts = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if datetime.now(UTC) - ts > timedelta(minutes=STALE_AFTER_MIN):
                logger.info("[voice] context stale (>%d min) — ignoring", STALE_AFTER_MIN)
                return {}
        except ValueError:
            pass
    return data


def write_voice_context(payload: dict[str, Any], path: Path | None = None) -> Path:
    """Write the fact sheet atomically (temp file + rename)."""
    p = path or voice_context_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **payload,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix="voice_context.", dir=str(p.parent)
    )
    import contextlib

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, p)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return p


def render_for_prompt(ctx: dict[str, Any]) -> str:
    """Compress the fact sheet into a few lines suitable for an LLM prompt."""
    if not ctx:
        return f"(context unavailable; respond conservatively)\n{render_tasks_block()}"
    lines: list[str] = []
    if "pnl_today_pct" in ctx:
        lines.append(f"pnl_today: {ctx['pnl_today_pct']:+.2%}")
    if "open_positions" in ctx:
        lines.append(f"open_positions: {ctx['open_positions']}")
    if "unread_mail" in ctx:
        lines.append(f"unread_mail: {ctx['unread_mail']}")
    if "next_event" in ctx and ctx["next_event"]:
        lines.append(f"next_event: {ctx['next_event']}")
    if "atlas_health" in ctx:
        lines.append(f"atlas_health: {ctx['atlas_health']}")
    tasks_block = render_tasks_block()
    if tasks_block:
        lines.append(tasks_block)
    if not lines:
        return "(context empty)"
    return "\n".join(lines)


def _tasks_path() -> Path:
    """Resolve tasks.json — dashboard owns web/data/tasks.json.

    Test override: ``JARVIS_TASKS_PATH`` (explicit file path). The generic
    ``JARVIS_STATE_DIR`` is *not* honored here because the dashboard
    writes to web/data/tasks.json regardless of state-dir overrides, so
    pointing at state/tasks.json would silently miss every task created
    in the UI.
    """
    explicit = os.environ.get("JARVIS_TASKS_PATH")
    if explicit:
        return Path(explicit)
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "web" / "data" / "tasks.json"


def load_tasks() -> list[dict[str, Any]]:
    """Read tasks from web/data/tasks.json. Returns empty list on miss/error."""
    p = _tasks_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        return list(data.get("tasks") or [])
    if isinstance(data, list):
        return data
    return []


def render_tasks_block(limit: int = 8) -> str:
    """Render open tasks as a compact bullet block for the LLM prompt.

    Filters to non-done items, sorts by urgency+importance (Eisenhower
    do-first), shows up to ``limit``. Returns an empty string when no
    open tasks so the prompt stays terse.
    """
    tasks = load_tasks()
    open_tasks = [
        t for t in tasks if str(t.get("kanban", "")).lower() not in ("done", "archived")
    ]
    if not open_tasks:
        return ""

    def rank(t: dict[str, Any]) -> int:
        urg = str(t.get("urgency", "")).lower() == "urgent"
        imp = str(t.get("importance", "")).lower() == "important"
        return -(int(urg) * 2 + int(imp))

    open_tasks.sort(key=rank)
    bullets: list[str] = []
    for t in open_tasks[:limit]:
        title = str(t.get("title", "")).strip()
        kanban = str(t.get("kanban", "?")).lower()
        urg = "U" if str(t.get("urgency", "")).lower() == "urgent" else " "
        imp = "I" if str(t.get("importance", "")).lower() == "important" else " "
        bullets.append(f"  - [{urg}{imp}/{kanban}] {title}"[:120])
    return f"open_tasks ({len(open_tasks)}):\n" + "\n".join(bullets)


__all__ = [
    "voice_context_path",
    "load_voice_context",
    "write_voice_context",
    "render_for_prompt",
    "render_tasks_block",
    "load_tasks",
    "STALE_AFTER_MIN",
]
