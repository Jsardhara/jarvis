"""Backend protocol for LLM calls.

Defines the contract every LLM backend (Claude SDK, vLLM, Ollama, ...) implements
so the rest of Jarvis stays agnostic about which engine generates tokens.

Two methods cover every current call site:

* :py:meth:`Backend.query` — one-shot text turn.
* :py:meth:`Backend.query_multimodal` — one-shot turn with Anthropic-format
  content blocks (text + image + document mix).

Each returns a :class:`BackendResult` carrying the assembled text plus optional
:class:`TokenUsage` for cost telemetry. The wrapping client adapter
(:mod:`jarvis.llm.client`) unpacks ``result.text`` so callers that expect a
``str`` keep working unchanged.

Streaming is intentionally out of scope here — :mod:`jarvis.agent` still owns
the streaming Claude path directly. A streaming abstraction lands in a later
phase once the one-shot path is proven through the migration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TokenUsage:
    """Token counts surfaced by a backend when it can report them.

    Backends that cannot report usage (most local backends today) leave the
    ``BackendResult.usage`` field as ``None`` and the cost tracker falls back
    to a char-count heuristic — matching today's behaviour.
    """

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class BackendResult:
    """Result of a single LLM call."""

    text: str
    usage: TokenUsage | None = None
    model_id: str = ""


@runtime_checkable
class Backend(Protocol):
    """Protocol every LLM backend implements.

    ``name`` is a short stable identifier ("claude", "vllm", "ollama", ...)
    used by the router and the cost log. ``model`` on each call is the model
    id the caller requested; backends are free to map it to a native id or
    ignore it in favour of an instance-bound default (the vLLM/Ollama
    pattern, where the serving process is dedicated to one model at a time).
    """

    name: str

    def query(
        self,
        system: str,
        user: str,
        *,
        model: str,
    ) -> BackendResult:
        """One-shot text turn. Synchronous, blocking."""
        ...

    def query_multimodal(
        self,
        system: str,
        content: list[dict],
        *,
        model: str,
    ) -> BackendResult:
        """One-shot multimodal turn.

        ``content`` is a list of Anthropic-format content blocks
        (text / image / document). Backends without native multimodal
        support raise :class:`NotImplementedError`.
        """
        ...

    def is_available(self) -> bool:
        """Health check — can this backend serve a request right now?

        Used by the router to fall back gracefully when the configured
        backend is offline. Implementations should be cheap (sub-second)
        and never raise.
        """
        ...
