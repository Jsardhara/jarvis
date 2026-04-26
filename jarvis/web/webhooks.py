"""FastAPI webhook receivers for Slack/Discord/Twilio.

Run:
    uvicorn jarvis.web.webhooks:app --reload --port 8765

Each endpoint:
  - verifies signature (when applicable)
  - parses to our normalized message dict
  - hands to Echo for triage
  - appends an InboxEvent for the daemon
"""
from __future__ import annotations

import json
import logging
from typing import Any

try:
    from fastapi import FastAPI, Form, Header, HTTPException, Request
    from fastapi.responses import JSONResponse, PlainTextResponse
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

from ..bridges.slack import parse_event, verify_slack_signature
from ..bridges.twilio_sms import parse_twilio_form
from ..config import get_settings
from ..contract import InboxEvent
from ..state import append_inbox
from ..subsystems.echo import Echo

log = logging.getLogger(__name__)


def make_app(echo: Echo | None = None) -> FastAPI:  # pragma: no cover - thin wrapper
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi not installed — pip install jarvis[web]")
    echo = echo or Echo()
    app = FastAPI(title="Jarvis Webhooks", version="0.1.0")

    @app.post("/webhooks/slack")
    async def slack(request: Request,
                    x_slack_signature: str = Header(""),
                    x_slack_request_timestamp: str = Header("")):
        body = await request.body()
        secret = get_settings().slack_signing_secret or ""
        if secret and not verify_slack_signature(body, x_slack_request_timestamp,
                                                 x_slack_signature, secret):
            raise HTTPException(401, "bad signature")
        payload = json.loads(body)
        if payload.get("type") == "url_verification":
            return PlainTextResponse(payload.get("challenge", ""))
        msg = parse_event(payload)
        if msg:
            triage = echo.triage([msg])
            append_inbox(InboxEvent(agent="echo", severity="info",
                                    summary=f"slack msg from {msg['user']}",
                                    ref={"msg": msg, "triage": triage.result["counts"]}))
        return JSONResponse({"ok": True})

    @app.post("/webhooks/twilio")
    async def twilio(From: str = Form(""), Body: str = Form(""),
                     MessageSid: str = Form("")):
        msg = parse_twilio_form({"From": From, "Body": Body, "MessageSid": MessageSid})
        triage = echo.triage([msg])
        append_inbox(InboxEvent(agent="echo", severity="info",
                                summary=f"sms from {From}",
                                ref={"msg": msg, "triage": triage.result["counts"]}))
        return PlainTextResponse("<Response/>", media_type="application/xml")

    @app.post("/webhooks/discord")
    async def discord(request: Request):
        # Discord interactions need ed25519 verification when using slash commands;
        # for now accept the webhook and parse content
        payload = await request.json()
        msg = {
            "surface": "discord",
            "channel": payload.get("channel_id"),
            "channel_type": "channel",
            "user": (payload.get("author") or {}).get("id"),
            "text": payload.get("content", ""),
            "ts": payload.get("id"),
        }
        triage = echo.triage([msg])
        append_inbox(InboxEvent(agent="echo", severity="info",
                                summary="discord msg",
                                ref={"msg": msg, "triage": triage.result["counts"]}))
        return JSONResponse({"ok": True})

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "jarvis-webhooks"}

    return app


# Module-level app for `uvicorn jarvis.web.webhooks:app`
app = None  # populated by make_app at import-time when fastapi available
if HAS_FASTAPI:  # pragma: no cover
    app = make_app()
