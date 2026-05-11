"""Speech-cleaning + last-mile Haiku rewrite.

Every spoken line passes through ``clean_for_speech`` before TTS.
If the cleaned text still looks structural (long, list-like, JSON-ish),
``rewrite_for_speech`` makes one Haiku call to rephrase in spoken cadence.

Pure-string cleaner is idempotent. Rewrite is best-effort — on LLM
failure it returns the cleaned input so the voice loop never crashes.
"""
from __future__ import annotations

import logging
import re

from .persona import PERSONA

logger = logging.getLogger(__name__)

REWRITE_MODEL = "claude-haiku-4-5"

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_JSON_BLOB_RE = re.compile(r"\{[^{}]*\}")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_STAR_RE = re.compile(r"(?<!\w)\*([^*]+)\*(?!\w)")
_ITALIC_UND_RE = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def _submit(*, system: str, user: str, model: str) -> str:
    """Indirection point so tests can patch the LLM call."""
    from ..claude_queue import submit

    reply = submit(system=system, user=user, model=model)
    if isinstance(reply, dict):
        reply = reply.get("text", "")
    return (reply or "").strip()


def clean_for_speech(text: str | None) -> str:
    """Strip markdown, code fences, JSON blobs, bullet markers.

    Idempotent — running twice yields the same result.
    """
    if not text:
        return ""

    out = text

    # Drop fenced code blocks first (they may contain other markdown).
    out = _CODE_FENCE_RE.sub(" ", out)

    # Drop JSON-ish blobs (single-level braces).
    while _JSON_BLOB_RE.search(out):
        new = _JSON_BLOB_RE.sub(" ", out)
        if new == out:
            break
        out = new

    # Unwrap bold/italic, keep the inner text.
    out = _BOLD_RE.sub(r"\1", out)
    out = _ITALIC_STAR_RE.sub(r"\1", out)
    out = _ITALIC_UND_RE.sub(r"\1", out)

    # Inline code → plain.
    out = _INLINE_CODE_RE.sub(r"\1", out)

    # Drop heading markers + bullet markers + numbered list markers.
    out = _HEADING_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = _NUMBERED_LIST_RE.sub("", out)

    # Strip any leftover hash / underscore / backtick / asterisk fragments.
    out = out.replace("`", "").replace("#", "")
    # Stray asterisks/underscores from unmatched markdown.
    out = re.sub(r"(?<!\w)[*_](?!\w)", "", out)

    # Collapse whitespace.
    out = _MULTI_NEWLINE_RE.sub(". ", out)
    out = out.replace("\n", " ")
    out = _MULTI_SPACE_RE.sub(" ", out)

    return out.strip()


_REWRITE_SYSTEM = (
    PERSONA
    + "\n\nThe operator just got a response. Rewrite it for spoken delivery.\n"
    "One or two sentences max. ~25 words. Conversational. No markdown.\n"
    "Numbers spoken as numbers. Keep the meaning, lose the structure."
)


def rewrite_for_speech(text: str) -> str:
    """Haiku rewrite for talk-pass. Falls back to input on failure."""
    if not text:
        return ""
    try:
        out = _submit(system=_REWRITE_SYSTEM, user=text, model=REWRITE_MODEL)
    except Exception as exc:  # noqa: BLE001 — voice never crashes on LLM fail
        logger.warning("[voice.speech] rewrite failed: %s", exc)
        return text
    return out or text
