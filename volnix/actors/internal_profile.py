"""Load internal agent team definitions from YAML.

Internal agents are autonomous team members that work toward a mission
inside a compiled world. They collaborate via messaging services and
research via other available services. The lead agent produces the
deliverable.

Format mirrors external agent profile (profile.py) with additions:
mission, deliverable, lead designation, personality.

Example YAML::

    mission: "Predict S&P 500 direction over the next quarter."
    deliverable: prediction

    agents:
      - role: macro-economist
        lead: true
        personality: "Focuses on GDP growth and Fed policy."
        permissions:
          read: [slack, twitter, reddit]
          write: [slack]
      - role: risk-analyst
        personality: "Focuses on tail risks and volatility."
        permissions:
          read: [slack, twitter, reddit]
          write: [slack]
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


class InternalAgentProfile:
    """Parsed internal agent team profile.

    Attributes:
        mission: The team's mission statement.
        deliverable: Deliverable preset name (e.g. "prediction", "synthesis").
        agents: List of ActorDefinition for each team member.
        lead_id: ActorId of the designated lead agent.
    """

    def __init__(
        self,
        mission: str,
        deliverable: str | None,
        agents: list[ActorDefinition],
        lead_id: ActorId | None,
    ) -> None:
        self.mission = mission
        self.deliverable = deliverable
        self.agents = agents
        self.lead_id = lead_id


def load_internal_profile(path: str | Path) -> InternalAgentProfile:
    """Load internal agent team from YAML file.

    Args:
        path: Path to the internal agent YAML file.

    Returns:
        InternalAgentProfile with mission, deliverable, agent definitions,
        and lead actor ID.

    Raises:
        ValueError: If YAML is malformed or missing required fields.
        FileNotFoundError: If path does not exist.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "agents" not in raw:
        raise ValueError(f"Internal agent profile must have 'agents' key: {path}")

    mission = raw.get("mission", "")
    deliverable = raw.get("deliverable")
    agents_raw = raw["agents"]

    if not isinstance(agents_raw, list) or not agents_raw:
        raise ValueError(f"Internal agent profile must have at least one agent: {path}")

    definitions: list[ActorDefinition] = []
    lead_id: ActorId | None = None

    for entry in agents_raw:
        role = entry.get("role", "internal-agent")
        role_hash = hashlib.md5(role.encode()).hexdigest()[:8]
        actor_id = ActorId(entry.get("id", f"{role}-{role_hash}"))

        is_lead = entry.get("lead", False)
        if is_lead:
            lead_id = actor_id

        metadata: dict[str, Any] = {}
        if is_lead:
            metadata["lead"] = True

        definitions.append(
            ActorDefinition(
                id=actor_id,
                type=ActorType.AGENT,
                role=role,
                permissions=entry.get("permissions", {}),
                budget=entry.get("budget"),
                personality_hint=entry.get("personality", ""),
                metadata=metadata,
            )
        )

    # Default: first agent is lead if none explicitly marked
    if lead_id is None and definitions:
        lead_id = definitions[0].id
        definitions[0] = definitions[0].model_copy(
            update={"metadata": {**definitions[0].metadata, "lead": True}}
        )

    logger.info(
        "Loaded internal agent profile: %d agents, lead=%s, mission=%s, deliverable=%s",
        len(definitions),
        lead_id,
        bool(mission),
        deliverable,
    )

    return InternalAgentProfile(
        mission=mission,
        deliverable=deliverable,
        agents=definitions,
        lead_id=lead_id,
    )
