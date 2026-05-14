"""Tests for J11 — Skill Library loader."""
from __future__ import annotations

from jarvis.skills import Skill, get_skill, list_skills, load_skills

EXPECTED_SLUGS = {
    "code-review",
    "meeting-prep",
    "exam-prep",
    "trip-plan",
    "weekend-plan",
    "paper-summarize",
    "standup-summary",
}


def test_load_skills_finds_all() -> None:
    skills = load_skills()
    missing = EXPECTED_SLUGS - set(skills.keys())
    assert not missing, f"missing skill slugs: {missing}"


def test_skill_has_required_fields() -> None:
    for skill in load_skills().values():
        assert isinstance(skill, Skill)
        assert skill.title, f"{skill.slug} missing title"
        assert skill.description, f"{skill.slug} missing description"
        assert skill.prompt, f"{skill.slug} missing prompt body"
        assert skill.model, f"{skill.slug} missing model"
        assert isinstance(skill.agents, list)


def test_get_skill_by_slug() -> None:
    skill = get_skill("code-review")
    assert skill is not None
    assert skill.slug == "code-review"
    assert skill.title == "Code Review"
    assert "forge" in skill.agents


def test_get_skill_unknown_returns_none() -> None:
    assert get_skill("blarp") is None
    assert get_skill("") is None


def test_list_skills_returns_sorted() -> None:
    skills = list_skills()
    slugs = [s.slug for s in skills]
    assert slugs == sorted(slugs)
    assert len(slugs) >= len(EXPECTED_SLUGS)
