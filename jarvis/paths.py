"""OS-aware path resolution for Jarvis runtime data.

Standardises where state files, logs, caches, model weights, and training
datasets live across operating systems. On Linux this means XDG-compliant
locations under ``~/.local/share`` and ``~/.config``; on macOS the
``~/Library`` hierarchy; on Windows the ``%APPDATA%`` / ``%LOCALAPPDATA%``
hierarchy.

Env vars always win. The existing ``JARVIS_PROJECT_ROOT`` and
``JARVIS_STATE_DIR`` overrides used by :mod:`jarvis.config` keep working; this
module adds platform-aware defaults so a fresh install on Linux or macOS
doesn't require any manual env setup before Jarvis boots.

Existing callers continue to use :func:`jarvis.config.get_settings`; this
module is the foundation for a later sweep that migrates path resolution
project-wide. For now it stands alone so it can be adopted incrementally.

Public surface::

    state_dir()      -> ~/.local/share/jarvis/state         (Linux)
                       ~/Library/Application Support/jarvis/state (macOS)
                       %APPDATA%\\jarvis\\state             (Windows)
    config_dir()     -> ~/.config/jarvis                     (Linux)
                       ~/Library/Application Support/jarvis  (macOS)
                       %APPDATA%\\jarvis                    (Windows)
    cache_dir()      -> ~/.cache/jarvis
    log_dir()        -> state_dir() / "logs"
    models_dir()     -> state_dir() / "models"   (local LLM weights)
    training_dir()   -> state_dir() / "training" (fine-tune datasets)

Every accessor calls ``mkdir(parents=True, exist_ok=True)`` so callers can
treat the returned path as guaranteed-to-exist.
"""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import PlatformDirs

_APP_NAME = "jarvis"
_APP_AUTHOR = "jarvis"  # ignored on Linux, used on Windows registry path

_dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR, roaming=False)


def _env_path(key: str) -> Path | None:
    """Read an env var as a Path, or ``None`` if unset or empty."""
    raw = os.environ.get(key)
    if not raw:
        return None
    return Path(raw).expanduser()


def _ensure(path: Path) -> Path:
    """``mkdir -p`` + return the path. Idempotent."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    """Where mutable JSONL state files live (tasks, facts, chat_turns, ...).

    Precedence: ``JARVIS_STATE_DIR`` env > ``JARVIS_PROJECT_ROOT/state`` env >
    OS-standard data dir.
    """
    override = _env_path("JARVIS_STATE_DIR")
    if override is not None:
        return _ensure(override)
    project_root = _env_path("JARVIS_PROJECT_ROOT")
    if project_root is not None:
        return _ensure(project_root / "state")
    return _ensure(Path(_dirs.user_data_dir) / "state")


def config_dir() -> Path:
    """Where user configuration lives (``config.toml`` etc.).

    Precedence: ``JARVIS_CONFIG_DIR`` env > OS-standard config dir.
    """
    override = _env_path("JARVIS_CONFIG_DIR")
    if override is not None:
        return _ensure(override)
    return _ensure(Path(_dirs.user_config_dir))


def cache_dir() -> Path:
    """Transient caches (HTTP, sentence-transformer model downloads, ...).

    Precedence: ``JARVIS_CACHE_DIR`` env > OS-standard cache dir.
    """
    override = _env_path("JARVIS_CACHE_DIR")
    if override is not None:
        return _ensure(override)
    return _ensure(Path(_dirs.user_cache_dir))


def log_dir() -> Path:
    """Where rotated log files live. Defaults to ``state_dir() / "logs"``."""
    override = _env_path("JARVIS_LOG_DIR")
    if override is not None:
        return _ensure(override)
    return _ensure(state_dir() / "logs")


def models_dir() -> Path:
    """Local LLM weights (gguf/safetensors). Big files — usually on a fast SSD.

    Precedence: ``JARVIS_MODELS_DIR`` env > ``state_dir() / "models"``.
    """
    override = _env_path("JARVIS_MODELS_DIR")
    if override is not None:
        return _ensure(override)
    return _ensure(state_dir() / "models")


def training_dir() -> Path:
    """Datasets prepared for fine-tuning.

    Precedence: ``JARVIS_TRAINING_DIR`` env > ``state_dir() / "training"``.
    """
    override = _env_path("JARVIS_TRAINING_DIR")
    if override is not None:
        return _ensure(override)
    return _ensure(state_dir() / "training")


def describe() -> dict[str, str]:
    """Snapshot of all resolved paths. Diagnostic helper for ``jarvis info``."""
    return {
        "state_dir": str(state_dir()),
        "config_dir": str(config_dir()),
        "cache_dir": str(cache_dir()),
        "log_dir": str(log_dir()),
        "models_dir": str(models_dir()),
        "training_dir": str(training_dir()),
    }
