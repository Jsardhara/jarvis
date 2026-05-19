"""Tests for jarvis.llm.vllm_backend — stub + health check."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from jarvis.llm.vllm_backend import VLLMBackend, VLLMConfig


def test_query_raises_not_implemented() -> None:
    """The query method is a stub until the local PC lands."""
    b = VLLMBackend()
    with pytest.raises(NotImplementedError, match="not implemented"):
        b.query("sys", "user", model="x")


def test_query_multimodal_raises_not_implemented() -> None:
    b = VLLMBackend()
    with pytest.raises(NotImplementedError, match="multimodal"):
        b.query_multimodal("sys", [{"type": "text", "text": "hi"}], model="x")


def test_default_config() -> None:
    """Defaults point at localhost:8000/v1 with Qwen 72B."""
    b = VLLMBackend()
    assert b.config.url == "http://localhost:8000/v1"
    assert "Qwen" in b.config.model


def test_custom_config() -> None:
    cfg = VLLMConfig(url="http://other-host:9000/v1", model="my-model")
    b = VLLMBackend(config=cfg)
    assert b.config.url == "http://other-host:9000/v1"
    assert b.config.model == "my-model"


class _FakeResp:
    def __init__(self, status: int) -> None:
        self.status_code = status


def test_is_available_true_on_200() -> None:
    b = VLLMBackend()
    with patch("jarvis.llm.vllm_backend.httpx.get", return_value=_FakeResp(200)):
        assert b.is_available() is True


def test_is_available_false_on_5xx() -> None:
    b = VLLMBackend()
    with patch("jarvis.llm.vllm_backend.httpx.get", return_value=_FakeResp(503)):
        assert b.is_available() is False


def test_is_available_false_on_connection_error() -> None:
    b = VLLMBackend()

    def raise_conn(*_a: Any, **_kw: Any) -> Any:
        raise httpx.ConnectError("nope")

    with patch("jarvis.llm.vllm_backend.httpx.get", side_effect=raise_conn):
        assert b.is_available() is False


def test_is_available_false_on_os_error() -> None:
    """DNS/socket failures bubble as OSError; we swallow them."""
    b = VLLMBackend()

    def raise_os(*_a: Any, **_kw: Any) -> Any:
        raise OSError("getaddrinfo failed")

    with patch("jarvis.llm.vllm_backend.httpx.get", side_effect=raise_os):
        assert b.is_available() is False
