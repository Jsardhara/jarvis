"""Gmail IMAP/SMTP mail provider.

Implements the 4 mail methods of OutlookProvider Protocol against Gmail
using IMAP4_SSL + SMTP_SSL with an app-specific password (requires 2FA on
the Google account).

Calendar / tasks methods are intentionally absent — composed via TempoStack.
"""
from __future__ import annotations

import email
import imaplib
import logging
import smtplib
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class GmailIMAPError(RuntimeError):
    """Raised on IMAP/SMTP failure."""


@dataclass(frozen=True)
class GmailConfig:
    address: str
    app_password: str
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    label: str = "GMAIL"  # tag attached to messages so multi-mail can dedupe


class GmailIMAPProvider:
    """IMAP/SMTP-backed mail provider for Gmail."""

    def __init__(
        self,
        config: GmailConfig,
        imap_factory: Any | None = None,  # injection seam — returns IMAP4_SSL-like
        smtp_factory: Any | None = None,  # injection seam — returns SMTP_SSL-like
    ):
        self._config = config
        self._imap_factory = imap_factory or self._default_imap
        self._smtp_factory = smtp_factory or self._default_smtp

    # ---------- factory defaults ----------

    def _default_imap(self) -> imaplib.IMAP4_SSL:
        c = imaplib.IMAP4_SSL(self._config.imap_host, self._config.imap_port)
        c.login(self._config.address, self._config.app_password)
        return c

    def _default_smtp(self) -> smtplib.SMTP_SSL:
        s = smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port)
        s.login(self._config.address, self._config.app_password)
        return s

    @contextmanager
    def _imap(self):
        client = self._imap_factory()
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
        client = self._smtp_factory()
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
                typ, fetched = c.fetch(mid, "(BODY.PEEK[])")
                if typ != "OK":
                    continue
                raw = _extract_raw(fetched)
                msg = email.message_from_bytes(raw)
                messages.append(_map_message(msg, mid.decode(), self._config.label))
            return messages

    def get_message(self, msg_id: str) -> dict:
        with self._imap() as c:
            typ, fetched = c.fetch(msg_id.encode(), "(RFC822)")
            if typ != "OK":
                raise GmailIMAPError(f"fetch failed for {msg_id}")
            raw = _extract_raw(fetched)
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


# ---------- helpers ----------


def _extract_raw(fetched: list) -> bytes:
    """Pull the literal-message bytes out of imaplib's nested fetch tuple."""
    for part in fetched:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1]
    return b""


def _map_message(msg: email.message.Message, mid: str, label: str) -> dict:
    snippet = _extract_body(msg, max_chars=200)
    return {
        "id": mid,
        "from": str(msg.get("From", "")),
        "subject": str(msg.get("Subject", "")),
        "snippet": snippet,
        "labels": ["UNREAD", "INBOX", label],
    }


def _extract_body(msg: email.message.Message, max_chars: int = 0) -> str:
    """Return text/plain body; falls back to text/html stripped briefly."""
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get("Content-Disposition", "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                text = _decode_part(part)
                break
        if not text:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    text = _decode_part(part)
                    break
    else:
        text = _decode_part(msg)
    text = text.strip()
    return text[:max_chars] if max_chars else text


def _decode_part(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")
