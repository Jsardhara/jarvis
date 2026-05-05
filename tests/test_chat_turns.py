"""Tests for chat_turns persistence (cross-device chat history)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.chat_turns import (
    ChatTurnRecord,
    append_turn,
    read_recent,
    user_id_from_token,
)


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "chat_turns.jsonl"


def _make(turn_id: str, *, user_id: str = "default", user_text: str = "hi") -> ChatTurnRecord:
    return ChatTurnRecord(
        user_id=user_id,
        turn_id=turn_id,
        user_text=user_text,
        assistant_text="ok",
        tool_calls=[],
        model="claude-opus-4-7",
        cost_usd=0.0,
        duration_ms=10,
        ts="2026-05-05T12:00:00+00:00",
    )


def test_append_writes_jsonl(store_path: Path) -> None:
    record = _make("t1")
    append_turn(record, path=store_path)

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["turn_id"] == "t1"
    assert parsed["user_id"] == "default"
    assert parsed["assistant_text"] == "ok"


def test_read_recent_returns_last_n_in_chronological_order(store_path: Path) -> None:
    for i in range(5):
        append_turn(_make(f"t{i}"), path=store_path)

    recent = read_recent("default", limit=3, path=store_path)
    assert [r.turn_id for r in recent] == ["t2", "t3", "t4"]


def test_read_recent_filters_by_user_id(store_path: Path) -> None:
    append_turn(_make("a1", user_id="alice"), path=store_path)
    append_turn(_make("b1", user_id="bob"), path=store_path)
    append_turn(_make("a2", user_id="alice"), path=store_path)

    alice_turns = read_recent("alice", limit=10, path=store_path)
    assert [r.turn_id for r in alice_turns] == ["a1", "a2"]


def test_read_recent_returns_empty_when_no_file(store_path: Path) -> None:
    assert read_recent("default", limit=5, path=store_path) == []


def test_corrupted_lines_skipped(store_path: Path) -> None:
    append_turn(_make("t1"), path=store_path)
    with store_path.open("a", encoding="utf-8") as fh:
        fh.write("not valid json\n")
    append_turn(_make("t2"), path=store_path)

    recent = read_recent("default", limit=10, path=store_path)
    assert [r.turn_id for r in recent] == ["t1", "t2"]


def test_user_id_from_token_is_stable_and_short() -> None:
    a = user_id_from_token("hello")
    b = user_id_from_token("hello")
    c = user_id_from_token("world")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_user_id_from_empty_token_returns_default() -> None:
    assert user_id_from_token("") == "default"
    assert user_id_from_token(None) == "default"  # type: ignore[arg-type]
