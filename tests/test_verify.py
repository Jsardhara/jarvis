"""Verification layer tests."""
from __future__ import annotations

from jarvis.contract import AgentResponse
from jarvis.verify import (
    make_verification,
    verify_atlas,
    verify_default,
    verify_response,
    verify_tempo,
    wrap_verification,
)


def test_make_verification_has_required_fields():
    v = make_verification("verified", "test evidence")
    assert v["status"] == "verified"
    assert v["evidence"] == "test evidence"
    assert "checked_at" in v


def test_wrap_verification_updates_response():
    resp = AgentResponse(agent="tempo", intent="read", action="fetched")
    wrapped = wrap_verification(resp, "verified", "test")
    assert wrapped.verification["status"] == "verified"
    assert wrapped.verification["evidence"] == "test"


def test_verify_tempo_read_actions():
    resp = AgentResponse(agent="tempo", intent="read", action="fetched", result={})
    verified = verify_tempo(resp)
    assert verified.verification["status"] == "verified"


def test_verify_tempo_write_actions():
    resp = AgentResponse(agent="tempo", intent="write", action="send_mail", result={})
    verified = verify_tempo(resp)
    assert verified.verification["status"] == "post_state_checked"


def test_verify_atlas_executed_trades():
    resp = AgentResponse(agent="atlas", intent="trade", action="executed", result={})
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "post_state_checked"


def test_verify_atlas_proposed_trades():
    resp = AgentResponse(agent="atlas", intent="trade", action="proposed", result={}, needs_confirm=True)
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "inference"


def test_verify_atlas_read_actions():
    resp = AgentResponse(agent="atlas", intent="read", action="fetched", result={})
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "verified"


def test_verify_response_dispatches_to_agent_verifier():
    resp = AgentResponse(agent="tempo", intent="read", action="fetched", result={})
    verified = verify_response(resp)
    assert verified.verification["status"] == "verified"


def test_verify_response_uses_default_for_unknown_agent():
    resp = AgentResponse(agent="unknown_agent", intent="do", action="done", result={})
    verified = verify_response(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_proposed_actions():
    resp = AgentResponse(agent="scholar", intent="plan", action="proposed", result={}, needs_confirm=True)
    verified = verify_default(resp)
    assert verified.verification["status"] == "inference"


def test_verify_default_completed_actions():
    resp = AgentResponse(agent="scholar", intent="plan", action="done", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_tempo_schedule_action():
    resp = AgentResponse(agent="tempo", intent="schedule", action="schedule", result={})
    verified = verify_tempo(resp)
    assert verified.verification["status"] == "post_state_checked"


def test_verify_tempo_cancel_action():
    resp = AgentResponse(agent="tempo", intent="cancel", action="cancel", result={})
    verified = verify_tempo(resp)
    assert verified.verification["status"] == "post_state_checked"


def test_verify_tempo_complete_action():
    resp = AgentResponse(agent="tempo", intent="complete", action="complete", result={})
    verified = verify_tempo(resp)
    assert verified.verification["status"] == "post_state_checked"


def test_verify_atlas_vetoed_trades():
    resp = AgentResponse(agent="atlas", intent="trade", action="vetoed", result={})
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "inference"


def test_verify_atlas_halted_trades():
    resp = AgentResponse(agent="atlas", intent="trade", action="halted", result={})
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "inference"


def test_verify_atlas_with_needs_confirm_true():
    resp = AgentResponse(agent="atlas", intent="trade", action="something", result={}, needs_confirm=True)
    verified = verify_atlas(resp)
    assert verified.verification["status"] == "inference"


def test_verify_atlas_subagents():
    for agent in ["atlas.oracle", "atlas.architect", "atlas.guardian", "atlas.trader", "atlas.sage"]:
        resp = AgentResponse(agent=agent, intent="action", action="done", result={})
        verified = verify_response(resp)
        assert verified.verification["status"] in ["verified", "inference"]


def test_verify_default_executed_actions():
    resp = AgentResponse(agent="forge", intent="build", action="executed", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_approved_actions():
    resp = AgentResponse(agent="lens", intent="research", action="approved", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_reviewed_actions():
    resp = AgentResponse(agent="scholar", intent="study", action="reviewed", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_ranked_actions():
    resp = AgentResponse(agent="atlas", intent="rank", action="ranked", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_scanned_actions():
    resp = AgentResponse(agent="lens", intent="monitor", action="scanned", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "verified"


def test_verify_default_unknown_action_returns_unknown():
    resp = AgentResponse(agent="unknown_agent", intent="unknown", action="unknown_action", result={})
    verified = verify_default(resp)
    assert verified.verification["status"] == "unknown"


def test_verify_response_preserves_original_fields():
    resp = AgentResponse(
        agent="tempo",
        intent="read",
        action="fetched",
        result={"count": 5},
        confidence=0.9,
        follow_ups=["next step"],
    )
    verified = verify_response(resp)
    assert verified.result == resp.result
    assert verified.confidence == resp.confidence
    assert verified.follow_ups == resp.follow_ups
    assert verified.verification["status"] == "verified"
