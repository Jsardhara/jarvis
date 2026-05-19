"""Backend router — picks an LLM :class:`~jarvis.llm.backend.Backend` per agent.

This is the **backend** layer of routing (Claude vs vLLM vs Ollama), distinct
from :mod:`jarvis.llm.model_router` which picks the **model** within Claude
(Opus vs Sonnet) for chat-time tier escalation. The two are orthogonal — model
routing decides what *capability tier* the message needs, backend routing
decides what *engine* generates the tokens.

Precedence (first hit wins):

    1. ``JARVIS_LLM_BACKEND_<AGENT>`` env var (uppercased)
    2. ``JARVIS_LLM_BACKEND`` env var (global override)
    3. Per-agent config from ``config.toml`` (P3, not yet wired)
    4. Hard default: ``"claude"`` — today's behaviour, zero-risk fallback

Backends are cached in a module-level registry so repeated lookups are free
and downstream connection pooling (httpx clients on vLLM/Ollama) doesn't
fan out. :func:`reset_registry` exists for tests.
"""
from __future__ import annotations

import logging
import os

from jarvis.llm.backend import Backend
from jarvis.llm.claude_backend import ClaudeBackend

log = logging.getLogger(__name__)

_DEFAULT_BACKEND_NAME = "claude"
_VALID_BACKENDS = frozenset({"claude", "vllm", "ollama"})

_REGISTRY: dict[str, Backend] = {}


def _build(name: str) -> Backend:
    """Construct a fresh backend by name. Lazy imports keep stubs out of hot paths."""
    if name == "claude":
        return ClaudeBackend()
    if name == "vllm":
        from jarvis.llm.vllm_backend import VLLMBackend, VLLMConfig

        url = os.environ.get("JARVIS_VLLM_URL")
        model = os.environ.get("JARVIS_VLLM_MODEL")
        cfg = VLLMConfig(
            url=url or VLLMConfig().url,
            model=model or VLLMConfig().model,
        )
        return VLLMBackend(config=cfg)
    if name == "ollama":
        from jarvis.llm.ollama_backend import OllamaBackend, OllamaConfig

        url = os.environ.get("JARVIS_OLLAMA_URL")
        model = os.environ.get("JARVIS_OLLAMA_MODEL")
        cfg = OllamaConfig(
            url=url or OllamaConfig().url,
            model=model or OllamaConfig().model,
        )
        return OllamaBackend(config=cfg)
    raise ValueError(
        f"Unknown backend {name!r}. Valid values: {sorted(_VALID_BACKENDS)}"
    )


def _resolve_name(agent: str) -> str:
    """Pick a backend name for ``agent`` using env-var precedence."""
    per_agent_env = f"JARVIS_LLM_BACKEND_{agent.upper()}"
    name = os.environ.get(per_agent_env)
    if name:
        return _validate(name, source=per_agent_env)

    global_env = "JARVIS_LLM_BACKEND"
    name = os.environ.get(global_env)
    if name:
        return _validate(name, source=global_env)

    return _DEFAULT_BACKEND_NAME


def _validate(name: str, *, source: str) -> str:
    """Coerce + validate a backend name from an env var. Unknown → default + warn."""
    clean = name.strip().lower()
    if clean not in _VALID_BACKENDS:
        log.warning(
            "backend_router: %s=%r is not a valid backend (%s). Falling back to %s.",
            source,
            name,
            sorted(_VALID_BACKENDS),
            _DEFAULT_BACKEND_NAME,
        )
        return _DEFAULT_BACKEND_NAME
    return clean


def get_backend_for_agent(agent: str) -> Backend:
    """Return the :class:`Backend` instance to use for ``agent`` calls.

    Cached — repeated lookups return the same backend instance so any
    underlying connection pool (httpx) is reused.
    """
    name = _resolve_name(agent)
    backend = _REGISTRY.get(name)
    if backend is None:
        backend = _build(name)
        _REGISTRY[name] = backend
    return backend


def get_default_backend() -> Backend:
    """Backend for callers that don't specify an agent (legacy paths)."""
    return get_backend_for_agent("jarvis")


def reset_registry() -> None:
    """Clear the backend cache. Tests only — production never calls this."""
    _REGISTRY.clear()


def list_active_backends() -> list[str]:
    """Names of backends currently cached. Diagnostic helper for /health endpoints."""
    return sorted(_REGISTRY.keys())
