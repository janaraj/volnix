"""Tests for FeedbackEngine -- integration of all feedback components."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from volnix.core.events import CapabilityGapEvent
from volnix.core.types import ActorId, Timestamp, ToolName
from volnix.engines.feedback.engine import FeedbackEngine


def _make_gap_event(
    actor: str = "agent-1", tool: str = "jira_create_issue"
) -> CapabilityGapEvent:
    now = datetime.now(UTC)
    return CapabilityGapEvent(
        event_type="capability.gap",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=1),
        actor_id=ActorId(actor),
        requested_tool=ToolName(tool),
    )


async def test_engine_initializes(
    annotation_db, mock_event_bus, mock_ledger
):
    """FeedbackEngine lazy-initializes when deps are in _config."""
    engine = FeedbackEngine()

    conn_mgr = AsyncMock()
    conn_mgr.get_connection = AsyncMock(return_value=annotation_db)

    config = {
        "_conn_mgr": conn_mgr,
        "_artifact_store": AsyncMock(),
        "_profile_registry": MagicMock(),
        "_profile_loader": MagicMock(),
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
    }

    await engine.initialize(config, mock_event_bus)
    # C1 fix: _on_initialize sets _initialized=False; deps not there yet
    # Trigger lazy init explicitly (simulates first use)
    await engine._ensure_initialized()

    assert engine._annotation_store is not None
    assert engine._capture is not None
    assert engine._promoter is not None


async def test_auto_annotate_capability_gap(
    annotation_db, mock_event_bus, mock_ledger
):
    """Capability gap events are auto-annotated when configured."""
    engine = FeedbackEngine()

    conn_mgr = AsyncMock()
    conn_mgr.get_connection = AsyncMock(return_value=annotation_db)

    # Profile registry returns None for unknown tools
    # so the engine falls back to prefix extraction
    profile_registry = MagicMock()
    profile_registry.get_profile_for_action = MagicMock(return_value=None)
    profile_registry.list_profiles = MagicMock(return_value=[])

    config = {
        "_conn_mgr": conn_mgr,
        "_artifact_store": AsyncMock(),
        "_profile_registry": profile_registry,
        "_profile_loader": MagicMock(),
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
    }

    await engine.initialize(config, mock_event_bus)
    engine._ledger = mock_ledger

    gap_event = _make_gap_event(tool="jira_create_issue")
    await engine._handle_event(gap_event)

    annotations = await engine._annotation_store.get_by_service("jira")
    assert len(annotations) == 1
    assert "capability gap" in annotations[0]["text"].lower()
    assert "jira_create_issue" in annotations[0]["text"]


async def test_add_annotation_records_ledger(
    annotation_db, mock_event_bus, mock_ledger
):
    """Adding an annotation records a typed ledger entry."""
    engine = FeedbackEngine()

    conn_mgr = AsyncMock()
    conn_mgr.get_connection = AsyncMock(return_value=annotation_db)

    config = {
        "_conn_mgr": conn_mgr,
        "_artifact_store": AsyncMock(),
        "_profile_registry": MagicMock(),
        "_profile_loader": MagicMock(),
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
    }

    await engine.initialize(config, mock_event_bus)
    engine._ledger = mock_ledger

    seq = await engine.add_annotation(
        "stripe", "Refunds >180 days fail", "user"
    )
    assert seq >= 1

    # C2 fix: typed entry, not generic LedgerEntry
    assert mock_ledger.append.call_count == 1
    entry = mock_ledger.entries[0]
    assert entry.entry_type == "feedback.annotation"
    assert entry.service_id == "stripe"
    assert entry.annotation_text == "Refunds >180 days fail"


async def test_engine_without_deps(mock_event_bus):
    """Engine initializes gracefully without optional dependencies."""
    engine = FeedbackEngine()

    config = {
        "auto_annotate_gaps": True,
        "promotion_min_annotations": 1,
        "promotion_min_operations": 3,
        "promotion_max_error_rate": 0.3,
    }

    await engine.initialize(config, mock_event_bus)
    await engine._ensure_initialized()

    assert engine._annotation_store is None
    assert engine._capture is None
    assert engine._promoter is None
