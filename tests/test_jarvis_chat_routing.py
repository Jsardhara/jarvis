"""Tests for JarvisChat routing + recap behavior.

Stubs the SDK client so we don't hit Claude. Verifies:
- stream() emits a "model" event before any text
- two-client pool builds each model once
- recap is injected on lane switch, not on same-lane turns
- legacy ctor model="..." bypasses routing
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from jarvis import jarvis_agent
from jarvis.jarvis_agent import JarvisChat, StreamEvent
from jarvis.model_router import (
    DEFAULT_OPUS_ID,
    DEFAULT_SONNET_ID,
    RouteDecision,
)


class _FakeClient:
    """Minimal ClaudeSDKClient stand-in with a recorded query log."""

    def __init__(self, model: str, response_text: str = "ok"):
        self.model = model
        self.response_text = response_text
        self.queries: list[str] = []
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
        # Yield one fake AssistantMessage-like object containing a single TextBlock.
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        yield AssistantMessage(
            content=[TextBlock(text=self.response_text)],
            model=self.model,
            parent_tool_use_id=None,
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=42,
            duration_api_ms=42,
            is_error=False,
            num_turns=1,
            session_id="sess",
            total_cost_usd=0.001,
        )


@pytest.fixture
def fake_pool(monkeypatch):
    """Patch _build_client_for so JarvisChat hands out FakeClient instances."""
    created: dict[str, _FakeClient] = {}

    def _factory(self, model: str) -> _FakeClient:
        if model not in created:
            created[model] = _FakeClient(model)
            # Mirror the real impl: cache on the chat instance too
            self._clients[model] = created[model]
        return created[model]

    monkeypatch.setattr(JarvisChat, "_build_client_for", _factory)
    return created


@pytest.fixture
def chat(fake_pool):
    # Skip registry construction (build_default_registry hits real subsystems
    # which load env-driven providers); inject an empty dict.
    return JarvisChat(registry={})


# ---------- collect helper ----------


async def _collect(stream) -> list[StreamEvent]:
    out = []
    async for ev in stream:
        out.append(ev)
    return out


# ---------- tests ----------


@pytest.mark.asyncio
async def test_first_event_is_model_decision(chat):
    events = await _collect(chat.stream("hey jarvis"))
    assert events[0].type == "model"
    assert events[0].payload["model"] == DEFAULT_SONNET_ID
    assert events[0].payload["manual"] is False


@pytest.mark.asyncio
async def test_short_greeting_routes_to_sonnet_lane(chat, fake_pool):
    await _collect(chat.stream("hi"))
    assert DEFAULT_SONNET_ID in fake_pool
    assert DEFAULT_OPUS_ID not in fake_pool


@pytest.mark.asyncio
async def test_heavy_keyword_routes_to_opus_lane(chat, fake_pool):
    await _collect(chat.stream("refactor the orchestrator dispatch flow"))
    assert DEFAULT_OPUS_ID in fake_pool
    assert DEFAULT_SONNET_ID not in fake_pool


@pytest.mark.asyncio
async def test_pool_reuses_client_on_same_lane(chat, fake_pool):
    await _collect(chat.stream("hi"))
    await _collect(chat.stream("thanks"))
    # Both turns hit sonnet; only one fake client created.
    assert len(fake_pool) == 1
    sonnet = fake_pool[DEFAULT_SONNET_ID]
    assert len(sonnet.queries) == 2


@pytest.mark.asyncio
async def test_recap_injected_on_lane_switch(chat, fake_pool):
    # Sonnet first
    await _collect(chat.stream("hello"))
    # Then opus (heavy keyword forces the switch)
    await _collect(chat.stream("now refactor that"))

    opus = fake_pool[DEFAULT_OPUS_ID]
    # Opus's first prompt must contain the recap header AND the new message
    prompt = opus.queries[0]
    assert "Earlier in this thread" in prompt
    assert "now refactor that" in prompt


@pytest.mark.asyncio
async def test_no_recap_on_same_lane_turn(chat, fake_pool):
    await _collect(chat.stream("hi"))
    await _collect(chat.stream("ok thanks"))
    sonnet = fake_pool[DEFAULT_SONNET_ID]
    # Second sonnet query is the bare message — no recap
    assert "Earlier in this thread" not in sonnet.queries[1]


@pytest.mark.asyncio
async def test_manual_override_event_marked_manual(chat):
    events = await _collect(chat.stream("/opus what time is it"))
    model_event = next(e for e in events if e.type == "model")
    assert model_event.payload["model"] == DEFAULT_OPUS_ID
    assert model_event.payload["manual"] is True


@pytest.mark.asyncio
async def test_legacy_ctor_model_bypasses_routing(fake_pool, monkeypatch):
    chat = JarvisChat(registry={}, model=DEFAULT_OPUS_ID)
    # Even a short greeting routes to opus when ctor model= is set
    events = await _collect(chat.stream("hi"))
    model_event = next(e for e in events if e.type == "model")
    assert model_event.payload["model"] == DEFAULT_OPUS_ID
    assert model_event.payload["reason"].startswith("explicit ctor")


@pytest.mark.asyncio
async def test_custom_route_function_overrides_default(fake_pool):
    forced = (
        RouteDecision(
            model=DEFAULT_OPUS_ID,
            reason="test override",
            tier=1,
            length_chars=2,
            manual=False,
        ),
        "hi",
    )
    chat = JarvisChat(registry={}, route=lambda _msg: forced)
    events = await _collect(chat.stream("hi"))
    assert next(e for e in events if e.type == "model").payload["reason"] == "test override"


def test_load_soul_lite_returns_short_text():
    full = jarvis_agent.load_soul("full")
    lite = jarvis_agent.load_soul("lite")
    assert len(lite) < len(full)
    assert "Jarvis" in lite
