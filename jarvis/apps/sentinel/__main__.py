"""Sentinel daemon entrypoint.

Usage::

    python -m jarvis.apps.sentinel

Delegates to :func:`jarvis.apps.sentinel.scheduler.main` which builds the
APScheduler instance, wires the cron jobs (defined in
:mod:`jarvis.apps.sentinel.routines`), and blocks until SIGINT/SIGTERM.
"""
from __future__ import annotations

from jarvis.apps.sentinel.scheduler import main

if __name__ == "__main__":
    raise SystemExit(main())
