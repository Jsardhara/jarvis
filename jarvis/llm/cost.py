"""Cost telemetry — log per-call token usage, roll up daily totals.

MODEL_RATES maps model-id substrings -> (in_usd_per_mtok, out_usd_per_mtok).
Rates are defaults; override by editing MODEL_RATES before calling log_cost.

Each entry also records the ``backend`` that served the request ("claude",
"vllm", "ollama", ...). Local backends ship at zero rate today; the field
exists so the dashboard can break costs out per engine once the operator
flips a subsystem off Claude.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from jarvis.config import get_settings

log = logging.getLogger(__name__)

# Per-million-token rates (USD).  Keys match on substring of model id.
MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku": (1.0, 5.0),
}

_DEFAULT_RATE: tuple[float, float] = (3.0, 15.0)  # fallback to sonnet pricing

# Per-backend rate overrides. Local backends are free; the entry exists so
# operators can plug in an electricity-cost estimate later if they want a
# real number. (in_usd_per_mtok, out_usd_per_mtok).
_BACKEND_OVERRIDES: dict[str, tuple[float, float]] = {
    "vllm": (0.0, 0.0),
    "ollama": (0.0, 0.0),
}


def _rate_for(model: str, backend: str = "claude") -> tuple[float, float]:
    """Return (in_rate, out_rate) for a model id on a given backend.

    Local backends override to $0 regardless of model id — the model name is
    still recorded so cost-log filters by model continue to work, but the
    arithmetic resolves to zero spend.
    """
    if backend in _BACKEND_OVERRIDES:
        return _BACKEND_OVERRIDES[backend]
    for key, rate in MODEL_RATES.items():
        if key in model:
            return rate
    return _DEFAULT_RATE


def _cost_log_path() -> Path:
    return get_settings().state_dir / "cost_log.jsonl"


def log_cost(
    agent: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    *,
    backend: str = "claude",
) -> None:
    """Append one cost entry to state/cost_log.jsonl.

    ``backend`` is keyword-only so existing positional callers keep working.
    Defaults to "claude" because every pre-P2 entry was a Claude call.
    """
    in_rate, out_rate = _rate_for(model, backend=backend)
    cost_usd = (in_tokens / 1_000_000) * in_rate + (out_tokens / 1_000_000) * out_rate
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "agent": agent,
        "model": model,
        "backend": backend,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "cost_usd": round(cost_usd, 8),
    }
    p = _cost_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def daily_rollup(target_date: date | None = None) -> dict:
    """Sum today's (or ``target_date``'s) costs grouped by agent, model, and backend.

    Returns::

        {
            "date": "2026-04-28",
            "total_usd": 1.23,
            "by_agent": {"tempo": 0.4, ...},
            "by_model": {"claude-sonnet-4-6": 0.4, ...},
            "by_backend": {"claude": 1.20, "vllm": 0.03, ...},
            "call_count": 5,
        }

    Entries written before the backend column shipped are bucketed under
    "claude" so historical aggregates stay accurate.
    """
    target = target_date or date.today()
    target_str = target.isoformat()

    p = _cost_log_path()
    if not p.exists():
        return _empty_rollup(target_str)

    total_usd = 0.0
    by_agent: dict[str, float] = {}
    by_model: dict[str, float] = {}
    by_backend: dict[str, float] = {}
    call_count = 0

    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("cost_log: skipping malformed line")
            continue
        ts_str = entry.get("ts", "")
        if not ts_str.startswith(target_str):
            continue
        cost = float(entry.get("cost_usd", 0.0))
        agent = str(entry.get("agent", "unknown"))
        model = str(entry.get("model", "unknown"))
        backend = str(entry.get("backend", "claude"))  # default for pre-P2 rows

        total_usd += cost
        by_agent[agent] = round(by_agent.get(agent, 0.0) + cost, 8)
        by_model[model] = round(by_model.get(model, 0.0) + cost, 8)
        by_backend[backend] = round(by_backend.get(backend, 0.0) + cost, 8)
        call_count += 1

    return {
        "date": target_str,
        "total_usd": round(total_usd, 6),
        "by_agent": by_agent,
        "by_model": by_model,
        "by_backend": by_backend,
        "call_count": call_count,
    }


def _empty_rollup(date_str: str) -> dict:
    return {
        "date": date_str,
        "total_usd": 0.0,
        "by_agent": {},
        "by_model": {},
        "by_backend": {},
        "call_count": 0,
    }
