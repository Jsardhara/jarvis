"""Tests for jarvis.supervisor — retry, dead-letter, inbox crit events."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.contract import AgentResponse, InboxEvent
from jarvis.supervisor import (
    SupervisedFailure,
    read_dead_letter,
    supervise_call,
    supervise_call_text,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _ok_response(agent: str = "tempo") -> AgentResponse:
    return AgentResponse(agent=agent, intent="test", action="done", result={"ok": True})


def _make_reg(agent: str, *, call_fn=None, call_text_fn=None) -> dict:
    """Build a minimal registry dict with a mock AgentDescriptor."""
    desc = MagicMock()
    desc.call = call_fn or MagicMock(return_value=_ok_response(agent))
    desc.call_text = call_text_fn or MagicMock(return_value=_ok_response(agent))
    return {agent: desc}


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch):
    """Redirect state_dir to a temp directory and clear the lru_cache."""
    import jarvis.supervisor as sup_mod
    from jarvis.config import get_settings

    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()
    # Also patch the module-level cache so calls inside supervisor pick up the new path
    monkeypatch.setattr(sup_mod, "_REQUESTS_EXC", None)
    monkeypatch.setattr(sup_mod, "_HTTPX_EXC", None)
    yield tmp_path
    get_settings.cache_clear()


# ── Core retry behaviour ──────────────────────────────────────────────────────


def test_transient_connection_error_retried_then_succeeds(tmp_state):
    """ConnectionError is transient — retried twice, then succeeds on third call."""
    call_count = 0

    def _flaky(*_args, **_kwargs) -> AgentResponse:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("network blip")
        return _ok_response()

    reg = _make_reg("tempo", call_fn=_flaky)
    inbox_cb = MagicMock()

    with patch("jarvis.supervisor.time.sleep"):
        result = supervise_call(reg, "tempo", "triage", {}, on_inbox_event=inbox_cb)

    assert result.action == "done"
    assert call_count == 3
    # No inbox event — call eventually succeeded
    inbox_cb.assert_not_called()


def test_value_error_no_retry_lands_in_dead_letter(tmp_state):
    """ValueError is deterministic — no retry, straight to dead-letter."""
    call_count = 0

    def _bad(*_args, **_kwargs) -> AgentResponse:
        nonlocal call_count
        call_count += 1
        raise ValueError("unknown action 'foo'")

    reg = _make_reg("scholar", call_fn=_bad)
    inbox_cb = MagicMock()

    with pytest.raises(SupervisedFailure) as exc_info:
        supervise_call(reg, "scholar", "foo", {}, on_inbox_event=inbox_cb)

    assert call_count == 1  # no retry
    sf = exc_info.value
    assert sf.record.error_class == "ValueError"
    assert sf.record.retries == 0

    # Dead-letter file written
    dl_path = tmp_state / "dead_letter.jsonl"
    assert dl_path.exists()
    records = read_dead_letter()
    assert len(records) == 1
    assert records[0].agent == "scholar"
    assert records[0].action == "foo"

    # Crit inbox event emitted
    inbox_cb.assert_called_once()
    evt: InboxEvent = inbox_cb.call_args[0][0]
    assert evt.severity == "crit"
    assert "scholar.foo" in evt.summary


def test_runtime_error_retried_once_then_dead_letter(tmp_state):
    """RuntimeError is non-transient, non-deterministic — retried up to MAX_RETRIES, then dead-lettered."""
    call_count = 0

    def _runtime(*_args, **_kwargs) -> AgentResponse:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("subsystem crashed")

    reg = _make_reg("lens", call_fn=_runtime)
    inbox_cb = MagicMock()

    with patch("jarvis.supervisor.time.sleep"), pytest.raises(SupervisedFailure) as exc_info:
        supervise_call(reg, "lens", "quick_search", {}, on_inbox_event=inbox_cb)

    # 1 initial + 2 retries = 3 total calls
    assert call_count == 3
    sf = exc_info.value
    assert sf.record.error_class == "RuntimeError"
    assert sf.record.retries == 2

    inbox_cb.assert_called_once()
    evt: InboxEvent = inbox_cb.call_args[0][0]
    assert evt.severity == "crit"


def test_dead_letter_file_is_append_only_and_parseable_jsonl(tmp_state):
    """Multiple failures produce valid JSONL — each line is parseable."""

    def _bad(*_args, **_kwargs) -> AgentResponse:
        raise ValueError("bad1")

    def _bad2(*_args, **_kwargs) -> AgentResponse:
        raise ValueError("bad2")

    reg1 = _make_reg("tempo", call_fn=_bad)
    reg2 = _make_reg("atlas", call_fn=_bad2)

    with patch("jarvis.supervisor.time.sleep"):
        with pytest.raises(SupervisedFailure):
            supervise_call(reg1, "tempo", "triage", {})
        with pytest.raises(SupervisedFailure):
            supervise_call(reg2, "atlas", "portfolio", {})

    dl_path = tmp_state / "dead_letter.jsonl"
    assert dl_path.exists()
    lines = [l.strip() for l in dl_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2

    for line in lines:
        parsed = json.loads(line)
        assert "ts" in parsed
        assert "agent" in parsed
        assert "error_class" in parsed

    records = read_dead_letter()
    assert {r.agent for r in records} == {"tempo", "atlas"}


def test_inbox_event_emitted_with_severity_crit(tmp_state):
    """Inbox callback is called with severity='crit' and agent name in summary."""

    def _fail(*_args, **_kwargs) -> AgentResponse:
        raise ValueError("exploded")

    reg = _make_reg("forge", call_fn=_fail)
    received: list[InboxEvent] = []

    with pytest.raises(SupervisedFailure):
        supervise_call(reg, "forge", "execute", {}, on_inbox_event=received.append)

    assert len(received) == 1
    evt = received[0]
    assert evt.severity == "crit"
    assert evt.agent == "forge"
    assert "forge.execute" in evt.summary


def test_supervise_call_text_success(tmp_state):
    """supervise_call_text returns response when no error."""
    reg = _make_reg("tempo")
    result = supervise_call_text(reg, "tempo", "check inbox")
    assert result.action == "done"


def test_supervise_call_text_value_error_dead_letters(tmp_state):
    """supervise_call_text deterministic error lands in dead-letter."""

    def _bad(text: str) -> AgentResponse:
        raise ValueError("no free text")

    reg = _make_reg("scholar", call_text_fn=_bad)
    inbox_cb = MagicMock()

    with pytest.raises(SupervisedFailure) as exc_info:
        supervise_call_text(reg, "scholar", "help", on_inbox_event=inbox_cb)

    sf = exc_info.value
    assert sf.record.action == "call_text"
    assert sf.record.error_class == "ValueError"
    inbox_cb.assert_called_once()


def test_read_dead_letter_empty_when_no_file(tmp_state):
    """read_dead_letter returns [] when dead_letter.jsonl does not exist."""
    records = read_dead_letter()
    assert records == []


def test_read_dead_letter_respects_limit(tmp_state):
    """read_dead_letter(limit=1) returns only the most recent record."""

    def _bad(*_args, **_kwargs) -> AgentResponse:
        raise ValueError("x")

    reg1 = _make_reg("tempo", call_fn=_bad)
    reg2 = _make_reg("atlas", call_fn=_bad)

    with pytest.raises(SupervisedFailure):
        supervise_call(reg1, "tempo", "triage", {})
    with pytest.raises(SupervisedFailure):
        supervise_call(reg2, "atlas", "portfolio", {})

    records = read_dead_letter(limit=1)
    assert len(records) == 1
    assert records[0].agent == "atlas"
