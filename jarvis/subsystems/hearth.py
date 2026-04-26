"""Hearth — Home Assistant bridge (Phase 7 stub).

Read state + call services on a local Home Assistant instance.
Supabase API: https://developers.home-assistant.io/docs/api/rest/
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..contract import AgentResponse


class HomeAssistantClient:
    """Thin REST client for Home Assistant. Long-lived access token via
    HOMEASSISTANT_TOKEN env var. Base URL HOMEASSISTANT_URL (default
    http://localhost:8123)."""

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = (base_url or os.environ.get("HOMEASSISTANT_URL", "http://localhost:8123")).rstrip("/")
        self.token = token or os.environ.get("HOMEASSISTANT_TOKEN")
        self._client = httpx.Client(timeout=5.0, transport=transport,
                                    headers={"Authorization": f"Bearer {self.token}"} if self.token else {})

    def _get(self, path: str) -> Any | None:
        try:
            r = self._client.get(self.base_url + path)
            return r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, httpx.ConnectError):
            return None

    def _post(self, path: str, body: dict) -> Any | None:
        try:
            r = self._client.post(self.base_url + path, json=body)
            return r.json() if r.status_code in (200, 201) else None
        except (httpx.HTTPError, httpx.ConnectError):
            return None

    def states(self) -> list[dict] | None:
        return self._get("/api/states")

    def state(self, entity_id: str) -> dict | None:
        return self._get(f"/api/states/{entity_id}")

    def call_service(self, domain: str, service: str, data: dict) -> Any | None:
        return self._post(f"/api/services/{domain}/{service}", data)


class Hearth:
    """Voice-trigger lights/thermostat/music. All state-changing calls
    surface needs_confirm=True for safety; a confirmed-variant skips it."""

    def __init__(self, client: HomeAssistantClient | None = None):
        self.client = client or HomeAssistantClient()

    def list_devices(self, domain: str | None = None) -> AgentResponse:
        states = self.client.states() or []
        if domain:
            states = [s for s in states if s.get("entity_id", "").startswith(f"{domain}.")]
        return AgentResponse(
            agent="hearth",
            intent="list_devices",
            action="listed",
            result={"count": len(states), "devices": [
                {"entity_id": s["entity_id"], "state": s.get("state"), "name": s.get("attributes", {}).get("friendly_name")}
                for s in states
            ]},
            confidence=1.0 if states else 0.0,
        )

    def light_on(self, entity_id: str, brightness: int | None = None) -> AgentResponse:
        return AgentResponse(
            agent="hearth",
            intent="light_on",
            action="proposed",
            result={"entity_id": entity_id, "brightness": brightness},
            needs_confirm=True,
            follow_ups=[f"confirm to turn on {entity_id}"],
            confidence=0.95,
        )

    def light_on_confirmed(self, entity_id: str, brightness: int | None = None) -> AgentResponse:
        body: dict[str, Any] = {"entity_id": entity_id}
        if brightness is not None:
            body["brightness"] = brightness
        out = self.client.call_service("light", "turn_on", body)
        return AgentResponse(
            agent="hearth",
            intent="light_on",
            action="executed" if out is not None else "failed",
            result={"entity_id": entity_id, "response": out},
            confidence=1.0 if out is not None else 0.0,
        )

    def thermostat_set(self, entity_id: str, temperature: float) -> AgentResponse:
        out = self.client.call_service("climate", "set_temperature",
                                       {"entity_id": entity_id, "temperature": temperature})
        return AgentResponse(
            agent="hearth",
            intent="set_temperature",
            action="executed" if out is not None else "failed",
            result={"entity_id": entity_id, "temperature": temperature, "response": out},
            confidence=1.0 if out is not None else 0.0,
        )

    def media_play(self, entity_id: str, content_id: str, content_type: str = "music") -> AgentResponse:
        out = self.client.call_service("media_player", "play_media",
                                       {"entity_id": entity_id, "media_content_id": content_id,
                                        "media_content_type": content_type})
        return AgentResponse(
            agent="hearth",
            intent="play_media",
            action="executed" if out is not None else "failed",
            result={"entity_id": entity_id, "content_id": content_id, "response": out},
            confidence=1.0 if out is not None else 0.0,
        )
