"""vLLM backend — stub for the OpenAI-compatible API exposed by vLLM.

Full implementation lands when the dual-3090 PC is online and a vLLM serving
process is reachable (default ``http://localhost:8000/v1``). Until then this
file provides:

* A working :py:meth:`VLLMBackend.is_available` health check so the router
  can detect when vLLM comes online without code changes.
* :py:meth:`VLLMBackend.query` / :py:meth:`VLLMBackend.query_multimodal` that
  raise :class:`NotImplementedError` with a clear message instead of silently
  pretending to work.

When the implementation lands it uses the OpenAI Python client pointed at
``self.url`` with ``api_key="not-needed"`` — vLLM doesn't auth by default
because it's local. Chat-completions for text; multimodal goes through the
OpenAI vision content-blocks shape (which differs from Anthropic's; the
backend will translate).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from jarvis.llm.backend import BackendResult

log = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:8000/v1"
_DEFAULT_MODEL = "Qwen/Qwen2.5-72B-Instruct-AWQ"
_HEALTH_TIMEOUT_SEC = 2.0


@dataclass(frozen=True)
class VLLMConfig:
    """vLLM connection config."""

    url: str = _DEFAULT_URL
    model: str = _DEFAULT_MODEL


class VLLMBackend:
    """Backend for vLLM over its OpenAI-compatible REST API.

    Stub: ``query`` / ``query_multimodal`` raise ``NotImplementedError`` until
    P3 lands the real client wiring. ``is_available`` is real today and lets
    the router check whether a vLLM serving process is reachable.
    """

    name = "vllm"

    def __init__(self, config: VLLMConfig | None = None) -> None:
        self.config = config or VLLMConfig()

    def query(
        self,
        system: str,
        user: str,
        *,
        model: str,
    ) -> BackendResult:
        raise NotImplementedError(
            "VLLMBackend.query is not implemented yet. "
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
            "VLLMBackend.query_multimodal is not implemented yet. "
            "Requires a vision-capable model (Qwen 2.5-VL or similar)."
        )

    def is_available(self) -> bool:
        """``GET /models`` with short timeout — cheap reachability probe."""
        try:
            r = httpx.get(f"{self.config.url}/models", timeout=_HEALTH_TIMEOUT_SEC)
        except (httpx.HTTPError, OSError) as exc:
            log.debug("vllm_backend: %s unreachable (%s)", self.config.url, exc)
            return False
        return r.status_code == 200
