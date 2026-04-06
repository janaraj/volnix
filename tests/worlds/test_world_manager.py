"""Tests for WorldManager — world lifecycle CRUD."""

from __future__ import annotations

import json

import pytest

from volnix.core.types import WorldId
from volnix.worlds.manager import WorldManager


@pytest.fixture
def world_mgr(tmp_path):
    """Fresh WorldManager using a temp directory."""
    return WorldManager(data_dir=str(tmp_path / "worlds"))


class TestWorldManagerCreate:
    """World creation tests."""

    async def test_create_world_returns_world_id(self, world_mgr):
        wid = await world_mgr.create_world(
            name="Test World",
            plan_data={"name": "Test World"},
            seed=42,
        )
        assert str(wid).startswith("world_")

    async def test_create_world_writes_metadata(self, world_mgr):
        wid = await world_mgr.create_world(
            name="Test",
            plan_data={},
            seed=1,
        )
        meta_path = world_mgr.get_world_dir(wid) / "metadata.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["world_id"] == str(wid)
        assert data["name"] == "Test"
        assert data["seed"] == 1
        assert data["status"] == "created"

    async def test_create_world_writes_plan(self, world_mgr):
        plan = {"name": "My World", "services": {"email": {}}}
        wid = await world_mgr.create_world(
            name="My World",
            plan_data=plan,
            seed=42,
        )
        plan_path = world_mgr.get_world_dir(wid) / "plan.json"
        assert plan_path.exists()
        loaded = json.loads(plan_path.read_text())
        assert loaded["name"] == "My World"

    async def test_create_world_records_services(self, world_mgr):
        wid = await world_mgr.create_world(
            name="Svc",
            plan_data={},
            seed=42,
            services=["email", "chat"],
        )
        world = await world_mgr.get_world(wid)
        assert world["services"] == ["email", "chat"]


class TestWorldManagerQuery:
    """World listing and retrieval tests."""

    async def test_list_worlds_empty(self, world_mgr):
        worlds = await world_mgr.list_worlds()
        assert worlds == []

    async def test_list_worlds_returns_newest_first(self, world_mgr):
        w1 = await world_mgr.create_world(name="First", plan_data={})
        w2 = await world_mgr.create_world(name="Second", plan_data={})
        worlds = await world_mgr.list_worlds()
        assert len(worlds) == 2
        assert worlds[0]["world_id"] == str(w2)
        assert worlds[1]["world_id"] == str(w1)

    async def test_list_worlds_respects_limit(self, world_mgr):
        for i in range(5):
            await world_mgr.create_world(name=f"W{i}", plan_data={})
        worlds = await world_mgr.list_worlds(limit=3)
        assert len(worlds) == 3

    async def test_get_world_found(self, world_mgr):
        wid = await world_mgr.create_world(name="Found", plan_data={})
        world = await world_mgr.get_world(wid)
        assert world is not None
        assert world["name"] == "Found"

    async def test_get_world_not_found(self, world_mgr):
        result = await world_mgr.get_world(WorldId("world_nonexistent"))
        assert result is None


class TestWorldManagerLifecycle:
    """World lifecycle (mark_generated, delete) tests."""

    async def test_mark_generated(self, world_mgr):
        wid = await world_mgr.create_world(name="Gen", plan_data={})
        await world_mgr.mark_generated(wid, entity_count=50, actor_count=3)
        world = await world_mgr.get_world(wid)
        assert world["status"] == "generated"
        assert world["entity_count"] == 50
        assert world["actor_count"] == 3

    async def test_delete_world(self, world_mgr):
        wid = await world_mgr.create_world(name="Del", plan_data={})
        assert world_mgr.get_world_dir(wid).exists()
        deleted = await world_mgr.delete_world(wid)
        assert deleted is True
        assert not world_mgr.get_world_dir(wid).exists()
        assert await world_mgr.get_world(wid) is None

    async def test_delete_nonexistent(self, world_mgr):
        deleted = await world_mgr.delete_world(WorldId("world_nope"))
        assert deleted is False


class TestWorldManagerPaths:
    """Path and DB location tests."""

    async def test_get_state_db_path(self, world_mgr):
        wid = await world_mgr.create_world(name="DB", plan_data={})
        path = world_mgr.get_state_db_path(wid)
        assert path.endswith("state.db")
        assert str(wid) in path

    async def test_get_world_dir(self, world_mgr):
        wid = await world_mgr.create_world(name="Dir", plan_data={})
        d = world_mgr.get_world_dir(wid)
        assert d.exists()
        assert d.name == str(wid)


class TestWorldManagerPersistence:
    """Reload from disk tests."""

    async def test_load_existing_worlds(self, tmp_path):
        # Create worlds with first manager
        mgr1 = WorldManager(data_dir=str(tmp_path / "worlds"))
        wid = await mgr1.create_world(name="Persistent", plan_data={"x": 1})
        await mgr1.mark_generated(wid, entity_count=10, actor_count=2)

        # Create second manager pointing to same directory — should reload
        mgr2 = WorldManager(data_dir=str(tmp_path / "worlds"))
        world = await mgr2.get_world(wid)
        assert world is not None
        assert world["name"] == "Persistent"
        assert world["status"] == "generated"
        assert world["entity_count"] == 10
