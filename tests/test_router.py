"""Intent classifier tests."""
from __future__ import annotations

import pytest

from jarvis.router import classify


@pytest.mark.parametrize("request_text,expected", [
    ("check my inbox", "aide"),
    ("draft a reply to Bob", "aide"),
    ("what's on my calendar today", "chronos"),
    ("schedule a meeting Tuesday 3pm", "chronos"),
    ("add a todo to call dentist", "chronos"),
    ("research the new Anthropic model", "sherlock"),
    ("look up FastAPI middleware patterns", "sherlock"),
    ("fix the bug in atlas/api/main.py", "forge"),
    ("ship the new feature to repo X", "forge"),
    ("what's my portfolio doing", "ledger"),
    ("any open positions in ATLAS", "ledger"),
    ("reply to that slack DM", "echo"),
])
def test_single_agent_routing(request_text: str, expected: str):
    c = classify(request_text)
    assert c.primary == expected
    assert c.confidence >= 0.7


def test_briefing_multi_dispatch():
    c = classify("give me my morning briefing")
    assert c.primary == "aide"
    assert "chronos" in c.parallel
    assert "ledger" in c.parallel


def test_empty_request():
    c = classify("")
    assert c.primary == "jarvis"
    assert c.confidence == 0.0


def test_unmatched_falls_to_jarvis():
    c = classify("tell me a joke about ducks")
    assert c.primary == "jarvis"
    assert c.confidence < 0.5


def test_multi_rule_match_picks_primary_and_parallel():
    # 'email' + 'calendar' both hit
    c = classify("any email about the calendar invite")
    assert c.primary == "aide"
    assert "chronos" in c.parallel
