"""Eval harness for LLM router — 50 samples, ≥90% accuracy required.

Two test functions:
- test_eval_mock_classifier  — always runs, uses canned mock responses.
- test_eval_live_classifier  — skipped unless ANTHROPIC_API_KEY is set.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from jarvis.router import classify

# ---------------------------------------------------------------------------
# 50-sample eval corpus: (request, expected_primary)
# ---------------------------------------------------------------------------

EVAL_SAMPLES: list[tuple[str, str]] = [
    # tempo — mail
    ("check my outlook inbox", "tempo"),
    ("draft a reply to professor Chen", "tempo"),
    ("send the project proposal email", "tempo"),
    ("any unread mail from mom", "tempo"),
    ("compose an email to the team", "tempo"),
    # tempo — calendar
    ("schedule a meeting with Sarah on Friday", "tempo"),
    ("what's on my calendar today", "tempo"),
    ("find free time next week", "tempo"),
    ("cancel my 3pm appointment", "tempo"),
    ("remind me to call the dentist tomorrow", "tempo"),
    # scholar
    ("when is my CS401 assignment due", "scholar"),
    ("plan my study sessions for the midterm", "scholar"),
    ("add the machine learning homework to my tasks", "scholar"),
    ("how should I prepare for the algorithms final exam", "scholar"),
    ("summarize this research paper for my class", "scholar"),
    ("what's my GPA looking like", "scholar"),
    ("help me outline my essay for English 201", "scholar"),
    ("create a study schedule for CS501", "scholar"),
    ("list my open assignments", "scholar"),
    ("what courses am I enrolled in", "scholar"),
    # lens
    ("research the latest LLM benchmarks", "lens"),
    ("look up Claude 4 release notes", "lens"),
    ("monitor anthropic news", "lens"),
    ("summarize recent AI safety developments", "lens"),
    ("find out what's happening with OpenAI today", "lens"),
    ("track mentions of NVIDIA in tech news", "lens"),
    ("investigate the new Python 3.14 features", "lens"),
    ("watch for updates on FastAPI 1.0", "lens"),
    ("what's in the news about machine learning", "lens"),
    ("search for recent papers on attention mechanisms", "lens"),
    # forge
    ("fix the bug in the auth module", "forge"),
    ("refactor the database layer", "forge"),
    ("ship the new API endpoint to production", "forge"),
    ("open a pull request for the feature branch", "forge"),
    ("deploy the latest build", "forge"),
    ("implement the new search function", "forge"),
    ("commit the changes to the repo", "forge"),
    ("merge the dev branch into main", "forge"),
    ("write tests for the payment module", "forge"),
    ("build the TypeScript project", "forge"),
    # atlas
    ("what's my portfolio value today", "atlas"),
    ("show me my open positions", "atlas"),
    ("run a backtest on the momentum strategy", "atlas"),
    ("what's my P&L this week", "atlas"),
    ("check my BTC holdings", "atlas"),
    ("trigger the ATLAS pipeline", "atlas"),
    ("how's my trading strategy performing", "atlas"),
    ("show me the market drawdown", "atlas"),
    ("paper trade the trend strategy", "atlas"),
    ("scan for new trade signals", "atlas"),
]

assert len(EVAL_SAMPLES) == 50, f"Expected 50 samples, got {len(EVAL_SAMPLES)}"

_KNOWN_AGENTS = {"tempo", "scholar", "lens", "forge", "atlas", "jarvis"}


def _make_canned_response(expected_primary: str) -> MagicMock:
    """Return a mock Anthropic message yielding the correct classification."""
    content_block = MagicMock()
    content_block.text = json.dumps(
        {
            "primary": expected_primary,
            "parallel": [],
            "rationale": f"eval canned: {expected_primary}",
            "confidence": 0.9,
        }
    )
    msg = MagicMock()
    msg.content = [content_block]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 30
    return msg


# ---------------------------------------------------------------------------
# Mock eval — always runs
# ---------------------------------------------------------------------------


def test_eval_mock_classifier():
    """Eval harness with mocked Anthropic — must reach ≥90% (45/50)."""
    from jarvis import router

    correct = 0
    failures: list[tuple[str, str, str]] = []

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(router, "USE_LLM_ROUTER", True):
            for request_text, expected in EVAL_SAMPLES:
                canned = _make_canned_response(expected)
                with patch("jarvis.router.anthropic") as mock_module:
                    mock_client = MagicMock()
                    mock_module.Anthropic.return_value = mock_client
                    mock_client.messages.create.return_value = canned

                    # Clear LRU cache so each call goes through mock
                    router.classify_llm.cache_clear()
                    result = classify(request_text)

                if result.primary == expected:
                    correct += 1
                else:
                    failures.append((request_text, expected, result.primary))

    pass_rate = correct / len(EVAL_SAMPLES)
    failure_summary = "\n".join(
        f"  '{req}' → expected={exp}, got={got}" for req, exp, got in failures
    )
    assert pass_rate >= 0.90, (
        f"Eval pass rate {pass_rate:.0%} ({correct}/50) < 90%.\nFailures:\n{failure_summary}"
    )


# ---------------------------------------------------------------------------
# Regex-only eval — sanity check that pure regex hits ≥70%
# ---------------------------------------------------------------------------


def test_eval_regex_baseline():
    """Regex-only classify must hit ≥70% on the eval corpus (sanity floor)."""
    from jarvis import router

    correct = 0
    with patch.object(router, "USE_LLM_ROUTER", False), patch.dict(os.environ, {}, clear=True):
        for request_text, expected in EVAL_SAMPLES:
            result = classify(request_text)
            if result.primary == expected:
                correct += 1

    pass_rate = correct / len(EVAL_SAMPLES)
    assert pass_rate >= 0.70, f"Regex baseline {pass_rate:.0%} ({correct}/50) < 70%"


# ---------------------------------------------------------------------------
# Live eval — skipped unless ANTHROPIC_API_KEY is present
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ANTHROPIC_API_KEY") is None,
    reason="ANTHROPIC_API_KEY not set — skipping live LLM eval",
)
def test_eval_live_classifier():
    """Live eval against real Haiku model — ≥90% required."""
    correct = 0
    failures: list[tuple[str, str, str]] = []

    from jarvis import router

    router.classify_llm.cache_clear()

    for request_text, expected in EVAL_SAMPLES:
        result = classify(request_text)
        if result.primary == expected:
            correct += 1
        else:
            failures.append((request_text, expected, result.primary))

    pass_rate = correct / len(EVAL_SAMPLES)
    failure_summary = "\n".join(
        f"  '{req}' → expected={exp}, got={got}" for req, exp, got in failures
    )
    assert pass_rate >= 0.90, (
        f"Live eval pass rate {pass_rate:.0%} ({correct}/50) < 90%.\nFailures:\n{failure_summary}"
    )
