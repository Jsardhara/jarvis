"""Tests for jarvis.llm.ollama_backend — stub + health check."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from jarvis.llm.ollama_backend import OllamaBackend, OllamaConfig


def test_query_raises_not_implemented() -> None:
    b = OllamaBackend()
    with pytest.raises(NotImplementedError, match="not implemented"):
        b.query("sys", "user", model="x")


def test_query_multimodal_raises_not_implemented() -> None:
    b = OllamaBackend()
    with pytest.raises(NotImplementedError, match="multimodal"):
        b.query_multimodal("sys", [{"type": "text", "text": "hi"}], model="x")


def test_default_config() -> None:
    """Defaults point at localhost:11434/v1 with qwen2.5:7b."""
    b = OllamaBackend()
    assert b.config.url == "http://localhost:11434/v1"
    assert b.config.model == "qwen2.5:7b"


def test_custom_config() -> None:
    cfg = OllamaConfig(url="http://nas:11434/v1", model="llama3.2:3b")
    b = OllamaBackend(config=cfg)
    assert b.config.url == "http://nas:11434/v1"
    assert b.config.model == "llama3.2:3b"


class _FakeResp:
    def __init__(self, status: int) -> None:
        self.status_code = status


def test_is_available_true_on_200() -> None:
    b = OllamaBackend()
    with patch("jarvis.llm.ollama_backend.httpx.get", return_value=_FakeResp(200)):
        assert b.is_available() is True


def test_is_available_false_on_404() -> None:
    b = OllamaBackend()
    with patch("jarvis.llm.ollama_backend.httpx.get", return_value=_FakeResp(404)):
        assert b.is_available() is False


def test_is_available_false_on_connection_error() -> None:
    b = OllamaBackend()

    def raise_conn(*_a: Any, **_kw: Any) -> Any:
        raise httpx.ConnectError("ollama not running")

    with patch("jarvis.llm.ollama_backend.httpx.get", side_effect=raise_conn):
        assert b.is_available() is False
