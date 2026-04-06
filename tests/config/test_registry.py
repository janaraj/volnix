"""Tests for volnix.config.registry — live config registry and subscriptions."""
import pytest
from volnix.config.registry import ConfigRegistry
from volnix.config.schema import VolnixConfig


def test_get_section():
    """get_section returns the correct section model."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    sim = registry.get_section("simulation")
    assert sim.mode == "governed"
    assert sim.seed == 42


def test_get_value():
    """get() retrieves a specific key from a section."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    assert registry.get("simulation", "seed") == 42
    assert registry.get("budget", "warning_threshold_pct") == 80.0


def test_get_missing_section():
    """get_section raises AttributeError for unknown section."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    with pytest.raises(AttributeError):
        registry.get_section("nonexistent_section")


def test_update_tunable():
    """update_tunable changes the runtime config value."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    registry.update_tunable("simulation", "seed", 999)
    assert registry.get("simulation", "seed") == 999


def test_subscribe_and_notify():
    """Subscribed callbacks are notified on update_tunable."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    notifications: list[tuple] = []

    def on_change(section, key, value):
        notifications.append((section, key, value))

    registry.subscribe("simulation", "seed", on_change)
    registry.update_tunable("simulation", "seed", 123)
    assert len(notifications) == 1
    assert notifications[0] == ("simulation", "seed", 123)


def test_get_missing_key():
    """get() raises AttributeError for unknown key within a valid section."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    with pytest.raises(AttributeError):
        registry.get("simulation", "nonexistent_key")


def test_update_tunable_notifies_multiple():
    """Multiple subscribers all receive notification."""
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    results_a: list = []
    results_b: list = []

    registry.subscribe("budget", "warning_threshold_pct", lambda s, k, v: results_a.append(v))
    registry.subscribe("budget", "warning_threshold_pct", lambda s, k, v: results_b.append(v))

    registry.update_tunable("budget", "warning_threshold_pct", 90.0)

    assert results_a == [90.0]
    assert results_b == [90.0]


def test_get_section_returns_typed():
    """get_section returns the actual typed Pydantic model, not a dict."""
    from volnix.config.schema import SimulationConfig
    config = VolnixConfig()
    registry = ConfigRegistry(config)
    section = registry.get_section("simulation")
    assert isinstance(section, SimulationConfig)
