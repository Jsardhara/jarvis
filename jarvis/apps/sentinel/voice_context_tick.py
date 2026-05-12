"""Sentinel cron — refresh the voice fact sheet from inbox tail.

Runs every 5 min. Reads recent ``state/inbox.jsonl`` events written by
the existing email/calendar/atlas/scholar ticks, picks the latest
relevant fields, writes ``state/voice_context.json`` atomically.

Zero LLM calls. Zero new subsystem fetches. Pure file → file.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.apps.voice.context_cache import write_voice_context

logger = logging.getLogger(__name__)


def _latest_value(events: list[Any], agent: str, ref_key: str) -> Any:
    """Return the most-recent ref[ref_key] from events with given agent."""
    for ev in reversed(events):
        if getattr(ev, "agent", None) != agent:
            continue
        ref = getattr(ev, "ref", {}) or {}
        if ref_key in ref:
            return ref[ref_key]
    return None


def _next_event_summary(events: list[Any]) -> str | None:
    """Pluck the next calendar event title from the latest tempo tick."""
    for ev in reversed(events):
        if getattr(ev, "agent", None) != "tempo":
            continue
        ref = getattr(ev, "ref", {}) or {}
        items = ref.get("events") or []
        if items and isinstance(items, list):
            first = items[0]
            if isinstance(first, dict):
                title = first.get("subject") or first.get("title") or ""
                start = first.get("start") or first.get("when") or ""
                if title:
                    return f"{title} {start}".strip()
    return None


def voice_context_tick() -> dict[str, Any]:
    """Build + persist the fact sheet. Returns the payload for tests."""
    from jarvis.state import read_inbox

    events = read_inbox(limit=200)

    pnl = _latest_value(events, "atlas", "pnl_pct")
    open_positions = _latest_value(events, "atlas", "open_positions")
    atlas_states = _latest_value(events, "atlas", "agent_states") or {}
    atlas_health = (
        "healthy"
        if all(s == "running" for s in atlas_states.values()) and atlas_states
        else "degraded" if atlas_states else "unknown"
    )

    unread = _latest_value(events, "tempo", "counts") or {}
    if isinstance(unread, dict):
        unread_count = int(unread.get("action_required", 0) or 0) + int(
            unread.get("info_only", 0) or 0
        )
    else:
        unread_count = 0

    payload = {
        "pnl_today_pct": float(pnl) if pnl is not None else 0.0,
        "open_positions": int(open_positions or 0),
        "unread_mail": unread_count,
        "next_event": _next_event_summary(events) or "",
        "atlas_health": atlas_health,
    }
    write_voice_context(payload)
    logger.info(
        "[voice] context refreshed: pnl=%s pos=%s mail=%s health=%s",
        payload["pnl_today_pct"],
        payload["open_positions"],
        payload["unread_mail"],
        payload["atlas_health"],
    )
    return payload


__all__ = ["voice_context_tick"]
