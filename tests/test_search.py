"""Tests for jarvis.search — global search across all state sources."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jarvis.config import get_settings

# ── helpers ──────────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_state(tmp_path: Path) -> None:
    """Write minimal fixture data into the isolated state dir."""
    # Inbox
    _write_jsonl(
        tmp_path / "inbox.jsonl",
        [
            {
                "ts": "2026-04-29T10:00:00+00:00",
                "agent": "tempo",
                "severity": "info",
                "summary": "New email from professor about linear algebra exam",
                "ref": {},
            },
            {
                "ts": "2026-04-29T11:00:00+00:00",
                "agent": "atlas",
                "severity": "warn",
                "summary": "Portfolio drawdown alert triggered",
                "ref": {"pnl_pct": -0.05},
            },
        ],
    )

    # Tasks
    _write_json(
        tmp_path / "tasks.json",
        {
            "version": 1,
            "tasks": [
                {
                    "id": "task001",
                    "title": "Submit linear algebra assignment",
                    "due": "2026-05-01",
                    "tags": ["school", "course:linalg"],
                    "status": "open",
                    "created": "2026-04-28T09:00:00+00:00",
                    "updated": "2026-04-28T09:00:00+00:00",
                },
                {
                    "id": "task002",
                    "title": "Review trading strategy backtest",
                    "due": "2026-05-03",
                    "tags": ["atlas"],
                    "status": "open",
                    "created": "2026-04-28T10:00:00+00:00",
                    "updated": "2026-04-28T10:00:00+00:00",
                },
            ],
        },
    )

    # Confirmations (decisions)
    _write_jsonl(
        tmp_path / "confirmations.jsonl",
        [
            {
                "id": "conf001",
                "ts": "2026-04-28T15:00:00+00:00",
                "agent": "atlas",
                "intent": "trigger_strategy",
                "request": "run alpha-1 strategy in paper mode",
                "args": {"strategy_id": "alpha-1", "mode": "paper"},
                "summary": "confirm to run strategy alpha-1 in paper",
                "status": "pending",
                "resolved_ts": None,
                "resolved_result": None,
            },
        ],
    )

    # Agent log
    _write_jsonl(
        tmp_path / "agent_log.jsonl",
        [
            {
                "ts": "2026-04-29T12:00:00+00:00",
                "request_id": "req001",
                "agent": "scholar",
                "action": "solve_problem",
                "status": "ok",
                "duration_ms": 450,
                "confidence": 0.95,
                "needs_confirm": False,
                "summary": "",
                "error": None,
            },
        ],
    )

    # Scholar problems
    _write_jsonl(
        tmp_path / "scholar_problems.jsonl",
        [
            {
                "id": "prob001",
                "ts": "2026-04-29T14:00:00+00:00",
                "course": "Linear Algebra",
                "problem": "Find eigenvalues of matrix A = [[3,1],[0,3]]",
                "response": {"final_answer": "eigenvalue 3 with multiplicity 2"},
                "rated_correct": None,
            },
        ],
    )

    # Scholar exams
    _write_jsonl(
        tmp_path / "scholar_exams.jsonl",
        [
            {
                "session_id": "exam001",
                "started_iso": "2026-04-29T18:00:00+00:00",
                "ends_iso": "2026-04-29T19:00:00+00:00",
                "course": "Linear Algebra",
                "duration_min": 60,
                "problems": [{"id": "p1", "prompt": "Find all eigenvalues of B"}],
            },
        ],
    )

    # Forge runs
    _write_jsonl(
        tmp_path / "forge_runs.jsonl",
        [
            {
                "run_id": "run001",
                "repo_path": "/repos/jarvis",
                "branch": "forge/run001-add-feature",
                "task": "Add global search feature to jarvis backend",
                "started_iso": "2026-04-29T16:00:00+00:00",
                "finished_iso": "2026-04-29T16:15:00+00:00",
                "status": "completed",
                "commit_sha": "abc1234",
                "diff_summary": "+120 -5",
                "log_path": "/state/forge_runs/run001.log",
                "pushed": False,
            },
        ],
    )


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def seeded_state(isolated_state: Path) -> Path:
    """Write fixture data on top of the already-isolated state dir."""
    _seed_state(isolated_state)
    return isolated_state


# ── keyword search ────────────────────────────────────────────────────────────


def test_keyword_matches_inbox() -> None:
    from jarvis.search import search_all

    hits = search_all("linear algebra")
    kinds = [h.kind for h in hits]
    assert "inbox" in kinds
    inbox_hits = [h for h in hits if h.kind == "inbox"]
    assert any("linear algebra" in h.snippet.lower() for h in inbox_hits)


def test_keyword_matches_tasks() -> None:
    from jarvis.search import search_all

    hits = search_all("assignment")
    kinds = [h.kind for h in hits]
    assert "task" in kinds
    task_hits = [h for h in hits if h.kind == "task"]
    assert any("assignment" in h.title.lower() for h in task_hits)


def test_keyword_matches_decisions() -> None:
    from jarvis.search import search_all

    hits = search_all("alpha-1")
    kinds = [h.kind for h in hits]
    assert "decision" in kinds


def test_keyword_matches_agent_log() -> None:
    from jarvis.search import search_all

    hits = search_all("solve_problem")
    kinds = [h.kind for h in hits]
    assert "agent_log" in kinds


def test_keyword_matches_scholar_problem() -> None:
    from jarvis.search import search_all

    hits = search_all("eigenvalues")
    kinds = [h.kind for h in hits]
    assert "problem" in kinds


def test_keyword_matches_scholar_exam() -> None:
    from jarvis.search import search_all

    hits = search_all("Linear Algebra")
    kinds = [h.kind for h in hits]
    assert "exam" in kinds


def test_keyword_matches_forge_run() -> None:
    from jarvis.search import search_all

    hits = search_all("global search")
    kinds = [h.kind for h in hits]
    assert "forge_run" in kinds


# ── semantic chat search ──────────────────────────────────────────────────────


def test_semantic_chat_hits_returned(monkeypatch) -> None:
    """When memory_index.search returns canned results they appear as chat hits."""
    from jarvis.search import search_all

    from jarvis import memory_index
    from jarvis.memory_index import IndexedTurn

    canned_turn = IndexedTurn(
        turn_id="turn001",
        ts="2026-04-28T09:00:00+00:00",
        role="assistant",
        text="The eigenvalues of a diagonal matrix are its diagonal entries.",
        lane="sonnet",
        embedding=None,
    )
    monkeypatch.setattr(
        memory_index,
        "search",
        lambda query, top_k=5: [(0.87, canned_turn)],
    )

    hits = search_all("diagonal matrix eigenvalues")
    chat_hits = [h for h in hits if h.kind == "chat"]
    assert len(chat_hits) >= 1
    assert chat_hits[0].score == pytest.approx(0.87)
    assert "eigenvalues" in chat_hits[0].snippet.lower()


def test_semantic_chat_href_contains_turn_id(monkeypatch) -> None:
    from jarvis.search import search_all

    from jarvis import memory_index
    from jarvis.memory_index import IndexedTurn

    canned_turn = IndexedTurn(
        turn_id="turn999",
        ts="2026-04-28T09:00:00+00:00",
        role="user",
        text="What is a rank-deficient matrix?",
        embedding=None,
    )
    monkeypatch.setattr(
        memory_index,
        "search",
        lambda query, top_k=5: [(0.72, canned_turn)],
    )

    hits = search_all("rank deficient")
    chat_hits = [h for h in hits if h.kind == "chat"]
    assert any("turn999" in h.href for h in chat_hits)


# ── deduplication ─────────────────────────────────────────────────────────────


def test_dedup_keeps_higher_score(monkeypatch) -> None:
    """Same (kind, id) from two sources keeps the higher-scored hit."""
    from jarvis.search import search_all

    from jarvis import memory_index
    from jarvis.memory_index import IndexedTurn

    # Seed a chat turn that matches keyword AND appears in semantic results
    canned_turn = IndexedTurn(
        turn_id="dup_turn",
        ts="2026-04-29T10:00:00+00:00",
        role="assistant",
        text="linear algebra eigenvalues study guide",
        embedding=None,
    )
    monkeypatch.setattr(
        memory_index,
        "search",
        lambda query, top_k=5: [(0.99, canned_turn)],
    )

    # Also write the same turn to the chat index so keyword scan can find it
    index_path = get_settings().state_dir / "jarvis_chat_index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(canned_turn.model_dump()) + "\n", encoding="utf-8"
    )

    hits = search_all("eigenvalues")
    chat_hits = [h for h in hits if h.kind == "chat"]
    ids = [h.id for h in chat_hits]
    assert ids.count("dup_turn") <= 1  # deduped
    # The surviving hit should carry the higher score (semantic = 0.99)
    surviving = next((h for h in chat_hits if h.id == "dup_turn"), None)
    if surviving:
        assert surviving.score == pytest.approx(0.99)


# ── limit_per_kind ────────────────────────────────────────────────────────────


def test_limit_per_kind_enforced(seeded_state: Path) -> None:
    """With limit_per_kind=1, no source should contribute more than 1 result."""
    from jarvis.search import search_all

    # Add multiple tasks that all match
    _write_json(
        seeded_state / "tasks.json",
        {
            "version": 1,
            "tasks": [
                {
                    "id": f"task{i:03d}",
                    "title": f"linear algebra task {i}",
                    "due": None,
                    "tags": [],
                    "status": "open",
                    "created": "2026-04-29T00:00:00+00:00",
                    "updated": "2026-04-29T00:00:00+00:00",
                }
                for i in range(10)
            ],
        },
    )

    hits = search_all("linear algebra", limit_per_kind=1)
    task_hits = [h for h in hits if h.kind == "task"]
    assert len(task_hits) <= 1


# ── empty query ───────────────────────────────────────────────────────────────


def test_empty_query_returns_empty() -> None:
    from jarvis.search import search_all

    hits = search_all("")
    assert hits == []


def test_whitespace_query_returns_empty() -> None:
    from jarvis.search import search_all

    hits = search_all("   ")
    assert hits == []


# ── href format ───────────────────────────────────────────────────────────────


def test_href_formats_correct() -> None:
    from jarvis.search import search_all

    hits = search_all("linear algebra")

    for hit in hits:
        assert hit.href.startswith("/"), f"{hit.kind} href must be absolute path: {hit.href}"

    # Check known hrefs
    task_hits = [h for h in hits if h.kind == "task"]
    if task_hits:
        assert "/status-board" in task_hits[0].href

    inbox_hits = [h for h in hits if h.kind == "inbox"]
    if inbox_hits:
        assert "/inbox" in inbox_hits[0].href


# ── score range ───────────────────────────────────────────────────────────────


def test_scores_in_valid_range() -> None:
    from jarvis.search import search_all

    hits = search_all("strategy")
    for hit in hits:
        assert 0.0 <= hit.score <= 1.0, f"{hit.kind} hit score out of range: {hit.score}"


# ── sorted by score desc ──────────────────────────────────────────────────────


def test_results_sorted_by_score_desc(monkeypatch) -> None:
    from jarvis.search import search_all

    from jarvis import memory_index
    from jarvis.memory_index import IndexedTurn

    canned = IndexedTurn(
        turn_id="t1",
        ts="2026-04-29T00:00:00+00:00",
        role="assistant",
        text="linear algebra eigenvalues study",
        embedding=None,
    )
    monkeypatch.setattr(
        memory_index, "search", lambda q, top_k=5: [(0.91, canned)]
    )

    hits = search_all("linear algebra")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


# ── SearchHit dataclass ───────────────────────────────────────────────────────


def test_search_hit_is_frozen() -> None:
    from jarvis.search import SearchHit

    hit = SearchHit(
        kind="task",
        id="abc",
        title="Test",
        snippet="snippet text",
        ts="2026-04-29T00:00:00+00:00",
        score=0.75,
        href="/status-board?task=abc",
        metadata={},
    )
    with pytest.raises((AttributeError, TypeError)):
        hit.score = 0.5  # type: ignore[misc]


def test_snippet_max_200_chars() -> None:
    from jarvis.search import search_all

    # Tasks have longer descriptions via tags field; this verifies clipping.
    hits = search_all("linear algebra")
    for hit in hits:
        assert len(hit.snippet) <= 200, f"{hit.kind} snippet too long: {len(hit.snippet)}"
