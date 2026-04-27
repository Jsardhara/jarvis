"""Drexel (Office 365) IMAP/SMTP provider via OAuth2 device-code.

Microsoft disabled basic auth for Exchange Online in 2022; IMAP/SMTP still
work but require XOAUTH2. We acquire access tokens via MSAL's device-code
flow using a borrowed public client_id (Thunderbird's, by default) — no
Azure app registration needed on the operator side.

Scopes (Outlook IMAP/SMTP delegated):
    https://outlook.office.com/IMAP.AccessAsUser.All
    https://outlook.office.com/SMTP.Send
"""
from __future__ import annotations

import base64
import email
import imaplib
import logging
import smtplib
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.subsystems.gmail_imap_provider import _extract_body, _map_message

logger = logging.getLogger(__name__)

OUTLOOK_IMAP_HOST = "outlook.office365.com"
OUTLOOK_IMAP_PORT = 993
OUTLOOK_SMTP_HOST = "smtp.office365.com"
OUTLOOK_SMTP_PORT = 587
OUTLOOK_SCOPES = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
    "https://outlook.office.com/SMTP.Send",
]


class DrexelOAuthError(RuntimeError):
    """Raised when MSAL or IMAP/SMTP fails."""


@dataclass(frozen=True)
class DrexelConfig:
    address: str
    client_id: str
    tenant: str = "common"
    cache_path: Path | None = None
    label: str = "DREXEL"


def _xoauth2_sasl(user: str, access_token: str) -> bytes:
    """Build XOAUTH2 SASL initial response (RFC 4422 / Outlook docs)."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode()


class DrexelOAuthProvider:
    """OAuth-IMAP mail provider for Drexel/Office 365."""

    def __init__(
        self,
        config: DrexelConfig,
        msal_app: Any | None = None,  # injection seam
        imap_factory: Any | None = None,
        smtp_factory: Any | None = None,
    ):
        self._config = config
        self._msal_app = msal_app
        self._imap_factory = imap_factory
        self._smtp_factory = smtp_factory

    # ---------- token ----------

    def _build_msal_app(self) -> Any:
        if self._msal_app is not None:
            return self._msal_app
        import msal

        cache = msal.SerializableTokenCache()
        if self._config.cache_path and self._config.cache_path.exists():
            cache.deserialize(self._config.cache_path.read_text(encoding="utf-8"))
        self._msal_app = msal.PublicClientApplication(
            client_id=self._config.client_id,
            authority=f"https://login.microsoftonline.com/{self._config.tenant}",
            token_cache=cache,
        )
        return self._msal_app

    def _persist_cache(self, app: Any) -> None:
        cache = getattr(app, "token_cache", None)
        if cache is None or not getattr(cache, "has_state_changed", False):
            return
        path = self._config.cache_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cache.serialize(), encoding="utf-8")

    def _acquire_token(self) -> str:
        app = self._build_msal_app()
        accounts = app.get_accounts(username=self._config.address) or app.get_accounts()
        result: dict[str, Any] | None = None
        if accounts:
            result = app.acquire_token_silent(OUTLOOK_SCOPES, account=accounts[0])
        if not result:
            flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPES)
            if "user_code" not in flow:
                raise DrexelOAuthError(f"device flow init failed: {flow}")
            print(flow["message"])  # operator prompt — never logs the token  # noqa: T201
            result = app.acquire_token_by_device_flow(flow)
        if not result or "access_token" not in result:
            raise DrexelOAuthError(f"token acquisition failed: {result}")
        self._persist_cache(app)
        return result["access_token"]

    # ---------- factories ----------

    def _open_imap(self) -> imaplib.IMAP4_SSL:
        if self._imap_factory is not None:
            return self._imap_factory()
        token = self._acquire_token()
        c = imaplib.IMAP4_SSL(OUTLOOK_IMAP_HOST, OUTLOOK_IMAP_PORT)
        sasl = _xoauth2_sasl(self._config.address, token)
        c.authenticate("XOAUTH2", lambda _challenge: sasl)
        return c

    def _open_smtp(self) -> smtplib.SMTP:
        if self._smtp_factory is not None:
            return self._smtp_factory()
        token = self._acquire_token()
        s = smtplib.SMTP(OUTLOOK_SMTP_HOST, OUTLOOK_SMTP_PORT)
        s.starttls()
        sasl_b64 = base64.b64encode(_xoauth2_sasl(self._config.address, token)).decode()
        code, resp = s.docmd("AUTH", f"XOAUTH2 {sasl_b64}")
        if code != 235:
            raise DrexelOAuthError(f"SMTP XOAUTH2 auth failed: {code} {resp!r}")
        return s

    @contextmanager
    def _imap(self):
        client = self._open_imap()
        try:
            client.select("INBOX")
            yield client
        finally:
            with suppress(Exception):
                client.close()
            with suppress(Exception):
                client.logout()

    @contextmanager
    def _smtp(self):
        client = self._open_smtp()
        try:
            yield client
        finally:
            with suppress(Exception):
                client.quit()

    # ---------- mail methods (Protocol) ----------

    def list_unread(self, max_results: int = 25) -> list[dict]:
        with self._imap() as c:
            typ, data = c.search(None, "UNSEEN")
            if typ != "OK" or not data or not data[0]:
                return []
            ids = data[0].split()[-max_results:]
            messages: list[dict] = []
            for mid in reversed(ids):
                typ, fetched = c.fetch(mid, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT])")
                if typ != "OK":
                    continue
                raw = b""
                for part in fetched:
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw += part[1]
                msg = email.message_from_bytes(raw)
                messages.append(_map_message(msg, mid.decode(), self._config.label))
            return messages

    def get_message(self, msg_id: str) -> dict:
        with self._imap() as c:
            typ, fetched = c.fetch(msg_id.encode(), "(RFC822)")
            if typ != "OK":
                raise DrexelOAuthError(f"fetch failed for {msg_id}")
            raw = b""
            for part in fetched:
                if isinstance(part, tuple) and len(part) >= 2:
                    raw += part[1]
            msg = email.message_from_bytes(raw)
            mapped = _map_message(msg, msg_id, self._config.label)
            mapped["body"] = _extract_body(msg)
            return mapped

    def draft_reply(self, msg_id: str, body: str) -> dict:
        return {
            "draft_id": f"draft-{uuid4().hex[:8]}",
            "in_reply_to": msg_id,
            "body": body,
            "label": self._config.label,
        }

    def send(self, to: str, subject: str, body: str) -> dict:
        msg = EmailMessage()
        msg["From"] = self._config.address
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with self._smtp() as s:
            s.send_message(msg)
        return {
            "id": f"sent-{uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "ts": datetime.now(UTC).isoformat(),
            "label": self._config.label,
        }
