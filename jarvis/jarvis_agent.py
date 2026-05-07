"""Jarvis chatbot — Sonnet/Opus auto-routing with the OpenClaw soul.

Wraps the claude-agent-sdk ``ClaudeSDKClient``. Each user turn is routed
through ``jarvis.model_router.decide_model`` to either:

    Sonnet 4.6  — chitchat, lookups, short turns. Lite soul.
    Opus 4.7    — heavy tasks, code, sensitive actions. Full soul.

A ``/opus `` or ``/sonnet `` prefix forces the lane.

Two persistent SDK clients are held side-by-side; each owns its own
session so prompt caching stays warm. When routing flips lanes between
turns, a brief recap of the last 3 turn pairs is prepended to the new
lane's first call so Jarvis doesn't appear to forget what just happened.

Streaming
---------
``JarvisChat.stream(message)`` yields a sequence of typed events the web
layer turns into SSE frames:

    {"type": "model",       "model": "...", "reason": "...", "tier": int, "manual": bool}
    {"type": "text",        "delta": "...token..."}
    {"type": "tool_use",    "agent": "tempo", "action": "today", "args": {...}, "tool_use_id": "..."}
    {"type": "tool_result", "tool_use_id": "...", "is_error": bool, "text": "..."}
    {"type": "done",        "duration_ms": int, "is_error": bool, "total_cost_usd": float, ...}
    {"type": "error",       "message": "..."}
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)

from jarvis.model_router import (
    DEFAULT_OPUS_ID,
    DEFAULT_SONNET_ID,
    RouteDecision,
    decide_model,
)
from jarvis.subsystems.registry import AgentDescriptor, build_default_registry

logger = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_OPUS_ID  # back-compat alias
SOUL_FULL = "jarvis_soul.md"
SOUL_LITE = "jarvis_soul_lite.md"

_RECAP_TURN_PAIRS = 3
_RECAP_MAX_CHARS = 800
_TURN_LOG_MAX = 12  # 6 user + 6 assistant
_TURN_LOG_PATH = Path("state/jarvis_turn_log.json")
_SEMANTIC_RECAP_TOP_K = 3
_SEMANTIC_MIN_SCORE = 0.4
_SEMANTIC_MAX_CHARS = 120  # per hit in recap


# ---------- Turn-log persistence ----------


def _load_turn_log() -> list[dict[str, str]]:
    """Restore prior conversation turns from disk so memory survives restarts."""
    if not _TURN_LOG_PATH.exists():
        return []
    try:
        raw = json.loads(_TURN_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("turn-log read failed (%s); starting empty", exc)
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw[-_TURN_LOG_MAX:]:
        if isinstance(entry, dict) and isinstance(entry.get("role"), str) and isinstance(entry.get("text"), str):
            out.append({"role": entry["role"], "text": entry["text"]})
    return out


def _save_turn_log(turns: list[dict[str, str]]) -> None:
    """Persist the rolling turn log to disk (atomic write)."""
    try:
        _TURN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _TURN_LOG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(turns, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_TURN_LOG_PATH)
    except OSError as exc:
        logger.warning("turn-log write failed: %s", exc)


# ---------- Soul loader ----------


def load_soul(variant: str = "full") -> str:
    """Read the soul markdown for the given variant.

    ``variant="full"`` → opus lane (full doctrine).
    ``variant="lite"`` → sonnet lane (identity + tone + tool contract only).
    """
    filename = SOUL_FULL if variant == "full" else SOUL_LITE
    here = Path(__file__).parent / "personas" / filename
    return here.read_text(encoding="utf-8")


# ---------- Tool definitions ----------


_AGENT_DESCRIPTIONS = {
    "tempo": (
        "Gmail (+optional Drexel) for mail, iCloud for calendar + reminders + tasks. "
        "Actions: triage (unread only), list_recent_mail (latest read+unread), "
        "search_mail (args: query, max_results — searches subject/body/from across all mail, "
        "use this when the user names a topic like 'email about exam change'), "
        "draft_reply, send_mail, today, find_free, schedule, cancel, add, list_open, complete."
    ),
    "scholar": (
        "Academics + study planning. Actions: list_assignments, add_assignment, "
        "plan_week, summarize."
    ),
    "lens": (
        "Web research + monitoring. Actions: quick_search, deep_research, monitor."
    ),
    "forge": (
        "Code-work delegation (open PRs, run agents on the codebase). "
        "Actions: execute (args: repo, task, push)."
    ),
    "atlas": (
        "Trading orchestrator (Oracle/Architect/Guardian/Trader/Sage). Actions: "
        "portfolio, positions, pnl, oracle_scan, architect_rank, guardian_check, "
        "trader_execute, trader_execute_confirmed, sage_review, pipeline."
    ),
}

_RECALL_DESCRIPTION = (
    "Semantic long-term chat memory. "
    "Use JarvisChat.semantic_search(query, top_k) to find relevant past turns. "
    "The orchestrator automatically surfaces relevant history during cross-lane recap."
)


def _build_delegate_tool(registry: dict[str, AgentDescriptor]):
    """Closure capturing the registry so the tool can dispatch to real agents."""

    @tool(
        "delegate",
        (
            "Hand a task to one of your subsystem agents. Tempo owns mail / "
            "calendar / reminders, Scholar owns academics, Lens owns research, "
            "Forge owns code work, Atlas owns trading. Returns the agent's "
            "response envelope as JSON."
        ),
        {
            "agent": str,
            "action": str,
            "args": dict,
        },
    )
    async def delegate(args: dict[str, Any]) -> dict[str, Any]:
        agent_name = str(args.get("agent", "")).lower()
        action = str(args.get("action", "")).strip()
        call_args = args.get("args") or {}
        if agent_name not in registry:
            return _err(
                f"unknown agent {agent_name!r}; choose tempo / scholar / lens / forge / atlas"
            )
        desc = registry[agent_name]
        if action not in desc.actions:
            return _err(
                f"unknown action {action!r} on {agent_name}; valid: "
                + ", ".join(sorted(desc.actions))
            )
        try:
            resp = desc.call(action, call_args)
        except Exception as exc:  # surface to model so it can recover
            return _err(f"{agent_name}.{action} raised: {exc}")
        return {
            "content": [
                {
                    "type": "text",
                    "text": resp.model_dump_json(),
                }
            ]
        }

    return delegate


def _err(msg: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": msg}],
        "is_error": True,
    }


# ---------- Streaming chat ----------


@dataclass
class StreamEvent:
    type: str
    payload: dict[str, Any]


# Type alias for an injectable model-router (used in tests).
RouteFn = Callable[[str], tuple[RouteDecision, str]]


class JarvisChat:
    """Two-client pool with per-turn routing + cross-lane recap.

    The ``model`` kwarg is preserved for back-compat: when explicitly set,
    routing is bypassed and every turn uses that model with the full soul.
    """

    def __init__(
        self,
        registry: dict[str, AgentDescriptor] | None = None,
        model: str | None = None,
        opus_model: str = DEFAULT_OPUS_ID,
        sonnet_model: str = DEFAULT_SONNET_ID,
        route: RouteFn | None = None,
    ):
        self._registry = registry or build_default_registry()
        self._opus_model = opus_model
        self._sonnet_model = sonnet_model
        self._forced_model = model  # if set, routing is bypassed
        self._route_fn = route or self._default_route
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._connected: set[str] = set()
        self._last_lane: str | None = None
        self._turn_log: list[dict[str, str]] = _load_turn_log()

    # ----- routing -----

    def _default_route(self, message: str) -> tuple[RouteDecision, str]:
        return decide_model(message, opus_id=self._opus_model, sonnet_id=self._sonnet_model)

    # ----- soul + client construction -----

    def _system_for(self, model: str) -> str:
        variant = "full" if model == self._opus_model else "lite"
        soul = load_soul(variant)
        agents_block = "\n".join(
            f"- **{name}** — {desc}" for name, desc in _AGENT_DESCRIPTIONS.items()
        )
        addendum = (
            "\n\n---\n\n## Tool use\n\n"
            "You have one tool, `delegate(agent, action, args)`. Use it to dispatch "
            "to your team. Available agents and their actions:\n\n"
            f"{agents_block}\n\n"
            "When a request needs an agent, call `delegate` and synthesize the "
            "response for Jyot. Do not pretend to act on his behalf without "
            "actually calling the tool.\n\n"
            "## Semantic memory\n\n"
            f"{_RECALL_DESCRIPTION}\n"
            "Relevant past turns are automatically prepended to your context when "
            "switching model lanes. You do not need to call a tool for recall — "
            "the relevant history appears in the recap block above the current message."
        )
        return soul + addendum

    def _build_client_for(self, model: str) -> ClaudeSDKClient:
        if model in self._clients:
            return self._clients[model]
        delegate = _build_delegate_tool(self._registry)
        srv = create_sdk_mcp_server(name="jarvis-team", version="0.1.0", tools=[delegate])
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=self._system_for(model),
            mcp_servers={"jarvis-team": srv},
            allowed_tools=["mcp__jarvis-team__delegate"],
            permission_mode="bypassPermissions",
        )
        client = ClaudeSDKClient(options=opts)
        self._clients[model] = client
        return client

    # ----- recap -----

    def _recap(self, upcoming_message: str | None = None) -> str | None:
        """Return a short context recap of the last few turn pairs, or None.

        If *upcoming_message* is provided, up to ``_SEMANTIC_RECAP_TOP_K``
        semantically relevant past turns (score > _SEMANTIC_MIN_SCORE) are
        appended after the recent-pairs block.  Each hit is capped at
        ``_SEMANTIC_MAX_CHARS`` characters and the total recap stays within
        ``_RECAP_MAX_CHARS``.
        """
        if not self._turn_log:
            return None
        # Take the last N user/assistant pairs
        pairs: list[tuple[str, str]] = []
        user_buf: str | None = None
        for entry in self._turn_log:
            if entry["role"] == "user":
                user_buf = entry["text"]
            elif entry["role"] == "assistant" and user_buf is not None:
                pairs.append((user_buf, entry["text"]))
                user_buf = None
        if not pairs:
            return None
        recent = pairs[-_RECAP_TURN_PAIRS:]
        lines = ["[Earlier in this thread, on a different model:]"]
        for u, a in recent:
            lines.append(f"- You said: {u.strip()[:200]}")
            lines.append(f"- I responded: {a.strip()[:200]}")
        recap = "\n".join(lines)
        recap = recap[:_RECAP_MAX_CHARS]

        # Augment with semantic hits when an upcoming message is known.
        if upcoming_message:
            semantic_lines = self._semantic_recap_lines(upcoming_message)
            if semantic_lines:
                budget = _RECAP_MAX_CHARS - len(recap)
                if budget > 40:
                    block = "\n".join(semantic_lines)
                    recap += "\n" + block[:budget]
        return recap

    def _semantic_recap_lines(self, query: str) -> list[str]:
        """Return formatted lines for semantic recall to embed in recap."""
        try:
            from .memory_index import search as _search

            hits = _search(query, top_k=_SEMANTIC_RECAP_TOP_K)
        except Exception as exc:
            logger.debug("semantic recap search failed: %s", exc)
            return []
        if not hits:
            return []
        lines = ["[Possibly relevant from earlier:]"]
        for score, turn in hits:
            if score < _SEMANTIC_MIN_SCORE:
                continue
            snippet = turn.text.strip().replace("\n", " ")[:_SEMANTIC_MAX_CHARS]
            lines.append(f"- [{turn.role}] {snippet}")
        return lines if len(lines) > 1 else []

    def _record_turn(self, role: str, text: str, lane: str | None = None) -> None:
        if not text:
            return
        self._turn_log.append({"role": role, "text": text})
        if len(self._turn_log) > _TURN_LOG_MAX:
            self._turn_log = self._turn_log[-_TURN_LOG_MAX:]
        _save_turn_log(self._turn_log)
        self._index_turn(role=role, text=text, lane=lane)

    def _index_turn(self, role: str, text: str, lane: str | None) -> None:
        """Persist turn to semantic index. Never raises — failures are warnings."""
        try:
            from datetime import UTC, datetime

            from .memory_index import IndexedTurn, append_turn, embed, turn_id_from_dict

            ts = datetime.now(UTC).isoformat()
            raw = {"role": role, "text": text, "ts": ts}
            tid = turn_id_from_dict(raw)
            vec = embed(text)
            turn = IndexedTurn(
                turn_id=tid,
                ts=ts,
                role=role,
                text=text,
                lane=lane,
                embedding=vec,
            )
            append_turn(turn)
        except Exception as exc:
            logger.warning("memory index write failed: %s", exc)

    # ----- public API -----

    async def connect(self, model: str | None = None) -> None:
        target = model or self._opus_model
        client = self._build_client_for(target)
        await client.connect()
        self._connected.add(target)

    async def close(self) -> None:
        for model, client in list(self._clients.items()):
            with suppress(Exception):
                await client.disconnect()
            self._connected.discard(model)
        self._clients.clear()

    def semantic_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Return top-K semantically similar past turns as plain dicts.

        Each item has: score (float), role, text, ts, lane.
        Returns an empty list when the memory index is unavailable.
        """
        try:
            from .memory_index import search as _search

            hits = _search(query, top_k=top_k)
        except Exception as exc:
            logger.warning("semantic_search failed: %s", exc)
            return []
        return [
            {
                "score": round(score, 6),
                "role": turn.role,
                "text": turn.text,
                "ts": turn.ts,
                "lane": turn.lane,
            }
            for score, turn in hits
        ]

    async def stream(self, message: str) -> AsyncIterator[StreamEvent]:
        """Send one user turn, yield events as Claude responds."""
        if self._forced_model is not None:
            decision = RouteDecision(
                model=self._forced_model,
                reason="explicit ctor model= override",
                tier=0,
                length_chars=len(message or ""),
                manual=False,
            )
            cleaned = (message or "").strip()
        else:
            decision, cleaned = self._route_fn(message)

        # Always emit the model decision first so the UI badges render
        # before any text streams.
        yield StreamEvent(
            "model",
            {
                "model": decision.model,
                "reason": decision.reason,
                "tier": decision.tier,
                "manual": decision.manual,
                "length_chars": decision.length_chars,
            },
        )

        client = self._build_client_for(decision.model)

        if decision.model not in self._connected:
            try:
                await client.connect()
            except Exception as exc:
                yield StreamEvent("error", {"message": f"connect failed: {exc}"})
                return
            self._connected.add(decision.model)

        prompt = cleaned
        if (
            self._last_lane is not None
            and self._last_lane != decision.model
            and not self._forced_model
        ):
            recap = self._recap(upcoming_message=cleaned)
            if recap:
                prompt = f"{recap}\n\n[Now Jyot says:]\n{cleaned}"

        try:
            await client.query(prompt)
        except Exception as exc:
            yield StreamEvent("error", {"message": f"query failed: {exc}"})
            return

        assistant_text_buf: list[str] = []
        try:
            async for sdk_msg in client.receive_response():
                async for ev in _convert_message(sdk_msg):
                    if ev.type == "text":
                        assistant_text_buf.append(str(ev.payload.get("delta", "")))
                    yield ev
        except Exception as exc:
            yield StreamEvent("error", {"message": f"stream error: {exc}"})
            return

        # Update lane + log AFTER the response completes successfully.
        self._last_lane = decision.model
        self._record_turn("user", cleaned, lane=decision.model)
        self._record_turn("assistant", "".join(assistant_text_buf), lane=decision.model)


async def _convert_message(msg: Any) -> AsyncIterator[StreamEvent]:
    """Translate an SDK message into one or more StreamEvents."""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                if block.text:
                    yield StreamEvent("text", {"delta": block.text})
            elif isinstance(block, ThinkingBlock):
                yield StreamEvent("thinking", {"delta": block.thinking})
            elif isinstance(block, ToolUseBlock):
                input_obj = block.input if isinstance(block.input, dict) else {}
                yield StreamEvent(
                    "tool_use",
                    {
                        "tool_use_id": block.id,
                        "name": block.name,
                        "agent": str(input_obj.get("agent", "")),
                        "action": str(input_obj.get("action", "")),
                        "args": input_obj.get("args") or {},
                    },
                )
        return

    if isinstance(msg, UserMessage):
        for block in msg.content if isinstance(msg.content, list) else []:
            if isinstance(block, ToolResultBlock):
                content = block.content
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts: list[str] = []
                    for piece in content:
                        if isinstance(piece, dict) and "text" in piece:
                            parts.append(str(piece["text"]))
                    text = "".join(parts)
                yield StreamEvent(
                    "tool_result",
                    {
                        "tool_use_id": block.tool_use_id,
                        "is_error": bool(block.is_error),
                        "text": text,
                    },
                )
        return

    if isinstance(msg, SystemMessage):
        return

    if isinstance(msg, ResultMessage):
        yield StreamEvent(
            "done",
            {
                "duration_ms": msg.duration_ms,
                "is_error": msg.is_error,
                "session_id": msg.session_id,
                "stop_reason": msg.stop_reason,
                "total_cost_usd": msg.total_cost_usd,
            },
        )
        return
