"""Registry env-driven mode detection tests.

Verifies that build_default_registry() picks live vs mock providers based on
env vars, and that AgentDescriptor.mode is surfaced correctly.
Also verifies /api/agents exposes the mode field.
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.subsystems.registry import AgentDescriptor, build_default_registry
from jarvis.web.api import make_app

# ---------------------------------------------------------------------------
# test_tempo_mode_live_when_env_set
# ---------------------------------------------------------------------------


def test_tempo_mode_live_when_env_set(monkeypatch):
    """Tempo descriptor has mode='live' when APPLE_ID env var is set."""
    monkeypatch.setenv("APPLE_ID", "user@icloud.com")
    reg = build_default_registry()
    assert reg["tempo"].mode == "live"


def test_tempo_mode_live_when_gmail_env_set(monkeypatch):
    """Tempo descriptor has mode='live' when GMAIL_ADDRESS env var is set."""
    monkeypatch.delenv("APPLE_ID", raising=False)
    monkeypatch.setenv("GMAIL_ADDRESS", "user@gmail.com")
    reg = build_default_registry()
    assert reg["tempo"].mode == "live"


# ---------------------------------------------------------------------------
# test_tempo_mode_mock_when_env_missing
# ---------------------------------------------------------------------------


def test_tempo_mode_mock_when_env_missing(monkeypatch):
    """Tempo descriptor has mode='mock' when neither APPLE_ID nor GMAIL_ADDRESS is set."""
    monkeypatch.delenv("APPLE_ID", raising=False)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    reg = build_default_registry()
    assert reg["tempo"].mode == "mock"


# ---------------------------------------------------------------------------
# test_lens_mode_mock_when_no_exa_key
# ---------------------------------------------------------------------------


def test_lens_mode_mock_when_no_exa_key(monkeypatch):
    """Lens descriptor has mode='mock' when EXA_API_KEY is absent."""
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    reg = build_default_registry()
    assert reg["lens"].mode == "mock"


def test_lens_mode_live_when_exa_key_set(monkeypatch):
    """Lens descriptor has mode='live' when EXA_API_KEY is present."""
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")
    reg = build_default_registry()
    assert reg["lens"].mode == "live"


# ---------------------------------------------------------------------------
# test_atlas_mode_via_health_check
# ---------------------------------------------------------------------------


def test_atlas_mode_returned_from_registry(monkeypatch):
    """Atlas descriptor mode is either 'live' or 'mock' (valid string)."""
    reg = build_default_registry()
    assert reg["atlas"].mode in ("live", "mock")


def test_forge_mode_mock_when_claude_absent(monkeypatch):
    """Forge falls back to mode='mock' when claude CLI is not on PATH."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    reg = build_default_registry()
    assert reg["forge"].mode == "mock"


def test_forge_mode_live_when_claude_present(monkeypatch, tmp_path):
    """Forge uses mode='live' (WorktreeRunner) when claude CLI is found on PATH."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/claude")
    # Point repo_root at tmp_path so WorktreeRunner doesn't touch the real repo
    import jarvis.subsystems.forge_runner as fr

    monkeypatch.setattr(fr, "_DEFAULT_TIMEOUT", 1)
    # Patch WorktreeRunner.__init__ to avoid real filesystem side effects
    original_init = fr.WorktreeRunner.__init__

    def _patched_init(self, repo_root=None, claude_bin="claude", timeout=600):
        original_init(self, repo_root=tmp_path, claude_bin=claude_bin, timeout=timeout)

    monkeypatch.setattr(fr.WorktreeRunner, "__init__", _patched_init)
    reg = build_default_registry()
    assert reg["forge"].mode == "live"


def test_scholar_mode_is_always_live(monkeypatch):
    """Scholar descriptor is always mode='live' (no external API dependency)."""
    reg = build_default_registry()
    assert reg["scholar"].mode == "live"


# ---------------------------------------------------------------------------
# AgentDescriptor default mode
# ---------------------------------------------------------------------------


def test_agent_descriptor_default_mode():
    """AgentDescriptor defaults to mode='mock'."""

    desc = AgentDescriptor(name="test", instance=object(), description="test agent")
    assert desc.mode == "mock"


# ---------------------------------------------------------------------------
# test_api_agents_surfaces_mode_field
# ---------------------------------------------------------------------------


def test_api_agents_surfaces_mode_field(monkeypatch):
    """GET /api/agents returns a 'mode' field for each agent."""
    monkeypatch.delenv("APPLE_ID", raising=False)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    reg = build_default_registry()
    client = TestClient(make_app(registry=reg))
    r = client.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) > 0
    for agent in agents:
        assert "mode" in agent, f"agent {agent['name']!r} missing 'mode' field"
        assert agent["mode"] in ("live", "mock"), f"invalid mode {agent['mode']!r}"


def test_api_agents_tempo_mode_mock_when_no_env(monkeypatch):
    """GET /api/agents shows tempo mode=mock when no mail env vars."""
    monkeypatch.delenv("APPLE_ID", raising=False)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    reg = build_default_registry()
    client = TestClient(make_app(registry=reg))
    r = client.get("/api/agents")
    agents_by_name = {a["name"]: a for a in r.json()["agents"]}
    assert agents_by_name["tempo"]["mode"] == "mock"


def test_api_agents_tempo_mode_live_when_env_set(monkeypatch):
    """GET /api/agents shows tempo mode=live when APPLE_ID is set."""
    monkeypatch.setenv("APPLE_ID", "user@icloud.com")
    reg = build_default_registry()
    client = TestClient(make_app(registry=reg))
    r = client.get("/api/agents")
    agents_by_name = {a["name"]: a for a in r.json()["agents"]}
    assert agents_by_name["tempo"]["mode"] == "live"
