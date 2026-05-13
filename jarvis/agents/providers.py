"""Provider protocols and mock implementations.

Tempo owns Outlook (mail + calendar + tasks) via Microsoft Graph.
Real OutlookProvider lands once Azure app registration is supplied.
Until then MockOutlook gives deterministic fixtures so the rest of the
stack runs end-to-end.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

log = logging.getLogger(__name__)


# Module-import diagnostic: warn loud and once when no live web-search key is set
# so the dashboard / operator know Lens is in fallback mode rather than silently
# serving fixture data. Cleared once the key appears (the registry recomputes on
# each ``build_default_registry`` call, this is a one-shot import-time signal).
if not (
    os.environ.get("BRAVE_SEARCH_API_KEY")
    or os.environ.get("PERPLEXITY_API_KEY")
    or os.environ.get("EXA_API_KEY")
):
    log.warning(
        "lens: no web-search API key set (BRAVE_SEARCH_API_KEY / "
        "PERPLEXITY_API_KEY / EXA_API_KEY) — falling back to MockSearch. "
        "Responses will be marked degraded=True."
    )


class OutlookProvider(Protocol):
    # Mail
    def list_unread(self, max_results: int = 25) -> list[dict]: ...
    def list_recent(self, max_results: int = 25) -> list[dict]: ...
    def search_mail(self, query: str, max_results: int = 25) -> list[dict]: ...
    def get_message(self, msg_id: str) -> dict: ...
    def draft_reply(self, msg_id: str, body: str) -> dict: ...
    def send(self, to: str, subject: str, body: str) -> dict: ...

    # Calendar
    def list_events(self, start_iso: str, end_iso: str) -> list[dict]: ...
    def create_event(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> dict: ...
    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> list[dict]: ...
    def cancel_event(self, event_id: str) -> dict: ...

    # Tasks (Microsoft To Do)
    def list_tasks(self) -> list[dict]: ...
    def add_task_remote(self, title: str, due: str | None) -> dict: ...
    def complete_task_remote(self, task_id: str) -> dict: ...


class SearchProvider(Protocol):
    def search(self, query: str, num_results: int = 5) -> list[dict]: ...
    def fetch(self, url: str) -> dict: ...


# ---------- Mocks (default until creds wired) ----------


class MockOutlook:
    """Single mock that fakes mail + calendar + tasks behind the OutlookProvider Protocol."""

    def __init__(
        self,
        seed_mail: list[dict] | None = None,
        seed_events: list[dict] | None = None,
        seed_tasks: list[dict] | None = None,
    ):
        self._mail: dict[str, dict] = {m["id"]: m for m in (seed_mail if seed_mail is not None else _seed_mail())}
        self._events: dict[str, dict] = {e["id"]: e for e in (seed_events if seed_events is not None else _seed_events())}
        self._tasks: dict[str, dict] = {t["id"]: t for t in (seed_tasks if seed_tasks is not None else _seed_tasks())}
        self._sent: list[dict] = []

    # Mail
    def list_unread(self, max_results: int = 25) -> list[dict]:
        unread = [m for m in self._mail.values() if "UNREAD" in m.get("labels", [])]
        return unread[:max_results]

    def list_recent(self, max_results: int = 25) -> list[dict]:
        return list(self._mail.values())[:max_results]

    def search_mail(self, query: str, max_results: int = 25) -> list[dict]:
        q = query.lower().strip()
        if not q:
            return []
        hits = [
            m for m in self._mail.values()
            if q in (m.get("subject") or "").lower()
            or q in (m.get("snippet") or "").lower()
            or q in (m.get("from") or "").lower()
        ]
        return hits[:max_results]

    def get_message(self, msg_id: str) -> dict:
        return self._mail[msg_id]

    def draft_reply(self, msg_id: str, body: str) -> dict:
        return {"draft_id": f"draft-{uuid4().hex[:8]}", "in_reply_to": msg_id, "body": body}

    def send(self, to: str, subject: str, body: str) -> dict:
        rec = {
            "id": f"sent-{uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "ts": datetime.now(UTC).isoformat(),
        }
        self._sent.append(rec)
        return rec

    @property
    def sent(self) -> list[dict]:
        return list(self._sent)

    # Calendar
    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return [e for e in self._events.values() if start_iso <= e["start"] <= end_iso]

    def create_event(self, summary: str, start_iso: str, end_iso: str, attendees: list[str]) -> dict:
        eid = f"ev-{uuid4().hex[:8]}"
        evt = {
            "id": eid,
            "summary": summary,
            "start": start_iso,
            "end": end_iso,
            "attendees": attendees,
        }
        self._events[eid] = evt
        return evt

    def find_free(self, duration_min: int, window_start_iso: str, window_end_iso: str) -> list[dict]:
        return [{"start": window_start_iso, "end": window_end_iso, "duration_min": duration_min}]

    def cancel_event(self, event_id: str) -> dict:
        evt = self._events.pop(event_id, None)
        return {"cancelled": event_id, "found": evt is not None}

    # Tasks
    def list_tasks(self) -> list[dict]:
        return list(self._tasks.values())

    def add_task_remote(self, title: str, due: str | None) -> dict:
        tid = f"todo-{uuid4().hex[:8]}"
        task = {"id": tid, "title": title, "due": due, "status": "open"}
        self._tasks[tid] = task
        return task

    def complete_task_remote(self, task_id: str) -> dict:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "done"
            return self._tasks[task_id]
        return {"id": task_id, "status": "not_found"}


def _seed_mail() -> list[dict]:
    return [
        {
            "id": "m1",
            "from": "professor@university.edu",
            "subject": "Office hours moved to Thursday",
            "snippet": "Hi class — moving Thursday OH to 2pm.",
            "labels": ["UNREAD", "INBOX"],
        },
        {
            "id": "m2",
            "from": "manager@work.com",
            "subject": "Friday review",
            "snippet": "Can we sync at 3pm Friday on the Q2 plan?",
            "labels": ["UNREAD", "INBOX", "IMPORTANT"],
        },
        {
            "id": "m3",
            "from": "newsletter@medium.com",
            "subject": "Top stories this week",
            "snippet": "The 10 best engineering reads…",
            "labels": ["UNREAD", "INBOX", "CATEGORY_PROMOTIONS"],
        },
    ]


def _seed_events() -> list[dict]:
    today = datetime.now(UTC).date().isoformat()
    return [
        {
            "id": "ev1",
            "summary": "Standup",
            "start": f"{today}T14:00:00+00:00",
            "end": f"{today}T14:30:00+00:00",
            "attendees": ["team@example.com"],
        },
    ]


def _seed_tasks() -> list[dict]:
    return [
        {"id": "todo-1", "title": "Submit CS401 problem set", "due": None, "status": "open"},
    ]


class MockSearch:
    def __init__(self, fixtures: dict[str, list[dict]] | None = None):
        self._fixtures = fixtures or {}

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        return self._fixtures.get(query, [
            {
                "title": f"Result {i + 1} for '{query}'",
                "url": f"https://example.com/{query.replace(' ', '-')}/{i + 1}",
                "snippet": f"Mock snippet {i + 1}",
                "score": 1.0 - i * 0.1,
            }
            for i in range(num_results)
        ])

    def fetch(self, url: str) -> dict:
        return {"url": url, "text": f"Mock body for {url}", "title": "Mock"}


class PerplexitySearch:
    """Perplexity Search provider — direct HTTPS calls to api.perplexity.ai.

    Instantiated when ``PERPLEXITY_API_KEY`` is present in env. Hits the
    /search endpoint for query results and falls back to a plain HTTP GET +
    crude text extraction for ``fetch`` (Perplexity Search API does not
    expose a URL-content endpoint).

    Same data the perplexity-search-mcp server returns; direct HTTPS skips
    the Node subprocess + JSON-RPC stdio hop, which only matters for
    interactive MCP clients (Claude Desktop) — not for a long-running
    Python subsystem.
    """

    BASE_URL = "https://api.perplexity.ai"
    TIMEOUT_S = 15.0

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        import httpx

        payload = {
            "query": query,
            "max_results": max(1, min(num_results, 20)),
            "max_tokens_per_page": 1024,
        }
        try:
            resp = httpx.post(
                f"{self.BASE_URL}/search",
                json=payload,
                headers=self._headers(),
                timeout=self.TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            return []

        out: list[dict] = []
        for item in data.get("results", []):
            snippet = item.get("snippet") or ""
            out.append(
                {
                    "title": item.get("title") or item.get("url", ""),
                    "url": item.get("url", ""),
                    "snippet": snippet[:480],
                    "date": item.get("date"),
                    "last_updated": item.get("last_updated"),
                }
            )
        return out

    def fetch(self, url: str) -> dict:
        """Best-effort URL body fetch + crude text strip.

        Used by Lens.deep_research to feed synthesis. Perplexity Search has
        no URL-content endpoint, so we GET the page directly. Fails open
        with empty text rather than raising.
        """
        import re

        import httpx

        try:
            resp = httpx.get(
                url,
                timeout=self.TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": "JarvisLens/0.2 (research)"},
            )
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPError:
            return {"url": url, "title": "", "text": ""}

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = (title_match.group(1).strip() if title_match else "")[:200]
        # Strip script/style blocks then HTML tags
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return {"url": url, "title": title, "text": cleaned[:4000]}


class BraveSearch:
    """Brave Search API provider — 2000 queries/mo free tier.

    Endpoint: GET https://api.search.brave.com/res/v1/web/search
    Auth:     X-Subscription-Token: <key>
    Sign up:  https://api-dashboard.search.brave.com/

    Returns same shape as PerplexitySearch / MockSearch so Lens callers
    don't change. ``fetch`` is a plain HTTP GET + crude HTML strip — Brave
    Search doesn't expose URL-content extraction.
    """

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"
    TIMEOUT_S = 12.0

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        import httpx

        params = {
            "q": query,
            "count": str(max(1, min(num_results, 20))),
            "safesearch": "moderate",
        }
        try:
            resp = httpx.get(
                self.BASE_URL,
                params=params,
                headers=self._headers(),
                timeout=self.TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            return []

        results = (data.get("web") or {}).get("results", [])
        out: list[dict] = []
        for item in results[:num_results]:
            description = item.get("description") or ""
            out.append(
                {
                    "title": item.get("title") or item.get("url", ""),
                    "url": item.get("url", ""),
                    "snippet": description[:480],
                    "date": item.get("page_age"),
                    "last_updated": item.get("page_fetched"),
                }
            )
        return out

    def fetch(self, url: str) -> dict:
        import re

        import httpx

        try:
            resp = httpx.get(
                url,
                timeout=self.TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": "JarvisLens/0.2 (research)"},
            )
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPError:
            return {"url": url, "title": "", "text": ""}

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = (title_match.group(1).strip() if title_match else "")[:200]
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return {"url": url, "title": title, "text": cleaned[:4000]}


# Back-compat alias — registry imports `ExaSearch` from this module.
ExaSearch = PerplexitySearch
