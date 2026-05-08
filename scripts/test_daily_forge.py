"""Manual smoke test for daily_forge_tick.

Run anytime to test the full pipeline. Retries on rate limits (60s backoff,
up to 60 min) so it survives OAuth-pool throttling.

    python scripts/test_daily_forge.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure jarvis package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.daemon.notifier import default_notifier  # noqa: E402
from jarvis.daemon.routines import daily_forge_tick  # noqa: E402
from jarvis.subsystems.registry import build_default_registry  # noqa: E402

MAX_RETRIES = 60  # 60 attempts * 60s = 60 min worst case
BACKOFF_SEC = 60


def main() -> int:
    reg = build_default_registry()
    notifier = default_notifier()

    print("[forge-test] starting daily_forge_tick")
    for attempt in range(1, MAX_RETRIES + 1):
        result = daily_forge_tick(reg, notifier)
        status = result.get("status", "unknown")
        err = (result.get("rec") or {}).get("error") or result.get("error", "")

        print(f"[forge-test] attempt {attempt}: status={status}")
        if status == "success":
            rec = result.get("rec") or {}
            print(f"[forge-test] folder:       {rec.get('folder')}")
            print(f"[forge-test] commit:       {rec.get('commit_sha')}")
            print(f"[forge-test] cost_usd:     {rec.get('cost_usd')}")
            print(f"[forge-test] duration_sec: {rec.get('duration_sec')}")
            print(f"[forge-test] repo_url:     {rec.get('repo_url')}")
            return 0

        if status in ("skipped_budget", "skipped_no_news", "crashed"):
            print(f"[forge-test] terminal status — not retrying. err={err}")
            return 1

        if status == "failed" and "RateLimit" in err:
            if attempt < MAX_RETRIES:
                print(f"[forge-test] rate-limited, sleeping {BACKOFF_SEC}s …")
                time.sleep(BACKOFF_SEC)
                continue
            print("[forge-test] retries exhausted")
            return 1

        # Other failure — don't loop forever
        print(f"[forge-test] non-retryable failure: {err}")
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
