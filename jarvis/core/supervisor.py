"""Dispatch supervisor — retry + dead-letter for subsystem calls.

Wraps registry agent calls so transient failures retry transparently and
permanent failures land in state/dead_letter.jsonl + emit a crit inbox event.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from jarvis.config import get_settings
from jarvis.contract import AgentResponse, InboxEvent

log = logging.getLogger(__name__)

# ── Transient exception types ─────────────────────────────────────────────────

_TRANSIENT_EXC: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError)

# Lazily extend with requests/httpx if available at call time
_REQUESTS_EXC: type[BaseException] | None = None
_HTTPX_EXC: type[BaseException] | None = None


def _transient_types() -> tuple[type[BaseException], ...]:
    """Return the current set of transient exception types (lazy import)."""
    global _REQUESTS_EXC, _HTTPX_EXC
    extras: list[type[BaseException]] = []
    if _REQUESTS_EXC is None:
        try:
            from requests.exceptions import RequestException  # type: ignore[import-untyped]
            _REQUESTS_EXC = RequestException
        except ImportError:
            _REQUESTS_EXC = type(None)  # sentinel: never matched
    if _REQUESTS_EXC is not type(None):
        extras.append(_REQUESTS_EXC)  # type: ignore[arg-type]

    if _HTTPX_EXC is None:
        try:
            from httpx import RequestError as HttpxRequestError  # type: ignore[import-untyped]
            _HTTPX_EXC = HttpxRequestError
        except ImportError:
            _HTTPX_EXC = type(None)
    if _HTTPX_EXC is not type(None):
        extras.append(_HTTPX_EXC)  # type: ignore[arg-type]

    return _TRANSIENT_EXC + tuple(extras)


# Deterministic errors — no retry, straight to dead-letter
_DETERMINISTIC_EXC: tuple[type[BaseException], ...] = (ValueError, TypeError)

# ── Dead-letter record ────────────────────────────────────────────────────────


class DeadLetterRecord(BaseModel):
    ts: str
    request_id: str
    agent: str
    action: str
    args_summary: str  # truncated to 200 chars
    error_class: str
    error_msg: str
    retries: int
    traceback: str


InboxEventCallback = Callable[[InboxEvent], None]


def _dead_letter_path() -> Path:
    return get_settings().state_dir / "dead_letter.jsonl"


def _append_dead_letter(record: DeadLetterRecord) -> None:
    path = _dead_letter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def _now_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


def _is_deterministic(exc: BaseException) -> bool:
    """Return True when exc should not be retried."""
    if isinstance(exc, _DETERMINISTIC_EXC):
        return True
    # HTTPException from fastapi — 4xx codes are operator errors, not transient
    try:
        from fastapi import HTTPException  # type: ignore[import-untyped]
        if isinstance(exc, HTTPException) and exc.status_code < 500:
            return True
    except ImportError:
        pass
    return False


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, _transient_types())


def _args_summary(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    raw = json.dumps(args, default=str)
    return raw[:200]


def _build_dead_letter(
    *,
    request_id: str,
    agent: str,
    action: str,
    args: dict[str, Any] | None,
    exc: BaseException,
    retries: int,
) -> DeadLetterRecord:
    return DeadLetterRecord(
        ts=_now_iso(),
        request_id=request_id,
        agent=agent,
        action=action,
        args_summary=_args_summary(args),
        error_class=type(exc).__name__,
        error_msg=str(exc),
        retries=retries,
        traceback=traceback.format_exc(),
    )


def _emit_crit_inbox(
    agent: str,
    action: str,
    retries: int,
    exc: BaseException,
    on_inbox_event: InboxEventCallback | None,
) -> None:
    if on_inbox_event is None:
        return
    summary = f"{agent}.{action} failed after {retries} retr{'y' if retries == 1 else 'ies'}: {exc}"
    event = InboxEvent(
        agent=agent,
        severity="crit",
        summary=summary[:300],
        ref={"error_class": type(exc).__name__},
    )
    try:
        on_inbox_event(event)
    except Exception:
        log.warning("on_inbox_event callback raised during supervisor crit emit", exc_info=True)


# ── Public API ────────────────────────────────────────────────────────────────

_MAX_RETRIES = 2
_BACKOFF_DELAYS_S = (0.2, 0.8)


class SupervisedFailure(Exception):
    """Raised when a supervised call exhausts retries or hits a deterministic error."""

    def __init__(self, reason: str, dead_letter_path: Path, record: DeadLetterRecord) -> None:
        super().__init__(reason)
        self.dead_letter_path = dead_letter_path
        self.record = record


def _run_with_supervision(
    *,
    fn: Callable[[], AgentResponse],
    agent: str,
    action: str,
    args: dict[str, Any] | None,
    request_id: str,
    on_inbox_event: InboxEventCallback | None,
) -> AgentResponse:
    """Core retry loop shared by supervise_call and supervise_call_text."""
    attempt = 0
    last_exc: BaseException | None = None

    while attempt <= _MAX_RETRIES:
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            if _is_deterministic(exc):
                log.debug(
                    "supervisor: deterministic error in %s.%s — skipping retry: %s",
                    agent, action, exc,
                )
                break
            if _is_transient(exc) and attempt < _MAX_RETRIES:
                delay = _BACKOFF_DELAYS_S[attempt]
                log.warning(
                    "supervisor: transient error in %s.%s (attempt %d/%d), retrying in %.1fs: %s",
                    agent, action, attempt + 1, _MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
                attempt += 1
                continue
            # Non-transient, non-deterministic (e.g. RuntimeError) — retry up to limit
            if attempt < _MAX_RETRIES:
                delay = _BACKOFF_DELAYS_S[attempt]
                log.warning(
                    "supervisor: error in %s.%s (attempt %d/%d), retrying in %.1fs: %s",
                    agent, action, attempt + 1, _MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
                attempt += 1
                continue
            break

    # Dead-letter path
    assert last_exc is not None
    record = _build_dead_letter(
        request_id=request_id,
        agent=agent,
        action=action,
        args=args,
        exc=last_exc,
        retries=attempt,
    )
    _append_dead_letter(record)
    _emit_crit_inbox(agent, action, attempt, last_exc, on_inbox_event)
    log.error(
        "supervisor: %s.%s dead-lettered after %d retries: %s",
        agent, action, attempt, last_exc,
    )
    raise SupervisedFailure(
        reason=str(last_exc),
        dead_letter_path=_dead_letter_path(),
        record=record,
    ) from last_exc


def supervise_call(
    reg: Any,
    agent: str,
    action: str,
    args: dict[str, Any] | None = None,
    request_id: str | None = None,
    on_inbox_event: InboxEventCallback | None = None,
) -> AgentResponse:
    """Call reg[agent].call(action, args) with retry + dead-letter supervision."""
    rid = request_id or uuid4().hex[:12]
    desc = reg[agent]
    return _run_with_supervision(
        fn=lambda: desc.call(action, args),
        agent=agent,
        action=action,
        args=args,
        request_id=rid,
        on_inbox_event=on_inbox_event,
    )


def supervise_call_text(
    reg: Any,
    agent: str,
    text: str,
    request_id: str | None = None,
    on_inbox_event: InboxEventCallback | None = None,
) -> AgentResponse:
    """Call reg[agent].call_text(text) with retry + dead-letter supervision."""
    rid = request_id or uuid4().hex[:12]
    desc = reg[agent]
    return _run_with_supervision(
        fn=lambda: desc.call_text(text),
        agent=agent,
        action="call_text",
        args={"text": text[:200]},
        request_id=rid,
        on_inbox_event=on_inbox_event,
    )


# ── Dead-letter reader (for API endpoint) ────────────────────────────────────


def read_dead_letter(limit: int = 50) -> list[DeadLetterRecord]:
    """Return the most recent N dead-letter records (newest last)."""
    path = _dead_letter_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if limit else lines
    records: list[DeadLetterRecord] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(DeadLetterRecord(**json.loads(line)))
        except Exception:
            log.warning("supervisor: malformed dead-letter line skipped")
    return records
