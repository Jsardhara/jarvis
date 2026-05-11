"""Tests for forge_daily — pick_project + scaffold_daily orchestration."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from jarvis.subsystems import forge_daily, forge_github


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _envelope(result: str | dict, cost: float = 0.42) -> str:
    payload = {"result": result, "total_cost_usd": cost}
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

def test_slugify_lowercases_and_dashes():
    assert forge_daily._slugify("Hello World!") == "hello-world"


def test_slugify_trims_trailing_dashes():
    assert forge_daily._slugify("---hi---") == "hi"


def test_slugify_truncates_to_max_len():
    out = forge_daily._slugify("a" * 100, max_len=10)
    assert len(out) <= 10


def test_slugify_empty_returns_untitled():
    assert forge_daily._slugify("") == "untitled"
    assert forge_daily._slugify("!!!") == "untitled"


# ---------------------------------------------------------------------------
# _is_retryable_output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    ["rate_limit hit", "HTTP 429 received", "service overloaded", "529 backend"],
)
def test_is_retryable_true(text):
    assert forge_daily._is_retryable_output(text) is True


def test_is_retryable_false_on_normal_error():
    assert forge_daily._is_retryable_output("file not found") is False


# ---------------------------------------------------------------------------
# _resolve_claude_bin
# ---------------------------------------------------------------------------

def test_resolve_claude_bin_raises_when_missing(monkeypatch):
    monkeypatch.setattr(forge_daily.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="claude CLI not on PATH"):
        forge_daily._resolve_claude_bin()


def test_resolve_claude_bin_returns_path(monkeypatch):
    monkeypatch.setattr(forge_daily.shutil, "which", lambda _: "/usr/bin/claude")
    assert forge_daily._resolve_claude_bin() == "/usr/bin/claude"


# ---------------------------------------------------------------------------
# _run_with_retry
# ---------------------------------------------------------------------------

def test_run_with_retry_returns_immediately_on_success(monkeypatch):
    fake = subprocess.CompletedProcess(["claude"], 0, "ok", "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    proc = forge_daily._run_with_retry(["claude"], timeout=5, backoff=())
    assert proc.returncode == 0


def test_run_with_retry_returns_on_non_retryable_error(monkeypatch):
    fake = subprocess.CompletedProcess(["claude"], 2, "syntax error", "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake)
    proc = forge_daily._run_with_retry(["claude"], timeout=5, backoff=(0.01,))
    assert proc.returncode == 2


def test_run_with_retry_retries_on_rate_limit_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_run(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(["claude"], 1, "rate_limit", "")
        return subprocess.CompletedProcess(["claude"], 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(forge_daily.time, "sleep", lambda _: None)
    proc = forge_daily._run_with_retry(["claude"], timeout=5, backoff=(0.0,))
    assert proc.returncode == 0
    assert calls["n"] == 2


def test_run_with_retry_gives_up_after_attempts(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(["claude"], 1, "rate_limit", ""),
    )
    monkeypatch.setattr(forge_daily.time, "sleep", lambda _: None)
    proc = forge_daily._run_with_retry(["claude"], timeout=5, backoff=(0.0,))
    assert proc.returncode == 1


# ---------------------------------------------------------------------------
# pick_project
# ---------------------------------------------------------------------------

_STORY = {"source": "Reuters", "title": "Flood relief", "url": "https://r/a", "summary": "bad floods"}


def test_pick_project_raises_on_empty_stories():
    with pytest.raises(ValueError, match="empty stories list"):
        forge_daily.pick_project([])


def test_pick_project_parses_envelope_and_records_spend(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")

    spec_payload = {
        "slug": "flood-tracker",
        "title": "Flood Relief Tracker",
        "news_url": "https://r/a",
        "news_source": "Reuters",
        "spec_md": "## Why\nfloods\n## What\nmap",
    }
    proc = subprocess.CompletedProcess(
        ["claude"], 0, _envelope(json.dumps(spec_payload), cost=0.30), ""
    )
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)

    spent: list[tuple[float, str]] = []
    monkeypatch.setattr(
        forge_daily.budget,
        "record_spend",
        lambda usd, tag="": spent.append((usd, tag)),
    )

    spec = forge_daily.pick_project([_STORY])
    assert spec.slug == "flood-tracker"
    assert spec.title == "Flood Relief Tracker"
    assert "## Why" in spec.spec_md
    assert spent and spent[0][0] == 0.30 and spent[0][1] == "forge.pick_project"


def test_pick_project_strips_markdown_fence(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    payload = {
        "slug": "x", "title": "X", "news_url": "u",
        "news_source": "s", "spec_md": "spec",
    }
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    proc = subprocess.CompletedProcess(["claude"], 0, _envelope(fenced, 0), "")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    spec = forge_daily.pick_project([_STORY])
    assert spec.slug == "x"


def test_pick_project_accepts_dict_result(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    payload = {
        "slug": "y", "title": "Y", "news_url": "u",
        "news_source": "s", "spec_md": "spec",
    }
    envelope = json.dumps({"result": payload, "total_cost_usd": 0})
    proc = subprocess.CompletedProcess(["claude"], 0, envelope, "")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    spec = forge_daily.pick_project([_STORY])
    assert spec.slug == "y"


def test_pick_project_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    proc = subprocess.CompletedProcess(["claude"], 1, "", "boom")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)
    with pytest.raises(RuntimeError, match="claude exited 1"):
        forge_daily.pick_project([_STORY])


def test_pick_project_raises_on_empty_spec_md(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    payload = {
        "slug": "z", "title": "Z", "news_url": "u",
        "news_source": "s", "spec_md": "",
    }
    proc = subprocess.CompletedProcess(
        ["claude"], 0, _envelope(json.dumps(payload), 0), ""
    )
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)
    with pytest.raises(ValueError, match="empty spec_md"):
        forge_daily.pick_project([_STORY])


def test_pick_project_unexpected_result_type_raises(monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    envelope = json.dumps({"result": 42, "total_cost_usd": 0})
    proc = subprocess.CompletedProcess(["claude"], 0, envelope, "")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)
    with pytest.raises(ValueError, match="unexpected result type"):
        forge_daily.pick_project([_STORY])


# ---------------------------------------------------------------------------
# ProjectSpec / DailyForgeRun dataclasses
# ---------------------------------------------------------------------------

def test_project_spec_to_dict():
    spec = forge_daily.ProjectSpec(
        slug="s", title="T", news_url="u", news_source="src", spec_md="m",
    )
    assert spec.to_dict() == {
        "slug": "s", "title": "T", "news_url": "u",
        "news_source": "src", "spec_md": "m",
    }


def test_daily_forge_run_to_dict():
    run = forge_daily.DailyForgeRun(
        date="2026-05-11", slug="s", title="T", folder="f",
        repo_url="u", commit_sha="abc", cost_usd=1.0, duration_sec=2.0,
        status="success",
    )
    d = run.to_dict()
    assert d["status"] == "success"
    assert d["error"] is None


# ---------------------------------------------------------------------------
# scaffold_daily — happy + failure paths
# ---------------------------------------------------------------------------

def _make_spec() -> forge_daily.ProjectSpec:
    return forge_daily.ProjectSpec(
        slug="foo", title="Foo Project", news_url="https://r/a",
        news_source="Reuters", spec_md="## Why\nbecause\n",
    )


def test_scaffold_daily_success(tmp_path, monkeypatch):
    spec = _make_spec()
    clone = tmp_path / "clone"
    clone.mkdir()
    ctx = forge_github.GitHubContext(user="alice", repo="alice/x", clone_dir=clone)

    monkeypatch.setattr(forge_daily.forge_github, "ensure_mono_repo_clone", lambda: ctx)
    monkeypatch.setattr(
        forge_daily, "_run_claude_in",
        lambda folder, prompt: (0, "build log", 1.25),
    )
    pushed: list[tuple] = []
    monkeypatch.setattr(
        forge_daily.forge_github, "update_index",
        lambda c, e: pushed.append(("idx", e)),
    )
    monkeypatch.setattr(
        forge_daily.forge_github, "push_daily",
        lambda c, folder, msg: "deadbeef",
    )
    monkeypatch.setattr(
        forge_daily.budget, "record_spend", lambda *a, **kw: None,
    )

    run = forge_daily.scaffold_daily(spec)
    assert run.status == "success"
    assert run.commit_sha == "deadbeef"
    assert run.cost_usd == 1.25
    assert run.error is None
    # SPEC.md + README.md seeded
    folder_path = clone / run.folder
    assert (folder_path / "SPEC.md").exists()
    assert (folder_path / "README.md").exists()
    # Forge log written
    assert any(p.suffix == ".log" for p in (clone.parent / "forge-logs").iterdir())


def test_scaffold_daily_handles_existing_folder_with_v2(tmp_path, monkeypatch):
    spec = _make_spec()
    clone = tmp_path / "clone"
    clone.mkdir()
    # pre-create today's folder so it gets bumped to -v2
    today = forge_daily._today_str()
    (clone / f"{today}-foo").mkdir()
    ctx = forge_github.GitHubContext(user="alice", repo="alice/x", clone_dir=clone)
    monkeypatch.setattr(forge_daily.forge_github, "ensure_mono_repo_clone", lambda: ctx)
    monkeypatch.setattr(
        forge_daily, "_run_claude_in",
        lambda folder, prompt: (0, "log", 0.0),
    )
    monkeypatch.setattr(forge_daily.forge_github, "update_index", lambda *a: None)
    monkeypatch.setattr(forge_daily.forge_github, "push_daily", lambda *a: "sha")
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    run = forge_daily.scaffold_daily(spec)
    assert run.folder.endswith("-v2")
    assert run.status == "success"


def test_scaffold_daily_records_failed_when_claude_nonzero(tmp_path, monkeypatch):
    spec = _make_spec()
    clone = tmp_path / "clone"
    clone.mkdir()
    ctx = forge_github.GitHubContext(user="alice", repo="alice/x", clone_dir=clone)
    monkeypatch.setattr(forge_daily.forge_github, "ensure_mono_repo_clone", lambda: ctx)
    monkeypatch.setattr(
        forge_daily, "_run_claude_in",
        lambda folder, prompt: (3, "log", 0.5),
    )
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    run = forge_daily.scaffold_daily(spec)
    assert run.status == "failed"
    assert "claude exited 3" in (run.error or "")


def test_scaffold_daily_handles_ensure_clone_exception(tmp_path, monkeypatch):
    spec = _make_spec()

    def boom():
        raise RuntimeError("gh down")

    monkeypatch.setattr(forge_daily.forge_github, "ensure_mono_repo_clone", boom)
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    run = forge_daily.scaffold_daily(spec)
    assert run.status == "failed"
    assert "RuntimeError" in (run.error or "")


def test_scaffold_daily_handles_timeout(tmp_path, monkeypatch):
    spec = _make_spec()
    clone = tmp_path / "clone"
    clone.mkdir()
    ctx = forge_github.GitHubContext(user="alice", repo="alice/x", clone_dir=clone)
    monkeypatch.setattr(forge_daily.forge_github, "ensure_mono_repo_clone", lambda: ctx)

    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(forge_daily, "_run_claude_in", boom)
    monkeypatch.setattr(forge_daily.budget, "record_spend", lambda *a, **kw: None)

    run = forge_daily.scaffold_daily(spec)
    assert run.status == "failed"
    assert "timeout" in (run.error or "").lower()


# ---------------------------------------------------------------------------
# _run_claude_in — parses cost envelope
# ---------------------------------------------------------------------------

def test_run_claude_in_parses_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")

    snap = MagicMock(remaining_usd=4.0)
    monkeypatch.setattr(forge_daily.budget, "snapshot", lambda: snap)

    envelope = json.dumps({"total_cost_usd": 1.5})
    proc = subprocess.CompletedProcess(["claude"], 0, envelope, "")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)

    rc, log_text, cost = forge_daily._run_claude_in(tmp_path, "prompt")
    assert rc == 0
    assert cost == 1.5
    assert envelope in log_text


def test_run_claude_in_handles_unparseable_envelope(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_daily, "_resolve_claude_bin", lambda: "/bin/claude")
    snap = MagicMock(remaining_usd=4.0)
    monkeypatch.setattr(forge_daily.budget, "snapshot", lambda: snap)
    proc = subprocess.CompletedProcess(["claude"], 0, "not json", "stderr")
    monkeypatch.setattr(forge_daily, "_run_with_retry", lambda *a, **kw: proc)

    rc, log_text, cost = forge_daily._run_claude_in(tmp_path, "prompt")
    assert cost == 0.0
    assert "stderr" in log_text


# ---------------------------------------------------------------------------
# _today_str — sanity
# ---------------------------------------------------------------------------

def test_today_str_format():
    s = forge_daily._today_str()
    assert len(s) == 10 and s[4] == "-" and s[7] == "-"
