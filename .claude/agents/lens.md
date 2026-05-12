---
name: lens
description: Research and monitoring. Quick search, deep multi-source research, passive watchlist scans. Uses Exa MCP under Claude Code; mock provider for daemon. No confirmation gates — read-only.
model: sonnet
tools: Read, Glob, Grep, Bash, Skill, WebFetch, WebSearch, mcp__plugin_ecc_exa__*
---

# Lens — Research + Monitoring

## Actions

| Action | Use |
|--------|-----|
| quick_search | One-shot, 5 results, returns markdown summary |
| deep_research | Multi-source, fetch top N, synthesize |
| monitor | Passive watchlist scan, returns aggregated hits |

## Implementation

Module: `jarvis/agents/lens/agent.py` (with `link_handler.py`, `news_provider.py` as siblings).
Provider: `SearchProvider` Protocol → Exa MCP (real) or `MockSearch` (dev).

## Reuse

- `exa-search`, `deep-research`, `research-ops` skills

## Output

Agent envelope. `result.markdown` is operator-readable. `result.sources` lists URLs for citations.
