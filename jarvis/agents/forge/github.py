"""GitHub helper for the daily Forge mono-repo.

Owns the local clone of ``<user>/forge-projects`` and provides commit/push.
Uses ``gh`` CLI (assumed authed by operator). Detects username at runtime
via ``gh api user``.

Layout:
    state/forge-projects-clone/
        INDEX.md                       — top-level table of all daily projects
        2026-05-04-border-aid-tracker/
            README.md
            ... project files ...
        2026-05-05-...
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jarvis.config import get_settings

log = logging.getLogger(__name__)

REPO_NAME = "forge-projects"


@dataclass(frozen=True)
class GitHubContext:
    user: str
    repo: str  # "<user>/<name>"
    clone_dir: Path

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo}"


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    log.debug("run: %s (cwd=%s)", " ".join(cmd), cwd)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _gh_username() -> str:
    res = _run(["gh", "api", "user", "--jq", ".login"])
    user = res.stdout.strip()
    if not user:
        raise RuntimeError("gh api user returned empty login — is gh authed?")
    return user


def _clone_dir() -> Path:
    return get_settings().state_dir / "forge-projects-clone"


def ensure_mono_repo_clone() -> GitHubContext:
    """Idempotently ensure the mono-repo exists on GitHub and is cloned locally.

    Strategy:
      1. Detect username via gh api user.
      2. If clone dir exists with .git → return context.
      3. If repo exists on GitHub → clone it.
      4. Else → gh repo create --public --add-readme --clone.
    """
    user = _gh_username()
    repo = f"{user}/{REPO_NAME}"
    clone_dir = _clone_dir()

    if (clone_dir / ".git").exists():
        return GitHubContext(user=user, repo=repo, clone_dir=clone_dir)

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    if clone_dir.exists():  # incomplete previous attempt
        shutil.rmtree(clone_dir)

    # Probe whether the repo already exists on GitHub
    probe = _run(["gh", "repo", "view", repo, "--json", "name"], check=False)
    if probe.returncode == 0:
        log.info("forge_github: cloning existing %s", repo)
        _run(["gh", "repo", "clone", repo, str(clone_dir)])
    else:
        log.info("forge_github: creating %s", repo)
        _run(
            [
                "gh",
                "repo",
                "create",
                repo,
                "--public",
                "--add-readme",
                "--description",
                "Daily autonomous Forge projects, one per day, generated from world news.",
                "--clone",
            ],
            cwd=clone_dir.parent,
        )
        # `gh repo create --clone` creates folder named REPO_NAME by default
        default_clone = clone_dir.parent / REPO_NAME
        if default_clone.exists() and default_clone != clone_dir:
            default_clone.rename(clone_dir)

    if not (clone_dir / ".git").exists():
        raise RuntimeError(f"forge_github: clone failed at {clone_dir}")

    return GitHubContext(user=user, repo=repo, clone_dir=clone_dir)


def push_daily(ctx: GitHubContext, folder: str, commit_msg: str) -> str:
    """Add+commit+push the daily project folder. Returns commit SHA."""
    # Pull latest first to avoid push rejections
    _run(["git", "pull", "--rebase", "--autostash"], cwd=ctx.clone_dir, check=False)
    _run(["git", "add", folder, "INDEX.md"], cwd=ctx.clone_dir, check=False)
    # Use --allow-empty=false; if nothing changed, skip
    status = _run(["git", "status", "--porcelain"], cwd=ctx.clone_dir)
    if not status.stdout.strip():
        log.warning("forge_github: nothing to commit for %s", folder)
        return ""
    _run(["git", "commit", "-m", commit_msg], cwd=ctx.clone_dir)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=ctx.clone_dir).stdout.strip()
    _run(["git", "push", "origin", "main"], cwd=ctx.clone_dir)
    return sha


def update_index(ctx: GitHubContext, entry_md: str) -> None:
    """Append a row to INDEX.md (creates header if missing)."""
    index_path = ctx.clone_dir / "INDEX.md"
    header = (
        "# Forge — Daily Projects\n\n"
        "One project per day, autonomously generated from world news.\n\n"
        "| Date | Project | Source | Folder |\n"
        "|------|---------|--------|--------|\n"
    )
    if not index_path.exists():
        index_path.write_text(header + entry_md.strip() + "\n", encoding="utf-8")
        return
    existing = index_path.read_text(encoding="utf-8")
    if "| Date | Project |" not in existing:
        existing = header + existing
    index_path.write_text(existing.rstrip() + "\n" + entry_md.strip() + "\n", encoding="utf-8")
