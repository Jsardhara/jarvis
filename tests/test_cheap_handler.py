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
    assert captured["user"] == "what's my pnl today"
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
async def test_dispatch_keyword_routes_to_jarvis_chat(monkeypatch):
    """State-changing utterances now hit the unified JarvisChat brain."""
    submitted = []
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: submitted.append(kw) or "no",
        raising=False,
    )

    captured_text: list[str] = []

    class _FakeChat:
        async def respond_single(self, text: str) -> dict:
            captured_text.append(text)
            return {
                "responses": {
                    "agent_brain": {
                        "agent": "jarvis-chat",
                        "action": "draft created",
                        "result": {"text": "draft created", "source": "jarvis-chat"},
                    },
                },
                "needs_confirm": False,
                "source": "jarvis-chat",
            }

    cheap_handler._JARVIS_CHAT_SINGLETON["instance"] = _FakeChat()

    try:
        out = await cheap_handler.handle("draft an email to the team about delays")
    finally:
        cheap_handler._JARVIS_CHAT_SINGLETON["instance"] = None

    assert submitted == []
    assert captured_text == ["draft an email to the team about delays"]
    assert out["source"] == "jarvis-chat"
    assert out["responses"]["agent_brain"]["action"] == "draft created"


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_orchestrator_when_chat_raises(monkeypatch):
    """If JarvisChat.respond_single blows up, voice still answers via legacy path."""
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: "x",
        raising=False,
    )

    class _BoomChat:
        async def respond_single(self, text: str) -> dict:
            raise RuntimeError("sdk crashed")

    cheap_handler._JARVIS_CHAT_SINGLETON["instance"] = _BoomChat()

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

    try:
        out = await cheap_handler.handle("draft an email to the team about delays")
    finally:
        cheap_handler._JARVIS_CHAT_SINGLETON["instance"] = None

    assert captured_text == ["draft an email to the team about delays"]
    assert out["source"] == "orchestrator"
    assert out["needs_confirm"] is True


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
async def test_haiku_call_passes_system_prompt(monkeypatch):
    """Brevity is now enforced by VOICE_SYSTEM_PROMPT, not a max_tokens cap."""
    captured = {}
    monkeypatch.setattr(
        "jarvis.claude_queue.submit",
        lambda **kw: captured.update(kw) or "ok",
        raising=False,
    )
    await cheap_handler.handle("how is everything")
    assert "chief of staff" in captured["system"].lower()
    assert "1-2 sentences" in captured["system"]
