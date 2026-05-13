"""Daily Forge — autonomous news→project→GitHub loop.

Two operations:

- ``pick_project(stories)`` — Opus picks ONE story and writes a buildable
  MVP web-app spec.
- ``scaffold_daily(spec)`` — claude CLI builds the project in a folder
  inside the forge-projects mono-repo clone, then forge_github commits
  and pushes.

Cost is read from the claude CLI ``--output-format json`` envelope and
recorded via ``budget.record_spend``.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.agents.atlas import budget

from . import github as forge_github

log = logging.getLogger(__name__)


# ── Cost estimates (rough, used only by budget guard pre-call) ────────────────

PICK_COST_ESTIMATE_USD = 0.50
SCAFFOLD_COST_ESTIMATE_USD = 2.50

# Hard wall-clock cap for the claude scaffold call (60 min).
SCAFFOLD_TIMEOUT_SEC = 60 * 60

# Cap claude session turns. Each `claude -p` call is one session.
MAX_TURNS = 60

OPUS_MODEL = "claude-opus-4-7"


@dataclass(frozen=True)
class ProjectSpec:
    slug: str
    title: str
    news_url: str
    news_source: str
    spec_md: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyForgeRun:
    date: str
    slug: str
    title: str
    folder: str
    repo_url: str
    commit_sha: str
    cost_usd: float
    duration_sec: float
    status: str  # "success" | "skipped_budget" | "failed"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Slug + path helpers ───────────────────────────────────────────────────────


def _slugify(text: str, max_len: int = 30) -> str:
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _today_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


# ── pick_project ──────────────────────────────────────────────────────────────


_PICK_SYSTEM_PROMPT = """You are Forge — autonomous project-builder for Jyot.

You are picking ONE world-news story to inspire today's web-app MVP.

Hard constraints:
- Pick a story that maps cleanly to a useful, buildable web-app a single
  developer could ship in 60 minutes.
- The MVP must be useful to real people, not a toy.
- Avoid politically charged angles. Stick to what the world needs:
  information access, coordination, awareness, services.
- Web app only. Next.js + Tailwind preferred. Plain HTML/JS acceptable.
  Backend optional (use FastAPI if needed). No native/mobile/binary builds.

Output ONLY valid JSON, no prose, with this shape:
{
  "slug": "kebab-case-max-30-chars",
  "title": "Human-readable project title",
  "news_url": "the picked story URL",
  "news_source": "Reuters | AP | BBC",
  "spec_md": "<300-500 words of markdown spec>"
}

The spec_md must contain:
- ## Why (2-3 sentences linking to the news story)
- ## What it does (concrete user value)
- ## Build (file tree + key components, tech stack pinned)
- ## Done when (clear acceptance criteria)

The slug must NOT include a date prefix — that gets added externally.
"""


_PICK_JSON_SCHEMA = {
    "type": "object",
    "required": ["slug", "title", "news_url", "news_source", "spec_md"],
    "properties": {
        "slug": {"type": "string"},
        "title": {"type": "string"},
        "news_url": {"type": "string"},
        "news_source": {"type": "string"},
        "spec_md": {"type": "string"},
    },
    "additionalProperties": False,
}


def pick_project(stories: list[dict[str, Any]]) -> ProjectSpec:
    """Ask Opus (via claude CLI) to pick one story and write a buildable MVP spec.

    Uses the claude CLI subprocess (same auth path as Jarvis chat — uses your
    Pro/Max plan, not the API key + OAuth-API rate limit pool). Raises on
    process or parse failure.
    """
    if not stories:
        raise ValueError("pick_project: empty stories list")

    payload_lines: list[str] = []
    for i, s in enumerate(stories[:8], 1):
        payload_lines.append(
            f"### Story {i} — {s.get('source', '?')}\n"
            f"Title: {s.get('title', '')}\n"
            f"URL: {s.get('url', '')}\n"
            f"Summary: {s.get('summary', '')[:400]}\n"
        )
    user_msg = (
        _PICK_SYSTEM_PROMPT
        + "\n\n---\n\nPick one and design the MVP. Reply with ONLY the JSON object.\n\n"
        + "\n".join(payload_lines)
    )

    claude_bin = _resolve_claude_bin()
    cmd = [
        claude_bin,
        "-p",
        user_msg,
        "--output-format",
        "json",
        "--max-turns",
        "1",
    ]
    log.info("pick_project: invoking claude CLI (Opus)")
    proc = _run_with_retry(cmd, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pick_project: claude exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout)[:300]}"
        )

    envelope = json.loads(proc.stdout.strip().splitlines()[-1])
    cost_usd = float(envelope.get("total_cost_usd") or 0.0)
    if cost_usd > 0:
        budget.record_spend(cost_usd, tag="forge.pick_project")

    raw = envelope.get("result", "")
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError(f"pick_project: unexpected result type {type(raw)}")

    spec = ProjectSpec(
        slug=_slugify(str(data.get("slug", "untitled"))),
        title=str(data.get("title", "Untitled")).strip()[:120],
        news_url=str(data.get("news_url", "")),
        news_source=str(data.get("news_source", "")),
        spec_md=str(data.get("spec_md", "")),
    )
    if not spec.spec_md:
        raise ValueError("pick_project: empty spec_md")
    return spec


# ── scaffold_daily ────────────────────────────────────────────────────────────


_SCAFFOLD_PROMPT_TEMPLATE = """You are Forge — autonomous project-builder.

Build the MVP described below. Work inside the CURRENT directory.

Hard rules:
- Write files only in the current directory tree. No edits outside it.
- Tech stack: prefer Next.js + Tailwind for web apps, FastAPI for backend
  if needed. Pure HTML/JS is fine for tiny utilities.
- Include a clear README.md at the project root with: purpose, news source,
  how to run, what works, known gaps.
- Make it actually run. Include package.json / requirements.txt as needed.
- Do NOT spawn additional agents. Do not call git. Just write files.
- Stop when the spec acceptance criteria are met.

Spec:
---
{spec_md}
---

News inspiration:
- Source: {news_source}
- URL: {news_url}

Begin.
"""


def _resolve_claude_bin() -> str:
    bin_name = "claude"
    resolved = shutil.which(bin_name)
    if resolved is None:
        raise RuntimeError("claude CLI not on PATH")
    return resolved


_RETRY_BACKOFF_SEC: tuple[float, ...] = (60.0, 180.0, 600.0)
_RETRY_PATTERNS = ("rate_limit", "429", "overloaded", "529")


def _is_retryable_output(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _RETRY_PATTERNS)


def _run_with_retry(
    cmd: list[str],
    *,
    timeout: int,
    cwd: str | None = None,
    backoff: tuple[float, ...] = _RETRY_BACKOFF_SEC,
) -> subprocess.CompletedProcess[str]:
    """Run a claude CLI subprocess with exponential backoff on rate-limit errors.

    Pro/Max plan shares one rolling rate-limit bucket across the host. When
    the CLI surfaces a 429/overloaded signal, retry with backoff instead of
    failing the daily forge run.
    """
    attempts = len(backoff) + 1
    last: subprocess.CompletedProcess[str] | None = None
    for i in range(attempts):
        proc = subprocess.run(  # noqa: S603 — caller-supplied claude CLI
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        last = proc
        if proc.returncode == 0:
            return proc
        merged = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if not _is_retryable_output(merged) or i >= attempts - 1:
            return proc
        delay = backoff[i]
        log.warning(
            "claude CLI rate-limited (attempt %d/%d) — sleeping %.0fs",
            i + 1,
            attempts,
            delay,
        )
        time.sleep(delay)
    assert last is not None
    return last


def _run_claude_in(folder: Path, prompt: str) -> tuple[int, str, float]:
    """Run claude CLI with --output-format json. Returns (exit, log_text, cost_usd)."""
    claude_bin = _resolve_claude_bin()
    # Hard-cap claude's spend to remaining daily budget (minus a small safety margin)
    remaining = max(0.50, budget.snapshot().remaining_usd - 0.20)
    cmd = [
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(MAX_TURNS),
        "--permission-mode",
        "bypassPermissions",
        "--max-budget-usd",
        f"{remaining:.2f}",
    ]
    log.info("scaffold: claude -p in %s (timeout %ds)", folder, SCAFFOLD_TIMEOUT_SEC)
    started = time.monotonic()
    proc = _run_with_retry(cmd, timeout=SCAFFOLD_TIMEOUT_SEC, cwd=str(folder))
    duration = time.monotonic() - started
    log.info("scaffold: claude exit=%d duration=%.1fs", proc.returncode, duration)

    cost = 0.0
    log_text = (proc.stdout or "") + "\n--STDERR--\n" + (proc.stderr or "")
    # Parse final JSON envelope
    try:
        env = json.loads(proc.stdout.strip().splitlines()[-1])
        cost = float(env.get("total_cost_usd") or env.get("cost_usd") or 0.0)
    except Exception:
        pass
    return proc.returncode, log_text, cost


def _write_initial_files(folder: Path, spec: ProjectSpec) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SPEC.md").write_text(spec.spec_md, encoding="utf-8")
    # Forge will overwrite README.md but seed one in case it skips
    seed = (
        f"# {spec.title}\n\n"
        f"Inspired by [{spec.news_source}]({spec.news_url}).\n\n"
        f"See SPEC.md for build details.\n"
    )
    (folder / "README.md").write_text(seed, encoding="utf-8")


def scaffold_daily(spec: ProjectSpec) -> DailyForgeRun:
    """Build the MVP in the mono-repo clone and push to GitHub."""
    started_at = time.monotonic()
    date_str = _today_str()
    folder_name = f"{date_str}-{spec.slug}"
    error: str | None = None
    cost_usd = 0.0
    commit_sha = ""
    status = "failed"
    repo_url = ""

    try:
        ctx = forge_github.ensure_mono_repo_clone()
        repo_url = ctx.repo_url
        target = ctx.clone_dir / folder_name
        if target.exists():
            i = 2
            while (ctx.clone_dir / f"{folder_name}-v{i}").exists():
                i += 1
            folder_name = f"{folder_name}-v{i}"
            target = ctx.clone_dir / folder_name

        _write_initial_files(target, spec)

        prompt = _SCAFFOLD_PROMPT_TEMPLATE.format(
            spec_md=spec.spec_md,
            news_source=spec.news_source,
            news_url=spec.news_url,
        )
        exit_code, log_text, cost_usd = _run_claude_in(target, prompt)

        log_dir = ctx.clone_dir.parent / "forge-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{folder_name}.log").write_text(log_text, encoding="utf-8")

        if exit_code != 0:
            error = f"claude exited {exit_code}"
        else:
            entry = (
                f"| {date_str} | {spec.title} | "
                f"[{spec.news_source}]({spec.news_url}) | "
                f"[{folder_name}](./{folder_name}) |"
            )
            forge_github.update_index(ctx, entry)
            commit_msg = f"daily forge {date_str}: {spec.title} ({spec.slug})"
            commit_sha = forge_github.push_daily(ctx, folder_name, commit_msg)
            status = "success"

    except subprocess.TimeoutExpired:
        error = f"timeout > {SCAFFOLD_TIMEOUT_SEC}s"
        log.error("scaffold_daily: %s", error)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.exception("scaffold_daily failed")

    duration = time.monotonic() - started_at
    if cost_usd > 0:
        budget.record_spend(cost_usd, tag="forge.scaffold_daily")

    return DailyForgeRun(
        date=date_str,
        slug=spec.slug,
        title=spec.title,
        folder=folder_name,
        repo_url=repo_url,
        commit_sha=commit_sha,
        cost_usd=cost_usd,
        duration_sec=duration,
        status=status,
        error=error,
    )
