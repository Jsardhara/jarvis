"""SessionStart hook — inject Sentinel inbox summary into Claude context.

Reads `state/inbox.jsonl` (newline-delimited events written by the Sentinel
daemon) and prints a short digest. Hook stdout becomes additionalContext for
the session.

Wire-up in `.claude/settings.json`:

    "hooks": {
      "SessionStart": [
        {"matcher": "*", "command": "python .claude/hooks/session_start_inbox.py"}
      ]
    }
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

WINDOW_HOURS = 24
MAX_EVENTS_SHOWN = 6


def _state_dir() -> Path:
    env = os.environ.get("JARVIS_STATE_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "state"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _recent(events: list[dict], hours: int) -> list[dict]:
    cutoff = datetime.now().astimezone() - timedelta(hours=hours)
    keep: list[dict] = []
    for e in events:
        ts_raw = e.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.astimezone()
        if ts >= cutoff:
            keep.append(e)
    return keep


def _format(events: list[dict]) -> str:
    if not events:
        return "Jarvis inbox: no Sentinel events in last 24h."
    by_agent = Counter(e.get("agent", "unknown") for e in events)
    by_severity = Counter(e.get("severity", "info") for e in events)
    head = (
        f"Jarvis inbox ({len(events)} events / {WINDOW_HOURS}h) — "
        f"agents: {dict(by_agent)} • severity: {dict(by_severity)}"
    )
    sample = events[-MAX_EVENTS_SHOWN:]
    lines = [head, "Recent:"]
    for e in sample:
        agent = e.get("agent", "?")
        sev = e.get("severity", "info")
        summary = e.get("summary", "(no summary)")
        lines.append(f"  - [{sev}] {agent}: {summary}")
    return "\n".join(lines)


def main() -> int:
    inbox = _state_dir() / "inbox.jsonl"
    digest = _format(_recent(_load(inbox), WINDOW_HOURS))
    sys.stdout.write(digest + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
