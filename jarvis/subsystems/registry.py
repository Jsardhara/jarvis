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
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from ..contract import AgentResponse
from .atlas import AtlasBridge, AtlasOrchestrator
from .forge import Forge, MockRunner
from .lens import Lens
from .providers import BraveSearch, ExaSearch, MockOutlook, MockSearch
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


def _tempo_is_live() -> bool:
    """Return True when at least one real mail-provider env var is set."""
    return bool(os.environ.get("APPLE_ID") or os.environ.get("GMAIL_ADDRESS"))


def _lens_provider() -> tuple[Any, Literal["live", "mock"]]:
    """Return (provider_instance, mode) for Lens based on env.

    Resolution order: Brave → Perplexity/Exa → Mock. Brave wins because it
    sits on a 2000-query/mo free tier and ships better-quality web results
    than the legacy mock fixtures.
    """
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if brave_key:
        return BraveSearch(api_key=brave_key), "live"
    paid_key = os.environ.get("PERPLEXITY_API_KEY") or os.environ.get("EXA_API_KEY")
    if paid_key:
        return ExaSearch(api_key=paid_key), "live"
    return MockSearch(), "mock"


@dataclass
class AgentDescriptor:
    name: str
    instance: Any
    actions: dict[str, ActionFn] = field(default_factory=dict)
    default_for_text: ActionFn | None = None
    description: str = ""
    mode: Literal["live", "mock"] = "mock"

    def call(self, action: str, args: dict[str, Any] | None = None) -> AgentResponse:
        if action not in self.actions:
            raise ValueError(f"unknown action '{action}' for agent '{self.name}'")
        return self.actions[action](**(args or {}))

    def call_text(self, text: str) -> AgentResponse:
        if self.default_for_text is None:
            raise ValueError(f"agent '{self.name}' does not accept free text")
        return self.default_for_text(text)


def build_default_registry() -> dict[str, AgentDescriptor]:
    # Tempo: live when a real provider env var is present
    tempo_live = _tempo_is_live()
    outlook = _build_outlook()
    tempo_mode: Literal["live", "mock"] = "live" if tempo_live else "mock"
    if tempo_live:
        logger.info("tempo: live mode (real mail provider)")
    else:
        logger.info("tempo: mock mode (no APPLE_ID / GMAIL_ADDRESS)")
    tempo = Tempo(outlook)

    # Lens: live when EXA_API_KEY present
    lens_provider, lens_mode = _lens_provider()
    lens = Lens(lens_provider)

    # Forge: live when claude CLI is on PATH, otherwise MockRunner
    forge_mode: Literal["live", "mock"]
    try:
        from .forge_runner import WorktreeRunner as RealWorktreeRunner

        forge_runner: Any = RealWorktreeRunner()
        forge_mode = "live"
        logger.info("forge: live mode (worktree runner)")
    except (RuntimeError, FileNotFoundError) as exc:
        logger.warning("forge: falling back to mock (%s)", exc)
        forge_runner = MockRunner()
        forge_mode = "mock"
    forge = Forge(forge_runner)

    # Atlas: auto_mock_on_offline — health check decides live/mock per-call
    atlas_bridge = AtlasBridge()
    atlas = AtlasOrchestrator(bridge=atlas_bridge, allow_mock=True, auto_mock_on_offline=True)
    atlas_mode: Literal["live", "mock"] = "live" if atlas._health_check() else "mock"

    scholar = Scholar()

    return {
        "tempo": AgentDescriptor(
            name="tempo",
            instance=tempo,
            description="Gmail mail + iCloud calendar/tasks",
            mode=tempo_mode,
            actions={
                "triage": tempo.triage,
                "triage_smart": tempo.triage_smart,
                "search_mail": tempo.search_mail,
                "list_recent_mail": tempo.list_recent_mail,
                "snooze_mail": tempo.snooze_mail,
                "triage_status": tempo.triage_status,
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
            mode="live",
            actions={
                "list_assignments": scholar.list_assignments,
                "add_assignment": scholar.add_assignment,
                "plan_week": scholar.plan_week,
                "summarize": scholar.summarize,
                "upload_doc": scholar.upload_doc,
                "list_docs": scholar.list_docs,
                "get_doc_summary": scholar.get_doc_summary,
                "get_doc_flashcards": scholar.get_doc_flashcards,
                "generate_doc_flashcards": scholar.generate_doc_flashcards,
                "rate_flashcard": scholar.rate_flashcard,
                "due_flashcards": scholar.due_flashcards,
                "solve_problem": scholar.solve_problem,
                "rate_problem": scholar.rate_problem,
                "weak_topics": scholar.weak_topics,
                "exam_session": scholar.exam_session,
                "import_seed": scholar.import_seed,
                "ingest_syllabus": scholar.ingest_syllabus,
            },
            default_for_text=lambda _text: scholar.list_assignments(),
        ),
        "lens": AgentDescriptor(
            name="lens",
            instance=lens,
            description="Research + monitoring",
            mode=lens_mode,
            actions={
                "quick_search": lens.quick_search,
                "deep_research": lens.deep_research,
                "monitor": lens.monitor,
                "world_brief": lens.world_brief,
            },
            default_for_text=lambda text: lens.quick_search(text),
        ),
        "forge": AgentDescriptor(
            name="forge",
            instance=forge,
            description="Code-work delegation",
            mode=forge_mode,
            actions={
                "execute": forge.execute,
                "list_runs": forge.list_runs,
                "get_run": forge.get_run,
                "pick_project": forge.pick_project,
                "scaffold_daily": forge.scaffold_daily,
            },
            default_for_text=lambda text: forge.execute(repo="?", task=text, push=False),
        ),
        "atlas": AgentDescriptor(
            name="atlas",
            instance=atlas,
            description="Trading orchestrator (Oracle/Architect/Guardian/Trader/Sage)",
            mode=atlas_mode,
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
