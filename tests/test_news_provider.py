"""Tests for jarvis.agents.lens.news_provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.agents.lens.news_provider import (
    NewsItem,
    dedup_items,
    parse_feed,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _rss(items: list[tuple[str, str, str]], pub_offset_hours: int = 0) -> bytes:
    """Build a minimal RSS feed body. items = [(title, link, summary), ...]."""
    pub = datetime.now(UTC) - timedelta(hours=pub_offset_hours)
    pub_str = pub.strftime("%a, %d %b %Y %H:%M:%S +0000")
    blocks = []
    for title, link, summary in items:
        blocks.append(
            f"<item><title>{title}</title><link>{link}</link>"
            f"<description>{summary}</description><pubDate>{pub_str}</pubDate></item>"
        )
    body = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>fixture</title>" + "".join(blocks) + "</channel></rss>"
    )
    return body.encode("utf-8")


# ── parse_feed ────────────────────────────────────────────────────────────────


def test_parse_feed_extracts_basic_fields():
    body = _rss([("Earthquake hits Pacific", "https://r.com/x", "Magnitude 6 reported")])
    items = parse_feed("Reuters", body)
    assert len(items) == 1
    assert items[0].title == "Earthquake hits Pacific"
    assert items[0].url == "https://r.com/x"
    assert "Magnitude 6" in items[0].summary
    assert items[0].source == "Reuters"
    assert isinstance(items[0].published, datetime)


def test_parse_feed_strips_html():
    body = _rss([("Title", "https://r.com/x", "<b>bold</b> text")])
    items = parse_feed("AP", body)
    assert items[0].summary == "bold text"


def test_parse_feed_skips_entries_without_required_fields():
    body = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
    body += b"<item><title></title><link></link></item></channel></rss>"
    items = parse_feed("BBC", body)
    assert items == []


def test_parse_feed_handles_malformed_input():
    items = parse_feed("Reuters", b"not xml")
    assert items == []


# ── dedup_items ───────────────────────────────────────────────────────────────


def _item(title: str, source: str = "Reuters", offset_min: int = 0) -> NewsItem:
    return NewsItem(
        title=title,
        summary="",
        url=f"https://r.com/{title.replace(' ', '_')}",
        published=datetime.now(UTC) - timedelta(minutes=offset_min),
        source=source,
    )


def test_dedup_drops_near_duplicates():
    items = [
        _item("Earthquake hits Pacific coast", offset_min=0),
        _item("Earthquake hits Pacific coast region", source="AP", offset_min=10),
        _item("Stock market closes higher", offset_min=20),
    ]
    out = dedup_items(items)
    titles = [it.title for it in out]
    # Both quake stories collapse to the newer one
    assert any("Earthquake" in t for t in titles)
    assert any("Stock market" in t for t in titles)
    assert len(out) == 2


def test_dedup_keeps_newest_per_cluster():
    items = [
        _item("UN summit opens in Geneva", offset_min=120),  # older
        _item("UN summit opens in Geneva today", source="BBC", offset_min=5),  # newer
    ]
    out = dedup_items(items)
    assert len(out) == 1
    assert "today" in out[0].title


def test_dedup_keeps_distinct_stories():
    items = [
        _item("Earthquake Pacific", offset_min=0),
        _item("Election result Brazil", offset_min=10),
        _item("Climate report released UN", offset_min=20),
    ]
    out = dedup_items(items)
    assert len(out) == 3


# ── Async fetch (mocked) ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_world_brief_async_uses_window(monkeypatch):
    """Items older than window_hours are filtered out."""
    from jarvis.agents.lens import news_provider as np

    fresh = _item("Fresh story", offset_min=10)
    stale = NewsItem(
        title="Stale story",
        summary="",
        url="https://r.com/old",
        published=datetime.now(UTC) - timedelta(hours=48),
        source="Reuters",
    )

    async def fake_fetch_one(client, source, url):
        return [fresh, stale]

    monkeypatch.setattr(np, "_fetch_one", fake_fetch_one)
    out = await np.fetch_world_brief_async(window_hours=18)
    titles = [it.title for it in out]
    assert "Fresh story" in titles
    assert "Stale story" not in titles
