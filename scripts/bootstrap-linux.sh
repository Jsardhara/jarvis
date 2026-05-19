#!/usr/bin/env bash
# Bootstrap Jarvis on a fresh Linux box (Ubuntu 22.04 / 24.04 tested).
#
# Idempotent first-boot setup for the new PC. Stages:
#
#   1. Verify OS + Python 3.11+.
#   2. Install OS packages (build tools, ffmpeg, portaudio for voice).
#   3. Set up project venv + editable install.
#   4. Create XDG state/config/cache dirs under ~/.local/share/jarvis etc.
#   5. Seed an empty config file if one doesn't exist.
#   6. Install systemd units (delegates to install-services.sh).
#   7. Print next-step pointers for vLLM / Ollama install once the new PC is up.
#
# Usage:
#   bash scripts/bootstrap-linux.sh                      # full bootstrap
#   bash scripts/bootstrap-linux.sh --skip-services      # everything except systemd
#   bash scripts/bootstrap-linux.sh --skip-apt           # skip OS package install
#   bash scripts/bootstrap-linux.sh --dry-run            # print actions, no execute
#
# Re-runnable: every step skips work that's already done.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_APT=0
SKIP_SERVICES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-apt)      SKIP_APT=1; shift ;;
        --skip-services) SKIP_SERVICES=1; shift ;;
        --dry-run)       DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '/^# Usage:/,/^# Re-runnable/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "[bootstrap] unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

say() { echo "[bootstrap] $*"; }

# ---------------------------------------------------------------------------
# 1. OS + Python check
# ---------------------------------------------------------------------------

if [[ "$(uname)" != "Linux" ]]; then
    echo "[bootstrap] this script is for Linux only. macOS support is a future phase." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "[bootstrap] python3 not found. Install Python 3.11+ and re-run." >&2
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 11 ]]; }; then
    echo "[bootstrap] python $PY_VERSION found, but Jarvis needs >=3.11." >&2
    echo "  On Ubuntu: sudo apt install python3.11 python3.11-venv" >&2
    exit 1
fi

say "OS Linux, Python $PY_VERSION — OK"

# ---------------------------------------------------------------------------
# 2. OS packages
# ---------------------------------------------------------------------------

if [[ $SKIP_APT -eq 0 ]]; then
    if command -v apt-get >/dev/null 2>&1; then
        say "installing OS packages (apt)..."
        run sudo apt-get update -qq
        run sudo apt-get install -y --no-install-recommends \
            build-essential \
            python3-pip \
            python3-venv \
            ffmpeg \
            portaudio19-dev \
            libsndfile1 \
            curl \
            git
    else
        say "non-apt distro detected. Install equivalents of: build-essential, python3-venv, ffmpeg, portaudio dev headers, libsndfile."
    fi
fi

# ---------------------------------------------------------------------------
# 3. Project venv + editable install
# ---------------------------------------------------------------------------

VENV_DIR="$PROJECT_ROOT/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    say "creating venv at $VENV_DIR"
    run python3 -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
say "installing jarvis in editable mode..."
run "$VENV_PY" -m pip install --upgrade --quiet pip
run "$VENV_PY" -m pip install --quiet -e "$PROJECT_ROOT[dev,web]"

# Optional extras the operator can install later:
say "optional extras not auto-installed (run manually when ready):"
say "  voice : .venv/bin/pip install -e '$PROJECT_ROOT[voice]'"
say "  links : .venv/bin/pip install -e '$PROJECT_ROOT[links]'"

# ---------------------------------------------------------------------------
# 4. XDG dirs
# ---------------------------------------------------------------------------

say "creating XDG dirs..."
for d in \
    "$HOME/.local/share/jarvis/state" \
    "$HOME/.local/share/jarvis/logs" \
    "$HOME/.local/share/jarvis/models" \
    "$HOME/.local/share/jarvis/training" \
    "$HOME/.config/jarvis" \
    "$HOME/.cache/jarvis"; do
    run mkdir -p "$d"
done

# ---------------------------------------------------------------------------
# 5. Seed env file
# ---------------------------------------------------------------------------

ENV_FILE="$HOME/.config/jarvis/env"
if [[ ! -f "$ENV_FILE" ]]; then
    say "seeding $ENV_FILE (copy from $PROJECT_ROOT/.env if you have one)..."
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        run cp "$PROJECT_ROOT/.env" "$ENV_FILE"
    else
        run cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
        say "$ENV_FILE seeded from .env.example. Edit it before starting services."
    fi
fi

# ---------------------------------------------------------------------------
# 6. systemd units
# ---------------------------------------------------------------------------

if [[ $SKIP_SERVICES -eq 0 ]]; then
    say "installing systemd units (api + sentinel only by default — enable others manually)..."
    PYTHON_BIN="$VENV_PY" run bash "$SCRIPT_DIR/install-services.sh" --units api,sentinel
else
    say "skipping systemd install. Run scripts/install-services.sh when ready."
fi

# ---------------------------------------------------------------------------
# 7. Next steps
# ---------------------------------------------------------------------------

cat <<EOF

[bootstrap] done. Quick verification:

  systemctl --user status jarvis-api
  systemctl --user status jarvis-sentinel
  tail -f ~/.local/share/jarvis/logs/sentinel.log

To enable the web dashboard:
  bash scripts/install-services.sh --units dashboard

To enable voice (after editing ~/.config/jarvis/env with VOICE_ENABLED=true):
  bash scripts/install-services.sh --units voice

Once your dual 3090s are running:
  # vLLM (Qwen 2.5 72B AWQ across both cards):
  $VENV_PY -m pip install vllm
  bash scripts/install-services.sh --units vllm
  export JARVIS_LLM_BACKEND=vllm   # in ~/.config/jarvis/env

  # Ollama for sidecar models:
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5:7b
  bash scripts/install-services.sh --units ollama
  export JARVIS_LLM_BACKEND_SENTINEL=ollama

See docs/JARVIS_2026_ROADMAP.md for the full migration sequence.
EOF
