"""Tests for volnix.engines.state.store -- EntityStore CRUD operations."""

import pytest

from volnix.core.errors import EntityNotFoundError, StateError
from volnix.core.types import EntityId


async def test_create_and_read(store):
    """Create an entity and read it back; verify fields match."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice", "age": 30})

    result = await store.read("user", eid)
    assert result is not None
    assert result["name"] == "Alice"
    assert result["age"] == 30
    assert result["_entity_type"] == "user"
    assert result["_entity_id"] == "user-1"


async def test_create_duplicate_raises(store):
    """Creating the same (type, id) twice raises StateError."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice"})

    with pytest.raises(StateError, match="already exists"):
        await store.create("user", eid, {"name": "Bob"})


async def test_read_missing_none(store):
    """Reading a nonexistent entity returns None."""
    result = await store.read("user", EntityId("no-such-id"))
    assert result is None


async def test_update_merges(store):
    """Update merges new fields into existing entity data."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice", "age": 30})
    await store.update("user", eid, {"age": 31, "email": "a@b.com"})

    result = await store.read("user", eid)
    assert result is not None
    assert result["name"] == "Alice"  # preserved
    assert result["age"] == 31  # updated
    assert result["email"] == "a@b.com"  # added


async def test_update_returns_previous(store):
    """Update returns the pre-update state for retractability."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice", "age": 30})
    previous = await store.update("user", eid, {"age": 31})

    assert previous is not None
    assert previous["name"] == "Alice"
    assert previous["age"] == 30


async def test_update_missing_raises(store):
    """Updating a nonexistent entity raises EntityNotFoundError."""
    with pytest.raises(EntityNotFoundError):
        await store.update("user", EntityId("no-such-id"), {"name": "Bob"})


async def test_delete_returns_previous(store):
    """Delete returns the pre-delete state for retractability."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice", "age": 30})
    previous = await store.delete("user", eid)

    assert previous is not None
    assert previous["name"] == "Alice"
    assert previous["age"] == 30


async def test_delete_then_read_none(store):
    """After deleting an entity, read returns None."""
    eid = EntityId("user-1")
    await store.create("user", eid, {"name": "Alice"})
    await store.delete("user", eid)

    result = await store.read("user", eid)
    assert result is None


async def test_delete_missing_returns_none(store):
    """Deleting a nonexistent entity returns None (idempotent)."""
    result = await store.delete("user", EntityId("no-such-id"))
    assert result is None


async def test_query_by_type(store):
    """Query returns all entities of a given type."""
    for i in range(3):
        await store.create("user", EntityId(f"u-{i}"), {"name": f"User {i}"})
    for i in range(2):
        await store.create("order", EntityId(f"o-{i}"), {"total": i * 10})

    users = await store.query("user")
    assert len(users) == 3

    orders = await store.query("order")
    assert len(orders) == 2


async def test_query_with_filters(store):
    """Query with filters returns only matching entities."""
    await store.create("user", EntityId("u-1"), {"name": "Alice", "status": "active"})
    await store.create("user", EntityId("u-2"), {"name": "Bob", "status": "inactive"})
    await store.create("user", EntityId("u-3"), {"name": "Charlie", "status": "active"})

    active = await store.query("user", filters={"status": "active"})
    assert len(active) == 2
    names = {u["name"] for u in active}
    assert names == {"Alice", "Charlie"}


async def test_count(store):
    """Count returns the correct number of entities per type."""
    for i in range(3):
        await store.create("user", EntityId(f"u-{i}"), {"name": f"User {i}"})

    assert await store.count("user") == 3
    assert await store.count("order") == 0
