"""Pytest fixtures — isolate state dir per test."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import get_settings


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch):
    """Each test gets a clean state dir, no shared file pollution."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_PROJECT_ROOT", str(tmp_path.parent))
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
