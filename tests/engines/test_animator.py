"""Tests for terrarium.engines.animator — world tick, scheduled/organic events.

Full test suites are in tests/engines/animator/ — this file contains
basic smoke tests for backwards compatibility.
"""
import pytest
from terrarium.engines.animator.engine import WorldAnimatorEngine
from terrarium.engines.animator.config import AnimatorConfig
from terrarium.engines.animator.context import AnimatorContext
from terrarium.engines.animator.generator import OrganicGenerator
from terrarium.scheduling.scheduler import WorldScheduler


def test_animator_imports():
    """All animator module components are importable."""
    assert WorldAnimatorEngine is not None
    assert AnimatorConfig is not None
    assert AnimatorContext is not None
    assert OrganicGenerator is not None
    assert WorldScheduler is not None


def test_animator_config_defaults():
    """AnimatorConfig has sensible defaults."""
    config = AnimatorConfig()
    assert config.enabled is True
    assert config.creativity == "medium"
    assert config.event_frequency == "moderate"
    assert config.creativity_budget_per_tick == 3
    assert config.tick_interval_seconds == 60.0


def test_scheduler_empty():
    """Empty scheduler has zero pending."""
    scheduler = WorldScheduler()
    assert scheduler.pending_count == 0
