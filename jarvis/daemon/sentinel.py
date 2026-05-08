"""Sentinel — APScheduler-driven daemon.

Run:
    python -m jarvis.daemon.sentinel

Schedules cron routines that watch inbox/calendar/atlas/news/school,
write to state/inbox.jsonl, and push alerts via Notifier.

Sentinel is infrastructure, not an agent — it drives the six top-level
agents (tempo, atlas, lens, scholar, forge) on a schedule.
"""
from __future__ import annotations

import logging
import os
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from ..subsystems.atlas import AtlasBridge, AtlasOrchestrator
from ..subsystems.lens import Lens
from ..subsystems.providers import MockOutlook, MockSearch
from ..subsystems.registry import build_default_registry
from ..subsystems.scholar import Scholar
from ..subsystems.tempo import Tempo
from ..triggers import scan_periodic
from .mission_control_bridge import sync_tick as mission_control_sync_tick
from .notifier import default_notifier
from .routines import (
    atlas_daily_rollup,
    atlas_tick,
    calendar_tick,
    daily_forge_tick,
    email_tick,
    heartbeat_tick,
    morning_digest,
    news_tick,
    scholar_tick,
)
from .voice_context_tick import voice_context_tick

log = logging.getLogger("sentinel")


def _build_subsystems():
    """Mocks until creds wired. Swap MockOutlook → OutlookProvider once Azure app reg lands."""
    tempo = Tempo(MockOutlook())
    atlas = AtlasOrchestrator(bridge=AtlasBridge(), allow_mock=True)
    lens = Lens(MockSearch())
    scholar = Scholar()
    return tempo, atlas, lens, scholar


def _triggers_tick(reg: dict) -> None:
    """Periodic job: run all polling-style trigger rules and emit InboxEvents."""
    try:
        fired = scan_periodic(reg)
        if fired:
            log.info("triggers_tick: %d trigger(s) fired", len(fired))
    except Exception:
        log.warning("triggers_tick failed", exc_info=True)


# Module-level state for Atlas health tracking (last known status)
_atlas_health_last: dict = {"healthy": None}


def atlas_health_tick(atlas_api_url: str) -> dict:
    """Check Atlas /system/health every 60s; push notification on 200↔503 transitions."""
    import httpx

    from ..contract import InboxEvent
    from ..state import append_inbox

    was_healthy = _atlas_health_last.get("healthy")
    try:
        resp = httpx.get(f"{atlas_api_url}/system/health", timeout=3.0)
        is_healthy = resp.status_code == 200
    except Exception:
        is_healthy = False

    transitioned = was_healthy is not None and was_healthy != is_healthy
    if transitioned:
        if not is_healthy:
            summary = "Atlas degraded — check agents"
            severity = "alert"
        else:
            summary = "Atlas recovered"
            severity = "info"
        append_inbox(InboxEvent(agent="sentinel", severity=severity, summary=summary))
        log.warning("atlas_health_tick: %s", summary)

    _atlas_health_last["healthy"] = is_healthy
    return {"healthy": is_healthy, "transitioned": transitioned}


def build_scheduler(scheduler: BlockingScheduler | None = None) -> BlockingScheduler:
    tempo, atlas, lens, scholar = _build_subsystems()
    notifier = default_notifier()
    watchlist = [t.strip() for t in os.environ.get("JARVIS_WATCHLIST", "BTC,ETH").split(",") if t.strip()]
    reg = build_default_registry()

    sched = scheduler or BlockingScheduler(timezone="UTC")

    sched.add_job(email_tick, "interval", minutes=15, args=[tempo, notifier], id="email")
    sched.add_job(calendar_tick, "interval", hours=1, args=[tempo, notifier], id="calendar")
    sched.add_job(atlas_tick, "interval", minutes=5, args=[atlas, notifier], id="atlas")
    sched.add_job(news_tick, "interval", minutes=30, args=[lens, watchlist, notifier], id="news")
    sched.add_job(scholar_tick, "interval", hours=2, args=[scholar, notifier], id="scholar")
    sched.add_job(morning_digest, "cron", hour=8, minute=0,
                  args=[reg, notifier], id="morning")
    sched.add_job(morning_digest, "cron", hour=18, minute=0,
                  args=[reg, notifier], id="evening")
    sched.add_job(atlas_daily_rollup, "cron", hour=22, minute=0,
                  args=[atlas, notifier], id="atlas_rollup")
    sched.add_job(heartbeat_tick, "interval", seconds=60, args=[sched, notifier], id="heartbeat")
    sched.add_job(mission_control_sync_tick, "interval", seconds=30, id="mc_sync")
    sched.add_job(_triggers_tick, "interval", minutes=30, args=[reg], id="triggers")
    # Voice fact sheet refresh — feeds the cheap voice handler with current
    # pnl / mail counts / next event so quick queries skip subsystem fan-out.
    sched.add_job(voice_context_tick, "interval", minutes=5, id="voice_context")
    atlas_api_url = os.environ.get("JARVIS_ATLAS_API", "http://localhost:8000")
    sched.add_job(
        atlas_health_tick, "interval", seconds=60, args=[atlas_api_url], id="atlas_health"
    )
    # Daily autonomous Forge — picks news story, builds MVP, pushes to GitHub
    sched.add_job(
        daily_forge_tick,
        "cron",
        hour=10,  # 10:00 UTC == 06:00 ET (EDT-aware via misfire_grace)
        minute=0,
        args=[reg, notifier],
        id="daily_forge",
        max_instances=1,
        misfire_grace_time=3600,
    )

    return sched


def main() -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sched = build_scheduler()

    def _shutdown(signum, frame):
        log.info("shutting down…")
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("sentinel started — %d jobs scheduled", len(sched.get_jobs()))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
