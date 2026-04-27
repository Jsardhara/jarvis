"""Tests for GmailIMAPProvider — mock IMAP4_SSL + SMTP_SSL."""
from __future__ import annotations

from email.message import EmailMessage

import pytest

from jarvis.subsystems.gmail_imap_provider import GmailConfig, GmailIMAPProvider


def _make_msg(subject: str, body: str, from_addr: str = "alice@example.com") -> bytes:
    m = EmailMessage()
    m["From"] = from_addr
    m["Subject"] = subject
    m.set_content(body)
    return bytes(m)


class _FakeIMAP:
    def __init__(self, messages: dict[bytes, bytes]):
        self.messages = messages
        self.calls: list[tuple] = []
        self.selected: str | None = None
        self.closed = False
        self.logged_out = False

    def select(self, mailbox: str):
        self.selected = mailbox
        self.calls.append(("select", mailbox))
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        self.calls.append(("search", criteria))
        ids = b" ".join(self.messages.keys())
        return ("OK", [ids])

    def fetch(self, mid: bytes, parts: str):
        self.calls.append(("fetch", mid, parts))
        body = self.messages.get(mid, b"")
        return ("OK", [(b"header", body)])

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True


class _FakeSMTP:
    def __init__(self):
        self.sent: list = []
        self.quit_called = False

    def send_message(self, msg):
        self.sent.append(msg)

    def quit(self):
        self.quit_called = True


@pytest.fixture
def cfg():
    return GmailConfig(address="me@gmail.com", app_password="pw")


def test_list_unread_maps_messages(cfg):
    msgs = {b"1": _make_msg("Hello", "Body of email")}
    fake = _FakeIMAP(msgs)
    p = GmailIMAPProvider(cfg, imap_factory=lambda: fake)
    out = p.list_unread(max_results=5)
    assert len(out) == 1
    assert out[0]["id"] == "1"
    assert out[0]["subject"] == "Hello"
    assert "GMAIL" in out[0]["labels"]
    assert "Body of email" in out[0]["snippet"]
    assert fake.selected == "INBOX"
    assert fake.closed and fake.logged_out


def test_list_unread_empty(cfg):
    fake = _FakeIMAP({})
    p = GmailIMAPProvider(cfg, imap_factory=lambda: fake)
    assert p.list_unread() == []


def test_get_message_returns_full_body(cfg):
    msgs = {b"99": _make_msg("S", "Full body content")}
    fake = _FakeIMAP(msgs)
    p = GmailIMAPProvider(cfg, imap_factory=lambda: fake)
    msg = p.get_message("99")
    assert msg["id"] == "99"
    assert "Full body content" in msg["body"]


def test_send_uses_smtp(cfg):
    smtp = _FakeSMTP()
    p = GmailIMAPProvider(cfg, smtp_factory=lambda: smtp)
    res = p.send("to@x.com", "Subj", "Body")
    assert res["to"] == "to@x.com"
    assert res["subject"] == "Subj"
    assert res["label"] == "GMAIL"
    assert res["id"].startswith("sent-")
    assert smtp.quit_called
    assert len(smtp.sent) == 1
    sent = smtp.sent[0]
    assert sent["From"] == "me@gmail.com"
    assert sent["To"] == "to@x.com"
    assert sent["Subject"] == "Subj"


def test_draft_reply_returns_envelope(cfg):
    p = GmailIMAPProvider(cfg, imap_factory=lambda: _FakeIMAP({}))
    res = p.draft_reply("42", "thanks")
    assert res["draft_id"].startswith("draft-")
    assert res["in_reply_to"] == "42"
    assert res["body"] == "thanks"
    assert res["label"] == "GMAIL"


def test_logout_runs_even_when_close_fails(cfg):
    class _Brittle(_FakeIMAP):
        def close(self):
            raise RuntimeError("close blew up")

    fake = _Brittle({})
    p = GmailIMAPProvider(cfg, imap_factory=lambda: fake)
    out = p.list_unread()
    assert out == []
    assert fake.logged_out
