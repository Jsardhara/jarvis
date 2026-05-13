"""Fix 1 — atlas.guardian_check publishes violations to inbox as crit InboxEvent.

Without this wiring, guardian rejections only show up in the AgentResponse result,
never on the dashboard/voice/morning brief. These tests pin the new behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from jarvis.agents.atlas.agent import AtlasBridge, AtlasOrchestrator
from jarvis.contract import InboxEvent


def _orch_in_mock_mode() -> AtlasOrchestrator:
    """Build an orchestrator that won't try real HTTP calls."""
    bridge = AtlasBridge(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    return AtlasOrchestrator(bridge=bridge, allow_mock=True, mode="mock")


def test_guardian_check_live_mode_writes_inbox_crit():
    """mode=live forces a violation in the mock path → must emit crit InboxEvent."""
    orch = _orch_in_mock_mode()

    captured: list[InboxEvent] = []

    def _capture(event: InboxEvent) -> InboxEvent:
        captured.append(event)
        return event

    with patch("jarvis.state.append_inbox", side_effect=_capture) as mock_append:
        resp = orch.guardian_check("strat_001", mode="live")

    assert resp.result["approved"] is False
    assert resp.result["violations"], "expected at least one violation"
    assert mock_append.called, "guardian_check must emit inbox event on violation"

    event = captured[0]
    assert event.agent == "atlas"
    assert event.severity == "crit"
    assert "Guardian violation" in event.summary
    assert event.ref["strategy_id"] == "strat_001"
    assert event.ref["violations"] == resp.result["violations"]


def test_guardian_check_approved_does_not_write_inbox():
    """Paper-mode mock returns approved=True → no inbox event."""
    orch = _orch_in_mock_mode()

    with patch("jarvis.state.append_inbox") as mock_append:
        resp = orch.guardian_check("strat_002", mode="paper")

    assert resp.result["approved"] is True
    assert not mock_append.called, "no inbox event when guardian approves"


def test_guardian_check_inbox_failure_is_swallowed():
    """If append_inbox raises (disk full, malformed state), guardian_check still returns normally."""
    orch = _orch_in_mock_mode()

    with patch("jarvis.state.append_inbox", side_effect=OSError("disk full")):
        # Should not raise; the violation is still in result even if inbox write fails.
        resp = orch.guardian_check("strat_003", mode="live")

    assert resp.result["approved"] is False
    assert resp.result["violations"]


def test_guardian_check_live_bridge_violation_writes_inbox():
    """When the live HTTP bridge returns violations, the same inbox event fires."""
    bridge = MagicMock(spec=AtlasBridge)
    bridge.pipeline_guardian_check.return_value = {
        "status": "completed",
        "correlation_id": "corr_xyz",
        "approved": False,
        "violations": ["position size exceeds cap", "stop loss missing"],
    }
    orch = AtlasOrchestrator(bridge=bridge, allow_mock=False, mode="live")

    # Force the live path to be selected by stubbing the offline check.
    with patch.object(orch, "_is_offline", return_value=False), \
         patch.object(orch, "_use_mock", return_value=False), \
         patch("jarvis.state.append_inbox") as mock_append:
        resp = orch.guardian_check("strat_004", mode="live")

    assert mock_append.called
    event = mock_append.call_args[0][0]
    assert event.agent == "atlas"
    assert event.severity == "crit"
    assert event.ref["strategy_id"] == "strat_004"
    assert "position size exceeds cap" in event.ref["violations"]
