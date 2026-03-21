"""Tests for terrarium.persistence.migrations — schema migration system."""
import pytest
import pytest_asyncio
from terrarium.persistence.migrations import MigrationRunner


@pytest.mark.asyncio
async def test_migration_register():
    ...


@pytest.mark.asyncio
async def test_migration_get_current_version():
    ...


@pytest.mark.asyncio
async def test_migration_migrate_up():
    ...


@pytest.mark.asyncio
async def test_migration_get_pending():
    ...
