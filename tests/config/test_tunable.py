"""Tests for terrarium.config.tunable — runtime-tunable parameters."""
import pytest
from terrarium.config.tunable import TunableField, TunableRegistry


def test_register_and_get():
    """Registering a tunable field allows retrieval of its value."""
    registry = TunableRegistry()
    field = TunableField(
        section="simulation",
        key="seed",
        current_value=42,
        default_value=42,
    )
    registry.register(field)
    assert registry.get("simulation", "seed") == 42


def test_update_with_validation():
    """Updating a tunable field with a passing validator succeeds."""
    registry = TunableRegistry()
    field = TunableField(
        section="budget",
        key="warning_threshold_pct",
        current_value=80.0,
        default_value=80.0,
        validators=[lambda v: isinstance(v, (int, float)) and 0 <= v <= 100],
    )
    registry.register(field)
    registry.update("budget", "warning_threshold_pct", 90.0)
    assert registry.get("budget", "warning_threshold_pct") == 90.0


def test_update_fails_validation():
    """Updating with a value that fails validation raises ValueError."""
    registry = TunableRegistry()
    field = TunableField(
        section="budget",
        key="warning_threshold_pct",
        current_value=80.0,
        default_value=80.0,
        validators=[lambda v: isinstance(v, (int, float)) and 0 <= v <= 100],
    )
    registry.register(field)
    with pytest.raises(ValueError):
        registry.update("budget", "warning_threshold_pct", 150.0)
    # Value should remain unchanged
    assert registry.get("budget", "warning_threshold_pct") == 80.0


def test_listener_called():
    """Listeners are invoked when a tunable field is updated."""
    registry = TunableRegistry()
    field = TunableField(
        section="simulation",
        key="seed",
        current_value=42,
        default_value=42,
    )
    registry.register(field)

    notifications: list[tuple] = []
    registry.add_listener("simulation", "seed", lambda s, k, v: notifications.append((s, k, v)))

    registry.update("simulation", "seed", 99)
    assert len(notifications) == 1
    assert notifications[0] == ("simulation", "seed", 99)


def test_list_tunable():
    """list_tunable returns all registered fields."""
    registry = TunableRegistry()
    f1 = TunableField(section="a", key="x", current_value=1, default_value=1)
    f2 = TunableField(section="b", key="y", current_value=2, default_value=2)
    registry.register(f1)
    registry.register(f2)
    fields = registry.list_tunable()
    assert len(fields) == 2
    keys = {(f.section, f.key) for f in fields}
    assert ("a", "x") in keys
    assert ("b", "y") in keys
