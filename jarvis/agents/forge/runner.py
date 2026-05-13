"""Real Forge runner — git worktree + claude CLI dispatch.

Each execute() call:
1. Checks for uncommitted changes in the main repo (blocks worktree add cleanly).
2. Creates a fresh git worktree at .forge-worktrees/{run_id}/.
3. Branches off the target branch (default current HEAD).
4. Invokes `claude -p <prompt>` (one-shot, non-interactive) with the task brief.
5. Captures stdout/stderr to state/forge_runs/{run_id}.log.
6. On success: returns diff summary + commit SHA, optionally pushes.
7. Tears down worktree after run UNLESS keep_worktree=True.

Runs are persisted to state/forge_runs.jsonl for list_runs().
"""
from __future__ import annotations

import contextlib
import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 600  # seconds


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slug(text: str, max_len: int = 30) -> str:
    """Convert task text to a safe branch-name fragment."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")


@dataclass(frozen=True)
class ForgeRun:
    run_id: str
    repo_path: str
    branch: str
    task: str
    started_iso: str
    finished_iso: str | None
    status: Literal["running", "completed", "failed", "killed"]
    commit_sha: str | None
    diff_summary: str
    log_path: str
    pushed: bool


class WorktreeRunner:
    """Run tasks inside isolated git worktrees using the claude CLI.

    Parameters
    ----------
    repo_root:
        Root of the git repository.  Defaults to cwd.
    claude_bin:
        Name or full path of the claude binary.  Validated against PATH on init.
    timeout:
        Subprocess timeout in seconds for the claude call (default 600).
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        claude_bin: str = "claude",
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._repo_root = Path(repo_root) if repo_root else Path.cwd()
        self._timeout = timeout

        resolved = shutil.which(claude_bin)
        if resolved is None:
            raise RuntimeError(
                f"claude CLI not on PATH; install or fall back to MockRunner "
                f"(looked for: {claude_bin!r})"
            )
        self._claude_bin = resolved

        self._worktree_base = self._repo_root / ".forge-worktrees"
        self._state_dir = self._repo_root / "state" / "forge_runs"
        self._runs_jsonl = self._repo_root / "state" / "forge_runs.jsonl"

        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignore()

        # In-memory index: run_id -> ForgeRun (populated from both execute() + load)
        self._index: dict[str, ForgeRun] = {}
        self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, agent_name: str, prompt: str) -> str:
        """Adapter for the staged ``Forge`` pipeline.

        The staged pipeline issues per-stage calls of the form
        ``runner.run(agent_name, prompt)`` and only consumes a string artifact
        of stage output, not a full :class:`ForgeRun` record. We delegate to
        :meth:`execute` (repo=cwd, task=prompt) and return its
        ``diff_summary`` so the live runner is drop-in compatible with
        :class:`MockRunner`. ``agent_name`` is currently unused at the live
        layer; stages already encode the role in the prompt.
        """
        del agent_name  # reserved for future per-stage tool selection
        forge_run = self.execute(repo=str(self._repo_root), task=prompt)
        return forge_run.diff_summary or ""

    def execute(
        self,
        repo: str,
        task: str,
        push: bool = False,
        branch: str | None = None,
        keep_worktree: bool = False,
    ) -> ForgeRun:
        """Dispatch a task via claude CLI inside a fresh git worktree."""
        run_id = uuid.uuid4().hex[:12]
        started = _now_iso()
        log_path = str(self._state_dir / f"{run_id}.log")

        # Safety: reject dirty working tree
        dirty_run = self._check_dirty(run_id, repo, task, started, log_path)
        if dirty_run is not None:
            self._persist(dirty_run)
            return dirty_run

        branch_name = branch or f"forge/{run_id}-{_slug(task)}"
        worktree_path = self._worktree_base / run_id

        # Write a placeholder running record
        running = ForgeRun(
            run_id=run_id,
            repo_path=repo,
            branch=branch_name,
            task=task,
            started_iso=started,
            finished_iso=None,
            status="running",
            commit_sha=None,
            diff_summary="",
            log_path=log_path,
            pushed=False,
        )
        self._index[run_id] = running

        try:
            self._git_worktree_add(worktree_path, branch_name)
            exit_code, log_text = self._run_claude(task, worktree_path, log_path)

            if exit_code != 0:
                final = _replace(running, status="failed", finished_iso=_now_iso())
                self._maybe_cleanup(worktree_path, keep_worktree)
                self._persist(final)
                return final

            sha = self._get_commit_sha(worktree_path)
            diff = self._get_diff_stat(worktree_path)

            pushed = False
            if push:
                pushed = self._git_push(worktree_path, branch_name)

            final = _replace(
                running,
                status="completed",
                finished_iso=_now_iso(),
                commit_sha=sha,
                diff_summary=diff,
                pushed=pushed,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("forge run %s failed: %s", run_id, exc)
            final = _replace(running, status="failed", finished_iso=_now_iso())
            self._maybe_cleanup(worktree_path, keep_worktree)
            self._persist(final)
            return final

        self._maybe_cleanup(worktree_path, keep_worktree)
        self._persist(final)
        return final

    def list_runs(self, limit: int = 50) -> list[ForgeRun]:
        """Return recent runs, most recent first."""
        runs = sorted(
            self._index.values(),
            key=lambda r: r.started_iso,
            reverse=True,
        )
        return runs[:limit]

    def get_run(self, run_id: str) -> ForgeRun | None:
        return self._index.get(run_id)

    def kill(self, run_id: str) -> bool:
        """Mark a running job as killed.  Returns False if not found or not running."""
        run = self._index.get(run_id)
        if run is None or run.status != "running":
            return False
        killed = _replace(run, status="killed", finished_iso=_now_iso())
        self._persist(killed)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_dirty(
        self, run_id: str, repo: str, task: str, started: str, log_path: str
    ) -> ForgeRun | None:
        """Return a failed ForgeRun if the repo has uncommitted changes, else None."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self._repo_root), "status", "--porcelain"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout.strip():
                return ForgeRun(
                    run_id=run_id,
                    repo_path=repo,
                    branch="",
                    task=task,
                    started_iso=started,
                    finished_iso=_now_iso(),
                    status="failed",
                    commit_sha=None,
                    diff_summary="rejected: uncommitted changes in main repo",
                    log_path=log_path,
                    pushed=False,
                )
        except Exception:  # noqa: BLE001
            pass
        return None

    def _git_worktree_add(self, worktree_path: Path, branch: str) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self._repo_root),
                "worktree",
                "add",
                str(worktree_path),
                "-b",
                branch,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _run_claude(self, task: str, worktree_path: Path, log_path: str) -> tuple[int, str]:
        """Invoke claude CLI with the task prompt; capture output to log file."""
        prompt = (
            f"You are working inside a git worktree at {worktree_path}.\n"
            f"Task: {task}\n"
            "Complete the task. Commit all changes with a descriptive message."
        )
        try:
            result = subprocess.run(
                [self._claude_bin, "-p", prompt],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            log_text = result.stdout + result.stderr
            Path(log_path).write_text(log_text, encoding="utf-8")
            return result.returncode, log_text
        except subprocess.TimeoutExpired:
            Path(log_path).write_text("timeout\n", encoding="utf-8")
            return 1, "timeout"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            Path(log_path).write_text(msg, encoding="utf-8")
            return 1, msg

    def _get_commit_sha(self, worktree_path: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:  # noqa: BLE001
            pass
        return None

    def _get_diff_stat(self, worktree_path: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    def _git_push(self, worktree_path: Path, branch: str) -> bool:
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=str(worktree_path),
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    def _maybe_cleanup(self, worktree_path: Path, keep: bool) -> None:
        if keep:
            return
        with contextlib.suppress(Exception):
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repo_root),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def _persist(self, run: ForgeRun) -> None:
        self._index[run.run_id] = run
        record = asdict(run)
        try:
            with self._runs_jsonl.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not persist forge run %s: %s", run.run_id, exc)

    def _load_index(self) -> None:
        """Populate in-memory index from existing jsonl (most recent record wins)."""
        if not self._runs_jsonl.exists():
            return
        try:
            for line in self._runs_jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    run = ForgeRun(**record)
                    self._index[run.run_id] = run
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load forge_runs.jsonl: %s", exc)

    def _ensure_gitignore(self) -> None:
        """Add .forge-worktrees/ to .gitignore if not already present."""
        gitignore = self._repo_root / ".gitignore"
        entry = ".forge-worktrees/"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if entry in content:
                return
            gitignore.write_text(content.rstrip("\n") + f"\n{entry}\n", encoding="utf-8")
        else:
            gitignore.write_text(f"{entry}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Immutable "replace" helper (frozen dataclass workaround)
# ---------------------------------------------------------------------------

def _replace(run: ForgeRun, **changes: object) -> ForgeRun:
    """Return a new ForgeRun with the given fields replaced."""
    d = asdict(run)
    d.update(changes)
    return ForgeRun(**d)
