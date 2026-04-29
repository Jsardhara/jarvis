"""Scholar — academics and study planning.

Owns: course tracking, assignment planning, study sessions, paper/notes
summarization, exam prep schedules. Pulls due dates from local task store
(Tempo writes them) but plans the WORK around them.

Scholar does NOT manage the calendar — that's Tempo. Scholar produces
study plans which Tempo then schedules.

Study Companion integration lives in ``StudyService`` (scholar_study.py).
Scholar wraps it here and returns ``AgentResponse`` envelopes.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import get_settings
from ..contract import AgentResponse, Task
from ..state import add_task, load_tasks

log = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

_SOLVE_SYSTEM = (
    "You are a step-by-step problem solver. Given a problem, work through it carefully "
    "and return ONLY valid JSON with this exact shape: "
    '{"steps": ["step1", "step2", ...], "final_answer": "...", '
    '"concepts_used": ["concept1", ...], "weak_topic_candidates": []}. '
    "No markdown fences, no extra keys."
)


def _query_claude(system: str, user: str) -> str:
    """One-shot Claude query — delegates to the shared llm.query_claude_sync helper.

    Preserved for back-compat: all scholar code calls this function directly.
    """
    from ..llm import query_claude_sync

    return query_claude_sync(system, user, model=_MODEL)


def _problems_path() -> Path:
    return get_settings().state_dir / "scholar_problems.jsonl"


def _weak_topics_path() -> Path:
    return get_settings().state_dir / "scholar_weak_topics.json"


def _exams_path() -> Path:
    return get_settings().state_dir / "scholar_exams.jsonl"


def _seeds_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "state" / "scholar_seeds"


def _read_problems() -> list[dict[str, Any]]:
    path = _problems_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_problem(record: dict[str, Any]) -> None:
    with _problems_path().open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def _update_problem(problem_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    path = _problems_path()
    records = _read_problems()
    found: dict[str, Any] | None = None
    updated: list[dict[str, Any]] = []
    for r in records:
        if r["id"] == problem_id:
            r = {**r, **updates}
            found = r
        updated.append(r)
    if found is None:
        return None
    with path.open("w") as fh:
        for r in updated:
            fh.write(json.dumps(r) + "\n")
    return found


_GLOBAL_COURSE = "_global"

# Map seed-file slugs to display course names
_SEED_COURSE_MAP: dict[str, str] = {
    "linalg": "Linear Algebra",
    "linalg_exam": "Linear Algebra",
}


def _pretty_course(seed_name: str) -> str:
    """Pretty-print a seed name into a course label."""
    if seed_name in _SEED_COURSE_MAP:
        return _SEED_COURSE_MAP[seed_name]
    return seed_name.replace("_", " ").replace("-", " ").title()


def _course_key(course: str | None) -> str:
    """Normalise a course name for the weak-topics keyspace."""
    return course.strip() if course and course.strip() else _GLOBAL_COURSE


def _load_weak_topics() -> dict[str, dict[str, Any]]:
    """Return weak-topic store keyed by course name.

    Auto-migrates legacy flat shape `{concept: stats}` into
    `{_global: {concept: stats}}` on first read.
    """
    path = _weak_topics_path()
    if not path.exists():
        return {}
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if not raw:
        return {}
    # Legacy flat format detection: any value with miss_count means flat.
    is_flat = any(
        isinstance(v, dict) and "miss_count" in v for v in raw.values()
    )
    if is_flat:
        return {_GLOBAL_COURSE: raw}
    # Already nested by course
    return {k: dict(v) for k, v in raw.items() if isinstance(v, dict)}


def _save_weak_topics(data: dict[str, dict[str, Any]]) -> None:
    _weak_topics_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _top_weak_topics(
    course_slice: dict[str, Any], top_n: int
) -> list[dict[str, Any]]:
    """Return top N entries from a single course's weak-topic slice."""
    items = sorted(
        course_slice.items(),
        key=lambda kv: kv[1].get("miss_count", 0),
        reverse=True,
    )
    return [
        {
            "concept": concept,
            "miss_count": entry.get("miss_count", 0),
            "last_seen": entry.get("last_seen", ""),
            "sample_problem_ids": entry.get("sample_problem_ids", [])[:5],
        }
        for concept, entry in items[:top_n]
    ]


_SYLLABUS_SYSTEM = (
    "You are a syllabus parser. Extract a structured study plan from the syllabus text. "
    "Return ONLY valid JSON with this exact shape: "
    '{"course_title": "...", "exam_date_iso": "YYYY-MM-DD" | null, '
    '"exam_window_min": 60 | null, '
    '"topics": [{"name": "...", "week": 1, "concept_tags": ["..."]}], '
    '"weekly_plan": [{"week": 1, "focus": "...", "study_minutes_per_day": 45}], '
    '"key_dates": [{"label": "...", "date_iso": "YYYY-MM-DD"}]} '
    "No markdown fences, no extra keys."
)


def _safe_filename(name: str) -> str:
    """Sanitize a course name into a filesystem-safe filename component."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "untitled"


def _syllabi_dir() -> Path:
    return get_settings().state_dir / "scholar_syllabi"


@dataclass
class StudyBlock:
    title: str
    minutes: int
    due_iso: str | None = None
    course: str | None = None
    tags: list[str] = field(default_factory=list)


class Scholar:
    """Local-only. No external provider yet — courses and notes live in state."""

    _study_svc: Any = None  # lazy StudyService instance

    def __init__(self, tempo: Any = None) -> None:
        self._tempo = tempo

    # ── Internal ─────────────────────────────────────────────────────────────

    def _svc(self):
        """Lazily instantiate StudyService on first study action."""
        if self._study_svc is None:
            from .scholar_study import StudyService

            self._study_svc = StudyService()
        return self._study_svc

    def _api_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        return key

    # ── Assignments ──────────────────────────────────────────────────────────

    def list_assignments(self) -> AgentResponse:
        """Return open tasks tagged 'school' or 'course:*'."""
        tasks = [
            t
            for t in load_tasks()
            if t.status == "open"
            and any(
                tag.startswith("school") or tag.startswith("course:") for tag in t.tags
            )
        ]
        return AgentResponse(
            agent="scholar",
            intent="list_assignments",
            action="listed",
            result={"assignments": [t.model_dump() for t in tasks], "count": len(tasks)},
            confidence=1.0,
        )

    def add_assignment(
        self, title: str, course: str, due: str | None = None, due_iso: str | None = None
    ) -> AgentResponse:
        """Create a school task.  Accepts ``due`` or ``due_iso`` for the date."""
        effective_due = due or due_iso
        tags = ["school", f"course:{course}"]
        t = Task(title=title, due=effective_due, tags=tags)
        add_task(t)
        return AgentResponse(
            agent="scholar",
            intent="add_assignment",
            action="created",
            result={"assignment": t.model_dump()},
            confidence=1.0,
        )

    def plan_week(self, hours_per_day: float = 3.0) -> AgentResponse:
        """Break open assignments into study blocks across the next 7 days."""
        assignments = [
            t
            for t in load_tasks()
            if t.status == "open"
            and any(
                tag.startswith("school") or tag.startswith("course:") for tag in t.tags
            )
        ]
        plan: list[dict] = []
        now = datetime.now(UTC)
        per_assignment_min = max(30, int((hours_per_day * 60) // max(1, len(assignments))))
        for i, a in enumerate(assignments):
            day_offset = i % 7
            slot_start = (now + timedelta(days=day_offset)).replace(
                hour=18, minute=0, second=0, microsecond=0
            )
            block = StudyBlock(
                title=a.title,
                minutes=per_assignment_min,
                due_iso=a.due,
                course=next(
                    (t.split(":", 1)[1] for t in a.tags if t.startswith("course:")), None
                ),
                tags=a.tags,
            )
            plan.append(
                {
                    "block": block.__dict__,
                    "proposed_start_iso": slot_start.isoformat(),
                }
            )
        return AgentResponse(
            agent="scholar",
            intent="plan_week",
            action="proposed",
            result={"plan": plan, "count": len(plan), "hours_per_day": hours_per_day},
            follow_ups=["confirm to schedule blocks via Tempo"] if plan else [],
            needs_confirm=bool(plan),
            confidence=0.8,
        )

    def summarize(self, title: str, content: str) -> AgentResponse:
        """Stub: real summarization happens in the CC agent prompt with LLM."""
        first_lines = content.strip().splitlines()[:10]
        synopsis = " ".join(first_lines)[:500]
        return AgentResponse(
            agent="scholar",
            intent="summarize",
            action="summarized",
            result={"title": title, "synopsis": synopsis, "length_chars": len(content)},
            confidence=0.5,
        )

    # ── Study Companion wrappers ─────────────────────────────────────────────

    def upload_doc(self, filename: str, content_b64: str) -> AgentResponse:
        """Decode base64 bytes, store document, return document dict."""
        content_bytes = base64.b64decode(content_b64)
        doc = self._svc().upload_document(filename, content_bytes)
        return AgentResponse(
            agent="scholar",
            intent="upload_doc",
            action="stored",
            result={"document": doc},
            confidence=1.0,
        )

    def list_docs(self) -> AgentResponse:
        docs = self._svc().list_documents()
        return AgentResponse(
            agent="scholar",
            intent="list_docs",
            action="listed",
            result={"documents": docs, "count": len(docs)},
            confidence=1.0,
        )

    def get_doc_summary(self, doc_id: str) -> AgentResponse:
        summary = self._svc().get_summary(doc_id, self._api_key())
        return AgentResponse(
            agent="scholar",
            intent="get_doc_summary",
            action="summarized",
            result={"summary": summary},
            confidence=1.0,
        )

    def get_doc_flashcards(self, doc_id: str) -> AgentResponse:
        cards = self._svc().get_flashcards(doc_id)
        return AgentResponse(
            agent="scholar",
            intent="get_doc_flashcards",
            action="listed",
            result={"flashcards": cards, "count": len(cards)},
            confidence=1.0,
        )

    def generate_doc_flashcards(self, doc_id: str) -> AgentResponse:
        cards = self._svc().generate_flashcards(doc_id, self._api_key())
        return AgentResponse(
            agent="scholar",
            intent="generate_doc_flashcards",
            action="generated",
            result={"flashcards": cards, "count": len(cards)},
            confidence=1.0,
        )

    def rate_flashcard(self, card_id: str, rating: int) -> AgentResponse:
        card = self._svc().rate_card(card_id, rating)
        return AgentResponse(
            agent="scholar",
            intent="rate_flashcard",
            action="rated",
            result={"card": card},
            confidence=1.0,
        )

    def due_flashcards(self, course: str | None = None) -> AgentResponse:
        cards = self._svc().due_cards()
        if course:
            tag = f"course:{course.strip()}"
            cards = [c for c in cards if tag in (c.get("tags") or [])]
        return AgentResponse(
            agent="scholar",
            intent="due_flashcards",
            action="listed",
            result={"flashcards": cards, "count": len(cards)},
            confidence=1.0,
        )

    # ── Problem solver ───────────────────────────────────────────────────────

    def solve_problem(
        self, problem: str, course: str | None = None
    ) -> AgentResponse:
        """Walk a problem step-by-step via Claude and persist to state."""
        user_msg = (
            f"Course: {course}\n\nProblem: {problem}" if course else problem
        )
        raw = _query_claude(_SOLVE_SYSTEM, user_msg) or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("solve_problem: non-JSON response, wrapping as steps: %r", raw[:200])
            data = {
                "steps": [raw] if raw else [],
                "final_answer": "",
                "concepts_used": [],
                "weak_topic_candidates": [],
            }

        problem_id = uuid4().hex[:12]
        record: dict[str, Any] = {
            "id": problem_id,
            "ts": datetime.now(UTC).isoformat(),
            "course": course,
            "problem": problem,
            "response": data,
            "rated_correct": None,
        }
        _write_problem(record)

        return AgentResponse(
            agent="scholar",
            intent="solve_problem",
            action="solved",
            result={
                "id": problem_id,
                "steps": data.get("steps", []),
                "final_answer": data.get("final_answer", ""),
                "concepts_used": data.get("concepts_used", []),
                "weak_topic_candidates": data.get("weak_topic_candidates", []),
            },
            confidence=0.9,
        )

    def rate_problem(self, problem_id: str, correct: bool) -> AgentResponse:
        """Record whether the operator got a problem right; update weak topics
        scoped to the problem's original course."""
        updated = _update_problem(problem_id, {"rated_correct": correct})
        if updated is None:
            raise ValueError(f"problem {problem_id!r} not found")

        course_key = _course_key(updated.get("course"))
        topics = _load_weak_topics()
        course_slice = dict(topics.get(course_key, {}))

        if not correct:
            concepts: list[str] = updated.get("response", {}).get("concepts_used", [])
            now_iso = datetime.now(UTC).isoformat()
            for concept in concepts:
                entry = course_slice.get(
                    concept,
                    {"miss_count": 0, "last_seen": "", "sample_problem_ids": []},
                )
                sample_ids: list[str] = list(entry.get("sample_problem_ids", []))
                if problem_id not in sample_ids:
                    sample_ids.append(problem_id)
                course_slice[concept] = {
                    "miss_count": entry.get("miss_count", 0) + 1,
                    "last_seen": now_iso,
                    "sample_problem_ids": sample_ids[-10:],
                }
            topics[course_key] = course_slice
            _save_weak_topics(topics)

        return AgentResponse(
            agent="scholar",
            intent="rate_problem",
            action="rated",
            result={
                "problem_id": problem_id,
                "correct": correct,
                "course": course_key if course_key != _GLOBAL_COURSE else None,
                "weak_topics_after": _top_weak_topics(course_slice, 8),
            },
            confidence=1.0,
        )

    def weak_topics(
        self, top_n: int = 8, course: str | None = None
    ) -> AgentResponse:
        """Return top N concepts by miss count, scoped to a single course."""
        topics = _load_weak_topics()
        course_key = _course_key(course)
        course_slice = topics.get(course_key, {})
        return AgentResponse(
            agent="scholar",
            intent="weak_topics",
            action="listed",
            result={
                "course": course_key if course_key != _GLOBAL_COURSE else None,
                "weak_topics": _top_weak_topics(course_slice, top_n),
            },
            confidence=1.0,
        )

    def exam_session(
        self,
        course: str,
        duration_min: int = 60,
        problem_count: int = 5,
    ) -> AgentResponse:
        """Generate a timed practice exam session."""

        session_id = uuid4().hex[:12]
        now = datetime.now(UTC)
        ends = now + timedelta(minutes=duration_min)

        # Try pulling from flashcard deck first
        cards = self._svc().due_cards()
        course_cards = [c for c in cards if course.lower() in json.dumps(c.get("tags", [])).lower()]
        problems: list[dict[str, Any]] = []

        if course_cards:
            for card in course_cards[:problem_count]:
                problems.append({
                    "id": uuid4().hex[:12],
                    "prompt": card["front"],
                    "expected_concepts": card.get("tags", []),
                })

        # Fill remainder with Claude-generated problems
        remaining = problem_count - len(problems)
        if remaining > 0:
            system = (
                "You are an exam question generator. Return ONLY a JSON array of "
                f"{remaining} exam problems for the course below. "
                'Each element: {"prompt": "...", "expected_concepts": ["..."]}. '
                "No markdown fences."
            )
            raw = _query_claude(system, f"Course: {course}") or "[]"
            try:
                generated = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("exam_session: non-JSON, skipping fill: %r", raw[:200])
                generated = []
            if not isinstance(generated, list):
                generated = []
            for item in generated[:remaining]:
                if not isinstance(item, dict):
                    continue
                problems.append({
                    "id": uuid4().hex[:12],
                    "prompt": str(item.get("prompt", "")),
                    "expected_concepts": list(item.get("expected_concepts", [])),
                })

        session: dict[str, Any] = {
            "session_id": session_id,
            "started_iso": now.isoformat(),
            "ends_iso": ends.isoformat(),
            "course": course,
            "duration_min": duration_min,
            "problems": problems,
        }
        with _exams_path().open("a") as fh:
            fh.write(json.dumps(session) + "\n")

        return AgentResponse(
            agent="scholar",
            intent="exam_session",
            action="created",
            result=session,
            confidence=1.0,
        )

    # ── Seed import ──────────────────────────────────────────────────────────

    def import_seed(
        self, seed_name: str, course: str | None = None
    ) -> AgentResponse:
        """Load a seed JSON file into StudyService as flashcards.

        Each imported card is tagged ``course:{course}`` so per-course filters
        on ``due_flashcards`` match. ``course`` defaults to a pretty version
        of ``seed_name`` (e.g. ``"linalg_exam"`` → ``"Linear Algebra"`` if a
        known mapping exists, else title-cased seed name).
        """
        seed_file = _seeds_dir() / f"{seed_name}.json"
        if not seed_file.exists():
            raise ValueError(f"seed {seed_name!r} not found at {seed_file}")

        course_name = (course or _pretty_course(seed_name)).strip()
        course_tag = f"course:{course_name}"

        raw_cards: list[dict[str, Any]] = json.loads(seed_file.read_text(encoding="utf-8"))
        svc = self._svc()

        # Create a virtual document to attach cards to
        doc = svc.upload_document(
            f"{seed_name}.txt",
            f"Seed deck: {seed_name} ({course_name})".encode(),
        )
        doc_id: str = doc["id"]

        from datetime import date as _date

        from .study_db import StudyFlashcard, _now, get_session

        today = _date.today().isoformat()
        now = _now()
        saved: list[dict[str, Any]] = []

        with get_session() as session:
            for item in raw_cards:
                concept_tags = list(item.get("concept_tags", []))
                # Always include the course tag so filters match
                if course_tag not in concept_tags:
                    concept_tags.append(course_tag)
                card = StudyFlashcard(
                    id=uuid4().hex,
                    doc_id=doc_id,
                    front=str(item.get("front", "")),
                    back=str(item.get("back", "")),
                    source_page=None,
                    tags=json.dumps(concept_tags),
                    ease_factor=2.5,
                    interval=1,
                    repetitions=0,
                    due_date=today,
                    created_at=now,
                )
                session.add(card)
                saved.append({
                    "id": card.id,
                    "front": card.front,
                    "back": card.back,
                    "tags": concept_tags,
                })

        return AgentResponse(
            agent="scholar",
            intent="import_seed",
            action="imported",
            result={
                "seed_name": seed_name,
                "course": course_name,
                "doc_id": doc_id,
                "cards_imported": len(saved),
                "cards": saved,
            },
            confidence=1.0,
        )

    # ── Syllabus ingest ──────────────────────────────────────────────────────

    def ingest_syllabus(
        self,
        filename: str,
        content_b64: str,
        course: str,
        tempo: Any | None = None,
    ) -> AgentResponse:
        """Parse a syllabus, persist plan, generate flashcards, push tasks."""
        from datetime import date as _date

        from ..contract import InboxEvent
        from ..state import append_inbox
        from .scholar_study import _extract_text
        from .study_db import StudyFlashcard, _now, get_session

        content = base64.b64decode(content_b64)
        text, _pages = _extract_text(filename, content)

        system_prompt = (
            "You are a syllabus parser. Extract a structured study plan from the "
            "syllabus text. Return ONLY valid JSON with this exact shape: "
            '{"course_title": "...", "exam_date_iso": "YYYY-MM-DD" | null, '
            '"exam_window_min": 60-180 | null, '
            '"topics": [{"name": "...", "week": 1, "concept_tags": ["..."]}], '
            '"weekly_plan": [{"week": 1, "focus": "...", "study_minutes_per_day": 45}], '
            '"key_dates": [{"label": "Midterm 1", "date_iso": "YYYY-MM-DD"}]}. '
            "No markdown fences, no extra keys."
        )
        raw = (_query_claude(system_prompt, text) or "{}").strip()
        # Tolerate ```json fences if Claude added them despite the prompt
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]
        raw = raw.strip()
        try:
            plan: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("ingest_syllabus: non-JSON response: %r", raw[:200])
            plan = {}

        course_name = course.strip() or "Untitled"
        course_tag = f"course:{course_name}"
        topics = list(plan.get("topics") or [])
        weekly_plan = list(plan.get("weekly_plan") or [])
        key_dates = list(plan.get("key_dates") or [])

        # Persist plan
        syllabi_dir = _syllabi_dir()
        syllabi_dir.mkdir(parents=True, exist_ok=True)
        plan_path = syllabi_dir / f"{_safe_filename(course_name)}.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Create virtual document for cards
        svc = self._svc()
        doc = svc.upload_document(
            f"syllabus_{_safe_filename(course_name)}.txt",
            f"Syllabus deck: {course_name}".encode(),
        )
        doc_id: str = doc["id"]

        # Auto-generate flashcards from topics
        today = _date.today().isoformat()
        now = _now()
        cards_imported = 0
        with get_session() as session:
            for item in topics:
                concept_tags = list(item.get("concept_tags") or [])
                if course_tag not in concept_tags:
                    concept_tags.append(course_tag)
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                card = StudyFlashcard(
                    id=uuid4().hex,
                    doc_id=doc_id,
                    front=f"Define {name}.",
                    back="[generated]",
                    source_page=None,
                    tags=json.dumps(concept_tags),
                    ease_factor=2.5,
                    interval=1,
                    repetitions=0,
                    due_date=today,
                    created_at=now,
                )
                session.add(card)
                cards_imported += 1

        # Auto-schedule study blocks via tempo
        tasks_created = 0
        if tempo is not None:
            for entry in weekly_plan:
                focus = str(entry.get("focus", "")).strip()
                if not focus:
                    continue
                try:
                    tempo.add(
                        title=f"Study: {focus}",
                        due=None,
                        tags=[course_tag, "scholar"],
                    )
                    tasks_created += 1
                except Exception as exc:  # don't break ingest on tempo failures
                    log.warning("tempo.add failed in ingest_syllabus: %s", exc)

        # Surface key dates as inbox events
        for kd in key_dates:
            label = str(kd.get("label", "")).strip()
            date_iso = str(kd.get("date_iso", "")).strip()
            if not label or not date_iso:
                continue
            try:
                append_inbox(
                    InboxEvent(
                        agent="scholar",
                        severity="info",
                        summary=f"Upcoming: {label} on {date_iso}",
                        payload={"course": course_name, "date_iso": date_iso, "label": label},
                    )
                )
            except Exception as exc:
                log.warning("append_inbox failed in ingest_syllabus: %s", exc)

        return AgentResponse(
            agent="scholar",
            intent="ingest_syllabus",
            action="ingested",
            result={
                "course": course_name,
                "course_title": str(plan.get("course_title", "")),
                "exam_date_iso": plan.get("exam_date_iso"),
                "topics_count": len(topics),
                "weekly_plan_weeks": len(weekly_plan),
                "key_dates": key_dates,
                "deck_doc_id": doc_id,
                "cards_imported": cards_imported,
                "tasks_created": tasks_created,
            },
            confidence=0.85,
        )
