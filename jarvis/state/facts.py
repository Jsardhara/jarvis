"""Declarative key-value fact extraction for Jarvis memory.

Regex-based, no LLM — keeps fact capture cheap and deterministic. Facts
land in ``state/facts.jsonl`` as append-only JSON lines. Reads dedup by
key (latest wins), so the rolling truth survives many writes.

Patterns currently matched (case-insensitive, applied in order):

* ``call me <name>``                              → key="name"
* ``my <field> is <value>``                       → key=<field>
* ``i (prefer|like|love) X``                      → key="preference"
* ``remember (that) X``                           → key="reminder"
* ``i ('m|am|live) in <place>``                   → key="location"
* ``i work from <hours>`` (or am free / available)→ key="hours"
* ``i <verb> every <cadence>``                    → key="routine:<verb>"
* ``don't / never / do not X``                    → key="avoid"

Failures never raise — extract returns an empty list and reads return
whatever could be parsed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)


_PROMPT_FACT_CAP = 30


@dataclass(frozen=True)
class KeyValueFact:
    """One declarative fact captured from a user turn."""

    key: str
    value: str
    extracted_from_turn_id: str
    ts: str  # ISO UTC


def _facts_path() -> Path:
    return get_settings().state_dir / "facts.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Extraction ────────────────────────────────────────────────────────────────


# Patterns ordered most-specific first so "call me J" doesn't shadow as preference.
_PAT_CALL_ME = re.compile(r"\bcall me\s+([A-Za-z][\w\s']{0,40})", re.IGNORECASE)
# Multi-word fields supported via non-greedy `[\w\s]+?` so "my favorite color is blue"
# captures field="favorite color", value="blue".
_PAT_MY_X_IS = re.compile(
    r"\bmy\s+([\w\s]+?)\s+is\s+([\w\s][\w\s:.,'\-]{0,80})",
    re.IGNORECASE,
)
_PAT_REMEMBER = re.compile(
    r"\bremember\s+(?:that\s+)?(.+)",
    re.IGNORECASE,
)
_PAT_PREFERENCE = re.compile(
    r"\bi\s+(?:prefer|like|love)\s+([\w\s][\w\s'\-]{0,60})",
    re.IGNORECASE,
)
# Location — handles BOTH "I'm in Brooklyn" (contraction, no space) and
# "I live in Philly" (verb-with-space). The alternation embeds the
# separator so contractions don't fail `\s+` matching.
_PAT_LOCATION = re.compile(
    r"\bi(?:'m| am| live)\s+in\s+([\w\s][\w\s'\-,]{0,40})",
    re.IGNORECASE,
)
# Working hours / availability — supports "i work from 9 to 6" and the
# contraction forms ("i'm available", "i'm free").
_PAT_HOURS = re.compile(
    r"\bi(?:\s+work|'m available|\s+am available|'m free|\s+am free)\s+(?:from\s+)?([\w\s][\w\s:.,'\-]{0,60})",
    re.IGNORECASE,
)
# Schedule "every X" — "I check mail every morning", "I do standup every monday".
_PAT_ROUTINE = re.compile(
    r"\bi\s+(\w+)\s+(?:every|each)\s+(\w+(?:\s+at\s+[\w:]+)?)",
    re.IGNORECASE,
)
# Don't-do preferences — "don't call me X", "no notifications after 10pm".
_PAT_AVOID = re.compile(
    r"\b(?:don[''']t|do not|never)\s+(.+?)(?:\.|$|,)",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    """Trim trailing punctuation and whitespace from an extracted slot."""
    return value.strip().rstrip(".!?,;:").strip()


def extract_facts(user_text: str, turn_id: str) -> list[KeyValueFact]:
    """Return a list of facts extracted from *user_text*.

    Each pattern is tried independently; a single sentence can yield
    multiple facts (e.g. "call me J and remember my flight is 6am").
    """
    if not user_text:
        return []
    text = user_text.strip()
    if not text:
        return []
    ts = _now_iso()
    out: list[KeyValueFact] = []

    m = _PAT_CALL_ME.search(text)
    if m:
        name = _clean(m.group(1))
        if name:
            out.append(KeyValueFact(key="name", value=name, extracted_from_turn_id=turn_id, ts=ts))

    m = _PAT_MY_X_IS.search(text)
    if m:
        key = _clean(m.group(1)).lower()
        value = _clean(m.group(2))
        # Skip the trivially short / pronoun-y cases that yield noise.
        if key and value and key not in {"name"}:
            out.append(
                KeyValueFact(
                    key=key,
                    value=value,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_REMEMBER.search(text)
    if m:
        body = _clean(m.group(1))
        if body:
            out.append(
                KeyValueFact(
                    key="reminder",
                    value=body,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_PREFERENCE.search(text)
    if m:
        body = _clean(m.group(1))
        if body:
            out.append(
                KeyValueFact(
                    key="preference",
                    value=body,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_LOCATION.search(text)
    if m:
        body = _clean(m.group(1))
        if body:
            out.append(
                KeyValueFact(
                    key="location",
                    value=body,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_HOURS.search(text)
    if m:
        body = _clean(m.group(1))
        if body:
            out.append(
                KeyValueFact(
                    key="hours",
                    value=body,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_ROUTINE.search(text)
    if m:
        verb = _clean(m.group(1)).lower()
        cadence = _clean(m.group(2))
        if verb and cadence:
            out.append(
                KeyValueFact(
                    key=f"routine:{verb}",
                    value=cadence,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    m = _PAT_AVOID.search(text)
    if m:
        body = _clean(m.group(1))
        # Cap body length so a rambling sentence doesn't poison the store.
        if body and len(body) <= 80:
            out.append(
                KeyValueFact(
                    key="avoid",
                    value=body,
                    extracted_from_turn_id=turn_id,
                    ts=ts,
                )
            )

    return out


# ── Persistence ───────────────────────────────────────────────────────────────


def append_fact(fact: KeyValueFact) -> None:
    """Append a single fact JSON line to ``state/facts.jsonl``.

    Best-effort: filesystem errors are logged and swallowed so a failed
    write never blocks the chat hot path.
    """
    try:
        path = _facts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_if_large(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(fact), ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("facts append failed: %s", exc)


def read_facts(limit: int = 50) -> list[KeyValueFact]:
    """Return facts deduped by key (latest ts wins per key).

    *limit* caps the dedup-output count, returning the most recent
    distinct keys.  Returns an empty list if the file is absent or
    unreadable.
    """
    path = _facts_path()
    if not path.exists():
        return []
    by_key: dict[str, KeyValueFact] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            try:
                fact = KeyValueFact(
                    key=str(data["key"]),
                    value=str(data["value"]),
                    extracted_from_turn_id=str(data.get("extracted_from_turn_id", "")),
                    ts=str(data.get("ts", "")),
                )
            except (KeyError, TypeError):
                continue
            prior = by_key.get(fact.key)
            if prior is None or fact.ts >= prior.ts:
                by_key[fact.key] = fact
    except OSError as exc:
        log.warning("facts read failed: %s", exc)
        return []
    # Newest-first by ts, capped at *limit*.
    ordered = sorted(by_key.values(), key=lambda f: f.ts, reverse=True)
    if limit > 0:
        ordered = ordered[:limit]
    return ordered


def render_facts_for_prompt(facts: list[KeyValueFact]) -> str:
    """Format facts as a prompt block. Empty string if no facts.

    Caller is expected to pre-trim to ``_PROMPT_FACT_CAP`` if desired;
    this function additionally caps internally so a runaway file can't
    pollute the prompt.
    """
    if not facts:
        return ""
    trimmed = facts[:_PROMPT_FACT_CAP]
    lines = ["Known facts about the operator:"]
    for f in trimmed:
        lines.append(f"- {f.key}: {f.value}")
    return "\n".join(lines)


__all__ = [
    "KeyValueFact",
    "append_fact",
    "extract_facts",
    "read_facts",
    "render_facts_for_prompt",
]
