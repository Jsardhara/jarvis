"""Tests for Study Companion backend — StudyService, SM-2 algorithm, API routes."""
from __future__ import annotations

import os
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# StudyService unit tests (no FastAPI needed)
# ---------------------------------------------------------------------------


@pytest.fixture()
def study_svc(tmp_path):
    """Return a StudyService backed by a temp SQLite DB."""
    os.environ["JARVIS_STATE_DIR"] = str(tmp_path)
    from jarvis.subsystems.study_db import _reset_engine, init_db

    _reset_engine()
    init_db()
    from jarvis.subsystems.scholar_study import StudyService

    yield StudyService()
    # cleanup
    _reset_engine()
    os.environ.pop("JARVIS_STATE_DIR", None)


# ── upload_document ──────────────────────────────────────────────────────────


def test_upload_txt_document(study_svc):
    content = b"Linear algebra is the study of vectors and matrices."
    doc = study_svc.upload_document("notes.txt", content)
    assert doc["filename"] == "notes.txt"
    assert doc["title"] == "notes"
    assert "vectors" in doc["content_text"]
    assert doc["page_count"] == 1


def test_upload_md_document(study_svc):
    content = b"# Chapter 1\n\nEigenvalues are special scalars."
    doc = study_svc.upload_document("chapter.md", content)
    assert doc["page_count"] == 1
    assert "Eigenvalues" in doc["content_text"]


def test_upload_unsupported_type_raises(study_svc):
    with pytest.raises(ValueError, match="unsupported file type"):
        study_svc.upload_document("image.png", b"\x89PNG\r\n")


# ── list / get / delete ──────────────────────────────────────────────────────


def test_list_documents_empty(study_svc):
    assert study_svc.list_documents() == []


def test_list_documents_after_upload(study_svc):
    study_svc.upload_document("a.txt", b"Alpha content")
    study_svc.upload_document("b.txt", b"Beta content")
    docs = study_svc.list_documents()
    assert len(docs) == 2


def test_get_document_not_found(study_svc):
    assert study_svc.get_document("nonexistent") is None


def test_delete_document(study_svc):
    doc = study_svc.upload_document("del.txt", b"To be deleted")
    assert study_svc.delete_document(doc["id"]) is True
    assert study_svc.get_document(doc["id"]) is None


def test_delete_nonexistent_returns_false(study_svc):
    assert study_svc.delete_document("ghost") is False


# ── get_summary (mocked Claude) ──────────────────────────────────────────────


def test_get_summary_calls_claude_and_caches(study_svc):
    doc = study_svc.upload_document("lecture.txt", b"Vector spaces are fundamental.")

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"tldr":"Vectors matter.","key_concepts":["vector space"],"important_points":[{"text":"Basis","page":1}]}'
        )
    ]

    with patch("jarvis.subsystems.scholar_study._call_claude_summary") as mock_call:
        mock_call.return_value = {
            "tldr": "Vectors matter.",
            "key_concepts": ["vector space"],
            "important_points": [{"text": "Basis", "page": 1}],
        }
        summary1 = study_svc.get_summary(doc["id"], "fake-key")
        summary2 = study_svc.get_summary(doc["id"], "fake-key")

    assert mock_call.call_count == 1  # cached on second call
    assert summary1["tldr"] == "Vectors matter."
    assert summary2["id"] == summary1["id"]


def test_get_summary_missing_doc_raises(study_svc):
    with pytest.raises(ValueError, match="not found"):
        study_svc.get_summary("ghost", "fake-key")


# ── generate_flashcards (mocked Claude) ──────────────────────────────────────


def test_generate_flashcards(study_svc):
    doc = study_svc.upload_document("cards.txt", b"Matrices encode linear maps.")

    with patch("jarvis.subsystems.scholar_study._call_claude_flashcards") as mock_call:
        mock_call.return_value = [
            {"front": "What is a matrix?", "back": "A rectangular array.", "source_page": 1, "tags": ["linear-algebra"]},
            {"front": "What is a vector?", "back": "An element of a vector space.", "source_page": None, "tags": []},
        ]
        cards = study_svc.generate_flashcards(doc["id"], "fake-key")

    assert len(cards) == 2
    assert cards[0]["front"] == "What is a matrix?"
    assert cards[0]["ease_factor"] == 2.5
    assert cards[0]["interval"] == 1
    assert cards[0]["repetitions"] == 0


def test_generate_flashcards_missing_doc_raises(study_svc):
    with pytest.raises(ValueError, match="not found"):
        study_svc.generate_flashcards("ghost", "fake-key")


# ── SM-2 rate_card ───────────────────────────────────────────────────────────


def _make_card(study_svc, doc_id: str) -> dict:
    with patch("jarvis.subsystems.scholar_study._call_claude_flashcards") as mock_call:
        mock_call.return_value = [
            {"front": "Q", "back": "A", "source_page": None, "tags": []}
        ]
        cards = study_svc.generate_flashcards(doc_id, "fake-key")
    return cards[0]


def test_rate_card_again_resets(study_svc):
    doc = study_svc.upload_document("sm2.txt", b"SM-2 algorithm test content.")
    card = _make_card(study_svc, doc["id"])
    updated = study_svc.rate_card(card["id"], 0)  # Again
    assert updated["interval"] == 1
    assert updated["repetitions"] == 0
    assert updated["due_date"] == (date.today() + timedelta(days=1)).isoformat()


def test_rate_card_good_increments(study_svc):
    doc = study_svc.upload_document("sm2b.txt", b"Good rating test.")
    card = _make_card(study_svc, doc["id"])
    updated = study_svc.rate_card(card["id"], 2)  # Good, first rep
    assert updated["repetitions"] == 1
    assert updated["interval"] == 1


def test_rate_card_good_second_rep(study_svc):
    doc = study_svc.upload_document("sm2c.txt", b"Second rep test.")
    card = _make_card(study_svc, doc["id"])
    study_svc.rate_card(card["id"], 2)  # rep 0 → 1
    updated = study_svc.rate_card(card["id"], 2)  # rep 1 → 2
    assert updated["interval"] == 6


def test_rate_card_easy_increases_ease(study_svc):
    doc = study_svc.upload_document("sm2d.txt", b"Easy rating test.")
    card = _make_card(study_svc, doc["id"])
    updated = study_svc.rate_card(card["id"], 3)  # Easy
    assert updated["ease_factor"] == pytest.approx(2.65)


def test_rate_card_hard_decreases_ease(study_svc):
    doc = study_svc.upload_document("sm2e.txt", b"Hard rating test.")
    card = _make_card(study_svc, doc["id"])
    updated = study_svc.rate_card(card["id"], 1)  # Hard
    assert updated["ease_factor"] == pytest.approx(2.35)


def test_rate_card_invalid_rating_raises(study_svc):
    doc = study_svc.upload_document("sm2f.txt", b"Invalid rating test.")
    card = _make_card(study_svc, doc["id"])
    with pytest.raises(ValueError, match="rating must be 0-3"):
        study_svc.rate_card(card["id"], 5)


# ── due_cards ────────────────────────────────────────────────────────────────


def test_due_cards_returns_new_cards(study_svc):
    doc = study_svc.upload_document("due.txt", b"Due cards test content.")
    with patch("jarvis.subsystems.scholar_study._call_claude_flashcards") as mock_call:
        mock_call.return_value = [
            {"front": "Due Q", "back": "Due A", "source_page": None, "tags": []}
        ]
        study_svc.generate_flashcards(doc["id"], "fake-key")
    due = study_svc.due_cards()
    assert len(due) == 1
    assert due[0]["front"] == "Due Q"


def test_due_cards_empty_after_good_rating(study_svc):
    doc = study_svc.upload_document("due2.txt", b"Due after rating test.")
    with patch("jarvis.subsystems.scholar_study._call_claude_flashcards") as mock_call:
        mock_call.return_value = [
            {"front": "Q2", "back": "A2", "source_page": None, "tags": []}
        ]
        cards = study_svc.generate_flashcards(doc["id"], "fake-key")
    study_svc.rate_card(cards[0]["id"], 2)  # Good → due tomorrow
    due = study_svc.due_cards()
    assert len(due) == 0


# ---------------------------------------------------------------------------
# FastAPI route tests
# ---------------------------------------------------------------------------

fastapi_mod = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.web.api import make_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    os.environ["JARVIS_STATE_DIR"] = str(tmp_path)
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")
    from jarvis.subsystems.study_db import _reset_engine

    _reset_engine()
    app = make_app()
    with TestClient(app) as c:
        yield c
    _reset_engine()
    os.environ.pop("JARVIS_STATE_DIR", None)


def test_api_upload_and_list(client):
    resp = client.post(
        "/api/scholar/documents",
        files={"file": ("notes.txt", b"API test content.", "text/plain")},
    )
    assert resp.status_code == 200
    doc = resp.json()["data"]
    assert doc["filename"] == "notes.txt"

    resp2 = client.get("/api/scholar/documents")
    assert resp2.status_code == 200
    assert len(resp2.json()["data"]) == 1


def test_api_get_missing_doc(client):
    resp = client.get("/api/scholar/documents/ghost")
    assert resp.status_code == 404


def test_api_delete_doc(client):
    resp = client.post(
        "/api/scholar/documents",
        files={"file": ("del.txt", b"Delete me.", "text/plain")},
    )
    doc_id = resp.json()["data"]["id"]
    del_resp = client.delete(f"/api/scholar/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert client.get(f"/api/scholar/documents/{doc_id}").status_code == 404


def test_api_due_cards_empty(client):
    resp = client.get("/api/scholar/due")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_api_rate_card(client):
    resp = client.post(
        "/api/scholar/documents",
        files={"file": ("rate.txt", b"Rate me content.", "text/plain")},
    )
    doc_id = resp.json()["data"]["id"]

    with patch("jarvis.subsystems.scholar_study._call_claude_flashcards") as mock_call:
        mock_call.return_value = [
            {"front": "Rate Q", "back": "Rate A", "source_page": None, "tags": []}
        ]
        gen_resp = client.post(f"/api/scholar/documents/{doc_id}/flashcards")

    assert gen_resp.status_code == 200
    card_id = gen_resp.json()["data"][0]["id"]

    rate_resp = client.post(
        f"/api/scholar/flashcards/{card_id}/rate",
        json={"rating": 2},
    )
    assert rate_resp.status_code == 200
    assert rate_resp.json()["data"]["repetitions"] == 1
