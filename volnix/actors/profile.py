"""Agent profile loader — parse external agent definitions from YAML.

Agent profiles define external agent roles, permissions, and budgets
independently from the world definition. Loaded at runtime, not compile time.

Usage::

    # Load from YAML
    agents = load_agent_profile("agents.yaml")

    # Create a default for unregistered agents
    agent = make_default_agent("crewai-analyst")
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

from volnix.actors.definition import ActorDefinition
from volnix.core.types import ActorId, ActorType

logger = logging.getLogger(__name__)


def load_agent_profile(path: str | Path) -> list[ActorDefinition]:
    """Load external agent definitions from a YAML file.

    YAML format::

        agents:
          - role: financial-analyst
            permissions:
              read: [alpaca]
              write: []
            budget:
              api_calls: 200

    Each agent gets a deterministic ID based on role hash.
    All agents are type=AGENT (external).

    Args:
        path: Path to agent profile YAML.

    Returns:
        List of ActorDefinition objects.

    Raises:
        FileNotFoundError: If path doesn't exist.
        ValueError: If YAML is malformed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Agent profile not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "agents" not in raw:
        raise ValueError(f"Agent profile must have 'agents' key: {path}")

    agents_raw = raw["agents"]
    if not isinstance(agents_raw, list):
        raise ValueError(f"'agents' must be a list: {path}")

    definitions: list[ActorDefinition] = []
    for entry in agents_raw:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "external-agent")
        role_hash = hashlib.md5(role.encode()).hexdigest()[:8]  # noqa: S324
        actor_id = entry.get("id", f"{role}-{role_hash}")

        definitions.append(
            ActorDefinition(
                id=ActorId(actor_id),
                type=ActorType.AGENT,
                role=role,
                permissions=entry.get("permissions", {}),
                budget=entry.get("budget"),
                metadata=entry.get("metadata", {}),
            )
        )

    logger.info("Loaded %d agent profiles from %s", len(definitions), path)
    return definitions


def make_default_agent(
    agent_name: str,
    default_permissions: dict[str, Any] | None = None,
    default_budget: dict[str, Any] | None = None,
) -> ActorDefinition:
    """Create a default agent definition for unregistered external agents.

    Used when no agent profile is provided and an agent connects
    with an unknown actor_id.

    Args:
        agent_name: Human-readable name (used to generate deterministic ID).
        default_permissions: Permission dict. If None, read/write all.
        default_budget: Budget dict. If None, no budget limit.

    Returns:
        ActorDefinition with sensible defaults.
    """
    name_hash = hashlib.md5(agent_name.encode()).hexdigest()[:8]  # noqa: S324
    return ActorDefinition(
        id=ActorId(f"{agent_name}-{name_hash}"),
        type=ActorType.HUMAN,
        role=agent_name,
        permissions=default_permissions or {"read": "all", "write": "all"},
        budget=default_budget,
    )
