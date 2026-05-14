"""Skill library — named, reusable workflow templates.

Each skill is a markdown file in this directory with a YAML frontmatter
header (between ``---`` fences) followed by the prompt body. The
operator invokes a skill via a slash command (e.g. ``/code-review``);
``jarvis.agent.JarvisChat.stream`` parses the slash, looks up the slug
here, and dispatches via ``_stream_via_skill``.

Frontmatter shape:

    ---
    slug: code-review
    title: Code Review
    description: Walk a diff and surface concrete issues
    agents: [forge]
    model: claude-sonnet-4-6
    ---
    <prompt body>

The loader caches results in-memory and only reloads when any markdown
file's mtime changes, so subsequent ``get_skill`` calls are O(1).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parent
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, "Skill"] | None = None
_CACHE_FINGERPRINT: tuple[tuple[str, float], ...] | None = None


@dataclass(frozen=True)
class Skill:
    """A single named workflow template."""

    slug: str
    title: str
    description: str
    prompt: str
    agents: list[str]
    model: str


# ---------- frontmatter parsing ----------


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Return ``(meta, body)`` for a markdown file with YAML frontmatter.

    Minimal hand-rolled parser — supports ``key: value`` lines plus
    inline JSON-style lists ``[a, b, c]``. Avoids a hard PyYAML dep.
    Empty meta + full body on missing/invalid frontmatter.
    """
    text = raw.lstrip()
    if not text.startswith("---"):
        return {}, raw
    after = text[3:].lstrip("\r\n")
    end = after.find("\n---")
    if end == -1:
        return {}, raw
    header = after[:end]
    body_start = end + len("\n---")
    body = after[body_start:].lstrip("\r\n")

    meta: dict[str, Any] = {}
    for line in header.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = [
                _strip_quotes(p.strip())
                for p in inner.split(",")
                if p.strip()
            ]
            meta[key] = items
        else:
            meta[key] = _strip_quotes(value)
    return meta, body


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# ---------- loader ----------


def _fingerprint() -> tuple[tuple[str, float], ...]:
    """Snapshot ``(name, mtime)`` for every skill markdown file."""
    out: list[tuple[str, float]] = []
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        try:
            out.append((path.name, path.stat().st_mtime))
        except OSError:
            continue
    return tuple(out)


def _build_skill(path: Path) -> Skill | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill read failed for %s: %s", path.name, exc)
        return None
    meta, body = _parse_frontmatter(raw)
    slug = str(meta.get("slug") or "").strip()
    if not slug:
        # Fall back to filename stem with underscores → hyphens.
        slug = path.stem.replace("_", "-")
    title = str(meta.get("title") or slug).strip()
    description = str(meta.get("description") or "").strip()
    agents_raw = meta.get("agents") or []
    if isinstance(agents_raw, str):
        agents = [a.strip() for a in agents_raw.split(",") if a.strip()]
    else:
        agents = [str(a).strip() for a in agents_raw if str(a).strip()]
    model = str(meta.get("model") or "claude-sonnet-4-6").strip()
    return Skill(
        slug=slug,
        title=title,
        description=description,
        prompt=body.strip(),
        agents=agents,
        model=model,
    )


def load_skills() -> dict[str, Skill]:
    """Load all skill markdown files. Cached by mtime fingerprint."""
    global _CACHE, _CACHE_FINGERPRINT
    fp = _fingerprint()
    with _CACHE_LOCK:
        if _CACHE is not None and _CACHE_FINGERPRINT == fp:
            return _CACHE
        skills: dict[str, Skill] = {}
        for path in sorted(_SKILLS_DIR.glob("*.md")):
            skill = _build_skill(path)
            if skill is None:
                continue
            skills[skill.slug] = skill
        _CACHE = skills
        _CACHE_FINGERPRINT = fp
        return skills


def get_skill(slug: str) -> Skill | None:
    """Look up a skill by slug. Returns ``None`` if unknown."""
    if not slug:
        return None
    return load_skills().get(slug.strip())


def list_skills() -> list[Skill]:
    """Return all skills sorted by slug."""
    return sorted(load_skills().values(), key=lambda s: s.slug)


__all__ = ["Skill", "load_skills", "get_skill", "list_skills"]
