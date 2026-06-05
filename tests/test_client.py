"""Direct tests for jarvis.llm.client -- the post-P1/P2 facade.

Most of client.py was previously exercised only indirectly via
test_claude_queue.py and test_cost_backend.py. These tests hit the public
surface directly with a stub Backend so we don't need claude_agent_sdk
installed and so the cost-logging path is verified end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.llm import client
from jarvis.llm.backend import BackendResult, TokenUsage


# ---------------------------------------------------------------------------
# Stub backend wired into the router
# ---------------------------------------------------------------------------


class _StubBackend:
    """In-memory backend that records calls + returns a canned reply."""

    def __init__(self, name: str = "stub", reply: str = "OK") -> None:
        self.name = name
        self.reply = reply
        self.usage: TokenUsage | None = TokenUsage(input_tokens=11, output_tokens=22)
        self.calls: list[dict] = []
        self.mm_calls: list[dict] = []

    def query(self, system: str, user: str, *, model: str) -> BackendResult:
        self.calls.append({"system": system, "user": user, "model": model})
        return BackendResult(text=self.reply, usage=self.usage, model_id=model)

    def query_multimodal(
        self, system: str, content: list[dict], *, model: str
    ) -> BackendResult:
        self.mm_calls.append({"system": system, "content": content, "model": model})
        return BackendResult(text=self.reply, usage=self.usage, model_id=model)

    def is_available(self) -> bool:
        return True


@pytest.fixture
def stub_backend(monkeypatch: pytest.MonkeyPatch) -> _StubBackend:
    """Route every agent through a single recording stub backend."""
    backend = _StubBackend()
    monkeypatch.setattr(
        "jarvis.llm.backend_router.get_backend_for_agent",
        lambda agent: backend,
    )
    return backend


# ---------------------------------------------------------------------------
# query_claude_sync
# ---------------------------------------------------------------------------


def test_query_sync_calls_backend_with_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    out = client.query_claude_sync(
        "sys-prompt", "user-msg", model="claude-sonnet-4-6", agent="tempo"
    )
    assert out == "OK"
    assert len(stub_backend.calls) == 1
    assert stub_backend.calls[0]["system"] == "sys-prompt"
    assert stub_backend.calls[0]["user"] == "user-msg"
    assert stub_backend.calls[0]["model"] == "claude-sonnet-4-6"


def test_query_sync_records_cost_with_backend_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """A successful call appends one row to cost_log.jsonl tagged with backend.name."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    captured: list[dict] = []

    def fake_log_cost(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr("jarvis.llm.cost.log_cost", fake_log_cost)

    client.query_claude_sync("sys", "user", model="claude-opus-4-7", agent="atlas")

    assert len(captured) == 1
    row = captured[0]
    assert row["agent"] == "atlas"
    assert row["model"] == "claude-opus-4-7"
    assert row["backend"] == "stub"  # threaded from backend.name
    assert row["in_tokens"] == 11
    assert row["out_tokens"] == 22


def test_query_sync_falls_back_to_char_heuristic_when_usage_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """Backends without usage telemetry -> char-count heuristic kicks in."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    stub_backend.usage = None

    captured: list[dict] = []
    monkeypatch.setattr(
        "jarvis.llm.cost.log_cost", lambda **kw: captured.append(kw)
    )

    client.query_claude_sync("a" * 40, "b" * 80, model="m", agent="jarvis")

    assert len(captured) == 1
    # 4 chars/token -> 10 + 20 = 30 input tokens
    assert captured[0]["in_tokens"] == 30


def test_query_sync_swallows_cost_log_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """A failing log_cost must NOT block the LLM call from returning."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    def boom(**_kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr("jarvis.llm.cost.log_cost", boom)
    out = client.query_claude_sync("s", "u", agent="tempo")
    assert out == "OK"


# ---------------------------------------------------------------------------
# query_claude_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_async_returns_backend_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """Non-Claude backend in async path -> falls back to sync backend.query."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    out = await client.query_claude_async("sys", "user", agent="sentinel")
    assert out == "OK"
    assert len(stub_backend.calls) == 1


# ---------------------------------------------------------------------------
# query_multimodal_sync
# ---------------------------------------------------------------------------


def test_query_multimodal_sync_passes_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    content = [
        {"type": "text", "text": "describe"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "ZmFrZQ=="},
        },
    ]
    out = client.query_multimodal_sync("sys", content, model="m", agent="lens")
    assert out == "OK"
    assert len(stub_backend.mm_calls) == 1
    assert stub_backend.mm_calls[0]["content"] == content


def test_query_multimodal_sync_uses_first_text_block_for_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """The user-text heuristic for cost falls back to the first text block."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    stub_backend.usage = None  # force heuristic path
    captured: list[dict] = []
    monkeypatch.setattr(
        "jarvis.llm.cost.log_cost", lambda **kw: captured.append(kw)
    )

    content = [
        {"type": "image", "source": {}},
        {"type": "text", "text": "describe this please"},
    ]
    client.query_multimodal_sync("sys", content, agent="lens")
    assert captured[0]["in_tokens"] > 0  # heuristic produced a non-zero count


def test_query_multimodal_sync_empty_text_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_backend: _StubBackend
) -> None:
    """No text blocks at all -> heuristic still works (zero user_text contribution)."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    stub_backend.usage = None
    captured: list[dict] = []
    monkeypatch.setattr(
        "jarvis.llm.cost.log_cost", lambda **kw: captured.append(kw)
    )

    content = [{"type": "image", "source": {}}]
    client.query_multimodal_sync("system" * 10, content, agent="lens")
    assert len(captured) == 1
    # system contributes (~60 chars / 4 = 15 tokens) but no user text.
    assert captured[0]["in_tokens"] >= 1


# ---------------------------------------------------------------------------
# _first_text_block (pure helper)
# ---------------------------------------------------------------------------


def test_first_text_block_picks_first_text() -> None:
    content = [
        {"type": "image", "source": {}},
        {"type": "text", "text": "first"},
        {"type": "text", "text": "second"},
    ]
    assert client._first_text_block(content) == "first"


def test_first_text_block_handles_no_text() -> None:
    assert client._first_text_block([{"type": "image", "source": {}}]) == ""


def test_first_text_block_handles_malformed_entries() -> None:
    """Non-dict entries are skipped without raising."""
    content = ["not-a-dict", {"type": "text", "text": "hello"}]
    assert client._first_text_block(content) == "hello"


def test_first_text_block_handles_non_string_text() -> None:
    """text field present but not a string -> still returns empty."""
    content = [{"type": "text", "text": 123}]
    assert client._first_text_block(content) == ""


# ---------------------------------------------------------------------------
# _estimate_tokens (pure helper)
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty_returns_zero() -> None:
    assert client._estimate_tokens("") == 0


def test_estimate_tokens_floors_at_one() -> None:
    """Short input still produces at least 1 token (avoid 0-token cost rows)."""
    assert client._estimate_tokens("a") == 1


def test_estimate_tokens_roughly_4_chars_per_token() -> None:
    assert client._estimate_tokens("a" * 400) == 100
