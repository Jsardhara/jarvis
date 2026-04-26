"""Sentinel — APScheduler-driven daemon.

Run:
    python -m jarvis.daemon.sentinel

Schedules cron routines that watch inbox/calendar/atlas/news, write to
state/inbox.jsonl, and push alerts via Notifier (Pushover or noop).

Stops cleanly on SIGINT.
"""
from __future__ import annotations

import logging
import os
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from ..subsystems.aide import Aide
from ..subsystems.chronos import Chronos
from ..subsystems.ledger import AtlasClient, Ledger
from ..subsystems.providers import MockCalendar, MockGmail
from ..subsystems.sherlock import MockSearch, Sherlock
from .notifier import default_notifier
from .routines import atlas_tick, calendar_tick, email_tick, morning_digest, news_tick

log = logging.getLogger("sentinel")


def _build_subsystems():
    """Phase 3 ships with mocks; swap to real MCP/HTTP providers in Phase 1.5/3.1."""
    aide = Aide(MockGmail())
    chronos = Chronos(MockCalendar())
    ledger = Ledger(client=AtlasClient(), allow_mock=True)
    sherlock = Sherlock(MockSearch())
    return aide, chronos, ledger, sherlock


def build_scheduler(scheduler: BlockingScheduler | None = None) -> BlockingScheduler:
    """Build a configured scheduler. Exposed for tests so they can use BackgroundScheduler."""
    aide, chronos, ledger, sherlock = _build_subsystems()
    notifier = default_notifier()
    watchlist = [t.strip() for t in os.environ.get("JARVIS_WATCHLIST", "BTC,ETH").split(",") if t.strip()]

    sched = scheduler or BlockingScheduler(timezone="UTC")

    sched.add_job(email_tick, "interval", minutes=15, args=[aide, notifier], id="email")
    sched.add_job(calendar_tick, "interval", hours=1, args=[chronos, notifier], id="calendar")
    sched.add_job(atlas_tick, "interval", minutes=5, args=[ledger, notifier], id="atlas")
    sched.add_job(news_tick, "interval", minutes=30, args=[sherlock, watchlist, notifier], id="news")
    sched.add_job(morning_digest, "cron", hour=8, minute=0,
                  args=[aide, chronos, ledger, notifier], id="morning")
    sched.add_job(morning_digest, "cron", hour=18, minute=0,
                  args=[aide, chronos, ledger, notifier], id="evening")

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
