"""Condition expander -- preset + overrides -> concrete WorldConditions.

The expander also applies the resulting conditions to shape world data
during the compilation phase:

* Marks entities as stale / incomplete
* Generates adversarial actor personalities
* Configures service failure rates
* Injects auth gaps and exposed secrets
"""

from __future__ import annotations

from typing import Any

from terrarium.reality.dimensions import WorldConditions
from terrarium.reality.presets import RealityPreset


class ConditionExpander:
    """Expands a reality preset + overrides into concrete world conditions.

    Then applies those conditions to shape world data during compilation.
    """

    def __init__(self) -> None:
        ...

    def expand(
        self,
        preset: RealityPreset,
        overrides: dict[str, Any] | None = None,
    ) -> WorldConditions:
        """Expand preset + overrides into full ``WorldConditions``.

        Parameters
        ----------
        preset:
            The base reality preset to start from.
        overrides:
            Optional dict of dimension field overrides applied on top of the
            preset values.

        Returns
        -------
        WorldConditions:
            The fully resolved conditions.
        """
        ...

    def apply_to_entities(
        self,
        conditions: WorldConditions,
        entities: dict[str, list],
    ) -> dict[str, list]:
        """Apply data-quality conditions to generated entities.

        Marks a percentage of entities as stale, incomplete, or inconsistent
        based on the ``data_quality`` dimension values.
        """
        ...

    def apply_to_actors(
        self,
        conditions: WorldConditions,
        actors: list[dict],
    ) -> list[dict]:
        """Apply adversarial conditions to actor generation.

        Tags a percentage of actors as hostile / manipulative based on the
        ``adversarial`` dimension values.
        """
        ...

    def apply_to_services(
        self,
        conditions: WorldConditions,
        services: dict,
    ) -> dict:
        """Apply service-reliability conditions to service configs.

        Configures failure-rate and timeout probabilities on each service
        definition.
        """
        ...

    def apply_to_boundaries(
        self,
        conditions: WorldConditions,
        world_plan: dict,
    ) -> dict:
        """Apply boundary-security conditions (auth gaps, exposed secrets).

        Injects misconfigured auth and exposed-secret scenarios into the
        world plan.
        """
        ...
