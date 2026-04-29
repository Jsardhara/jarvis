"""Tests for jarvis.memory_index — semantic chat memory.

Sentence-transformers is *not* loaded during these tests.  All embedding
calls are monkeypatched to return small 4-dimensional fake vectors so the
suite stays fast and offline.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_st_available(monkeypatch):
    """Mark sentence-transformers as *available* but intercept encode()."""
    import jarvis.memory_index as mi

    monkeypatch.setattr(mi, "_ST_AVAILABLE", True)


@pytest.fixture()
def fake_embed(monkeypatch):
    """Replace embed() with a deterministic 4-dim function.

    The vector for a string is derived from its length so different texts
    produce different (but reproducible) vectors.
    """
    import jarvis.memory_index as mi

    def _fake_embed(text: str) -> list[float]:
        n = len(text)
        base = [n * 0.1, n * 0.05, n * 0.02, 1.0]
        # Normalise to unit length so cosine = dot product
        mag = sum(x * x for x in base) ** 0.5
        return [x / mag for x in base] if mag else [0.0, 0.0, 0.0, 1.0]

    monkeypatch.setattr(mi, "embed", _fake_embed)
    return _fake_embed


@pytest.fixture()
def tmp_index(tmp_path, monkeypatch):
    """Point the index at a temp file for isolation."""
    import jarvis.memory_index as mi

    idx_file = tmp_path / "test_index.jsonl"
    monkeypatch.setattr(mi, "_get_index_path", lambda: idx_file)
    return idx_file


# ── embed() ───────────────────────────────────────────────────────────────────


def test_embed_returns_none_when_st_unavailable(monkeypatch):
    import jarvis.memory_index as mi

    monkeypatch.setattr(mi, "_ST_AVAILABLE", False)
    result = mi.embed("hello world")
    assert result is None


def test_fake_embed_returns_4dim_vector(fake_embed):
    import jarvis.memory_index as mi

    vec = mi.embed("hello")
    assert vec is not None
    assert len(vec) == 4


def test_embed_returns_list_of_floats(fake_embed):
    import jarvis.memory_index as mi

    vec = mi.embed("some text here")
    assert vec is not None
    assert all(isinstance(v, float) for v in vec)


# ── append_turn + load ────────────────────────────────────────────────────────


def test_append_turn_writes_parseable_jsonl(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    turn = mi.IndexedTurn(
        turn_id="abc123",
        ts=datetime.now(UTC).isoformat(),
        role="user",
        text="hello jarvis",
        embedding=mi.embed("hello jarvis"),
    )
    mi.append_turn(turn)

    lines = tmp_index.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["turn_id"] == "abc123"
    assert parsed["role"] == "user"
    assert parsed["text"] == "hello jarvis"
    assert isinstance(parsed["embedding"], list)


def test_append_turn_accumulates_lines(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    for i in range(5):
        turn = mi.IndexedTurn(
            turn_id=f"id{i}",
            ts=datetime.now(UTC).isoformat(),
            role="user",
            text=f"message {i}",
            embedding=mi.embed(f"message {i}"),
        )
        mi.append_turn(turn)

    lines = tmp_index.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5


# ── _cosine ───────────────────────────────────────────────────────────────────


def test_cosine_identical_vectors():
    from jarvis.memory_index import _cosine

    v = [0.5, 0.5, 0.5, 0.5]
    assert abs(_cosine(v, v) - 1.0) < 1e-6


def test_cosine_orthogonal_vectors():
    from jarvis.memory_index import _cosine

    a = [1.0, 0.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0, 0.0]
    assert abs(_cosine(a, b)) < 1e-6


def test_cosine_zero_vector():
    from jarvis.memory_index import _cosine

    assert _cosine([0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]) == 0.0


# ── search() ─────────────────────────────────────────────────────────────────


def _seed_index(mi: Any, texts: list[str], tmp_index: Path, fake_embed: Any) -> None:
    """Helper: write several turns to tmp_index."""
    for i, text in enumerate(texts):
        turn = mi.IndexedTurn(
            turn_id=f"seed{i}",
            ts=datetime.now(UTC).isoformat(),
            role="user" if i % 2 == 0 else "assistant",
            text=text,
            embedding=mi.embed(text),
        )
        mi.append_turn(turn)


def test_search_returns_hits_ranked_by_similarity(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    texts = [
        "short",                # short text
        "a medium length message about trading",
        "this is a very long detailed message that contains lots of useful information",
    ]
    _seed_index(mi, texts, tmp_index, fake_embed)

    # Query similar to the longest text (similar length → higher cosine)
    results = mi.search("long detailed useful", top_k=3)

    assert len(results) == 3
    # Scores must be in descending order
    scores = [s for s, _ in results]
    assert scores == sorted(scores, reverse=True)


def test_search_returns_empty_when_no_embeddings(tmp_index, fake_embed, monkeypatch):
    import jarvis.memory_index as mi

    # Write a turn with no embedding
    turn = mi.IndexedTurn(
        turn_id="no_vec",
        ts=datetime.now(UTC).isoformat(),
        role="user",
        text="some text",
        embedding=None,
    )
    mi.append_turn(turn)

    results = mi.search("some text", top_k=5)
    assert results == []


def test_search_returns_empty_on_missing_index(tmp_index):
    import jarvis.memory_index as mi

    # Index file does not exist
    assert not tmp_index.exists()
    results = mi.search("anything")
    assert results == []


def test_search_respects_top_k(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    for i in range(10):
        mi.append_turn(
            mi.IndexedTurn(
                turn_id=f"t{i}",
                ts=datetime.now(UTC).isoformat(),
                role="user",
                text="x" * (i + 1),
                embedding=mi.embed("x" * (i + 1)),
            )
        )

    results = mi.search("xx", top_k=3)
    assert len(results) == 3


# ── search_window() ───────────────────────────────────────────────────────────


def test_search_window_excludes_old_turns(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
    recent_ts = datetime.now(UTC).isoformat()

    mi.append_turn(
        mi.IndexedTurn(
            turn_id="old",
            ts=old_ts,
            role="user",
            text="old message",
            embedding=mi.embed("old message"),
        )
    )
    mi.append_turn(
        mi.IndexedTurn(
            turn_id="new",
            ts=recent_ts,
            role="user",
            text="recent message",
            embedding=mi.embed("recent message"),
        )
    )

    results = mi.search_window("message", top_k=5, days=30)
    ids = [t.turn_id for _, t in results]
    assert "new" in ids
    assert "old" not in ids


def test_search_window_returns_empty_when_all_old(tmp_index, fake_embed):
    import jarvis.memory_index as mi

    old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    mi.append_turn(
        mi.IndexedTurn(
            turn_id="ancient",
            ts=old_ts,
            role="user",
            text="ancient turn",
            embedding=mi.embed("ancient turn"),
        )
    )

    results = mi.search_window("ancient turn", top_k=5, days=30)
    assert results == []


# ── turn_id_from_dict ─────────────────────────────────────────────────────────


def test_turn_id_is_stable():
    from jarvis.memory_index import turn_id_from_dict

    entry = {"role": "user", "text": "hello", "ts": "2024-01-01T00:00:00+00:00"}
    assert turn_id_from_dict(entry) == turn_id_from_dict(entry)


def test_turn_id_differs_for_different_texts():
    from jarvis.memory_index import turn_id_from_dict

    a = turn_id_from_dict({"role": "user", "text": "hello"})
    b = turn_id_from_dict({"role": "user", "text": "world"})
    assert a != b


# ── JarvisChat.semantic_search integration ────────────────────────────────────


def test_semantic_search_returns_correct_shape(tmp_index, fake_embed, monkeypatch):
    """JarvisChat.semantic_search returns list[dict] with expected keys."""
    import jarvis.memory_index as mi
    from jarvis.jarvis_agent import JarvisChat

    # Pre-populate index
    mi.append_turn(
        mi.IndexedTurn(
            turn_id="chat1",
            ts=datetime.now(UTC).isoformat(),
            role="user",
            text="what are my tasks",
            embedding=mi.embed("what are my tasks"),
        )
    )

    chat = JarvisChat(registry={})
    results = chat.semantic_search("tasks", top_k=5)

    assert isinstance(results, list)
    if results:
        item = results[0]
        assert "score" in item
        assert "role" in item
        assert "text" in item
        assert "ts" in item
        assert "lane" in item


def test_semantic_search_returns_empty_on_empty_index(tmp_index):
    """No results when index is empty — no crash."""
    from jarvis.jarvis_agent import JarvisChat

    chat = JarvisChat(registry={})
    results = chat.semantic_search("hello")
    assert results == []


def test_semantic_search_empty_on_embed_failure(tmp_index, monkeypatch):
    """When embed returns None, semantic_search returns []."""
    import jarvis.memory_index as mi

    monkeypatch.setattr(mi, "embed", lambda text: None)

    from jarvis.jarvis_agent import JarvisChat

    chat = JarvisChat(registry={})
    results = chat.semantic_search("anything")
    assert results == []
