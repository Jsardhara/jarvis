"""Tests for jarvis.model_router.decide_model."""
from __future__ import annotations

import pytest

from jarvis.model_router import (
    DEFAULT_OPUS_ID,
    DEFAULT_SONNET_ID,
    RouteDecision,
    decide_model,
)


def _opus(d: RouteDecision) -> bool:
    return d.model == DEFAULT_OPUS_ID


def _sonnet(d: RouteDecision) -> bool:
    return d.model == DEFAULT_SONNET_ID


# ---------- manual override ----------


def test_opus_prefix_forces_opus_and_strips():
    decision, cleaned = decide_model("/opus refactor the orchestrator")
    assert _opus(decision)
    assert decision.manual is True
    assert cleaned == "refactor the orchestrator"


def test_sonnet_prefix_forces_sonnet_and_strips():
    decision, cleaned = decide_model("/sonnet what time is it")
    assert _sonnet(decision)
    assert decision.manual is True
    assert cleaned == "what time is it"


def test_override_is_case_insensitive():
    decision, cleaned = decide_model("/OPUS hello")
    assert _opus(decision)
    assert decision.manual is True
    assert cleaned == "hello"


def test_override_without_space_does_not_match():
    decision, _cleaned = decide_model("/opushello")
    # treated as a normal short message, not a slash override
    assert decision.manual is False


# ---------- tier escalation ----------


def test_tier1_keyword_routes_to_opus():
    # "live trade" is a tier-1 trigger in classify.py
    decision, _ = decide_model("live trade BTC now")
    assert _opus(decision)
    assert decision.tier == 1
    assert "tier 1" in decision.reason


def test_tier2_keyword_routes_to_opus():
    decision, _ = decide_model("drawdown alert — review now")
    assert _opus(decision)
    assert decision.tier == 2


# ---------- heavy keywords ----------


def test_code_keyword_routes_to_opus():
    decision, _ = decide_model("can you refactor that function")
    assert _opus(decision)
    assert "heavy" in decision.reason


def test_design_keyword_routes_to_opus():
    decision, _ = decide_model("design a retry policy for the daemon")
    assert _opus(decision)


# ---------- length ----------


def test_long_message_routes_to_opus():
    msg = "I need help with " + "many things " * 30  # > 280 chars
    decision, _ = decide_model(msg)
    assert _opus(decision)
    assert "long message" in decision.reason


def test_multi_sentence_routes_to_opus():
    decision, _ = decide_model("First. Second. Third. Fourth.")
    assert _opus(decision)


# ---------- greetings / lookups → sonnet ----------


@pytest.mark.parametrize("greeting", ["hi", "hey jarvis", "hello", "yo", "thanks", "gm", "gn"])
def test_greetings_route_to_sonnet(greeting: str):
    decision, _ = decide_model(greeting)
    assert _sonnet(decision)
    assert decision.manual is False


def test_short_question_routes_to_sonnet():
    decision, _ = decide_model("what's on my calendar?")
    assert _sonnet(decision)


# ---------- defaults ----------


def test_empty_input_routes_to_sonnet():
    decision, cleaned = decide_model("")
    assert _sonnet(decision)
    assert cleaned == ""


def test_whitespace_routes_to_sonnet():
    decision, _ = decide_model("   \n  ")
    assert _sonnet(decision)


def test_short_tier5_routes_to_sonnet():
    decision, _ = decide_model("status check")
    assert _sonnet(decision)


def test_decision_carries_length_and_tier():
    decision, _ = decide_model("hey there friend")
    assert decision.length_chars == len("hey there friend")
    assert decision.tier == 5
    assert decision.is_sonnet
    assert not decision.is_opus
