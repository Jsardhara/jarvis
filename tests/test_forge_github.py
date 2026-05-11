"""Tests for forge_github — gh CLI clone/create + push/index helpers."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jarvis.subsystems import forge_github
from jarvis.subsystems.forge_github import (
    GitHubContext,
    REPO_NAME,
    ensure_mono_repo_clone,
    push_daily,
    update_index,
)


# ---------------------------------------------------------------------------
# subprocess.run mock helper
# ---------------------------------------------------------------------------

def _make_run(responses: dict[str, dict]):
    """Return a fake subprocess.run that matches command tail to responses.

    Keys are space-joined command tails (e.g. "gh api user"); values are dicts
    with returncode/stdout/stderr.
    """
    calls: list[list[str]] = []

    def _run(cmd, *args, cwd=None, capture_output=True, text=True, check=False, **kwargs):
        cmd_list = list(cmd)
        calls.append(cmd_list)
        joined = " ".join(cmd_list)
        for key, resp in responses.items():
            if key in joined:
                rc = resp.get("returncode", 0)
                out = resp.get("stdout", "")
                err = resp.get("stderr", "")
                if check and rc != 0:
                    raise subprocess.CalledProcessError(rc, cmd_list, out, err)
                return subprocess.CompletedProcess(cmd_list, rc, out, err)
        # Default: success, empty
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


# ---------------------------------------------------------------------------
# GitHubContext
# ---------------------------------------------------------------------------

def test_github_context_repo_url():
    ctx = GitHubContext(user="alice", repo="alice/forge-projects", clone_dir=Path("/tmp/x"))
    assert ctx.repo_url == "https://github.com/alice/forge-projects"


# ---------------------------------------------------------------------------
# ensure_mono_repo_clone
# ---------------------------------------------------------------------------

def test_ensure_returns_existing_clone(tmp_path, monkeypatch):
    """If clone_dir/.git exists, skip gh entirely."""
    clone = tmp_path / "forge-projects-clone"
    (clone / ".git").mkdir(parents=True)

    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)
    fake_run = _make_run({"gh api user": {"stdout": "alice"}})
    monkeypatch.setattr(subprocess, "run", fake_run)

    ctx = ensure_mono_repo_clone()
    assert ctx.user == "alice"
    assert ctx.repo == f"alice/{REPO_NAME}"
    assert ctx.clone_dir == clone
    # only username probe should have run; no clone/create
    cmds = [" ".join(c) for c in fake_run.calls]
    assert any("gh api user" in c for c in cmds)
    assert not any("gh repo clone" in c for c in cmds)
    assert not any("gh repo create" in c for c in cmds)


def test_ensure_clones_existing_remote(tmp_path, monkeypatch):
    """Repo exists on GitHub but not locally → gh repo clone."""
    clone = tmp_path / "forge-projects-clone"
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "gh api user" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "alice\n", "")
        if "gh repo view" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, '{"name":"forge-projects"}', "")
        if "gh repo clone" in joined:
            (clone / ".git").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd_list, 0, "", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ctx = ensure_mono_repo_clone()
    assert ctx.user == "alice"
    assert (clone / ".git").exists()


def test_ensure_creates_repo_when_missing(tmp_path, monkeypatch):
    """Repo missing on GitHub → gh repo create --clone."""
    clone = tmp_path / "forge-projects-clone"
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)
    created: list[str] = []

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "gh api user" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "bob\n", "")
        if "gh repo view" in joined:
            # not found
            return subprocess.CompletedProcess(cmd_list, 1, "", "not found")
        if "gh repo create" in joined:
            (clone / ".git").mkdir(parents=True)
            created.append(joined)
            return subprocess.CompletedProcess(cmd_list, 0, "", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ctx = ensure_mono_repo_clone()
    assert ctx.user == "bob"
    assert created, "gh repo create should have been called"
    assert "--public" in created[0]


def test_ensure_renames_default_clone_dir(tmp_path, monkeypatch):
    """gh repo create --clone names dir REPO_NAME — code renames to clone_dir."""
    clone = tmp_path / "forge-projects-clone"
    default = tmp_path / REPO_NAME
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "gh api user" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "carol", "")
        if "gh repo view" in joined:
            return subprocess.CompletedProcess(cmd_list, 1, "", "")
        if "gh repo create" in joined:
            (default / ".git").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd_list, 0, "", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ctx = ensure_mono_repo_clone()
    assert (clone / ".git").exists()
    assert not default.exists()


def test_ensure_clears_incomplete_clone(tmp_path, monkeypatch):
    """clone_dir exists but no .git → wipe + reclone."""
    clone = tmp_path / "forge-projects-clone"
    clone.mkdir()
    (clone / "stale.txt").write_text("junk")
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "gh api user" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "dan", "")
        if "gh repo view" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, '{"name":"x"}', "")
        if "gh repo clone" in joined:
            (clone / ".git").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd_list, 0, "", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ensure_mono_repo_clone()
    assert not (clone / "stale.txt").exists()


def test_ensure_raises_when_username_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: tmp_path / "x")
    fake_run = _make_run({"gh api user": {"stdout": "  \n"}})
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="empty login"):
        ensure_mono_repo_clone()


def test_ensure_raises_if_clone_did_not_create_git(tmp_path, monkeypatch):
    clone = tmp_path / "forge-projects-clone"
    monkeypatch.setattr(forge_github, "_clone_dir", lambda: clone)

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "gh api user" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "x", "")
        if "gh repo view" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "{}", "")
        # gh repo clone returns success but no .git appears
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="clone failed"):
        ensure_mono_repo_clone()


# ---------------------------------------------------------------------------
# push_daily
# ---------------------------------------------------------------------------

def _ctx(tmp_path: Path) -> GitHubContext:
    clone = tmp_path / "clone"
    clone.mkdir()
    return GitHubContext(user="alice", repo="alice/forge-projects", clone_dir=clone)


def test_push_daily_returns_empty_when_clean(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        if "git status --porcelain" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sha = push_daily(ctx, "2026-05-11-foo", "msg")
    assert sha == ""


def test_push_daily_commits_and_pushes_when_dirty(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    pushed: list[str] = []

    def fake_run(cmd, *a, cwd=None, capture_output=True, text=True, check=False, **kw):
        cmd_list = list(cmd)
        joined = " ".join(cmd_list)
        pushed.append(joined)
        if "git status --porcelain" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, " M foo\n", "")
        if "git rev-parse HEAD" in joined:
            return subprocess.CompletedProcess(cmd_list, 0, "abc1234\n", "")
        return subprocess.CompletedProcess(cmd_list, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sha = push_daily(ctx, "2026-05-11-foo", "msg")
    assert sha == "abc1234"
    assert any("git commit -m msg" in c for c in pushed)
    assert any("git push origin main" in c for c in pushed)


# ---------------------------------------------------------------------------
# update_index
# ---------------------------------------------------------------------------

def test_update_index_creates_with_header(tmp_path):
    ctx = _ctx(tmp_path)
    update_index(ctx, "| 2026-05-11 | Foo | src | folder |")
    contents = (ctx.clone_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "Forge" in contents and "Daily Projects" in contents
    assert "| Date | Project |" in contents
    assert "| 2026-05-11 | Foo |" in contents


def test_update_index_appends_to_existing(tmp_path):
    ctx = _ctx(tmp_path)
    idx = ctx.clone_dir / "INDEX.md"
    idx.write_text(
        "# Forge\n\n| Date | Project | Source | Folder |\n"
        "|------|---------|--------|--------|\n| 2026-05-10 | A | s | f |\n",
        encoding="utf-8",
    )
    update_index(ctx, "| 2026-05-11 | B | s | f |")
    contents = idx.read_text(encoding="utf-8")
    assert "| 2026-05-10 | A |" in contents
    assert "| 2026-05-11 | B |" in contents


def test_update_index_prepends_header_to_legacy_file(tmp_path):
    """Existing INDEX.md without table header gets header prepended."""
    ctx = _ctx(tmp_path)
    idx = ctx.clone_dir / "INDEX.md"
    idx.write_text("legacy notes\n", encoding="utf-8")
    update_index(ctx, "| 2026-05-11 | B | s | f |")
    contents = idx.read_text(encoding="utf-8")
    assert "| Date | Project |" in contents
    assert "legacy notes" in contents
