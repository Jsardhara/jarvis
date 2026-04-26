"""Twilio SMS bridge — webhook receive + send."""
from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings


class TwilioBridge:
    surface = "sms"
    URL_TEMPLATE = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self, account_sid: str | None = None, auth_token: str | None = None,
                 from_number: str | None = None, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.account_sid = account_sid or s.twilio_account_sid
        self.auth_token = auth_token or s.twilio_auth_token
        self.from_number = from_number or s.twilio_phone
        self._client = httpx.Client(timeout=5.0, transport=transport)

    def send(self, channel: str, body: str) -> dict[str, Any]:
        """channel = destination phone number in E.164 format."""
        if not (self.account_sid and self.auth_token and self.from_number):
            return {"ok": False, "error": "missing_credentials"}
        r = self._client.post(
            self.URL_TEMPLATE.format(sid=self.account_sid),
            data={"From": self.from_number, "To": channel, "Body": body},
            auth=(self.account_sid, self.auth_token),
        )
        return {"ok": r.status_code in (200, 201), "status": r.status_code,
                "sid": r.json().get("sid") if r.content else None}


def parse_twilio_form(form: dict) -> dict:
    """Normalize Twilio's form-encoded inbound webhook to our message dict."""
    return {
        "surface": "sms",
        "channel": form.get("From"),
        "channel_type": "dm",
        "user": form.get("From"),
        "text": form.get("Body", ""),
        "ts": form.get("MessageSid"),
    }
