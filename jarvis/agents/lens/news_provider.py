"""Unbiased world-news provider — mainstream RSS aggregation.

Pulls BBC, NPR, AlJazeera, and Google News RSS feeds in parallel, dedups
by title similarity, returns last-N-hours sorted by recency. Used by
``lens.world_brief``.

Reasoning: a mix of UK, US, Middle-East, and global-aggregator sources
broadens the editorial frame relative to any single outlet. No Exa or LLM
call here — that layer is optional in lens.py. See :data:`FEEDS` for the
authoritative source list.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

log = logging.getLogger(__name__)


# ── Feed catalogue ────────────────────────────────────────────────────────────

FEEDS: tuple[tuple[str, str], ...] = (
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml"),
    ("AlJazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Google News", "https://news.google.com/rss/search?q=when:1d&hl=en-US&gl=US&ceid=US:en"),
)


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    url: str
    published: datetime
    source: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published": self.published.isoformat(),
            "source": self.source,
        }


# ── Parsing ───────────────────────────────────────────────────────────────────


_HTML_TAG = re.compile(r"<[^>]+>")
_TOKEN = re.compile(r"\b\w+\b", re.UNICODE)


def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text or "").strip()


def _parse_published(entry: dict) -> datetime | None:
    """Best-effort RFC822 → UTC datetime."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def parse_feed(source: str, body: bytes) -> list[NewsItem]:
    """Parse an RSS/Atom feed body into NewsItems. Resilient to malformed input."""
    parsed = feedparser.parse(body)
    items: list[NewsItem] = []
    for entry in parsed.entries:
        title = _strip_html(entry.get("title", ""))
        url = entry.get("link", "")
        if not title or not url:
            continue
        published = _parse_published(entry)
        if published is None:
            continue
        summary = _strip_html(entry.get("summary", ""))[:500]
        items.append(
            NewsItem(
                title=title,
                summary=summary,
                url=url,
                published=published,
                source=source,
            )
        )
    return items


# ── Dedup ─────────────────────────────────────────────────────────────────────


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) >= 4}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedup_items(items: Iterable[NewsItem], threshold: float = 0.55) -> list[NewsItem]:
    """Drop near-duplicate stories. Keeps newest per cluster."""
    sorted_items = sorted(items, key=lambda x: x.published, reverse=True)
    kept: list[NewsItem] = []
    kept_tokens: list[set[str]] = []
    for item in sorted_items:
        tokens = _tokens(item.title)
        is_dup = any(_jaccard(tokens, prev) >= threshold for prev in kept_tokens)
        if not is_dup:
            kept.append(item)
            kept_tokens.append(tokens)
    return kept


# ── Fetching ──────────────────────────────────────────────────────────────────


async def _fetch_one(client: httpx.AsyncClient, source: str, url: str) -> list[NewsItem]:
    try:
        resp = await client.get(url, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        return parse_feed(source, resp.content)
    except Exception as exc:  # network or parser issue — skip this feed
        log.warning("news_provider feed %s failed: %s", source, exc)
        return []


async def fetch_world_brief_async(window_hours: int = 18) -> list[NewsItem]:
    """Pull all feeds, filter to last *window_hours*, dedup, sort by recency."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    async with httpx.AsyncClient(headers={"User-Agent": "Jarvis/1.0"}) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, src, url) for src, url in FEEDS)
        )
    flat: list[NewsItem] = [item for batch in results for item in batch]
    fresh = [it for it in flat if it.published >= cutoff]
    return dedup_items(fresh)


def fetch_world_brief(window_hours: int = 18) -> list[NewsItem]:
    """Synchronous wrapper for callers outside an event loop."""
    return asyncio.run(fetch_world_brief_async(window_hours=window_hours))
