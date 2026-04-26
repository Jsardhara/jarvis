"""Forge — code-work delegation.

Forge orchestrates a planner→tdd→implement→review chain on a target repo.
The actual Agent-tool spawning happens inside the CC agent prompt at
.claude/agents/forge.md. This module exposes the workflow state machine
and a dry-run/plan mode that can be exercised by the daemon and tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

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
        return self._responses.get(agent, {"agent": agent, "status": "ok", "summary": f"mock {agent}"})


class Forge:
    def __init__(self, runner: CodeAgentRunner):
        self.runner = runner

    def execute(self, repo: str, task: str, constraints: list[str] | None = None,
                stages: tuple[str, ...] = STAGES, push: bool = False) -> AgentResponse:
        """Run the full chain. push=False stops before opening a PR (default safe)."""
        job = ForgeJob(repo=repo, task=task, constraints=constraints or [])
        for stage in stages:
            if stage == "open_pr" and not push:
                continue
            agent_name = self._stage_to_agent(stage)
            prompt = self._stage_prompt(stage, job)
            out = self.runner.run(agent_name, prompt)
            job.stages_completed.append(stage)
            job.artifacts[stage] = out

        action = "completed" if push else "proposed"
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
            follow_ups=[] if push else ["confirm to open PR"],
            needs_confirm=not push,
            confidence=0.85,
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
