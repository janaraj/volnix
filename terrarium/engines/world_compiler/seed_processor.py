"""Seed processing for world compilation.

Processes seed descriptions into guaranteed entities placed on top of
generated world content.
"""
from terrarium.reality.seeds import Seed, SeedProcessor


class CompilerSeedProcessor:
    def __init__(self, seed_processor: SeedProcessor | None = None) -> None: ...

    async def process(
        self, seeds: list[dict], entities: dict, schemas: dict
    ) -> dict:
        """Process all seeds and insert guaranteed situations into entities."""
        ...

    async def process_nl_seeds(self, seed_descriptions: list[str]) -> list[Seed]:
        """Convert natural language seed descriptions to structured Seeds."""
        ...
