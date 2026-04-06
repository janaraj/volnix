"""Tests for volnix.persistence.config — persistence configuration model."""

import pytest

from volnix.persistence.config import PersistenceConfig


def test_persistence_config_defaults():
    """Default values should match the documented contract."""
    cfg = PersistenceConfig()
    assert cfg.base_dir == "volnix_data"
    assert cfg.wal_mode is True
    assert cfg.max_connections == 5
    assert cfg.migration_auto_run is True
    assert cfg.backup_interval_seconds == 0


def test_persistence_config_custom():
    """Custom values should override defaults."""
    cfg = PersistenceConfig(
        base_dir="/tmp/custom",
        wal_mode=False,
        max_connections=10,
        migration_auto_run=False,
        backup_interval_seconds=300,
    )
    assert cfg.base_dir == "/tmp/custom"
    assert cfg.wal_mode is False
    assert cfg.max_connections == 10
    assert cfg.migration_auto_run is False
    assert cfg.backup_interval_seconds == 300


def test_persistence_config_type_validation():
    """Invalid types raise validation errors."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        PersistenceConfig(max_connections="not_a_number")


def test_persistence_config_serialization():
    """Config can be serialized and deserialized."""
    config = PersistenceConfig(base_dir="/custom", wal_mode=False)
    data = config.model_dump()
    restored = PersistenceConfig(**data)
    assert restored.base_dir == "/custom"
    assert restored.wal_mode is False
