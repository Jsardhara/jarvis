"""Multi-account mail provider — fans out across Gmail + Drexel.

Each upstream provider returns its own integer UIDs which collide across
accounts. We compose-ID them with the provider's label prefix:

    "GMAIL:123"
    "DREXEL:7"

`get_message`, `draft_reply` route by the prefix. `list_unread` merges and
prepends prefixes. `send` routes by recipient domain — drexel.edu → Drexel
SMTP, anything else → Gmail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class _MailBackend(Protocol):
    def list_unread(self, max_results: int = 25) -> list[dict]: ...
    def get_message(self, msg_id: str) -> dict: ...
    def draft_reply(self, msg_id: str, body: str) -> dict: ...
    def send(self, to: str, subject: str, body: str) -> dict: ...


@dataclass(frozen=True)
class _Account:
    label: str
    backend: _MailBackend
    domain: str | None = None  # for send routing; None → never default-routed


class MultiMailProvider:
    """Composes multiple mail backends behind the OutlookProvider mail subset."""

    def __init__(
        self,
        accounts: list[_Account],
        default_label: str,
    ):
        if not accounts:
            raise ValueError("MultiMailProvider needs at least one account")
        labels = [a.label for a in accounts]
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate account labels: {labels}")
        if default_label not in labels:
            raise ValueError(f"default_label {default_label!r} not in accounts {labels}")
        self._accounts = {a.label: a for a in accounts}
        self._default_label = default_label

    @classmethod
    def from_backends(
        cls,
        gmail: _MailBackend | None,
        drexel: _MailBackend | None,
        default: str = "GMAIL",
    ) -> MultiMailProvider:
        accounts: list[_Account] = []
        if gmail is not None:
            accounts.append(_Account(label="GMAIL", backend=gmail, domain="gmail.com"))
        if drexel is not None:
            accounts.append(_Account(label="DREXEL", backend=drexel, domain="drexel.edu"))
        return cls(accounts=accounts, default_label=default)

    # ---------- routing helpers ----------

    @staticmethod
    def _split(prefixed_id: str) -> tuple[str, str]:
        if ":" not in prefixed_id:
            return ("", prefixed_id)
        label, _, raw = prefixed_id.partition(":")
        return label, raw

    def _route_by_id(self, prefixed_id: str) -> tuple[_Account, str]:
        label, raw = self._split(prefixed_id)
        if label not in self._accounts:
            raise KeyError(f"unknown account label in id {prefixed_id!r}")
        return self._accounts[label], raw

    def _route_by_recipient(self, to: str) -> _Account:
        domain = to.rsplit("@", 1)[-1].lower() if "@" in to else ""
        for acc in self._accounts.values():
            if acc.domain and acc.domain == domain:
                return acc
        return self._accounts[self._default_label]

    # ---------- mail methods (Protocol subset) ----------

    def list_unread(self, max_results: int = 25) -> list[dict]:
        merged: list[dict] = []
        per_account = max(1, max_results // max(len(self._accounts), 1))
        for label, acc in self._accounts.items():
            try:
                items = acc.backend.list_unread(per_account)
            except Exception as exc:
                logger.warning("list_unread failed for %s: %s", label, exc)
                continue
            for item in items:
                merged.append({**item, "id": f"{label}:{item['id']}", "account": label})
        return merged[:max_results]

    def get_message(self, msg_id: str) -> dict:
        acc, raw = self._route_by_id(msg_id)
        result = acc.backend.get_message(raw)
        return {**result, "id": msg_id, "account": acc.label}

    def draft_reply(self, msg_id: str, body: str) -> dict:
        acc, raw = self._route_by_id(msg_id)
        result = acc.backend.draft_reply(raw, body)
        return {**result, "in_reply_to": msg_id, "account": acc.label}

    def send(self, to: str, subject: str, body: str) -> dict:
        acc = self._route_by_recipient(to)
        result = acc.backend.send(to, subject, body)
        return {**result, "account": acc.label}

    # ---------- introspection ----------

    @property
    def labels(self) -> list[str]:
        return list(self._accounts.keys())


# Public alias so tests / external composers can build accounts without
# touching the underscore-prefixed dataclass directly.
MailAccount = _Account
