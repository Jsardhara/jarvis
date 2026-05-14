"""Intent classifier tests — six-agent routing."""
from __future__ import annotations

import pytest

from jarvis.core.router import classify


@pytest.mark.parametrize("request_text,expected", [
    ("check my outlook inbox", "tempo"),
    ("draft a reply to Bob", "tempo"),
    ("what's on my calendar today", "tempo"),
    ("schedule a meeting Tuesday 3pm", "tempo"),
    ("add a todo to call dentist", "tempo"),
    ("research the new Anthropic model", "lens"),
    ("look up FastAPI middleware patterns", "lens"),
    ("monitor anthropic releases", "lens"),
    ("fix the bug in main.py", "forge"),
    ("ship the new feature to repo X", "forge"),
    ("what's my portfolio doing", "atlas"),
    ("any open positions", "atlas"),
    ("backtest the trend strategy", "atlas"),
    ("when is my CS401 assignment due", "scholar"),
    ("plan my study sessions for the midterm", "scholar"),
])
def test_single_agent_routing(request_text: str, expected: str):
    c = classify(request_text)
    assert c.primary == expected
    assert c.confidence >= 0.7


def test_briefing_multi_dispatch():
    c = classify("give me my morning briefing")
    assert c.primary == "tempo"
    assert "scholar" in c.parallel
    assert "atlas" in c.parallel


def test_empty_request():
    c = classify("")
    assert c.primary == "jarvis"
    assert c.confidence == 0.0


def test_unmatched_falls_to_jarvis():
    c = classify("tell me a joke about ducks")
    assert c.primary == "jarvis"
    assert c.confidence < 0.5


def test_multi_rule_match_routes_primary_then_parallel():
    c = classify("any email about the calendar invite then research the topic")
    assert c.primary == "tempo"
    assert "lens" in c.parallel


def test_watchlist_routes_to_atlas():
    """``add Nvidia to my watchlist`` → atlas with add_to_watchlist action."""
    c = classify("add Nvidia to my watchlist")
    assert c.primary == "atlas"
    assert c.action == "add_to_watchlist"


def test_overdue_fans_to_tempo_and_scholar():
    """An ``overdue`` query fans out to tempo + scholar — both surface items."""
    c = classify("is anything overdue?")
    targets = {c.primary, *c.parallel}
    assert c.primary in {"tempo", "scholar"}
    assert "tempo" in targets
    assert "scholar" in targets


def test_pause_trader_routes_correctly():
    """``pause the trader`` → atlas, action=pause_agent (confirmation-gated)."""
    c = classify("pause the trader")
    assert c.primary == "atlas"
    assert c.action == "pause_agent"


def test_add_assignment_action():
    """``add CS401 homework due Friday`` → scholar, add_assignment (not list)."""
    c = classify("add CS401 homework due Friday")
    assert c.primary == "scholar"
    assert c.action == "add_assignment"


def test_todo_in_codebase_routes_to_forge():
    """``TODO in our codebase`` → forge, NOT tempo's todo rule."""
    c = classify("is there a TODO in our codebase about timeouts")
    assert c.primary == "forge"


def test_primary_by_earliest_mention():
    """Primary chosen by earliest match position in request text."""
    c = classify("check inbox and tell me about my BTC position")
    assert c.primary == "tempo"
    assert "atlas" in c.parallel


def test_confidence_tiers_match_rule_strength():
    """Confidence ladder: empty 0.0 → unmatched 0.3 → multi 0.7/0.85 → single 0.9."""
    assert classify("").confidence == 0.0
    assert classify("blarp the quux").confidence == 0.3
    # single-rule clean match
    assert classify("check my outlook inbox").confidence == 0.9
    # multi-rule mix (no briefing)
    multi = classify("any email about the calendar invite then research the topic")
    assert multi.confidence == 0.7
    # multi-domain briefing keyword bumps to 0.85
    assert classify("morning briefing please").confidence == 0.85


def test_watchlist_routes_to_atlas():
    """``add Nvidia to my watchlist`` -> atlas with add_to_watchlist action."""
    c = classify("add Nvidia to my watchlist")
    assert c.primary == "atlas"
    assert c.action == "add_to_watchlist"


def test_overdue_fans_to_tempo_and_scholar():
    """An ``overdue`` query fans out to tempo + scholar -- both surface items."""
    c = classify("is anything overdue?")
    targets = {c.primary, *c.parallel}
    assert c.primary in {"tempo", "scholar"}
    assert "tempo" in targets
    assert "scholar" in targets


def test_pause_trader_routes_correctly():
    """``pause the trader`` -> atlas, action=pause_agent (confirmation-gated)."""
    c = classify("pause the trader")
    assert c.primary == "atlas"
    assert c.action == "pause_agent"


def test_add_assignment_action():
    """``add CS401 homework due Friday`` -> scholar, add_assignment (not list)."""
    c = classify("add CS401 homework due Friday")
    assert c.primary == "scholar"
    assert c.action == "add_assignment"


def test_todo_in_codebase_routes_to_forge():
    """``TODO in our codebase`` -> forge, NOT tempo's todo rule."""
    c = classify("is there a TODO in our codebase about timeouts")
    assert c.primary == "forge"


def test_primary_by_earliest_mention():
    """Primary chosen by earliest match position in request text."""
    c = classify("check inbox and tell me about my BTC position")
    assert c.primary == "tempo"
    assert "atlas" in c.parallel


def test_confidence_tiers_match_rule_strength():
    """Confidence ladder: empty 0.0 -> unmatched 0.3 -> multi 0.7/0.85 -> single 0.9."""
    assert classify("").confidence == 0.0
    assert classify("blarp the quux").confidence == 0.3
    assert classify("check my outlook inbox").confidence == 0.9
    multi = classify("any email about the calendar invite then research the topic")
    assert multi.confidence == 0.7
    assert classify("morning briefing please").confidence == 0.85
