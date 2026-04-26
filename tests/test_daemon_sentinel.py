"""Sentinel scheduler wiring — verifies all 6 jobs register w/ correct triggers."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from jarvis.daemon.sentinel import build_scheduler


def test_build_scheduler_registers_all_jobs():
    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    job_ids = {j.id for j in sched.get_jobs()}
    assert {"email", "calendar", "atlas", "news", "morning", "evening"} <= job_ids


def test_intervals_are_configured():
    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    by_id = {j.id: j for j in sched.get_jobs()}
    # IntervalTrigger exposes interval as timedelta
    assert by_id["email"].trigger.interval.total_seconds() == 15 * 60
    assert by_id["atlas"].trigger.interval.total_seconds() == 5 * 60
    assert by_id["news"].trigger.interval.total_seconds() == 30 * 60


def test_morning_digest_is_cron_at_8am():
    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    by_id = {j.id: j for j in sched.get_jobs()}
    morning = by_id["morning"]
    fields = {f.name: str(f) for f in morning.trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "0"
