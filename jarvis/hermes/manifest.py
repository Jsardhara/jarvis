"""Hermes crew manifest loader.

The manifest in ``docs/hermes/agent-manifest.yaml`` is the human-editable source
of truth for the Jarvis crew: identities, personalities, capabilities, safety
policy, and dashboard metadata.

Keep this module dependency-light. It uses a tiny YAML-subset parser so the
read-only dashboard endpoint does not require adding PyYAML to the runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

AGENT_ORDER = ("jarvis", "tempo", "scholar", "lens", "forge", "atlas", "sentinel", "me")
LOCKED_AGENT_IDS = frozenset(AGENT_ORDER)


class ManifestError(ValueError):
    """Raised when the Hermes manifest is missing or malformed."""


@dataclass(frozen=True)
class HermesManifest:
    """Validated Hermes crew manifest."""

    version: int
    system: str
    migration_strategy: str
    operator: str | None
    contract: dict[str, Any]
    approval_defaults: dict[str, Any]
    agents: dict[str, dict[str, Any]]


def default_manifest_path() -> Path:
    """Return the repo-local Hermes agent manifest path."""

    return Path(__file__).resolve().parents[2] / "docs" / "hermes" / "agent-manifest.yaml"


def load_manifest(path: str | Path | None = None) -> HermesManifest:
    """Load and validate the Hermes crew manifest.

    Args:
        path: Optional manifest path. Defaults to ``docs/hermes/agent-manifest.yaml``.

    Raises:
        ManifestError: when the manifest is missing required fields or locked agents.
    """

    manifest_path = Path(path) if path is not None else default_manifest_path()
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")

    data = _parse_yaml_subset(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be a mapping")

    agents = data.get("agents")
    if not isinstance(agents, dict):
        raise ManifestError("manifest must define agents mapping")

    missing = sorted(LOCKED_AGENT_IDS.difference(agents))
    if missing:
        raise ManifestError(f"missing locked agents: {', '.join(missing)}")

    extra = sorted(set(agents).difference(LOCKED_AGENT_IDS))
    if extra:
        raise ManifestError(f"unknown agents are not allowed in locked crew: {', '.join(extra)}")

    return HermesManifest(
        version=int(data.get("version", 1)),
        system=str(data.get("system", "")),
        migration_strategy=str(data.get("migration_strategy", "")),
        operator=data.get("operator"),
        contract=_mapping(data.get("contract"), "contract"),
        approval_defaults=_mapping(data.get("approval_defaults"), "approval_defaults"),
        agents={agent_id: _mapping(agent, f"agents.{agent_id}") for agent_id, agent in agents.items()},
    )


def agent_cards(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return dashboard-friendly agent cards from the manifest."""

    manifest = load_manifest(path)
    cards: list[dict[str, Any]] = []
    for agent_id in _ordered_agent_ids(manifest.agents):
        raw = manifest.agents[agent_id]
        cards.append(
            {
                "id": agent_id,
                "name": raw.get("name", agent_id.title()),
                "role": raw.get("role", ""),
                "personality": raw.get("personality", ""),
                "status": raw.get("status", "active"),
                "model_tier": raw.get("model_tier", "balanced"),
                "icon": raw.get("icon", "Circle"),
                "color": raw.get("color", "neutral"),
                "capabilities": list(raw.get("capabilities") or []),
                "tools": list(raw.get("tools") or []),
                "confirmation_gates": list(raw.get("confirmation_gates") or []),
                "dashboard": dict(raw.get("dashboard") or {}),
                "safety": _public_safety(raw.get("safety") or {}),
            }
        )
    return cards


def manifest_payload(path: str | Path | None = None) -> dict[str, Any]:
    """Return the normalized API payload for ``GET /api/hermes/agents``."""

    manifest = load_manifest(path)
    return {
        "system": manifest.system,
        "migration_strategy": manifest.migration_strategy,
        "operator": manifest.operator,
        "agents": agent_cards(path),
        "approval_defaults": manifest.approval_defaults,
        "contract": manifest.contract,
    }


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be a mapping")
    return value


def _public_safety(value: Any) -> dict[str, Any]:
    safety = _mapping(value, "agent safety")
    # The dashboard needs policy flags, not local filesystem paths.
    return {key: val for key, val in safety.items() if key != "source_path"}


def _ordered_agent_ids(agents: dict[str, Any]) -> list[str]:
    return [agent_id for agent_id in AGENT_ORDER if agent_id in agents]


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by ``agent-manifest.yaml``.

    Supported constructs:
    - indentation-based mappings
    - scalar values: strings, ints, floats, booleans, null
    - block lists using ``- item``
    - inline empty lists: ``[]``

    It intentionally does not try to be a general YAML parser.
    """

    significant: list[tuple[int, str, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        significant.append((indent, raw_line.strip(), raw_line))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for idx, (indent, line, raw_line) in enumerate(significant):
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ManifestError(f"list item without list parent: {raw_line}")
            parent.append(_parse_scalar(line[2:].strip()))
            continue

        if ":" not in line:
            raise ManifestError(f"invalid manifest line: {raw_line}")
        if not isinstance(parent, dict):
            raise ManifestError(f"mapping entry inside non-mapping: {raw_line}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            parent[key] = _parse_scalar(raw_value)
            continue

        next_line = significant[idx + 1] if idx + 1 < len(significant) else None
        is_list = bool(next_line and next_line[0] > indent and next_line[1].startswith("- "))
        container: dict[str, Any] | list[Any] = [] if is_list else {}
        parent[key] = container
        stack.append((indent, container))

    return root


def _parse_scalar(value: str) -> Any:
    if value == "[]":
        return []
    if value == "{}":
        return {}
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
