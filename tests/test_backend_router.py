"""Tests for jarvis.llm.backend_router — per-agent backend selection."""
from __future__ import annotations

import pytest

from jarvis.llm import backend_router
from jarvis.llm.claude_backend import ClaudeBackend
from jarvis.llm.ollama_backend import OllamaBackend
from jarvis.llm.vllm_backend import VLLMBackend


@pytest.fixture(autouse=True)
def _clear_registry_and_env(monkeypatch: pytest.MonkeyPatch):
    """Each test starts with a clean registry + no backend env vars."""
    backend_router.reset_registry()
    for key in list(globals().get("__os_env__", {}) or {}):
        if key.startswith("JARVIS_LLM_BACKEND"):
            monkeypatch.delenv(key, raising=False)
    # Also explicitly clear the known names.
    for key in (
        "JARVIS_LLM_BACKEND",
        "JARVIS_LLM_BACKEND_JARVIS",
        "JARVIS_LLM_BACKEND_SENTINEL",
        "JARVIS_LLM_BACKEND_TEMPO",
        "JARVIS_VLLM_URL",
        "JARVIS_VLLM_MODEL",
        "JARVIS_OLLAMA_URL",
        "JARVIS_OLLAMA_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    backend_router.reset_registry()


# ---------------------------------------------------------------------------
# Default
# ---------------------------------------------------------------------------


def test_default_is_claude_backend() -> None:
    """With no env vars, every agent gets a ClaudeBackend."""
    assert isinstance(backend_router.get_backend_for_agent("jarvis"), ClaudeBackend)
    assert isinstance(backend_router.get_backend_for_agent("sentinel"), ClaudeBackend)


def test_default_backend_helper_returns_claude() -> None:
    assert isinstance(backend_router.get_default_backend(), ClaudeBackend)


# ---------------------------------------------------------------------------
# Global env override
# ---------------------------------------------------------------------------


def test_global_env_var_routes_all_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "ollama")
    assert isinstance(backend_router.get_backend_for_agent("jarvis"), OllamaBackend)
    assert isinstance(backend_router.get_backend_for_agent("sentinel"), OllamaBackend)


def test_global_env_var_vllm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "vllm")
    assert isinstance(backend_router.get_backend_for_agent("jarvis"), VLLMBackend)


def test_global_env_var_normalizes_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "Claude")
    assert isinstance(backend_router.get_backend_for_agent("jarvis"), ClaudeBackend)


def test_global_env_var_unknown_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown backend names log a warning and fall back to claude."""
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "not-a-real-backend")
    assert isinstance(backend_router.get_backend_for_agent("jarvis"), ClaudeBackend)


# ---------------------------------------------------------------------------
# Per-agent env override
# ---------------------------------------------------------------------------


def test_per_agent_env_var_wins_over_global(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "ollama")  # global
    monkeypatch.setenv("JARVIS_LLM_BACKEND_TEMPO", "vllm")  # per-agent
    assert isinstance(backend_router.get_backend_for_agent("tempo"), VLLMBackend)
    assert isinstance(backend_router.get_backend_for_agent("scholar"), OllamaBackend)


def test_per_agent_env_var_uses_uppercase_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env var name is built by uppercasing the agent string."""
    monkeypatch.setenv("JARVIS_LLM_BACKEND_SENTINEL", "ollama")
    assert isinstance(backend_router.get_backend_for_agent("sentinel"), OllamaBackend)


# ---------------------------------------------------------------------------
# Registry caching
# ---------------------------------------------------------------------------


def test_backend_instance_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated lookups return the same instance (connection pool reuse)."""
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "ollama")
    first = backend_router.get_backend_for_agent("jarvis")
    second = backend_router.get_backend_for_agent("scholar")
    assert first is second


def test_reset_registry_clears_cache() -> None:
    """``reset_registry`` is the test-only escape hatch."""
    first = backend_router.get_backend_for_agent("jarvis")
    backend_router.reset_registry()
    second = backend_router.get_backend_for_agent("jarvis")
    assert first is not second


def test_list_active_backends_empty_by_default() -> None:
    """No lookups yet → registry is empty."""
    assert backend_router.list_active_backends() == []


def test_list_active_backends_after_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND_TEMPO", "vllm")
    monkeypatch.setenv("JARVIS_LLM_BACKEND_SENTINEL", "ollama")
    backend_router.get_backend_for_agent("jarvis")
    backend_router.get_backend_for_agent("tempo")
    backend_router.get_backend_for_agent("sentinel")
    assert sorted(backend_router.list_active_backends()) == ["claude", "ollama", "vllm"]


# ---------------------------------------------------------------------------
# Custom URL/model env vars wire into the backend instance
# ---------------------------------------------------------------------------


def test_vllm_picks_up_custom_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "vllm")
    monkeypatch.setenv("JARVIS_VLLM_URL", "http://gpu-rig:8000/v1")
    monkeypatch.setenv("JARVIS_VLLM_MODEL", "Llama-3.3-70B")
    b = backend_router.get_backend_for_agent("jarvis")
    assert isinstance(b, VLLMBackend)
    assert b.config.url == "http://gpu-rig:8000/v1"
    assert b.config.model == "Llama-3.3-70B"


def test_ollama_picks_up_custom_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "ollama")
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://nas:11434/v1")
    monkeypatch.setenv("JARVIS_OLLAMA_MODEL", "llama3.2:3b")
    b = backend_router.get_backend_for_agent("jarvis")
    assert isinstance(b, OllamaBackend)
    assert b.config.url == "http://nas:11434/v1"
    assert b.config.model == "llama3.2:3b"
