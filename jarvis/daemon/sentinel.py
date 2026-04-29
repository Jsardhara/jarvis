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
    atlas_tick,
    calendar_tick,
    email_tick,
    heartbeat_tick,
    morning_digest,
    news_tick,
    scholar_tick,
)

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
    sched.add_job(heartbeat_tick, "interval", seconds=60, args=[sched, notifier], id="heartbeat")
    sched.add_job(mission_control_sync_tick, "interval", seconds=30, id="mc_sync")
    sched.add_job(_triggers_tick, "interval", minutes=30, args=[reg], id="triggers")

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
