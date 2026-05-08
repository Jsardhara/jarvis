"""Tests for ``jarvis/voice/cheap_handler.py``.

Verifies the routing tiers:
  Tier 0 — local pattern (no LLM)
  Tier 1 — Haiku
  Tier 2 — Sonnet (escalation on heavy keywords)
  Tier 3 — full Orchestrator (state-changing dispatch keywords)
"""

from __future__ import annotations

from typing import Any

import pytest

from jarvis.voice import cheap_handler


@pytest.mark.asyncio
async def test_local_time_query_skips_llm(monkeypatch):
    """'what time is it' returns instantly with no Claude call."""
    submitted = []

    def _spy(**kwargs: Any) -> str:
        submitted.append(kwargs)
        return "should-not-fire"

    monkeypatch.setattr("jarvis.claude_queue.submit", _spy, raising=False)
    out = await cheap_handler.handle("what time is it")
    assert submitted == []
    body = out["responses"]["voice"]
    assert ":" in body["action"]  # 'It's H:MM AM/PM'
    assert out["source"] == "local"


@pytest.mark.asyncio
async def test_thanks_returns_silent_ack(monkeypatch):
    submitted = []
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: submitted.append(kw) or "x",
        raising=False,
    )
    out = await cheap_handler.handle("thanks")
    assert submitted == []
    assert out["responses"]["voice"]["action"] == ""


@pytest.mark.asyncio
async def test_status_query_uses_haiku(monkeypatch):
    captured = {}

    def _fake_submit(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "PnL is up about one percent today."

    monkeypatch.setattr("jarvis.claude_queue.submit", _fake_submit, raising=False)
    out = await cheap_handler.handle("what's my pnl today")
    assert captured["model"] == "claude-haiku-4-5"
    assert captured["max_tokens"] == 120
    assert "PnL" in out["responses"]["voice"]["action"]
    assert out["source"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_explain_query_escalates_to_sonnet(monkeypatch):
    captured = {}

    def _fake_submit(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "Because the trader was paused after a drawdown."

    monkeypatch.setattr("jarvis.claude_queue.submit", _fake_submit, raising=False)
    out = await cheap_handler.handle("explain why pnl is down")
    assert captured["model"] == "claude-sonnet-4-6"
    assert "Because" in out["responses"]["voice"]["action"]


@pytest.mark.asyncio
async def test_code_keyword_escalates_to_sonnet(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: captured.update(kw) or "Here's a refactor.",
        raising=False,
    )
    await cheap_handler.handle("code review this snippet")
    assert captured["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_dispatch_keyword_falls_through_to_orchestrator(monkeypatch):
    """Drafting / scheduling go through the full Orchestrator path."""
    submitted = []
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: submitted.append(kw) or "no",
        raising=False,
    )

    captured_text: list[str] = []

    async def _fake_dispatch(text: str) -> dict:
        captured_text.append(text)
        return {
            "responses": {"tempo": {"agent": "tempo", "action": "draft created"}},
            "needs_confirm": True,
        }

    class _FakeOrch:
        def __init__(self, reg: Any) -> None:
            pass

        async def dispatch(self, text: str) -> dict:
            return await _fake_dispatch(text)

    import sys
    import types

    fake_orch_mod = types.ModuleType("jarvis.orchestrator")
    fake_orch_mod.Orchestrator = _FakeOrch  # type: ignore[attr-defined]
    fake_reg_mod = types.ModuleType("jarvis.subsystems.registry")
    fake_reg_mod.build_default_registry = lambda: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jarvis.orchestrator", fake_orch_mod)
    monkeypatch.setitem(sys.modules, "jarvis.subsystems.registry", fake_reg_mod)

    out = await cheap_handler.handle("draft an email to the team about delays")
    assert submitted == []  # no Haiku/Sonnet shortcut call
    assert captured_text == ["draft an email to the team about delays"]
    assert out["needs_confirm"] is True
    assert out["source"] == "orchestrator"


@pytest.mark.asyncio
async def test_empty_text_returns_empty_response():
    out = await cheap_handler.handle("")
    assert out["responses"]["voice"]["action"] == ""
    assert out["source"] == "empty"


@pytest.mark.asyncio
async def test_claude_failure_returns_apology_not_crash(monkeypatch):
    def _boom(**kwargs: Any) -> str:
        raise RuntimeError("rate-limited")

    monkeypatch.setattr("jarvis.claude_queue.submit", _boom, raising=False)
    out = await cheap_handler.handle("what's my pnl today")
    assert "trouble" in out["responses"]["voice"]["action"].lower()


@pytest.mark.asyncio
async def test_repeat_replays_last_reply(monkeypatch):
    """'repeat' returns whatever was cached from the prior reply."""
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: "PnL is up.",
        raising=False,
    )
    cheap_handler._LAST_REPLY["text"] = ""  # reset state
    first = await cheap_handler.handle("what's my pnl")
    assert first["responses"]["voice"]["action"] == "PnL is up."

    second = await cheap_handler.handle("repeat")
    assert second["responses"]["voice"]["action"] == "PnL is up."
    assert second["source"] == "local"


@pytest.mark.asyncio
async def test_max_tokens_default_caps_response(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: captured.update(kw) or "ok",
        raising=False,
    )
    await cheap_handler.handle("how is everything")
    assert captured["max_tokens"] == cheap_handler.DEFAULT_MAX_TOKENS == 120
