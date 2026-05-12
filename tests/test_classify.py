"""Tier classification tests."""
from __future__ import annotations

import pytest

from jarvis.core.classify import TierClassification, classify_tier


# Tier 1: safety/risk
@pytest.mark.parametrize("request_text", [
    "execute live trade now",
    "live mode trading",
    "mass delete all records",
    "stop sentinel",
    "force push to main",
])
def test_tier_1_safety_risk(request_text: str):
    result = classify_tier(request_text)
    assert result.tier == 1, f"Expected tier 1 for {request_text!r}, got {result.tier} ({result.rationale})"


# Tier 2: time-sensitive
@pytest.mark.parametrize("request_text", [
    "my deadline is today",
    "meeting starting soon",
    "exam today at 2pm",
    "drawdown alert critical",
    "this is urgent",
])
def test_tier_2_time_sensitive(request_text: str):
    result = classify_tier(request_text)
    assert result.tier == 2, f"Expected tier 2 for {request_text!r}, got {result.tier} ({result.rationale})"


# Tier 3: trading/research
@pytest.mark.parametrize("request_text", [
    "paper trade on momentum",
    "backtest the strategy",
    "market scan for gainers",
    "monitor bitcoin news",
    "what's my portfolio value",
])
def test_tier_3_trading_research(request_text: str):
    result = classify_tier(request_text)
    assert result.tier == 3, f"Expected tier 3 for {request_text!r}, got {result.tier} ({result.rationale})"


# Tier 4: scheduling/correspondence
@pytest.mark.parametrize("request_text", [
    "draft a reply",
    "schedule a meeting",
    "add a todo",
    "check my inbox",
    "create a study plan",
])
def test_tier_4_scheduling_mail(request_text: str):
    result = classify_tier(request_text)
    assert result.tier == 4, f"Expected tier 4 for {request_text!r}, got {result.tier} ({result.rationale})"


# Tier 5: routine
@pytest.mark.parametrize("request_text", [
    "what time is it",
    "hello",
    "status check",
])
def test_tier_5_routine(request_text: str):
    result = classify_tier(request_text)
    assert result.tier == 5, f"Expected tier 5 for {request_text!r}, got {result.tier} ({result.rationale})"


def test_classify_returns_tier_classification():
    result = classify_tier("check portfolio")
    assert isinstance(result, TierClassification)
    assert 1 <= result.tier <= 5
    assert result.rationale


def test_classify_empty_defaults_to_tier_5():
    result = classify_tier("")
    assert result.tier == 5


def test_classify_with_agent_context():
    result = classify_tier("stop", agent="sentinel", action="stop")
    assert result.tier == 1


def test_classify_first_match_wins():
    result = classify_tier("live trade today urgent")
    assert result.tier == 1
