"""Seed processor -- guaranteed situations in the world.

Seeds are specific scenarios placed into the world on top of generated
content.  They are guaranteed to exist.  Everything else is generated
from conditions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Seed(BaseModel, frozen=True):
    """A single seeded situation to inject into the world.

    Seeds guarantee that specific scenarios exist in the generated world,
    regardless of what the condition-based generation produces.
    """

    description: str                         # NL description of the situation
    customer: dict[str, Any] | None = None   # customer attributes to guarantee
    charge: dict[str, Any] | None = None     # charge attributes
    ticket: dict[str, Any] | None = None     # ticket attributes
    actor: dict[str, Any] | None = None      # actor attributes
    custom: dict[str, Any] | None = None     # any other entity attributes


class SeedProcessor:
    """Processes seed definitions and injects them into the entity set."""

    def __init__(self, llm_router: Any = None) -> None:
        ...

    async def process_seeds(
        self,
        seeds: list[Seed],
        entities: dict,
    ) -> dict:
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
        ...

    async def expand_nl_seed(self, description: str) -> Seed:
        """Expand a natural-language seed description into a structured ``Seed``.

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
        ...

    def validate_seeds(
        self,
        seeds: list[Seed],
        entities: dict,
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
        ...
