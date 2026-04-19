"""Tier-1 fixture loader (PMF Plan Phase 4B Step 9).

Loads pack-authored YAML memory fixtures at world compile time when
``memory.tier_mode == "mixed"``. Records get ``tier="tier1"``,
``source="pack_fixture"``, ``consolidated_from=None``. These are
hand-authored beliefs a pack wants its NPCs (or agents, or teams)
to start with, as opposed to Tier-2 memories accumulated at runtime.

Called by Step 10's composition only when the config's ``tier_mode``
opts in. This module is a pure library function — no engine
coupling.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.store import MemoryStoreProtocol

logger = logging.getLogger(__name__)


class Tier1Fixture(BaseModel):
    """One pack-authored fact for one owner.

    Frozen + extra-forbidden so typos in pack YAML fail at load
    time instead of silently dropping a field (D9-5).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1)
    importance: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


async def load_tier1_fixtures(fixtures_path: Path, store: MemoryStoreProtocol) -> int:
    """Load Tier-1 fixtures from ``fixtures_path`` into ``store``.

    Returns the number of records inserted.

    Missing file → returns 0 (not an error; packs may not ship
    fixtures; D9-3).
    Malformed YAML → raises ``yaml.YAMLError``.
    Malformed fixture dict → raises ``pydantic.ValidationError``.
    Duplicate record_id (e.g. running twice) → raises the store's
    PK-collision error (D9-8).
    """
    if not fixtures_path.exists():
        logger.info(
            "Tier1Loader: no fixtures file at %s — skipping.",
            fixtures_path,
        )
        return 0

    with fixtures_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    # Empty file → yaml.safe_load returns None. Treat as no records.
    if raw is None:
        return 0
    if not isinstance(raw, dict):
        raise ValueError(
            f"Tier1Loader: {fixtures_path} must contain a top-level "
            f"mapping (owner_id -> list of fixtures), got {type(raw).__name__}."
        )

    count = 0
    # D9-6: deterministic iteration order.
    for owner_id in sorted(raw.keys()):
        fixture_list = raw[owner_id]
        if not isinstance(fixture_list, list):
            raise ValueError(
                f"Tier1Loader: owner {owner_id!r} in {fixtures_path} "
                f"must map to a list of fixtures, got "
                f"{type(fixture_list).__name__}."
            )
        for idx, fixture_raw in enumerate(fixture_list):
            fixture = Tier1Fixture.model_validate(fixture_raw)
            record = MemoryRecord(
                record_id=MemoryRecordId(f"tier1:{owner_id}:{idx}"),
                scope="actor",
                owner_id=owner_id,
                kind="semantic",
                tier="tier1",
                source="pack_fixture",
                content=fixture.content,
                content_hash=content_hash_of(fixture.content),
                importance=fixture.importance,
                tags=list(fixture.tags),
                created_tick=0,
                consolidated_from=None,
            )
            await store.insert(record)
            count += 1

    logger.info("Tier1Loader: loaded %d fixture records from %s", count, fixtures_path)
    return count
