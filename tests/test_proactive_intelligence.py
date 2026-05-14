"""Tests for J8 — proactive intelligence pass.

All five tests mock ``jarvis.llm.queue.submit`` so no live LLM call is made.
The fixture in ``conftest.py`` already isolates state to ``tmp_path`` per
test, so dedup/fire-log assertions are deterministic.
"""
from __future__ import annotations

from unittest.mock import patch

from jarvis.apps.sentinel.proactive_intelligence import run_proactive_pass
from jarvis.state import read_inbox

# Patch site — proactive_intelligence imported submit at module load time,
# so we patch the rebound name on that module, not on jarvis.llm.queue.
_SUBMIT_PATH = "jarvis.apps.sentinel.proactive_intelligence.submit"


def _reply(*observations: dict[str, str]) -> str:
    """Build a JSON-array reply mimicking the LLM output."""
    import json

    return json.dumps(list(observations))


def test_emits_inbox_events_for_each_observation() -> None:
    """Two observations from the LLM → two InboxEvents appended."""
    reply = _reply(
        {
            "observation": "3 tasks mention Q3 — draft a status update",
            "suggestion": "Draft Q3 status",
            "severity": "info",
        },
        {
            "observation": "Project Atlas had no activity for 4 days",
            "suggestion": "Ping Atlas owner",
            "severity": "warn",
        },
    )
    with patch(_SUBMIT_PATH, return_value=reply):
        events = run_proactive_pass()

    assert len(events) == 2
    inbox = read_inbox(limit=10)
    summaries = [e.summary for e in inbox if e.agent == "jarvis"]
    assert "3 tasks mention Q3 — draft a status update" in summaries
    assert "Project Atlas had no activity for 4 days" in summaries
    severities = {e.summary: e.severity for e in inbox if e.agent == "jarvis"}
    assert severities["Project Atlas had no activity for 4 days"] == "warn"
    refs = {e.summary: e.ref for e in inbox if e.agent == "jarvis"}
    assert refs["3 tasks mention Q3 — draft a status update"]["kind"] == (
        "proactive_intelligence"
    )
    assert refs["3 tasks mention Q3 — draft a status update"]["suggestion"] == (
        "Draft Q3 status"
    )


def test_caps_at_max_observations() -> None:
    """LLM returns 5 observations — emitter caps to default max_observations=3."""
    reply = _reply(
        *[
            {
                "observation": f"observation number {i}",
                "suggestion": f"do thing {i}",
                "severity": "info",
            }
            for i in range(5)
        ]
    )
    with patch(_SUBMIT_PATH, return_value=reply):
        events = run_proactive_pass()

    assert len(events) == 3
    inbox_summaries = [
        e.summary for e in read_inbox(limit=20) if e.agent == "jarvis"
    ]
    assert len(inbox_summaries) == 3


def test_handles_markdown_fence() -> None:
    """Reply wrapped in ```json … ``` fence — parser strips it cleanly."""
    inner = _reply(
        {
            "observation": "Watchlist overlaps with this morning's news",
            "suggestion": "Skim lens digest",
            "severity": "info",
        }
    )
    fenced = f"```json\n{inner}\n```"
    with patch(_SUBMIT_PATH, return_value=fenced):
        events = run_proactive_pass()

    assert len(events) == 1
    assert events[0].summary == "Watchlist overlaps with this morning's news"


def test_dedups_recent_observations() -> None:
    """Same observations on a second call → emits 0 (7-day dedup window)."""
    reply = _reply(
        {
            "observation": "Task X stale for a week",
            "suggestion": "Close or revive",
            "severity": "warn",
        },
        {
            "observation": "Inbox / calendar conflict tomorrow",
            "suggestion": "Move 2pm meeting",
            "severity": "info",
        },
    )
    with patch(_SUBMIT_PATH, return_value=reply):
        first = run_proactive_pass()
    assert len(first) == 2

    with patch(_SUBMIT_PATH, return_value=reply):
        second = run_proactive_pass()
    assert len(second) == 0


def test_empty_response_emits_nothing() -> None:
    """LLM returns ``"[]"`` — no events emitted, no exceptions raised."""
    with patch(_SUBMIT_PATH, return_value="[]"):
        events = run_proactive_pass()

    assert events == []
    jarvis_events = [e for e in read_inbox(limit=20) if e.agent == "jarvis"]
    assert jarvis_events == []
