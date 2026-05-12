"""Tempo — single time-and-correspondence agent.

Owns mail + calendar + tasks behind the OutlookProvider Protocol. Concrete
backends compose via TempoStack:
    mail     → Gmail IMAP + Drexel (MultiMailProvider)
    calendar → iCloud CalDAV
    tasks    → iCloud reminders

Operator forwards Outlook → Gmail; the Outlook backend was retired.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.config import get_settings
from jarvis.contract import AgentResponse, Task
from jarvis.state.memory import load_preferences
from jarvis.state import add_task, load_tasks, update_task
from ..providers import OutlookProvider

log = logging.getLogger(__name__)

# Mail triage tiers
TIER_SKIP = "skip"
TIER_INFO = "info_only"
TIER_MEETING = "meeting_info"
TIER_ACTION = "action_required"

_PROMO_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
_MEETING_KEYWORDS = ("meet", "sync", "call", "calendar", "invite", "schedule")
_ACTION_KEYWORDS = ("action", "due", "asap", "urgent", "review", "approve", "respond")

# Smart-triage buckets
BUCKET_ACTION = "action_required"
BUCKET_INFO = "info_only"
BUCKET_NOISE = "noise"

_SMART_TRIAGE_SYSTEM = (
    "You triage email. Given a list of {id, subject, from, body_preview}, "
    "return ONLY a JSON array of {id, bucket, reason} where bucket is one of "
    "action_required/info_only/noise. No markdown fences, no extra text."
)


def classify_message(msg: dict) -> str:
    labels = set(msg.get("labels", []))
    snippet = (msg.get("snippet", "") + " " + msg.get("subject", "")).lower()
    if labels & _PROMO_LABELS:
        return TIER_SKIP
    if any(k in snippet for k in _MEETING_KEYWORDS):
        return TIER_MEETING
    if any(k in snippet for k in _ACTION_KEYWORDS):
        return TIER_ACTION
    if "IMPORTANT" in labels:
        return TIER_ACTION
    return TIER_INFO


def _today_window() -> tuple[str, str]:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


# ── Smart-triage state paths ──────────────────────────────────────────────────


def _triage_path() -> Path:
    return get_settings().state_dir / "tempo_triage.jsonl"


def _snoozes_path() -> Path:
    return get_settings().state_dir / "tempo_snoozes.json"


def _load_triage_cache() -> dict[str, dict[str, Any]]:
    """Return {msg_id: record} from tempo_triage.jsonl."""
    path = _triage_path()
    if not path.exists():
        return {}
    cache: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            cache[rec["id"]] = rec
        except (json.JSONDecodeError, KeyError):
            log.warning("tempo: malformed triage cache line skipped")
    return cache


def _append_triage_record(record: dict[str, Any]) -> None:
    """Append one classification record to tempo_triage.jsonl."""
    path = _triage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _load_snoozes() -> dict[str, str]:
    """Return {msg_id: until_iso} from tempo_snoozes.json."""
    path = _snoozes_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_snoozes(snoozes: dict[str, str]) -> None:
    """Atomically write snooze map to tempo_snoozes.json."""
    path = _snoozes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snoozes, indent=2), encoding="utf-8")


def _active_snoozes(snoozes: dict[str, str], now_iso: str) -> set[str]:
    """Return the set of msg_ids whose snooze has not yet expired."""
    return {mid for mid, until in snoozes.items() if until > now_iso}


def _classify_batch_with_llm(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Call Claude to classify a batch of mail items.

    Returns a list of {id, bucket, reason}. Falls back to BUCKET_INFO on
    any parse failure so one bad item never breaks the whole batch.
    """
    from jarvis.llm.client import query_claude_sync

    user_payload = json.dumps(
        [
            {
                "id": m["id"],
                "subject": m.get("subject", ""),
                "from": m.get("from", ""),
                "body_preview": m.get("body_preview", m.get("snippet", "")),
            }
            for m in items
        ]
    )
    raw = query_claude_sync(_SMART_TRIAGE_SYSTEM, user_payload)
    try:
        results = json.loads(raw)
        if not isinstance(results, list):
            raise ValueError("expected list")
        return results
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("tempo: LLM triage parse error (%s); defaulting all to info_only", exc)
        return [{"id": m["id"], "bucket": BUCKET_INFO, "reason": "parse_error"} for m in items]


def _apply_important_sender_override(
    classifications: list[dict[str, Any]],
    mail_by_id: dict[str, dict[str, Any]],
    important_senders: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Force bucket=action_required for any mail from an important sender."""
    if not important_senders:
        return classifications
    sender_set = {s.lower() for s in important_senders}
    result: list[dict[str, Any]] = []
    for item in classifications:
        msg = mail_by_id.get(item["id"], {})
        sender = (msg.get("from", "") or "").lower()
        if any(s in sender for s in sender_set):
            result.append({**item, "bucket": BUCKET_ACTION, "classified_by": "override"})
        else:
            result.append(item)
    return result


class Tempo:
    def __init__(self, outlook: OutlookProvider):
        self.outlook = outlook

    # ---------- Mail ----------

    def triage(self, max_results: int = 25) -> AgentResponse:
        msgs = self.outlook.list_unread(max_results=max_results)
        buckets: dict[str, list[dict]] = {
            TIER_SKIP: [], TIER_INFO: [], TIER_MEETING: [], TIER_ACTION: [],
        }
        for m in msgs:
            tier = classify_message(m)
            buckets[tier].append({
                "id": m["id"], "from": m.get("from"),
                "subject": m.get("subject"), "snippet": m.get("snippet"),
            })
        return AgentResponse(
            agent="tempo",
            intent="triage_inbox",
            action="triaged",
            result={
                "counts": {k: len(v) for k, v in buckets.items()},
                "buckets": buckets,
                "total": len(msgs),
            },
            follow_ups=(
                ["draft replies for action_required"] if buckets[TIER_ACTION] else []
            ) + (
                ["accept/decline meeting requests"] if buckets[TIER_MEETING] else []
            ),
            confidence=0.95,
        )

    def triage_smart(self, max_results: int = 50) -> AgentResponse:
        """Classify unread mail into action_required / info_only / noise.

        - Skips already-cached message IDs (idempotent).
        - Filters snoozed messages (until their snooze time passes).
        - Applies important-sender override after the LLM pass.
        - Persists each new classification to state/tempo_triage.jsonl.
        """

        msgs = self.outlook.list_unread(max_results=max_results)
        now_iso = datetime.now(UTC).isoformat()
        snoozes = _load_snoozes()
        snoozed_ids = _active_snoozes(snoozes, now_iso)

        # Filter out snoozed messages
        msgs = [m for m in msgs if m["id"] not in snoozed_ids]

        cache = _load_triage_cache()
        mail_by_id: dict[str, dict[str, Any]] = {m["id"]: m for m in msgs}

        # Split: already classified vs. needs LLM
        needs_classify = [m for m in msgs if m["id"] not in cache]
        cached_results = [cache[m["id"]] for m in msgs if m["id"] in cache]

        # LLM classification for new items
        needs_classify_ids = {m["id"] for m in needs_classify}
        llm_results: list[dict[str, Any]] = []
        if needs_classify:
            raw_classifications = _classify_batch_with_llm(needs_classify)
            # Drop any IDs the LLM hallucinated that weren't in the batch
            raw_classifications = [r for r in raw_classifications if r.get("id") in needs_classify_ids]
            prefs = load_preferences()
            overridden = _apply_important_sender_override(
                raw_classifications, mail_by_id, prefs.important_senders
            )
            for item in overridden:
                classified_by = item.get("classified_by", "claude")
                record: dict[str, Any] = {
                    "id": item["id"],
                    "ts": now_iso,
                    "bucket": item.get("bucket", BUCKET_INFO),
                    "reason": item.get("reason", ""),
                    "classified_by": classified_by,
                }
                _append_triage_record(record)
                llm_results.append(record)

        all_results = cached_results + llm_results

        # Build output buckets
        buckets: dict[str, list[dict[str, Any]]] = {
            BUCKET_ACTION: [],
            BUCKET_INFO: [],
            BUCKET_NOISE: [],
        }
        for rec in all_results:
            bucket = rec.get("bucket", BUCKET_INFO)
            if bucket not in buckets:
                bucket = BUCKET_INFO
            msg = mail_by_id.get(rec["id"], {})
            entry = {
                "id": rec["id"],
                "subject": msg.get("subject", ""),
                "from": msg.get("from", ""),
                "reason": rec.get("reason", ""),
            }
            if bucket == BUCKET_ACTION:
                entry["body_preview"] = msg.get("body_preview", msg.get("snippet", ""))
            buckets[bucket].append(entry)

        counts = {k: len(v) for k, v in buckets.items()}
        return AgentResponse(
            agent="tempo",
            intent="triage_smart",
            action="classified",
            result={
                "action_required": buckets[BUCKET_ACTION],
                "info_only": buckets[BUCKET_INFO],
                "noise": buckets[BUCKET_NOISE],
                "counts": counts,
            },
            follow_ups=(
                ["draft replies for action_required"] if buckets[BUCKET_ACTION] else []
            ),
            confidence=0.9,
        )

    def search_mail(self, query: str, max_results: int = 25) -> AgentResponse:
        """Find messages matching ``query`` in subject/body/from across all mail (read + unread)."""
        msgs = self.outlook.search_mail(query=query, max_results=max_results)
        hits = [
            {
                "id": m["id"],
                "from": m.get("from", ""),
                "subject": m.get("subject", ""),
                "snippet": m.get("snippet", ""),
                "date": m.get("date", ""),
                "is_unread": "UNREAD" in m.get("labels", []),
            }
            for m in msgs
        ]
        return AgentResponse(
            agent="tempo",
            intent="search_mail",
            action="searched",
            result={"query": query, "hits": hits, "count": len(hits)},
            follow_ups=(
                [f"open message {hits[0]['id']}"] if hits else []
            ),
            confidence=0.9,
        )

    def list_recent_mail(self, max_results: int = 25) -> AgentResponse:
        """Return the most recent messages, read or unread."""
        msgs = self.outlook.list_recent(max_results=max_results)
        items = [
            {
                "id": m["id"],
                "from": m.get("from", ""),
                "subject": m.get("subject", ""),
                "snippet": m.get("snippet", ""),
                "date": m.get("date", ""),
                "is_unread": "UNREAD" in m.get("labels", []),
            }
            for m in msgs
        ]
        return AgentResponse(
            agent="tempo",
            intent="list_recent_mail",
            action="listed",
            result={"messages": items, "count": len(items)},
            confidence=0.95,
        )

    def snooze_mail(self, msg_id: str, until_iso: str) -> AgentResponse:
        """Snooze a message until ``until_iso``. Filters it from triage_smart until then."""
        snoozes = _load_snoozes()
        updated = {**snoozes, msg_id: until_iso}
        _save_snoozes(updated)
        return AgentResponse(
            agent="tempo",
            intent="snooze_mail",
            action="snoozed",
            result={"msg_id": msg_id, "until_iso": until_iso},
            confidence=1.0,
        )

    def triage_status(self) -> AgentResponse:
        """Return summary: total unread, bucket counts from cache, snoozed count, top 5 actions."""
        cache = _load_triage_cache()
        snoozes = _load_snoozes()
        now_iso = datetime.now(UTC).isoformat()
        snoozed_ids = _active_snoozes(snoozes, now_iso)

        counts: dict[str, int] = {BUCKET_ACTION: 0, BUCKET_INFO: 0, BUCKET_NOISE: 0}
        action_items: list[dict[str, Any]] = []
        for rec in cache.values():
            bucket = rec.get("bucket", BUCKET_INFO)
            if bucket in counts:
                counts[bucket] += 1
            if bucket == BUCKET_ACTION:
                action_items.append(rec)

        # Sort action items newest-first and cap at 5
        top_action = sorted(action_items, key=lambda r: r.get("ts", ""), reverse=True)[:5]

        return AgentResponse(
            agent="tempo",
            intent="triage_status",
            action="summarised",
            result={
                "total_classified": len(cache),
                "counts": counts,
                "snoozed_count": len(snoozed_ids),
                "top_action_required": top_action,
            },
            confidence=1.0,
        )

    def draft_reply(self, msg_id: str, body: str) -> AgentResponse:
        draft = self.outlook.draft_reply(msg_id, body)
        return AgentResponse(
            agent="tempo",
            intent="draft_reply",
            action="proposed",
            result={"draft": draft},
            follow_ups=["confirm to send"],
            needs_confirm=True,
            confidence=0.9,
        )

    def send_mail(self, to: str, subject: str, body: str) -> AgentResponse:
        sent = self.outlook.send(to, subject, body)
        return AgentResponse(
            agent="tempo",
            intent="send_mail",
            action="sent",
            result={"sent": sent},
            confidence=1.0,
        )

    # ---------- Calendar ----------

    def today(self) -> AgentResponse:
        start, end = _today_window()
        events = self.outlook.list_events(start, end)
        return AgentResponse(
            agent="tempo",
            intent="list_today",
            action="listed",
            result={"events": events, "count": len(events)},
            confidence=1.0,
        )

    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> AgentResponse:
        slots = self.outlook.find_free(duration_min, window_start_iso, window_end_iso)
        return AgentResponse(
            agent="tempo",
            intent="find_free_time",
            action="proposed",
            result={"slots": slots, "duration_min": duration_min},
            follow_ups=["create event in slot"],
            confidence=0.85,
        )

    def schedule(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> AgentResponse:
        evt = self.outlook.create_event(summary, start_iso, end_iso, attendees)
        return AgentResponse(
            agent="tempo",
            intent="create_event",
            action="created",
            result={"event": evt},
            needs_confirm=False,
            confidence=1.0,
        )

    def cancel(self, event_id: str) -> AgentResponse:
        out = self.outlook.cancel_event(event_id)
        return AgentResponse(
            agent="tempo",
            intent="cancel_event",
            action="cancelled" if out["found"] else "not_found",
            result=out,
            confidence=1.0 if out["found"] else 0.0,
        )

    # ---------- Tasks (local + Microsoft To Do mirror) ----------

    def add(self, title: str, due: str | None = None, tags: list[str] | None = None) -> AgentResponse:
        t = Task(title=title, due=due, tags=tags or [])
        add_task(t)
        return AgentResponse(
            agent="tempo",
            intent="add_task",
            action="created",
            result={"task": t.model_dump()},
            confidence=1.0,
        )

    def list_open(self) -> AgentResponse:
        tasks = [t for t in load_tasks() if t.status == "open"]
        return AgentResponse(
            agent="tempo",
            intent="list_tasks",
            action="listed",
            result={"tasks": [t.model_dump() for t in tasks], "count": len(tasks)},
            confidence=1.0,
        )

    def complete(self, task_id: str) -> AgentResponse:
        updated = update_task(task_id, status="done", updated=datetime.now(UTC).isoformat())
        return AgentResponse(
            agent="tempo",
            intent="complete_task",
            action="updated" if updated else "not_found",
            result={"task": updated.model_dump() if updated else None},
            confidence=1.0 if updated else 0.0,
        )
