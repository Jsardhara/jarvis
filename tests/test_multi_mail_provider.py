"""Tests for MultiMailProvider — pure routing logic, no network."""
from __future__ import annotations

import pytest

from jarvis.subsystems.multi_mail_provider import MailAccount, MultiMailProvider


class _FakeBackend:
    def __init__(self, label: str, unread: list[dict] | None = None):
        self.label = label
        self._unread = unread or []
        self.calls: list[tuple] = []

    def list_unread(self, max_results: int = 25) -> list[dict]:
        self.calls.append(("list_unread", max_results))
        return [dict(item) for item in self._unread[:max_results]]

    def get_message(self, msg_id: str) -> dict:
        self.calls.append(("get_message", msg_id))
        return {"id": msg_id, "from": f"{self.label}@x", "subject": "s", "snippet": "b", "labels": [self.label]}

    def draft_reply(self, msg_id: str, body: str) -> dict:
        self.calls.append(("draft_reply", msg_id, body))
        return {"draft_id": "d1", "in_reply_to": msg_id, "body": body, "label": self.label}

    def send(self, to: str, subject: str, body: str) -> dict:
        self.calls.append(("send", to, subject, body))
        return {"id": f"sent-{self.label}", "to": to, "subject": subject, "body": body, "ts": "now", "label": self.label}


def _make(gmail_unread=None, drexel_unread=None) -> tuple[MultiMailProvider, _FakeBackend, _FakeBackend]:
    g = _FakeBackend("GMAIL", gmail_unread or [])
    d = _FakeBackend("DREXEL", drexel_unread or [])
    multi = MultiMailProvider.from_backends(gmail=g, drexel=d, default="GMAIL")
    return multi, g, d


def test_requires_at_least_one_account():
    with pytest.raises(ValueError):
        MultiMailProvider(accounts=[], default_label="GMAIL")


def test_duplicate_labels_rejected():
    g1 = _FakeBackend("GMAIL")
    g2 = _FakeBackend("GMAIL")
    with pytest.raises(ValueError):
        MultiMailProvider(
            accounts=[MailAccount("GMAIL", g1), MailAccount("GMAIL", g2)],
            default_label="GMAIL",
        )


def test_default_label_must_exist():
    g = _FakeBackend("GMAIL")
    with pytest.raises(ValueError):
        MultiMailProvider(
            accounts=[MailAccount("GMAIL", g)],
            default_label="DREXEL",
        )


def test_list_unread_merges_and_prefixes_ids():
    multi, g, d = _make(
        gmail_unread=[{"id": "1", "subject": "g", "labels": ["UNREAD"]}],
        drexel_unread=[{"id": "7", "subject": "d", "labels": ["UNREAD"]}],
    )
    items = multi.list_unread(max_results=10)
    ids = sorted(item["id"] for item in items)
    assert ids == ["DREXEL:7", "GMAIL:1"]
    accounts = sorted(item["account"] for item in items)
    assert accounts == ["DREXEL", "GMAIL"]


def test_get_message_routes_by_prefix():
    multi, g, d = _make()
    res = multi.get_message("DREXEL:42")
    assert res["account"] == "DREXEL"
    assert res["id"] == "DREXEL:42"
    assert ("get_message", "42") in d.calls
    assert g.calls == []


def test_get_message_unknown_prefix_raises():
    multi, _, _ = _make()
    with pytest.raises(KeyError):
        multi.get_message("UNKNOWN:1")


def test_draft_reply_routes_by_prefix():
    multi, g, d = _make()
    res = multi.draft_reply("GMAIL:5", "hi")
    assert res["account"] == "GMAIL"
    assert res["in_reply_to"] == "GMAIL:5"
    assert ("draft_reply", "5", "hi") in g.calls


def test_send_routes_drexel_recipient_to_drexel():
    multi, g, d = _make()
    res = multi.send("prof@drexel.edu", "Q", "body")
    assert res["account"] == "DREXEL"
    assert g.calls == []


def test_send_routes_gmail_default_for_unknown_domain():
    multi, g, d = _make()
    res = multi.send("friend@example.com", "Q", "body")
    assert res["account"] == "GMAIL"


def test_send_routes_gmail_for_gmail_recipient():
    multi, g, d = _make()
    res = multi.send("foo@gmail.com", "Q", "body")
    assert res["account"] == "GMAIL"


def test_list_unread_skips_failing_account():
    class _Broken(_FakeBackend):
        def list_unread(self, max_results: int = 25):
            raise RuntimeError("imap down")

    g = _FakeBackend("GMAIL", [{"id": "1", "subject": "ok"}])
    broken = _Broken("DREXEL")
    multi = MultiMailProvider.from_backends(gmail=g, drexel=broken, default="GMAIL")
    items = multi.list_unread(10)
    assert len(items) == 1
    assert items[0]["account"] == "GMAIL"


def test_labels_property():
    multi, _, _ = _make()
    assert sorted(multi.labels) == ["DREXEL", "GMAIL"]


def test_only_gmail_when_drexel_absent():
    g = _FakeBackend("GMAIL", [{"id": "1", "subject": "ok"}])
    multi = MultiMailProvider.from_backends(gmail=g, drexel=None, default="GMAIL")
    assert multi.labels == ["GMAIL"]
    res = multi.send("anyone@drexel.edu", "Q", "B")
    assert res["account"] == "GMAIL"  # falls back to default since DREXEL absent
