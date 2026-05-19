"""Ollama backend — stub for Ollama's OpenAI-compatible API.

Ollama exposes a Chat Completions endpoint at ``http://localhost:11434/v1``
that is API-compatible with the OpenAI Python client. This stub provides a
real health check and ``NotImplementedError`` placeholders for the call
methods; the call implementation lands alongside vLLM when the new PC is up.

Intended use on the dual-3090 PC: serve the sentinel tier (Haiku-equivalent)
7B model and any vision/embedding sidecars. The primary brain stays on vLLM.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from jarvis.llm.backend import BackendResult

log = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "qwen2.5:7b"
_HEALTH_TIMEOUT_SEC = 2.0


@dataclass(frozen=True)
class OllamaConfig:
    """Ollama connection config."""

    url: str = _DEFAULT_URL
    model: str = _DEFAULT_MODEL


class OllamaBackend:
    """Backend for Ollama over its OpenAI-compatible REST API.

    Stub: ``query`` / ``query_multimodal`` raise ``NotImplementedError``.
    ``is_available`` is real and lets the router check reachability.
    """

    name = "ollama"

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()

    def query(
        self,
        system: str,
        user: str,
        *,
        model: str,
    ) -> BackendResult:
        raise NotImplementedError(
            "OllamaBackend.query is not implemented yet. "
            f"Configured url={self.config.url}, model={self.config.model}. "
            "Lands when the local PC is set up — see docs/JARVIS_2026_ROADMAP.md."
        )

    def query_multimodal(
        self,
        system: str,
        content: list[dict],
        *,
        model: str,
    ) -> BackendResult:
        raise NotImplementedError(
            "OllamaBackend.query_multimodal is not implemented yet. "
            "Requires a vision-capable model pulled into Ollama "
            "(qwen2.5-vl:7b or similar)."
        )

    def is_available(self) -> bool:
        """``GET /models`` with short timeout — cheap reachability probe."""
        try:
            r = httpx.get(f"{self.config.url}/models", timeout=_HEALTH_TIMEOUT_SEC)
        except (httpx.HTTPError, OSError) as exc:
            log.debug("ollama_backend: %s unreachable (%s)", self.config.url, exc)
            return False
        return r.status_code == 200
