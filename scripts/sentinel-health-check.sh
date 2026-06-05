#!/bin/bash
# Sentinel daily system health check
# Reports: disk usage, memory, uptime, Python venv status

echo "=== Sentinel System Health Check ==="
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Uptime (fallback for Windows)
 echo "--- Uptime ---"
 date +"Uptime not available on Windows"
 echo ""

# Disk usage
echo "--- Disk Usage ---"
df -h /c /d 2>/dev/null || df -h /
echo ""

# Memory (Linux/macOS compatible approach)
echo "--- Memory ---"
if command -v free >/dev/null 2>&1; then
    free -h
else
    echo "free command not available on this system"
fi
echo ""

# Python venvs status
echo "--- Python Environments ---"
echo "Python3: $(python3 --version 2>/dev/null || echo 'not found')"
echo "UV: $(uv --version 2>/dev/null || echo 'not found')"
echo "Node: $(node --version 2>/dev/null || echo 'not found')"
echo "Git: $(git --version 2>/dev/null || echo 'not found')"
echo ""

# Jarvis repo status
echo "--- Jarvis Repo ---"
[ -d "/c/Users/jyot2/jarvis" ] && (
    cd /c/Users/jyot2/jarvis
    echo "Branch: $(git branch --show-current 2>/dev/null)"
    echo "Status: $(git status --short 2>/dev/null | head -5)"
    [ -z "$(git status --short 2>/dev/null)" ] && echo "Clean -- no uncommitted changes"
) || echo "Jarvis repo not found"
echo ""

# Atlas read-only check
echo "--- Atlas ---"
[ -d "/c/Users/jyot2/atlas" ] && echo "Atlas repo: present (READ-ONLY)" || echo "Atlas repo: not found"
echo ""

echo "=== End Sentinel Report ==="
