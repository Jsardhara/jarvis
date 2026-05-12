"""TempoStack — composes calendar/tasks (iCloud) + mail (Gmail + Drexel).

Drop-in replacement for the OutlookProvider Protocol used by Tempo. All 11
methods proxy to the appropriate backend:

    Calendar / Tasks → ICloudProvider
    Mail             → MultiMailProvider (Gmail + Drexel)

Use ``build_default_tempo_stack()`` to construct from env vars; tests can
build directly with explicit backends.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TempoStack:
    """Composes calendar/tasks + mail behind the OutlookProvider Protocol."""

    calendar: Any  # ICloudProvider-shaped (7 methods)
    mail: Any      # MultiMailProvider-shaped (4 methods)

    # ---------- mail (delegates to MultiMailProvider) ----------

    def list_unread(self, max_results: int = 25) -> list[dict]:
        return self.mail.list_unread(max_results)

    def list_recent(self, max_results: int = 25) -> list[dict]:
        return self.mail.list_recent(max_results)

    def search_mail(self, query: str, max_results: int = 25) -> list[dict]:
        return self.mail.search_mail(query, max_results)

    def get_message(self, msg_id: str) -> dict:
        return self.mail.get_message(msg_id)

    def draft_reply(self, msg_id: str, body: str) -> dict:
        return self.mail.draft_reply(msg_id, body)

    def send(self, to: str, subject: str, body: str) -> dict:
        return self.mail.send(to, subject, body)

    # ---------- calendar (delegates to ICloudProvider) ----------

    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        return self.calendar.list_events(start_iso, end_iso)

    def create_event(
        self,
        summary: str,
        start_iso: str,
        end_iso: str,
        attendees: list[str],
    ) -> dict:
        return self.calendar.create_event(summary, start_iso, end_iso, attendees)

    def find_free(
        self,
        duration_min: int,
        window_start_iso: str,
        window_end_iso: str,
    ) -> list[dict]:
        return self.calendar.find_free(duration_min, window_start_iso, window_end_iso)

    def cancel_event(self, event_id: str) -> dict:
        return self.calendar.cancel_event(event_id)

    # ---------- tasks (delegates to ICloudProvider) ----------

    def list_tasks(self) -> list[dict]:
        return self.calendar.list_tasks()

    def add_task_remote(self, title: str, due: str | None) -> dict:
        return self.calendar.add_task_remote(title, due)

    def complete_task_remote(self, task_id: str) -> dict:
        return self.calendar.complete_task_remote(task_id)


def build_default_tempo_stack() -> TempoStack:
    """Construct from env vars. Raises if required vars missing.

    Required:
        APPLE_ID, APPLE_APP_PASSWORD
        GMAIL_ADDRESS, GMAIL_APP_PASSWORD

    Optional (Drexel — adds school mail if all present):
        DREXEL_ADDRESS, DREXEL_CLIENT_ID
    """
    from jarvis.agents.tempo.providers.gmail_imap import GmailConfig, GmailIMAPProvider
    from jarvis.agents.tempo.providers.icloud import ICloudConfig, ICloudProvider
    from jarvis.agents.tempo.providers.multi_mail import MultiMailProvider

    apple_id = _required("APPLE_ID")
    apple_pw = _required("APPLE_APP_PASSWORD")
    apple_url = os.getenv("APPLE_CALDAV_URL", "https://caldav.icloud.com")
    icloud = ICloudProvider(ICloudConfig(apple_id=apple_id, app_password=apple_pw, caldav_url=apple_url))

    gmail_addr = _required("GMAIL_ADDRESS")
    gmail_pw = _required("GMAIL_APP_PASSWORD")
    gmail = GmailIMAPProvider(GmailConfig(address=gmail_addr, app_password=gmail_pw))

    drexel: Any | None = None
    drexel_addr = os.getenv("DREXEL_ADDRESS")
    drexel_client_id = os.getenv("DREXEL_CLIENT_ID")
    if drexel_addr and drexel_client_id:
        from jarvis.agents.tempo.providers.drexel_oauth import DrexelConfig, DrexelOAuthProvider

        cache_path = Path(os.getenv("DREXEL_TOKEN_CACHE", "state/.drexel_msal_cache.json"))
        drexel = DrexelOAuthProvider(
            DrexelConfig(
                address=drexel_addr,
                client_id=drexel_client_id,
                tenant=os.getenv("DREXEL_TENANT", "common"),
                cache_path=cache_path,
                interactive=False,  # service path — auth via the CLI entrypoint
            )
        )

    multi = MultiMailProvider.from_backends(gmail=gmail, drexel=drexel, default="GMAIL")
    return TempoStack(calendar=icloud, mail=multi)


def _required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"TempoStack: required env var {key} not set")
    return val
