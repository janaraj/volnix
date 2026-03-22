"""Seed processor -- guaranteed situations in the world.

Seeds are specific scenarios placed into the world on top of generated
content.  They are guaranteed to exist.  Everything else is generated
from conditions.  The generic Seed model works across any domain.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Seed(BaseModel, frozen=True):
    """A specific scenario guaranteed to exist in the world.

    Seeds guarantee that specific scenarios exist in the generated world,
    regardless of what the condition-based generation produces.  The model
    is domain-agnostic -- ``entity_hints`` and ``actor_hints`` are
    free-form dicts the LLM interprets during world compilation.
    """

    description: str
    entity_hints: dict[str, Any] = Field(default_factory=dict)
    actor_hints: dict[str, Any] = Field(default_factory=dict)


class SeedProcessor:
    """Processes seed definitions and injects them into the entity set.

    Actual seed expansion requires an LLM (provided by D4).  This class
    provides the interface and stub implementations.
    """

    def __init__(self, llm_router: Any = None) -> None:
        """Initialize with an optional LLM router for seed expansion."""
        self._llm_router = llm_router

    async def process_seeds(
        self,
        seeds: list[Seed],
        entities: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert seeded situations into the entity set.

        Parameters
        ----------
        seeds:
            List of seed definitions to inject.
        entities:
            The current entity dictionary to augment.

        Returns
        -------
        dict:
            Updated entity dictionary with seeded entries.
        """
        return dict(entities)

    async def expand_nl_seed(self, description: str) -> Seed:
        """Expand a natural-language seed description into a structured Seed.

        Uses the LLM router to interpret the description and produce
        concrete attribute values.

        Parameters
        ----------
        description:
            Free-text description of the desired scenario.

        Returns
        -------
        Seed:
            Structured seed with populated fields.
        """
        return Seed(description=description)

    def validate_seeds(
        self,
        seeds: list[Seed],
        entities: dict[str, Any],
    ) -> list[str]:
        """Validate seeds are consistent with entity schemas.

        Parameters
        ----------
        seeds:
            Seeds to validate.
        entities:
            Entity dictionary containing schema information.

        Returns
        -------
        list[str]:
            List of validation error messages (empty if all valid).
        """
        return []
