"""Forge code-delegation workflow tests."""
from __future__ import annotations

from jarvis.agents.forge.agent import STAGES, Forge, MockRunner


def test_execute_runs_all_stages_except_pr_when_no_push():
    runner = MockRunner()
    f = Forge(runner)
    resp = f.execute(repo="owner/repo", task="add feature X", push=False)
    assert resp.action == "proposed"
    assert resp.needs_confirm is True
    assert "open_pr" not in resp.result["stages"]
    # plan, tdd, implement, review, security
    assert len(resp.result["stages"]) == 5


def test_execute_with_push_runs_open_pr():
    runner = MockRunner()
    f = Forge(runner)
    resp = f.execute(repo="o/r", task="t", push=True)
    assert resp.action == "completed"
    assert resp.needs_confirm is False
    assert "open_pr" in resp.result["stages"]


def test_runner_receives_per_stage_prompts():
    runner = MockRunner()
    f = Forge(runner)
    f.execute(repo="o/r", task="add darkmode", push=False)
    agents_called = [c[0] for c in runner.calls]
    assert "planner" in agents_called
    assert "code-reviewer" in agents_called
    assert "security-reviewer" in agents_called


def test_constraints_appear_in_prompts():
    runner = MockRunner()
    f = Forge(runner)
    f.execute(repo="o/r", task="t", constraints=["no breaking changes"], push=False)
    plan_prompt = runner.calls[0][1]
    assert "no breaking changes" in plan_prompt


def test_subset_of_stages_runs():
    runner = MockRunner()
    f = Forge(runner)
    resp = f.execute(repo="o/r", task="t", stages=("plan", "review"), push=False)
    assert resp.result["stages"] == ["plan", "review"]


def test_stages_constant_is_full_chain():
    assert STAGES == ("plan", "tdd", "implement", "review", "security", "open_pr")
