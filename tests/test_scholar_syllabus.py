"""Tests for Scholar.ingest_syllabus — PDF/text → study plan → flashcards + tasks."""
from __future__ import annotations

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PARSED_PLAN = {
    "course_title": "Introduction to Calculus",
    "exam_date_iso": "2026-05-15",
    "exam_window_min": 120,
    "topics": [
        {"name": "Limits", "week": 1, "concept_tags": ["limits", "continuity"]},
        {"name": "Derivatives", "week": 2, "concept_tags": ["derivatives", "chain-rule"]},
        {"name": "Integrals", "week": 3, "concept_tags": ["integrals", "ftc"]},
    ],
    "weekly_plan": [
        {"week": 1, "focus": "Limits and continuity", "study_minutes_per_day": 45},
        {"week": 2, "focus": "Derivatives and rules", "study_minutes_per_day": 60},
        {"week": 3, "focus": "Integration techniques", "study_minutes_per_day": 75},
    ],
    "key_dates": [
        {"label": "Midterm 1", "date_iso": "2026-04-15"},
        {"label": "Final Exam", "date_iso": "2026-05-15"},
    ],
}

_SYLLABUS_TEXT = b"Introduction to Calculus syllabus. Week 1: Limits. Week 2: Derivatives."


@pytest.fixture()
def scholar_env(tmp_path):
    """Isolated Scholar instance with tmp state dir and reset study DB."""
    os.environ["JARVIS_STATE_DIR"] = str(tmp_path)
    from jarvis.agents.scholar.db import _reset_engine, init_db

    _reset_engine()
    init_db()
    yield tmp_path
    _reset_engine()
    os.environ.pop("JARVIS_STATE_DIR", None)


@pytest.fixture()
def scholar(scholar_env):
    from jarvis.agents.scholar.agent import Scholar

    return Scholar()


@pytest.fixture()
def mock_tempo():
    tempo = MagicMock()
    tempo.add.return_value = MagicMock()
    return tempo


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------


def test_safe_filename_plain():
    from jarvis.agents.scholar.agent import _safe_filename

    assert _safe_filename("Linear Algebra") == "Linear_Algebra"


def test_safe_filename_special_chars():
    from jarvis.agents.scholar.agent import _safe_filename

    assert _safe_filename("Calc 101: Advanced!") == "Calc_101_Advanced"


def test_safe_filename_unicode():
    from jarvis.agents.scholar.agent import _safe_filename

    result = _safe_filename("Álgebra Lineal")
    assert result  # not empty
    assert "/" not in result
    assert "\\" not in result


def test_safe_filename_empty():
    from jarvis.agents.scholar.agent import _safe_filename

    assert _safe_filename("   ") == "untitled"


def test_safe_filename_leading_trailing_underscores():
    from jarvis.agents.scholar.agent import _safe_filename

    result = _safe_filename("!!course!!")
    assert not result.startswith("_")
    assert not result.endswith("_")


# ---------------------------------------------------------------------------
# ingest_syllabus — happy path
# ---------------------------------------------------------------------------


def test_ingest_syllabus_returns_agent_response(scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    assert resp.agent == "scholar"
    assert resp.intent == "ingest_syllabus"
    assert resp.action == "ingested"


def test_ingest_syllabus_result_fields(scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    result = resp.result
    assert result["course"] == "Calculus"
    assert result["course_title"] == "Introduction to Calculus"
    assert result["exam_date_iso"] == "2026-05-15"
    assert result["topics_count"] == 3
    assert result["weekly_plan_weeks"] == 3
    assert len(result["key_dates"]) == 2
    assert result["cards_imported"] == 3
    assert result["tasks_created"] == 3
    assert result["deck_doc_id"]


def test_ingest_syllabus_persists_plan_to_state(scholar_env, scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    syllabi_dir = scholar_env / "scholar_syllabi"
    assert syllabi_dir.exists()
    saved_files = list(syllabi_dir.glob("*.json"))
    assert len(saved_files) == 1
    saved = json.loads(saved_files[0].read_text())
    assert saved["course_title"] == "Introduction to Calculus"


def test_ingest_syllabus_creates_flashcards(scholar_env, scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    # Verify cards exist in DB
    from sqlalchemy import select

    from jarvis.agents.scholar.db import StudyFlashcard, get_session

    with get_session() as session:
        cards = session.scalars(
            select(StudyFlashcard).where(StudyFlashcard.doc_id == resp.result["deck_doc_id"])
        ).all()
        fronts = [c.front for c in cards]

    assert len(fronts) == 3
    assert any("Limits" in f for f in fronts)
    assert any("Derivatives" in f for f in fronts)
    assert any("Integrals" in f for f in fronts)


def test_ingest_syllabus_card_tags_include_course(scholar_env, scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    from sqlalchemy import select

    from jarvis.agents.scholar.db import StudyFlashcard, get_session

    with get_session() as session:
        cards = session.scalars(
            select(StudyFlashcard).where(StudyFlashcard.doc_id == resp.result["deck_doc_id"])
        ).all()
        all_tags = [json.loads(c.tags) for c in cards]

    for tags in all_tags:
        assert "course:Calculus" in tags


def test_ingest_syllabus_calls_tempo_add(scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    # One add() call per weekly_plan entry
    assert mock_tempo.add.call_count == 3
    call_titles = [call.kwargs.get("title") or call.args[0] for call in mock_tempo.add.call_args_list]
    assert any("Limits and continuity" in t for t in call_titles)


def test_ingest_syllabus_no_tempo_no_crash(scholar):
    """When tempo=None, tasks_created=0 and no exception raised."""
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
        )

    assert resp.result["tasks_created"] == 0


def test_ingest_syllabus_fires_inbox_events(scholar_env, scholar, mock_tempo):
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = json.dumps(_PARSED_PLAN)

        scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    from jarvis.state import read_inbox

    events = read_inbox(limit=50)
    summaries = [e.summary for e in events]
    assert any("Midterm 1" in s for s in summaries)
    assert any("Final Exam" in s for s in summaries)


def test_ingest_syllabus_claude_json_fence_tolerance(scholar_env, scholar, mock_tempo):
    """Claude occasionally wraps JSON in fences despite the prompt; parser must handle it."""
    content_b64 = base64.b64encode(_SYLLABUS_TEXT).decode()
    fenced = f"```json\n{json.dumps(_PARSED_PLAN)}\n```"

    with patch("jarvis.agents.scholar.agent._query_claude") as mock_claude, patch(
        "jarvis.agents.scholar.study._extract_text"
    ) as mock_extract:
        mock_extract.return_value = (_SYLLABUS_TEXT.decode(), 1)
        mock_claude.return_value = fenced

        resp = scholar.ingest_syllabus(
            filename="calculus.txt",
            content_b64=content_b64,
            course="Calculus",
            tempo=mock_tempo,
        )

    assert resp.result["topics_count"] == 3


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def test_registry_has_ingest_syllabus():
    """Scholar AgentDescriptor exposes ingest_syllabus action."""
    from unittest.mock import MagicMock, patch

    with patch("jarvis.agents.registry._build_outlook"), patch(
        "jarvis.agents.registry.build_default_tempo_stack"
    ), patch("jarvis.agents.registry.AtlasBridge"), patch(
        "jarvis.agents.registry.AtlasOrchestrator"
    ) as mock_atlas_cls:
        mock_atlas = MagicMock()
        mock_atlas._health_check.return_value = False
        mock_atlas_cls.return_value = mock_atlas

        from jarvis.agents.registry import build_default_registry

        reg = build_default_registry()

    assert "ingest_syllabus" in reg["scholar"].actions
