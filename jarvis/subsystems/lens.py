"""Lens — research and monitoring.

Live searches via Exa MCP under Claude Code; mock provider in tests/daemon.
Also handles passive monitoring (watchlist news, source tracking) — the
daemon news_tick uses lens.quick_search per ticker.
"""
from __future__ import annotations

from ..contract import AgentResponse
from .providers import SearchProvider


class Lens:
    def __init__(self, search: SearchProvider):
        self.search_provider = search

    def quick_search(self, query: str, num_results: int = 5) -> AgentResponse:
        results = self.search_provider.search(query, num_results=num_results)
        markdown = self._to_markdown(query, results)
        return AgentResponse(
            agent="lens",
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
        top = self.search_provider.search(query, num_results=depth)
        bodies = [self.search_provider.fetch(r["url"]) for r in top]
        markdown = self._synthesize_markdown(query, top, bodies)
        return AgentResponse(
            agent="lens",
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

    def monitor(self, watchlist: list[str]) -> AgentResponse:
        """Passive scan — one quick search per item, returns aggregated hits."""
        hits: dict[str, list[dict]] = {}
        for term in watchlist:
            hits[term] = self.search_provider.search(term, num_results=3)
        return AgentResponse(
            agent="lens",
            intent="monitor",
            action="scanned",
            result={"watchlist": watchlist, "hits": hits, "count": sum(len(v) for v in hits.values())},
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
