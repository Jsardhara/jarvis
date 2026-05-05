"""Eval harness for the regex-based router — 50-sample corpus, ≥80% required.

The LLM router was removed (Pro/Max plan budget reasons). The regex
classifier is now the only entry point, so this corpus doubles as the
acceptance gate for routing accuracy.
"""
from __future__ import annotations

from jarvis.router import classify

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


def test_eval_regex_baseline() -> None:
    """Regex-only classify must hit ≥80% on the eval corpus."""
    correct = 0
    failures: list[tuple[str, str, str]] = []
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
    assert pass_rate >= 0.80, (
        f"Regex eval pass rate {pass_rate:.0%} ({correct}/50) < 80%.\n"
        f"Failures:\n{failure_summary}"
    )
