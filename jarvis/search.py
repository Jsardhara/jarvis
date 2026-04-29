"""Global search across inbox, tasks, decisions, agent logs, chat history.

Combines:
  - Keyword scan (case-insensitive substring) across all sources
  - Semantic search via memory_index.search() for chat-history matches
Returns ranked unified results.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

_KIND = Literal[
    "inbox",
    "task",
    "decision",
    "agent_log",
    "chat",
    "problem",
    "exam",
    "forge_run",
]

_SNIPPET_MAX = 200
_TOTAL_CAP = 30


@dataclass(frozen=True)
class SearchHit:
    kind: _KIND
    id: str
    title: str
    snippet: str  # <= 200 chars
    ts: str  # ISO-8601
    score: float  # 0..1
    href: str  # frontend URL
    metadata: dict[str, Any]


def search_all(query: str, limit_per_kind: int = 5) -> list[SearchHit]:
    """Search all state sources. Returns up to limit_per_kind hits per source,
    total capped at _TOTAL_CAP, sorted by score desc."""
    q = query.strip()
    if not q:
        return []

    keyword_hits = _keyword_scan(q, limit_per_kind)
    semantic_hits = _semantic_chat(q, limit_per_kind)

    merged = _merge(keyword_hits, semantic_hits, limit_per_kind)
    return merged[:_TOTAL_CAP]


# ── keyword scan ──────────────────────────────────────────────────────────────


def _keyword_scan(query: str, limit_per_kind: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    hits.extend(_scan_inbox(query, limit_per_kind))
    hits.extend(_scan_tasks(query, limit_per_kind))
    hits.extend(_scan_decisions(query, limit_per_kind))
    hits.extend(_scan_agent_log(query, limit_per_kind))
    hits.extend(_scan_problems(query, limit_per_kind))
    hits.extend(_scan_exams(query, limit_per_kind))
    hits.extend(_scan_forge_runs(query, limit_per_kind))
    return hits


def _kw_score(query: str, field: str) -> float:
    """Keyword relevance: len(query) / len(field) + 0.3, capped at 0.95."""
    if not field:
        return 0.3
    raw = len(query) / max(len(field), 1) + 0.3
    return min(raw, 0.95)


def _snip(text: str) -> str:
    return text[:_SNIPPET_MAX]


def _state_path(filename: str) -> Path:
    from jarvis.config import get_settings

    return get_settings().state_dir / filename


def _load_jsonl(filename: str) -> list[dict[str, Any]]:
    path = _state_path(filename)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # For JSONL files that may have duplicate IDs (later record wins)
        rec_id = _record_id(rec)
        if rec_id:
            seen_ids.discard(rec_id)
            # Add at end; dedup later by taking last occurrence per id
        records.append(rec)
    return records


def _record_id(rec: dict[str, Any]) -> str | None:
    return rec.get("id") or rec.get("request_id") or rec.get("session_id") or rec.get("run_id")


def _dedup_jsonl(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep last occurrence of each record by its id field."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        rid = _record_id(rec)
        if rid:
            seen[rid] = rec
        else:
            # No stable id — keep as-is (append with synthetic key)
            seen[id(rec)] = rec  # type: ignore[arg-type]
    return list(seen.values())


def _scan_inbox(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    hits: list[SearchHit] = []
    records = _load_jsonl("inbox.jsonl")
    for i, rec in enumerate(records):
        summary = rec.get("summary", "")
        agent = rec.get("agent", "")
        text = f"{summary} {agent}"
        if ql not in text.lower():
            continue
        hit_id = f"inbox_{i}"
        hits.append(
            SearchHit(
                kind="inbox",
                id=hit_id,
                title=summary[:80] or "(inbox event)",
                snippet=_snip(summary),
                ts=rec.get("ts", ""),
                score=_kw_score(query, summary),
                href=f"/inbox#{hit_id}",
                metadata={"agent": agent, "severity": rec.get("severity", "")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_tasks(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    path = _state_path("tasks.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data.get("tasks", []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, OSError):
        return []

    hits: list[SearchHit] = []
    for task in tasks:
        title = task.get("title", "")
        tags_str = " ".join(task.get("tags", []))
        text = f"{title} {tags_str}"
        if ql not in text.lower():
            continue
        task_id = task.get("id", "")
        hits.append(
            SearchHit(
                kind="task",
                id=task_id,
                title=title,
                snippet=_snip(f"{title} [{task.get('status', '')}]"),
                ts=task.get("updated", task.get("created", "")),
                score=_kw_score(query, title),
                href=f"/status-board?task={task_id}",
                metadata={"status": task.get("status"), "due": task.get("due")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_decisions(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    records = _dedup_jsonl(_load_jsonl("confirmations.jsonl"))
    hits: list[SearchHit] = []
    for rec in records:
        intent = rec.get("intent", "")
        summary = rec.get("summary", "")
        request = rec.get("request", "")
        text = f"{intent} {summary} {request}"
        if ql not in text.lower():
            continue
        conf_id = rec.get("id", "")
        title = intent or summary or "decision"
        hits.append(
            SearchHit(
                kind="decision",
                id=conf_id,
                title=title[:80],
                snippet=_snip(summary or intent),
                ts=rec.get("ts", ""),
                score=_kw_score(query, text),
                href=f"/decisions#{conf_id}",
                metadata={"status": rec.get("status"), "agent": rec.get("agent")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_agent_log(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    records = _load_jsonl("agent_log.jsonl")
    hits: list[SearchHit] = []
    for rec in records:
        agent = rec.get("agent", "")
        action = rec.get("action", "")
        error = rec.get("error") or ""
        text = f"{agent} {action} {error}"
        if ql not in text.lower():
            continue
        req_id = rec.get("request_id", "")
        title = f"{agent}: {action}"
        hits.append(
            SearchHit(
                kind="agent_log",
                id=req_id,
                title=title[:80],
                snippet=_snip(f"{title} ({rec.get('status', '')})" + (f" — {error}" if error else "")),
                ts=rec.get("ts", ""),
                score=_kw_score(query, text),
                href=f"/activity#{req_id}",
                metadata={"status": rec.get("status"), "agent": agent},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_problems(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    records = _load_jsonl("scholar_problems.jsonl")
    hits: list[SearchHit] = []
    for rec in records:
        problem = rec.get("problem", "")
        course = rec.get("course", "")
        response = rec.get("response") or {}
        final_answer = response.get("final_answer", "") if isinstance(response, dict) else ""
        text = f"{problem} {course} {final_answer}"
        if ql not in text.lower():
            continue
        prob_id = rec.get("id", "")
        hits.append(
            SearchHit(
                kind="problem",
                id=prob_id,
                title=problem[:80],
                snippet=_snip(f"[{course}] {problem}"),
                ts=rec.get("ts", ""),
                score=_kw_score(query, text),
                href=f"/scholar?problem={prob_id}",
                metadata={"course": course, "rated_correct": rec.get("rated_correct")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_exams(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    records = _load_jsonl("scholar_exams.jsonl")
    hits: list[SearchHit] = []
    for rec in records:
        course = rec.get("course", "")
        session_id = rec.get("session_id", "")
        problems = rec.get("problems", [])
        problem_text = " ".join(
            p.get("prompt", "") for p in problems if isinstance(p, dict)
        )
        text = f"{course} {problem_text}"
        if ql not in text.lower():
            continue
        hits.append(
            SearchHit(
                kind="exam",
                id=session_id,
                title=f"Exam: {course}"[:80],
                snippet=_snip(f"[{course}] {rec.get('started_iso', '')} — {len(problems)} problems"),
                ts=rec.get("started_iso", ""),
                score=_kw_score(query, text),
                href=f"/scholar?exam={session_id}",
                metadata={"course": course, "duration_min": rec.get("duration_min")},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _scan_forge_runs(query: str, limit: int) -> list[SearchHit]:
    ql = query.lower()
    records = _dedup_jsonl(_load_jsonl("forge_runs.jsonl"))
    hits: list[SearchHit] = []
    for rec in records:
        task = rec.get("task", "")
        branch = rec.get("branch", "")
        diff = rec.get("diff_summary", "")
        text = f"{task} {branch} {diff}"
        if ql not in text.lower():
            continue
        run_id = rec.get("run_id", "")
        hits.append(
            SearchHit(
                kind="forge_run",
                id=run_id,
                title=task[:80],
                snippet=_snip(f"[{rec.get('status', '')}] {task}"),
                ts=rec.get("started_iso", ""),
                score=_kw_score(query, text),
                href=f"/team/forge?run={run_id}",
                metadata={"status": rec.get("status"), "branch": branch},
            )
        )
        if len(hits) >= limit:
            break
    return hits


# ── semantic chat ─────────────────────────────────────────────────────────────


def _semantic_chat(query: str, limit: int) -> list[SearchHit]:
    try:
        from jarvis import memory_index

        results = memory_index.search(query, top_k=limit)
    except Exception as exc:
        log.debug("semantic search failed: %s", exc)
        return []

    hits: list[SearchHit] = []
    for score, turn in results:
        hits.append(
            SearchHit(
                kind="chat",
                id=turn.turn_id,
                title=f"[{turn.role}] {turn.text[:60]}",
                snippet=_snip(turn.text),
                ts=turn.ts,
                score=float(score),
                href=f"/jarvis?recall={turn.turn_id}",
                metadata={"role": turn.role, "lane": turn.lane},
            )
        )
    return hits


# ── merge + dedup ─────────────────────────────────────────────────────────────


def _merge(
    keyword: list[SearchHit],
    semantic: list[SearchHit],
    limit_per_kind: int,
) -> list[SearchHit]:
    """Merge keyword + semantic hits, dedupe (kind, id) keeping higher score,
    enforce limit_per_kind, sort by score desc."""
    combined: dict[tuple[str, str], SearchHit] = {}

    for hit in keyword + semantic:
        key = (hit.kind, hit.id)
        existing = combined.get(key)
        if existing is None or hit.score > existing.score:
            combined[key] = hit

    # Group by kind, apply per-kind limit
    by_kind: dict[str, list[SearchHit]] = {}
    for hit in combined.values():
        by_kind.setdefault(hit.kind, []).append(hit)

    result: list[SearchHit] = []
    for kind_hits in by_kind.values():
        kind_hits.sort(key=lambda h: h.score, reverse=True)
        result.extend(kind_hits[:limit_per_kind])

    result.sort(key=lambda h: h.score, reverse=True)
    return result
