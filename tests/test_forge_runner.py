"""Tests for forge_runner.WorktreeRunner — real git worktree + claude CLI dispatch.

Uses tmp_path for repo_root and monkeypatches subprocess.run to avoid
real git/claude calls.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.subsystems.forge_runner import ForgeRun, WorktreeRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_mock(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    raise_on: str | None = None,
) -> Any:
    """Return a callable that mimics subprocess.run for all git/claude calls.

    git status --porcelain always returns empty stdout (clean repo) so the
    dirty-check gate never fires unless the test explicitly wants it to.
    The provided stdout is returned only for non-git-status calls (e.g. the
    claude invocation and git rev-parse).
    """
    calls: list[list[str]] = []

    def _run(cmd, *args, **kwargs):  # noqa: ANN001
        cmd_list = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        calls.append(cmd_list)
        if raise_on and raise_on in " ".join(cmd_list):
            raise OSError(f"mocked failure: {raise_on}")
        result = MagicMock()
        result.returncode = returncode
        result.stderr = stderr
        # Return empty stdout for git status so dirty-check passes cleanly.
        if "--porcelain" in cmd_list:
            result.stdout = ""
        else:
            result.stdout = stdout
        return result

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


def _init_git_repo(path: Path) -> None:
    """Initialise a real bare-minimum git repo so git commands can run against it."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True, capture_output=True,
    )
    # Need at least one commit so HEAD exists
    readme = path / "README.md"
    readme.write_text("init")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# ForgeRun dataclass
# ---------------------------------------------------------------------------

def test_forge_run_is_frozen() -> None:
    run = ForgeRun(
        run_id="abc123",
        repo_path="/tmp/r",
        branch="forge/abc123-add-thing",
        task="add thing",
        started_iso="2026-01-01T00:00:00+00:00",
        finished_iso=None,
        status="running",
        commit_sha=None,
        diff_summary="",
        log_path="/tmp/r/log.txt",
        pushed=False,
    )
    with pytest.raises((AttributeError, TypeError)):
        run.status = "completed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# WorktreeRunner.__init__ — path resolution
# ---------------------------------------------------------------------------

def test_runner_raises_when_claude_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When claude binary is not on PATH, raise RuntimeError immediately."""
    monkeypatch.setattr("shutil.which", lambda _bin: None)
    with pytest.raises(RuntimeError, match="claude CLI not on PATH"):
        WorktreeRunner(repo_root=tmp_path, claude_bin="claude-not-a-real-bin")


def test_runner_init_ok_when_claude_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
    assert runner._claude_bin == "/usr/bin/claude"


# ---------------------------------------------------------------------------
# WorktreeRunner.execute — happy path (all subprocess mocked)
# ---------------------------------------------------------------------------

def test_execute_creates_worktree_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """execute() must issue `git worktree add -b forge/<id>-<slug>` call."""
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc1234\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="add dark mode")

    worktree_adds = [c for c in mock_run.calls if "worktree" in c and "add" in c]
    assert worktree_adds, f"no worktree add call found in: {mock_run.calls}"
    cmd = worktree_adds[0]
    branch_idx = cmd.index("-b") + 1
    assert cmd[branch_idx].startswith("forge/")
    assert run.branch.startswith("forge/")


def test_execute_invokes_claude_with_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """claude CLI must receive -p <prompt> as subprocess args."""
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="deadbeef\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        runner.execute(repo=str(tmp_path), task="implement feature Y")

    claude_calls = [c for c in mock_run.calls if "claude" in c[0] or "/usr/bin/claude" in c[0]]
    assert claude_calls, f"no claude call in {mock_run.calls}"
    flat = " ".join(claude_calls[0])
    assert "implement feature Y" in flat or "-p" in claude_calls[0]


def test_execute_returns_completed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="deadbeef\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="fix bug")

    assert run.status == "completed"
    assert run.finished_iso is not None
    assert run.log_path != ""


def test_execute_tears_down_worktree_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        runner.execute(repo=str(tmp_path), task="refactor")

    remove_calls = [c for c in mock_run.calls if "worktree" in c and "remove" in c]
    assert remove_calls, f"expected worktree remove, got: {mock_run.calls}"
    assert "--force" in remove_calls[0]


def test_execute_keeps_worktree_when_flag_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        runner.execute(repo=str(tmp_path), task="refactor", keep_worktree=True)

    remove_calls = [c for c in mock_run.calls if "worktree" in c and "remove" in c]
    assert remove_calls == [], "worktree should NOT be removed when keep_worktree=True"


def test_execute_pushes_when_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="ship", push=True)

    push_calls = [c for c in mock_run.calls if "push" in c]
    assert push_calls, f"expected git push, got: {mock_run.calls}"
    assert run.pushed is True


def test_execute_does_not_push_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="quiet")

    push_calls = [c for c in mock_run.calls if "push" in c]
    assert push_calls == []
    assert run.pushed is False


# ---------------------------------------------------------------------------
# WorktreeRunner.execute — failure path
# ---------------------------------------------------------------------------

def test_execute_returns_failed_run_on_claude_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")

    def _run(cmd, *args, **kwargs):
        result = MagicMock()
        cmd_list = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if "/usr/bin/claude" in cmd_list[0]:
            result.returncode = 1
            result.stdout = ""
            result.stderr = "claude failed"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="bad task")

    assert run.status == "failed"
    assert run.finished_iso is not None


def test_execute_rejects_dirty_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If git status shows uncommitted changes, execute() should return a failed run."""
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")

    # git status --porcelain returns non-empty output → dirty
    def _run(cmd, *args, **kwargs):
        result = MagicMock()
        cmd_list = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if "status" in cmd_list and "--porcelain" in cmd_list:
            result.returncode = 0
            result.stdout = "M dirty_file.py"
        else:
            result.returncode = 0
            result.stdout = ""
        result.stderr = ""
        return result

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="attempt")

    assert run.status == "failed"
    assert "uncommitted" in run.diff_summary.lower() or run.log_path != ""


# ---------------------------------------------------------------------------
# Persistence — list_runs / get_run
# ---------------------------------------------------------------------------

def test_list_runs_returns_recent_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        r1 = runner.execute(repo=str(tmp_path), task="task one")
        r2 = runner.execute(repo=str(tmp_path), task="task two")

    runs = runner.list_runs(limit=50)
    ids = [r.run_id for r in runs]
    assert r1.run_id in ids
    assert r2.run_id in ids


def test_list_runs_respects_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        for i in range(5):
            runner.execute(repo=str(tmp_path), task=f"task {i}")

    runs = runner.list_runs(limit=3)
    assert len(runs) <= 3


def test_get_run_returns_correct_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        original = runner.execute(repo=str(tmp_path), task="find me")

    found = runner.get_run(original.run_id)
    assert found is not None
    assert found.run_id == original.run_id
    assert found.task == "find me"


def test_get_run_returns_none_for_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
    assert runner.get_run("nonexistent-id") is None


def test_runs_persisted_to_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs must be written to state/forge_runs.jsonl as newline-delimited JSON."""
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="sha123\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
        run = runner.execute(repo=str(tmp_path), task="persist me")

    jsonl_path = tmp_path / "state" / "forge_runs.jsonl"
    assert jsonl_path.exists(), f"expected {jsonl_path}"
    lines = [ln for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record["run_id"] == run.run_id
    assert record["task"] == "persist me"


# ---------------------------------------------------------------------------
# kill()
# ---------------------------------------------------------------------------

def test_kill_returns_false_for_nonrunning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    runner = WorktreeRunner(repo_root=tmp_path, claude_bin="claude")
    assert runner.kill("no-such-run") is False


# ---------------------------------------------------------------------------
# gitignore patching
# ---------------------------------------------------------------------------

def test_gitignore_updated_with_forge_worktrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _bin: "/usr/bin/claude")
    mock_run = _make_run_mock(stdout="abc\n")

    with patch("jarvis.subsystems.forge_runner.subprocess.run", side_effect=mock_run):
        WorktreeRunner(repo_root=tmp_path, claude_bin="claude")

    gitignore = tmp_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        assert ".forge-worktrees/" in content
