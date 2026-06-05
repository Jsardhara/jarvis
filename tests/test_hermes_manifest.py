"""Tests for the Hermes crew manifest loader."""
from __future__ import annotations

from pathlib import Path

import pytest


REQUIRED_AGENT_IDS = {"jarvis", "tempo", "scholar", "lens", "forge", "atlas", "sentinel", "me"}


def test_load_manifest_contains_locked_agent_set() -> None:
    from jarvis.hermes.manifest import load_manifest

    manifest = load_manifest()

    assert set(manifest.agents) == REQUIRED_AGENT_IDS
    assert manifest.system == "jarvis-hermes"
    assert manifest.migration_strategy == "hybrid"


def test_agent_cards_include_personality_and_dashboard_metadata() -> None:
    from jarvis.hermes.manifest import agent_cards

    cards = agent_cards()
    by_id = {card["id"]: card for card in cards}

    assert by_id["tempo"]["personality"].startswith("Crisp executive assistant")
    assert by_id["forge"]["model_tier"] == "strongest_coding"
    assert by_id["atlas"]["status"] == "paper"
    assert by_id["atlas"]["safety"]["paper_mode_default"] is True
    assert "source_path" not in by_id["atlas"]["safety"]
    assert "atlas_execution" in by_id["atlas"]["confirmation_gates"]
    assert by_id["sentinel"]["dashboard"]["primary_widgets"] == [
        "job_grid",
        "next_runs",
        "heartbeat",
        "alert_ticker",
    ]


def test_load_manifest_rejects_missing_locked_agent(tmp_path: Path) -> None:
    from jarvis.hermes.manifest import ManifestError, load_manifest

    bad_manifest = tmp_path / "agent-manifest.yaml"
    bad_manifest.write_text(
        "version: 1\n"
        "system: jarvis-hermes\n"
        "migration_strategy: hybrid\n"
        "agents:\n"
        "  jarvis:\n"
        "    name: Jarvis\n"
        "    role: Orchestrator\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="missing locked agents"):
        load_manifest(bad_manifest)


def test_load_manifest_rejects_unknown_agent(tmp_path: Path) -> None:
    from jarvis.hermes.manifest import ManifestError, load_manifest

    agents = "".join(
        f"  {agent_id}:\n    name: {agent_id.title()}\n    role: Test\n"
        for agent_id in REQUIRED_AGENT_IDS
    )
    bad_manifest = tmp_path / "agent-manifest.yaml"
    bad_manifest.write_text(
        "version: 1\n"
        "system: jarvis-hermes\n"
        "migration_strategy: hybrid\n"
        "contract:\n  envelope_fields: []\n"
        "approval_defaults:\n  require_confirmation: []\n"
        "agents:\n"
        f"{agents}"
        "  rogue:\n    name: Rogue\n    role: Unknown\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="unknown agents"):
        load_manifest(bad_manifest)
