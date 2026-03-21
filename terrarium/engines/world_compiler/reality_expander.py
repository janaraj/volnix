"""Reality expansion for the world compiler.

Integrates the reality/ module into the compilation pipeline.
Expands presets into conditions and applies them to world data.
"""
from terrarium.reality.dimensions import WorldConditions
from terrarium.reality.expander import ConditionExpander
from terrarium.reality.presets import RealityPreset


class CompilerRealityExpander:
    """Bridges the reality module and the world compiler."""

    def __init__(self, expander: ConditionExpander | None = None) -> None: ...

    async def expand_and_apply(
        self, world_plan: dict, preset: str, overrides: dict | None = None
    ) -> tuple[dict, WorldConditions]:
        """Expand reality preset and apply conditions to the world plan.

        Returns the modified world plan and the conditions used.
        """
        ...
