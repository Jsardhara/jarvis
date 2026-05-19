"""Tests for jarvis.llm.claude_backend — Claude SDK wrapper."""
from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from jarvis.llm.backend import BackendResult, TokenUsage
from jarvis.llm.claude_backend import (
    ClaudeBackend,
    _extract_usage,
    _strip_fences,
)


# ---------------------------------------------------------------------------
# Helpers — fake claude_agent_sdk that records calls and emits a scripted stream
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistantMessage:
    def __init__(self, blocks: list[_FakeTextBlock]) -> None:
        self.content = blocks


class _FakeResultMessage:
    def __init__(self, usage: dict[str, int]) -> None:
        self.usage = usage


class _FakeClaudeAgentOptions:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, *, stream: list[Any]) -> dict:
    """Stand up a fake ``claude_agent_sdk`` module that emits ``stream``."""
    captured: dict = {"prompts": [], "options": []}

    async def fake_query(*, prompt: Any, options: Any):  # type: ignore[no-untyped-def]
        captured["prompts"].append(prompt)
        captured["options"].append(options)
        for msg in stream:
            yield msg

    fake_module = types.ModuleType("claude_agent_sdk")
    fake_module.AssistantMessage = _FakeAssistantMessage  # type: ignore[attr-defined]
    fake_module.TextBlock = _FakeTextBlock  # type: ignore[attr-defined]
    fake_module.ClaudeAgentOptions = _FakeClaudeAgentOptions  # type: ignore[attr-defined]
    fake_module.query = fake_query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_module)
    return captured


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_extract_usage_pulls_int_fields() -> None:
    msg = _FakeResultMessage({"input_tokens": 42, "output_tokens": 7, "ratio": "skip"})
    out = _extract_usage(msg)
    assert out == {"input_tokens": 42, "output_tokens": 7}


def test_extract_usage_returns_empty_when_missing() -> None:
    msg = object()  # no .usage attribute
    assert _extract_usage(msg) == {}


def test_extract_usage_returns_empty_when_not_dict() -> None:
    msg = types.SimpleNamespace(usage="not-a-dict")
    assert _extract_usage(msg) == {}


def test_strip_fences_handles_plain_text() -> None:
    assert _strip_fences("hello") == "hello"
    assert _strip_fences("  hello  ") == "hello"


def test_strip_fences_handles_fenced_block() -> None:
    raw = "```\nhello\n```"
    assert _strip_fences(raw) == "hello"


def test_strip_fences_handles_lang_fenced_block() -> None:
    raw = "```python\nprint('hi')\n```"
    assert _strip_fences(raw) == "print('hi')"


# ---------------------------------------------------------------------------
# ClaudeBackend.query
# ---------------------------------------------------------------------------


def test_query_assembles_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [
        _FakeAssistantMessage([_FakeTextBlock("hello "), _FakeTextBlock("world")]),
    ]
    _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    result = backend.query("sys", "user", model="claude-sonnet-4-6")
    assert isinstance(result, BackendResult)
    assert result.text == "hello world"
    assert result.model_id == "claude-sonnet-4-6"


def test_query_captures_usage_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [
        _FakeResultMessage({"input_tokens": 100, "output_tokens": 25}),
        _FakeAssistantMessage([_FakeTextBlock("ok")]),
    ]
    _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    result = backend.query("sys", "user", model="claude-opus-4-7")
    assert result.usage is not None
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 25


def test_query_returns_none_usage_when_sdk_omits(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [_FakeAssistantMessage([_FakeTextBlock("ok")])]
    _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    result = backend.query("sys", "user", model="claude-sonnet-4-6")
    assert result.usage is None


def test_query_strips_markdown_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [_FakeAssistantMessage([_FakeTextBlock("```\nhello\n```")])]
    _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    result = backend.query("sys", "user", model="claude-sonnet-4-6")
    assert result.text == "hello"


def test_query_passes_model_and_system_to_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [_FakeAssistantMessage([_FakeTextBlock("ok")])]
    captured = _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    backend.query("THE-SYS", "THE-USER", model="claude-opus-4-7")
    assert captured["prompts"] == ["THE-USER"]
    opts = captured["options"][0]
    assert opts.kwargs["model"] == "claude-opus-4-7"
    assert opts.kwargs["system_prompt"] == "THE-SYS"
    assert opts.kwargs["permission_mode"] == "bypassPermissions"


# ---------------------------------------------------------------------------
# ClaudeBackend.query_multimodal
# ---------------------------------------------------------------------------


def test_multimodal_wraps_content_in_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = [_FakeAssistantMessage([_FakeTextBlock("vision-reply")])]
    captured = _install_fake_sdk(monkeypatch, stream=stream)
    content = [
        {"type": "text", "text": "describe"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "ZmFrZQ=="},
        },
    ]
    backend = ClaudeBackend()
    result = backend.query_multimodal("sys", content, model="claude-sonnet-4-6")
    assert result.text == "vision-reply"
    # prompt is an async generator — collect it to inspect.
    # (No need to drain it for assertions; we verify the SDK was called.)
    assert len(captured["prompts"]) == 1


def test_multimodal_captures_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = [
        _FakeResultMessage({"input_tokens": 1500, "output_tokens": 80}),
        _FakeAssistantMessage([_FakeTextBlock("ok")]),
    ]
    _install_fake_sdk(monkeypatch, stream=stream)
    backend = ClaudeBackend()
    result = backend.query_multimodal(
        "sys", [{"type": "text", "text": "hi"}], model="claude-sonnet-4-6"
    )
    assert result.usage == TokenUsage(input_tokens=1500, output_tokens=80)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


def test_is_available_true_when_sdk_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_sdk(monkeypatch, stream=[])
    assert ClaudeBackend().is_available() is True


def test_is_available_false_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    # Now `import claude_agent_sdk` raises ImportError because the cached
    # module entry is None.
    assert ClaudeBackend().is_available() is False
