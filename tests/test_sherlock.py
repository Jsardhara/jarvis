"""Sherlock research tests."""
from __future__ import annotations

from jarvis.subsystems.sherlock import MockSearch, Sherlock


def test_quick_search_returns_results():
    s = Sherlock(MockSearch())
    resp = s.quick_search("anthropic mcp", num_results=3)
    assert resp.action == "searched"
    assert resp.result["count"] == 3
    assert "anthropic mcp" in resp.result["markdown"]


def test_deep_research_synthesizes():
    s = Sherlock(MockSearch())
    resp = s.deep_research("FastAPI middleware", depth=2)
    assert resp.action == "researched"
    assert len(resp.result["sources"]) == 2
    assert "TL;DR" in resp.result["markdown"]


def test_quick_search_uses_fixture():
    fixtures = {"foo": [{"title": "Custom", "url": "https://x.io", "snippet": "s", "score": 1.0}]}
    s = Sherlock(MockSearch(fixtures))
    resp = s.quick_search("foo", num_results=5)
    assert resp.result["results"][0]["title"] == "Custom"


def test_markdown_includes_links():
    s = Sherlock(MockSearch())
    resp = s.quick_search("test")
    md = resp.result["markdown"]
    assert "https://example.com" in md
