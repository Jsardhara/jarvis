"""Discord bridge — webhook send. Bot/Gateway lives in a separate process (Phase 4.1)."""
from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings


class DiscordBridge:
    surface = "discord"
    URL_TEMPLATE = "https://discord.com/api/v10/channels/{channel_id}/messages"

    def __init__(self, bot_token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.bot_token = bot_token or get_settings().discord_bot_token
        self._client = httpx.Client(timeout=5.0, transport=transport)

    def send(self, channel: str, body: str) -> dict[str, Any]:
        if not self.bot_token:
            return {"ok": False, "error": "no_bot_token"}
        r = self._client.post(
            self.URL_TEMPLATE.format(channel_id=channel),
            json={"content": body},
            headers={"Authorization": f"Bot {self.bot_token}"},
        )
        return {"ok": r.status_code in (200, 201), "status": r.status_code, "body": r.json() if r.content else {}}
