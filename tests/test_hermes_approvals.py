"""Tests for Hermes-native approval policy and queue adapters."""
from __future__ import annotations

from jarvis.contract import Confirmation


def test_approval_policy_requires_risky_manifest_gates() -> None:
    from jarvis.hermes.approvals import approval_policy

    policy = approval_policy()

    assert policy["gates"]["send_mail"]["requires_confirmation"] is True
    assert policy["gates"]["send_mail"]["risk"] == "external"
    assert policy["gates"]["calendar_mutation"]["agents"] == ["tempo"]
    assert policy["gates"]["remote_code_push"]["agents"] == ["forge"]
    assert policy["gates"]["atlas_execution"]["risk"] == "financial"
    assert policy["gates"]["sentinel_restart"]["risk"] == "system"


def test_action_policy_normalizes_aliases_and_safe_reads() -> None:
    from jarvis.hermes.approvals import action_policy

    assert action_policy("tempo", "send_mail").requires_confirmation is True
    assert action_policy("tempo", "schedule").gate == "calendar_mutation"
    assert action_policy("forge", "push").gate == "remote_code_push"
    assert action_policy("atlas", "trader_execute").risk == "financial"
    assert action_policy("sentinel", "restart_sentinel").gate == "sentinel_restart"
    assert action_policy("lens", "quick_search").requires_confirmation is False
    assert action_policy("scholar", "document_summary").risk == "read"


def test_confirmation_to_approval_shape() -> None:
    from jarvis.hermes.approvals import confirmation_to_approval

    conf = Confirmation(
        id="conf_test",
        agent="atlas",
        intent="trade.execute",
        request="buy 1 share of XYZ",
        args={"symbol": "XYZ", "qty": 1},
        summary="Proposed paper trade execution",
    )

    approval = confirmation_to_approval(conf)

    assert approval["id"] == "conf_test"
    assert approval["agent"] == "atlas"
    assert approval["action"] == "trade.execute"
    assert approval["risk"] == "financial"
    assert approval["status"] == "pending"
    assert approval["payload"] == {"symbol": "XYZ", "qty": 1}


def test_hermes_approvals_endpoints_return_policy_and_queue(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)

    from fastapi.testclient import TestClient
    from jarvis.apps.api import app as api_module

    client = TestClient(api_module.make_app(registry={}))

    policy_resp = client.get("/api/hermes/approval-policy")
    assert policy_resp.status_code == 200
    assert policy_resp.json()["gates"]["atlas_execution"]["risk"] == "financial"

    queue_resp = client.get("/api/hermes/approvals")
    assert queue_resp.status_code == 200
    assert "approvals" in queue_resp.json()


def test_hermes_reject_endpoint_resolves_existing_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))

    from fastapi.testclient import TestClient
    from jarvis import config
    from jarvis.apps.api import app as api_module
    from jarvis.state import add_confirmation, read_confirmations

    config.get_settings.cache_clear()
    add_confirmation(
        Confirmation(
            id="conf_reject",
            agent="sentinel",
            intent="restart_sentinel",
            summary="Restart Sentinel service",
        )
    )

    client = TestClient(api_module.make_app(registry={}))
    reject_resp = client.post("/api/hermes/approvals/conf_reject/reject")

    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"
    assert read_confirmations(status=None, limit=0)[0].status == "rejected"
    config.get_settings.cache_clear()
