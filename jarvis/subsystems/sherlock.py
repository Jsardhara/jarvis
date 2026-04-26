"""Sherlock — research client.

Phase 2 ships an Exa-shaped Protocol + a deterministic mock. The CC agent
prompt at .claude/agents/sherlock.md uses the Exa MCP directly when running
under Claude Code; this module is for the daemon and tests.
"""
from __future__ import annotations

from typing import Protocol

from ..contract import AgentResponse


class SearchProvider(Protocol):
    def search(self, query: str, num_results: int = 5) -> list[dict]: ...
    def fetch(self, url: str) -> dict: ...


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


class Sherlock:
    def __init__(self, search: SearchProvider):
        self.search_provider = search

    def quick_search(self, query: str, num_results: int = 5) -> AgentResponse:
        results = self.search_provider.search(query, num_results=num_results)
        markdown = self._to_markdown(query, results)
        return AgentResponse(
            agent="sherlock",
            intent="quick_search",
            action="searched",
            result={
                "query": query,
                "results": results,
                "markdown": markdown,
                "count": len(results),
            },
            confidence=0.9,
        )

    def deep_research(self, query: str, depth: int = 3) -> AgentResponse:
        """Multi-step research: search → fetch top N → synthesize."""
        top = self.search_provider.search(query, num_results=depth)
        bodies = [self.search_provider.fetch(r["url"]) for r in top]
        markdown = self._synthesize_markdown(query, top, bodies)
        return AgentResponse(
            agent="sherlock",
            intent="deep_research",
            action="researched",
            result={
                "query": query,
                "sources": [{"url": r["url"], "title": r["title"]} for r in top],
                "markdown": markdown,
                "depth": depth,
            },
            confidence=0.85,
        )

    @staticmethod
    def _to_markdown(query: str, results: list[dict]) -> str:
        lines = [f"# Search: {query}", ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r['title']}]({r['url']})")
            if r.get("snippet"):
                lines.append(f"   - {r['snippet']}")
        return "\n".join(lines)

    @staticmethod
    def _synthesize_markdown(query: str, top: list[dict], bodies: list[dict]) -> str:
        lines = [f"# Research: {query}", "", "## TL;DR", ""]
        lines.append(f"Synthesized from {len(top)} sources. (LLM synthesis lives in the CC agent.)")
        lines.append("")
        lines.append("## Sources")
        for r, b in zip(top, bodies, strict=False):
            lines.append(f"- **[{r['title']}]({r['url']})** — {b.get('text', '')[:120]}")
        return "\n".join(lines)
