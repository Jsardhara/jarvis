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
        return self._search_imap(["UNSEEN"], max_results, force_unread_label=True)

    def list_recent(self, max_results: int = 25) -> list[dict]:
        return self._search_imap(["ALL"], max_results, force_unread_label=False)

    def search_mail(self, query: str, max_results: int = 25) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        # IMAP TEXT covers headers + body; quote to preserve spaces.
        criteria = ["TEXT", f'"{q}"']
        return self._search_imap(criteria, max_results, force_unread_label=False)

    def _search_imap(
        self,
        criteria: list[str],
        max_results: int,
        *,
        force_unread_label: bool,
    ) -> list[dict]:
        with self._imap() as c:
            typ, data = c.search(None, *criteria)
            if typ != "OK" or not data or not data[0]:
                return []
            ids = data[0].split()[-max_results:]
            messages: list[dict] = []
            for mid in reversed(ids):
                typ, fetched = c.fetch(mid, "(BODY.PEEK[] FLAGS)")
                if typ != "OK":
                    continue
                raw = _extract_raw(fetched)
                flags = _extract_flags(fetched)
                msg = email.message_from_bytes(raw)
                mapped = _map_message(msg, mid.decode(), self._config.label)
                if not force_unread_label:
                    is_unread = b"\\Seen" not in flags
                    labels = [lbl for lbl in mapped.get("labels", []) if lbl != "UNREAD"]
                    if is_unread:
                        labels = ["UNREAD"] + labels
                    mapped["labels"] = labels
                messages.append(mapped)
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


def _extract_flags(fetched: list) -> bytes:
    """Pull FLAGS bytes from imaplib's fetch response, or b'' if absent."""
    for part in fetched:
        if isinstance(part, tuple) and part and isinstance(part[0], bytes):
            head = part[0]
            if b"FLAGS" in head:
                return head
        elif isinstance(part, bytes) and b"FLAGS" in part:
            return part
    return b""


def _map_message(msg: email.message.Message, mid: str, label: str) -> dict:
    snippet = _extract_body(msg, max_chars=200)
    subject = _decode_header_value(msg.get("Subject", ""))
    from_ = _decode_header_value(msg.get("From", ""))
    to_ = _decode_header_value(msg.get("To", ""))
    delivered_to = _decode_header_value(msg.get("Delivered-To", ""))
    forward_for = _decode_header_value(msg.get("X-Forwarded-For", ""))
    labels = ["UNREAD", "INBOX", label]
    forwarded_from = _detect_forward_origin(to_, delivered_to, forward_for)
    if forwarded_from:
        labels.append(forwarded_from)
    return {
        "id": mid,
        "from": from_,
        "to": to_,
        "subject": subject,
        "snippet": snippet,
        "labels": labels,
        "forwarded_from": forwarded_from,
        "date": _parse_message_date(msg.get("Date", "")),
    }


def _parse_message_date(raw: Any) -> str:
    """Parse RFC 2822 Date header → UTC ISO 8601. Empty string on failure."""
    from email.utils import parsedate_to_datetime

    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return ""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _decode_header_value(raw: Any) -> str:
    """Decode RFC 2047 encoded headers (=?UTF-8?q?...?=)."""
    from email.header import decode_header, make_header

    if not raw:
        return ""
    try:
        return str(make_header(decode_header(str(raw))))
    except Exception:
        return str(raw)


def _detect_forward_origin(to: str, delivered_to: str, forward_for: str) -> str | None:
    """Return a label like 'DREXEL_FORWARD' when this Gmail message arrived
    via auto-forward from a recognized school/work mailbox.
    """
    import os

    domain = os.getenv("DREXEL_FORWARD_DOMAIN", "drexel.edu").lower()
    haystack = " ".join([to, delivered_to, forward_for]).lower()
    if domain and domain in haystack:
        return "DREXEL_FORWARD"
    return None


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
