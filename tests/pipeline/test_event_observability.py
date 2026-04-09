"""Tests for Gap 2 -- event observability on ALLOW / pass-through pipeline paths.

Verifies that each pipeline step emits the appropriate event in paths that
were previously silent (no events on ALLOW).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.core.context import ActionContext, ResponseProposal
from volnix.core.events import (
    CapabilityResolvedEvent,
    PermissionAllowEvent,
    PolicyFlagEvent,
    ResponderDispatchEvent,
    ValidationFailureEvent,
)
from volnix.core.types import (
    ActorId,
    ActorType,
    EntityId,
    PolicyId,
    ServiceId,
    StateDelta,
    StepVerdict,
)
from volnix.engines.adapter.engine import AgentAdapterEngine
from volnix.engines.permission.engine import PermissionEngine
from volnix.engines.policy.engine import PolicyEngine
from volnix.validation.step import ValidationStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    action: str = "email_send",
    actor_id: str = "agent-1",
    service_id: str = "gmail",
    input_data: dict | None = None,
) -> ActionContext:
    """Create a minimal ActionContext for testing."""
    now = datetime.now(UTC)
    return ActionContext(
        request_id="test-obs-001",
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {},
        world_time=now,
        wall_time=now,
        tick=1,
    )


def _make_registry(*actors: ActorDefinition) -> ActorRegistry:
    reg = ActorRegistry()
    for a in actors:
        reg.register(a)
    return reg


def _make_agent(
    actor_id: str = "agent-1",
    role: str = "support-agent",
    permissions: dict | None = None,
) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role=role,
        permissions=permissions or {},
    )


# ---------------------------------------------------------------------------
# Permission ALLOW events
# ---------------------------------------------------------------------------


class TestPermissionAllowEmitsEvent:
    """PermissionEngine emits PermissionAllowEvent on every ALLOW path."""

    @pytest.mark.asyncio
    async def test_ungoverned_unknown_actor(self):
        """Ungoverned + unknown actor emits reason='ungoverned'."""
        engine = PermissionEngine()
        engine._actor_registry = _make_registry()  # empty
        engine._world_mode = "ungoverned"
        ctx = _make_ctx(actor_id="unknown")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        allow_events = [e for e in result.events if isinstance(e, PermissionAllowEvent)]
        assert len(allow_events) == 1
        assert allow_events[0].reason == "ungoverned"
        assert allow_events[0].actor_id == ActorId("unknown")

    @pytest.mark.asyncio
    async def test_no_registry_emits_ungoverned(self):
        """No actor registry injected emits reason='ungoverned'."""
        engine = PermissionEngine()
        engine._actor_registry = None
        engine._world_mode = "governed"
        ctx = _make_ctx()
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        allow_events = [e for e in result.events if isinstance(e, PermissionAllowEvent)]
        assert len(allow_events) == 1
        assert allow_events[0].reason == "ungoverned"

    @pytest.mark.asyncio
    async def test_no_permissions_defined(self):
        """Actor with empty permissions emits reason='no_permissions_defined'."""
        engine = PermissionEngine()
        engine._actor_registry = _make_registry(_make_agent(permissions={}))
        engine._world_mode = "governed"
        ctx = _make_ctx()
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        allow_events = [e for e in result.events if isinstance(e, PermissionAllowEvent)]
        assert len(allow_events) == 1
        assert allow_events[0].reason == "no_permissions_defined"

    @pytest.mark.asyncio
    async def test_explicit_permission(self):
        """Actor with correct permissions emits reason='explicit_permission'."""
        engine = PermissionEngine()
        engine._actor_registry = _make_registry(
            _make_agent(permissions={"write": "all", "read": "all"})
        )
        engine._world_mode = "governed"
        ctx = _make_ctx()
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        allow_events = [e for e in result.events if isinstance(e, PermissionAllowEvent)]
        assert len(allow_events) == 1
        assert allow_events[0].reason == "explicit_permission"
        assert allow_events[0].event_type == "permission.allow"


# ---------------------------------------------------------------------------
# Policy pass-through events
# ---------------------------------------------------------------------------


class TestPolicyPassthroughEmitsFlag:
    """PolicyEngine emits PolicyFlagEvent(policy_id='none') on pass-through."""

    @pytest.mark.asyncio
    async def test_no_policies_emits_flag(self):
        """No policies defined still emits a flag event."""
        engine = PolicyEngine()
        engine._policies = []
        ctx = _make_ctx()
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        flag_events = [e for e in result.events if isinstance(e, PolicyFlagEvent)]
        assert len(flag_events) == 1
        assert flag_events[0].policy_id == PolicyId("none")
        assert flag_events[0].actor_id == ActorId("agent-1")
        assert flag_events[0].action == "email_send"

    @pytest.mark.asyncio
    async def test_policies_exist_none_triggered(self):
        """Policies exist but none match -- emits flag with policy_id='none'."""
        engine = PolicyEngine()
        engine._policies = [
            {
                "name": "block-payments",
                "trigger": {"action": "payment_create"},
                "enforcement": "block",
            },
        ]
        ctx = _make_ctx(action="email_send")  # won't match payment_create
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        flag_events = [e for e in result.events if isinstance(e, PolicyFlagEvent)]
        assert len(flag_events) == 1
        assert flag_events[0].policy_id == PolicyId("none")


# ---------------------------------------------------------------------------
# Capability resolved events
# ---------------------------------------------------------------------------


class TestCapabilityResolvedEmitsEvent:
    """AdapterEngine emits CapabilityResolvedEvent on ALLOW paths."""

    @pytest.mark.asyncio
    async def test_tier1_resolved(self):
        """Tool found in pack registry -> tier1 event."""
        pack_registry = MagicMock()
        pack_registry.has_tool.return_value = True
        engine = AgentAdapterEngine()
        engine._config = {}
        engine._bus = MagicMock()
        engine._pack_registry = pack_registry

        ctx = _make_ctx(action="email_send")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        resolved = [e for e in result.events if isinstance(e, CapabilityResolvedEvent)]
        assert len(resolved) == 1
        assert resolved[0].resolved_tier == "tier1"
        assert resolved[0].requested_tool == "email_send"
        assert resolved[0].event_type == "capability.resolved"

    @pytest.mark.asyncio
    async def test_tier2_resolved(self):
        """Tool found in profile registry -> tier2 event."""
        pack_registry = MagicMock()
        pack_registry.has_tool.return_value = False  # not in tier1

        profile = MagicMock()
        profile.service_name = "zendesk"
        profile_registry = MagicMock()
        profile_registry.get_profile_for_action.return_value = profile

        engine = AgentAdapterEngine()
        engine._config = {}
        engine._bus = MagicMock()
        engine._pack_registry = pack_registry
        engine._profile_registry = profile_registry

        ctx = _make_ctx(action="create_ticket")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        resolved = [e for e in result.events if isinstance(e, CapabilityResolvedEvent)]
        assert len(resolved) == 1
        assert resolved[0].resolved_tier == "tier2"
        assert resolved[0].service_id == "zendesk"

    @pytest.mark.asyncio
    async def test_passthrough_resolved(self):
        """No pack registry -> passthrough event."""
        engine = AgentAdapterEngine()
        engine._config = {}
        engine._bus = MagicMock()
        engine._pack_registry = None

        ctx = _make_ctx(action="email_send")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        resolved = [e for e in result.events if isinstance(e, CapabilityResolvedEvent)]
        assert len(resolved) == 1
        assert resolved[0].resolved_tier == "passthrough"


# ---------------------------------------------------------------------------
# Responder dispatch events (basic coverage -- full tier tests need pack setup)
# ---------------------------------------------------------------------------


class TestResponderDispatchEmitsEvent:
    """ResponderDispatchEvent is emitted -- tested via integration-level context."""

    @pytest.mark.asyncio
    async def test_event_type_fields(self):
        """Verify ResponderDispatchEvent can be constructed with expected fields."""
        from volnix.core.types import Timestamp

        now = datetime.now(UTC)
        event = ResponderDispatchEvent(
            event_type="responder.dispatch",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            actor_id=ActorId("agent-1"),
            action="email_send",
            fidelity_tier=1,
            service_id="gmail",
        )
        assert event.fidelity_tier == 1
        assert event.action == "email_send"
        assert event.service_id == "gmail"
        assert event.profile_name == ""

    @pytest.mark.asyncio
    async def test_tier2_event_with_profile(self):
        """ResponderDispatchEvent can carry profile_name for tier2."""
        from volnix.core.types import Timestamp

        now = datetime.now(UTC)
        event = ResponderDispatchEvent(
            event_type="responder.dispatch",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            actor_id=ActorId("agent-1"),
            action="create_ticket",
            fidelity_tier=2,
            profile_name="zendesk",
            service_id="zendesk",
        )
        assert event.fidelity_tier == 2
        assert event.profile_name == "zendesk"


# ---------------------------------------------------------------------------
# Validation failure events
# ---------------------------------------------------------------------------


class TestValidationFailureEmitsEvent:
    """ValidationStep emits ValidationFailureEvent on ERROR."""

    @pytest.mark.asyncio
    async def test_structural_error_emits_failure_event(self):
        """StateDelta with missing entity_type produces a ValidationFailureEvent."""
        step = ValidationStep()
        ctx = _make_ctx()
        ctx.response_proposal = ResponseProposal(
            proposed_state_deltas=[
                StateDelta(
                    entity_type="",
                    entity_id=EntityId("e1"),
                    operation="create",
                    fields={"name": "x"},
                ),
            ],
        )
        result = await step.execute(ctx)

        assert result.verdict == StepVerdict.ERROR
        fail_events = [e for e in result.events if isinstance(e, ValidationFailureEvent)]
        assert len(fail_events) == 1
        assert fail_events[0].failure_type == "pipeline_proposal"
        assert "errors" in fail_events[0].details
        assert fail_events[0].event_type == "validation.failure"

    @pytest.mark.asyncio
    async def test_unknown_operation_emits_failure_event(self):
        """StateDelta with unknown operation produces a ValidationFailureEvent."""
        step = ValidationStep()
        ctx = _make_ctx()
        ctx.response_proposal = ResponseProposal(
            proposed_state_deltas=[
                StateDelta(
                    entity_type="widget",
                    entity_id=EntityId("w1"),
                    operation="upsert",
                    fields={"name": "x"},
                ),
            ],
        )
        result = await step.execute(ctx)

        assert result.verdict == StepVerdict.ERROR
        fail_events = [e for e in result.events if isinstance(e, ValidationFailureEvent)]
        assert len(fail_events) == 1
        assert any("upsert" in str(e) for e in fail_events[0].details.get("errors", []))

    @pytest.mark.asyncio
    async def test_valid_proposal_no_failure_event(self):
        """Valid proposal produces ALLOW with no ValidationFailureEvent."""
        step = ValidationStep()
        ctx = _make_ctx()
        ctx.response_proposal = ResponseProposal(
            response_body={"id": "w1"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="widget",
                    entity_id=EntityId("w1"),
                    operation="create",
                    fields={"name": "x"},
                ),
            ],
        )
        result = await step.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        fail_events = [e for e in result.events if isinstance(e, ValidationFailureEvent)]
        assert len(fail_events) == 0
