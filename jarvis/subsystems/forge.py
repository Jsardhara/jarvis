"""Forge — code-work delegation.

Forge orchestrates a planner→tdd→implement→review chain on a target repo.
The actual Agent-tool spawning happens inside the CC agent prompt at
.claude/agents/forge.md. This module exposes the workflow state machine
and a dry-run/plan mode that can be exercised by the daemon and tests.

Plan F1 adds `WorktreeRunner` — spawns each sub-agent inside an isolated
`git worktree` on a fresh `forge/<short_uuid>` branch. Push + PR creation
are gated by the orchestrator's tier-4 confirmation flow: the runner only
executes `git push` and opens a PR when called with `confirmed=True`.
"""
from __future__ import annotations

import subprocess
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..contract import AgentResponse


class CodeAgentRunner(Protocol):
    """Interface for whatever actually runs sub-agents. CC's Agent tool in prod, mock in tests."""

    def run(self, agent: str, prompt: str) -> dict: ...


@dataclass
class ForgeJob:
    repo: str
    task: str
    constraints: list[str] = field(default_factory=list)
    stages_completed: list[str] = field(default_factory=list)
    artifacts: dict[str, dict] = field(default_factory=dict)


STAGES = ("plan", "tdd", "implement", "review", "security", "open_pr")


class MockRunner:
    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    def run(self, agent: str, prompt: str) -> dict:
        self.calls.append((agent, prompt))
        return self._responses.get(
            agent, {"agent": agent, "status": "ok", "summary": f"mock {agent}"}
        )


SubagentCallable = Callable[..., dict[str, Any]]
PRCreator = Callable[..., dict[str, Any]]


def _short_uuid() -> str:
    return uuid.uuid4().hex[:8]


class WorktreeRunner:
    """Run a sub-agent inside an isolated `git worktree`.

    Lifecycle:
      1. `git worktree add <tmp> -b forge/<short>` from `repo_path`.
      2. Invoke `subagent(agent=..., prompt=..., cwd=<tmp>)`.
      3. If `push=True` AND `confirmed=True`: `git push -u origin <branch>` + open PR.
      4. On any failure: `git worktree remove --force <tmp>` and surface error.

    Confirmation gate: callers pass `push=True, confirmed=False` for the first
    pass; orchestrator surfaces `needs_confirm=True` to the operator. After the
    operator approves via `POST /api/confirmations/{id}/approve`, callers
    re-invoke with `confirmed=True` and the runner finalizes push + PR.
    """

    def __init__(
        self,
        repo_path: str,
        subagent: SubagentCallable,
        pr_creator: PRCreator,
        remote: str = "origin",
        base_branch: str = "main",
    ) -> None:
        self.repo_path = repo_path
        self.subagent = subagent
        self.pr_creator = pr_creator
        self.remote = remote
        self.base_branch = base_branch

    def run(
        self,
        agent: str,
        prompt: str,
        *,
        push: bool = False,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        branch = f"forge/{_short_uuid()}"
        tmp = tempfile.mkdtemp(prefix="forge-worktree-")
        worktree_path = str(Path(tmp))

        try:
            subprocess.run(
                ["git", "-C", self.repo_path, "worktree", "add", worktree_path, "-b", branch],
                check=True,
                capture_output=True,
                text=True,
            )

            sub_result = self.subagent(agent=agent, prompt=prompt, cwd=worktree_path)
            output = sub_result.get("output", "")
            files_changed = list(sub_result.get("files_changed", []))

            pushed = False
            pr_url: str | None = None
            needs_confirm = False

            if push and not confirmed:
                # Gate: defer push + PR until operator confirms
                needs_confirm = True
            elif push and confirmed:
                subprocess.run(
                    ["git", "-C", worktree_path, "push", "-u", self.remote, branch],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                pushed = True
                pr = self.pr_creator(
                    head=branch,
                    base=self.base_branch,
                    title=f"forge: {prompt[:60]}",
                    body=f"Automated PR from forge agent `{agent}`.\n\n{output}",
                )
                pr_url = pr.get("html_url") or pr.get("url")

            return {
                "agent": agent,
                "branch": branch,
                "worktree_path": worktree_path,
                "output": output,
                "files_changed": files_changed,
                "pushed": pushed,
                "pr_url": pr_url,
                "needs_confirm": needs_confirm,
            }
        except Exception as exc:  # noqa: BLE001 — runner must never let exceptions escape unhandled
            self._cleanup(worktree_path)
            return {
                "agent": agent,
                "branch": branch,
                "worktree_path": worktree_path,
                "error": str(exc),
                "pushed": False,
                "pr_url": None,
                "files_changed": [],
            }

    def _cleanup(self, worktree_path: str) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            subprocess.run(
                ["git", "-C", self.repo_path, "worktree", "remove", "--force", worktree_path],
                check=False,
                capture_output=True,
                text=True,
            )


class Forge:
    def __init__(self, runner: CodeAgentRunner):
        self.runner = runner

    def execute(
        self,
        repo: str,
        task: str,
        constraints: list[str] | None = None,
        stages: tuple[str, ...] = STAGES,
        push: bool = False,
    ) -> AgentResponse:
        """Run the full chain.

        push=False stops before opening a PR (default safe). push=True always
        requests confirmation first — the orchestrator gates the actual push
        behind tier-4 confirmation, then re-runs with confirmed=True via the
        runner's own gate.
        """
        job = ForgeJob(repo=repo, task=task, constraints=constraints or [])
        for stage in stages:
            if stage == "open_pr" and not push:
                continue
            agent_name = self._stage_to_agent(stage)
            prompt = self._stage_prompt(stage, job)
            out = self.runner.run(agent_name, prompt)
            job.stages_completed.append(stage)
            job.artifacts[stage] = out

        # When the runner is a real WorktreeRunner, push goes through the
        # tier-4 confirmation gate: surface `push_pending` + needs_confirm,
        # and the actual `git push` only fires after re-invocation with
        # confirmed=True. With the legacy MockRunner we preserve the older
        # contract used by the daemon plan-mode harness.
        gated = isinstance(self.runner, WorktreeRunner)
        if push and gated:
            action = "push_pending"
            needs_confirm = True
            follow_ups = ["confirm to push branch + open PR"]
        elif push:
            action = "completed"
            needs_confirm = False
            follow_ups = []
        else:
            action = "proposed"
            needs_confirm = True
            follow_ups = ["confirm to open PR"]

        return AgentResponse(
            agent="forge",
            intent="ship_code",
            action=action,
            result={
                "repo": repo,
                "task": task,
                "stages": job.stages_completed,
                "artifacts": job.artifacts,
            },
            follow_ups=follow_ups,
            needs_confirm=needs_confirm,
            confidence=0.85,
        )

    def pick_project(self, brief: list[dict] | None = None) -> AgentResponse:
        """Daily Forge: pick one news story and design a buildable MVP spec."""
        from . import forge_daily

        try:
            spec = forge_daily.pick_project(brief or [])
        except Exception as exc:
            return AgentResponse(
                agent="forge",
                intent="pick_project",
                action="failed",
                result={"error": f"{type(exc).__name__}: {exc}"},
                confidence=0.0,
            )
        return AgentResponse(
            agent="forge",
            intent="pick_project",
            action="picked",
            result=spec.to_dict(),
            confidence=0.85,
        )

    def scaffold_daily(self, spec: dict) -> AgentResponse:
        """Daily Forge: build the picked MVP and push to the mono-repo."""
        from . import forge_daily

        try:
            project_spec = forge_daily.ProjectSpec(
                slug=str(spec.get("slug", "")),
                title=str(spec.get("title", "")),
                news_url=str(spec.get("news_url", "")),
                news_source=str(spec.get("news_source", "")),
                spec_md=str(spec.get("spec_md", "")),
            )
            run = forge_daily.scaffold_daily(project_spec)
        except Exception as exc:
            return AgentResponse(
                agent="forge",
                intent="scaffold_daily",
                action="failed",
                result={"error": f"{type(exc).__name__}: {exc}"},
                confidence=0.0,
            )
        return AgentResponse(
            agent="forge",
            intent="scaffold_daily",
            action=run.status,
            result=run.to_dict(),
            confidence=0.9 if run.status == "success" else 0.3,
        )

    def list_runs(self, limit: int = 50) -> AgentResponse:
        """Proxy to runner.list_runs() when supported; return empty list otherwise."""
        runs: list[dict] = []
        if hasattr(self.runner, "list_runs"):
            raw = self.runner.list_runs(limit=limit)
            runs = [r if isinstance(r, dict) else vars(r) for r in raw]
        return AgentResponse(
            agent="forge",
            intent="list_runs",
            action="listed",
            result={"runs": runs, "count": len(runs)},
        )

    def get_run(self, run_id: str) -> AgentResponse:
        """Proxy to runner.get_run() when supported; return not_found otherwise."""
        run: dict | None = None
        if hasattr(self.runner, "get_run"):
            raw = self.runner.get_run(run_id)
            if raw is not None:
                run = raw if isinstance(raw, dict) else vars(raw)
        if run is None:
            return AgentResponse(
                agent="forge",
                intent="get_run",
                action="not_found",
                result={"run_id": run_id},
            )
        return AgentResponse(
            agent="forge",
            intent="get_run",
            action="found",
            result={"run": run},
        )

    @staticmethod
    def _stage_to_agent(stage: str) -> str:
        return {
            "plan": "planner",
            "tdd": "tdd-guide",
            "implement": "general-purpose",
            "review": "code-reviewer",
            "security": "security-reviewer",
            "open_pr": "general-purpose",
        }.get(stage, stage)

    @staticmethod
    def _stage_prompt(stage: str, job: ForgeJob) -> str:
        base = f"Repo: {job.repo}\nTask: {job.task}\nConstraints: {job.constraints}\n"
        prompts = {
            "plan": base + "Produce an implementation plan.",
            "tdd": base + "Write failing tests for the task.",
            "implement": base + "Implement code so the tests pass.",
            "review": base + "Review the implementation. Flag CRITICAL/HIGH issues.",
            "security": base + "Run a security review against OWASP top 10.",
            "open_pr": base + "Open PR with full context. Title and body markdown.",
        }
        return prompts.get(stage, base)
