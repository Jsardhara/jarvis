"""Jarvis chatbot — Claude Opus 4.7 with the OpenClaw soul.

Wraps the claude-agent-sdk ClaudeSDKClient so the user can talk to Jarvis
in natural language. Jarvis has tools for delegating to each subsystem
(tempo / scholar / lens / forge / atlas) — every tool call also flows
through the existing AgentDescriptor.call() so verification, tier, and
memory are recorded the same way as direct dispatches.

Streaming
---------
``JarvisChat.stream(message)`` yields a sequence of typed events the web
layer turns into SSE frames:

    {"type": "text",     "delta": "...token..."}
    {"type": "tool_use", "agent": "tempo", "action": "today", "args": {...}, "tool_use_id": "..."}
    {"type": "tool_result", "tool_use_id": "...", "result": {...}}
    {"type": "done"}
    {"type": "error", "message": "..."}
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
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

from jarvis.subsystems.registry import AgentDescriptor, build_default_registry

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
SOUL_FILENAME = "jarvis_soul.md"


# ---------- Soul loader ----------


def load_soul() -> str:
    here = Path(__file__).parent / "personas" / SOUL_FILENAME
    return here.read_text(encoding="utf-8")


# ---------- Tool definitions ----------


_AGENT_DESCRIPTIONS = {
    "tempo": (
        "Outlook + iCloud calendar + reminders + Gmail/Drexel mail. Actions: "
        "triage, draft_reply, send_mail, today, find_free, schedule, cancel, "
        "add, list_open, complete."
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
            return _err(f"unknown agent {agent_name!r}; choose tempo / scholar / lens / forge / atlas")
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


class JarvisChat:
    """One persistent SDK client. Conversation history lives inside the SDK
    session (each ``query`` is a new turn in the same session)."""

    def __init__(
        self,
        registry: dict[str, AgentDescriptor] | None = None,
        model: str = DEFAULT_MODEL,
        soul: str | None = None,
    ):
        self._registry = registry or build_default_registry()
        self._soul = soul or load_soul()
        self._model = model
        self._client: ClaudeSDKClient | None = None

    def _build_client(self) -> ClaudeSDKClient:
        if self._client is not None:
            return self._client
        delegate = _build_delegate_tool(self._registry)
        srv = create_sdk_mcp_server(name="jarvis-team", version="0.1.0", tools=[delegate])
        agents_block = "\n".join(
            f"- **{name}** — {desc}" for name, desc in _AGENT_DESCRIPTIONS.items()
        )
        system_addendum = (
            "\n\n---\n\n## Tool use\n\n"
            "You have one tool, `delegate(agent, action, args)`. Use it to dispatch "
            "to your team. Available agents and their actions:\n\n"
            f"{agents_block}\n\n"
            "When a request needs an agent, call `delegate` and synthesize the "
            "response for Jyot. Do not pretend to act on his behalf without "
            "actually calling the tool."
        )
        full_system = self._soul + system_addendum
        opts = ClaudeAgentOptions(
            model=self._model,
            system_prompt=full_system,
            mcp_servers={"jarvis-team": srv},
            allowed_tools=["mcp__jarvis-team__delegate"],
            permission_mode="bypassPermissions",  # tool calls are pre-authorized via authority gate
        )
        self._client = ClaudeSDKClient(options=opts)
        return self._client

    async def connect(self) -> None:
        client = self._build_client()
        await client.connect()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def stream(self, message: str) -> AsyncIterator[StreamEvent]:
        """Send one user turn, yield events as Claude responds."""
        client = self._build_client()
        if not getattr(self, "_connected", False):
            try:
                await client.connect()
            except Exception as exc:
                yield StreamEvent("error", {"message": f"connect failed: {exc}"})
                return
            self._connected = True
        try:
            await client.query(message)
        except Exception as exc:
            yield StreamEvent("error", {"message": f"query failed: {exc}"})
            return

        try:
            async for sdk_msg in client.receive_response():
                async for ev in _convert_message(sdk_msg):
                    yield ev
        except Exception as exc:
            yield StreamEvent("error", {"message": f"stream error: {exc}"})


async def _convert_message(msg: Any) -> AsyncIterator[StreamEvent]:
    """Translate an SDK message into one or more StreamEvents."""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                if block.text:
                    yield StreamEvent("text", {"delta": block.text})
            elif isinstance(block, ThinkingBlock):
                # surface thinking lightly — keep payload short
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
        # Tool results round-trip through the SDK as user messages with
        # ToolResultBlock content. Surface them so the dashboard can update.
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
        return  # initial init message, nothing user-visible

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
