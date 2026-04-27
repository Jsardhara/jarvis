"""Tests for DrexelOAuthProvider — mock MSAL + IMAP + SMTP."""
from __future__ import annotations

from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

from jarvis.subsystems.drexel_oauth_provider import (
    DrexelConfig,
    DrexelOAuthError,
    DrexelOAuthProvider,
    _xoauth2_sasl,
)


def _make_msg(subject: str = "S", body: str = "B") -> bytes:
    m = EmailMessage()
    m["From"] = "prof@drexel.edu"
    m["Subject"] = subject
    m.set_content(body)
    return bytes(m)


class _FakeIMAP:
    def __init__(self, messages: dict[bytes, bytes]):
        self.messages = messages

    def select(self, mailbox):
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        return ("OK", [b" ".join(self.messages.keys())])

    def fetch(self, mid, parts):
        return ("OK", [(b"hdr", self.messages.get(mid, b""))])

    def close(self):
        pass

    def logout(self):
        pass


class _FakeSMTP:
    def __init__(self):
        self.sent = []

    def send_message(self, msg):
        self.sent.append(msg)

    def quit(self):
        pass


@pytest.fixture
def cfg(tmp_path):
    return DrexelConfig(
        address="me@drexel.edu",
        client_id="fake-client-id",
        cache_path=tmp_path / "cache.json",
    )


def test_xoauth2_sasl_format():
    sasl = _xoauth2_sasl("u@d.com", "TOKEN")
    assert sasl == b"user=u@d.com\x01auth=Bearer TOKEN\x01\x01"


def test_acquire_token_uses_silent_when_account_present(cfg):
    msal_mock = MagicMock()
    msal_mock.token_cache.has_state_changed = False
    msal_mock.get_accounts.return_value = [{"username": "me@drexel.edu"}]
    msal_mock.acquire_token_silent.return_value = {"access_token": "silent-tok"}
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    tok = p._acquire_token()
    assert tok == "silent-tok"
    msal_mock.initiate_device_flow.assert_not_called()


def test_acquire_token_falls_back_to_device_flow(cfg, capsys):
    msal_mock = MagicMock()
    msal_mock.token_cache.has_state_changed = True
    msal_mock.token_cache.serialize.return_value = '{"refresh":"x"}'
    msal_mock.get_accounts.return_value = []
    msal_mock.acquire_token_silent.return_value = None
    msal_mock.initiate_device_flow.return_value = {
        "user_code": "ABC",
        "message": "Visit https://microsoft.com/devicelogin and enter ABC",
    }
    msal_mock.acquire_token_by_device_flow.return_value = {"access_token": "dev-tok"}
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    tok = p._acquire_token()
    assert tok == "dev-tok"
    out = capsys.readouterr().out
    assert "ABC" in out
    assert "dev-tok" not in out  # token never printed


def test_acquire_token_failure_raises(cfg):
    msal_mock = MagicMock()
    msal_mock.get_accounts.return_value = []
    msal_mock.acquire_token_silent.return_value = None
    msal_mock.initiate_device_flow.return_value = {"error": "down"}
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    with pytest.raises(DrexelOAuthError):
        p._acquire_token()


def test_acquire_token_device_flow_no_token_raises(cfg):
    msal_mock = MagicMock()
    msal_mock.get_accounts.return_value = []
    msal_mock.acquire_token_silent.return_value = None
    msal_mock.initiate_device_flow.return_value = {"user_code": "X", "message": "go"}
    msal_mock.acquire_token_by_device_flow.return_value = {"error": "denied"}
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    with pytest.raises(DrexelOAuthError):
        p._acquire_token()


def test_list_unread_via_injected_imap(cfg):
    msgs = {b"7": _make_msg("Final exam reminder", "Body")}
    fake = _FakeIMAP(msgs)
    p = DrexelOAuthProvider(cfg, imap_factory=lambda: fake)
    items = p.list_unread()
    assert len(items) == 1
    assert "DREXEL" in items[0]["labels"]


def test_send_via_injected_smtp(cfg):
    smtp = _FakeSMTP()
    p = DrexelOAuthProvider(cfg, smtp_factory=lambda: smtp)
    res = p.send("ta@drexel.edu", "Q", "Body")
    assert res["account"] if "account" in res else res["label"] == "DREXEL"
    assert smtp.sent[0]["To"] == "ta@drexel.edu"


def test_draft_reply_returns_envelope(cfg):
    p = DrexelOAuthProvider(cfg, imap_factory=lambda: _FakeIMAP({}))
    res = p.draft_reply("DREXEL-9", "ack")
    assert res["in_reply_to"] == "DREXEL-9"
    assert res["body"] == "ack"
    assert res["label"] == "DREXEL"


def test_persist_cache_writes_when_state_changed(cfg):
    msal_mock = MagicMock()
    cache = MagicMock()
    cache.has_state_changed = True
    cache.serialize.return_value = '{"k":"v"}'
    msal_mock.token_cache = cache
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    p._persist_cache(msal_mock)
    assert cfg.cache_path.exists()
    assert cfg.cache_path.read_text(encoding="utf-8") == '{"k":"v"}'


def test_persist_cache_skips_when_unchanged(cfg):
    msal_mock = MagicMock()
    cache = MagicMock()
    cache.has_state_changed = False
    msal_mock.token_cache = cache
    p = DrexelOAuthProvider(cfg, msal_app=msal_mock)
    p._persist_cache(msal_mock)
    assert not cfg.cache_path.exists()
