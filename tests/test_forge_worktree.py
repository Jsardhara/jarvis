"""Worktree runner tests — Forge sub-agent isolation via git worktree.

Plan F1: WorktreeRunner spawns sub-agent in an isolated `git worktree`,
optionally pushes branch and opens a PR. Push is gated by the orchestrator's
tier-4 confirmation flow — runner only executes push after `confirmed=True`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.subsystems.forge import Forge, WorktreeRunner


@pytest.fixture
def fake_subagent():
    """Fake sub-agent callable: returns dict {output, files_changed}."""
    return MagicMock(return_value={
        "output": "implemented feature X",
        "files_changed": ["src/foo.py", "tests/test_foo.py"],
    })


@pytest.fixture
def fake_pr_creator():
    """Fake GitHub PR-creator MCP-shaped callable."""
    return MagicMock(return_value={"html_url": "https://github.com/o/r/pull/42"})


def _fake_run_factory():
    """Track every subprocess.run call. All git ops succeed by default."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    fake_run.calls = calls  # type: ignore[attr-defined]
    return fake_run


# ---- WorktreeRunner unit tests ----


def test_worktree_runner_creates_isolated_branch(fake_subagent):
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=MagicMock(),
        )
        out = runner.run("planner", "do the thing")

    # First git call should be `git worktree add ... -b forge/<short>`
    worktree_add_calls = [c for c in fake_run.calls if "worktree" in c and "add" in c]
    assert worktree_add_calls, f"expected git worktree add call, got: {fake_run.calls}"
    cmd = worktree_add_calls[0]
    assert "-b" in cmd
    branch_idx = cmd.index("-b") + 1
    assert cmd[branch_idx].startswith("forge/")
    assert out["branch"].startswith("forge/")
    assert "worktree_path" in out


def test_worktree_runner_runs_subagent_in_worktree(fake_subagent):
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=MagicMock(),
        )
        out = runner.run("implement", "ship feature X")

    fake_subagent.assert_called_once()
    kwargs = fake_subagent.call_args.kwargs
    # Sub-agent must receive the worktree cwd + the prompt
    assert kwargs["agent"] == "implement"
    assert kwargs["prompt"] == "ship feature X"
    assert kwargs["cwd"] == out["worktree_path"]
    assert out["output"] == "implemented feature X"
    assert out["files_changed"] == ["src/foo.py", "tests/test_foo.py"]


def test_worktree_runner_does_not_push_without_confirmation(fake_subagent, fake_pr_creator):
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=fake_pr_creator,
        )
        # push=True but confirmed=False — runner must NOT push
        out = runner.run("implement", "ship", push=True, confirmed=False)

    push_calls = [c for c in fake_run.calls if "push" in c]
    assert push_calls == [], f"unexpected git push: {push_calls}"
    fake_pr_creator.assert_not_called()
    assert out["pushed"] is False
    assert out["pr_url"] is None
    assert out.get("needs_confirm") is True


def test_worktree_runner_pushes_after_confirmed(fake_subagent, fake_pr_creator):
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=fake_pr_creator,
        )
        out = runner.run("implement", "ship", push=True, confirmed=True)

    push_calls = [c for c in fake_run.calls if "push" in c]
    assert push_calls, "expected git push call"
    cmd = push_calls[0]
    assert "-u" in cmd
    assert "origin" in cmd
    assert any(part.startswith("forge/") for part in cmd)
    assert out["pushed"] is True


def test_worktree_runner_creates_pr_when_pushed(fake_subagent, fake_pr_creator):
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=fake_pr_creator,
        )
        out = runner.run("implement", "ship feature X", push=True, confirmed=True)

    fake_pr_creator.assert_called_once()
    kwargs = fake_pr_creator.call_args.kwargs
    assert kwargs["head"].startswith("forge/")
    assert "title" in kwargs
    assert "body" in kwargs
    assert out["pr_url"] == "https://github.com/o/r/pull/42"


def test_worktree_runner_cleans_up_on_failure(fake_subagent):
    """If sub-agent raises, worktree must be removed and error returned."""
    fake_run = _fake_run_factory()
    fake_subagent.side_effect = RuntimeError("model crashed")

    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=MagicMock(),
        )
        out = runner.run("implement", "ship")

    remove_calls = [c for c in fake_run.calls if "worktree" in c and "remove" in c]
    assert remove_calls, f"expected `git worktree remove`, got: {fake_run.calls}"
    assert "--force" in remove_calls[0]
    assert "error" in out
    assert "model crashed" in out["error"]


def test_worktree_runner_swallows_cleanup_failure(fake_subagent):
    """If cleanup itself raises, runner must still return the original error."""
    fake_subagent.side_effect = RuntimeError("subagent failed")

    call_count = {"n": 0}

    def fake_run(cmd, *args, **kwargs):
        call_count["n"] += 1
        # First call: `worktree add` — succeed.
        # Cleanup call (`worktree remove`): raise to exercise the swallow branch.
        if "remove" in cmd:
            raise OSError("cleanup blew up")
        result = MagicMock()
        result.returncode = 0
        return result

    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=MagicMock(),
        )
        out = runner.run("implement", "ship")

    assert "error" in out
    assert "subagent failed" in out["error"]


# ---- Forge integration tests ----


def test_forge_uses_worktree_runner_when_constructed_with_one(fake_subagent, fake_pr_creator):
    """Forge.execute should delegate to WorktreeRunner.run for each stage."""
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=fake_pr_creator,
        )
        forge = Forge(runner)
        resp = forge.execute(repo="o/r", task="add feature X", push=False)

    assert resp.agent == "forge"
    assert resp.action == "proposed"
    assert resp.needs_confirm is True
    # Each stage triggered a sub-agent invocation
    assert fake_subagent.call_count >= 1


def test_forge_push_pending_action_when_push_requested(fake_subagent, fake_pr_creator):
    """push=True must surface `push_pending` + needs_confirm — actual push happens after confirm."""
    fake_run = _fake_run_factory()
    with patch("jarvis.subsystems.forge.subprocess.run", side_effect=fake_run):
        runner = WorktreeRunner(
            repo_path="C:/repos/x",
            subagent=fake_subagent,
            pr_creator=fake_pr_creator,
        )
        forge = Forge(runner)
        resp = forge.execute(repo="o/r", task="t", push=True)

    assert resp.needs_confirm is True
    assert resp.action == "push_pending"
    # No real `git push` should have fired before confirmation
    push_calls = [c for c in fake_run.calls if "push" in c]
    assert push_calls == []
