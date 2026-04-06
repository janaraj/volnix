"""Shared fixtures for reporter tests.

Provides factory functions for creating test events without needing
a real state engine or event bus.
"""

from __future__ import annotations

from datetime import UTC, datetime

from volnix.core.events import (
    AnimatorEvent,
    BudgetExhaustedEvent,
    BudgetWarningEvent,
    CapabilityGapEvent,
    PermissionDeniedEvent,
    PolicyBlockEvent,
    PolicyEscalateEvent,
    PolicyHoldEvent,
    WorldEvent,
)
from volnix.core.types import (
    ActorId,
    EntityId,
    PolicyId,
    ServiceId,
    Timestamp,
    ToolName,
)

_now = datetime(2026, 3, 23, 12, 0, 0, tzinfo=UTC)


def make_ts(tick: int = 0) -> Timestamp:
    """Create a Timestamp with a given tick."""
    return Timestamp(world_time=_now, wall_time=_now, tick=tick)


def make_world_event(
    actor_id: str = "agent-1",
    action: str = "email_send",
    tick: int = 1,
    target_entity: str | None = None,
    service_id: str = "email_svc",
) -> WorldEvent:
    """Create a WorldEvent for testing."""
    return WorldEvent(
        event_type=f"world.{action}",
        timestamp=make_ts(tick),
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        target_entity=EntityId(target_entity) if target_entity else None,
    )


def make_permission_denied(
    actor_id: str = "agent-1",
    action: str = "read_secret",
    reason: str = "not authorized",
    tick: int = 1,
) -> PermissionDeniedEvent:
    """Create a PermissionDeniedEvent for testing."""
    return PermissionDeniedEvent(
        event_type="permission.denied",
        timestamp=make_ts(tick),
        actor_id=ActorId(actor_id),
        action=action,
        reason=reason,
    )


def make_policy_block(
    actor_id: str = "agent-1",
    action: str = "delete_all",
    reason: str = "policy forbids",
    tick: int = 1,
) -> PolicyBlockEvent:
    """Create a PolicyBlockEvent for testing."""
    return PolicyBlockEvent(
        event_type="policy.block",
        timestamp=make_ts(tick),
        policy_id=PolicyId("pol-1"),
        actor_id=ActorId(actor_id),
        action=action,
        reason=reason,
    )


def make_policy_hold(
    actor_id: str = "agent-1",
    action: str = "large_transfer",
    tick: int = 1,
) -> PolicyHoldEvent:
    """Create a PolicyHoldEvent for testing."""
    return PolicyHoldEvent(
        event_type="policy.hold",
        timestamp=make_ts(tick),
        policy_id=PolicyId("pol-2"),
        actor_id=ActorId(actor_id),
        action=action,
        approver_role="supervisor",
        timeout_seconds=300,
        hold_id="hold-1",
    )


def make_policy_escalate(
    actor_id: str = "agent-1",
    action: str = "escalate_request",
    tick: int = 1,
) -> PolicyEscalateEvent:
    """Create a PolicyEscalateEvent for testing."""
    return PolicyEscalateEvent(
        event_type="policy.escalate",
        timestamp=make_ts(tick),
        policy_id=PolicyId("pol-3"),
        actor_id=ActorId(actor_id),
        action=action,
        target_role="supervisor",
        original_actor=ActorId(actor_id),
    )


def make_budget_warning(
    actor_id: str = "agent-1",
    tick: int = 1,
) -> BudgetWarningEvent:
    """Create a BudgetWarningEvent for testing."""
    return BudgetWarningEvent(
        event_type="budget.warning",
        timestamp=make_ts(tick),
        actor_id=ActorId(actor_id),
        budget_type="api_calls",
        threshold_pct=80.0,
        remaining=20.0,
    )


def make_budget_exhausted(
    actor_id: str = "agent-1",
    tick: int = 1,
) -> BudgetExhaustedEvent:
    """Create a BudgetExhaustedEvent for testing."""
    return BudgetExhaustedEvent(
        event_type="budget.exhausted",
        timestamp=make_ts(tick),
        actor_id=ActorId(actor_id),
        budget_type="api_calls",
    )


def make_capability_gap(
    actor_id: str = "agent-1",
    tool: str = "missing_tool",
    tick: int = 1,
) -> CapabilityGapEvent:
    """Create a CapabilityGapEvent for testing."""
    return CapabilityGapEvent(
        event_type="capability.gap",
        timestamp=make_ts(tick),
        actor_id=ActorId(actor_id),
        requested_tool=ToolName(tool),
    )


def make_animator_event(
    actor_id: str = "world",
    sub_type: str = "npc_action",
    content: dict | None = None,
    tick: int = 1,
) -> AnimatorEvent:
    """Create an AnimatorEvent for testing."""
    return AnimatorEvent(
        event_type="animator.event",
        timestamp=make_ts(tick),
        sub_type=sub_type,
        actor_id=ActorId(actor_id),
        content=content or {},
    )
