"""Tests for jarvis.paths — OS-aware path resolution with env overrides."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis import paths


class _FakeDirs:
    """Stand-in for PlatformDirs that returns pre-set paths."""

    def __init__(
        self,
        user_data_dir: str,
        user_config_dir: str,
        user_cache_dir: str,
    ) -> None:
        self.user_data_dir = user_data_dir
        self.user_config_dir = user_config_dir
        self.user_cache_dir = user_cache_dir


# ---------------------------------------------------------------------------
# state_dir
# ---------------------------------------------------------------------------


def test_state_dir_uses_jarvis_state_dir_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "explicit-state"
    monkeypatch.setenv("JARVIS_STATE_DIR", str(target))
    out = paths.state_dir()
    assert out == target
    assert out.exists()


def test_state_dir_falls_back_to_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_STATE_DIR", raising=False)
    monkeypatch.setenv("JARVIS_PROJECT_ROOT", str(tmp_path))
    out = paths.state_dir()
    assert out == tmp_path / "state"
    assert out.exists()


def test_state_dir_falls_back_to_platformdirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No env vars -> platformdirs picks the OS-standard data dir."""
    monkeypatch.delenv("JARVIS_STATE_DIR", raising=False)
    monkeypatch.delenv("JARVIS_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(
        paths,
        "_dirs",
        _FakeDirs(
            user_data_dir=str(tmp_path / "data"),
            user_config_dir=str(tmp_path / "cfg"),
            user_cache_dir=str(tmp_path / "cache"),
        ),
    )
    out = paths.state_dir()
    assert out == tmp_path / "data" / "state"
    assert out.exists()


# ---------------------------------------------------------------------------
# config_dir
# ---------------------------------------------------------------------------


def test_config_dir_uses_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "my-config"
    monkeypatch.setenv("JARVIS_CONFIG_DIR", str(target))
    out = paths.config_dir()
    assert out == target
    assert out.exists()


def test_config_dir_falls_back_to_platformdirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_CONFIG_DIR", raising=False)
    monkeypatch.setattr(
        paths,
        "_dirs",
        _FakeDirs(
            user_data_dir=str(tmp_path / "data"),
            user_config_dir=str(tmp_path / "cfg"),
            user_cache_dir=str(tmp_path / "cache"),
        ),
    )
    out = paths.config_dir()
    assert out == tmp_path / "cfg"


# ---------------------------------------------------------------------------
# cache_dir
# ---------------------------------------------------------------------------


def test_cache_dir_uses_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "my-cache"
    monkeypatch.setenv("JARVIS_CACHE_DIR", str(target))
    assert paths.cache_dir() == target


def test_cache_dir_falls_back_to_platformdirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_CACHE_DIR", raising=False)
    monkeypatch.setattr(
        paths,
        "_dirs",
        _FakeDirs(
            user_data_dir=str(tmp_path / "data"),
            user_config_dir=str(tmp_path / "cfg"),
            user_cache_dir=str(tmp_path / "cache"),
        ),
    )
    assert paths.cache_dir() == tmp_path / "cache"


# ---------------------------------------------------------------------------
# log_dir / models_dir / training_dir
# ---------------------------------------------------------------------------


def test_log_dir_defaults_under_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_LOG_DIR", raising=False)
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    assert paths.log_dir() == tmp_path / "logs"


def test_log_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "elsewhere-logs"
    monkeypatch.setenv("JARVIS_LOG_DIR", str(target))
    assert paths.log_dir() == target


def test_models_dir_defaults_under_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_MODELS_DIR", raising=False)
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    assert paths.models_dir() == tmp_path / "models"


def test_models_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fast-ssd" / "models"
    monkeypatch.setenv("JARVIS_MODELS_DIR", str(target))
    assert paths.models_dir() == target


def test_training_dir_defaults_under_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JARVIS_TRAINING_DIR", raising=False)
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    assert paths.training_dir() == tmp_path / "training"


def test_training_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "datasets"
    monkeypatch.setenv("JARVIS_TRAINING_DIR", str(target))
    assert paths.training_dir() == target


# ---------------------------------------------------------------------------
# Idempotency + describe()
# ---------------------------------------------------------------------------


def test_repeated_calls_are_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    assert paths.state_dir() == paths.state_dir()
    assert paths.state_dir().exists()


def test_env_with_tilde_expands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leading ~ in an env var expands to the user home.

    Path.expanduser() resolves home differently per platform: POSIX uses
    HOME, Windows uses USERPROFILE. Patch both so the test is deterministic
    on either OS.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("JARVIS_STATE_DIR", "~/jarvis-state")
    out = paths.state_dir()
    assert out == tmp_path / "jarvis-state"


def test_empty_env_treated_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty string falls back to next-in-precedence (not the empty path)."""
    monkeypatch.setenv("JARVIS_STATE_DIR", "")
    monkeypatch.setenv("JARVIS_PROJECT_ROOT", str(tmp_path))
    assert paths.state_dir() == tmp_path / "state"


def test_describe_returns_all_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("JARVIS_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("JARVIS_CACHE_DIR", str(tmp_path / "cache"))
    info = paths.describe()
    assert set(info.keys()) == {
        "state_dir",
        "config_dir",
        "cache_dir",
        "log_dir",
        "models_dir",
        "training_dir",
    }
    assert info["state_dir"].endswith("s")
