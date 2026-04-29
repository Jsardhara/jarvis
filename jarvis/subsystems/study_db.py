"""SQLAlchemy 2.0 models for the Study Companion.

DB lives at state/study.db (path resolved via JARVIS_STATE_DIR or project root).
Call ``init_db()`` once at startup, then use ``get_session()`` for all access.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


def _db_path() -> Path:
    state_dir = os.environ.get("JARVIS_STATE_DIR")
    if state_dir:
        p = Path(state_dir)
    else:
        p = Path(__file__).resolve().parents[2] / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p / "study.db"


def _engine():  # type: ignore[return]
    url = f"sqlite:///{_db_path()}"
    return create_engine(url, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class StudyDocument(Base):
    __tablename__ = "study_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    summaries: Mapped[list[StudySummary]] = relationship(
        "StudySummary", back_populates="document", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list[StudyFlashcard]] = relationship(
        "StudyFlashcard", back_populates="document", cascade="all, delete-orphan"
    )


class StudySummary(Base):
    __tablename__ = "study_summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, ForeignKey("study_documents.id"), nullable=False)
    tldr: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_concepts: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    important_points: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped[StudyDocument] = relationship("StudyDocument", back_populates="summaries")


class StudyFlashcard(Base):
    __tablename__ = "study_flashcards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String, ForeignKey("study_documents.id"), nullable=False)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # SM-2 fields
    ease_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped[StudyDocument] = relationship("StudyDocument", back_populates="flashcards")
    review_logs: Mapped[list[StudyReviewLog]] = relationship(
        "StudyReviewLog", back_populates="card", cascade="all, delete-orphan"
    )


class StudyReviewLog(Base):
    __tablename__ = "study_review_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    card_id: Mapped[str] = mapped_column(
        String, ForeignKey("study_flashcards.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    card: Mapped[StudyFlashcard] = relationship("StudyFlashcard", back_populates="review_logs")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_engine_instance = None


def _get_engine():
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = _engine()
    return _engine_instance


def init_db() -> None:
    """Create all tables if they do not exist. Safe to call multiple times."""
    global _engine_instance
    _engine_instance = _engine()
    Base.metadata.create_all(_engine_instance)


def _reset_engine() -> None:
    """For tests: force a new engine on next call (needed when JARVIS_STATE_DIR changes)."""
    global _engine_instance
    _engine_instance = None


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager yielding a SQLAlchemy Session. Auto-commits on success, rolls back on error."""
    engine = _get_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _now() -> datetime:
    return datetime.now(UTC)
