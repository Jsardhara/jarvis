"""Daily Forge cost cap.

Tracks per-day USD spend in ``state/budget.jsonl`` and rejects requests
that would exceed the cap. Used by ``daily_forge_tick``.

Schema (one line per spend record):
    {"date": "2026-05-04", "ts": "...iso...", "tag": "forge.scaffold", "usd": 1.23}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jarvis.config import get_settings

log = logging.getLogger(__name__)

# Hard daily cap. Routine aborts if today's spend + estimate > this.
DAILY_CAP_USD = 5.00


def _budget_path() -> Path:
    return get_settings().state_dir / "budget.jsonl"


@dataclass(frozen=True)
class BudgetSnapshot:
    date: str  # YYYY-MM-DD
    spent_usd: float
    cap_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)


def _today_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def today_spent() -> float:
    """Sum USD spent today (UTC date)."""
    path = _budget_path()
    if not path.exists():
        return 0.0
    today = _today_str()
    total = 0.0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("date") == today:
                try:
                    total += float(rec.get("usd", 0))
                except (TypeError, ValueError):
                    continue
    return total


def snapshot(cap_usd: float = DAILY_CAP_USD) -> BudgetSnapshot:
    return BudgetSnapshot(date=_today_str(), spent_usd=today_spent(), cap_usd=cap_usd)


def can_afford(estimate_usd: float, cap_usd: float = DAILY_CAP_USD) -> bool:
    """Return True if today's spend + estimate would stay within cap."""
    return (today_spent() + estimate_usd) <= cap_usd


def record_spend(usd: float, tag: str = "") -> None:
    """Append a spend record to state/budget.jsonl."""
    if usd <= 0:
        return
    path = _budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "date": _today_str(),
        "ts": datetime.now(UTC).isoformat(),
        "tag": tag,
        "usd": round(float(usd), 4),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    log.info("budget: recorded $%.4f (tag=%s)", usd, tag)
