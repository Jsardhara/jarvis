"""Hearth Home Assistant bridge tests."""
from __future__ import annotations

import httpx

from jarvis.subsystems.hearth import Hearth, HomeAssistantClient


def _transport(routes: dict[str, httpx.Response]):
    def handler(req: httpx.Request) -> httpx.Response:
        key = f"{req.method} {req.url.path}"
        return routes.get(key, httpx.Response(404))
    return httpx.MockTransport(handler)


def test_list_devices_empty():
    client = HomeAssistantClient("http://t", token="x", transport=_transport({}))
    h = Hearth(client)
    resp = h.list_devices()
    assert resp.result["count"] == 0
    assert resp.confidence == 0.0


def test_list_devices_filtered_by_domain():
    states = [
        {"entity_id": "light.lamp", "state": "off", "attributes": {"friendly_name": "Lamp"}},
        {"entity_id": "switch.fan", "state": "on", "attributes": {}},
    ]
    client = HomeAssistantClient("http://t", token="x",
                                 transport=_transport({"GET /api/states": httpx.Response(200, json=states)}))
    h = Hearth(client)
    resp = h.list_devices(domain="light")
    assert resp.result["count"] == 1
    assert resp.result["devices"][0]["entity_id"] == "light.lamp"


def test_light_on_proposes():
    h = Hearth(HomeAssistantClient("http://t", token="x", transport=_transport({})))
    resp = h.light_on("light.lamp", brightness=200)
    assert resp.needs_confirm is True
    assert resp.action == "proposed"
    assert resp.result["brightness"] == 200


def test_light_on_confirmed_executes():
    routes = {"POST /api/services/light/turn_on": httpx.Response(200, json=[])}
    client = HomeAssistantClient("http://t", token="x", transport=_transport(routes))
    h = Hearth(client)
    resp = h.light_on_confirmed("light.lamp")
    assert resp.action == "executed"
    assert resp.confidence == 1.0


def test_light_on_confirmed_fails_when_unreachable():
    h = Hearth(HomeAssistantClient("http://t", token="x", transport=_transport({})))
    resp = h.light_on_confirmed("light.lamp")
    assert resp.action == "failed"


def test_thermostat_set():
    routes = {"POST /api/services/climate/set_temperature": httpx.Response(200, json=[])}
    h = Hearth(HomeAssistantClient("http://t", token="x", transport=_transport(routes)))
    resp = h.thermostat_set("climate.living", 70.5)
    assert resp.action == "executed"


def test_media_play():
    routes = {"POST /api/services/media_player/play_media": httpx.Response(200, json=[])}
    h = Hearth(HomeAssistantClient("http://t", token="x", transport=_transport(routes)))
    resp = h.media_play("media_player.kitchen", "spotify://track/1")
    assert resp.action == "executed"


def test_state_endpoint():
    routes = {"GET /api/states/light.lamp": httpx.Response(200, json={"state": "on"})}
    client = HomeAssistantClient("http://t", token="x", transport=_transport(routes))
    assert client.state("light.lamp") == {"state": "on"}


def test_default_url_from_env(monkeypatch):
    monkeypatch.setenv("HOMEASSISTANT_URL", "http://homeassistant.local:8123")
    monkeypatch.setenv("HOMEASSISTANT_TOKEN", "tok")
    c = HomeAssistantClient()
    assert c.base_url == "http://homeassistant.local:8123"
    assert c.token == "tok"
