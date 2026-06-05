"""Tests for jarvis.training.extract -- ShareGPT-format training data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.training import extract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# extract_chat_persona
# ---------------------------------------------------------------------------


def test_chat_persona_emits_sharegpt_pair(tmp_path: Path) -> None:
    """One ChatTurnRecord -> one ShareGPT example with two conversations entries."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    _write_jsonl(
        src,
        [
            {
                "turn_id": "t1",
                "user_text": "what's the plan?",
                "assistant_text": "Run W3-W5 first. Then merge.",
                "ts": "2026-05-19T10:00:00Z",
            }
        ],
    )

    result = extract.extract_chat_persona(source=src, target=tgt)

    assert result.written == 1
    assert result.skipped == 0
    rows = _read_jsonl(tgt)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "chat_turns"
    assert row["turn_id"] == "t1"
    assert row["conversations"] == [
        {"from": "human", "value": "what's the plan?"},
        {"from": "gpt", "value": "Run W3-W5 first. Then merge."},
    ]


def test_chat_persona_skips_empty_sides(tmp_path: Path) -> None:
    """Turns missing either side are skipped, not emitted as broken pairs."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    _write_jsonl(
        src,
        [
            {"turn_id": "a", "user_text": "hi", "assistant_text": ""},
            {"turn_id": "b", "user_text": "", "assistant_text": "hello"},
            {"turn_id": "c", "user_text": "ok", "assistant_text": "got it"},
        ],
    )

    result = extract.extract_chat_persona(source=src, target=tgt)
    assert result.written == 1
    assert result.skipped == 2


def test_chat_persona_skips_short_text(tmp_path: Path) -> None:
    """Single-char turns (whitespace, punctuation) are dropped."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    _write_jsonl(
        src,
        [
            {"turn_id": "x", "user_text": "?", "assistant_text": "yes that works"},
        ],
    )
    result = extract.extract_chat_persona(source=src, target=tgt)
    assert result.written == 0
    assert result.skipped == 1


def test_chat_persona_idempotent_rerun(tmp_path: Path) -> None:
    """Running the extractor twice over the same source yields no duplicates."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    _write_jsonl(
        src,
        [
            {"turn_id": "t1", "user_text": "hi", "assistant_text": "hello"},
            {"turn_id": "t2", "user_text": "ok", "assistant_text": "got it"},
        ],
    )

    r1 = extract.extract_chat_persona(source=src, target=tgt)
    r2 = extract.extract_chat_persona(source=src, target=tgt)

    assert r1.written == 2
    assert r2.written == 0
    assert r2.deduped == 2
    assert len(_read_jsonl(tgt)) == 2  # no duplication


def test_chat_persona_appends_new_rows(tmp_path: Path) -> None:
    """When the source grows, only the new rows are appended to the target."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    _write_jsonl(
        src,
        [{"turn_id": "t1", "user_text": "hi", "assistant_text": "hello"}],
    )
    extract.extract_chat_persona(source=src, target=tgt)

    # Source grows with a new turn:
    _write_jsonl(
        src,
        [
            {"turn_id": "t1", "user_text": "hi", "assistant_text": "hello"},
            {"turn_id": "t2", "user_text": "next", "assistant_text": "got it"},
        ],
    )
    r = extract.extract_chat_persona(source=src, target=tgt)

    assert r.written == 1
    assert r.deduped == 1
    rows = _read_jsonl(tgt)
    assert {row["turn_id"] for row in rows} == {"t1", "t2"}


def test_chat_persona_missing_source_returns_zero(tmp_path: Path) -> None:
    """No source file -> empty result, target untouched."""
    tgt = tmp_path / "out.jsonl"
    r = extract.extract_chat_persona(source=tmp_path / "missing.jsonl", target=tgt)
    assert r.written == 0
    assert r.skipped == 0
    assert not tgt.exists()


def test_chat_persona_tolerates_malformed_lines(tmp_path: Path) -> None:
    """Garbage lines in the source are skipped, valid lines still extract."""
    src = tmp_path / "chat_turns.jsonl"
    tgt = tmp_path / "out.jsonl"
    src.write_text(
        json.dumps({"turn_id": "t1", "user_text": "hi", "assistant_text": "hello"})
        + "\nNOT JSON\n"
        + json.dumps({"turn_id": "t2", "user_text": "ok", "assistant_text": "yep"})
        + "\n",
        encoding="utf-8",
    )
    r = extract.extract_chat_persona(source=src, target=tgt)
    assert r.written == 2


# ---------------------------------------------------------------------------
# extract_email_voice
# ---------------------------------------------------------------------------


def test_email_voice_only_approved_or_sent(tmp_path: Path) -> None:
    """Drafts in 'drafted' or 'rejected' status are filtered out."""
    src = tmp_path / "drafted_replies.jsonl"
    tgt = tmp_path / "voice.jsonl"
    _write_jsonl(
        src,
        [
            {
                "id": "d1",
                "inbox_event_id": "e1",
                "to": "alice@x.com",
                "subject": "Re: budget",
                "body": "Looks fine. Approve.",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "approved",
            },
            {
                "id": "d2",
                "inbox_event_id": "e2",
                "to": "bob@x.com",
                "subject": "Re: plan",
                "body": "Sent.",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "sent",
            },
            {
                "id": "d3",
                "inbox_event_id": "e3",
                "to": "carol@x.com",
                "subject": "Re: meeting",
                "body": "Maybe later.",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "drafted",  # not approved -> skip
            },
            {
                "id": "d4",
                "inbox_event_id": "e4",
                "to": "dave@x.com",
                "subject": "Re: spam",
                "body": "nope",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "rejected",  # rejected -> skip
            },
        ],
    )
    r = extract.extract_email_voice(source=src, target=tgt)
    assert r.written == 2
    assert r.skipped == 2

    rows = _read_jsonl(tgt)
    ids = {row["draft_id"] for row in rows}
    assert ids == {"d1", "d2"}


def test_email_voice_sharegpt_shape(tmp_path: Path) -> None:
    """Approved draft -> human prompt mentions recipient + subject, gpt = body."""
    src = tmp_path / "drafted_replies.jsonl"
    tgt = tmp_path / "voice.jsonl"
    _write_jsonl(
        src,
        [
            {
                "id": "d1",
                "inbox_event_id": "e1",
                "to": "alice@x.com",
                "subject": "Re: budget",
                "body": "Looks fine. Approve.",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "approved",
            }
        ],
    )
    extract.extract_email_voice(source=src, target=tgt)

    rows = _read_jsonl(tgt)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "drafted_replies"
    assert row["conversations"][0]["from"] == "human"
    assert "alice@x.com" in row["conversations"][0]["value"]
    assert "Re: budget" in row["conversations"][0]["value"]
    assert row["conversations"][1] == {"from": "gpt", "value": "Looks fine. Approve."}


def test_email_voice_idempotent(tmp_path: Path) -> None:
    """Re-running the email extractor doesn't duplicate examples."""
    src = tmp_path / "drafted_replies.jsonl"
    tgt = tmp_path / "voice.jsonl"
    _write_jsonl(
        src,
        [
            {
                "id": "d1",
                "inbox_event_id": "e1",
                "to": "a@x",
                "subject": "x",
                "body": "yes",
                "drafted_at": "2026-05-19T08:00:00Z",
                "status": "approved",
            }
        ],
    )
    r1 = extract.extract_email_voice(source=src, target=tgt)
    r2 = extract.extract_email_voice(source=src, target=tgt)
    assert r1.written == 1
    assert r2.written == 0
    assert r2.deduped == 1


# ---------------------------------------------------------------------------
# extract_all
# ---------------------------------------------------------------------------


def test_extract_all_returns_one_result_per_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extract_all() returns one ExtractResult per extractor."""
    # Redirect state_dir + training_dir into tmp_path so the default paths land here.
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_TRAINING_DIR", str(tmp_path / "training"))

    # Seed empty sources -> both extractors return 0 written.
    (tmp_path / "chat_turns.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "drafted_replies.jsonl").write_text("", encoding="utf-8")

    results = extract.extract_all()
    assert len(results) == 2
    sources = {r.source for r in results}
    assert sources == {"chat_turns", "drafted_replies"}
