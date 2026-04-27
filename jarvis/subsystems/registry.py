"""Subsystem registry — central map of agent name -> instance + actions.

Six top-level agents:

    tempo    — Outlook (mail + calendar + tasks)
    scholar  — academics + study planning
    lens     — research + monitoring
    forge    — code-work delegation
    atlas    — trading orchestrator (Oracle/Architect/Guardian/Trader/Sage)

Plus jarvis itself as the orchestrator (handled outside the registry).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..contract import AgentResponse
from .atlas import AtlasBridge, AtlasOrchestrator
from .forge import Forge, MockRunner
from .lens import Lens
from .providers import MockOutlook, MockSearch
from .scholar import Scholar
from .tempo import Tempo
from .tempo_stack import build_default_tempo_stack

ActionFn = Callable[..., AgentResponse]

logger = logging.getLogger(__name__)


def _build_outlook() -> Any:
    """Try real iCloud + Gmail (+Drexel) stack; fall back to MockOutlook on missing env."""
    try:
        return build_default_tempo_stack()
    except RuntimeError as exc:
        logger.warning("TempoStack unavailable (%s); falling back to MockOutlook", exc)
        return MockOutlook()


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
    outlook = _build_outlook()
    tempo = Tempo(outlook)
    lens = Lens(MockSearch())
    forge = Forge(MockRunner())
    atlas = AtlasOrchestrator(bridge=AtlasBridge(), allow_mock=True)
    scholar = Scholar()

    return {
        "tempo": AgentDescriptor(
            name="tempo",
            instance=tempo,
            description="Outlook — mail, calendar, tasks",
            actions={
                "triage": tempo.triage,
                "draft_reply": tempo.draft_reply,
                "send_mail": tempo.send_mail,
                "today": tempo.today,
                "find_free": tempo.find_free,
                "schedule": tempo.schedule,
                "cancel": tempo.cancel,
                "add": tempo.add,
                "list_open": tempo.list_open,
                "complete": tempo.complete,
            },
            default_for_text=lambda _text: tempo.today(),
        ),
        "scholar": AgentDescriptor(
            name="scholar",
            instance=scholar,
            description="Academics + study planning",
            actions={
                "list_assignments": scholar.list_assignments,
                "add_assignment": scholar.add_assignment,
                "plan_week": scholar.plan_week,
                "summarize": scholar.summarize,
            },
            default_for_text=lambda _text: scholar.list_assignments(),
        ),
        "lens": AgentDescriptor(
            name="lens",
            instance=lens,
            description="Research + monitoring",
            actions={
                "quick_search": lens.quick_search,
                "deep_research": lens.deep_research,
                "monitor": lens.monitor,
            },
            default_for_text=lambda text: lens.quick_search(text),
        ),
        "forge": AgentDescriptor(
            name="forge",
            instance=forge,
            description="Code-work delegation",
            actions={"execute": forge.execute},
            default_for_text=lambda text: forge.execute(repo="?", task=text, push=False),
        ),
        "atlas": AgentDescriptor(
            name="atlas",
            instance=atlas,
            description="Trading orchestrator (Oracle/Architect/Guardian/Trader/Sage)",
            actions={
                "portfolio": atlas.portfolio,
                "positions": atlas.positions,
                "pnl": atlas.pnl,
                "oracle_scan": atlas.oracle_scan,
                "architect_rank": atlas.architect_rank,
                "guardian_check": atlas.guardian_check,
                "trader_execute": atlas.trader_execute,
                "trader_execute_confirmed": atlas.trader_execute_confirmed,
                "sage_review": atlas.sage_review,
                "pipeline": atlas.pipeline,
            },
            default_for_text=lambda _text: atlas.portfolio(),
        ),
    }
