"""Jarvis chatbot — Sonnet/Opus auto-routing with the OpenClaw soul.

Wraps the claude-agent-sdk ``ClaudeSDKClient``. Each user turn is routed
through ``jarvis.llm.model_router.decide_model`` to either:

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
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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

from jarvis.agents.registry import AgentDescriptor, build_default_registry
from jarvis.llm.model_router import (
    DEFAULT_OPUS_ID,
    DEFAULT_SONNET_ID,
    RouteDecision,
    decide_model,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_OPUS_ID  # back-compat alias
SOUL_FULL = "jarvis_soul.md"
SOUL_LITE = "jarvis_soul_lite.md"

_RECAP_TURN_PAIRS = 3
_RECAP_SAME_LANE_PAIRS = 2  # briefer recap when staying on the same lane
_RECAP_MAX_CHARS = 800
_TURN_LOG_MAX = 100  # bumped from 12 so hydration from chat_turns.jsonl fits
# Anchor at the project root so the file resolves the same whether the
# importer is uvicorn (started from the repo root), the voice daemon
# (started from any cwd), or a test runner from `tests/`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TURN_LOG_PATH = _PROJECT_ROOT / "state" / "jarvis_turn_log.json"
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
    """Persist the rolling turn log to disk (atomic write).

    Runs the disk write on a background thread so the chat hot path
    doesn't block on fsync.
    """
    snapshot = list(turns)

    def _write() -> None:
        try:
            _TURN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _TURN_LOG_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_TURN_LOG_PATH)
        except OSError as exc:
            logger.warning("turn-log write failed: %s", exc)

    threading.Thread(target=_write, daemon=True).start()


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


def _build_live_state_block() -> str:
    """Render the per-turn live operator state block.

    The SDK client caches its system prompt at connect time, so this
    block has to ride along with each user message instead. Empty
    return when there's nothing fresh to share so the prompt stays terse.

    Known declarative facts (state/facts.jsonl) are appended below the
    live state so the model has a stable picture of operator preferences
    on every turn.
    """
    body = ""
    try:
        from jarvis.apps.voice.context_cache import load_voice_context, render_for_prompt

        body = render_for_prompt(load_voice_context())
        if body in ("(context empty)", "(context unavailable; respond conservatively)"):
            body = ""
    except Exception:  # noqa: BLE001 — never block chat on context-read failure
        body = ""

    facts_block = ""
    try:
        from jarvis.state.facts import read_facts, render_facts_for_prompt

        facts_block = render_facts_for_prompt(read_facts(limit=30))
    except Exception as exc:  # noqa: BLE001 — facts must never break chat
        logger.debug("facts block render skipped: %s", exc)
        facts_block = ""

    parts: list[str] = []
    if body:
        parts.append(
            "[LIVE OPERATOR STATE — refreshed this turn; trust this over older context]\n"
            f"{body}"
        )
    if facts_block:
        parts.append(facts_block)
    return "\n\n".join(parts)


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
        # Pull cross-surface history (voice + chat) from the unified store so
        # the FIRST turn of every session already has continuity.  Best-effort:
        # any failure leaves _turn_log as-is.
        self._hydrate_from_unified_store()

    # ----- init helpers -----

    def _hydrate_from_unified_store(self, limit: int = 50) -> None:
        """Merge recent ChatTurnRecord entries into ``_turn_log``.

        Dedupes against existing entries by ``(role, text)`` so a record
        already on disk in ``jarvis_turn_log.json`` isn't double-counted.
        Ordered oldest-first to match the rolling-log convention.
        """
        try:
            from jarvis.state.chat_turns import read_recent

            records = read_recent(user_id="default", limit=limit)
        except Exception as exc:  # noqa: BLE001 — never block init on memory read
            logger.debug("unified-store hydrate skipped: %s", exc)
            return
        if not records:
            return
        existing: set[tuple[str, str]] = {
            (e.get("role", ""), e.get("text", "")) for e in self._turn_log
        }
        hydrated: list[dict[str, str]] = []
        # ``read_recent`` returns chronological order (oldest-first).
        for rec in records:
            user_text = (rec.user_text or "").strip()
            asst_text = (rec.assistant_text or "").strip()
            if user_text and ("user", user_text) not in existing:
                hydrated.append({"role": "user", "text": user_text})
                existing.add(("user", user_text))
            if asst_text and ("assistant", asst_text) not in existing:
                hydrated.append({"role": "assistant", "text": asst_text})
                existing.add(("assistant", asst_text))
        if not hydrated:
            return
        merged = hydrated + self._turn_log
        if len(merged) > _TURN_LOG_MAX:
            merged = merged[-_TURN_LOG_MAX:]
        self._turn_log = merged

    # ----- routing -----

    def _default_route(self, message: str) -> tuple[RouteDecision, str]:
        return decide_model(message, opus_id=self._opus_model, sonnet_id=self._sonnet_model)

    # ----- soul + client construction -----

    def _system_for(self, model: str) -> str:
        from jarvis.apps.voice.persona import PERSONA

        variant = "full" if model == self._opus_model else "lite"
        soul = load_soul(variant)
        # Text channel — keep terse persona but allow markdown.
        chat_persona = (
            PERSONA
            + "\n\nText channel — markdown ok, but stay terse. "
            "Fragments fine when natural. Never lecture.\n\n"
        )
        agents_block = "\n".join(
            f"- **{name}** — {desc}" for name, desc in _AGENT_DESCRIPTIONS.items()
        )
        addendum = (
            "\n\n---\n\n## Tool use\n\n"
            "You have a real tool surface — use it instead of guessing.\n\n"
            "**Subsystem dispatch** — `delegate(agent, action, args)`. Use this to "
            "hand work to your team. Available agents and their actions:\n\n"
            f"{agents_block}\n\n"
            "**File system + shell** — `Read`, `Bash`, `Grep`, `Glob`. Use these to "
            "inspect the operator's repo, run commands, find files. Default cwd is "
            "`C:\\Users\\jyot2\\jarvis`.\n\n"
            "**Desktop GUI control** — `mcp__jarvis-desktop__desktop_*` tools "
            "(screenshot, list_windows, focus_window, click, type, press_key, "
            "scroll, drag, get_mouse_position, get_screen_size, move_mouse, "
            "double_click, right_click). When the operator asks 'what's on "
            "screen', call `desktop_screenshot` first — do not narrate from memory. "
            "When asked to click / type / press something, do it; don't ask for a "
            "JSON config file. Take a screenshot, identify coordinates, then act.\n\n"
            "Never fabricate tool capabilities or claim a tool isn't 'in your "
            "registry' — the tools above are wired in. If a call fails, surface "
            "the actual error, then retry or escalate.\n\n"
            "## Semantic memory\n\n"
            f"{_RECALL_DESCRIPTION}\n"
            "Relevant past turns are automatically prepended to your context when "
            "switching model lanes. You do not need to call a tool for recall — "
            "the relevant history appears in the recap block above the current message."
        )

        # Live operator state — tasks, mail, calendar, atlas health.
        # Re-read on every turn so newly-created tasks land in context
        # without daemon refresh.
        from jarvis.apps.voice.context_cache import load_voice_context, render_for_prompt

        live_state = render_for_prompt(load_voice_context())
        if live_state and live_state != "(context empty)":
            addendum += (
                "\n\n## Live operator state (refreshed each turn)\n\n"
                f"{live_state}\n"
            )

        return chat_persona + soul + addendum

    def _build_client_for(self, model: str) -> ClaudeSDKClient:
        if model in self._clients:
            return self._clients[model]
        delegate = _build_delegate_tool(self._registry)
        srv = create_sdk_mcp_server(name="jarvis-team", version="0.1.0", tools=[delegate])
        opts = ClaudeAgentOptions(
            model=model,
            system_prompt=self._system_for(model),
            mcp_servers={
                "jarvis-team": srv,
                "jarvis-desktop": {
                    "type": "stdio",
                    "command": "C:\\Python314\\python.exe",
                    "args": [
                        "C:\\Users\\jyot2\\jarvis\\jarvis\\tools\\desktop_mcp.py",
                    ],
                },
            },
            allowed_tools=[
                "mcp__jarvis-team__delegate",
                # GUI control via the Jarvis Desktop MCP
                "mcp__jarvis-desktop__desktop_screenshot",
                "mcp__jarvis-desktop__desktop_list_windows",
                "mcp__jarvis-desktop__desktop_focus_window",
                "mcp__jarvis-desktop__desktop_get_mouse_position",
                "mcp__jarvis-desktop__desktop_get_screen_size",
                "mcp__jarvis-desktop__desktop_move_mouse",
                "mcp__jarvis-desktop__desktop_click",
                "mcp__jarvis-desktop__desktop_double_click",
                "mcp__jarvis-desktop__desktop_right_click",
                "mcp__jarvis-desktop__desktop_drag",
                "mcp__jarvis-desktop__desktop_type",
                "mcp__jarvis-desktop__desktop_press_key",
                "mcp__jarvis-desktop__desktop_scroll",
                # File system + shell so Jarvis can actually inspect the repo
                "Read",
                "Bash",
                "Grep",
                "Glob",
            ],
            permission_mode="bypassPermissions",
            cwd="C:\\Users\\jyot2\\jarvis",
        )
        client = ClaudeSDKClient(options=opts)
        self._clients[model] = client
        return client

    # ----- recap -----

    def _recap(
        self,
        upcoming_message: str | None = None,
        *,
        lane_switch: bool = True,
    ) -> str | None:
        """Return a short context recap of the last few turn pairs, or None.

        ``lane_switch=True`` → full recap (last 3 pairs + top-3 semantic).
        ``lane_switch=False`` → brief recap (last 2 pairs + top-1 semantic),
        used when the same model lane carries forward so the model still
        sees rolling context on the first turn of a new session.

        If *upcoming_message* is provided, semantically relevant past turns
        (score > ``_SEMANTIC_MIN_SCORE``) are appended after the recent-pairs
        block. Each hit is capped at ``_SEMANTIC_MAX_CHARS`` characters and
        the total recap stays within ``_RECAP_MAX_CHARS``.
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
        pair_cap = _RECAP_TURN_PAIRS if lane_switch else _RECAP_SAME_LANE_PAIRS
        recent = pairs[-pair_cap:]
        header = (
            "[Earlier in this thread, on a different model:]"
            if lane_switch
            else "[Rolling thread context:]"
        )
        lines = [header]
        for u, a in recent:
            lines.append(f"- You said: {u.strip()[:200]}")
            lines.append(f"- I responded: {a.strip()[:200]}")
        recap = "\n".join(lines)
        recap = recap[:_RECAP_MAX_CHARS]

        # Augment with semantic hits when an upcoming message is known.
        if upcoming_message:
            top_k = _SEMANTIC_RECAP_TOP_K if lane_switch else 1
            semantic_lines = self._semantic_recap_lines(
                upcoming_message, top_k=top_k
            )
            if semantic_lines:
                budget = _RECAP_MAX_CHARS - len(recap)
                if budget > 40:
                    block = "\n".join(semantic_lines)
                    recap += "\n" + block[:budget]
        return recap

    def _semantic_recap_lines(
        self, query: str, *, top_k: int = _SEMANTIC_RECAP_TOP_K
    ) -> list[str]:
        """Return formatted lines for semantic recall to embed in recap."""
        try:
            from jarvis.state.memory_index import search as _search

            hits = _search(query, top_k=top_k)
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
        if role == "user":
            self._extract_and_persist_facts(text)
            self._mark_operator_present("chat")

    @staticmethod
    def _mark_operator_present(surface: str) -> None:
        """Record an operator-presence mark so sentinel can detect inactivity.

        Best-effort: failures are logged at debug and swallowed. Never let the
        presence hook break the chat hot path.
        """
        try:
            from jarvis.state.operator_presence import mark_present

            mark_present(surface)
        except Exception as exc:  # noqa: BLE001
            logger.debug("operator_presence mark skipped: %s", exc)

    @staticmethod
    def _extract_and_persist_facts(text: str) -> None:
        """Regex-extract declarative facts from a user turn; append to disk.

        Best-effort: any failure is logged at debug level and swallowed.
        Never lets fact capture break the chat hot path.
        """
        try:
            from jarvis.state.facts import append_fact, extract_facts
            from jarvis.state.memory_index import turn_id_from_dict

            tid = turn_id_from_dict({"role": "user", "text": text})
            for fact in extract_facts(text, turn_id=tid):
                append_fact(fact)
        except Exception as exc:  # noqa: BLE001 — facts must never break chat
            logger.debug("facts extract skipped: %s", exc)

    @staticmethod
    def _record_unified_turn(
        *,
        user_text: str,
        assistant_text: str,
        lane: str | None,
        surface: Literal["voice", "chat", "api"],
        session_id: str = "default",
        user_id: str = "default",
        turn_id: str | None = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Append a turn pair to the unified ``chat_turns.jsonl`` store.

        Called from voice paths (cheap_handler) AND from JarvisChat itself
        when invoked outside the HTTP layer, so the dashboard sees every
        turn regardless of surface. Best-effort: failures are warnings.
        """
        if not user_text and not assistant_text:
            return
        try:
            from datetime import UTC, datetime
            from uuid import uuid4

            from jarvis.state.chat_turns import ChatTurnRecord, append_turn

            rec = ChatTurnRecord(
                user_id=user_id,
                turn_id=turn_id or uuid4().hex,
                user_text=user_text,
                assistant_text=assistant_text,
                model=lane or "",
                cost_usd=cost_usd,
                ts=datetime.now(UTC).isoformat(),
                session_id=session_id,
                surface=surface,
            )
            append_turn(rec)
        except Exception as exc:  # noqa: BLE001
            logger.warning("unified turn write failed: %s", exc)

    def _index_turn(self, role: str, text: str, lane: str | None) -> None:
        """Persist turn to semantic index. Never raises — failures are warnings.

        Embedding is dispatched to a background thread so the chat hot path
        is never blocked on the model call or disk write.
        """
        def _run() -> None:
            try:
                from datetime import UTC, datetime

                from jarvis.state.memory_index import (
                    IndexedTurn,
                    append_turn,
                    embed,
                    turn_id_from_dict,
                )

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
            except Exception as exc:  # noqa: BLE001
                logger.warning("memory index write failed: %s", exc)

        threading.Thread(target=_run, daemon=True).start()

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
            from jarvis.state.memory_index import search as _search

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

    async def stream(
        self,
        message: str,
        *,
        surface: Literal["voice", "chat", "api"] = "api",
        session_id: str = "default",
    ) -> AsyncIterator[StreamEvent]:
        """Send one user turn, yield events as Claude responds.

        ``surface`` and ``session_id`` are stamped on the unified
        ``chat_turns.jsonl`` record written when the turn completes, so the
        dashboard can attribute turns to voice vs. chat vs. terminal.
        """
        # Short-circuit: message contains a URL → run multimodal link_handler
        # and synthesize stream events from its summary. Skips the normal
        # routing + Claude SDK call entirely.
        from jarvis.agents.lens import link_handler

        if link_handler.extract_urls(message or ""):
            async for ev in self._stream_via_link_handler(
                message or "", surface=surface, session_id=session_id
            ):
                yield ev
            return

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
        if not self._forced_model:
            # Recap runs on EVERY turn so the first message of a session
            # still pulls history off disk.  Lane-switch promotes to the
            # full recap; same-lane turns get the brief variant.
            lane_switch = (
                self._last_lane is not None and self._last_lane != decision.model
            )
            recap = self._recap(upcoming_message=cleaned, lane_switch=lane_switch)
            if recap:
                prompt = f"{recap}\n\n[Now Jyot says:]\n{cleaned}"

        # Inject live operator state (tasks, mail, pnl, calendar) into THIS
        # user turn. The SDK client caches its system prompt at connect time
        # so anything time-sensitive has to ride along with the user message
        # to be visible to a long-lived session.
        live_block = _build_live_state_block()
        if live_block:
            prompt = f"{live_block}\n\n[Jyot]: {prompt}"

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
        assistant_text = "".join(assistant_text_buf)
        self._record_turn("assistant", assistant_text, lane=decision.model)

        # Unified chat_turns.jsonl write — skip when surface=="chat" because
        # the HTTP endpoint already persists with full tool-call metadata.
        # Voice/terminal paths land here and need the durable record so the
        # dashboard sees their turns.
        if surface != "chat":
            self._record_unified_turn(
                user_text=cleaned,
                assistant_text=assistant_text,
                lane=decision.model,
                surface=surface,
                session_id=session_id,
            )

    async def _stream_via_link_handler(
        self,
        message: str,
        *,
        surface: Literal["voice", "chat", "api"] = "api",
        session_id: str = "default",
    ) -> AsyncIterator[StreamEvent]:
        """Run link_handler in a thread, synthesize stream events from result."""
        import asyncio

        from jarvis.agents.lens import link_handler

        cleaned = message.strip()
        # Sonnet handles link summaries — emit decision badge first.
        decision_model = self._sonnet_model
        yield StreamEvent(
            "model",
            {
                "model": decision_model,
                "reason": "link_handler — multimodal URL ingestion",
                "tier": 2,
                "manual": False,
                "length_chars": len(cleaned),
            },
        )

        try:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, link_handler.handle, cleaned)
        except Exception as exc:  # pragma: no cover — already caught inside handle
            yield StreamEvent("error", {"message": f"link_handler failed: {exc}"})
            return

        if resp.action == "no_url":
            yield StreamEvent("text", {"delta": "No URL found in your message."})
            yield StreamEvent("done", {"total_cost_usd": 0.0})
            return

        if resp.action == "failed":
            err = resp.result.get("error", "unknown")
            yield StreamEvent(
                "text",
                {
                    "delta": (
                        f"Couldn't process that link — {err}. "
                        "Try a different URL or a public one."
                    )
                },
            )
            yield StreamEvent("done", {"total_cost_usd": 0.0})
            return

        summary = str(resp.result.get("summary", "")).strip() or "Nothing useful."
        # Surface the summary in one text event so the UI streams it as a
        # single delta — consistent with the rest of the pipeline.
        yield StreamEvent("text", {"delta": summary})
        yield StreamEvent("done", {"total_cost_usd": 0.0})

        self._last_lane = decision_model
        self._record_turn("user", cleaned, lane=decision_model)
        self._record_turn("assistant", summary, lane=decision_model)
        if surface != "chat":
            self._record_unified_turn(
                user_text=cleaned,
                assistant_text=summary,
                lane=decision_model,
                surface=surface,
                session_id=session_id,
            )

    async def respond_single(
        self,
        message: str,
        *,
        surface: Literal["voice", "chat", "api"] = "voice",
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Single-shot reply for non-streaming surfaces (voice channel).

        Drives :meth:`stream` end-to-end, accumulates the assistant text +
        tool-call summary, and returns a dispatch-shaped dict the voice
        loop can pass to :func:`jarvis.apps.voice.loop._spoken_text`.

        The artifact lands under the ``agent_brain`` key (not ``voice``)
        so the voice humanizer condenses long replies before TTS.
        """
        text_buf: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        cost_usd = 0.0
        try:
            async for ev in self.stream(
                message, surface=surface, session_id=session_id
            ):
                if ev.type == "text":
                    text_buf.append(str(ev.payload.get("delta", "")))
                elif ev.type == "tool_use":
                    tool_calls.append(
                        {
                            "name": str(ev.payload.get("name", "")),
                            "agent": str(ev.payload.get("agent", "")),
                            "action": str(ev.payload.get("action", "")),
                        }
                    )
                elif ev.type == "done":
                    raw_cost = ev.payload.get("total_cost_usd")
                    if isinstance(raw_cost, (int, float)):
                        cost_usd = float(raw_cost)
        except Exception as exc:  # pragma: no cover — voice never crashes on chat fail
            logger.warning("respond_single failed: %s", exc)
            return {
                "responses": {
                    "voice": {
                        "agent": "jarvis-chat",
                        "action": "Hit a snag running that.",
                        "result": {
                            "source": "jarvis-chat-error",
                            "text": "Hit a snag running that.",
                            "error": str(exc)[:500],
                        },
                    },
                },
                "needs_confirm": False,
                "source": "jarvis-chat-error",
            }
        spoken = "".join(text_buf).strip() or "Done."
        return {
            "responses": {
                "agent_brain": {
                    "agent": "jarvis-chat",
                    "action": spoken,
                    "result": {
                        "source": "jarvis-chat",
                        "text": spoken,
                        "tool_calls": tool_calls,
                        "cost_usd": cost_usd,
                    },
                },
            },
            "needs_confirm": False,
            "source": "jarvis-chat",
        }


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
