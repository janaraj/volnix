"""Personality generation for world compilation.

Generates actor personalities based on reality conditions and domain context.
"""
from terrarium.actors.generator import ActorGenerator
from terrarium.actors.definition import ActorDefinition
from terrarium.reality.dimensions import WorldConditions


class CompilerPersonalityGenerator:
    def __init__(self, actor_generator: ActorGenerator | None = None) -> None: ...

    async def generate_all_personalities(
        self, actors: list[dict], conditions: WorldConditions, domain: str
    ) -> list[ActorDefinition]:
        """Generate personalities for all actors based on conditions."""
        ...

    async def inject_adversarial_actors(
        self, actors: list[dict], conditions: WorldConditions, entity_count: int
    ) -> list[dict]:
        """Add adversarial actors based on adversarial dimension percentages."""
        ...
