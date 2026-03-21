"""Actor generator -- create actor personalities from reality conditions.

The :class:`ActorGenerator` uses an LLM router (when available) to produce
realistic personalities, adversarial profiles, and human behaviour traits
that are consistent with the world's reality conditions.
"""

from __future__ import annotations

from typing import Any

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.personality import Personality
from terrarium.reality.dimensions import WorldConditions


class ActorGenerator:
    """Generate actor personalities from reality conditions."""

    def __init__(self, llm_router: Any = None) -> None:
        ...

    async def generate_personalities(
        self,
        actors: list[ActorDefinition],
        conditions: WorldConditions,
    ) -> list[ActorDefinition]:
        """Assign personalities to actors based on world conditions.

        Parameters
        ----------
        actors:
            List of actor definitions (may lack personalities).
        conditions:
            The world conditions that influence personality generation.

        Returns
        -------
        list[ActorDefinition]:
            Actors with populated personality fields.
        """
        ...

    async def generate_adversarial_actors(
        self,
        count: int,
        sophistication: str,
        domain_context: str,
    ) -> list[ActorDefinition]:
        """Generate adversarial actors (hostile customers, etc.).

        Parameters
        ----------
        count:
            Number of adversarial actors to generate.
        sophistication:
            Sophistication level (low | medium | high).
        domain_context:
            Description of the domain for realistic generation.

        Returns
        -------
        list[ActorDefinition]:
            Newly generated adversarial actor definitions.
        """
        ...

    async def generate_human_personality(
        self,
        role: str,
        domain_context: str,
    ) -> Personality:
        """Generate a realistic personality for a human actor.

        Parameters
        ----------
        role:
            The actor's role (e.g. "supervisor", "customer").
        domain_context:
            Description of the domain for realistic generation.

        Returns
        -------
        Personality:
            A fully populated personality model.
        """
        ...
