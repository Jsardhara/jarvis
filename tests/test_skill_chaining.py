"""Tests for W3.2 — cross-skill orchestration.

Covers the ``chains_to`` frontmatter field and the
``render_chain_suggestion`` helper that produces the "try /next-slug"
footer the chat layer appends after a skill reply.
"""
from __future__ import annotations

from jarvis.skills import (
    Skill,
    get_skill,
    load_skills,
    render_chain_suggestion,
)


def test_chains_to_parsed_from_frontmatter() -> None:
    """trip-plan declares chains_to: [weekend-plan]; it should round-trip."""
    skill = get_skill("trip-plan")
    assert skill is not None
    assert "weekend-plan" in skill.chains_to


def test_chains_to_defaults_to_empty_list() -> None:
    """Skills without a chains_to frontmatter line keep an empty list."""
    code_review = get_skill("code-review")
    assert code_review is not None
    assert code_review.chains_to == []


def test_render_chain_suggestion_empty_when_no_chain() -> None:
    skill = Skill(
        slug="standalone",
        title="Standalone",
        description="No chain",
        prompt="...",
        agents=[],
        model="claude-sonnet-4-6",
    )
    # Even though `standalone` isn't in the catalog, the no-chain
    # short-circuit fires before any catalog lookup.
    assert render_chain_suggestion(skill) == ""


def test_render_chain_suggestion_single_target() -> None:
    skill = get_skill("trip-plan")
    assert skill is not None
    out = render_chain_suggestion(skill)
    assert "/weekend-plan" in out
    # Description of the chained skill is included so the operator sees
    # why it's being suggested.
    weekend = get_skill("weekend-plan")
    assert weekend is not None
    assert weekend.description in out


def test_render_chain_suggestion_drops_unknown_slugs() -> None:
    """A stale chains_to entry pointing at a non-existent skill must not
    surface a broken slash command."""
    skill = Skill(
        slug="custom",
        title="Custom",
        description="Test",
        prompt="...",
        agents=[],
        model="claude-sonnet-4-6",
        chains_to=["this-skill-does-not-exist"],
    )
    assert render_chain_suggestion(skill) == ""


def test_render_chain_suggestion_multi_target() -> None:
    """When multiple chains resolve, they render as a comma list."""
    real_slugs = list(load_skills().keys())
    assert len(real_slugs) >= 2
    skill = Skill(
        slug="custom-multi",
        title="Custom Multi",
        description="Test",
        prompt="...",
        agents=[],
        model="claude-sonnet-4-6",
        chains_to=real_slugs[:2],
    )
    out = render_chain_suggestion(skill)
    for s in real_slugs[:2]:
        assert f"/{s}" in out
