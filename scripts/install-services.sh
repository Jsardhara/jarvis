#!/usr/bin/env bash
# Install Jarvis user-level systemd units (Linux).
#
# Linux equivalent of scripts/install-services.ps1. Renders the templates
# under scripts/systemd/ with the local user's binary paths and writes them
# into ~/.config/systemd/user/.
#
# Usage:
#   bash scripts/install-services.sh                          # install all
#   bash scripts/install-services.sh --units api,sentinel     # subset
#   bash scripts/install-services.sh --uninstall              # remove
#   bash scripts/install-services.sh --print-only             # render to stdout
#
# Environment overrides (or set in your shell before running):
#   API_PORT       default 8765
#   WEB_PORT       default 3000
#   PYTHON_BIN     default `which python3`
#   PNPM_BIN       default `which pnpm`
#   VLLM_BIN       default `which vllm`
#   OLLAMA_BIN     default `which ollama`
#
# Idempotent — safe to re-run after editing a template or installing a
# missing binary.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/systemd"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

# Mapping: unit name -> template file. Order matters for ExecStart deps.
DEFAULT_UNITS=(api sentinel dashboard voice vllm ollama)

# ---------------------------------------------------------------------------
# Arg parse
# ---------------------------------------------------------------------------

ACTION="install"
UNITS=()
PRINT_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --units)
            IFS=',' read -r -a UNITS <<< "$2"
            shift 2
            ;;
        --uninstall)
            ACTION="uninstall"
            shift
            ;;
        --print-only)
            PRINT_ONLY=1
            shift
            ;;
        -h|--help)
            sed -n '/^# Usage:/,/^# Idempotent/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "[install-services] unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ${#UNITS[@]} -eq 0 ]]; then
    UNITS=("${DEFAULT_UNITS[@]}")
fi

# ---------------------------------------------------------------------------
# Resolve substitution values
# ---------------------------------------------------------------------------

JARVIS_ROOT="${JARVIS_ROOT:-$PROJECT_ROOT}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || echo /usr/bin/python3)}"
PNPM_BIN="${PNPM_BIN:-$(command -v pnpm || echo /usr/local/bin/pnpm)}"
VLLM_BIN="${VLLM_BIN:-$(command -v vllm || echo /usr/local/bin/vllm)}"
OLLAMA_BIN="${OLLAMA_BIN:-$(command -v ollama || echo /usr/local/bin/ollama)}"
API_PORT="${API_PORT:-8765}"
WEB_PORT="${WEB_PORT:-3000}"

render_template() {
    local template="$1"
    sed \
        -e "s|@JARVIS_ROOT@|$JARVIS_ROOT|g" \
        -e "s|@PYTHON@|$PYTHON_BIN|g" \
        -e "s|@PNPM@|$PNPM_BIN|g" \
        -e "s|@VLLM@|$VLLM_BIN|g" \
        -e "s|@OLLAMA@|$OLLAMA_BIN|g" \
        -e "s|@API_PORT@|$API_PORT|g" \
        -e "s|@WEB_PORT@|$WEB_PORT|g" \
        "$template"
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

uninstall() {
    echo "[install-services] uninstalling Jarvis units..."
    for unit in "${DEFAULT_UNITS[@]}"; do
        local name="jarvis-$unit.service"
        local target="$SYSTEMD_USER_DIR/$name"
        if systemctl --user is-active "$name" >/dev/null 2>&1; then
            systemctl --user stop "$name" || true
        fi
        if systemctl --user is-enabled "$name" >/dev/null 2>&1; then
            systemctl --user disable "$name" || true
        fi
        if [[ -f "$target" ]]; then
            rm -f "$target"
            echo "  removed $target"
        fi
    done
    systemctl --user daemon-reload
    echo "[install-services] done. State under ~/.local/share/jarvis/ is preserved."
}

print_only() {
    for unit in "${UNITS[@]}"; do
        local template="$TEMPLATE_DIR/jarvis-$unit.service.in"
        if [[ ! -f "$template" ]]; then
            echo "[install-services] no template for unit '$unit'" >&2
            continue
        fi
        echo "# === jarvis-$unit.service ==="
        render_template "$template"
        echo
    done
}

install() {
    echo "[install-services] installing into $SYSTEMD_USER_DIR"
    mkdir -p "$SYSTEMD_USER_DIR"
    mkdir -p "$HOME/.local/share/jarvis/logs"

    local installed=()
    for unit in "${UNITS[@]}"; do
        local template="$TEMPLATE_DIR/jarvis-$unit.service.in"
        local target="$SYSTEMD_USER_DIR/jarvis-$unit.service"
        if [[ ! -f "$template" ]]; then
            echo "  [skip] no template for unit '$unit'"
            continue
        fi
        render_template "$template" > "$target"
        installed+=("jarvis-$unit.service")
        echo "  wrote $target"
    done

    systemctl --user daemon-reload

    # Enable linger so units keep running after logout — matches the
    # Windows Startup folder convention.
    if command -v loginctl >/dev/null 2>&1; then
        loginctl enable-linger "$USER" 2>/dev/null || true
    fi

    for name in "${installed[@]}"; do
        systemctl --user enable --now "$name" 2>&1 | sed 's/^/    /'
    done

    echo
    echo "[install-services] done. Status:"
    for name in "${installed[@]}"; do
        local state
        state=$(systemctl --user is-active "$name" 2>/dev/null || echo "inactive")
        printf "  %-30s %s\n" "$name" "$state"
    done
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$ACTION" in
    uninstall)  uninstall ;;
    install)
        if [[ $PRINT_ONLY -eq 1 ]]; then
            print_only
        else
            install
        fi
        ;;
esac
