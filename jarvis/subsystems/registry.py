"""Subsystem registry — central map of agent name -> instance + callable actions.

Powers `/api/agents/{name}/dispatch` and the per-agent chat drawer. Each
agent exposes an explicit allowlist of actions so the API never invokes
arbitrary attributes. A `default_for_text` callable handles free-text
input from the drawer (when the user just types a sentence).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..contract import AgentResponse
from .aide import Aide
from .chronos import Chronos
from .echo import Echo
from .forge import Forge, MockRunner
from .hearth import Hearth
from .ledger import AtlasClient, Ledger
from .providers import MockCalendar, MockGmail
from .sherlock import MockSearch, Sherlock

ActionFn = Callable[..., AgentResponse]


@dataclass
class AgentDescriptor:
    name: str
    instance: Any
    actions: dict[str, ActionFn] = field(default_factory=dict)
    default_for_text: ActionFn | None = None
    description: str = ""

    def call(self, action: str, args: dict[str, Any] | None = None) -> AgentResponse:
        if action not in self.actions:
            raise ValueError(f"unknown action '{action}' for agent '{self.name}'")
        return self.actions[action](**(args or {}))

    def call_text(self, text: str) -> AgentResponse:
        if self.default_for_text is None:
            raise ValueError(f"agent '{self.name}' does not accept free text")
        return self.default_for_text(text)


def build_default_registry() -> dict[str, AgentDescriptor]:
    aide = Aide(MockGmail())
    chronos = Chronos(MockCalendar())
    sherlock = Sherlock(MockSearch())
    forge = Forge(MockRunner())
    ledger = Ledger(client=AtlasClient(), allow_mock=True)
    echo = Echo()
    hearth = Hearth()

    return {
        "aide": AgentDescriptor(
            name="aide",
            instance=aide,
            description="Email triage + drafts",
            actions={
                "triage": aide.triage,
                "draft_reply": aide.draft_reply,
                "send": aide.send,
            },
            default_for_text=lambda _text: aide.triage(),
        ),
        "chronos": AgentDescriptor(
            name="chronos",
            instance=chronos,
            description="Calendar + tasks",
            actions={
                "today": chronos.today,
                "find_free": chronos.find_free,
                "schedule": chronos.schedule,
                "cancel": chronos.cancel,
                "add": chronos.add,
                "list_open": chronos.list_open,
                "complete": chronos.complete,
            },
            default_for_text=lambda _text: chronos.today(),
        ),
        "sherlock": AgentDescriptor(
            name="sherlock",
            instance=sherlock,
            description="Web research",
            actions={
                "quick_search": sherlock.quick_search,
                "deep_research": sherlock.deep_research,
            },
            default_for_text=lambda text: sherlock.quick_search(text),
        ),
        "forge": AgentDescriptor(
            name="forge",
            instance=forge,
            description="Code agent runner",
            actions={"execute": forge.execute},
            default_for_text=lambda text: forge.execute(repo="?", task=text, push=False),
        ),
        "ledger": AgentDescriptor(
            name="ledger",
            instance=ledger,
            description="ATLAS / portfolio",
            actions={
                "portfolio": ledger.portfolio,
                "positions": ledger.positions,
                "pnl": ledger.pnl,
                "trigger_strategy": ledger.trigger_strategy,
                "trigger_strategy_confirmed": ledger.trigger_strategy_confirmed,
            },
            default_for_text=lambda _text: ledger.portfolio(),
        ),
        "echo": AgentDescriptor(
            name="echo",
            instance=echo,
            description="Slack / Discord / SMS",
            actions={
                "triage": echo.triage,
                "draft_reply": echo.draft_reply,
                "send": echo.send,
            },
            default_for_text=lambda _text: echo.triage([]),
        ),
        "hearth": AgentDescriptor(
            name="hearth",
            instance=hearth,
            description="Home Assistant",
            actions={
                "list_devices": hearth.list_devices,
                "light_on": hearth.light_on,
                "light_on_confirmed": hearth.light_on_confirmed,
                "thermostat_set": hearth.thermostat_set,
                "media_play": hearth.media_play,
            },
            default_for_text=lambda _text: hearth.list_devices(),
        ),
    }
