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
