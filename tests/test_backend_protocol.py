"""Tests for jarvis.llm.backend — Protocol + dataclasses."""
from __future__ import annotations

import pytest

from jarvis.llm.backend import Backend, BackendResult, TokenUsage


def test_token_usage_is_frozen() -> None:
    """TokenUsage should be immutable."""
    u = TokenUsage(input_tokens=10, output_tokens=20)
    assert u.input_tokens == 10
    assert u.output_tokens == 20
    with pytest.raises(Exception):
        u.input_tokens = 99  # type: ignore[misc]


def test_token_usage_defaults_to_zero() -> None:
    """Default TokenUsage represents 'unknown' as 0/0."""
    u = TokenUsage()
    assert u.input_tokens == 0
    assert u.output_tokens == 0


def test_backend_result_carries_text_and_usage() -> None:
    """BackendResult bundles the assembled text with optional usage."""
    r = BackendResult(
        text="hello",
        usage=TokenUsage(input_tokens=5, output_tokens=3),
        model_id="claude-sonnet-4-6",
    )
    assert r.text == "hello"
    assert r.usage is not None
    assert r.usage.output_tokens == 3
    assert r.model_id == "claude-sonnet-4-6"


def test_backend_result_usage_optional() -> None:
    """Backends without usage telemetry can omit it."""
    r = BackendResult(text="hello")
    assert r.usage is None
    assert r.model_id == ""


def test_backend_result_is_frozen() -> None:
    """BackendResult should be immutable."""
    r = BackendResult(text="hi")
    with pytest.raises(Exception):
        r.text = "bye"  # type: ignore[misc]


class _MinimalBackend:
    """Verifies the Protocol shape is satisfied by a plain class."""

    name = "minimal"

    def query(self, system: str, user: str, *, model: str) -> BackendResult:
        return BackendResult(text=f"{system}|{user}|{model}")

    def query_multimodal(
        self, system: str, content: list[dict], *, model: str
    ) -> BackendResult:
        return BackendResult(text=f"{system}|mm|{model}")

    def is_available(self) -> bool:
        return True


def test_minimal_class_satisfies_backend_protocol() -> None:
    """A plain class with the right methods is a valid Backend (structural typing)."""
    b: Backend = _MinimalBackend()
    out = b.query("sys", "user", model="m1")
    assert isinstance(out, BackendResult)
    assert out.text == "sys|user|m1"
    assert b.is_available() is True
