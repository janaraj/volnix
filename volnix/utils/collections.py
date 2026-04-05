"""Generic collection utilities for Volnix.

Reusable helpers for deduplication, merging, and filtering
of entity-like dict collections. No engine dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def dedup_entity_dicts(
    entities: list[dict[str, Any]],
    key: str = "id",
    strategy: str = "last_wins",
) -> list[dict[str, Any]]:
    """Deduplicate a list of entity dicts by a key field.

    Args:
        entities: List of entity dicts to deduplicate.
        key: The field name to deduplicate on (default: ``"id"``).
        strategy: ``"last_wins"`` (later entry replaces earlier) or
            ``"first_wins"`` (earlier entry kept, later dropped).

    Returns:
        Deduplicated list preserving insertion order.
    """
    seen: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    removed = 0

    for entity in entities:
        key_value = entity.get(key)
        if key_value is None:
            result.append(entity)
            continue

        key_str = str(key_value)
        if key_str in seen:
            if strategy == "last_wins":
                result[seen[key_str]] = entity
            removed += 1
        else:
            seen[key_str] = len(result)
            result.append(entity)

    if removed > 0:
        logger.debug(
            "dedup_entity_dicts: removed %d duplicates (key=%s, strategy=%s)",
            removed, key, strategy,
        )

    return result


def dedup_entity_collection(
    collection: dict[str, list[dict[str, Any]]],
    key: str = "id",
    strategy: str = "last_wins",
) -> dict[str, list[dict[str, Any]]]:
    """Deduplicate all entity lists in a type-keyed collection.

    Args:
        collection: Dict mapping entity_type to list of entity dicts.
        key: The field name to deduplicate on.
        strategy: ``"last_wins"`` or ``"first_wins"``.

    Returns:
        New dict with deduplicated lists per entity type.
    """
    return {
        entity_type: dedup_entity_dicts(entities, key=key, strategy=strategy)
        for entity_type, entities in collection.items()
    }
