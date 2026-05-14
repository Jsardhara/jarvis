"""Tests for cross-surface memory recall (J2).

Covers:
- JarvisChat runs recap on the FIRST turn of a session (not just on lane switch).
- JarvisChat hydrates ``_turn_log`` from chat_turns.jsonl on init.
- Voice tier 1/2 reads unified chat_turns into its prompt context.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from jarvis.agent import JarvisChat, StreamEvent
from jarvis.state import chat_turns as chat_turns_mod
from jarvis.state.chat_turns import ChatTurnRecord, append_turn


class _FakeClient:
    """Minimal ClaudeSDKClient stand-in with a recorded query log."""

    def __init__(self, model: str, response_text: str = "ok"):
        self.model = model
        self.response_text = response_text
        self.queries: list[str] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        pass

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
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
def fake_pool(monkeypatch: pytest.MonkeyPatch) -> dict[str, _FakeClient]:
    """Patch _build_client_for so JarvisChat hands out FakeClient instances."""
    created: dict[str, _FakeClient] = {}

    def _factory(self: JarvisChat, model: str) -> _FakeClient:
        if model not in created:
            created[model] = _FakeClient(model)
            self._clients[model] = created[model]  # type: ignore[assignment]
        return created[model]

    monkeypatch.setattr(JarvisChat, "_build_client_for", _factory)
    return created


@pytest.fixture
def isolated_chat_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect chat_turns.jsonl + turn_log to a tmpdir, freeze live state."""
    store = tmp_path / "chat_turns.jsonl"
    monkeypatch.setattr(chat_turns_mod, "_default_path", lambda: store)

    # Block disk-side persistence + live state from leaking real state in.
    monkeypatch.setattr("jarvis.agent._save_turn_log", lambda turns: None)
    monkeypatch.setattr("jarvis.agent._load_turn_log", lambda: [])
    monkeypatch.setattr("jarvis.agent._build_live_state_block", lambda: "")
    return store


async def _collect(stream: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    out: list[StreamEvent] = []
    async for ev in stream:
        out.append(ev)
    return out


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recap_runs_on_first_turn_same_lane(
    fake_pool: dict[str, _FakeClient],
    isolated_chat_store: Path,
) -> None:
    """First turn must still see recap pulled from disk, not gated by lane switch."""
    # Seed the unified store with one prior turn so hydration has content.
    append_turn(
        ChatTurnRecord(
            user_id="default",
            turn_id="prior-1",
            user_text="i prefer dark roast coffee",
            assistant_text="noted — dark roast it is.",
            model="claude-sonnet-4-6",
            ts="2026-05-12T20:00:00+00:00",
            session_id="default",
            surface="chat",
        ),
        path=isolated_chat_store,
    )

    chat = JarvisChat(registry={})
    # _last_lane is None — this simulates the first turn of a fresh session.
    assert chat._last_lane is None  # type: ignore[attr-defined]

    await _collect(chat.stream("how's it going"))

    # Find the lane that was actually picked and inspect its prompt.
    assert fake_pool, "expected a client to have been built"
    queried = [c for c in fake_pool.values() if c.queries]
    assert queried, "no query was ever recorded"
    prompt = queried[0].queries[0]
    # Either header style is acceptable — what matters is that recap fired.
    assert (
        "Rolling thread context" in prompt
        or "Earlier in this thread" in prompt
    ), f"expected recap header in prompt; got: {prompt[:200]}"


def test_hydrate_from_chat_turns_on_init(
    isolated_chat_store: Path,
) -> None:
    """JarvisChat.__init__ should merge recent ChatTurnRecord rows into _turn_log."""
    seeded_texts = [f"text-{i}" for i in range(5)]
    for i, txt in enumerate(seeded_texts):
        append_turn(
            ChatTurnRecord(
                user_id="default",
                turn_id=f"t{i}",
                user_text=txt,
                assistant_text=f"reply-{i}",
                model="claude-sonnet-4-6",
                ts=f"2026-05-12T20:00:0{i}+00:00",
                session_id="default",
                surface="chat",
            ),
            path=isolated_chat_store,
        )

    chat = JarvisChat(registry={})
    captured_texts = [e["text"] for e in chat._turn_log]  # type: ignore[attr-defined]
    for txt in seeded_texts:
        assert txt in captured_texts, f"missing hydrated user text {txt!r}"


@pytest.mark.asyncio
async def test_voice_tier1_reads_chat_turns(
    monkeypatch: pytest.MonkeyPatch,
    isolated_chat_store: Path,
) -> None:
    """Voice Haiku path must surface prior chat_turns context in its prompt."""
    from jarvis.apps.voice import cheap_handler

    # Seed a turn that should appear in the prompt context.
    append_turn(
        ChatTurnRecord(
            user_id="default",
            turn_id="prior-voice",
            user_text="my favorite snack is almonds",
            assistant_text="got it — almonds noted.",
            model="claude-haiku-4-5",
            ts="2026-05-13T08:00:00+00:00",
            session_id="default",
            surface="voice",
        ),
        path=isolated_chat_store,
    )

    captured: dict[str, str] = {}

    def _fake_submit(**kw: Any) -> str:
        captured.update(kw)
        return "ok"

    monkeypatch.setattr("jarvis.llm.queue.submit", _fake_submit, raising=False)

    # cheap_handler.handle routes 'how are things' → Haiku tier 1.
    out = await cheap_handler.handle("how are things")
    assert out["source"] == cheap_handler.DEFAULT_HAIKU_MODEL
    system = captured.get("system", "")
    assert "almonds" in system or "Recent conversation" in system, (
        f"voice prompt should include chat_turns recap; got: {system[:400]}"
    )
