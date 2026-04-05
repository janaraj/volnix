"""Tests for FeedbackEngine G4b methods -- sync + signals."""
from __future__ import annotations

from unittest.mock import AsyncMock

from volnix.engines.feedback.engine import FeedbackEngine


async def test_signals_without_run_manager(mock_event_bus):
    """Signals returns empty when run_manager not available."""
    engine = FeedbackEngine()
    config = {
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
        "external_sync_enabled": False,
        "signals_enabled": True,
        "signals_max_runs": 10,
        "signals_include_event_logs": False,
    }
    await engine.initialize(config, mock_event_bus)

    signals = await engine.get_local_signals()
    assert signals.total_runs == 0


async def test_sync_disabled_returns_empty(mock_event_bus):
    """Sync methods return empty when external_sync_enabled is False."""
    engine = FeedbackEngine()
    config = {
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
        "external_sync_enabled": False,
        "signals_enabled": True,
        "signals_max_runs": 10,
        "signals_include_event_logs": False,
    }
    await engine.initialize(config, mock_event_bus)

    reports = await engine.check_sync("twilio")
    assert reports == []

    proposal = await engine.propose_sync_update("twilio")
    assert proposal is None


async def test_signals_with_run_manager(mock_event_bus):
    """Signals computes when run_manager is available."""
    engine = FeedbackEngine()

    run_manager = AsyncMock()
    run_manager.list_runs = AsyncMock(return_value=[
        {
            "run_id": "r1",
            "world_def": {"name": "Test", "services": {"email": "x"}},
        },
    ])

    artifact_store = AsyncMock()
    artifact_store.load_artifact = AsyncMock(return_value=[])

    config = {
        "_run_manager": run_manager,
        "_artifact_store": artifact_store,
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
        "external_sync_enabled": False,
        "signals_enabled": True,
        "signals_max_runs": 10,
        "signals_include_event_logs": True,
    }
    await engine.initialize(config, mock_event_bus)

    signals = await engine.get_local_signals()
    assert signals.total_runs == 1
    assert "service_usage" in signals.signals
