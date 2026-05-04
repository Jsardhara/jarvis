"""Study Companion service — document storage, AI summarisation, flashcard SM-2.

All public methods return plain dicts/lists, not AgentResponse.
The Scholar class wraps these in AgentResponse envelopes.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from .study_db import (
    StudyDocument,
    StudyFlashcard,
    StudyReviewLog,
    StudySummary,
    _now,
    get_session,
)

log = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Return Anthropic API key.

    Priority:
    1. ANTHROPIC_API_KEY env var (explicit override)
    2. accessToken from ~/.claude/.credentials.json (same source as claude-agent-sdk)
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    creds = Path.home() / ".claude" / ".credentials.json"
    if creds.exists():
        try:
            data = json.loads(creds.read_text())
            token = data.get("claudeAiOauth", {}).get("accessToken", "")
            if token:
                return token
        except Exception:
            pass
    raise RuntimeError(
        "No Anthropic API key found. Set ANTHROPIC_API_KEY or log in via Claude Code."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RATING_AGAIN = 0
_RATING_HARD = 1
_RATING_GOOD = 2
_RATING_EASY = 3


def _today_iso() -> str:
    return date.today().isoformat()


def _doc_to_dict(doc: StudyDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "filename": doc.filename,
        "page_count": doc.page_count,
        "content_text": doc.content_text,
        "created_at": doc.created_at.isoformat(),
    }


def _summary_to_dict(s: StudySummary) -> dict[str, Any]:
    return {
        "id": s.id,
        "doc_id": s.doc_id,
        "tldr": s.tldr,
        "key_concepts": json.loads(s.key_concepts),
        "important_points": json.loads(s.important_points),
        "created_at": s.created_at.isoformat(),
    }


def _card_to_dict(c: StudyFlashcard) -> dict[str, Any]:
    return {
        "id": c.id,
        "doc_id": c.doc_id,
        "front": c.front,
        "back": c.back,
        "source_page": c.source_page,
        "tags": json.loads(c.tags),
        "ease_factor": c.ease_factor,
        "interval": c.interval,
        "repetitions": c.repetitions,
        "due_date": c.due_date,
        "created_at": c.created_at.isoformat(),
    }


def _extract_text(filename: str, content_bytes: bytes) -> tuple[str, int]:
    """Return (text, page_count).  Supports PDF (PyMuPDF), TXT, and MD."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content_bytes, filetype="pdf")
            pages = [page.get_text() for page in doc]
            return "\n".join(pages), len(pages)
        except Exception as exc:
            log.warning("PyMuPDF failed for %s: %s", filename, exc)
            return "", 0
    if lower.endswith((".txt", ".md")):
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = content_bytes.decode("utf-8", errors="ignore")
        return text, 1
    raise ValueError(f"unsupported file type: {filename}")


# ---------------------------------------------------------------------------
# SM-2 algorithm
# ---------------------------------------------------------------------------


def _apply_sm2(
    ease_factor: float,
    interval: int,
    repetitions: int,
    rating: int,
) -> tuple[float, int, int]:
    """Return (new_ease_factor, new_interval, new_repetitions).

    Rating scale: 0=Again, 1=Hard, 2=Good, 3=Easy.
    """
    if rating == _RATING_AGAIN:
        return ease_factor, 1, 0

    if rating == _RATING_HARD:
        new_ease = max(1.3, ease_factor - 0.15)
        new_interval = max(1, round(interval * 1.2))
        return new_ease, new_interval, repetitions + 1

    # Good (2) or Easy (3)
    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(interval * ease_factor)

    new_ease = ease_factor + 0.15 if rating == _RATING_EASY else ease_factor

    return new_ease, new_interval, repetitions + 1


# ---------------------------------------------------------------------------
# Claude API helpers
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = (
    "You are a study assistant. Analyse the document text provided and return ONLY valid JSON "
    "with this exact shape: "
    '{"tldr": "...", "key_concepts": ["...", ...], "important_points": [{"text": "...", "page": 1}, ...]}'
    ". No markdown fences, no extra keys."
)

_FLASHCARD_SYSTEM = (
    "You are a flashcard generator. Read the document text and produce 15-40 question/answer pairs "
    "as a JSON array. Each element must have exactly: "
    '{"front": "question", "back": "answer", "source_page": <int or null>, "tags": ["tag1", ...]}. '
    "Return ONLY the JSON array. No markdown fences."
)


def _call_claude_summary(text: str, api_key: str) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=_SUMMARY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": "Summarise the document above.",
                    },
                ],
            }
        ],
    )
    raw = response.content[0].text if response.content else "{}"
    return json.loads(raw)


def _call_claude_flashcards(text: str, api_key: str) -> list[dict[str, Any]]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=_FLASHCARD_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": "Generate flashcards for the document above.",
                    },
                ],
            }
        ],
    )
    raw = response.content[0].text if response.content else "[]"
    result = json.loads(raw)
    return result if isinstance(result, list) else []


# ---------------------------------------------------------------------------
# StudyService
# ---------------------------------------------------------------------------


class StudyService:
    """All DB operations for the Study Companion. Returns plain dicts/lists."""

    # ── Documents ────────────────────────────────────────────────────────────

    def upload_document(self, filename: str, content_bytes: bytes) -> dict[str, Any]:
        text, page_count = _extract_text(filename, content_bytes)
        doc_id = uuid4().hex
        title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        now = _now()
        with get_session() as session:
            doc = StudyDocument(
                id=doc_id,
                title=title,
                filename=filename,
                content_text=text,
                page_count=page_count,
                created_at=now,
            )
            session.add(doc)
        return {
            "id": doc_id,
            "title": title,
            "filename": filename,
            "page_count": page_count,
            "content_text": text,
            "created_at": now.isoformat(),
        }

    def list_documents(self) -> list[dict[str, Any]]:
        with get_session() as session:
            rows = session.scalars(
                select(StudyDocument).order_by(StudyDocument.created_at.desc())
            ).all()
            return [_doc_to_dict(r) for r in rows]

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with get_session() as session:
            doc = session.get(StudyDocument, doc_id)
            return _doc_to_dict(doc) if doc else None

    def delete_document(self, doc_id: str) -> bool:
        with get_session() as session:
            doc = session.get(StudyDocument, doc_id)
            if doc is None:
                return False
            session.delete(doc)
        return True

    # ── Summaries ────────────────────────────────────────────────────────────

    def get_summary(self, doc_id: str, api_key: str) -> dict[str, Any]:
        with get_session() as session:
            existing = session.scalars(
                select(StudySummary).where(StudySummary.doc_id == doc_id).limit(1)
            ).first()
            if existing:
                return _summary_to_dict(existing)

            doc = session.get(StudyDocument, doc_id)
            if doc is None:
                raise ValueError(f"document {doc_id!r} not found")

            data = _call_claude_summary(doc.content_text, api_key)
            now = _now()
            summary = StudySummary(
                id=uuid4().hex,
                doc_id=doc_id,
                tldr=data.get("tldr", ""),
                key_concepts=json.dumps(data.get("key_concepts", [])),
                important_points=json.dumps(data.get("important_points", [])),
                created_at=now,
            )
            session.add(summary)
            return _summary_to_dict(summary)

    # ── Flashcards ───────────────────────────────────────────────────────────

    def get_flashcards(self, doc_id: str) -> list[dict[str, Any]]:
        with get_session() as session:
            rows = session.scalars(
                select(StudyFlashcard).where(StudyFlashcard.doc_id == doc_id)
            ).all()
            return [_card_to_dict(r) for r in rows]

    def generate_flashcards(self, doc_id: str, api_key: str) -> list[dict[str, Any]]:
        with get_session() as session:
            doc = session.get(StudyDocument, doc_id)
            if doc is None:
                raise ValueError(f"document {doc_id!r} not found")

            pairs = _call_claude_flashcards(doc.content_text, api_key)
            today = _today_iso()
            now = _now()
            saved: list[dict[str, Any]] = []
            for pair in pairs:
                card = StudyFlashcard(
                    id=uuid4().hex,
                    doc_id=doc_id,
                    front=str(pair.get("front", "")),
                    back=str(pair.get("back", "")),
                    source_page=pair.get("source_page"),
                    tags=json.dumps(pair.get("tags", [])),
                    ease_factor=2.5,
                    interval=1,
                    repetitions=0,
                    due_date=today,
                    created_at=now,
                )
                session.add(card)
                saved.append(_card_to_dict(card))
            return saved

    def rate_card(self, card_id: str, rating: int) -> dict[str, Any]:
        if rating not in (0, 1, 2, 3):
            raise ValueError(f"rating must be 0-3, got {rating}")
        now = _now()
        with get_session() as session:
            card = session.get(StudyFlashcard, card_id)
            if card is None:
                raise ValueError(f"card {card_id!r} not found")

            new_ease, new_interval, new_reps = _apply_sm2(
                card.ease_factor, card.interval, card.repetitions, rating
            )
            card.ease_factor = new_ease
            card.interval = new_interval
            card.repetitions = new_reps
            due = (date.today() + timedelta(days=new_interval)).isoformat()
            card.due_date = due

            log_entry = StudyReviewLog(
                id=uuid4().hex,
                card_id=card_id,
                rating=rating,
                reviewed_at=now,
            )
            session.add(log_entry)
            return _card_to_dict(card)

    def due_cards(self) -> list[dict[str, Any]]:
        today = _today_iso()
        with get_session() as session:
            rows = session.scalars(
                select(StudyFlashcard)
                .where(StudyFlashcard.due_date <= today)
                .order_by(StudyFlashcard.due_date.asc())
            ).all()
            return [_card_to_dict(r) for r in rows]
