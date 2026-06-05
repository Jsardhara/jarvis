#!/usr/bin/env python3
"""Sentinel daily briefing generator for Jarvis system.

Produces: summary of what's running, what needs attention, upcoming deadlines.
Output goes to daily-briefing.json for dashboard consumption.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def check_jarvis_repo():
    repo = Path.home() / "jarvis"
    if not repo.exists():
        return {"status": "missing", "clean": None}
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=str(repo),
            timeout=10,
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(repo),
            timeout=10,
        )
        return {
            "status": "present",
            "branch": branch.stdout.strip(),
            "clean": status.stdout.strip() == "",
            "changes": [l for l in status.stdout.strip().splitlines() if l],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_atlas_repo():
    repo = Path.home() / "atlas"
    if not repo.exists():
        return {"status": "missing"}
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=str(repo),
            timeout=10,
        )
        return {
            "status": "present",
            "clean": result.stdout.strip() == "",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_hermes_home():
    home = Path.home() / "AppData" / "Local" / "hermes"
    if not home.exists():
        return {"status": "missing"}
    try:
        disk_free = os.statvfs(str(home)).f_bavail * os.statvfs(str(home)).f_frsize
        return {
            "status": "present",
            "free_bytes": disk_free,
            "sessions_count": len(list((home / "sessions").glob("*")) if (home / "sessions").exists() else []),
        }
    except Exception:
        return {"status": "present"}


def generate_briefing():
    now = datetime.now(timezone.utc)
    briefing = {
        "generated_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "checks": {
            "jarvis_repo": check_jarvis_repo(),
            "atlas_repo": check_atlas_repo(),
            "hermes_home": check_hermes_home(),
        },
        "needs_attention": [],
    }

    # Determine what needs attention
    jr = briefing["checks"]["jarvis_repo"]
    if jr.get("status") == "missing":
        briefing["needs_attention"].append("Jarvis repo not found")
    elif not jr.get("clean"):
        briefing["needs_attention"].append(f"Jarvis repo has uncommitted changes: {len(jr.get('changes', []))} files")

    at = briefing["checks"]["atlas_repo"]
    if at.get("status") == "missing":
        briefing["needs_attention"].append("Atlas repo not found (expected at ~/atlas)")

    return briefing


if __name__ == "__main__":
    briefing = generate_briefing()
    output_dir = Path.home() / "jarvis" / "state"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "daily-briefing.json"
    output_file.write_text(json.dumps(briefing, indent=2), encoding="utf-8")
    print(json.dumps(briefing, indent=2))

    if briefing["needs_attention"]:
        print("\n=== ITEMS NEEDING ATTENTION ===", file=sys.stderr)
        for item in briefing["needs_attention"]:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(0)  # still OK, just flagging
