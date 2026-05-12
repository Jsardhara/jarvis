"""Sonnet/Opus model routing for the Jarvis chatbot.

Decides per-turn whether the cheap fast model (Sonnet 4.6) or the deep
reasoning model (Opus 4.7) handles the request.

Hierarchy of signals (first match wins):
    1. Manual override   — message starts with "/opus " or "/sonnet "
    2. Tier escalation   — classify_tier → 1 or 2 (safety / time-sensitive)
    3. Heavy keywords    — code, refactor, plan, design, etc.
    4. Length            — > 280 chars or > 3 sentences
    5. Greeting / lookup — short conversational openers
    6. Default           — tier 5 ≤ 140 chars → sonnet, else opus
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.core.classify import classify_tier

DEFAULT_OPUS_ID = "claude-opus-4-7"
DEFAULT_SONNET_ID = "claude-sonnet-4-6"

_HEAVY_KEYWORDS = re.compile(
    r"\b(?:code|coding|refactor|debug|implement|design|plan|"
    r"analy[sz]e|review|synthes[ie]ze|compare|backtest|investigate|"
    r"deep\s+research|architect|orchestrate|trade\s+strateg|build\s+out|"
    r"draft\s+a\s+pr|write\s+a\s+pr|ship\s+a\s+pr)\b",
    re.IGNORECASE,
)

_GREETING = re.compile(
    r"^\s*(?:hi|hey|hello|yo|thanks|thank\s+you|ok|okay|cool|gm|gn|wassup|sup)\b",
    re.IGNORECASE,
)

_OPUS_PREFIX = re.compile(r"^\s*/opus\s+", re.IGNORECASE)
_SONNET_PREFIX = re.compile(r"^\s*/sonnet\s+", re.IGNORECASE)
_SHORT_LOOKUP_LIMIT = 80
_LENGTH_BUMP = 280
_TIER5_SHORT_LIMIT = 140


@dataclass(frozen=True)
class RouteDecision:
    model: str
    reason: str
    tier: int
    length_chars: int
    manual: bool

    @property
    def is_opus(self) -> bool:
        return "opus" in self.model

    @property
    def is_sonnet(self) -> bool:
        return "sonnet" in self.model


def decide_model(
    message: str,
    *,
    opus_id: str = DEFAULT_OPUS_ID,
    sonnet_id: str = DEFAULT_SONNET_ID,
) -> tuple[RouteDecision, str]:
    """Pick a model for the user's message.

    Returns ``(decision, cleaned_message)``. ``cleaned_message`` has any
    `/opus ` / `/sonnet ` prefix stripped so the downstream model sees only
    the user's intent.
    """
    raw = message or ""

    # 1. Manual override
    m = _OPUS_PREFIX.match(raw)
    if m:
        cleaned = raw[m.end():].strip()
        return (
            RouteDecision(
                model=opus_id,
                reason="manual override (/opus)",
                tier=0,
                length_chars=len(cleaned),
                manual=True,
            ),
            cleaned,
        )
    m = _SONNET_PREFIX.match(raw)
    if m:
        cleaned = raw[m.end():].strip()
        return (
            RouteDecision(
                model=sonnet_id,
                reason="manual override (/sonnet)",
                tier=0,
                length_chars=len(cleaned),
                manual=True,
            ),
            cleaned,
        )

    cleaned = raw.strip()
    length = len(cleaned)

    if not cleaned:
        return (
            RouteDecision(
                model=sonnet_id, reason="empty input → sonnet default",
                tier=5, length_chars=0, manual=False,
            ),
            cleaned,
        )

    tier_classification = classify_tier(cleaned)
    tier = tier_classification.tier

    # 2. Tier escalation
    if tier in (1, 2):
        return (
            RouteDecision(
                model=opus_id,
                reason=f"tier {tier} (safety/time-sensitive)",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )

    # 3. Heavy keywords
    if _HEAVY_KEYWORDS.search(cleaned):
        return (
            RouteDecision(
                model=opus_id,
                reason="heavy-task keyword",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )

    # 4. Length
    sentence_count = _count_sentences(cleaned)
    if length > _LENGTH_BUMP or sentence_count > 3:
        return (
            RouteDecision(
                model=opus_id,
                reason=f"long message ({length} chars / {sentence_count} sentences)",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )

    # 5. Greeting / short lookup → sonnet
    if _GREETING.match(cleaned):
        return (
            RouteDecision(
                model=sonnet_id,
                reason="greeting / chitchat",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )
    if length <= _SHORT_LOOKUP_LIMIT and cleaned.rstrip().endswith("?"):
        return (
            RouteDecision(
                model=sonnet_id,
                reason="short lookup question",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )

    # 6. Default
    if tier == 5 and length <= _TIER5_SHORT_LIMIT:
        return (
            RouteDecision(
                model=sonnet_id,
                reason=f"tier 5 routine ({length} chars)",
                tier=tier,
                length_chars=length,
                manual=False,
            ),
            cleaned,
        )

    return (
        RouteDecision(
            model=opus_id,
            reason=f"default escalation (tier {tier}, {length} chars)",
            tier=tier,
            length_chars=length,
            manual=False,
        ),
        cleaned,
    )


def _count_sentences(text: str) -> int:
    return max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
