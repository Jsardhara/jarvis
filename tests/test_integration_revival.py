"""End-to-end smoke tests for the integration-revival branch.

These tests exercise the full closed loop the audit identified as dead code:
guardian violation → inbox event → cross-agent reaction (notifier push).
Together they prove the system reacts to itself end-to-end, which is the
property the audit said was missing pre-fix.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

import jarvis.state as _state_mod
from jarvis.agents.atlas.agent import AtlasBridge, AtlasOrchestrator
from jarvis.contract import InboxEvent
from jarvis.core.triggers import fire_for_event
from jarvis.state import (
    append_inbox,
    register_inbox_listener,
    unregister_inbox_listener,
)


@pytest.fixture
def isolated_inbox_listeners(monkeypatch):
    """Replace ``_inbox_listeners`` with a fresh list for the duration of the test.

    Other modules (notably ``jarvis.apps.api.app``) register a fire_for_event
    listener at module-import time with a no-op default_notifier. Without
    isolation, that listener fires first on every append_inbox, writes its
    dedup record to triggers_fired.jsonl, and then the test's own listener
    sees the dedup and returns None — never reaching the test's mock notifier.
    Snapshotting the list gives each test a clean inbox-listener slate.
    """
    saved = list(_state_mod._inbox_listeners)
    _state_mod._inbox_listeners.clear()
    yield
    _state_mod._inbox_listeners.clear()
    _state_mod._inbox_listeners.extend(saved)


def _orch_in_mock_mode() -> AtlasOrchestrator:
    bridge = AtlasBridge(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    return AtlasOrchestrator(bridge=bridge, allow_mock=True, mode="mock")


def test_guardian_violation_propagates_to_notifier(tmp_path, monkeypatch, isolated_inbox_listeners):
    """Atlas guardian_check rejection → inbox crit → fire_for_event → notifier push.

    This is the closed-loop test. Pre-fix, every link in this chain was broken:
    guardian violations didn't write inbox events, and fire_for_event was an
    empty stub. If this test passes, the system reacts to itself.
    """
    from jarvis.core import triggers

    # Isolate trigger dedup file
    monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    notifier = MagicMock()

    # Register the cross-agent reaction layer — same wiring the API + sentinel
    # do at startup, but with our test-side mock notifier.
    listener = lambda event: fire_for_event({}, event, notifier=notifier)
    register_inbox_listener(listener)
    try:
        orch = _orch_in_mock_mode()
        # mode=live forces a violation in the mock path.
        resp = orch.guardian_check("strat_smoke", mode="live")
    finally:
        unregister_inbox_listener(listener)

    # 1. Atlas returned a rejection
    assert resp.result["approved"] is False
    assert resp.result["violations"]

    # 2. Notifier was pushed at priority=2 because the inbox event fanned out
    #    through fire_for_event's atlas_crit handler.
    assert notifier.push.called, "notifier.push should have fired on guardian violation"
    push_kwargs = notifier.push.call_args.kwargs
    push_args = notifier.push.call_args.args
    priority = push_kwargs.get("priority", push_args[2] if len(push_args) >= 3 else None)
    assert priority == 2, f"expected priority=2, got {priority}"


def test_forge_dead_letter_propagates_to_notifier(tmp_path, monkeypatch, isolated_inbox_listeners):
    """Manually writing a forge crit InboxEvent fires the forge handler.

    Mirrors what scan_periodic does for R4 when a dead-letter record appears.
    """
    from jarvis.core import triggers

    monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    notifier = MagicMock()

    listener = lambda event: fire_for_event({}, event, notifier=notifier)
    register_inbox_listener(listener)
    try:
        event = InboxEvent(
            agent="forge",
            severity="crit",
            summary="Forge execute failed: SDK timeout after 3 retries",
            ref={"request_id": "req_smoke_42", "error_class": "TimeoutError", "retries": 3},
        )
        append_inbox(event)
    finally:
        unregister_inbox_listener(listener)

    assert notifier.push.called
    priority = notifier.push.call_args.kwargs.get(
        "priority",
        notifier.push.call_args.args[2] if len(notifier.push.call_args.args) >= 3 else None,
    )
    assert priority == 2


def test_scholar_imminent_exam_triggers_tempo_add(tmp_path, monkeypatch, isolated_inbox_listeners):
    """Sentinel-style scholar warn → fire_for_event dispatches tempo.add.

    Uses a mocked registry so we don't touch real Tempo/iCloud.
    """
    from jarvis.contract import AgentResponse
    from jarvis.core import triggers

    monkeypatch.setattr(triggers, "_fired_path", lambda: tmp_path / "triggers_fired.jsonl")
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    tempo = MagicMock()
    tempo.call.return_value = AgentResponse(
        agent="tempo",
        intent="add_task",
        action="created",
        result={"task": {"id": "t_int_1"}},
    )
    reg = {"tempo": tempo}

    notifier = MagicMock()
    listener = lambda event: fire_for_event(reg, event, notifier=notifier)
    register_inbox_listener(listener)
    try:
        event = InboxEvent(
            agent="scholar",
            severity="warn",
            summary="Exam in 5h: Linear Algebra",
            ref={
                "session_id": "sess_smoke",
                "course": "Linear Algebra",
                "starts_at": "2026-05-13T12:00:00+00:00",
            },
        )
        append_inbox(event)
    finally:
        unregister_inbox_listener(listener)

    # tempo.add was dispatched via fire_for_event
    tempo.call.assert_called_once()
    call_args = tempo.call.call_args
    assert call_args[0][0] == "add"
    payload = call_args[0][1]
    assert "Linear Algebra" in payload["title"]
    assert payload["due"] == "2026-05-13T12:00:00+00:00"
