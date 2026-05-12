"""Fix 3 — scholar.exam_session → fire_exam_scheduled callback wiring.

These tests pin the contract that:

* Scholar exposes an ``on_exam_scheduled`` callback hook
* ``exam_session`` invokes it with the persisted session dict
* Callback failures never break the underlying exam creation
* The default registry wires the callback so creating an exam auto-blocks a
  tempo task via R1 (``fire_exam_scheduled``)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.agents.scholar.agent import Scholar
from jarvis.contract import AgentResponse


def _patch_claude_quiet(monkeypatch):
    """Make _query_claude a no-op so exam_session doesn't try to call the SDK."""
    monkeypatch.setattr(
        "jarvis.agents.scholar.agent._query_claude",
        lambda system, user: "[]",
    )


class TestExamSessionInvokesCallback:
    def test_callback_called_with_session_dict(self, monkeypatch, tmp_path):
        """The callback receives the persisted session dict (session_id, course, ...)."""
        _patch_claude_quiet(monkeypatch)
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        # Avoid hitting StudyService DB
        scholar = Scholar()
        scholar._svc = MagicMock()  # type: ignore[assignment]
        scholar._svc.return_value.due_cards.return_value = []

        captured: list[dict[str, Any]] = []
        scholar.set_on_exam_scheduled(lambda session: captured.append(session))

        resp = scholar.exam_session("Linear Algebra", duration_min=60, problem_count=0)

        assert isinstance(resp, AgentResponse)
        assert len(captured) == 1
        session = captured[0]
        assert session["course"] == "Linear Algebra"
        assert session["session_id"] == resp.result["session_id"]
        assert "started_iso" in session
        assert "ends_iso" in session

    def test_callback_failure_does_not_break_exam_session(self, monkeypatch, tmp_path):
        """If the callback raises, exam_session still returns a created AgentResponse."""
        _patch_claude_quiet(monkeypatch)
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        scholar = Scholar()
        scholar._svc = MagicMock()  # type: ignore[assignment]
        scholar._svc.return_value.due_cards.return_value = []

        scholar.set_on_exam_scheduled(
            lambda session: (_ for _ in ()).throw(RuntimeError("registry not ready"))
        )

        resp = scholar.exam_session("Statistics", duration_min=30, problem_count=0)
        assert resp.action == "created"
        assert resp.result["course"] == "Statistics"

    def test_no_callback_is_a_noop(self, monkeypatch, tmp_path):
        """Default-constructed Scholar (no callback) doesn't break exam_session."""
        _patch_claude_quiet(monkeypatch)
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        scholar = Scholar()
        scholar._svc = MagicMock()  # type: ignore[assignment]
        scholar._svc.return_value.due_cards.return_value = []

        resp = scholar.exam_session("Calculus", duration_min=45, problem_count=0)
        assert resp.action == "created"


class TestRegistryWiresCallback:
    def test_build_default_registry_wires_scholar_callback(
        self, monkeypatch, tmp_path
    ):
        """build_default_registry should set scholar.on_exam_scheduled so R1 fires."""
        from jarvis.agents import registry as registry_mod

        _patch_claude_quiet(monkeypatch)
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

        # Capture fire_exam_scheduled calls so we don't actually hit the trigger
        called_with: list[tuple[dict, dict]] = []
        monkeypatch.setattr(
            "jarvis.core.triggers.fire_exam_scheduled",
            lambda reg, session: called_with.append((reg, session)),
        )

        reg = registry_mod.build_default_registry()
        scholar = reg["scholar"].instance

        # Scholar must have a non-None callback wired
        assert scholar._on_exam_scheduled is not None

        # Calling exam_session should fan into fire_exam_scheduled via the callback
        scholar._svc = MagicMock()  # type: ignore[assignment]
        scholar._svc.return_value.due_cards.return_value = []

        scholar.exam_session("Test Course", duration_min=30, problem_count=0)

        assert len(called_with) == 1
        bound_reg, session = called_with[0]
        # The bound registry must be the same dict that was returned
        assert bound_reg is reg
        assert session["course"] == "Test Course"
